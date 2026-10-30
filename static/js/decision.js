// decision.js — AI Farm Decision Engine page.
// All text that comes from the API is escaped with escapeHtml() (common.js) before it
// is placed in innerHTML.

const DM = { coords: null, plan: null, ref: null };
const $d = (id) => document.getElementById(id);
const h = (x) => escapeHtml(x);
const inr = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : '₹' + Math.round(Number(n)).toLocaleString('en-IN');
const num = (n, d = 1) => (n === null || n === undefined || isNaN(n)) ? '—' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });
const cap = (s) => String(s || '').replace(/\b\w/g, c => c.toUpperCase());

const PROV_LABEL = { measured: 'measured', live: 'live', model: 'model estimate', reference: 'reference', observed: 'observed history', unavailable: 'unavailable' };
const prov = (kind) => `<span class="prov prov-${h(kind || 'unavailable')}" title="${h((DM.plan && DM.plan.provenance_legend && DM.plan.provenance_legend[kind]) || '')}">${h(PROV_LABEL[kind] || kind)}</span>`;

const PRESETS = {
  chickpea: { location: 'Indore, Madhya Pradesh', state: 'Madhya Pradesh', season: 'Rabi', area: 4, n: 40, p: 68, k: 80, ph: 7.2, temp: 19, hum: 17, rain: 80, seeds: 7000, labour: 9000 },
  maize: { location: 'Belagavi, Karnataka', state: 'Karnataka', season: 'Kharif', area: 2.5, n: 78, p: 48, k: 20, ph: 6.2, temp: 23, hum: 65, rain: 85, price: 2100, seeds: 4200, labour: 8000 },
  rice: { location: 'Kolkata, West Bengal', state: 'West Bengal', season: 'Kharif', area: 2, n: 85, p: 45, k: 40, ph: 6.4, temp: 24, hum: 82, rain: 220, price: 2200, seeds: 3000, labour: 12000 },
};

async function initDecisionPage() {
  await loadDmReference();
  $d('dm-form').addEventListener('submit', (e) => { e.preventDefault(); generatePlan(); });
  $d('dm-gps').addEventListener('click', dmGps);
  document.querySelectorAll('.preset').forEach(b => b.addEventListener('click', () => applyPreset(b.dataset.preset)));

  try {
    const me = await (await fetch('/api/auth/me', { credentials: 'include' })).json();
    if (me.success && me.user) {
      if (me.user.location && !$d('dm-location').value) $d('dm-location').value = me.user.location;
      if (me.user.farm_size_acres && !$d('dm-area').value) $d('dm-area').value = me.user.farm_size_acres;
      if (me.user.soil_type) $d('dm-soiltype').value = me.user.soil_type;
      const guess = (me.user.location || '').split(',').map(s => s.trim()).pop();
      if (guess && DM.ref && DM.ref.states.includes(guess)) $d('dm-state').value = guess;
    }
  } catch (e) { /* profile prefill is optional */ }

  const params = new URLSearchParams(location.search);
  if (params.get('plan')) loadExistingPlan(params.get('plan'));
}

async function loadDmReference() {
  try {
    const d = await (await fetch('/api/reference-data')).json();
    if (!d.success) return;
    DM.ref = d;
    const fill = (id, vals, ph) => { const el = $d(id); el.innerHTML = `<option value="">${h(ph)}</option>` + vals.map(v => `<option value="${h(v)}">${h(v)}</option>`).join(''); };
    fill('dm-state', d.states, 'Select state');
    fill('dm-season', d.seasons, "Auto (from today's date)");
    fill('dm-soiltype', d.soil_types, 'Select soil type');
    fill('dm-crop', (d.crops || []).map(cap), 'Let the engine choose');
    $d('dm-crop').querySelectorAll('option').forEach(o => { if (o.value) o.value = o.value.toLowerCase(); });
  } catch (e) { /* the form still works with typed values */ }
}

