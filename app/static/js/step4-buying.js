/**
 * step4-buying.js — Order Browser, cart management, checkout, auctions
 */
import { $, pct } from './ui.js';
import { API, safeFetchJson } from './api.js';
import { state } from './state.js';
import { DOMAIN_CFG, switchDomain } from './step3-optimizer.js';
import { updateGlobalCartBadge } from './step1-demand.js';

function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

export function switchS4View(view) {
  state._s4CurrentView = view;
  document.getElementById('s4ViewReview').style.display = view === 'review' ? '' : 'none';
  document.getElementById('s4ViewOrders').style.display = view === 'orders' ? '' : 'none';
  document.getElementById('s4ViewCatalog').style.display = view === 'catalog' ? '' : 'none';
  document.getElementById('s4SubReview').classList.toggle('active', view === 'review');
  document.getElementById('s4SubOrders').classList.toggle('active', view === 'orders');
  document.getElementById('s4SubCatalog').classList.toggle('active', view === 'catalog');
  if (view === 'orders') { obShowOrders(); }
  if (view === 'catalog' && typeof obLoadCatalog === 'function') { obLoadCatalog(); }
  if (view === 'review') { renderS4CartReview(); }
}


export function renderS4CartReview() {
  const body = document.getElementById('s4CartReviewBody');
  const checkoutArea = document.getElementById('s4CheckoutArea');
  const badgeInline = document.getElementById('s4CartBadgeInline');
  if (!body) return;

  // Collect items from both Step 1 selection and buying cart
  const s1Items = Object.values(state._s1SelectedItems || {});
  const hasS1Items = s1Items.length > 0;
  const hasBuyingCart = state.obCart.length > 0;

  if (!hasS1Items && !hasBuyingCart) {
    badgeInline.textContent = '0 pozycji';
    checkoutArea.style.display = 'none';
    body.innerHTML = '<div class="s4-empty-state">'
      + '<div class="icon">🛒</div>'
      + '<h3>Koszyk jest pusty</h3>'
      + '<p>Nie masz jeszcze zadnych produktow w koszyku. Wróc do kroku 1 aby wybrac produkty z katalogu lub dodaj je recznie.</p>'
      + '<div style="display:flex;gap:10px;justify-content:center">'
      + '<button class="btn btn-gold" onclick="goStep(1)" style="padding:10px 24px">&#8592; Wroc do katalogu (Krok 1)</button>'
      + '<button class="btn" onclick="switchS4View(\'catalog\')" style="padding:10px 24px;background:#E3F2FD;color:#1565C0">Przegladaj katalog</button>'
      + '</div></div>';
    return;
  }

  let html = '';
  let totalValue = 0;
  let totalItems = 0;

  // Show Step 1 items
  if (hasS1Items) {
    // Group by source
    const sourceLabel = state.currentS1Path === 'marketplace' ? 'Marketplace (Allegro / PunchOut)' : 'Zapotrzebowanie (Krok 1)';
    html += '<div class="section-label" style="color:var(--gold);margin-bottom:8px">' + sourceLabel + '</div>';
    html += '<table class="s4-review-table"><thead><tr><th>Produkt</th><th>Dostawca</th><th style="text-align:right">Ilosc</th><th style="text-align:right">Cena jedn.</th><th style="text-align:right">Wartosc</th></tr></thead><tbody>';
    s1Items.forEach(item => {
      const qty = item.qty || 1;
      const price = item.price || 0;
      const lineTotal = qty * price;
      totalValue += lineTotal;
      totalItems += qty;
      // Extract supplier name from item
      const supplier = item.supplier_name
        || (item.suppliers && item.suppliers[0] ? item.suppliers[0].name : '')
        || '';
      const sourceBadge = item.source === 'punchout'
        ? '<span class="src-badge" style="background:#EDE9FE;color:#7C3AED;margin-left:4px">PunchOut</span>'
        : item.source === 'allegro_mock' || item.source === 'allegro'
        ? '<span class="src-badge" style="background:#DBEAFE;color:#1D4ED8;margin-left:4px">Allegro</span>'
        : '';
      html += '<tr>'
        + '<td><strong>' + (item.name || item.id) + '</strong>' + sourceBadge + '</td>'
        + '<td style="font-size:12px;color:var(--txt2)">' + (supplier || '<span style="color:var(--warn)">Do przypisania</span>') + '</td>'
        + '<td style="text-align:right">' + qty + '</td>'
        + '<td style="text-align:right">' + price.toLocaleString('pl') + ' PLN</td>'
        + '<td style="text-align:right;font-weight:700">' + lineTotal.toLocaleString('pl') + ' PLN</td>'
        + '</tr>';
    });
    html += '</tbody></table>';
  }

  // Show buying cart items (if different from S1)
  if (hasBuyingCart && state.obCartState && state.obCartState.items) {
    if (hasS1Items) {
      html += '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--navy);margin:16px 0 8px">Pozycje z koszyka zakupowego</div>';
    }
    html += '<table class="s4-review-table"><thead><tr><th>Produkt</th><th>Kategoria</th><th style="text-align:right">Ilosc</th><th style="text-align:right">Cena</th><th style="text-align:right">Wartosc</th></tr></thead><tbody>';
    state.obCartState.items.forEach(item => {
      totalValue += item.line_total || 0;
      totalItems += item.quantity || 0;
      html += '<tr>'
        + '<td><strong>' + item.name + '</strong>'
        + (item.is_forced_bundle ? ' <span class="ob-bundle-badge">Zestaw</span>' : '')
        + (item.requires_approval ? ' <span class="ob-approval-badge">Zatw.</span>' : '')
        + '</td>'
        + '<td><span style="font-size:10px;color:var(--txt2)">' + (CAT_LABELS[item.category] || item.category || '-') + '</span></td>'
        + '<td style="text-align:right">' + item.quantity + '</td>'
        + '<td style="text-align:right">' + item.price.toLocaleString('pl') + ' PLN</td>'
        + '<td style="text-align:right;font-weight:700">' + item.line_total.toLocaleString('pl') + ' PLN</td>'
        + '</tr>';
    });
    html += '</tbody></table>';
  }

  badgeInline.textContent = totalItems + ' pozycji';
  body.innerHTML = html;

  // Show checkout area
  checkoutArea.style.display = '';
  const sumEl = document.getElementById('s4CheckoutSummary');
  let sumHtml = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:12px">';
  sumHtml += '<div style="background:#F8FAFC;border-radius:8px;padding:12px;text-align:center"><div style="font-size:20px;font-weight:700;color:var(--navy)">' + totalItems + '</div><div style="font-size:11px;color:var(--txt2)">Pozycji</div></div>';
  sumHtml += '<div style="background:#F8FAFC;border-radius:8px;padding:12px;text-align:center"><div style="font-size:20px;font-weight:700;color:var(--navy)">' + totalValue.toLocaleString('pl') + ' PLN</div><div style="font-size:11px;color:var(--txt2)">Wartosc koszyka</div></div>';
  if (state._selectedUnspscCode) {
    sumHtml += '<div style="background:#F8FAFC;border-radius:8px;padding:12px;text-align:center"><div style="font-size:14px;font-weight:700;color:var(--gold)">' + state._selectedUnspscCode + '</div><div style="font-size:11px;color:var(--txt2)">Kategoria UNSPSC</div></div>';
  }
  // Show source context (marketplace vs catalog vs domain)
  const s1Sources = new Set(s1Items.map(i => i.source || 'catalog'));
  if (s1Sources.has('punchout') || s1Sources.has('allegro_mock') || s1Sources.has('allegro')) {
    const sourceLabels = [];
    if (s1Sources.has('punchout')) sourceLabels.push('PunchOut cXML');
    if (s1Sources.has('allegro_mock') || s1Sources.has('allegro')) sourceLabels.push('Allegro');
    if (s1Sources.has('catalog') || s1Sources.has(undefined)) sourceLabels.push('Katalog');
    sumHtml += '<div style="background:#EDE9FE;border-radius:8px;padding:12px;text-align:center"><div style="font-size:14px;font-weight:700;color:#7C3AED">' + sourceLabels.join(' + ') + '</div><div style="font-size:11px;color:var(--txt2)">Zrodlo</div></div>';
  } else {
    const domainCfg = DOMAIN_CFG[state.currentDomain] || {};
    if (domainCfg.label) {
      sumHtml += '<div style="background:#F8FAFC;border-radius:8px;padding:12px;text-align:center"><div style="font-size:14px;font-weight:700;color:var(--navy)">' + domainCfg.label + '</div><div style="font-size:11px;color:var(--txt2)">Domena</div></div>';
    }
  }
  // Show unique suppliers count
  const s4Suppliers = new Set();
  s1Items.forEach(i => {
    if (i.supplier_name) s4Suppliers.add(i.supplier_name);
    (i.suppliers || []).forEach(s => s4Suppliers.add(s.name));
  });
  if (s4Suppliers.size > 0) {
    sumHtml += '<div style="background:#ECFDF5;border-radius:8px;padding:12px;text-align:center"><div style="font-size:20px;font-weight:700;color:#059669">' + s4Suppliers.size + '</div><div style="font-size:11px;color:var(--txt2)">Dostawcow</div></div>';
  }
  sumHtml += '</div>';

  // Approval info
  if (state.obCartState && state.obCartState.approval) {
    const appr = state.obCartState.approval;
    if (appr.requires_approval) {
      sumHtml += '<div style="padding:8px 12px;background:#fef3c7;border-radius:6px;font-size:11px;color:#92400e;margin-bottom:8px">'
        + '<strong>Wymaga zatwierdzenia:</strong> ' + appr.approval_level_name
        + ' | Zatwierdzajacy: ' + (appr.approvers || []).join(', ') + '</div>';
    } else {
      sumHtml += '<div style="padding:8px 12px;background:#d1fae5;border-radius:6px;font-size:11px;color:#065f46;font-weight:600;margin-bottom:8px">Automatyczne zatwierdzenie — zamowienie ponizej progu</div>';
    }
  }
  sumEl.innerHTML = sumHtml;
}

