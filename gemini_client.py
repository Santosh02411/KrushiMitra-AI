"""
gemini_client.py
------------------
One small, dependency-free (requests only) client for the three things
KrushiMitra AI uses Google Gemini for:

  * generate()           - grounded chat answers + Decision Engine explanations
  * embed()              - embeddings for the RAG knowledge base
  * generate_with_image() - multimodal leaf-photo assessment

Design rules:
  * The API key is sent in the ``x-goog-api-key`` header, never in the URL,
    so it can't leak into access logs or tracebacks.
  * Every method returns a plain dict ``{"ok": bool, ...}`` and never raises:
    callers decide how to degrade. Without a key everything returns
    ``{"ok": False, "reason": "not_configured"}`` - nothing is faked.
  * Google retires model IDs on a schedule, so each call walks a fallback list
    and only moves on when a model returns 404 (retired / renamed).
"""

import base64
import os

import requests

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

DEFAULT_CHAT_MODEL = "gemini-2.5-flash"
CHAT_FALLBACKS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]

DEFAULT_EMBED_MODEL = "gemini-embedding-001"
EMBED_FALLBACKS = ["gemini-embedding-001", "text-embedding-004"]
EMBED_DIM = 768  # gemini-embedding-001 supports reduced output dimensionality
EMBED_BATCH = 50

REQUEST_TIMEOUT = 40


def _unique(seq):
    seen = set()
    for item in seq:
        if item and item not in seen:
            seen.add(item)
            yield item


