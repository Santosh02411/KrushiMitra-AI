// assistant.js — RAG assistant page. Every API string is escaped before it reaches innerHTML.
const AS = { history: [], busy: false };
const $a = (id) => document.getElementById(id);
const ah = (x) => escapeHtml(x);

async function initAssistantPage() {
  $a('as-form').addEventListener('submit', (e) => { e.preventDefault(); askQuestion($a('as-input').value); });
  document.querySelectorAll('#as-suggest .preset').forEach(b => b.addEventListener('click', () => askQuestion(b.textContent)));
  $a('as-reset').addEventListener('click', () => {
    AS.history = [];
    $a('as-scroll').innerHTML = '<div class="msg bot">New conversation started. What would you like to know?</div>';
  });
  const drop = $a('as-drop'), file = $a('as-file');
  drop.addEventListener('click', () => file.click());
  file.addEventListener('change', () => { if (file.files[0]) uploadDoc(file.files[0]); file.value = ''; });
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('drag'); }));
  drop.addEventListener('drop', (e) => { if (e.dataTransfer.files[0]) uploadDoc(e.dataTransfer.files[0]); });
  await refreshKb();
}

async function refreshKb() {
  try {
    const [st, docs] = await Promise.all([
      fetch('/api/assistant/status', { credentials: 'include' }).then(r => r.json()),
      fetch('/api/assistant/documents', { credentials: 'include' }).then(r => r.json()),
    ]);
    if (st.success) {
      $a('as-mode').textContent = `· ${st.retrieval_mode}${st.generation_available ? '' : ' · AI generation off'}`;
      $a('as-stats').innerHTML = `<div class="kb-stats"><div><b>${ah(st.documents)}</b><span>documents</span></div><div><b>${ah(st.chunks)}</b><span>passages</span></div><div><b>${ah(st.embedded_chunks)}</b><span>embedded</span></div></div>` +
        `Retrieval: <b>${ah(st.retrieval_mode)}</b>.` + (st.generation_available ? '' : ' Add GEMINI_API_KEY to enable AI-written answers and semantic search.');
    }
    if (docs.success) {
      const builtin = docs.documents.filter(d => !d.deletable), mine = docs.documents.filter(d => d.deletable);
      $a('as-docs').innerHTML =
        (mine.length ? '<b style="font-size:.8rem">Uploaded documents</b>' + mine.map(docRow).join('') : '<div class="hint">No uploaded documents yet.</div>') +
        `<details style="margin-top:10px"><summary class="hint" style="cursor:pointer">Built-in references (${builtin.length})</summary>${builtin.map(docRow).join('')}</details>`;
      document.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => deleteDoc(b.dataset.del)));
    }
    return st;
  } catch (e) { $a('as-stats').textContent = 'Could not load the knowledge base status.'; }
}

function docRow(d) {
  return `<div class="doc"><div>${ah(d.title)}<small>${ah(d.n_chunks)} passages${d.scope === 'global' && d.deletable ? ' · shared' : ''}</small></div>${d.deletable ? `<button type="button" data-del="${ah(d.id)}">Delete</button>` : ''}</div>`;
}

async function deleteDoc(id) {
  if (!confirm('Delete this document from the knowledge base?')) return;
  await fetch(`/api/assistant/documents/${encodeURIComponent(id)}`, { method: 'DELETE', credentials: 'include' });
  refreshKb();
}

async function uploadDoc(file) {
  const st = $a('as-upload-status'); st.className = 'location-status'; st.textContent = `Uploading ${file.name}…`;
  const fd = new FormData(); fd.append('file', file);
  if ($a('as-shared') && $a('as-shared').checked) fd.append('shared', '1');
  try {
    const res = await fetch('/api/assistant/documents', { method: 'POST', credentials: 'include', body: fd });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Upload failed.');
    st.className = 'location-status ok';
    st.textContent = `Added “${data.title}” — ${data.chunks} passages. ${data.embedding_status === 'processing' ? 'Creating embeddings…' : 'Keyword search only (no Gemini key).'}`;
    await refreshKb();
    if (data.embedding_status === 'processing') pollEmbeddings();
  } catch (e) { st.className = 'location-status warn'; st.textContent = e.message; }
}