/* ═══ Step 5 — Data Source Selector ═══ */
let _monSource = 'demo';
let _monSuppliers = [];


const CAT_ICONS = {
  parts: '🔧', oe_components: '⚙️', oils: '🛢️', batteries: '🔋',
  tires: '🚗', bodywork: '💡', it_services: '💻', logistics: '📦',
  mro: '🛠️', packaging: '📋'
};
const CAT_LABELS = {
  parts:'Części zamienne', oe_components:'Komponenty OE', oils:'Oleje i płyny',
  batteries:'Akumulatory', tires:'Opony', bodywork:'Nadwozia',
  it_services:'IT / Licencje', logistics:'Logistyka', mro:'MRO / Narzędzia',
  packaging:'Opakowania'
};

export async function obLoadCatalog() {
  try {
    const data = await safeFetchJson(API + '/buying/catalog');
    state.obCatalog = data.products || [];
    state.obCategories = data.categories || [];
    obRenderSidebar();
    obRenderGrid();
  } catch(e) {
    $('obCatalogGrid').innerHTML = '<div style="color:var(--err)">Blad ladowania katalogu: '+e.message+'</div>';
  }
}

export function obRenderSidebar() {
  const list = $('obCatList');
  let html = '';
  let lastGroup = '';
  state.obCategories.forEach(c => {
    if (c.group !== lastGroup) {
      lastGroup = c.group;
      html += '<div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--txt2);padding:12px 16px 4px;font-weight:600">'
        + (c.group === 'direct' ? 'Bezpośrednie' : 'Pośrednie') + '</div>';
    }
    html += '<button class="cat-btn" data-cat="'+c.id+'" onclick="obFilterCat(\''+c.id+'\',this)">'
      + '<span class="cat-icon">'+c.icon+'</span> '+c.label+'</button>';
  });
  list.innerHTML = html;
}

export function obFilterCat(cat, btn) {
  state.obActiveCategory = cat;
  document.querySelectorAll('.ob-sidebar .cat-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  obRenderGrid();
}

export function obRenderGrid() {
  const items = state.obActiveCategory === 'all'
    ? state.obCatalog
    : state.obCatalog.filter(p => p.category === state.obActiveCategory);

  if (items.length === 0) {
    $('obCatalogGrid').innerHTML = '<div style="color:var(--txt2);font-size:13px;grid-column:1/-1">Brak produktow w tej kategorii.</div>';
    return;
  }

  let html = '';
  items.forEach((p, idx) => {
    const icon = CAT_ICONS[p.category] || '📦';
    const catLabel = CAT_LABELS[p.category] || p.category;
    const inCart = state.obCart.find(c => c.id === p.id);
    html += '<div class="ob-card" style="animation:fadeIn .3s ease '+(idx*0.04)+'s both">'
      + '<div class="ob-card-img">' + icon
      + (p.requires_approval ? '<span class="ob-card-badge">Zatwierdzenie</span>' : '')
      + '</div>'
      + '<div class="ob-card-body">'
      + '<div class="ob-card-cat">'+catLabel+'</div>'
      + '<div class="ob-card-name">'+p.name+'</div>'
      + '<div class="ob-card-desc">'+p.description+'</div>'
      + '<div class="ob-card-foot">'
      + '<div><span class="ob-card-price">'+p.price.toLocaleString('pl')+' PLN</span><span class="ob-card-unit"> / '+p.unit+'</span></div>'
      + (inCart
        ? '<button class="ob-add-btn" style="background:var(--ok)" onclick="obAddToCart(\''+p.id+'\')">W koszyku ('+inCart.quantity+')</button>'
        : '<button class="ob-add-btn" onclick="obAddToCart(\''+p.id+'\')">+ Dodaj</button>')
      + '</div>'
      + '</div></div>';
  });
  $('obCatalogGrid').innerHTML = html;
}

export function obAddToCart(id) {
  const existing = state.obCart.find(c => c.id === id);
  if (existing) {
    existing.quantity += 1;
  } else {
    state.obCart.push({ id, quantity: 1 });
  }
  obRecalculate();
}

export function obRemoveFromCart(id) {
  state.obCart = state.obCart.filter(c => c.id !== id);
  obRecalculate();
}

export function obUpdateQty(id, delta) {
  const item = state.obCart.find(c => c.id === id);
  if (!item) return;
  item.quantity = Math.max(1, item.quantity + delta);
  obRecalculate();
}

export async function obRecalculate() {
  obRenderGrid(); // update "in cart" badges
  if (state.obCart.length === 0) {
    state.obCartState = null;
    obRenderCart();
    updateGlobalCartBadge();
    return;
  }
  try {
    const data = await safeFetchJson(API + '/buying/calculate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ items: state.obCart })
    });
    state.obCartState = data;
    // Sync forced bundles back to local cart
    if (data.items) {
      const serverIds = new Set(data.items.map(i => i.id));
      // Add forced bundles not in local cart
      data.items.forEach(si => {
        if (si.is_forced_bundle && !state.obCart.find(c => c.id === si.id)) {
          state.obCart.push({ id: si.id, quantity: si.quantity });
        }
      });
      // Remove bundles from local cart if server removed them
      state.obCart = state.obCart.filter(c => serverIds.has(c.id));
    }
    obRenderCart();
    updateGlobalCartBadge();
  } catch(e) {
    console.error('Cart calc error:', e);
  }
}

