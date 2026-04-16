/**
 * step0-dashboard.js — Welcome Dashboard logic
 */
import { API, safeFetchJson } from './api.js';
import { plnShort, loadingHtml, emptyHtml } from './ui.js';
import { enableAssistantMode, loadDashActionCards } from './copilot.js';

export async function loadStartDashboard() {
  // Turn on the full-panel assistant + load proactive action cards.
  // Both calls are idempotent so repeat goStep(0) is safe.
  try { enableAssistantMode(); } catch (e) {}
  try { loadDashActionCards(); } catch (e) {}
  try { loadSpendWidget(); } catch (e) {}
  try { loadBiStatusWidget(); } catch (e) {}
  try { loadTaxonomyWidget(); } catch (e) {}

  try {
    // Fetch KPI + catalog + suppliers in parallel
    const [kpiRes, catRes, suppRes] = await Promise.allSettled([
      safeFetchJson(API + '/buying/kpi'),
      safeFetchJson(API + '/buying/catalog'),
      safeFetchJson(API + '/buying/orders'),
    ]);

    // KPI
    const kpi = kpiRes.status === 'fulfilled' ? kpiRes.value : {};
    const dk = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    dk('dkOrders', kpi.orders_total ?? 0);
    dk('dkSpend', kpi.total_spend ? (kpi.total_spend > 1000 ? (kpi.total_spend/1000).toFixed(1) + 'k' : kpi.total_spend.toFixed(0)) : '0');
    dk('dkSavings', kpi.avg_savings_pct ? kpi.avg_savings_pct.toFixed(1) + '%' : '\u2014');

    // Catalog count
    const catalog = catRes.status === 'fulfilled' ? catRes.value : [];
    dk('dkCatalog', Array.isArray(catalog) ? catalog.length : '\u2014');

    // Suppliers count (from catalog unique suppliers)
    let supplierSet = new Set();
    if (Array.isArray(catalog)) catalog.forEach(p => { if (p.supplier) supplierSet.add(p.supplier); if (p.suppliers) p.suppliers.forEach(s => supplierSet.add(s.name || s)); });
    dk('dkSuppliers', supplierSet.size || '4');

    // Compliance
    dk('dkCompliance', '94%');

    // KPI change indicators
    const setChange = (id, text, cls) => { const el = document.getElementById(id); if (el) { el.textContent = text; el.className = 'dk-change ' + cls; } };
    setChange('dkSuppChange', '+2 nowych', 'up');
    setChange('dkOrdChange', kpi.orders_total ? kpi.orders_total + ' aktywnych' : 'Brak', '');
    setChange('dkSavChange', kpi.avg_savings_pct > 0 ? '\u2191 ' + kpi.avg_savings_pct.toFixed(1) + '%' : '', 'up');
    setChange('dkCompChange', '\u2191 stabilny', 'up');

    // Recent activity from orders
    const orders = suppRes.status === 'fulfilled' ? suppRes.value : [];
    const actEl = document.getElementById('dashActivity');
    if (actEl) {
      const ordersList = Array.isArray(orders) ? orders : (orders.orders || []);
      if (ordersList.length > 0) {
        const statusColors = { draft:'blue', pending_approval:'amber', approved:'green', po_generated:'purple', confirmed:'green', shipped:'blue', delivered:'green', cancelled:'red' };
        const statusLabels = { draft:'Szkic', pending_approval:'Oczekuje', approved:'Zatwierdzono', po_generated:'PO wygenerowano', confirmed:'Potwierdzone', shipped:'W dostawie', delivered:'Dostarczone', cancelled:'Anulowane' };
        actEl.innerHTML = ordersList.slice(0, 6).map(o => {
          const col = statusColors[o.status] || 'blue';
          const label = statusLabels[o.status] || o.status;
          const date = o.created_at ? new Date(o.created_at).toLocaleDateString('pl-PL') : '';
          return '<div class="activity-item"><div class="activity-dot ' + col + '"></div><div class="activity-text"><b>' + (o.order_number || o.id || '\u2014') + '</b> \u2014 ' + label + '<br><span style="font-size:11px;color:var(--txt2)">' + (o.total_items || 0) + ' poz. \u00b7 ' + (o.total ? o.total.toFixed(2) + ' PLN' : '') + '</span></div><div class="activity-time">' + date + '</div></div>';
        }).join('');
      } else {
        actEl.innerHTML = '<div style="text-align:center;padding:24px;color:var(--txt2)"><div style="font-size:32px;margin-bottom:8px">\uD83D\uDE80</div><b>Brak zamowien</b><br><span style="font-size:12px">Kliknij "Nowe zapotrzebowanie" zeby zaczac</span></div>';
      }
    }
  } catch (err) {
    console.warn('Dashboard KPI load error:', err);
    const actEl = document.getElementById('dashActivity');
    if (actEl) actEl.innerHTML = '<div style="text-align:center;padding:24px;color:var(--txt2)"><div style="font-size:32px;margin-bottom:8px">\uD83D\uDE80</div><b>Gotowy do pracy</b><br><span style="font-size:12px">Wybierz akcje z kafelkow powyzej</span></div>';
  }
}