function applyPreset(name) {
  const p = PRESETS[name]; if (!p) return;
  const set = (id, v) => { $d(id).value = (v === undefined ? '' : v); };
  set('dm-location', p.location); set('dm-state', p.state); set('dm-season', p.season); set('dm-area', p.area);
  set('dm-n', p.n); set('dm-p', p.p); set('dm-k', p.k); set('dm-ph', p.ph);
  set('dm-temp', p.temp); set('dm-hum', p.hum); set('dm-rain', p.rain);
  set('dm-price', p.price); set('dm-c-seeds', p.seeds); set('dm-c-labour', p.labour);
  set('dm-crop', ''); set('dm-yield', ''); set('dm-oc', ''); set('dm-c-pest', ''); set('dm-c-water', ''); set('dm-c-other', '');
  DM.coords = null; $d('dm-gps-status').textContent = '';
  document.querySelectorAll('.opt-block').forEach(d => { d.open = true; });
}

function dmGps() {
  const st = $d('dm-gps-status'); const btn = $d('dm-gps');
  if (!navigator.geolocation) { st.textContent = 'GPS is not supported in this browser — type your location.'; st.className = 'location-status warn'; return; }
  btn.disabled = true; st.className = 'location-status'; st.textContent = 'Locating…';
  navigator.geolocation.getCurrentPosition(async (pos) => {
    DM.coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    try {
      const d = await (await fetch(`/api/reverse-geocode?lat=${DM.coords.lat}&lon=${DM.coords.lon}`, { credentials: 'include' })).json();
      if (d.success) {
        $d('dm-location').value = d.location_string || '';
        if (d.state && DM.ref && DM.ref.states.includes(d.state)) $d('dm-state').value = d.state;
      }
    } catch (e) { /* coordinates are still captured */ }
    st.className = 'location-status ok'; st.textContent = `GPS captured (±${Math.round(pos.coords.accuracy)} m).`; btn.disabled = false;
  }, () => { st.className = 'location-status warn'; st.textContent = 'GPS denied — type your location instead.'; btn.disabled = false; },
  { enableHighAccuracy: true, timeout: 10000 });
}

function collectInputs(overrides) {
  const v = (id) => { const x = $d(id).value.trim(); return x === '' ? null : x; };
  const body = {
    location: v('dm-location'), state: v('dm-state'), area_acres: v('dm-area'), season: v('dm-season'),
    sowing_date: v('dm-sowing'), soil_type: v('dm-soiltype'),
    n: v('dm-n'), p: v('dm-p'), k: v('dm-k'), ph: v('dm-ph'), organic_carbon: v('dm-oc'),
    selected_crop: v('dm-crop'), temperature: v('dm-temp'), humidity: v('dm-hum'), monthly_rainfall_mm: v('dm-rain'),
    manual_price_rs_per_quintal: v('dm-price'), manual_yield_t_per_acre: v('dm-yield'),
    expenses: { seeds: v('dm-c-seeds'), labour: v('dm-c-labour'), pesticides: v('dm-c-pest'), water: v('dm-c-water'), other: v('dm-c-other') },
    language: (typeof getCurrentLang === 'function' ? getCurrentLang() : 'en'),
  };
  if (DM.coords) { body.lat = DM.coords.lat; body.lon = DM.coords.lon; }
  Object.keys(body).forEach(k => { if (body[k] === null) delete body[k]; });
  return Object.assign(body, overrides || {});
}

async function generatePlan(overrides) {
  const err = $d('dm-error'); err.classList.remove('show');
  const btn = $d('dm-submit'); btn.disabled = true;
  $d('dm-output').innerHTML = `<div class="card plan-loading"><div class="big" style="font-size:2.4rem">🌾</div><h3>Building your plan…</h3>
    <div class="plan-steps"><span>Fetching live weather &amp; recent rainfall</span><span>Scoring crops against your soil and climate</span>
    <span>Estimating yield, price, fertilizer and costs</span><span>Drafting your 7-day action list</span></div></div>`;
  try {
    const res = await fetch('/api/decision-engine/plan', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(collectInputs(overrides)) });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.error || 'Could not build the plan.');
    DM.plan = data;
    renderPlan(data);
    requestExplanation(data.plan_id);
    $d('dm-output').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    $d('dm-output').innerHTML = `<div class="card plan-empty"><div class="big">⚠️</div><h3>We couldn't build a plan yet</h3><p>${h(e.message)}</p></div>`;
    err.textContent = e.message; err.classList.add('show');
  } finally { btn.disabled = false; }
}