export function obRenderCart() {
  const badge = $('obCartBadge');
  const totalItems = state.obCart.reduce((s, c) => s + c.quantity, 0);
  if (totalItems > 0) {
    badge.textContent = totalItems;
    badge.style.display = 'flex';
  } else {
    badge.style.display = 'none';
  }

  // If buying cart is empty but Step 1 has items, show those
  const s1CartItems = Object.values(state._s1SelectedItems || {});
  if ((!state.obCartState || !state.obCartState.items || state.obCartState.items.length === 0) && s1CartItems.length === 0) {
    $('obCartItems').innerHTML = '<div style="color:var(--txt2);font-size:13px;text-align:center;padding:40px 0">Koszyk jest pusty</div>';
    $('obCartMessages').innerHTML = '';
    $('obCartSummary').style.display = 'none';
    return;
  }
  // Show Step 1 items in sidebar if buying cart is empty
  if ((!state.obCartState || !state.obCartState.items || state.obCartState.items.length === 0) && s1CartItems.length > 0) {
    let s1Html = '';
    let s1Total = 0;
    s1CartItems.forEach(item => {
      const qty = item.qty || 1;
      const price = item.price || 0;
      const lineTotal = qty * price;
      s1Total += lineTotal;
      const supplier = item.supplier_name || (item.suppliers && item.suppliers[0] ? item.suppliers[0].name : '');
      s1Html += '<div class="ob-cart-item">'
        + '<div class="ob-cart-item-info">'
        + '<div class="ob-cart-item-name">' + (item.name || item.id) + '</div>'
        + '<div class="ob-cart-item-price">' + price.toLocaleString('pl') + ' PLN / ' + (item.unit || 'szt')
        + (supplier ? ' <span style="color:var(--ok);font-size:10px">&#9654; ' + supplier + '</span>' : '')
        + '</div></div>'
        + '<div class="ob-cart-item-qty"><span>' + qty + '</span></div>'
        + '<div class="ob-cart-item-total">' + lineTotal.toLocaleString('pl') + ' PLN</div>'
        + '</div>';
    });
    $('obCartItems').innerHTML = s1Html;
    $('obCartMessages').innerHTML = '';
    $('obCartSummary').style.display = 'block';
    $('obCartSummary').innerHTML = '<div class="ob-summary-row total"><span>Razem</span><span>' + s1Total.toLocaleString('pl') + ' PLN</span></div>';
    return;
  }

  let html = '';
  state.obCartState.items.forEach(item => {
    html += '<div class="ob-cart-item">'
      + '<div class="ob-cart-item-info">'
      + '<div class="ob-cart-item-name">'+item.name
      + (item.is_forced_bundle ? ' <span class="ob-bundle-badge">Zestaw</span>' : '')
      + (item.requires_approval ? ' <span class="ob-approval-badge">Zatw.</span>' : '')
      + '</div>'
      + '<div class="ob-cart-item-price">'+item.price.toLocaleString('pl')+' PLN / '+item.unit+'</div>'
      + '</div>';

    if (item.is_forced_bundle) {
      html += '<div style="font-size:10px;color:var(--gold);font-weight:600">auto</div>';
    } else {
      html += '<div class="ob-cart-item-qty">'
        + '<button onclick="obUpdateQty(\''+item.id+'\',-1)">-</button>'
        + '<span>'+item.quantity+'</span>'
        + '<button onclick="obUpdateQty(\''+item.id+'\',1)">+</button>'
        + '</div>';
    }

    html += '<div class="ob-cart-item-total">'+item.line_total.toLocaleString('pl')+' PLN</div>';

    if (!item.is_forced_bundle) {
      html += '<button class="ob-cart-remove" onclick="obRemoveFromCart(\''+item.id+'\')">&times;</button>';
    }
    html += '</div>';
  });
  $('obCartItems').innerHTML = html;

  // Messages
  let msgs = '';
  if (state.obCartState.errors && state.obCartState.errors.length > 0) {
    msgs += '<div class="ob-msg-panel ob-msg-error" style="margin:0 20px"><strong>Blokada zamowienia:</strong><ul style="margin:4px 0 0;padding-left:16px">';
    state.obCartState.errors.forEach(e => { msgs += '<li>'+e+'</li>'; });
    msgs += '</ul></div>';
  }
  if (state.obCartState.warnings && state.obCartState.warnings.length > 0) {
    msgs += '<div class="ob-msg-panel ob-msg-warn" style="margin:0 20px;margin-top:6px"><strong>Informacje:</strong><ul style="margin:4px 0 0;padding-left:16px">';
    state.obCartState.warnings.forEach(w => { msgs += '<li>'+w+'</li>'; });
    msgs += '</ul></div>';
  }
  $('obCartMessages').innerHTML = msgs;

  // Summary
  $('obCartSummary').style.display = 'block';
  let sumHtml = '<div class="ob-summary-row"><span>Wartosc produktow</span><span>'+state.obCartState.subtotal.toLocaleString('pl')+' PLN</span></div>';
  if (state.obCartState.discount > 0) {
    sumHtml += '<div class="ob-summary-row"><span>Rabaty</span><span class="discount">-'+state.obCartState.discount.toLocaleString('pl')+' PLN</span></div>';
  }
  sumHtml += '<div class="ob-summary-row"><span>Dostawa ('+state.obCartState.total_weight_kg+' kg)</span><span>'+state.obCartState.shipping_fee.toLocaleString('pl')+' PLN</span></div>';
  sumHtml += '<div class="ob-summary-row"><span>Czas dostawy</span><span>'+state.obCartState.delivery_days+' dni roboczych</span></div>';
  sumHtml += '<div class="ob-summary-row total"><span>Razem</span><span>'+state.obCartState.total.toLocaleString('pl')+' PLN</span></div>';

  // Approval chain info
  const appr = state.obCartState.approval;
  if (appr) {
    if (appr.requires_approval) {
      sumHtml += '<div style="margin-top:10px;padding:8px 12px;background:#fef3c7;border-radius:6px;font-size:11px;color:#92400e">'
        + '<div style="font-weight:700;margin-bottom:4px">⚠️ ' + appr.approval_level_name + '</div>'
        + '<div>Tryb: <b>' + (appr.workflow_mode === 'parallel' ? 'Równoległy' : 'Sekwencyjny') + '</b></div>'
        + '<div style="margin-top:3px">Zatwierdzający:</div>'
        + '<div>' + (appr.approvers||[]).map(function(a) { return '<span style="display:inline-block;background:#fff;padding:1px 6px;border-radius:3px;margin:2px 2px 0 0;font-size:10px;border:1px solid #d97706">' + a + '</span>'; }).join('') + '</div>'
        + '</div>';
    } else {
      sumHtml += '<div style="margin-top:10px;padding:8px 12px;background:#d1fae5;border-radius:6px;font-size:11px;color:#065f46;font-weight:600">'
        + '✅ Auto-zatwierdzenie — zamówienie poniżej progu</div>';
    }
  }

  $('obSummaryRows').innerHTML = sumHtml;

  const btn = $('obCheckoutBtn');
  if (state.obCartState.can_checkout) {
    btn.className = 'ob-checkout-btn ok';
    btn.textContent = 'Optymalizuj i zamow';
    btn.onclick = obShowCheckoutModal;
  } else {
    btn.className = 'ob-checkout-btn blocked';
    btn.textContent = 'Popraw bledy aby kontynuowac';
    btn.onclick = null;
  }
  updateGlobalCartBadge();
}

