// command_center.js — farmer dashboard. Data comes from /api/dashboard/overview (real DB records +
// live weather). Empty widgets show an explanation instead of dummy numbers.
const CC = { charts: {} };
const $c = (id) => document.getElementById(id);
const ch = (x) => escapeHtml(x);
const cinr = (n) => (n === null || n === undefined || isNaN(n)) ? '—' : '₹' + Math.round(Number(n)).toLocaleString('en-IN');
const cn = (n, d = 0) => (n === null || n === undefined || isNaN(n)) ? '—' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: d });
const ccap = (s) => String(s || '').replace(/\b\w/g, c => c.toUpperCase());
const empty = (msg, link) => `<div class="empty">${ch(msg)}${link ? ` <a href="${ch(link[0])}">${ch(link[1])}</a>` : ''}</div>`;

async function initCommandCenter() {
  $c('qa-type').addEventListener('change', () => { $c('qa-cat-wrap').style.display = $c('qa-type').value === 'expense' ? '' : 'none'; });
  $c('qa-add').addEventListener('click', quickAdd);
  await loadOverview();
}

async function loadOverview() {
  let qs = '';
  try { qs = await getGpsQueryString(); } catch (e) { /* GPS optional */ }
  try {
    const res = await fetch('/api/dashboard/overview' + qs, { credentials: 'include' });
    const d = await res.json();
    if (!d.success) throw new Error(d.error);
    renderOverview(d);
  } catch (e) {
    $c('cc-kpis').innerHTML = `<div class="kpi"><div class="l">Could not load your dashboard</div><div class="s">${ch(e.message || 'Please refresh.')}</div></div>`;
  }
}

function renderOverview(d) {
  const f = d.farm;
  $c('cc-sub').textContent = [f.location, f.farm_size_acres ? cn(f.farm_size_acres, 1) + ' acres' : null, f.soil_type].filter(Boolean).join(' · ') || 'Add your location and farm size in your profile for a personalised view.';

  const soil = d.soil, fin = d.finance, w = d.weather;
  $c('cc-kpis').innerHTML = [
    kpi('Active crops', cn(f.active_crops), f.active_crops ? 'growing now' : 'none saved yet', f.active_crops ? 'good' : ''),
    kpi('Soil health', soil.has_data ? soil.score + '/100' : '—', soil.has_data ? soil.band : 'no check yet', soil.has_data ? (soil.score >= 70 ? 'good' : soil.score >= 45 ? 'warn' : 'bad') : ''),
    kpi('Temperature', w.available ? cn(w.current.temperature, 0) + '°C' : '—', w.available ? (w.current.weather || '') : 'weather unavailable', ''),
    kpi('Net income', fin.has_data ? cinr(fin.net_rs) : '—', fin.has_data ? `${cinr(fin.total_income_rs)} in · ${cinr(fin.total_expenses_rs)} out` : 'no records yet', fin.has_data ? (fin.net_rs >= 0 ? 'good' : 'bad') : ''),
  ].join('');

  renderPlanCard(d.decision_plan, d.recent_plans);
  renderCrops(d.current_crops);
  renderSoil(soil);
  renderWeather(w);
  renderIrrigation(d.irrigation);
  renderActivities(d.activities);
  renderMarket(d.market);
  renderYield(d.yield);
  renderFinance(fin);
  renderRecent(d.recent);
}

const kpi = (l, v, s, cls) => `<div class="kpi ${cls || ''}"><div class="l">${ch(l)}</div><div class="v">${ch(v)}</div><div class="s">${ch(s)}</div></div>`;

function renderPlanCard(plan, recent) {
  const el = $c('cc-plan-card');
  if (plan.has_data) {
    el.innerHTML = `<div style="background:rgba(255,255,255,.12);border-radius:12px;padding:12px"><b>Latest saved plan: ${ch(ccap(plan.crop))}</b><br>${ch(plan.headline)}<br>
      <a style="color:#fff;font-weight:700" href="/decision-engine?plan=${encodeURIComponent(plan.plan_id)}">Open plan →</a></div>`;
  } else if (recent && recent.length) {
    el.innerHTML = `<div style="background:rgba(255,255,255,.12);border-radius:12px;padding:12px">Latest draft: <b>${ch(ccap(recent[0].crop))}</b> — <a style="color:#fff;font-weight:700" href="/decision-engine?plan=${encodeURIComponent(recent[0].plan_id)}">open</a></div>`;
  } else el.innerHTML = `<span style="opacity:.8">${ch(plan.message)}</span>`;
}