async function loadExistingPlan(id) {
  try {
    const res = await fetch(`/api/decision-engine/plans/${encodeURIComponent(id)}`, { credentials: 'include' });
    const data = await res.json();
    if (!data.success) return;
    DM.plan = data; renderPlan(data);
    if (data.explanation) showExplanation(data.explanation); else requestExplanation(data.plan_id);
  } catch (e) { /* ignore */ }
}

// ----------------------------------------------------------------------- //
// Rendering
// ----------------------------------------------------------------------- //
function renderPlan(p) {
  const s = p.summary;
  const parts = [];
  parts.push(`
  <div class="plan-banner">
    <div>
      <span class="prov prov-${h(s.ranking_basis_kind)}">${h(PROV_LABEL[s.ranking_basis_kind] || '')}</span>
      <h2>${h(s.headline)}</h2>
      <div class="meta">
        <span class="pill green">🌾 ${h(cap(s.primary_crop))}</span><span class="pill">${h(num(s.area_acres, 2))} acres</span>
        <span class="pill">${h(s.season)}${s.season_inferred ? ' (assumed)' : ''}</span>
        ${s.state ? `<span class="pill">${h(s.state)}</span>` : ''}<span class="pill">Sowing ${h(s.sowing_date)}</span>
      </div>
      <p class="hint" style="margin:10px 0 0">${h(s.ranking_basis)}</p>
    </div>
    <div class="plan-actions">
      <button class="btn btn-primary" id="dm-save" type="button">💾 Save to my farm</button>
      <button class="btn btn-ghost" type="button" onclick="window.print()">🖨 Print / PDF</button>
      <a class="btn btn-ghost" href="/dashboard">📈 Dashboard</a>
    </div>
  </div>`);

  if (p.data_gaps.length) parts.push(`<div class="notice warn"><b>Missing or assumed information</b><ul>${p.data_gaps.map(g => `<li>${h(g)}</li>`).join('')}</ul></div>`);
  if (p.data_quality.length) parts.push(`<div class="notice info"><b>Data-quality notes</b><ul>${p.data_quality.map(g => `<li>${h(g)}</li>`).join('')}</ul></div>`);

  parts.push(`<div class="ai-box" id="dm-ai"><h3>🤖 AI explanation <span class="prov prov-model">gemini</span></h3><div id="dm-ai-body" class="ai-text"><div class="typing"><span></span><span></span><span></span></div> <span class="hint">Writing a plain-language explanation of your plan…</span></div></div>`);

  parts.push(renderCrops(p));
  parts.push(renderSoil(p));
  parts.push(renderFertilizer(p.fertilizer));
  parts.push(renderIrrigationWeather(p));
  parts.push(renderMoney(p));
  parts.push(renderWeek(p.seven_day_plan));
  parts.push(renderRisks(p.risks));
  parts.push(`<div class="pcard"><header><h3>🏷 How to read this plan</h3></header>
    <div class="prov-legend">${Object.entries(p.provenance_legend).map(([k, t]) => `<span>${prov(k)} ${h(t)}</span>`).join('')}</div>
    <p class="hint" style="margin-top:12px">${h(p.disclaimer)}</p></div>`);

  $d('dm-output').innerHTML = parts.join('');
  const save = $d('dm-save');
  if (save) {
    if (p.saved) { save.textContent = '✅ Saved to your farm'; save.disabled = true; }
    else save.addEventListener('click', savePlan);
  }
  document.querySelectorAll('[data-plan-crop]').forEach(b => b.addEventListener('click', () => {
    $d('dm-crop').value = b.dataset.planCrop; generatePlan({ selected_crop: b.dataset.planCrop });
  }));
}