export function obToggleCart() {
  const drawer = $('obCartDrawer');
  const backdrop = $('obCartBackdrop');
  const isOpen = drawer.classList.contains('open');
  drawer.classList.toggle('open', !isOpen);
  backdrop.classList.toggle('open', !isOpen);
}

export function obShowCheckoutModal() {
  obToggleCart(); // close drawer
  const cats = [...new Set((state.obCartState?.items || []).map(i => i.category))];
  const glSuggestion = cats.includes('it_services') ? '420-IT-Services'
    : cats.includes('parts') || cats.includes('oe_components') ? '400-Auto-Parts'
    : cats.includes('oils') ? '410-Oils-Chemicals'
    : '400-General-Procurement';

  $('obCheckoutModal').style.display = 'block';
  $('obCheckoutModal').innerHTML = '<div class="ob-modal-backdrop" onclick="obCloseCheckout()">'
    + '<div class="ob-modal" onclick="event.stopPropagation()">'
    + '<div class="ob-modal-header"><h2>Potwierdzenie zamowienia</h2></div>'
    + '<div class="ob-modal-body">'
    + '<div class="ob-modal-field"><label>MPK (Centrum kosztow)</label><input id="obMpk" value="FLOW-ZAKUPY-01"></div>'
    + '<div class="ob-modal-field"><label>Konto GL</label><input id="obGl" value="'+glSuggestion+'"></div>'
    + '<div class="ob-modal-field"><label>Region docelowy</label><select id="obRegion">'
    + '<option value="PL-MA">Malopolska (Krakow)</option>'
    + '<option value="PL-SL">Slask (Katowice)</option>'
    + '<option value="PL-MZ">Mazowsze (Warszawa)</option>'
    + '<option value="PL-WP">Wielkopolska (Poznan)</option>'
    + '<option value="PL-PM">Pomorze (Gdansk)</option>'
    + '</select></div>'
    + '<div style="background:#F8FAFC;border-radius:8px;padding:12px;margin-top:8px">'
    + '<div style="font-size:12px;color:var(--txt2);margin-bottom:6px"><strong>Podsumowanie</strong></div>'
    + '<div style="font-size:12px;display:flex;justify-content:space-between"><span>Pozycje:</span><span>'+state.obCartState.total_items+'</span></div>'
    + '<div style="font-size:12px;display:flex;justify-content:space-between"><span>Wartosc koszyka:</span><span style="font-weight:700">'+state.obCartState.total.toLocaleString('pl')+' PLN</span></div>'
    + '<div style="font-size:12px;display:flex;justify-content:space-between"><span>Czas dostawy:</span><span>do '+state.obCartState.delivery_days+' dni</span></div>'
    + (state.obCartState.requires_manager_approval
      ? '<div style="font-size:11px;color:var(--warn);margin-top:6px;font-weight:600">Wymagane zatwierdzenie kierownika</div>'
      : '<div style="font-size:11px;color:var(--ok);margin-top:6px">Automatyczne zatwierdzenie</div>')
    + '</div>'
    + '</div>'
    + '<div class="ob-modal-footer">'
    + '<button onclick="obCloseCheckout()" style="background:#F1F5F9;color:var(--txt)">Anuluj</button>'
    + '<button onclick="obSubmitCheckout()" style="background:var(--gold);color:#fff">Optymalizuj dostawcow</button>'
    + '</div>'
    + '</div></div>';
}

export function obCloseCheckout() {
  $('obCheckoutModal').style.display = 'none';
  $('obCheckoutModal').innerHTML = '';
}

export async function obSubmitCheckout() {
  const mpk = $('obMpk').value;
  const gl = $('obGl').value;
  const region = $('obRegion').value;

  // Show loading in modal
  const footer = $('obCheckoutModal').querySelector('.ob-modal-footer');
  footer.innerHTML = '<div style="color:var(--gold);font-size:13px">Uruchamianie optymalizatora dostawcow...</div>';

  try {
    const result = await safeFetchJson(API + '/buying/optimize', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        items: state.obCart,
        mpk: mpk,
        gl_account: gl,
        destination_region: region,
      })
    });

    obCloseCheckout();
    obRenderOptimizationResults(result);
  } catch(e) {
    footer.innerHTML = '<div style="color:var(--err);font-size:13px">Blad: '+e.message+'</div>'
      + '<button onclick="obCloseCheckout()" style="background:#F1F5F9;color:var(--txt);padding:8px 16px;border:none;border-radius:6px;cursor:pointer;margin-top:8px">Zamknij</button>';
  }
}