/* ─── Spend widget (MVP-3) ─── */

const _plnFmt = plnShort; // shared util, kept local alias for readability

export async function loadSpendWidget() {
  const sel = document.getElementById('dswPeriod');
  const period = sel ? parseInt(sel.value, 10) : 90;

  const sub = document.getElementById('dswSubtitle');
  if (sub) {
    sub.textContent = period === 0
      ? 'Wszystkie zamowienia'
      : ('Ostatnie ' + period + ' dni');
  }

  try {
    const data = await safeFetchJson(API + '/buying/spend-analytics?period_days=' + period);
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };

    set('dswTotal', _plnFmt(data.total_spend));
    set('dswOrderCount', (data.order_count || 0) + ' zamowien');
    set('dswDirect', _plnFmt(data.direct_spend) + ' (' + (data.direct_pct || 0).toFixed(0) + '%)');
    set('dswIndirect', _plnFmt(data.indirect_spend) + ' (' + (data.indirect_pct || 0).toFixed(0) + '%)');

    const d = document.getElementById('dswBarDirect');
    const i = document.getElementById('dswBarIndirect');
    if (d) d.style.width = (data.direct_pct || 0) + '%';
    if (i) i.style.width = (data.indirect_pct || 0) + '%';

    const top = document.getElementById('dswTopCats');
    const cats = data.top_categories || [];
    if (!cats.length) {
      if (top) top.innerHTML = '<div class="section-label">Brak wydatkow w wybranym okresie</div>';
      return;
    }
    const max = cats[0].spend || 1;
    if (top) {
      top.innerHTML = '<div class="section-label">Top kategorie</div>'
        + cats.map(c => {
            const pct = max ? (c.spend / max * 100) : 0;
            const kind = c.group === 'indirect' ? 'indirect' : 'direct';
            return '<div class="dsw-cat-row">'
              + '<div class="dsw-cat-label">'
                + '<span class="dsw-cat-kind ' + kind + '">' + (kind === 'direct' ? 'D' : 'I') + '</span>'
                + (c.label || c.category)
              + '</div>'
              + '<div class="dsw-cat-track"><div class="dsw-cat-fill ' + kind + '" style="width:' + pct.toFixed(0) + '%"></div></div>'
              + '<div class="dsw-cat-spend">' + _plnFmt(c.spend) + '</div>'
            + '</div>';
          }).join('');
    }
  } catch (e) {
    const top = document.getElementById('dswTopCats');
    if (top) top.innerHTML = '<div class="section-label" style="color:var(--err)">Blad ladowania spend</div>';
  }
}


/* ─── BI status widget ─── */

const _BI_SHORT_LABELS = {
  'SAP ERP (mock)': 'ERP',
  'Enterprise BI (mock)': 'BI',
  'Salesforce CRM (mock)': 'CRM',
  'Finance Ledger (mock)': 'Finance',
  'SAP EWM (mock)': 'WMS',
};

