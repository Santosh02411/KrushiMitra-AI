"""
vision_service.py
-------------------
Leaf-photo handling for the Disease Check page.

What is real here
  * Uploads are validated by their actual bytes (JPEG/PNG/WEBP magic numbers),
    size-capped, stored under a random name OUTSIDE the public static folder,
    and served only to the account that uploaded them.
  * When GEMINI_API_KEY is set, the photo is sent to Gemini's multimodal model
    and the structured reply is shown - clearly labelled as an AI visual
    assessment, not a laboratory diagnosis. Its suggested conditions are
    cross-referenced with the app's symptom reference so the treatment text
    shown comes from the reference table, not from the model.
  * Without a key, the photo is only saved for the farmer's records and the
    page says it was NOT analysed. There is no pretend classifier.
"""

import json
import os
import re
import uuid

from disease_reference import DISEASE_REFERENCE

MAX_IMAGE_BYTES = 6 * 1024 * 1024

_MAGIC = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
]


class ImageError(ValueError):
    """Safe-to-show validation problem."""


def sniff_image(data):
    """Return (mime, ext) from the file's real bytes, or raise ImageError."""
    if not data:
        raise ImageError("The file is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError(f"Photo is too large (limit {MAX_IMAGE_BYTES // (1024 * 1024)} MB).")
    for magic, mime, ext in _MAGIC:
        if data.startswith(magic):
            return mime, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise ImageError("That file isn't a JPEG, PNG or WEBP image.")


ASSESS_SYSTEM = (
    "You are a plant-pathology assistant helping a smallholder farmer in India. You look at one photo of a "
    "crop leaf/plant and describe what is visible. You are NOT giving a diagnosis - only visual observations "
    "and possibilities, with honest uncertainty. If the image is not a plant, is blurry, or too dark, say so "
    "and do not guess. Reply with ONLY a JSON object, no prose, no code fences."
)

ASSESS_PROMPT = """Crop (as stated by the farmer, may be blank): {crop}

Return JSON with exactly these keys:
{{
  "is_plant_photo": true/false,
  "image_quality": "good" | "fair" | "poor",
  "observations": ["short factual things you can see (colour, spots, pattern, wilting, coating)"],
  "possible_conditions": [
    {{"name": "common name of disease, pest damage or deficiency", "likelihood": "low" | "medium" | "high",
      "reasoning": "one sentence tied to what is visible"}}
  ],
  "looks_healthy": true/false,
  "what_would_help_confirm": ["photos or checks that would reduce uncertainty"]
}}
Give at most 3 possible_conditions, ordered most to least likely. If the leaf looks healthy return an empty
list and looks_healthy true. Never include pesticide doses."""


def _parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def _tokens(s):
    return set(re.findall(r"[a-z]{4,}", s.lower()))


def match_reference(crop, condition_name):
    """Find the symptom-reference entry (if any) that corresponds to a condition
    name the model suggested. Pure string matching on the reference table."""
    entries = DISEASE_REFERENCE.get((crop or "").strip().lower(), [])
    want = _tokens(condition_name)
    best, best_score = None, 0
    for e in entries:
        have = _tokens(e["disease"])
        score = len(want & have)
        if score > best_score:
            best, best_score = e, score
    return best if best_score else None


def analyse_photo(gemini, data, mime, crop=None):
    """Run the Gemini vision assessment. Returns a dict that always states what
    kind of result it is."""
    if not gemini.configured:
        return {"analysed": False, "reason": "not_configured",
                "message": "Photo saved, but NOT analysed - AI photo assessment needs a GEMINI_API_KEY. "
                           "Use the symptom checker for a reference match."}
    res = gemini.generate_with_image(ASSESS_PROMPT.format(crop=crop or "not stated"), data, mime,
                                     system=ASSESS_SYSTEM)
    if not res.get("ok"):
        return {"analysed": False, "reason": res.get("reason", "error"),
                "message": f"Photo saved, but the AI assessment failed: {res.get('error', 'unknown error')}"}
    parsed = _parse_json(res["text"])
    if not parsed:
        return {"analysed": False, "reason": "bad_output",
                "message": "Photo saved, but the AI returned an unreadable answer - try again or use the "
                           "symptom checker."}

    conditions = []
    for c in (parsed.get("possible_conditions") or [])[:3]:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        ref = match_reference(crop, str(c["name"]))
        conditions.append({
            "name": str(c["name"])[:120],
            "likelihood": c.get("likelihood") if c.get("likelihood") in ("low", "medium", "high") else "low",
            "reasoning": str(c.get("reasoning", ""))[:300],
            "reference": ({"disease": ref["disease"], "cause": ref["cause"], "treatment": ref["treatment"],
                           "recommended_fungicide": ref["recommended_fungicide"]} if ref else None),
        })
    return {
        "analysed": True, "model_used": res.get("model_used"),
        "label": "AI visual assessment (Gemini vision) - possibilities, not a diagnosis",
        "is_plant_photo": bool(parsed.get("is_plant_photo", True)),
        "image_quality": parsed.get("image_quality") if parsed.get("image_quality") in ("good", "fair", "poor") else "fair",
        "observations": [str(o)[:200] for o in (parsed.get("observations") or [])[:6]],
        "possible_conditions": conditions,
        "looks_healthy": bool(parsed.get("looks_healthy", False)),
        "what_would_help_confirm": [str(o)[:200] for o in (parsed.get("what_would_help_confirm") or [])[:4]],
        "disclaimer": "Image assessment can be wrong, especially for look-alike conditions. Confirm with a local "
                      "Krishi Vigyan Kendra / agriculture officer before spraying, and follow the product label.",
    }


def new_filename(ext):
    return f"{uuid.uuid4().hex}.{ext}"
