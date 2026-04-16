/**
 * state.js — Shared mutable state for the Flow Procurement wizard (index.html)
 *
 * Every top-level `let` variable from the main <script> block is gathered here
 * so that future ES-module step files can import and mutate a single source of
 * truth instead of relying on implicit globals.
 *
 * Usage:
 *   import { state } from './state.js';
 *   state.currentStep = 2;
 */

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
