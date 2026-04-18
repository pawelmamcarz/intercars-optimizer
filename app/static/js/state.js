/**
 * state.js — Shared mutable state for the Flow Procurement wizard (index.html)
 *
 * Every top-level `let` variable from the main <script> block is gathered here
 * so that future ES-module step files can import and mutate a single source of
 * truth instead of relying on implicit globals.
 *
 * Usage:
 *   import { state, persistCart, restoreCart } from './state.js';
 *   state.currentStep = 2;
 */

const CART_STORAGE_KEY = 'flow_cart_v1';

/** Persist the current cart to localStorage. Silently no-ops on quota / SSR. */
export function persistCart() {
  try {
    const serial = {
      items: state._s1SelectedItems || {},
      domain: state.currentDomain || '',
      unspsc: state._selectedUnspscCode || '',
      path: state.currentS1Path || '',
      savedAt: Date.now(),
    };
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(serial));
  } catch (_) { /* storage disabled or quota full — cart still works in-memory */ }
}

/** Rehydrate cart from localStorage (called once on bootstrap). */
export function restoreCart() {
  try {
    const raw = localStorage.getItem(CART_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    // Age-off carts older than 7 days so stale data doesn't haunt returning users.
    if (parsed.savedAt && Date.now() - parsed.savedAt > 7 * 24 * 3600 * 1000) {
      localStorage.removeItem(CART_STORAGE_KEY);
      return;
    }
    if (parsed.items && typeof parsed.items === 'object') {
      state._s1SelectedItems = parsed.items;
    }
    if (parsed.domain) state.currentDomain = parsed.domain;
    if (parsed.unspsc) state._selectedUnspscCode = parsed.unspsc;
    // Restore the Step 1 path (catalog/adhoc/cif/marketplace) so a user who
    // was mid-session sees the same view. Default to 'catalog' when we have
    // items but no recorded path (e.g. older snapshot from pre-F5 storage) —
    // that way the catalog view renders with item quantities highlighted.
    if (parsed.path) {
      state.currentS1Path = parsed.path;
    } else if (Object.keys(state._s1SelectedItems || {}).length > 0 && !state.currentS1Path) {
      state.currentS1Path = 'catalog';
    }
  } catch (_) { /* corrupt payload — ignore */ }
}

/** Clear persisted cart (call after successful checkout). */
export function clearPersistedCart() {
  try { localStorage.removeItem(CART_STORAGE_KEY); } catch (_) {}
}

export const state = {
  // ── Domain & navigation ───────────────────────────────────────────────
  currentDomain: 'parts',
  currentStep: 0,
  categorySelected: false,

  // ── UNSPSC search ─────────────────────────────────────────────────────
  _selectedUnspscCode: '',
  _selectedUnspscLabel: '',
  _unspscTimer: null,

  // ── Data maps (loaded from API / demo) ────────────────────────────────
  productLabels: {},
  demandMap: {},
  totalSuppliers: 8,

  // ── Chart instances (Chart.js / Cytoscape) ────────────────────────────
  paretoChartInst: null,
  paretoMcInst: null,
  _lastOptimizeReq: null,     // { suppliers, demand } — used by MC re-solve
  radarChartInst: null,
  cyInstance: null,
  xyParetoInst: null,
  donutInst: null,
  mcHistInst: null,
  stabilityInst: null,
  predProfilesChart: null,

  // ── Step 1 — Zapotrzebowanie ──────────────────────────────────────────
  currentS1Kind: 'all',          // 'all' | 'direct' | 'indirect'
  currentS1Path: '',
  _s1CatalogData: [],
  _s1SelectedItems: {},        // { [id]: { ...item, qty } }
  _adhocRowId: 0,

  // ── Step 2 — Dostawcy ─────────────────────────────────────────────────
  step2Loaded: false,

  // ── Step 3 — Optymalizacja ────────────────────────────────────────────
  lastParetoPoints: [],
  lastOptDemand: [],           // demand for cross-module bridge
  lastOptAllocation: null,     // last allocation result
  currentAllocs: [],
  sortState: { key: null, dir: 'asc' },
  dataSource: 'demo',
  dbAvailable: false,

  // ── Step 4 — Zamowienie / Buying ──────────────────────────────────────
  _s4CurrentView: 'review',
  obCatalog: [],
  obCategories: [],
  obCart: [],                  // [{ id, quantity }]
  obCartState: null,
  obActiveCategory: 'all',
  _pendingOptimizationId: null,
  obInitialized: false,

  // ── Step 5 — Monitoring / Process Mining ──────────────────────────────
  _monSource: 'demo',
  _monSuppliers: [],
  pmReport: null,
  dfgView: 'frequency',

  // ── Marketplace ───────────────────────────────────────────────────────
  _mktAllegroData: [],
  _mktPunchoutSessionId: '',
  _mktPunchoutData: [],
  _mktPunchoutCategory: '',

  // ── Supplier panel ────────────────────────────────────────────────────
  suppInitialized: false,
  _suppCurrentId: null,

  // ── Copilot / AI assistant ────────────────────────────────────────────
  copilotOpen: false,
  copilotHistory: [],

  // ── Product detail modal ──────────────────────────────────────────────
  _pdmCurrentItem: null,
};
