/**
 * api.js — Shared API helpers for the Flow Procurement Platform
 * Usage:  import { API, safeFetchJson, apiGet, apiPost, apiPut } from './api.js';
 */

// API base URL — relative, works on any deployment
export const API = '/api/v1';

/**
 * Fetch JSON with automatic error handling.
 * Throws an Error whose message is the server's `detail` field (if available)
 * or the HTTP statusText.
 */
export async function safeFetchJson(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { const e = await r.json(); msg = e.detail || msg; } catch (_) {}
    throw new Error(msg);
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