function renderCrops(crops) {
  const el = $c('cc-crops');
  if (!crops.length) { el.innerHTML = empty('No active crop yet — save a plan from the Decision Engine or build a crop calendar.', ['/decision-engine', 'Build a plan']); return; }
  el.innerHTML = crops.map(c => `<div class="crop-row"><div class="top"><b>${ch(c.crop)}</b><span class="pill ${c.status === 'Growing' ? 'green' : ''}">${ch(c.status)}</span></div>
    <div class="prog"><div style="width:${c.progress_pct === null ? 0 : c.progress_pct}%"></div></div>
    <div class="hint">Sown ${ch(c.sowing_date)} · day ${ch(c.days_since_sowing)}${c.days_to_harvest !== null ? ` · harvest ${ch(c.harvest_date)} (${ch(c.days_to_harvest)} days)` : ''}${c.progress_pct !== null ? ` · ${ch(c.progress_pct)}% of cycle` : ''}</div></div>`).join('');
}

function renderSoil(s) {
  const el = $c('cc-soil');
  if (!s.has_data) { el.innerHTML = empty(s.message, ['/soil', 'Check soil']); return; }
  const circ = 2 * Math.PI * 52, off = circ * (1 - s.score / 100);
  const color = s.score >= 70 ? '#16A34A' : s.score >= 45 ? '#F59E0B' : '#E23F3F';
  el.innerHTML = `<div class="gauge"><svg viewBox="0 0 120 120" width="130" height="130"><circle cx="60" cy="60" r="52" fill="none" stroke="#EEF2EF" stroke-width="10"/>
    <circle cx="60" cy="60" r="52" fill="none" stroke="${color}" stroke-width="10" stroke-linecap="round" stroke-dasharray="${circ}" stroke-dashoffset="${off}" transform="rotate(-90 60 60)"/></svg><div class="n">${ch(s.score)}</div></div>
    <div style="text-align:center"><span class="pill ${s.score >= 70 ? 'green' : s.score >= 45 ? 'warn' : 'red'}">${ch(s.band)}</span>
    <div class="hint">N ${ch(s.n)} · P ${ch(s.p)} · K ${ch(s.k)}<br>checked ${ch(s.checked_on)}</div></div>`;
}

function renderWeather(w) {
  const el = $c('cc-weather');
  if (!w.available) { el.innerHTML = empty(w.message, ['/profile', 'Set location']); return; }
  const c = w.current;
  el.innerHTML = `<div class="wx-now"><div class="t">${ch(cn(c.temperature, 0))}°</div><div><b>${ch(c.weather || '')}</b><div class="hint">${ch(c.location || '')}<br>humidity ${ch(cn(c.humidity, 0))}% · wind ${ch(cn(c.wind_speed, 0))} km/h</div></div></div>
    <div class="fc-strip">${w.forecast.map(f => `<div><b>${ch((f.date || '').slice(5))}</b><br>${ch(cn(f.temperature, 0))}°<br><span class="rain">${ch(cn(f.rainfall || 0, 0))}mm</span></div>`).join('')}</div>
    ${w.alerts.length ? w.alerts.slice(0, 3).map(a => `<div class="alert-item ${a.severity === 'high' ? 'high' : ''}">⚠ ${ch(a.message)}</div>`).join('') : '<div class="hint" style="margin-top:8px">No rain or heat alerts this week.</div>'}`;
}

function renderIrrigation(i) {
  const el = $c('cc-irrigation');
  if (!i.has_data) { el.innerHTML = empty(i.message); return; }
  el.innerHTML = `<div class="stat"><div class="l">${ch(ccap(i.crop))}</div><div class="v" style="font-size:1.05rem">${ch(i.summary.message)}</div></div>
    <div class="irr-days">${i.schedule.map(d => `<div class="${d.needed ? 'on' : ''}">${ch((d.date || '').slice(8))}<br>${d.needed ? '💧' : '—'}</div>`).join('')}</div>
    <div class="hint" style="margin-top:6px">Water-balance rule on the live forecast.</div>`;
}

function renderActivities(a) {
  const act = $c('cc-activities'), fert = $c('cc-fert');
  if (!a.has_data) { act.innerHTML = empty(a.message); fert.innerHTML = empty('Fertilizer dates appear here once you have an active crop plan.'); return; }
  const row = (x) => `<div class="act"><span class="when ${x.in_days === 0 ? 'today' : ''}">${x.in_days === 0 ? 'Today' : 'in ' + ch(x.in_days) + 'd'}</span><div>${ch(x.label)}<small>${ch(x.crop)} · ${ch(x.date)}</small></div></div>`;
  act.innerHTML = a.upcoming.map(row).join('');
  fert.innerHTML = a.fertilizer_schedule.length ? a.fertilizer_schedule.map(row).join('') : empty('No fertilizer application due in the next two weeks.');
}