function renderCrops(p) {
  const c = p.crops.primary;
  const conf = c.suitability_confidence_pct;
  const alt = p.crops.alternatives || [];
  return `<div class="pcard"><header><h3>🌱 Best crop &amp; alternatives</h3>${prov(p.summary.ranking_basis_kind)}</header>
    <div class="crop-hero"><div class="crop-badge">🌾</div><div>
      <h3 style="margin:0;font-size:1.4rem">${h(cap(c.crop))}</h3>
      <div class="hint">${h(c.why)}</div>
      ${conf !== undefined ? `<div class="conf-bar" title="Model confidence"><div style="width:${Math.min(100, conf)}%"></div></div><div class="hint">Model confidence ${h(num(conf, 0))}% ${prov('model')}</div>` : ''}
      ${c.season_warning ? `<div class="notice warn" style="margin:8px 0 0">${h(c.season_warning)}</div>` : ''}
    </div></div>
    ${alt.length ? `<h4 style="margin:18px 0 0;font-size:.9rem">Alternative crops</h4><div class="alt-grid">${alt.map(a => `
      <div class="alt-card"><h4>${h(cap(a.crop))}</h4>
        <p>${h(a.why)}</p>
        ${a.vs_primary ? `<p style="color:var(--forest)">${h(a.vs_primary)}</p>` : (a.price_note ? `<p>${h(a.price_note)}</p>` : '')}
        ${a.season_warning ? `<p style="color:var(--earth)">${h(a.season_warning)}</p>` : ''}
        <button class="btn btn-ghost btn-small" type="button" data-plan-crop="${h(a.crop)}">Plan this crop →</button></div>`).join('')}</div>` : ''}
  </div>`;
}

function renderSoil(p) {
  const s = p.soil; const fit = s.suitability || {};
  let left = '';
  if (s.available) {
    const hh = s.health;
    left = `<div class="stat"><div class="l">Soil health score ${prov('reference')}</div><div class="v">${h(hh.soil_health_score)}<span style="font-size:.9rem">/100</span></div>
      <div class="s">N ${h(hh.nitrogen_status)} · P ${h(hh.phosphorus_status)} · K ${h(hh.potassium_status)} · pH ${h(hh.ph_status)}${hh.organic_carbon_status ? ' · OC ' + h(hh.organic_carbon_status) : ''}</div></div>
      <h4 style="font-size:.88rem;margin:14px 0 6px">Nutrient deficiencies</h4>
      ${s.deficiencies.length ? `<div>${s.deficiencies.map(d => `<span class="pill red">${h(d)} low</span> `).join('')}</div>` : '<span class="pill green">No nutrient is in the “low” band</span>'}
      <h4 style="font-size:.88rem;margin:14px 0 6px">What to improve</h4>
      <ul style="margin:0;padding-left:18px;font-size:.86rem">${hh.improvement_suggestions.map(x => `<li>${h(x)}</li>`).join('')}</ul>
      <p class="hint">${h(s.note)}</p>`;
  } else {
    left = `<div class="notice warn">${h(s.message)}</div>`;
  }
  let right = '';
  if (fit.covered) {
    right = `<div class="stat"><div class="l">Soil &amp; climate fit for ${h(cap(p.summary.primary_crop))} ${prov('reference')}</div><div class="v">${h(fit.verdict)}</div><div class="s">${h(fit.within)} of ${h(fit.checked)} parameters in the typical range</div></div>
      <div style="margin-top:10px">${fit.checks.map(c => `<div class="fit-row"><span>${h(c.parameter)}</span><span>${h(c.your_value)} <small class="hint">(typical ${h(c.typical_range[0])}–${h(c.typical_range[1])})</small></span><span class="${c.status === 'within' ? 'fit-ok' : 'fit-bad'}">${c.status === 'within' ? '✓ ok' : (c.status === 'below' ? '↓ low' : '↑ high')}</span></div>`).join('')}</div>
      <p class="hint">${h(fit.basis)}</p>`;
  } else {
    right = `<div class="notice info">${h(fit.message || 'Soil suitability could not be assessed for this crop.')}</div>`;
  }
  return `<div class="pcard"><header><h3>🧪 Soil suitability &amp; nutrients</h3></header><div class="two-col"><div>${left}</div><div>${right}</div></div></div>`;
}

function renderFertilizer(f) {
  if (!f.available) return `<div class="pcard"><header><h3>🚜 Fertilizer plan</h3>${prov('unavailable')}</header><div class="notice info">${h(f.message)}</div></div>`;
  return `<div class="pcard"><header><h3>🚜 Fertilizer plan</h3>${prov('reference')}</header>
    <p class="sub">For ${h(num(f.area_acres, 2))} acres — N ${h(num(f.npk_target_kg.N, 0))} kg, P ${h(num(f.npk_target_kg.P, 0))} kg, K ${h(num(f.npk_target_kg.K, 0))} kg in total.</p>
    <div style="overflow-x:auto"><table class="mini"><thead><tr><th>Stage</th><th>Fertilizer</th><th class="num" style="text-align:right">Qty (kg)</th><th style="text-align:right">≈ Cost</th></tr></thead>
    <tbody>${f.items.map(i => `<tr><td>${h(i.stage)}</td><td>${h(i.fertilizer)}</td><td class="num">${h(num(i.quantity_kg))}</td><td class="num">${inr(i.approx_cost_rs)}</td></tr>`).join('')}</tbody>
    <tfoot><tr><td colspan="3">Approximate total</td><td class="num">${inr(f.total_approx_cost_rs)}</td></tr></tfoot></table></div>
    <p class="hint">${h(f.reference)}</p></div>`;
}