class GeminiClient:
    def __init__(self, api_key=None, chat_model=None, embed_model=None):
        self.api_key = (api_key or "").strip() or None
        self.chat_model = chat_model or DEFAULT_CHAT_MODEL
        self.embed_model = embed_model or DEFAULT_EMBED_MODEL
        # Remember which embedding model actually worked so vectors stored in
        # the knowledge base and query vectors always come from the same one.
        self._working_embed_model = None

    # ------------------------------------------------------------------ #
    @property
    def configured(self):
        return bool(self.api_key)

    def _headers(self):
        return {"content-type": "application/json", "x-goog-api-key": self.api_key}

    @staticmethod
    def _api_error(resp):
        try:
            return resp.json().get("error", {}).get("message", "") or resp.text[:200]
        except Exception:
            return resp.text[:200]

    def _chat_models(self):
        return list(_unique([self.chat_model] + CHAT_FALLBACKS))

    # ------------------------------------------------------------------ #
    # Text generation
    # ------------------------------------------------------------------ #
    def generate(self, contents, system=None, max_tokens=1500, temperature=0.3):
        """contents: Gemini ``contents`` list ([{"role": "user"|"model", "parts": [...]}])."""
        if not self.configured:
            return {"ok": False, "reason": "not_configured",
                    "error": "Gemini isn't configured - add GEMINI_API_KEY to .env "
                             "(free key: https://aistudio.google.com/apikey)."}

        last_error = None
        tried = []
        for model_id in self._chat_models():
            tried.append(model_id)
            body = {
                "contents": contents,
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
            }
            if system:
                body["system_instruction"] = {"parts": [{"text": system}]}
            # Gemini 2.5 "thinking" tokens count against maxOutputTokens and can
            # swallow the whole budget on short answers; these answers don't
            # need it. If a model rejects the field we retry without it.
            if "2.5" in model_id and "pro" not in model_id:
                body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}

            result = self._post_generate(model_id, body)
            if result.get("retry_without_thinking"):
                body["generationConfig"].pop("thinkingConfig", None)
                result = self._post_generate(model_id, body)

            if result.get("model_missing"):
                last_error = f"Model '{model_id}' not found (retired?)."
                continue
            result.pop("retry_without_thinking", None)
            result.pop("model_missing", None)
            if result.get("ok"):
                result["model_used"] = model_id
            return result

        return {"ok": False, "reason": "no_model",
                "error": f"None of the Gemini models responded (tried: {', '.join(tried)}). "
                         f"{last_error or ''} Google periodically retires model IDs - check "
                         f"https://ai.google.dev/gemini-api/docs/models and update CHAT_MODEL in .env."}

    def _post_generate(self, model_id, body):
        try:
            resp = requests.post(f"{API_ROOT}/{model_id}:generateContent",
                                 headers=self._headers(), json=body, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            return {"ok": False, "reason": "timeout", "error": "Gemini took too long to respond - try again."}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "reason": "network", "error": f"Could not reach Gemini ({type(e).__name__})."}

        if resp.status_code == 404:
            return {"ok": False, "model_missing": True}
        if resp.status_code == 429:
            return {"ok": False, "reason": "rate_limit",
                    "error": "Gemini rate limit hit - wait a moment and try again."}
        if resp.status_code in (401, 403):
            return {"ok": False, "reason": "auth",
                    "error": "Gemini rejected the API key - check GEMINI_API_KEY in .env."}
        if resp.status_code == 400:
            detail = self._api_error(resp)
            if "thinking" in detail.lower() and "thinkingConfig" in body["generationConfig"]:
                return {"ok": False, "retry_without_thinking": True}
            return {"ok": False, "reason": "bad_request", "error": f"Gemini API error: {detail}"}
        if not resp.ok:
            return {"ok": False, "reason": "api_error",
                    "error": f"Gemini API error ({resp.status_code}): {self._api_error(resp)}"}

        try:
            data = resp.json()
        except ValueError:
            return {"ok": False, "reason": "bad_response", "error": "Gemini returned an unreadable response."}

        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            return {"ok": False, "reason": "blocked" if block else "empty",
                    "error": f"Gemini declined to answer ({block})." if block else "Gemini returned no response."}
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            return {"ok": False, "reason": "empty", "error": "Gemini returned an empty response."}
        return {"ok": True, "text": text,
                "finish_reason": candidates[0].get("finishReason")}

    # ------------------------------------------------------------------ #
    # Multimodal (leaf photo)
    # ------------------------------------------------------------------ #
    def generate_with_image(self, prompt, image_bytes, mime_type, system=None, max_tokens=1200):
        parts = [{"text": prompt},
                 {"inline_data": {"mime_type": mime_type,
                                  "data": base64.b64encode(image_bytes).decode("ascii")}}]
        return self.generate([{"role": "user", "parts": parts}], system=system,
                             max_tokens=max_tokens, temperature=0.2)

    # ------------------------------------------------------------------ #
    # Embeddings
    # ------------------------------------------------------------------ #
    def embed(self, texts, task_type="RETRIEVAL_DOCUMENT"):
        """Return {"ok": True, "vectors": [[...]], "model": str} or {"ok": False, ...}."""
        if not self.configured:
            return {"ok": False, "reason": "not_configured"}
        if not texts:
            return {"ok": True, "vectors": [], "model": self._working_embed_model or self.embed_model}

        candidates = ([self._working_embed_model] if self._working_embed_model
                      else list(_unique([self.embed_model] + EMBED_FALLBACKS)))
        last_error = "embedding failed"
        for model_id in candidates:
            vectors, status, err = self._embed_with_model(model_id, texts, task_type)
            if status == 404:
                last_error = f"Embedding model '{model_id}' not found."
                continue
            if vectors is None:
                return {"ok": False, "reason": "api_error", "error": err}
            self._working_embed_model = model_id
            return {"ok": True, "vectors": vectors, "model": model_id}
        return {"ok": False, "reason": "no_model", "error": last_error}

    def _embed_with_model(self, model_id, texts, task_type):
        vectors = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start:start + EMBED_BATCH]
            requests_body = []
            for t in batch:
                item = {"model": f"models/{model_id}", "content": {"parts": [{"text": t}]},
                        "taskType": task_type}
                if "embedding-001" in model_id:
                    item["outputDimensionality"] = EMBED_DIM
                requests_body.append(item)
            try:
                resp = requests.post(f"{API_ROOT}/{model_id}:batchEmbedContents",
                                     headers=self._headers(), json={"requests": requests_body},
                                     timeout=REQUEST_TIMEOUT)
            except requests.exceptions.RequestException as e:
                return None, None, f"Could not reach Gemini embeddings ({type(e).__name__})."
            if resp.status_code == 404:
                return None, 404, "not found"
            if not resp.ok:
                return None, resp.status_code, f"Embedding API error ({resp.status_code}): {self._api_error(resp)}"
            try:
                embeddings = resp.json().get("embeddings", [])
                batch_vectors = [e["values"] for e in embeddings]
            except (ValueError, KeyError, TypeError):
                return None, None, "Embedding API returned an unreadable response."
            if len(batch_vectors) != len(batch):
                return None, None, "Embedding API returned the wrong number of vectors."
            vectors.extend(batch_vectors)
        return vectors, 200, None


def client_from_env():
    return GeminiClient(
        api_key=os.getenv("GEMINI_API_KEY"),
        chat_model=os.getenv("CHAT_MODEL") or None,
        embed_model=os.getenv("EMBED_MODEL") or None,
    )
