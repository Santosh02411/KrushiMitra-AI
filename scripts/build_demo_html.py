"""
build_demo_html.py - regenerates demo/KrushiMitra_AI_Demo.html.

The demo is ONE self-contained HTML file (no server, no internet, no keys) that walks through the
whole product. Its content is not hand-written: this script runs the real app in-process, captures
real outputs of the real models (plans, dashboard, knowledge-base retrieval, symptom matching) and
embeds them. Only the weather is a fixed sample forecast, because a static file can't call a live
weather API - the demo says so on screen.

    python scripts/build_demo_html.py
"""
import json, os, re, sys, tempfile
from datetime import date, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "demo.db")
os.environ["SECRET_KEY"] = "demo-build"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
os.environ.pop("GEMINI_API_KEY", None)

import app as A, decision_engine as DE

def day(i, rain, temp, hum, wind, w):
    return {"date": (date.today() + timedelta(days=i)).isoformat(), "temperature": temp, "humidity": hum,
            "weather": w, "rainfall": rain, "wind_speed": wind, "uv_index": 8}
FORECAST = [day(0, 0, 31, 60, 10, "clear sky"), day(1, 0, 33, 55, 12, "partly cloudy"), day(2, 18, 28, 88, 12, "moderate rain"),
            day(3, 2, 29, 75, 10, "partly cloudy"), day(4, 0, 39, 40, 28, "clear sky"), day(5, 40, 26, 92, 15, "thunderstorm"),
            day(6, 0, 30, 65, 9, "partly cloudy")]
CUR = {"location": "Sample location", "temperature": 29, "humidity": 65, "weather": "partly cloudy", "wind_speed": 8,
       "rainfall": 0, "source": "open-meteo.com (live)"}
ws = A.weather_service
ws.get_current_weather_by_coords = lambda *a, **k: CUR; ws.get_forecast_by_coords = lambda *a, **k: FORECAST
ws.get_current_weather = lambda *a, **k: CUR; ws.get_forecast = lambda *a, **k: FORECAST
ws._geocode = lambda loc: {"lat": 15.85, "lon": 74.5, "name": loc, "country": "India"}
DE.fetch_recent_monthly_rainfall = lambda *a, **k: 96.0

PRESETS = {
  "chickpea": {"label": "Chickpea · Madhya Pradesh · Rabi", "body": {"state": "Madhya Pradesh", "location": "Indore, Madhya Pradesh", "season": "Rabi", "area_acres": 4, "n": 40, "p": 68, "k": 80, "ph": 7.2, "temperature": 19, "humidity": 17, "monthly_rainfall_mm": 80, "expenses": {"seeds": 7000, "labour": 9000}}},
  "maize": {"label": "Maize · Karnataka · Kharif", "body": {"state": "Karnataka", "location": "Belagavi, Karnataka", "season": "Kharif", "area_acres": 2.5, "n": 78, "p": 48, "k": 20, "ph": 6.2, "temperature": 23, "humidity": 65, "monthly_rainfall_mm": 85, "manual_price_rs_per_quintal": 2100, "expenses": {"seeds": 4200, "labour": 8000}}},
  "nosoil": {"label": "No soil test · Punjab · Rabi (graceful fallback)", "body": {"state": "Punjab", "season": "Rabi", "area_acres": 2}},
}
c = A.app.test_client(); c.get("/demo")
plans = {}
for k, p in PRESETS.items():
    plan = c.post("/api/decision-engine/plan", json=p["body"]).json
    assert plan.get("success"), plan
    plans[k] = plan
c.post(f"/api/decision-engine/plans/{plans['maize']['plan_id']}/save")
overview = c.get("/api/dashboard/overview").json
assert overview["success"]

QUESTIONS = ["Which diseases affect cotton and how are they managed?", "Which fertilizer schedule suits rice?",
             "Which government schemes offer crop insurance?", "What is the best pizza recipe in Rome?"]
chat = []
for q in QUESTIONS:
    r = c.post("/api/assistant/ask", json={"message": q}).json
    chat.append({"q": q, "r": r})
disease = c.post("/api/disease-check", json={"crop": "rice", "symptoms": ["diamond-shaped grey/white lesions with brown margins on leaves"]}).json["result"]
status = c.get("/api/assistant/status").json
info = A.crop_model.get_model_info()