function renderMarket(m) {
  const el = $c('cc-market');
  if (!m.has_data) { el.innerHTML = empty(m.message, ['/market', 'Browse markets']); return; }
  el.innerHTML = `<div class="stat"><div class="l">${ch(ccap(m.crop))} ${m.is_prediction ? '<span class="prov prov-model">model</span>' : '<span class="prov prov-observed">observed</span>'}</div>
    <div class="v">${cinr(m.price_rs_per_quintal)}<span style="font-size:.8rem">/qtl</span></div>
    <div class="s">${m.range ? `range ${cinr(m.range[0])}–${cinr(m.range[1])} · ` : ''}${ch(m.source || '')}</div></div>`;
}

function renderYield(y) {
  const el = $c('cc-yield');
  if (!y.has_data) { el.innerHTML = empty(y.message, ['/yield', 'Predict yield']); return; }
  let html = '';
  if (y.plan_estimate) html += `<div class="stat"><div class="l">${ch(ccap(y.plan_estimate.crop))} · from your plan <span class="prov prov-model">model</span></div><div class="v">${ch(cn(y.plan_estimate.total_tonnes.expected, 2))} t</div><div class="s">range ${ch(cn(y.plan_estimate.total_tonnes.low, 2))}–${ch(cn(y.plan_estimate.total_tonnes.high, 2))} t</div></div>`;
  html += (y.history || []).slice(-4).reverse().map(r => `<div class="act"><span class="when">${ch((r.date || '').slice(5))}</span><div>${ch(ccap(r.crop))}<small>${ch(cn(r.tonnes, 2))} t on ${ch(cn(r.area_acres, 1))} acres (predicted)</small></div></div>`).join('');
  el.innerHTML = html;
}

function renderFinance(f) {
  const s = $c('cc-fin-summary');
  if (!f.has_data) {
    s.innerHTML = empty(f.message, ['/records', 'Add records']);
    $c('cc-chart-monthly-empty').innerHTML = empty('Charts appear once you add income or expenses.');
    $c('cc-chart-cats-empty').innerHTML = empty('Charts appear once you add expenses.');
    $c('cc-chart-monthly').style.display = 'none'; $c('cc-chart-cats').style.display = 'none'; return;
  }
  s.innerHTML = `<div class="stat"><div class="l">Net</div><div class="v" style="color:${f.net_rs >= 0 ? 'var(--primary-dark)' : 'var(--danger)'}">${cinr(f.net_rs)}</div>
    <div class="s">Income ${cinr(f.total_income_rs)} · Expenses ${cinr(f.total_expenses_rs)}</div></div>`;
  $c('cc-chart-monthly').style.display = ''; $c('cc-chart-cats').style.display = '';
  $c('cc-chart-monthly-empty').innerHTML = ''; $c('cc-chart-cats-empty').innerHTML = '';
  draw('cc-chart-monthly', 'bar', f.monthly.map(m => m.month), [
    { label: 'Income', data: f.monthly.map(m => m.income), backgroundColor: '#16A34A', borderRadius: 6 },
    { label: 'Expenses', data: f.monthly.map(m => m.expenses), backgroundColor: '#B45309', borderRadius: 6 }]);
  const cats = Object.entries(f.expenses_by_category);
  if (cats.length) draw('cc-chart-cats', 'doughnut', cats.map(c => c[0]), [{ data: cats.map(c => c[1]), backgroundColor: ['#16A34A', '#0F766E', '#B45309', '#0369A1', '#7C3AED', '#64748B'] }]);
  else { $c('cc-chart-cats').style.display = 'none'; $c('cc-chart-cats-empty').innerHTML = empty('No expenses recorded yet.'); }
}

function draw(id, type, labels, datasets) {
  if (typeof Chart === 'undefined') return;
  if (CC.charts[id]) CC.charts[id].destroy();
  CC.charts[id] = new Chart($c(id), { type, data: { labels, datasets },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } }, scales: type === 'bar' ? { y: { beginAtZero: true } } : {} } });
}

function renderRecent(items) {
  $c('cc-recent').innerHTML = items.length ? items.map(i => `<div class="item"><span>${ch(i.icon)}</span><div>${ch(i.text)}<small>${ch(i.when)}</small></div></div>`).join('')
    : empty('Nothing logged yet. Soil checks, yield predictions, irrigation plans and records show up here.');
}

async function quickAdd() {
  const err = $c('qa-error'); err.classList.remove('show');
  const type = $c('qa-type').value;
  const body = { amount_rs: $c('qa-amount').value, crop: $c('qa-crop').value, note: $c('qa-note').value };
  if (type === 'expense') body.category = $c('qa-cat').value;
  if (!body.amount_rs || Number(body.amount_rs) <= 0) { err.textContent = 'Enter an amount greater than 0.'; err.classList.add('show'); return; }
  try {
    const res = await fetch(`/api/farm/${type}`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await res.json();
    if (!d.success) throw new Error(d.error || 'Could not add the record.');
    $c('qa-amount').value = ''; $c('qa-crop').value = ''; $c('qa-note').value = '';
    await loadOverview();
  } catch (e) { err.textContent = e.message; err.classList.add('show'); }
}