export function obRenderOptimizationResults(result) {
  const el = $('obCheckoutResults');
  el.style.display = 'block';

  if (!result.success) {
    el.innerHTML = '<div class="card" style="border-left:4px solid var(--err)"><div class="card-title">Blad optymalizacji</div>'
      + '<div style="color:var(--err);font-size:13px">'+result.message+'</div></div>';
    return;
  }

  state._pendingOptimizationId = result.optimization_id;
  const cs = result.cart_summary;
  const approvalInfo = cs.requires_manager_approval
    ? '<span style="color:var(--warn);font-weight:700">Po zlozeniu zamowienia: oczekuje na zatwierdzenie kierownika</span>'
    : '<span style="color:var(--ok);font-weight:600">Po zlozeniu zamowienia: automatyczne zatwierdzenie</span>';

  let html = '<div class="card mb-24" style="border-left:4px solid var(--gold)">'
    + '<div class="card-title" style="color:var(--navy);display:flex;justify-content:space-between;align-items:center">'
    + '<span>Wyniki optymalizacji dostawcow</span>'
    + '<span class="ob-status-badge" style="background:var(--gold);color:#fff">Gotowe do zamowienia</span>'
    + '</div>'
    + '<div class="grid-4 mb-16">'
    + '<div class="card kpi"><div class="kpi-value gold">'+cs.total_items+'</div><div class="kpi-label">Pozycji</div></div>'
    + '<div class="card kpi"><div class="kpi-value">'+cs.cart_total.toLocaleString('pl')+'</div><div class="kpi-label">Wartosc koszyka PLN</div></div>'
    + '<div class="card kpi"><div class="kpi-value" style="color:var(--ok)">'+result.optimized_cost.toLocaleString('pl')+'</div><div class="kpi-label">Koszt zoptymalizowany PLN</div></div>'
    + '<div class="card kpi"><div class="kpi-value gold">'+(result.savings_pln > 0 ? '-'+result.savings_pln.toLocaleString('pl') : '0')+'</div><div class="kpi-label">Oszczednosci PLN</div></div>'
    + '</div>'
    + '<div style="font-size:11px;color:var(--txt2);margin-bottom:12px">MPK: <strong>'+result.mpk+'</strong> | GL: <strong>'+result.gl_account+'</strong> | '+approvalInfo+'</div>'
    + '<div style="display:flex;gap:10px;align-items:center;padding:12px;background:#F0FDF4;border-radius:8px;border:1px solid #BBF7D0">'
    + '<button onclick="obPlaceOrder()" style="background:var(--ok);color:#fff;border:none;border-radius:8px;padding:12px 28px;font-size:15px;font-weight:700;cursor:pointer;letter-spacing:0.3px">Zloz zamowienie</button>'
    + '<span style="font-size:12px;color:var(--txt2)">Kliknij aby potwierdzic i zlozyc zamowienie u dostawcow</span>'
    + '</div>'
    + '</div>';

  // Domain results
  (result.domain_results || []).forEach(dr => {
    const catLabel = CAT_LABELS[dr.domain] || dr.domain;
    const catIcon = CAT_ICONS[dr.domain] || '📦';
    html += '<div class="ob-result-domain">';
    html += '<h4>'+catIcon+' '+catLabel + (dr.success ? '' : ' <span style="color:var(--err)">(blad)</span>') + '</h4>';

    if (dr.success && dr.allocations && dr.allocations.length > 0) {
      html += '<table><thead><tr><th>Dostawca</th><th>Produkt</th><th style="text-align:right">Qty</th><th style="text-align:right">Udzial</th><th style="text-align:right">Koszt PLN</th></tr></thead><tbody>';
      dr.allocations.forEach(a => {
        const share = (a.share || a.allocated_share || 0);
        const sharePct = (share * 100).toFixed(1);
        html += '<tr>'
          + '<td><a href="#" onclick="event.preventDefault();switchTab(\'suppliers\');setTimeout(()=>suppShowDetail(\''+(a.supplier_id||'')+'\'),200)" style="color:#1565c0;cursor:pointer">'+(a.supplier_name || a.supplier_id)+'</a></td>'
          + '<td>'+(a.product_id || '-')+'</td>'
          + '<td style="text-align:right">'+(a.allocated_qty || 0).toFixed(0)+'</td>'
          + '<td style="text-align:right"><span class="tag tag-green">'+sharePct+'%</span></td>'
          + '<td style="text-align:right;font-weight:700">'+(a.allocated_cost_pln || 0).toLocaleString('pl')+' PLN</td>'
          + '</tr>';
      });
      html += '</tbody></table>';
      html += '<div style="text-align:right;font-size:12px;margin-top:6px;font-weight:700;color:var(--navy)">Koszt domeny: '+(dr.domain_cost||0).toLocaleString('pl')+' PLN</div>';
    } else if (dr.message) {
      html += '<div style="color:var(--txt2);font-size:12px">'+dr.message+'</div>';
    }
    html += '</div>';
  });

  el.innerHTML = html;
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export async function obPlaceOrder() {
  if (!state._pendingOptimizationId) return;
  const el = $('obCheckoutResults');
  // Disable button, show loading
  const btn = el.querySelector('button[onclick="obPlaceOrder()"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Skladanie zamowienia...'; btn.style.opacity = '0.6'; }

  try {
    const result = await safeFetchJson(API + '/buying/checkout', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ optimization_id: state._pendingOptimizationId })
    });

    state._pendingOptimizationId = null;

    if (!result.success) {
      el.innerHTML = '<div class="card" style="border-left:4px solid var(--err)"><div class="card-title">Blad zamowienia</div>'
        + '<div style="color:var(--err);font-size:13px">'+result.message+'</div></div>';
      return;
    }

    // Clear cart
    state.obCart = [];
    state.obCartState = null;
    obRenderCart();

    // Show order confirmation
    const oid = result.order_id;
    const ost = result.order_status_label || result.order_status || '';
    const isApproval = result.requires_manager_approval;
    const cs = result.cart_summary;

    let html = '<div class="card mb-24" style="border-left:4px solid var(--ok)">'
      + '<div class="card-title" style="color:var(--ok);display:flex;justify-content:space-between;align-items:center">'
      + '<span>Zamowienie zlozone!</span>'
      + '<span class="ob-status-badge '+(result.order_status||'')+'">'+ost+'</span>'
      + '</div>'
      + '<div style="font-size:13px;margin-bottom:12px">Nr zamowienia: <strong style="color:var(--navy);font-size:16px">'+oid+'</strong></div>';

    if (isApproval) {
      html += '<div style="background:#FFFBEB;border:1px solid #FDE68A;border-radius:8px;padding:12px;margin-bottom:12px;font-size:13px">'
        + '<strong style="color:var(--warn)">Wymagane zatwierdzenie kierownika</strong><br>'
        + '<span style="color:var(--txt2)">Zamowienie zostalo wyslane do zatwierdzenia. Po akceptacji zostaną wygenerowane zamowienia zakupu (PO).</span></div>';
    } else {
      html += '<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:12px;margin-bottom:12px;font-size:13px">'
        + '<strong style="color:var(--ok)">Automatycznie zatwierdzone</strong><br>'
        + '<span style="color:var(--txt2)">Zamowienie zostalo automatycznie zatwierdzone i jest gotowe do generowania PO.</span></div>';
    }

    html += '<div class="grid-4 mb-16">'
      + '<div class="card kpi"><div class="kpi-value gold">'+cs.total_items+'</div><div class="kpi-label">Pozycji</div></div>'
      + '<div class="card kpi"><div class="kpi-value">'+cs.cart_total.toLocaleString('pl')+'</div><div class="kpi-label">Wartosc koszyka PLN</div></div>'
      + '<div class="card kpi"><div class="kpi-value" style="color:var(--ok)">'+result.optimized_cost.toLocaleString('pl')+'</div><div class="kpi-label">Koszt zoptymalizowany PLN</div></div>'
      + '<div class="card kpi"><div class="kpi-value gold">'+(result.savings_pln > 0 ? '-'+result.savings_pln.toLocaleString('pl') : '0')+'</div><div class="kpi-label">Oszczednosci PLN</div></div>'
      + '</div>'
      + '<div style="display:flex;gap:10px;margin-top:8px">'
      + '<button class="ob-action-btn primary" onclick="obShowOrderDetail(&quot;'+oid+'&quot;)">Sledz zamowienie</button>'
      + '<button class="ob-action-btn" onclick="obShowOrders()">Wszystkie zamowienia</button>'
      + '</div></div>';

    el.innerHTML = html;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch(e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Zloz zamowienie'; btn.style.opacity = '1'; }
    el.insertAdjacentHTML('afterbegin', '<div class="card" style="border-left:4px solid var(--err);margin-bottom:12px"><div style="color:var(--err);font-size:13px">Blad: '+e.message+'</div></div>');
  }
}

/* ═══ Order Lifecycle ═══ */