def read(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()
css = re.sub(r"@import url\([^)]*\);", "", read("static/css/style.css")) + "\n" + read("static/css/krushimitra.css")
common = read("static/js/common.js"); decision = read("static/js/decision.js"); cc = read("static/js/command_center.js")
dash_html = read("templates/dashboard.html")
dash_body = dash_html[dash_html.index('<div class="container cc-wrap">'):dash_html.index("{% endblock %}", dash_html.index('<div class="container cc-wrap">'))]
dash_body = re.sub(r"\{\{[^}]*\}\}", "#", dash_body).replace("{% if user %}, {{ user.name }}{% endif %}", "")

DATA = json.dumps({"plans": plans, "presets": {k: v["label"] for k, v in PRESETS.items()}, "overview": overview, "chat": chat,
                   "disease": disease, "status": status, "model": info, "built": date.today().isoformat()}, ensure_ascii=False).replace("</", "<\\/")

HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KrushiMitra AI - Interactive demo</title><style>__CSS__
.demo-tabs{position:sticky;top:0;z-index:70;background:#fff;border-bottom:1px solid var(--line);display:flex;gap:4px;padding:8px 14px;overflow-x:auto;align-items:center}
.demo-tabs .logo{margin-right:14px}.demo-tabs button{border:0;background:none;padding:9px 14px;border-radius:999px;font:600 .86rem Inter,system-ui,sans-serif;color:var(--ink-soft);cursor:pointer;white-space:nowrap}
.demo-tabs button.on{background:var(--primary-soft);color:var(--primary-dark)}.tab{display:none}.tab.on{display:block}
.demo-note{background:#FFF7E0;border-bottom:1px solid #F4DC9C;color:#7A4B00;font-size:.82rem;padding:8px 16px;text-align:center}
body{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-top:18px}
.flow div{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px;font-size:.88rem}.flow b{display:block;margin-bottom:4px}
</style></head><body>
<div class="demo-note"><b>Offline demo.</b> Every plan, chart and answer below is a real output of the app's own models and knowledge base, captured on __BUILT__. Weather is a fixed sample forecast (a static file can't call a live API) and AI-written text needs a Gemini key in the live app.</div>
<nav class="demo-tabs"><span class="logo"><span class="mark"></span> KrushiMitra <span class="logo-ai">AI</span></span>
<button class="on" data-tab="overview">Overview</button><button data-tab="planner">✨ AI Farm Planner</button><button data-tab="assistant">🧠 AI Assistant</button>
<button data-tab="dashboard">📈 Dashboard</button><button data-tab="disease">🐛 Disease check</button><button id="th" style="margin-left:auto" title="Toggle dark / light">🌙</button></nav>

<div class="tab on" id="tab-overview"><header class="lp-hero"><div class="container"><div>
<div class="eyebrow on-dark">Interactive demo · no server needed</div><h1>One plan for your farm — from <em>soil to market</em>.</h1>
<p class="lead">KrushiMitra AI combines your soil test, live weather, yield models and mandi prices into a personalised plan: best crop, fertilizer, irrigation, a 7-day to-do list and an honest profit estimate. Click through the tabs above to see each part working.</p>
<div class="lp-cta"><button class="btn btn-demo btn-lg" onclick="go('planner')">✨ See a farm plan</button><button class="btn btn-ghost-dark btn-lg" onclick="go('assistant')">🧠 Ask the assistant</button></div>
<div class="lp-trust"><div><b id="s1"></b>real field samples</div><div><b id="s2"></b>crops in soil model</div><div><b id="s3"></b>model accuracy (held-out)</div><div><b>6</b>languages in the app</div></div></div>
<div class="lp-mock"><div class="lp-mock-head"><span>How the engine works</span></div><div class="pick"><div class="row"><span>1 · You enter</span><span>soil, location, area</span></div><div class="row"><span>2 · Models run</span><span>crop · yield · price</span></div><div class="row"><span>3 · Rules apply</span><span>fertilizer · irrigation</span></div><div class="row"><span>4 · You get</span><span>labelled plan + 7-day list</span></div>
<div class="lp-chips"><span class="prov prov-measured">measured</span><span class="prov prov-live">live</span><span class="prov prov-model">model</span><span class="prov prov-reference">reference</span><span class="prov prov-observed">observed</span></div></div></div></div></header>
<section class="lp-section"><div class="container"><div class="section-head"><div class="eyebrow on-light">What this demo shows</div><h2>Everything below is real output</h2></div>
<div class="lp-grid"><div class="lp-feature"><div class="ic">✨</div><h3>AI Farm Decision Engine</h3><p>Three real plans: a full one with profit range, one needing your price, one with no soil test.</p></div>
<div class="lp-feature"><div class="ic">🧠</div><h3>RAG assistant</h3><p>Real retrieval from the knowledge base with sources — including a question it correctly refuses to answer.</p></div>
<div class="lp-feature"><div class="ic">📈</div><h3>Command center</h3><p>Built from real database records and the farm's saved crop plan.</p></div></div>
<p class="hint" style="margin-top:18px">To use the live app: run it locally (see README), open <code>/</code> and press <b>Try the demo — no sign-in</b>.</p></div></section></div>

<div class="tab" id="tab-planner"><header class="planner-head"><div class="container"><div class="eyebrow on-dark">✨ AI Farm Decision Engine</div><h1>Your personalised farming plan</h1><p>Pick a scenario. Each is a real engine run. Every figure is labelled measured · live · model · reference · observed.</p></div></header>
<div class="container planner-wrap"><div class="preset-row" id="presets" style="margin-bottom:14px"></div><div id="dm-output"></div></div></div>

<div class="tab" id="tab-assistant"><header class="planner-head"><div class="container"><div class="eyebrow on-dark">🧠 RAG Agricultural Assistant</div><h1>Ask anything about your farm</h1><p>Retrieved from the knowledge base and cited. If it isn't covered, the assistant says so.</p></div></header>
<div class="container planner-wrap"><div class="chat-shell" style="height:auto;min-height:420px"><div class="chat-top"><div><b>KrushiMitra Assistant</b> <span class="hint" id="as-mode"></span></div></div>
<div class="chat-scroll" id="as-scroll"><div class="msg bot">Pick a question below — these ran against the real knowledge base.</div></div><div class="suggest-row" id="as-suggest"></div></div></div></div>

<div class="tab" id="tab-dashboard"><header class="cc-head"><div class="container"><div><div class="eyebrow on-dark">📈 Farm command center</div><h1>Welcome, Demo Farmer</h1><p id="cc-sub"></p></div></div></header>__DASH__</div>

<div class="tab" id="tab-disease"><header class="planner-head"><div class="container"><div class="eyebrow on-dark">🐛 Disease check</div><h1>Symptom matching + photo AI</h1><p>Match symptoms to a 35-crop reference, or upload a leaf photo for a Gemini vision assessment (live app, needs a key).</p></div></header>
<div class="container planner-wrap"><div class="card"><h3>Symptom check — rice</h3><p class="hint">Symptom selected: “diamond-shaped grey/white lesions with brown margins on leaves”</p><div id="dz"></div></div>
<div class="notice info" style="margin-top:14px"><b>Photo assessment</b> sends the photo to Gemini's vision model and returns <i>possibilities with uncertainty</i> cross-referenced with this table — never a diagnosis. Without a key the app saves the photo and says it was not analysed.</div></div></div>

<script>__COMMON__</script>
<script>const DEMO=__DATA__;</script>
<script>__DECISION__</script>
<script>__CC__</script>
<script>
function go(t){document.querySelectorAll('.tab').forEach(e=>e.classList.toggle('on',e.id==='tab-'+t));document.querySelectorAll('.demo-tabs button').forEach(b=>b.classList.toggle('on',b.dataset.tab===t));window.scrollTo(0,0);if(t==='dashboard'&&!window._d){window._d=1;renderOverview(DEMO.overview);}}
document.querySelectorAll('.demo-tabs button[data-tab]').forEach(b=>b.onclick=()=>go(b.dataset.tab));
const th=document.getElementById('th');function setTheme(t){document.documentElement.setAttribute('data-theme',t);th.textContent=t==='dark'?'☀️':'🌙';}th.onclick=()=>setTheme(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark');setTheme(window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
document.getElementById('s1').textContent=(DEMO.model.training_samples||0).toLocaleString();document.getElementById('s2').textContent=DEMO.model.crop_classes;document.getElementById('s3').textContent=DEMO.model.test_accuracy_pct+'%';
// ---- planner: reuse the real renderer, swap network actions for demo behaviour
function showPlan(k){DM.plan=DEMO.plans[k];renderPlan(DM.plan);const ai=document.getElementById('dm-ai-body');if(ai)ai.innerHTML='<div class="hint">In the live app Gemini writes a plain-language explanation here (needs GEMINI_API_KEY). Everything else on this page is computed without it.</div>';
 const sv=document.getElementById('dm-save');if(sv){sv.onclick=()=>alert('In the live app this saves the crop calendar, soil check and yield estimate to your dashboard.');}
 document.querySelectorAll('[data-plan-crop]').forEach(b=>b.onclick=()=>alert('In the live app this re-runs the engine for '+b.dataset.planCrop+'. This offline demo ships three pre-computed scenarios.'));
 document.querySelectorAll('#presets .preset').forEach(x=>x.classList.toggle('on',x.dataset.k===k));}
const pr=document.getElementById('presets');Object.entries(DEMO.presets).forEach(([k,l])=>{const b=document.createElement('button');b.className='preset';b.dataset.k=k;b.textContent=l;b.onclick=()=>showPlan(k);pr.appendChild(b);});showPlan('chickpea');
// ---- dashboard charts without Chart.js
function draw(id,type,labels,ds){const cv=document.getElementById(id);if(!cv)return;const W=cv.width=520,H=cv.height=240,g=cv.getContext('2d');g.clearRect(0,0,W,H);g.font='12px sans-serif';
 if(type==='doughnut'){const d=ds[0].data,t=d.reduce((a,b)=>a+b,0)||1;let a0=-Math.PI/2;d.forEach((v,i)=>{const a1=a0+v/t*2*Math.PI;g.beginPath();g.moveTo(120,120);g.arc(120,120,95,a0,a1);g.fillStyle=ds[0].backgroundColor[i%6];g.fill();a0=a1;});g.beginPath();g.arc(120,120,52,0,7);g.fillStyle='#fff';g.fill();labels.forEach((l,i)=>{g.fillStyle=ds[0].backgroundColor[i%6];g.fillRect(250,30+i*26,12,12);g.fillStyle='#333';g.fillText(l+' — ₹'+Math.round(ds[0].data[i]).toLocaleString('en-IN'),270,41+i*26);});return;}
 const max=Math.max(1,...ds.flatMap(s=>s.data)),n=labels.length,gw=(W-60)/n;labels.forEach((l,i)=>{ds.forEach((s,j)=>{const h=s.data[i]/max*(H-60);g.fillStyle=s.backgroundColor;g.fillRect(40+i*gw+j*(gw/2.6)+8,H-30-h,gw/2.8,h);});g.fillStyle='#555';g.fillText(l,40+i*gw+8,H-10);});ds.forEach((s,j)=>{g.fillStyle=s.backgroundColor;g.fillRect(40+j*90,6,10,10);g.fillStyle='#333';g.fillText(s.label,54+j*90,15);});}
document.getElementById('qa-add')&&(document.getElementById('qa-add').onclick=()=>alert('In the live app this adds a record and refreshes the dashboard.'));
// ---- assistant
const sc=document.getElementById('as-scroll'),sg=document.getElementById('as-suggest');document.getElementById('as-mode').textContent='· '+DEMO.status.retrieval_mode+' · '+DEMO.status.documents+' documents · '+DEMO.status.chunks+' passages';
function add(c,h){const e=document.createElement('div');e.className='msg '+c;e.innerHTML=h;sc.appendChild(e);sc.scrollTop=sc.scrollHeight;return e;}
DEMO.chat.forEach(x=>{const b=document.createElement('button');b.className='preset';b.textContent=x.q;b.onclick=()=>{add('user',escapeHtml(x.q));const r=x.r;const src=(r.sources||[]).map(s=>`<div class="src"><span class="tag">${s.n}</span><b>${escapeHtml(s.title)}</b><div class="snip" style="display:block">${escapeHtml(s.snippet)}</div></div>`).join('');
 const badge=r.sources&&r.sources.length?'<span class="prov prov-reference">extractive — top matching passages (AI writing needs a Gemini key)</span>':'<span class="prov prov-unavailable">not found in knowledge base</span>';
 add('bot',escapeHtml(r.reply).replace(/\\n/g,'<br>')+`<div class="badge-row">${badge}<span class="prov prov-reference">${escapeHtml(r.retrieval_mode)}</span></div>`+(src?`<div class="src-list"><b style="font-size:.75rem">Sources</b>${src}</div>`:''));};sg.appendChild(b);});
// ---- disease
(function(){const r=DEMO.disease;document.getElementById('dz').innerHTML=(r.matches||[]).map(m=>`<div class="disease-match"><h4>${escapeHtml(m.disease)}</h4><div class="row"><b>Likely cause:</b> ${escapeHtml(m.cause)}</div><div class="row"><b>Treatment:</b> ${escapeHtml(m.treatment)}</div><div class="row"><b>Commonly used:</b> ${escapeHtml(m.recommended_fungicide)}</div></div>`).join('')+'<p class="hint">'+escapeHtml(r.disclaimer||'')+'</p>';})();
</script></body></html>"""

for k, v in {"__CSS__": css, "__COMMON__": common, "__DECISION__": decision.split("async function initDecisionPage")[0] + decision[decision.index("// Rendering"):],
             "__CC__": cc.split("async function initCommandCenter")[0] + cc[cc.index("function renderOverview"):], "__DASH__": dash_body,
             "__DATA__": DATA, "__BUILT__": date.today().strftime("%d %b %Y")}.items():
    HTML = HTML.replace(k, v)
out = os.path.join(ROOT, "demo", "KrushiMitra_AI_Demo.html")
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w", encoding="utf-8").write(HTML)
print("wrote", out, round(len(HTML) / 1024), "KB")
