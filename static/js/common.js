// common.js — runs on every page (included via base.html). Only touches
// elements that exist in base.html's nav, so it's safe everywhere.

// Escapes text before it's interpolated into an innerHTML template string.
// Anywhere a user can type free text that later gets rendered back (farm
// record notes/crop names, a registered user's name/location in the admin
// panel, a notification title, etc.), skipping this would let something
// like <img src=x onerror=...> execute in whoever's browser views it.
// Defined here (loaded first on every page, before script.js) so it's
// available to common.js's own renderers as well as script.js's.
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function initCommon() {
  initLanguage();

  const logoutBtn = document.getElementById('nav-logout-btn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {});
      window.location.href = '/login';
    });
  }

  const deleteBtn = document.getElementById('nav-delete-btn');
  if (deleteBtn) deleteBtn.addEventListener('click', handleDeleteAccount);

  initThemeToggle();
  initDropdown('nav-more-btn', 'nav-more-panel');
  initDropdown('avatar-btn', 'avatar-panel');
  initDropdown('nav-notif-btn', 'notif-panel');
  loadNavNotifications();
}

function initThemeToggle() {
  const btn = document.getElementById('theme-toggle-btn');
  if (!btn) return;
  const apply = (theme) => {
    document.documentElement.setAttribute('data-theme', theme);
    btn.textContent = theme === 'dark' ? '☀️' : '🌙';
  };
  apply(localStorage.getItem('krushi-theme') || 'light');
  btn.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    localStorage.setItem('krushi-theme', next);
    apply(next);
  });
}

function initDropdown(btnId, panelId) {
  const btn = document.getElementById(btnId);
  const panel = document.getElementById(panelId);
  if (!btn || !panel) return;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    panel.classList.toggle('show');
  });
  document.addEventListener('click', (e) => {
    if (!panel.contains(e.target) && e.target !== btn) panel.classList.remove('show');
  });
}

async function handleDeleteAccount() {
  if (!confirm('This permanently deletes your account and all your data (records, logs, history). This cannot be undone. Continue?')) return;
  const password = prompt('Enter your password to confirm account deletion:');
  if (!password) return;

  try {
    const res = await fetch('/api/auth/delete-account', {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const data = await res.json();
    if (!data.success) { alert(data.error || 'Could not delete account.'); return; }
    window.location.href = '/login';
  } catch (e) {
    alert('Could not delete account — please try again.');
  }
}

// Real browser GPS is far more likely to produce a usable forecast (and
// therefore real rain/disease-risk alerts) than the profile's free-text
// location field, which many users never fill in. Used for the nav
// notification bell (every page) and the home page's own notif widget.
// Fails silently (empty string) if denied/unavailable — the backend
// falls back to profile location either way.
async function getGpsQueryString() {
  try {
    const pos = await new Promise((resolve, reject) => {
      if (!navigator.geolocation) { reject(); return; }
      navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 4000 });
    });
    return `?lat=${pos.coords.latitude}&lon=${pos.coords.longitude}`;
  } catch (e) {
    return '';
  }
}

const NOTIF_ICONS = { rain: '🌧️', fertilizer: '🚜', harvest: '🌾', disease_risk: '🐛', disease_alert: '🐛' };

function renderNotifItems(notifications) {
  if (!notifications || !notifications.length) {
    return '<p class="notif-empty">Nothing needs attention right now — build a crop calendar for '
      + 'fertilizer/harvest reminders, and make sure your location is set (rain/disease-risk alerts need it).</p>';
  }
  return notifications.map(n => `
    <div class="notif-item"><span class="icon">${NOTIF_ICONS[n.type] || '🔔'}</span>
    <div><div class="title">${escapeHtml(n.title)}</div><div class="msg">${escapeHtml(n.message)}</div></div></div>`).join('');
}

async function loadNavNotifications() {
  const wrap = document.getElementById('notif-wrap');
  const badge = document.getElementById('nav-notif-badge');
  const list = document.getElementById('notif-panel-list');
  if (!wrap || !badge) return;
  // On the home page, initHomePage() already fetches the full
  // notifications list (which does a live weather call) — fetching it
  // again here just for the badge count doubles that work. Reuse that
  // page's own render target instead of a second independent fetch.
  if (document.getElementById('home-notif-list')) {
    wrap.style.display = 'inline-flex';
    return;
  }
  wrap.style.display = 'inline-flex';
  try {
    const gps = await getGpsQueryString();
    const res = await fetch(`/api/notifications${gps}`, { credentials: 'include' });
    if (res.status === 401) { wrap.style.display = 'none'; return; }
    const data = await res.json();
    const notifications = (data.success && data.notifications) || [];
    badge.textContent = notifications.length ? String(notifications.length) : '';
    if (list) list.innerHTML = renderNotifItems(notifications);
  } catch (e) {
    if (list) list.innerHTML = '<p class="notif-empty">Could not load alerts.</p>';
  }
}
