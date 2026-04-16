/**
 * ui.js — Common UI utilities for the Flow Procurement Platform
 *
 * Exports small, reusable helpers that appear across index.html, admin.html,
 * portal.html, requester.html and superadmin.html.
 */

// ── DOM shortcut ────────────────────────────────────────────────────────────
/** Shorthand for document.getElementById */
export const $ = id => document.getElementById(id);

// ── Number formatting ───────────────────────────────────────────────────────
/** Fixed-decimal format (default 4 digits). Returns '--' for non-numbers. */
export const fmt = (n, d = 4) => typeof n === 'number' ? n.toFixed(d) : '--';

/** Percentage format (e.g. 0.123 → '12.3%'). */
export const pct = n => (n * 100).toFixed(1) + '%';

/** Polish locale currency format: 1234.5 → '1 234,50'. */
export const plnFmt = n =>
  typeof n === 'number'
    ? n.toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '—';

// ── Chart colours ───────────────────────────────────────────────────────────
export const COLORS = [
  '#D4A843', '#1B2A4A', '#10B981', '#6366F1',
  '#EF4444', '#EC4899', '#F97316', '#0EA5E9',
];

// ── Tab switching ───────────────────────────────────────────────────────────
/**
 * Generic tab switcher used in admin.html, portal.html, etc.
 * Expects `.tab-btn` buttons and `.panel` containers with id="panel-<name>".
 *
 * @param {string} name   The tab/panel name suffix
 * @param {Event}  [evt]  The click event (optional — when called programmatically)
 */
export function switchTab(name, evt) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));

  const panel = document.getElementById('panel-' + name);
  if (panel) panel.classList.add('active');

  if (evt && evt.target) {
    evt.target.classList.add('active');
  } else {
    const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
    if (btn) btn.classList.add('active');
  }
}

// ── Toast notifications ─────────────────────────────────────────────────────
/**
 * Show a brief notification toast.
 * Requires an element with id="toast" in the page.
 *
 * @param {string}  msg      Text to display
 * @param {boolean} isError  If true, adds the 'error' class for red styling
 */
export function toast(msg, isError = false) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className = 'toast ' + (isError ? 'error' : 'ok');
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3500);
}

// ── Modal management ────────────────────────────────────────────────────────
/** Show a modal/overlay by id (assumes display:flex layout). */
export function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'flex';
}

/** Hide a modal/overlay by id. */
export function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}