function renderIrrigationWeather(p) {
  const irr = p.irrigation, w = p.weather;
  let irrHtml;
  if (irr.available) {
    const sch = irr.advice.irrigation_schedule;
    irrHtml = `<div class="stat"><div class="l">Next irrigation ${prov('live')}</div><div class="v">${h(irr.summary.message)}</div><div class="s">Seasonal need ≈ ${h(irr.advice.seasonal_requirement_mm)} mm · critical stages: ${h(irr.advice.critical_stages.join(', '))}</div></div>
      <div class="fc-strip" style="margin-top:10px">${sch.map(d => `<div><b>${h((d.date || '').slice(5))}</b><br>${d.irrigation_needed ? `💧 ${h(d.water_amount_mm)}mm` : '—'}</div>`).join('')}</div>
      <ul style="font-size:.82rem;padding-left:18px;margin:10px 0 0">${irr.advice.water_conservation_tips.slice(0, 3).map(t => `<li>${h(t)}</li>`).join('')}</ul>
      <p class="hint">${h(irr.note)} ${h(irr.method)}</p>`;
  } else irrHtml = `<div class="notice warn">${h(irr.message)}</div>`;

  let wxHtml;
  if (w.available) {
    const cur = w.current;
    wxHtml = `<div class="stat"><div class="l">Now · ${h(cur.location || '')} ${prov('live')}</div><div class="v">${h(num(cur.temperature, 0))}°C</div><div class="s">${h(cur.weather || '')} · humidity ${h(num(cur.humidity, 0))}% · wind ${h(num(cur.wind_speed, 0))} km/h</div></div>
      <div class="fc-strip" style="margin:10px 0">${w.forecast.map(d => `<div><b>${h((d.date || '').slice(5))}</b><br>${h(num(d.temperature, 0))}°<br><span class="rain">${h(num(d.rainfall || 0, 0))}mm</span></div>`).join('')}</div>
      <h4 style="font-size:.88rem;margin:8px 0 6px">Weather precautions</h4>
      ${w.precautions.length ? w.precautions.slice(0, 6).map(x => `<div class="risk ${x.severity === 'high' ? 'high' : 'medium'}"><span class="lv">${h((x.date || '').slice(5))}</span><span>${h(x.text)}</span></div>`).join('') : '<span class="pill green">No weather risks above the alert thresholds this week</span>'}
      ${w.spray_windows.length ? `<p class="hint">Good spraying days (dry &amp; calm): ${h(w.spray_windows.map(d => d.slice(5)).join(', '))}</p>` : '<p class="hint">No dry, calm spraying day in the forecast.</p>'}
      <p class="hint">${h(w.rule_note)}</p>`;
  } else wxHtml = `<div class="notice warn">${h(w.message)}</div>`;

  return `<div class="pcard"><header><h3>💧 Irrigation &amp; ⛅ weather precautions</h3></header><div class="two-col"><div>${irrHtml}</div><div>${wxHtml}</div></div></div>`;
}

function rangeBar(lo, exp, hi, fmt) {
  if (lo === undefined || hi === undefined || hi === lo) return `<div class="stat"><div class="l">Single value</div><div class="v">${fmt(exp)}</div></div>`;
  const min = Math.min(lo, 0), max = hi, span = (max - min) || 1;
  const pos = (v) => ((v - min) / span * 100).toFixed(1);
  return `<div class="range-bar"><div class="track"></div><div class="fill" style="left:${pos(lo)}%;width:${pos(hi) - pos(lo)}%"></div>
    <span class="dot2" style="left:${pos(exp)}%"></span>
    <span class="tick" style="left:${Math.max(6, pos(lo))}%;top:18px">${fmt(lo)}</span>
    <span class="tick exp" style="left:${Math.min(Math.max(pos(exp), 12), 88)}%;top:-6px">${fmt(exp)}</span>
    <span class="tick" style="left:${Math.min(94, pos(hi))}%;top:18px">${fmt(hi)}</span></div>`;
}