const STATUS_LABELS = {
  draft:'Szkic', pending_approval:'Oczekuje na zatwierdzenie', approved:'Zatwierdzone',
  po_generated:'PO wygenerowane', confirmed:'Potwierdzone', in_delivery:'W dostawie',
  delivered:'Dostarczone', cancelled:'Anulowane'
};

const STATUS_STEPS = ['pending_approval','approved','po_generated','confirmed','in_delivery','delivered'];

export async function obShowOrders() {
  // Switch to orders sub-view if on step 4
  if (state.currentStep === 4) switchS4View('orders');
  obLoadKpi();
  const panel = $('obOrderPanel');
  panel.style.display = 'block';
  panel.innerHTML = '<div style="color:var(--txt2);font-size:13px">Ladowanie zamowien...</div>';
  try {
    const r = await fetch(API+'/buying/orders');
    const data = await r.json();
    obRenderOrdersList(data.orders || []);
  } catch(e) {
    panel.innerHTML = '<div class="card" style="color:var(--err)">Blad: '+e.message+'</div>';
  }
  panel.scrollIntoView({ behavior:'smooth', block:'start' });
}

export function obRenderOrdersList(orders) {
  const panel = $('obOrderPanel');
  if (orders.length === 0) {
    panel.innerHTML = '<div class="card"><div class="card-title">Zamowienia</div>'
      + '<div style="color:var(--txt2);font-size:13px;text-align:center;padding:24px 0">Brak zamowien. Zloż pierwsze zamowienie przez koszyk.</div></div>';
    return;
  }
  let html = '<div class="card"><div class="card-title" style="display:flex;justify-content:space-between;align-items:center">'
    + '<span>Zamowienia ('+orders.length+')</span>'
    + '<button class="ob-action-btn secondary" onclick="$(&quot;obOrderPanel&quot;).style.display=&quot;none&quot;">Zamknij</button></div>'
    + '<div class="ob-orders-list">';
  orders.forEach(o => {
    html += '<div class="ob-order-row" onclick="obShowOrderDetail(&quot;'+o.order_id+'&quot;)">'
      + '<div><strong style="font-size:13px;color:var(--navy)">'+o.order_id+'</strong>'
      + '<div style="font-size:11px;color:var(--txt2)">'+new Date(o.created_at).toLocaleString('pl')
      + ' | '+o.total_items+' poz. | '+o.total.toLocaleString('pl')+' PLN</div></div>'
      + '<span class="ob-status-badge '+o.status+'">'+STATUS_LABELS[o.status]+'</span></div>';
  });
  html += '</div></div>';
  panel.innerHTML = html;
}

export async function obShowOrderDetail(orderId) {
  const panel = $('obOrderPanel');
  panel.innerHTML = '<div style="color:var(--txt2);font-size:13px">Ladowanie...</div>';
  try {
    const r = await fetch(API+'/buying/orders/'+orderId);
    const data = await r.json();
    if (!data.success) { panel.innerHTML = '<div class="card" style="color:var(--err)">'+data.message+'</div>'; return; }
    obRenderOrderDetail(data.order);
  } catch(e) {
    panel.innerHTML = '<div class="card" style="color:var(--err)">Blad: '+e.message+'</div>';
  }
}

export function obRenderOrderDetail(order) {
  const panel = $('obOrderPanel');
  const o = order;

  // Progress bar
  let progressHtml = '<div style="display:flex;gap:4px;margin:16px 0">';
  STATUS_STEPS.forEach((s,i) => {
    const idx = STATUS_STEPS.indexOf(o.status);
    const isCancelled = o.status === 'cancelled';
    let cls = 'background:#E2E8F0;color:var(--txt2)';
    if (isCancelled) cls = 'background:#F3F4F6;color:#9CA3AF';
    else if (i < idx) cls = 'background:var(--ok);color:#fff';
    else if (i === idx) cls = 'background:var(--gold);color:#fff';
    progressHtml += '<div style="flex:1;text-align:center;padding:6px 4px;border-radius:4px;font-size:10px;font-weight:700;'+cls+'">'
      + STATUS_LABELS[s] + '</div>';
  });
  progressHtml += '</div>';

  // Action buttons
  let actionsHtml = '<div style="margin-top:12px">';
  if (o.status === 'pending_approval')
    actionsHtml += '<button class="ob-action-btn primary" onclick="obOrderAction(&quot;'+o.order_id+'&quot;,&quot;approve&quot;)">Zatwierdz</button>';
  if (o.status === 'approved')
    actionsHtml += '<button class="ob-action-btn primary" onclick="obOrderAction(&quot;'+o.order_id+'&quot;,&quot;generate-po&quot;)">Generuj PO</button>';
  if (o.status === 'po_generated')
    actionsHtml += '<button class="ob-action-btn primary" onclick="obOrderAction(&quot;'+o.order_id+'&quot;,&quot;confirm&quot;)">Potwierdz (dostawca)</button>';
  if (o.status === 'confirmed')
    actionsHtml += '<button class="ob-action-btn primary" onclick="obOrderAction(&quot;'+o.order_id+'&quot;,&quot;ship&quot;)">Wyslij</button>';
  if (o.status === 'in_delivery')
    actionsHtml += '<button class="ob-action-btn primary" onclick="obOrderAction(&quot;'+o.order_id+'&quot;,&quot;deliver&quot;)">Potwierdz odbiór (GR)</button>';
  if (['pending_approval','approved','po_generated'].includes(o.status))
    actionsHtml += '<button class="ob-action-btn danger" onclick="obOrderAction(&quot;'+o.order_id+'&quot;,&quot;cancel&quot;)">Anuluj</button>';
  // Show in optimizer button — use first domain from domain_results
  const orderDomains = (o.domain_results || []).filter(d => d.success).map(d => d.domain);
  if (orderDomains.length > 0) {
    actionsHtml += '<button class="ob-action-btn" style="background:#EEF2FF;color:#4F46E5" onclick="obOpenInOptimizer(\'' + orderDomains[0] + '\')">Pokaz w optymalizatorze</button>';
  }
  actionsHtml += '<button class="ob-action-btn secondary" onclick="obShowOrders()">Wróc do listy</button></div>';

  // KPIs
  let html = '<div class="card mb-24">'
    + '<div class="card-title" style="display:flex;justify-content:space-between;align-items:center">'
    + '<span>'+o.order_id+'</span>'
    + '<span class="ob-status-badge '+o.status+'">'+STATUS_LABELS[o.status]+'</span></div>'
    + progressHtml
    + '<div class="grid-4 mb-16">'
    + '<div class="card kpi"><div class="kpi-value">'+o.total.toLocaleString('pl')+'</div><div class="kpi-label">Wartosc PLN</div></div>'
    + '<div class="card kpi"><div class="kpi-value" style="color:var(--ok)">'+o.optimized_cost.toLocaleString('pl')+'</div><div class="kpi-label">Koszt zoptymalizowany</div></div>'
    + '<div class="card kpi"><div class="kpi-value gold">-'+o.savings_pln.toLocaleString('pl')+'</div><div class="kpi-label">Oszczednosci PLN</div></div>'
    + '<div class="card kpi"><div class="kpi-value">'+o.total_items+'</div><div class="kpi-label">Pozycji</div></div>'
    + '</div>'
    + '<div style="font-size:11px;color:var(--txt2)">MPK: <strong>'+o.mpk+'</strong> | GL: <strong>'+o.gl_account+'</strong> | Utworzone: '+new Date(o.created_at).toLocaleString('pl')+'</div>'
    + actionsHtml + '</div>';

  // Purchase Orders
  if (o.purchase_orders && o.purchase_orders.length > 0) {
    html += '<div class="card mb-24"><div class="card-title">Zamowienia zakupu (PO)</div>';
    o.purchase_orders.forEach(po => {
      html += '<div class="ob-po-card">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
        + '<strong style="font-size:13px;color:var(--navy)">'+po.po_id+'</strong>'
        + '<span class="ob-status-badge '+(po.status==='confirmed'?'confirmed':'po_generated')+'">'+po.status+'</span></div>'
        + '<div style="font-size:12px;color:var(--txt2)">'+po.supplier_name+' | '+po.domain+' | '+po.po_total_pln.toLocaleString('pl')+' PLN'
        + ' | ETA: '+po.expected_delivery+'</div>';
      if (po.lines && po.lines.length > 0) {
        html += '<table style="margin-top:6px;font-size:11px"><thead><tr><th>Produkt</th><th style="text-align:right">Ilosc</th><th style="text-align:right">Koszt PLN</th></tr></thead><tbody>';
        po.lines.forEach(l => {
          html += '<tr><td>'+l.product_id+'</td><td style="text-align:right">'+l.quantity+'</td><td style="text-align:right">'+l.line_total.toLocaleString('pl')+'</td></tr>';
        });
        html += '</tbody></table>';
      }
      html += '</div>';
    });
    html += '</div>';
  }

  // Timeline
  html += '<div class="card"><div class="card-title">Historia zamowienia</div><div class="ob-timeline">';
  o.history.forEach((h, i) => {
    const isLast = i === o.history.length - 1;
    html += '<div class="ob-tl-item">'
      + '<div class="ob-tl-dot '+(isLast ? 'active' : 'done')+'"></div>'
      + '<div class="ob-tl-content">'
      + '<strong>'+STATUS_LABELS[h.status]+'</strong><span class="ts">'+new Date(h.timestamp).toLocaleString('pl')+'</span>'
      + '<div class="note">'+h.note+' <span style="color:var(--txt2)">('+(h.actor||'system')+')</span></div>'
      + '</div></div>';
  });
  html += '</div></div>';

  panel.innerHTML = html;
  panel.scrollIntoView({ behavior:'smooth', block:'start' });
}

