/**
 * product-detail.js — Product detail modal
 */
import { $ } from './ui.js';
import { state } from './state.js';
import { renderMktAllegro, renderMktPunchout, updateS1Summary, updateGlobalCartBadge } from './step1-demand.js';

export function openProductDetail(pid) {
  const item = state._mktPunchoutData.find(p => p.id === pid)
    || state._mktAllegroData.find(p => p.id === pid)
    || Object.values(state._s1SelectedItems).find(p => p.id === pid);
  if (!item) return;
  state._pdmCurrentItem = item;

  const d = item.details || {};
  document.getElementById('pdmTitle').textContent = item.name || item.id;
  document.getElementById('pdmPrice').innerHTML = (item.price || 0).toFixed(2) + ' PLN <span class="pdm-price-unit">/ ' + (item.unit || 'szt') + '</span>';

  const inCart = state._s1SelectedItems[pid];
  document.getElementById('pdmQtyInput').value = inCart ? inCart.qty : (d.min_order_qty || 1);

  const source = item.source === 'punchout' ? 'PunchOut cXML' : 'Allegro';
  const srcColor = item.source === 'punchout' ? 'background:#F3E8FF;color:#7C3AED' : 'background:#FFF7ED;color:#EA580C';

  let html = '';

  html += '<div class="pdm-badges">';
  html += '<span class="pdm-badge" style="' + srcColor + '">' + source + '</span>';
  if (item.supplier_name) html += '<span class="pdm-badge" style="background:#DBEAFE;color:#1E40AF">&#127970; ' + item.supplier_name + '</span>';
  if (item.contract_no) html += '<span class="pdm-badge" style="background:#D1FAE5;color:#065F46">&#128196; ' + item.contract_no + '</span>';
  html += '</div>';

  if (item.description) {
    html += '<div class="pdm-section"><div class="pdm-section-title">Opis produktu</div>';
    html += '<p style="font-size:13px;color:var(--txt);line-height:1.6;margin:0">' + item.description + '</p></div>';
  }

  html += '<div class="pdm-section"><div class="pdm-section-title">Logistyka i dostawa</div><div class="pdm-grid">';
  html += '<div class="pdm-field"><div class="pdm-field-label">Lead time</div><div class="pdm-field-value">&#128666; ' + (d.lead_time_note || (item.delivery_days || '?') + ' dni roboczych') + '</div></div>';
  html += '<div class="pdm-field"><div class="pdm-field-label">Warunki platnosci</div><div class="pdm-field-value">&#128179; ' + (d.payment_terms || 'Przelew 30 dni') + '</div></div>';
  html += '<div class="pdm-field"><div class="pdm-field-label">Gwarancja</div><div class="pdm-field-value">&#128737; ' + (d.warranty || '12 mies.') + '</div></div>';
  html += '<div class="pdm-field"><div class="pdm-field-label">Zwroty</div><div class="pdm-field-value">&#128257; ' + (d.return_policy || '14 dni na zwrot') + '</div></div>';
  html += '</div></div>';

  if (d.delivery_locations && d.delivery_locations.length) {
    html += '<div class="pdm-section"><div class="pdm-section-title">Miejsce dostawy</div>';
    html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
    d.delivery_locations.forEach(loc => {
      html += '<span style="padding:5px 12px;background:#f1f5f9;border-radius:6px;font-size:12px;color:var(--txt)">&#128205; ' + loc + '</span>';
    });
    html += '</div></div>';
  }

  html += '<div class="pdm-section"><div class="pdm-section-title">Polityka zakupowa</div><div class="pdm-grid">';
  html += '<div class="pdm-field"><div class="pdm-field-label">Min. zamowienie</div><div class="pdm-field-value">' + (d.min_order_qty || 1) + ' ' + (item.unit || 'szt') + '</div></div>';
  html += '<div class="pdm-field"><div class="pdm-field-label">Kategoria budzetowa</div><div class="pdm-field-value">' + (d.budget_category || 'OPEX') + '</div></div>';
  html += '<div class="pdm-field"><div class="pdm-field-label">Akceptacja</div><div class="pdm-field-value">' + (d.approval_policy || 'Automatyczna') + '</div></div>';
  html += '<div class="pdm-field"><div class="pdm-field-label">Zrodlo</div><div class="pdm-field-value">' + source + (item.contract_no ? ' \u2014 umowa ramowa' : '') + '</div></div>';
  html += '</div></div>';

  if (d.bulk_discounts && d.bulk_discounts.length) {
    html += '<div class="pdm-section"><div class="pdm-section-title">Rabaty ilosciowe</div>';
    d.bulk_discounts.forEach(bd => {
      html += '<div class="pdm-discount" style="margin-bottom:4px">&#127873; ' + bd.label + ' (cena: ' + (item.price * (1 - bd.discount_pct / 100)).toFixed(2) + ' PLN)</div>';
    });
    html += '</div>';
  }

  if (d.variants && d.variants.length) {
    html += '<div class="pdm-section"><div class="pdm-section-title">Warianty</div>';
    d.variants.forEach(v => {
      html += '<div style="margin-bottom:8px"><div class="pdm-field-label" style="margin-bottom:4px">' + v.type + '</div><div class="pdm-variant">';
      v.options.forEach((opt, i) => {
        html += '<span class="pdm-variant-chip' + (i === 0 ? ' selected" style="border-color:var(--gold);background:var(--gold-bg)"' : '"') + '>' + opt + '</span>';
      });
      html += '</div></div>';
    });
    html += '</div>';
  }

  document.getElementById('pdmBody').innerHTML = html;
  document.getElementById('pdmOverlay').classList.add('open');
}

export function closePdm() {
  document.getElementById('pdmOverlay').classList.remove('open');
  state._pdmCurrentItem = null;
}

export function pdmChangeQty(delta) {
  const inp = document.getElementById('pdmQtyInput');
  const minQty = state._pdmCurrentItem?.details?.min_order_qty || 1;
  let v = parseInt(inp.value) + delta;
  if (v < minQty) v = minQty;
  inp.value = v;
}

export function pdmAddToCart() {
  if (!state._pdmCurrentItem) return;
  const qty = parseInt(document.getElementById('pdmQtyInput').value) || 1;
  const item = state._pdmCurrentItem;
  state._s1SelectedItems[item.id] = { ...item, qty: qty };
  if (state._mktAllegroData.length) renderMktAllegro(state._mktAllegroData);
  if (state._mktPunchoutData.length) renderMktPunchout(state._mktPunchoutData);
  updateS1Summary();
  updateGlobalCartBadge();
  closePdm();
}

// Close on Escape
document.addEventListener('keydown', e => { if (e.key === 'Escape' && document.getElementById('pdmOverlay').classList.contains('open')) closePdm(); });