function renderMoney(p) {
  const y = p.yield, m = p.market, e = p.economics;
  const yHtml = y.available ? `<div class="stat"><div class="l">Expected yield ${prov(y.kind)}</div><div class="v">${h(num(y.total_tonnes.expected, 2))} t</div><div class="s">${h(num(y.per_hectare.expected, 2))} t/ha · ${h(num(y.area_acres, 2))} acres</div></div>
      ${rangeBar(y.total_tonnes.low, y.total_tonnes.expected, y.total_tonnes.high, v => num(v, 2) + ' t')}
      <p class="hint">${h(y.note)}${y.model_r2 !== null && y.model_r2 !== undefined ? ` Model fit R² ${h(num(y.model_r2, 2))}.` : ''}</p>`
    : `<div class="notice warn">${h(y.message)}</div>`;
  let mHtml;
  if (m.available) {
    mHtml = `<div class="stat"><div class="l">Market price ${prov(m.kind)}</div><div class="v">${inr(m.price_rs_per_quintal)}<span style="font-size:.8rem">/quintal</span></div>
      <div class="s">${h(m.data_source || '')}${m.observed_range ? ` · observed range ${inr(m.observed_range[0])}–${inr(m.observed_range[1])}` : ''}</div></div>
      ${m.accuracy_warning ? `<div class="notice warn" style="margin-top:8px">${h(m.accuracy_warning)}</div>` : ''}
      ${(m.nearby_markets || []).length ? `<h4 style="font-size:.86rem;margin:10px 0 4px">Nearest recorded markets ${prov('observed')}</h4>${m.nearby_markets.map(x => `<div class="fit-row" style="grid-template-columns:1.4fr 1fr auto"><span>${h(x.market || x.name || '')}</span><span>${h(x.state || '')}</span><span>${inr(x.median_price || x.modal_price || x.price)}</span></div>`).join('')}` : ''}`;
  } else mHtml = `<div class="notice warn">${h(m.message || 'No market price available.')}</div>`;

  let costHtml = `<table class="mini"><thead><tr><th>Cost item</th><th>Source</th><th style="text-align:right">₹</th></tr></thead><tbody>
    ${e.costs.length ? e.costs.map(c => `<tr><td>${h(c.item)}</td><td>${prov(c.kind)}</td><td class="num">${inr(c.amount_rs)}</td></tr>`).join('') : '<tr><td colspan="3" class="hint">No costs included yet.</td></tr>'}
    </tbody><tfoot><tr><td colspan="2">Costs included</td><td class="num">${inr(e.total_known_costs_rs)}</td></tr></tfoot></table>
    ${e.costs_not_estimated.length ? `<p class="hint">Not included: ${h(e.costs_not_estimated.join(', '))} — enter them under “Your costs” for a fuller picture.</p>` : ''}`;
  let profHtml;
  if (e.revenue) {
    profHtml = `<div class="three-col" style="margin-top:6px">
      <div class="stat"><div class="l">Revenue (est.)</div><div class="v">${inr(e.revenue.expected)}</div><div class="s">${inr(e.revenue.low)} – ${inr(e.revenue.high)}</div></div>
      <div class="stat"><div class="l">Profit (est.)</div><div class="v" style="color:${e.profit.expected >= 0 ? 'var(--primary-dark)' : 'var(--danger)'}">${inr(e.profit.expected)}</div><div class="s">${inr(e.profit.low)} – ${inr(e.profit.high)}</div></div>
      <div class="stat"><div class="l">Price used</div><div class="v" style="font-size:1.05rem">${inr(e.price_used_rs_per_quintal.expected)}</div><div class="s">per quintal (${inr(e.price_used_rs_per_quintal.low)}–${inr(e.price_used_rs_per_quintal.high)})</div></div></div>
      ${rangeBar(e.profit.low, e.profit.expected, e.profit.high, inr)}
      <div class="notice warn" style="margin-top:10px"><b>${h(e.profit_label)} — an estimate, not a guarantee.</b><ul>${e.caveats.map(c => `<li>${h(c)}</li>`).join('')}</ul></div>`;
  } else profHtml = `<div class="notice warn">${h(e.message)}</div>`;

  return `<div class="pcard"><header><h3>📊 Yield, price, costs &amp; profit</h3></header>
    <div class="two-col"><div>${yHtml}</div><div>${mHtml}</div></div>
    <div class="two-col" style="margin-top:18px"><div><h4 style="font-size:.9rem;margin:0 0 8px">Estimated production costs</h4>${costHtml}</div><div><h4 style="font-size:.9rem;margin:0 0 4px">Potential revenue &amp; profit ${prov(e.revenue ? 'model' : 'unavailable')}</h4>${profHtml}</div></div></div>`;
}