async function pollEmbeddings(tries = 0) {
  if (tries > 20) return;
  const st = await refreshKb();
  if (st && st.embedded_chunks < st.chunks) setTimeout(() => pollEmbeddings(tries + 1), 3500);
}

function addMsg(cls, html) {
  const el = document.createElement('div'); el.className = 'msg ' + cls; el.innerHTML = html;
  $a('as-scroll').appendChild(el); $a('as-scroll').scrollTop = $a('as-scroll').scrollHeight; return el;
}

function formatAnswer(text) {
  return ah(text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\[(\d{1,2})\]/g, '<span class="cite" data-n="$1">$1</span>');
}

async function askQuestion(q) {
  q = (q || '').trim();
  if (!q || AS.busy) return;
  AS.busy = true; $a('as-send').disabled = true; $a('as-input').value = '';
  addMsg('user', ah(q));
  const typing = addMsg('bot', '<div class="typing"><span></span><span></span><span></span></div>');
  try {
    const res = await fetch('/api/assistant/ask', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: q, history: AS.history.slice(-8), language: (typeof getCurrentLang === 'function' ? getCurrentLang() : 'en') }) });
    const d = await res.json();
    typing.remove();
    if (!d.success) { addMsg('note', ah(d.error || 'Something went wrong.')); return; }
    AS.history.push({ role: 'user', content: q }, { role: 'assistant', content: d.reply });
    const badges = [];
    if (!d.generated) badges.push('<span class="prov prov-reference">extractive — not AI-written</span>');
    else if (d.grounded) badges.push(`<span class="prov prov-live">grounded in ${d.sources.length} source${d.sources.length === 1 ? '' : 's'}</span>`);
    else badges.push('<span class="prov prov-unavailable">not found in knowledge base</span>');
    badges.push(`<span class="prov prov-reference">${ah(d.retrieval_mode)}</span>`);
    const rel = (s) => Math.max(4, Math.min(100, Math.round((s.semantic_score !== null && s.semantic_score !== undefined ? s.semantic_score : Math.min(1, s.keyword_score * 3)) * 100)));
    const src = (d.sources || []).map(s => `<div class="src" data-src="${ah(s.n)}"><span class="tag">${ah(s.n)}</span><b>${ah(s.title)}</b>
      <div class="relbar"><div style="width:${rel(s)}%"></div></div>
      <span class="hint">relevance ${s.semantic_score !== null && s.semantic_score !== undefined ? 'semantic ' + ah(s.semantic_score) + ' · ' : ''}keyword ${ah(s.keyword_score)}</span><div class="snip">${ah(s.snippet)}</div></div>`).join('');
    const rewritten = d.search_query && d.search_query.trim() !== q;
    const trace = `<div class="trace"><span class="st">① ${rewritten ? 'follow-up rewritten → “' + ah(d.search_query.slice(0, 60)) + '”' : 'question → search query'}</span><span class="ar">→</span>
      <span class="st">② ${ah((d.sources || []).length)} passage${(d.sources || []).length === 1 ? '' : 's'} retrieved (${ah(d.retrieval_mode)})</span><span class="ar">→</span>
      <span class="st">③ ${d.generated ? 'Gemini answer, cited' : 'passages shown (no AI writing)'}</span></div>`;
    const el = addMsg('bot', formatAnswer(d.reply) + `<div class="badge-row">${badges.join('')}</div>` + trace + (src ? `<div class="src-list"><b style="font-size:.75rem">Sources (click to expand)</b>${src}</div>` : ''));
    el.querySelectorAll('.src').forEach(s => s.addEventListener('click', () => s.classList.toggle('open')));
    el.querySelectorAll('.cite').forEach(c => c.addEventListener('click', () => { const t = el.querySelector(`.src[data-src="${c.dataset.n}"]`); if (t) { t.classList.add('open'); t.scrollIntoView({ block: 'nearest' }); } }));
  } catch (e) {
    typing.remove(); addMsg('note', 'Could not reach the assistant. Check your connection and try again.');
  } finally { AS.busy = false; $a('as-send').disabled = false; $a('as-input').focus(); }
}
