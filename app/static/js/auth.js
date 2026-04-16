/**
 * auth.js — Parameterised authentication module for the Flow Procurement Platform
 *
 * Works for every app (index, admin, portal, requester, superadmin) — just
 * pass the appropriate `storageKey` and optional callbacks.
 *
 * Usage:
 *   import { createAuth } from './auth.js';
 *   const auth = createAuth({
 *     storageKey: 'admin_token',
 *     onLogin(data)  { showMain(data.user); },
 *     onLogout()     { location.reload(); },
 *   });
 */

import { safeFetchJson } from './api.js';

/**
 * Factory that returns an auth object bound to a specific localStorage key.
 *
 * @param {Object}   opts
 * @param {string}   opts.storageKey   localStorage key for the JWT token
 * @param {Function} [opts.onLogin]    called after successful login(data)
 * @param {Function} [opts.onLogout]   called after logout()
 */
export function createAuth({ storageKey, onLogin, onLogout }) {
  let TOKEN = localStorage.getItem(storageKey) || '';

  const auth = {
    /** Return the current raw JWT string (empty when logged out). */
    getToken() {
      return TOKEN;
    },

    /**
     * Return standard auth + JSON headers — mirrors the `H()` helper used in
     * admin.html / portal.html.
     */
    H() {
      return {
        'Authorization': 'Bearer ' + TOKEN,
        'Content-Type': 'application/json',
      };
    },

    /** Quick boolean check. */
    isLoggedIn() {
      return !!TOKEN;
    },

    /**
     * Perform login via POST /auth/login.
     * On success stores the token and invokes the optional `onLogin` callback.
     */
    async login(username, password) {
      const data = await safeFetchJson('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      TOKEN = data.access_token;
      localStorage.setItem(storageKey, TOKEN);
      if (onLogin) onLogin(data);
      return data;
    },

    /** Clear the token from memory and localStorage, then invoke `onLogout`. */
    logout() {
      TOKEN = '';
      localStorage.removeItem(storageKey);
      if (onLogout) onLogout();
    },

    /**
     * Validate the current token against GET /auth/me.
     * Returns the user object on success, or `null` if the token is missing /
     * expired / invalid (and clears it from storage in that case).
     */
    async checkSession() {
      if (!TOKEN) return null;
      try {
        const res = await fetch('/auth/me', {
          headers: { 'Authorization': 'Bearer ' + TOKEN },
        });
        if (res.ok) return await res.json();
      } catch (_) { /* network error — treat as logged out */ }
      TOKEN = '';
      localStorage.removeItem(storageKey);
      return null;
    },
  };

  return auth;
}