export async function loadBiStatusWidget() {
  const el = document.getElementById('dbsChips');
  if (!el) return;
  try {
    const data = await safeFetchJson(API + '/bi/status');
    const connectors = data.connectors || [];
    if (!connectors.length) {
      el.innerHTML = '<span class="dbs-chip loading">Brak adapterow</span>';
      return;
    }
    el.innerHTML = connectors.map(c => {
      const status = c.status === 'ok' ? 'ok'
        : c.status === 'degraded' ? 'degraded'
        : 'mock';
      const short = _BI_SHORT_LABELS[c.name] || c.name;
      const latency = c.latency_ms ? Math.round(c.latency_ms) + 'ms' : '';
      const title = (c.name || short) + ' — ' + (c.note || '') + (latency ? ' · ' + latency : '');
      return '<span class="dbs-chip ' + status + '" title="' + title.replace(/"/g, '&quot;') + '">'
        + short
        + (latency ? '<span class="dbs-latency">' + latency + '</span>' : '')
      + '</span>';
    }).join('');
  } catch (e) {
    el.innerHTML = '<span class="dbs-chip degraded">Brak polaczenia</span>';
  }
}


/* ─── Taxonomy widget (10 domen × 27 subdomen) ─── */

function _escHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export async function loadTaxonomyWidget() {
  const tree = document.getElementById('dtxTree');
  const summary = document.getElementById('dtxSummary');
  if (!tree) return;
  tree.innerHTML = loadingHtml('Czytanie taksonomii zakupow...');
  try {
    const data = await safeFetchJson(API + '/domains/extended');
    const s = data.summary || {};
    if (summary && s.domains_total) {
      summary.textContent = s.domains_total + ' domen · ' + s.subdomains_total + ' subdomen';
    }
    const domains = data.domains || [];
    const direct = domains.filter(d => d.category === 'direct');
    const indirect = domains.filter(d => d.category === 'indirect');
    const html = [];
    html.push(_renderTaxSection('Direct &mdash; produkty do sprzedazy', 'direct', direct));
    html.push(_renderTaxSection('Indirect &mdash; OPEX', 'indirect', indirect));
    tree.innerHTML = html.join('');
  } catch (e) {
    tree.innerHTML = '<div style="font-size:11px;color:var(--err)">Blad ladowania taksonomii</div>';
  }
}

function _renderTaxSection(title, kind, domains) {
  if (!domains.length) return '';
  const rows = domains.map(d => {
    const subs = (d.subdomains || []).map(s => {
      const label = s.subdomain.replace(/_/g, ' ');
      return '<span class="dtx-sub-chip ' + kind + '" title="' + _escHtml(s.suppliers_count) + ' dostawcow">'
        + _escHtml(label) + '</span>';
    }).join('');
    const dom = _escHtml(d.domain);
    return '<div class="dtx-domain-row">'
      + '<div class="dtx-domain-head">'
        + '<span>' + _escHtml(d.label || d.domain) + '</span>'
        + '<span class="dtx-count">'
          + (d.subdomains ? d.subdomains.length : 0) + ' subdomen'
          + ' &middot; <a href="#" onclick="event.preventDefault();optimizeSubdomains(\'' + dom + '\')" style="color:var(--gold);font-weight:700;text-decoration:none">Optymalizuj &#9654;</a>'
        + '</span>'
      + '</div>'
      + (subs ? '<div class="dtx-subdomain-chips">' + subs + '</div>' : '')
      + '<div class="dtx-opt-result" id="dtxOpt-' + dom + '" style="display:none;margin-top:8px"></div>'
    + '</div>';
  }).join('');
  return '<div class="dtx-kind-title ' + kind + '">' + title + ' (' + domains.length + ')</div>' + rows;
}


export async function optimizeSubdomains(domain) {
  const slot = document.getElementById('dtxOpt-' + domain);
  if (!slot) return;
  if (slot.style.display === 'block') {
    slot.style.display = 'none';
    return;
  }
  slot.style.display = 'block';
  slot.innerHTML = loadingHtml('Liczenie subdomen...');
  try {
    const data = await safeFetchJson(
      API + '/dashboard/subdomain-aggregate/demo?domain=' + encodeURIComponent(domain),
    );
    if (data.error) {
      slot.innerHTML = '<div style="font-size:11px;color:var(--err)">' + _escHtml(data.message || 'Blad') + '</div>';
      return;
    }
    const agg = data.aggregate || {};
    const subs = data.subdomains || [];
    const maxCost = Math.max(1, ...subs.map(s => s.total_cost_pln || 0));
    const rows = subs.map(s => {
      if (!s.success) {
        return '<div class="dtx-sub-row miss">'
          + '<span class="dtx-sub-name">' + _escHtml(s.subdomain.replace(/_/g, ' ')) + '</span>'
          + '<span class="dtx-sub-miss">infeasible</span>'
        + '</div>';
      }
      const pct = (s.total_cost_pln / maxCost) * 100;
      const top = (s.top_suppliers || [])[0];
      const topStr = top ? top.supplier_name : '';
      return '<div class="dtx-sub-row">'
        + '<span class="dtx-sub-name">' + _escHtml(s.subdomain.replace(/_/g, ' ')) + '</span>'
        + '<span class="dtx-sub-bar"><span class="dtx-sub-fill" style="width:' + pct.toFixed(0) + '%"></span></span>'
        + '<span class="dtx-sub-cost">' + _plnShortTax(s.total_cost_pln) + '</span>'
        + '<span class="dtx-sub-sup">' + s.suppliers_used + ' dost. · ' + _escHtml(topStr) + '</span>'
      + '</div>';
    }).join('');
    slot.innerHTML =
      '<div class="dtx-opt-agg">'
        + '<b>Razem: ' + _plnShortTax(agg.total_cost_pln) + '</b>'
        + ' · unique sup: ' + agg.unique_suppliers
        + ' · ' + data.total_time_ms + 'ms'
      + '</div>'
      + '<div class="dtx-opt-list">' + rows + '</div>';
  } catch (e) {
    slot.innerHTML = '<div style="font-size:11px;color:var(--err)">Blad: ' + _escHtml(e.message) + '</div>';
  }
}

const _plnShortTax = plnShort;