export async function obOrderAction(orderId, action) {
  try {
    const r = await fetch(API+'/buying/orders/'+orderId+'/'+action, { method:'POST' });
    const data = await r.json();
    if (data.success) {
      obShowOrderDetail(orderId);
    } else {
      alert(data.message || 'Blad akcji');
    }
  } catch(e) { alert('Blad: '+e.message); }
}

/* ═══ Cross-module: Buying → Optimizer ═══ */
export function obOpenInOptimizer(domain) {
  // Switch to Optimization tab and select the domain. switchTab lives on
  // window — defined in the index.html bootstrap — so we use it via the
  // global to avoid a circular import with the inline script.
  if (typeof window.switchTab === 'function') window.switchTab('optimization');
  if (DOMAIN_CFG[domain]) switchDomain(domain);
}

/* ═══════════════════════════════════════════════════════════════
   TAB 6 — DOSTAWCY (Supplier Management)
   ═══════════════════════════════════════════════════════════════ */

let _suppCurrentId = null;


export async function obLoadKpi() {
  const panel = $('obKpiPanel');
  panel.style.display = 'block';
  try {
    const r = await fetch(API+'/buying/kpi');
    const d = await r.json();
    if (!d.success) { panel.style.display='none'; return; }
    const bySt = d.orders_by_status || {};
    const pending = (bySt.pending_approval||{}).count||0;
    const inDelivery = (bySt.in_delivery||{}).count||0;
    panel.innerHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:8px">'
      + kpiCard('Zamówienia', d.orders_total, '#1565C0', '📦')
      + kpiCard('Oczekujące', pending, '#E65100', '⏳')
      + kpiCard('W dostawie', inDelivery, '#2E7D32', '🚚')
      + kpiCard('Wydatki', (d.total_spend||0).toLocaleString('pl',{maximumFractionDigits:0})+' PLN', '#6A1B9A', '💰')
      + kpiCard('Oszczędności', (d.total_savings||0).toLocaleString('pl',{maximumFractionDigits:0})+' PLN', '#00695C', '📉')
      + kpiCard('Śr. zamówienie', (d.avg_order_value||0).toLocaleString('pl',{maximumFractionDigits:0})+' PLN', '#37474F', '📊')
      + '</div>';
  } catch(e) { panel.style.display='none'; }
}
export function kpiCard(label, value, color, icon) {
  return '<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:12px 16px;text-align:center">'
    + '<div style="font-size:20px;margin-bottom:4px">'+icon+'</div>'
    + '<div style="font-size:20px;font-weight:700;color:'+color+'">'+value+'</div>'
    + '<div style="font-size:11px;color:var(--txt2)">'+label+'</div></div>';
}


function suppGoToVies(searchText) {
  suppShowAddForm();
  const nipInput = document.getElementById('suppNipInput');
  if (nipInput) {
    const cleaned = searchText.replace(/[^0-9]/g, '');
    if (cleaned.length >= 7) nipInput.value = cleaned;
  }
  const form = document.getElementById('suppAddForm');
  if (form) form.scrollIntoView({behavior:'smooth'});
}