function renderWeek(w) {
  return `<div class="pcard"><header><h3>🗓 Next 7 days — what to do</h3>${prov(w.kind)}</header><p class="sub">${h(w.note)}</p>
    <div class="week">${w.days.map((d, i) => `<div class="day ${i === 0 ? 'today' : ''}"><h5>${i === 0 ? 'Today' : 'Day ' + h(d.day)} · ${h((d.date || '').slice(5))}</h5>
      <div class="wx">${d.weather ? `${h(d.weather.summary || '')} ${h(num(d.weather.temperature, 0))}° · ${h(num(d.weather.rain_mm || 0, 0))}mm` : 'no live weather'}</div>
      ${d.tasks.length ? d.tasks.map(t => `<div class="task t-${h(t.type)}">${h(t.text)}<small>${h(t.basis)}</small></div>`).join('') : '<div class="task">Nothing scheduled</div>'}</div>`).join('')}</div></div>`;
}

function renderRisks(risks) {
  return `<div class="pcard"><header><h3>⚠️ Risks &amp; precautions</h3></header>${risks.map(r => `<div class="risk ${h(r.level)}"><span class="lv">${h(r.level)}</span><span><b style="text-transform:capitalize">${h(r.category)}:</b> ${h(r.text)}</span></div>`).join('')}</div>`;
}

// ----------------------------------------------------------------------- //
// AI explanation + save
// ----------------------------------------------------------------------- //
async function requestExplanation(planId) {
  try {
    const res = await fetch(`/api/decision-engine/plans/${planId}/explain`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ language: (typeof getCurrentLang === 'function' ? getCurrentLang() : 'en') }) });
    const data = await res.json();
    if (data.success) showExplanation(data.explanation);
    else $d('dm-ai-body') && ($d('dm-ai-body').innerHTML = `<div class="hint">${h(data.error || 'The AI explanation is unavailable.')} The full plan above doesn't depend on it.</div>`);
  } catch (e) { $d('dm-ai-body') && ($d('dm-ai-body').innerHTML = '<div class="hint">Could not reach the explanation service.</div>'); }
}

function showExplanation(text) {
  const el = $d('dm-ai-body'); if (!el) return;
  // minimal, safe formatting: headings, bullets, paragraphs — everything escaped first
  const lines = String(text).split('\n');
  let out = '', inList = false;
  const close = () => { if (inList) { out += '</ul>'; inList = false; } };
  for (let raw of lines) {
    let line = raw.trim(); if (!line) { close(); continue; }
    line = h(line).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    const heading = line.match(/^#{1,4}\s*(.+)$/) || line.match(/^<b>(Summary|Why this crop|This week|Money \(estimate\)|Watch-outs)<\/b>:?$/i);
    if (heading) { close(); out += `<h5>${heading[1].replace(/<\/?b>/g, '')}</h5>`; continue; }
    const bullet = line.match(/^[-*•]\s+(.+)$/);
    if (bullet) { if (!inList) { out += '<ul>'; inList = true; } out += `<li>${bullet[1]}</li>`; continue; }
    close(); out += `<p>${line}</p>`;
  }
  close();
  el.innerHTML = out;
}

async function savePlan() {
  const btn = $d('dm-save'); btn.disabled = true;
  try {
    const res = await fetch(`/api/decision-engine/plans/${DM.plan.plan_id}/save`, { method: 'POST', credentials: 'include' });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Could not save.');
    btn.textContent = '✅ Saved — see your dashboard';
    btn.onclick = () => { window.location.href = '/dashboard'; }; btn.disabled = false;
  } catch (e) { btn.disabled = false; alert(e.message); }
}
