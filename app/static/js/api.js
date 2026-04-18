/**
 * api.js — Shared API helpers for the Flow Procurement Platform
 * Usage:  import { API, safeFetchJson, apiGet, apiPost, apiPut } from './api.js';
 *
 * Authorization is auto-attached from one of the known tokens in localStorage
 * (buyer_token / admin_token / portal_token / superadmin_token). Each SPA
 * sets its key via `createAuth({ storageKey })`. If multiple are present,
 * the first non-empty one wins — apps don't share a tab so collisions are
 * cheap to ignore.
 */

// API base URL — relative, works on any deployment
export const API = '/api/v1';

const _TOKEN_KEYS = ['buyer_token', 'admin_token', 'portal_token', 'superadmin_token', 'requester_token'];

/** Look up the first available JWT in localStorage. */
function _readToken() {
  if (typeof localStorage === 'undefined') return '';
  for (const k of _TOKEN_KEYS) {
    const v = localStorage.getItem(k);
    if (v) return v;
  }
  return '';
}

/** Merge caller-provided headers with auto Authorization. Caller wins. */
function _withAuth(headers) {
  const tok = _readToken();
  if (!tok) return headers || {};
  const out = { ...(headers || {}) };
  if (!out.Authorization && !out.authorization) {
    out.Authorization = 'Bearer ' + tok;
  }
  return out;
}

/**
 * Fetch JSON with automatic error handling and Bearer token injection.
 * Throws an Error whose message is the server's `detail` field (if available)
 * or the HTTP statusText.
 */
export async function safeFetchJson(url, opts = {}) {
  const merged = { ...opts, headers: _withAuth(opts.headers) };
  const r = await fetch(url, merged);
  if (!r.ok) {
    let msg = r.statusText;
    try { const e = await r.json(); msg = e.detail || msg; } catch (_) {}
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return r.json();
}

/** GET helper — prepends API base URL */
export function apiGet(path, headers = {}) {
  return safeFetchJson(API + path, { headers });
}

/** POST helper — prepends API base URL, serialises body as JSON */
export function apiPost(path, body, headers = {}) {
  return safeFetchJson(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
}

/** PUT helper — prepends API base URL, serialises body as JSON */
export function apiPut(path, body, headers = {}) {
  return safeFetchJson(API + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
}
