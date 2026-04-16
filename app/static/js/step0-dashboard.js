/**
 * step0-dashboard.js — Welcome Dashboard logic
 */
import { API, safeFetchJson } from './api.js';
import { enableAssistantMode, loadDashActionCards } from './copilot.js';

export async function loadStartDashboard() {
  // Turn on the full-panel assistant + load proactive action cards.
  // Both calls are idempotent so repeat goStep(0) is safe.
  try { enableAssistantMode(); } catch (e) {}
  try { loadDashActionCards(); } catch (e) {}
  try { loadSpendWidget(); } catch (e) {}

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

function _plnFmt(v) {
  if (!v) return '0 PLN';
  if (v >= 1e6) return (v / 1e6).toFixed(1).replace('.', ',') + ' mln PLN';
  if (v >= 1e3) return Math.round(v / 1e3) + ' tys. PLN';
  return Math.round(v) + ' PLN';
}

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