/* ═══ BUYER AUCTIONS ═══ */
export async function loadBuyerAuctions() {
  const el = document.getElementById('buyerAuctionList');
  try {
    // Seed demo if needed
    let r = await fetch(API + '/auctions/');
    let data = await r.json();
    if (!data.auctions || data.auctions.length === 0) {
      await fetch(API + '/auctions/demo');
      r = await fetch(API + '/auctions/');
      data = await r.json();
    }
    if (!data.auctions || data.auctions.length === 0) {
      el.innerHTML = '<div style="text-align:center;padding:20px;color:var(--txt2)">Brak aukcji. Kliknij "+ Nowa aukcja" aby utworzyc.</div>';
      return;
    }
    el.innerHTML = data.auctions.map(a => {
      const statusColors = {draft:'#6B7280',published:'#2563EB',active:'#D97706',closing:'#DC2626',closed:'#4B5563',awarded:'#059669',cancelled:'#9CA3AF'};
      const col = statusColors[a.status] || '#6B7280';
      const aid = a.auction_id || a.id;
      const bidCount = (a.bids||[]).length;
      const lineCount = (a.line_items||a.items||[]).length;
      return '<div class="ob-order-row" onclick="showAuctionDetail(\''+aid+'\')" style="cursor:pointer">'
        + '<div style="flex:1"><div style="font-weight:700;font-size:13px;color:var(--navy)">'+escHtml(a.title)+'</div>'
        + '<div style="font-size:11px;color:var(--txt2)">'+(a.auction_type||'')+' | '+lineCount+' pozycji | '+(a.invited_suppliers||[]).length+' dostawcow</div></div>'
        + '<div style="display:flex;gap:8px;align-items:center">'
        + '<span style="font-size:12px;font-weight:700;color:var(--navy)">'+bidCount+' ofert</span>'
        + '<span class="ob-status-badge" style="background:'+col+'22;color:'+col+'">'+a.status+'</span>'
        + '</div></div>';
    }).join('');
  } catch(e) { el.innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>'; }
}

export async function showAuctionDetail(id) {
  const modal = document.getElementById('auctionDetailModal');
  modal.style.display = 'flex';
  const body = document.getElementById('aucDetailBody');
  body.innerHTML = 'Ladowanie...';
  try {
    const [rA, rR, rS] = await Promise.all([
      fetch(API+'/auctions/'+id), fetch(API+'/auctions/'+id+'/ranking'), fetch(API+'/auctions/'+id+'/stats')
    ]);
    const aucData = await rA.json();
    const ranking = await rR.json();
    const stats = await rS.json();
    const auc = aucData.auction || aucData;  // unwrap {auction: {...}}
    document.getElementById('aucDetailTitle').textContent = auc.title || 'Aukcja';

    let html = '<div class="grid-3 mb-16">';
    html += '<div class="kpi"><div class="kpi-value">'+auc.status+'</div><div class="kpi-label">Status</div></div>';
    html += '<div class="kpi"><div class="kpi-value gold">'+(stats.total_bids||0)+'</div><div class="kpi-label">Oferty</div></div>';
    html += '<div class="kpi"><div class="kpi-value">'+(stats.unique_suppliers||stats.unique_bidders||0)+'</div><div class="kpi-label">Oferenci</div></div>';
    html += '</div>';

    // Best bids per line
    const bestBids = stats.best_bids || {};
    const bestKeys = Object.keys(bestBids);
    if (bestKeys.length > 0) {
      html += '<div style="margin-bottom:16px">';
      bestKeys.forEach(lid => {
        const bb = bestBids[lid];
        if (bb && bb.best_supplier) {
          html += '<div style="background:#D1FAE5;padding:10px 16px;border-radius:8px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">'
            + '<div><div style="font-size:11px;color:#065F46;font-weight:600">'+escHtml(bb.product_name||lid)+'</div>'
            + '<div style="font-size:12px;color:#065F46">Najlepsza: '+escHtml(bb.best_supplier)+'</div></div>'
            + '<div style="font-size:18px;font-weight:800;color:#065F46">'+(bb.best_price||0).toLocaleString('pl',{minimumFractionDigits:2})+' PLN</div></div>';
        }
      });
      html += '</div>';
    }

    // Ranking table — rankings is keyed by line_id
    const allBids = [];
    const rankings = ranking.rankings || {};
    Object.entries(rankings).forEach(([lid, li]) => {
      if (li.ranking) li.ranking.forEach(b => allBids.push({...b, line_id: lid, product_name: li.product_name}));
    });
    if (allBids.length > 0) {
      allBids.sort((a,b) => (a.unit_price||a.total_price||0) - (b.unit_price||b.total_price||0));
      html += '<div class="card-title" style="margin-top:16px">Ranking ofert</div><div class="tbl-wrap"><table><thead><tr>'
        + '<th>#</th><th>Dostawca</th><th>Cena jedn.</th><th>Lead time</th><th>Pozycja</th><th>Data</th></tr></thead><tbody>';
      allBids.forEach((b,i) => {
        const price = b.unit_price || b.total_price || 0;
        html += '<tr' + (i===0?' style="background:#D1FAE5"':'') + '><td><b>'+(i+1)+'</b></td><td>'+escHtml(b.supplier_id)+'</td>'
          + '<td style="font-weight:700">'+price.toLocaleString('pl',{minimumFractionDigits:2})+' PLN</td>'
          + '<td>'+(b.lead_time_days||'-')+' dni</td><td>'+escHtml(b.line_id||b.product_name||'-')+'</td>'
          + '<td style="font-size:11px">'+(b.submitted_at?new Date(b.submitted_at).toLocaleString('pl'):'-')+'</td></tr>';
      });
      html += '</tbody></table></div>';
    } else {
      html += '<div style="margin-top:16px;padding:16px;background:#F8FAFC;border-radius:8px;text-align:center;color:var(--txt2);font-size:13px">Brak ofert — dostawcy moga skladac oferty w Portalu Dostawcy.</div>';
    }

    // Lifecycle buttons
    html += '<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">';
    if (auc.status === 'draft') html += '<button class="ob-action-btn primary" onclick="auctionAction(\''+id+'\',\'publish\')">Opublikuj</button>';
    if (auc.status === 'published') html += '<button class="ob-action-btn primary" onclick="auctionAction(\''+id+'\',\'start\')">Rozpocznij</button>';
    if (auc.status === 'active') html += '<button class="ob-action-btn primary" onclick="auctionAction(\''+id+'\',\'close\')">Zamknij</button>';
    if (auc.status === 'closed') html += '<button class="ob-action-btn primary" onclick="auctionAction(\''+id+'\',\'award\')">Przyznaj</button>';
    if (!['cancelled','awarded'].includes(auc.status)) html += '<button class="ob-action-btn danger" onclick="auctionAction(\''+id+'\',\'cancel\')">Anuluj</button>';
    html += '</div>';

    body.innerHTML = html;
  } catch(e) { body.innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>'; }
}

export function closeAuctionDetail() {
  document.getElementById('auctionDetailModal').style.display = 'none';
}

export async function auctionAction(id, action) {
  try {
    await fetch(API+'/auctions/'+id+'/'+action, {method:'POST'});
    showAuctionDetail(id);
    loadBuyerAuctions();
  } catch(e) { alert('Blad: '+e.message); }
}

export function openCreateAuctionModal() { document.getElementById('createAuctionModal').style.display = 'flex'; }
export function closeCreateAuctionModal() { document.getElementById('createAuctionModal').style.display = 'none'; }

export async function submitCreateAuction() {
  const title = document.getElementById('newAucTitle').value.trim();
  if (!title) { alert('Podaj tytul aukcji.'); return; }
  let rawItems = [];
  try { rawItems = JSON.parse(document.getElementById('newAucItems').value); } catch(e) { alert('Nieprawidlowy JSON pozycji.'); return; }
  const lineItems = rawItems.map((it,i) => ({
    line_id: 'L'+(i+1).toString().padStart(3,'0'),
    product_name: it.name || it.product_name || '',
    quantity: it.quantity || 1,
    unit: it.unit || 'szt',
    max_unit_price: it.max_price || it.max_unit_price || 0
  }));
  const suppliers = document.getElementById('newAucSuppliers').value.split(',').map(s=>s.trim()).filter(Boolean);
  try {
    const r = await fetch(API+'/auctions/', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        title, auction_type: document.getElementById('newAucType').value,
        min_decrement_pct: parseFloat(document.getElementById('newAucDecrement').value),
        auto_extend_minutes: parseInt(document.getElementById('newAucExtend').value),
        line_items: lineItems, invited_suppliers: suppliers
      })
    });
    const data = await r.json();
    closeCreateAuctionModal();
    loadBuyerAuctions();
    const auc = data.auction || data;
    alert('Aukcja "'+auc.title+'" utworzona (status: '+auc.status+')');
  } catch(e) { alert('Blad: '+e.message); }
}

/* ═══ Predictive Analytics Functions ═══ */
let predProfilesChart = null;


