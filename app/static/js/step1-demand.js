/**
 * step1-demand.js — Category selection, catalog browsing, UNSPSC search,
 *                   CIF upload, ad-hoc rows, marketplace (Allegro/PunchOut)
 */
import { $, pct } from './ui.js';
import { API, safeFetchJson, apiGet, apiPost } from './api.js';
import { state } from './state.js';
import { DOMAIN_CFG, domainUrls, switchDomain, _makeGenericCfg } from './step3-optimizer.js';
import { openProductDetail } from './product-detail.js';

/* ── UNSPSC mapping tables ── */
export const _UNSPSC_DOMAIN_MAP = {
  '251010': 'vehicles', '251012': 'vehicles', '251030': 'vehicles', '251040': 'vehicles',
  '251110': 'vehicles', '251210': 'vehicles', '251310': 'vehicles',
  '251810': 'vehicles', '251815': 'vehicles',
  '25101500': 'parts', '25101600': 'parts', '25101700': 'parts', '25101900': 'parts',
  '25102000': 'oe_components', '25102100': 'oe_components', '25102200': 'oe_components',
  '25172000': 'batteries', '25171500': 'tires', '25171700': 'tires', '251725': 'bodywork',
  '26101100': 'bodywork',
  '15121500': 'oils', '15121900': 'fuels', '15111500': 'fuels',
  '43211500': 'electronics', '43211600': 'electronics', '43211900': 'electronics',
  '43222600': 'electronics', '43232300': 'it_services', '43231500': 'it_services',
  '44121500': 'office', '44103100': 'office', '44112000': 'office',
  '31121500': 'bearings', '31291500': 'bearings', '31271500': 'bearings',
  '32101500': 'semiconductors', '32121500': 'semiconductors',
  '78101800': 'transport_svc', '78102200': 'transport_svc',
  '24112400': 'packaging', '24102000': 'logistics', '24112200': 'vehicles',
  '27111700': 'mro',
  '80151500': 'fleet_svc', '80151600': 'fleet_svc', '80101500': 'consulting',
  '86101700': 'consulting',
  '82121500': 'printing', '82101500': 'printing',
  '95121500': 'real_estate', '95121600': 'real_estate',
  '72131500': 'construction_svc', '72111200': 'construction_svc',
  '84121500': 'financial_svc', '84131500': 'financial_svc',
  '85101500': 'healthcare_svc', '85121500': 'healthcare_svc',
  '90101500': 'travel', '90121500': 'travel',
};

export const _UNSPSC_SEGMENT_DOMAINS = {
  '10': ['horticulture'], '11': ['raw_materials'], '12': ['chemicals'],
  '13': ['rubber_plastics'], '14': ['paper'], '15': ['oils','fuels'],
  '20': ['mining_equip'], '21': ['agri_equip'], '22': ['construction_eq'],
  '23': ['industrial_mach'], '24': ['logistics','packaging'],
  '25': ['vehicles','parts','oe_components','batteries','tires','bodywork'],
  '26': ['electrical'], '27': ['mro'], '30': ['construction','steel'],
  '31': ['bearings'], '32': ['semiconductors'], '39': ['lighting'],
  '40': ['hvac'], '41': ['lab_equipment'], '42': ['medical'],
  '43': ['electronics','it_services'], '44': ['office'], '45': ['printing_equip'],
  '46': ['safety'], '47': ['cleaning'], '48': ['sports'], '49': ['furniture'],
  '50': ['food'], '51': ['pharma'], '52': ['appliances'], '53': ['clothing'],
  '55': ['publications'], '56': ['decorations'], '60': ['prefab'],
  '70': ['agri_services'], '71': ['mining_services'], '72': ['construction_svc'],
  '73': ['production_svc'], '76': ['industrial_clean'], '77': ['environmental'],
  '78': ['transport_svc','logistics'], '80': ['consulting','fleet_svc'],
  '81': ['engineering_svc'], '82': ['printing'], '83': ['utilities'],
  '84': ['financial_svc'], '85': ['healthcare_svc'], '86': ['consulting'],
  '90': ['travel'], '95': ['real_estate'],
};

const _DEFAULT_CHIPS = [
  {code:'25101500', label:'Hamulce', domain:'parts'},
  {code:'251010',   label:'Samochody', domain:'vehicles'},
  {code:'25102000', label:'OE Elektryka', domain:'oe_components'},
  {code:'15121500', label:'Oleje', domain:'oils'},
  {code:'25172000', label:'Akumulatory', domain:'batteries'},
  {code:'25171500', label:'Opony', domain:'tires'},
  {code:'26101100', label:'Elektryka', domain:'electrical'},
  {code:'30101500', label:'Stal', domain:'steel'},
  {code:'31121500', label:'Lozyska', domain:'bearings'},
  {code:'12131500', label:'Chemia', domain:'chemicals'},
  {code:'40101500', label:'HVAC', domain:'hvac'},
  {code:'46181500', label:'BHP', domain:'safety'},
  {code:'43211500', label:'IT / Komputery', domain:'electronics'},
  {code:'44121500', label:'Biuro', domain:'office'},
  {code:'78101800', label:'Transport', domain:'transport_svc'},
  {code:'24112400', label:'Opakowania', domain:'packaging'},
  {code:'27111700', label:'MRO / FM', domain:'mro'},
  {code:'80151500', label:'Fleet', domain:'fleet_svc'},
  {code:'72131500', label:'Budowlane', domain:'construction_svc'},
  {code:'80101500', label:'Consulting', domain:'consulting'},
  {code:'42181500', label:'Medyczne', domain:'medical'},
  {code:'50101500', label:'Zywnosc', domain:'food'},
  {code:'47131500', label:'Czystosc', domain:'cleaning'},
  {code:'49101500', label:'Meble', domain:'furniture'},
];

export function _findDomainByPrefix(code) {
  const seg = code.substring(0,2);
  const related = _UNSPSC_SEGMENT_DOMAINS[seg];
  return related ? related[0] : null;
}

/* ── UNSPSC search with debounce ── */
export function searchUNSPSC(query) {
  clearTimeout(state._unspscTimer);
  const dd = $('unspscDropdown');
  if (!query || query.length < 2) { dd.style.display = 'none'; return; }
  state._unspscTimer = setTimeout(async () => {
    try {
      const data = await safeFetchJson(API + '/unspsc/search?q=' + encodeURIComponent(query));
      if (!data || !data.results || !data.results.length) {
        dd.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--txt2)">Brak wynikow dla &quot;' + query + '&quot;</div>';
        dd.style.display = 'block';
        return;
      }
      let html = '';
      const levelLabels = {segment:'Segment',family:'Rodzina',class:'Klasa',commodity:'Towar'};
      const levelColors = {segment:'#1e3a5f',family:'#2563eb',class:'#7c3aed',commodity:'#059669'};
      const levelIndent = {segment:0,family:12,class:24,commodity:36};
      data.results.forEach(r => {
        const lvl = r.level || 'commodity';
        const badge = r.match === 'ai' ? '<span class="src-badge" style="background:var(--gold);color:#fff;margin-left:6px">AI</span>' : '';
        const lvlBadge = '<span class="src-badge" style="background:' + (levelColors[lvl]||'#666') + ';color:#fff;min-width:52px;text-align:center">' + (levelLabels[lvl]||lvl) + '</span>';
        const indent = levelIndent[lvl] || 0;
        const fontW = lvl === 'segment' ? '700' : lvl === 'family' ? '600' : '400';
        const fontSize = lvl === 'segment' ? '13px' : '12px';
        const bg = lvl === 'segment' ? '#f8fafc' : '';
        html += '<div style="padding:6px 14px 6px ' + (14+indent) + 'px;cursor:pointer;font-size:' + fontSize + ';border-bottom:1px solid #f3f4f6;display:flex;align-items:center;gap:8px;font-weight:' + fontW + ';background:' + bg + '" '
              + 'onmousedown="pickUNSPSC(\'' + r.code + '\',\'' + r.label.replace(/'/g, "\\'") + '\')">'
              + lvlBadge
              + '<span style="font-weight:700;color:var(--navy);min-width:70px">' + r.code + '</span>'
              + '<span style="color:var(--txt2)">' + r.label + '</span>' + badge + '</div>';
      });
      dd.innerHTML = html;
      dd.style.display = 'block';
    } catch(e) { dd.style.display = 'none'; }
  }, 250);
}

export function pickUNSPSC(code, label) {
  $('unspscSearchInput').value = code + ' \u2014 ' + label;
  $('unspscDropdown').style.display = 'none';
  state._selectedUnspscCode = code;
  state._selectedUnspscLabel = label;
  const domain = _UNSPSC_DOMAIN_MAP[code] || _findDomainByPrefix(code) || 'parts';
  updateCategoryChips(code, domain);
  state.categorySelected = true;
  const block = $('ctxCategoryBlock');
  if (block) block.style.display = '';
  switchDomain(domain);
  if (document.getElementById('s1WsCatalog')?.classList.contains('active')) loadS1Catalog();
}

export function updateCategoryChips(code, activeDomain) {
  const container = $('step1Categories');
  const seg = code.substring(0,2);
  safeFetchJson(API + '/unspsc/search?q=' + encodeURIComponent(code.substring(0,2)))
    .then(data => {
      const results = (data && data.results) || [];
      const children = results.filter(r =>
        r.code.startsWith(seg) && r.code !== code && r.level !== 'segment'
      ).slice(0, 12);
      _rebuildChips(container, code, activeDomain, children);
    })
    .catch(() => {
      _rebuildChips(container, code, activeDomain, []);
    });
}

function _rebuildChips(container, selectedCode, activeDomain, childResults) {
  container.innerHTML = '';
  const seg = selectedCode.substring(0,2);

  const activeBtn = document.createElement('button');
  activeBtn.className = 'domain-btn active';
  activeBtn.dataset.domain = activeDomain;
  activeBtn.style.cssText = 'padding:8px 16px;font-size:12px;border-radius:8px';
  const activeLabel = state._selectedUnspscLabel
    || (DOMAIN_CFG[activeDomain]||{}).label
    || activeDomain;
  activeBtn.textContent = selectedCode + ' ' + activeLabel.substring(0, 25);
  activeBtn.onclick = function() { selectCategory(activeDomain, this); };
  container.appendChild(activeBtn);

  if (childResults.length > 0) {
    const sep1 = document.createElement('span');
    sep1.style.cssText = 'width:1px;height:28px;background:var(--gold);margin:0 4px;align-self:center';
    container.appendChild(sep1);
    const label = document.createElement('span');
    label.style.cssText = 'font-size:10px;color:var(--gold);font-weight:600;align-self:center';
    label.textContent = 'Segment ' + seg + ':';
    container.appendChild(label);

    childResults.forEach(r => {
      const domain = _UNSPSC_DOMAIN_MAP[r.code] || _findDomainByPrefix(r.code) || activeDomain;
      const btn = document.createElement('button');
      btn.className = 'domain-btn';
      btn.dataset.domain = domain;
      btn.dataset.unspsc = r.code;
      btn.style.cssText = 'padding:6px 12px;font-size:11px;border-radius:8px;opacity:0.85';
      btn.textContent = r.code + ' ' + r.label.substring(0, 20) + (r.label.length > 20 ? '...' : '');
      btn.title = r.code + ' \u2014 ' + r.label;
      btn.onclick = function() { pickUNSPSC(r.code, r.label); };
      container.appendChild(btn);
    });
  }

  const sep2 = document.createElement('span');
  sep2.style.cssText = 'width:1px;height:28px;background:#e5e7eb;margin:0 6px;align-self:center';
  container.appendChild(sep2);
  const otherLabel = document.createElement('span');
  otherLabel.style.cssText = 'font-size:10px;color:var(--txt2);align-self:center';
  otherLabel.textContent = 'Inne:';
  container.appendChild(otherLabel);

  _DEFAULT_CHIPS.forEach(chip => {
    if (chip.code.startsWith(seg)) return;
    const btn = document.createElement('button');
    btn.className = 'domain-btn';
    btn.dataset.domain = chip.domain;
    btn.dataset.unspsc = chip.code;
    btn.style.cssText = 'padding:6px 12px;font-size:11px;border-radius:8px;opacity:0.4';
    btn.textContent = chip.code + ' ' + chip.label;
    btn.onclick = function() {
      state._selectedUnspscCode = chip.code;
      state._selectedUnspscLabel = chip.label;
      selectCategory(chip.domain, this);
    };
    container.appendChild(btn);
  });
}

export function setS1Kind(kind) {
  state.currentS1Kind = kind;
  document.querySelectorAll('.s1-kind-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.kind === kind);
  });
  document.querySelectorAll('.s1-cat-group').forEach(g => {
    g.classList.toggle('hidden', kind !== 'all' && g.dataset.kind !== kind);
  });
  document.querySelectorAll('.s1-path-card').forEach(card => {
    const kinds = (card.dataset.kinds || '').split(' ');
    const match = kind === 'all' || kinds.includes(kind);
    card.classList.toggle('dimmed', !match);
  });
  const ctxBlock = $('ctxKindBlock');
  const ctxChip  = $('ctxKind');
  if (ctxBlock && ctxChip) {
    if (kind === 'all') {
      ctxBlock.style.display = 'none';
    } else {
      ctxBlock.style.display = '';
      ctxChip.textContent = kind === 'direct' ? 'Direct' : 'Indirect';
      ctxChip.style.background = kind === 'direct' ? '#D1FAE5' : '#E0E7FF';
      ctxChip.style.color      = kind === 'direct' ? '#065F46' : '#3730A3';
    }
  }
}

export function selectCategory(domain, btn) {
  document.querySelectorAll('#step1Categories .domain-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  state.categorySelected = true;
  const block = $('ctxCategoryBlock');
  if (block) block.style.display = '';
  switchDomain(domain);
  if (document.getElementById('s1WsCatalog')?.classList.contains('active')) loadS1Catalog();
  const cfg = DOMAIN_CFG[domain] || {};
  if (cfg.unspsc) {
    document.querySelectorAll('#s1AdhocBody tr').forEach(tr => {
      const unspscInput = tr.querySelectorAll('input')[1];
      if (unspscInput && !unspscInput.value.trim()) {
        unspscInput.value = cfg.unspsc;
      }
    });
  }
}

/* ── Step 1 Path Switcher ── */
export function switchS1Path(path) {
  state.currentS1Path = path;
  ['catalog','adhoc','cif','marketplace'].forEach(p => {
    const card = document.getElementById('s1Path' + p.charAt(0).toUpperCase() + p.slice(1));
    const ws = document.getElementById('s1Ws' + p.charAt(0).toUpperCase() + p.slice(1));
    if (card) card.classList.toggle('active', p === path);
    if (ws) ws.classList.toggle('active', p === path);
  });
  if (path === 'catalog') loadS1Catalog();
  if (path === 'adhoc' && !document.getElementById('s1AdhocBody').children.length) { addAdhocRow(); }
  if (path === 'marketplace') { mktAutoLoad(); }
}

/* ── Catalog browser in Step 1 ── */
export async function loadS1Catalog() {
  const grid = $('s1CatalogGrid');
  grid.innerHTML = '<div style="color:var(--txt2);text-align:center;padding:20px;grid-column:1/-1">Ladowanie...</div>';
  try {
    let url = API + '/buying/catalog';
    if (state.categorySelected && state._selectedUnspscCode) {
      url += '?unspsc=' + encodeURIComponent(state._selectedUnspscCode);
    } else if (state.categorySelected && state.currentDomain) {
      url += '?category=' + encodeURIComponent(state.currentDomain);
    }
    const data = await safeFetchJson(url);
    state._s1CatalogData = data.products || [];
    renderS1Catalog(state._s1CatalogData);
    if (state.categorySelected && state._s1CatalogData.length === 0) {
      const q = state._selectedUnspscLabel || state.currentDomain || '';
      grid.innerHTML = '<div style="color:var(--txt2);text-align:center;padding:20px;grid-column:1/-1">'
        + 'Brak produktow w wybranej kategorii. '
        + '<a href="#" onclick="event.preventDefault();categorySelected=false;loadS1Catalog()" style="color:var(--gold)">Pokaz wszystkie</a>'
        + ' | <a href="#" onclick="event.preventDefault();switchS1Path(\'marketplace\');document.getElementById(\'mktAllegroQuery\').value=\'' + q.replace(/'/g,"\\'") + '\';mktAllegroSearch()" style="color:#FF5A00;font-weight:700">&#128269; Szukaj na Allegro</a>'
        + '</div>';
    }
  } catch(e) {
    grid.innerHTML = '<div style="color:var(--err);padding:12px;grid-column:1/-1">Blad: ' + e.message + '</div>';
  }
}

export function renderS1Catalog(items) {
  const grid = $('s1CatalogGrid');
  $('s1CatCount').textContent = items.length + ' produktow';
  if (!items.length) { grid.innerHTML = '<div style="color:var(--txt2);text-align:center;padding:20px;grid-column:1/-1">Brak produktow</div>'; return; }
  const icons = {'Czesci zamienne':'&#128295;','Komponenty OE':'&#9881;','Oleje i plyny':'&#128167;','Akumulatory':'&#128267;','Opony':'&#9898;','Nadwozie':'&#128663;'};
  grid.innerHTML = items.map(p => {
    const sel = state._s1SelectedItems[p.id];
    const qty = sel ? sel.qty : 0;
    const supps = p.suppliers || [];
    const suppBadge = supps.length === 1
      ? '<div style="font-size:10px;color:#1565c0;margin-top:2px">&#9654; ' + supps[0].name + '</div>'
      : supps.length > 1
        ? '<div style="font-size:10px;color:#1565c0;margin-top:2px">&#9654; ' + supps.length + ' dostawcow</div>'
        : '';
    return '<div class="s1-catalog-item' + (qty > 0 ? ' selected' : '') + '" data-pid="' + p.id + '">'
      + '<div class="s1-cat-img">' + (icons[p.category] || '&#128230;') + '</div>'
      + '<div class="s1-cat-body">'
      + '<div class="section-label" style="color:var(--gold)">' + (p.category || '') + '</div>'
      + '<div class="s1-cat-name">' + (p.name || p.id) + '</div>'
      + '<div class="s1-cat-price">' + (p.price || 0).toFixed(2) + ' PLN <span class="s1-cat-unit">/ ' + (p.unit || 'szt') + '</span></div>'
      + suppBadge
      + '<div class="s1-qty-ctrl">'
      + '<button onclick="s1CatQty(\'' + p.id + '\',-1)">-</button>'
      + '<input type="number" min="0" value="' + qty + '" style="width:40px" onchange="s1CatQtySet(\'' + p.id + '\',this.value)">'
      + '<button onclick="s1CatQty(\'' + p.id + '\',1)">+</button>'
      + '</div></div></div>';
  }).join('');
}

export function s1CatQty(pid, delta) {
  const item = state._s1CatalogData.find(p => p.id === pid);
  if (!item) return;
  const cur = (state._s1SelectedItems[pid]?.qty || 0) + delta;
  if (cur <= 0) { delete state._s1SelectedItems[pid]; } else { state._s1SelectedItems[pid] = { ...item, qty: cur }; }
  renderS1Catalog(state._s1CatalogData);
  updateS1Summary();
  updateGlobalCartBadge();
}

export function s1CatQtySet(pid, val) {
  const item = state._s1CatalogData.find(p => p.id === pid);
  if (!item) return;
  const qty = parseInt(val) || 0;
  if (qty <= 0) { delete state._s1SelectedItems[pid]; } else { state._s1SelectedItems[pid] = { ...item, qty }; }
  renderS1Catalog(state._s1CatalogData);
  updateS1Summary();
  updateGlobalCartBadge();
}

export function s1AddToCartFromCopilot(items) {
  if (!Array.isArray(items) || !items.length) return 0;
  let added = 0;
  items.forEach(it => {
    if (!it || !it.id || !it.qty || it.qty <= 0) return;
    const existing = state._s1SelectedItems[it.id];
    const newQty = (existing?.qty || 0) + it.qty;
    state._s1SelectedItems[it.id] = {
      id: it.id,
      name: it.name || existing?.name || it.id,
      qty: newQty,
      price: (it.price != null ? it.price : existing?.price) || 0,
      category: it.category || existing?.category || '',
      unspsc: it.unspsc || existing?.unspsc || '',
      suppliers: it.suppliers || existing?.suppliers || [],
    };
    added += it.qty;
  });
  if (state._s1CatalogData && state._s1CatalogData.length) {
    renderS1Catalog(state._s1CatalogData);
  }
  updateS1Summary();
  updateGlobalCartBadge();
  return added;
}

export function filterS1Catalog(q) {
  const query = q.toLowerCase();
  const filtered = state._s1CatalogData.filter(p => (p.name || '').toLowerCase().includes(query) || (p.id || '').toLowerCase().includes(query));
  renderS1Catalog(filtered);
}

/* ── Ad hoc form ── */
export function addAdhocRow() {
  state._adhocRowId++;
  const tbody = $('s1AdhocBody');
  const tr = document.createElement('tr');
  tr.id = 'adhoc-' + state._adhocRowId;
  const cfg = DOMAIN_CFG[state.currentDomain] || {};
  const prefillUnspsc = state.categorySelected ? (cfg.unspsc || '') : '';
  tr.innerHTML = '<td style="color:var(--txt2);font-size:11px">' + state._adhocRowId + '</td>'
    + '<td><input type="text" placeholder="np. Klocki hamulcowe TRW" onchange="calcAdhocRow(this)"></td>'
    + '<td><input type="text" value="' + prefillUnspsc + '" placeholder="UNSPSC" style="width:90px" onfocus="this.parentElement.style.position=\'relative\'" oninput="adhocUnspscSearch(this)"></td>'
    + '<td><input type="number" min="1" value="1" style="width:60px" onchange="calcAdhocRow(this)"></td>'
    + '<td><input type="text" value="szt" style="width:50px"></td>'
    + '<td><input type="number" min="0" step="0.01" placeholder="0.00" style="width:80px" onchange="calcAdhocRow(this)"></td>'
    + '<td class="adhoc-line-total" style="font-weight:600;white-space:nowrap">0.00 PLN</td>'
    + '<td><button class="s1-remove-row" onclick="removeAdhocRow(\'' + tr.id + '\')">&times;</button></td>';
  tbody.appendChild(tr);
}

export function removeAdhocRow(id) {
  document.getElementById(id)?.remove();
  recalcAdhocTotal();
}

/* Bulk-populate ad-hoc rows from an array of {name, qty, unit, price?}.
   Used by document ingest when catalog matching fails — user sees the
   rows pre-filled on Step 1 instead of silently losing the items. */
export function s1AddAdhocItems(items) {
  if (!Array.isArray(items) || !items.length) return 0;
  if (typeof window.switchS1Path === 'function') window.switchS1Path('adhoc');
  const tbody = $('s1AdhocBody');
  if (!tbody) return 0;
  let added = 0;
  items.forEach(it => {
    addAdhocRow();
    const tr = tbody.lastElementChild;
    if (!tr) return;
    const inputs = tr.querySelectorAll('input');
    // inputs[0]=name, [1]=unspsc, [2]=qty, [3]=unit, [4]=price
    if (inputs[0]) inputs[0].value = it.name || '';
    if (inputs[2]) inputs[2].value = String(it.qty || 1);
    if (inputs[3] && it.unit) inputs[3].value = it.unit;
    if (inputs[4] && typeof it.price === 'number') inputs[4].value = String(it.price);
    if (inputs[2]) calcAdhocRow(inputs[2]);
    added++;
  });
  return added;
}

export function calcAdhocRow(el) {
  const tr = el.closest('tr');
  const inputs = tr.querySelectorAll('input');
  const qty = parseFloat(inputs[2]?.value) || 0;
  const price = parseFloat(inputs[4]?.value) || 0;
  const total = qty * price;
  tr.querySelector('.adhoc-line-total').textContent = total.toFixed(2) + ' PLN';
  recalcAdhocTotal();
}

export function recalcAdhocTotal() {
  let sum = 0;
  document.querySelectorAll('#s1AdhocBody .adhoc-line-total').forEach(td => {
    sum += parseFloat(td.textContent) || 0;
  });
  $('s1AdhocTotal').textContent = sum.toFixed(2) + ' PLN';
  updateS1Summary();
}

export function adhocUnspscSearch(input) {
  const q = input.value.trim();
  if (q.length < 2) return;
  clearTimeout(input._timer);
  input._timer = setTimeout(async () => {
    try {
      const data = await safeFetchJson(API + '/unspsc/search?q=' + encodeURIComponent(q));
      if (!data?.results?.length) return;
      let dd = input.parentElement.querySelector('.adhoc-unspsc-dd');
      if (!dd) {
        dd = document.createElement('div');
        dd.className = 'adhoc-unspsc-dd';
        dd.style.cssText = 'position:absolute;top:100%;left:0;right:0;background:#fff;border:1px solid var(--border);border-radius:0 0 6px 6px;max-height:160px;overflow-y:auto;z-index:200;box-shadow:0 4px 12px rgba(0,0,0,.12);font-size:11px';
        input.parentElement.appendChild(dd);
      }
      dd.innerHTML = data.results.slice(0, 8).map(r =>
        '<div style="padding:6px 10px;cursor:pointer;border-bottom:1px solid #f3f4f6" onmousedown="event.preventDefault();this.parentElement.previousElementSibling.value=\'' + r.code + '\';this.parentElement.remove()">'
        + '<b>' + r.code + '</b> ' + r.label + '</div>'
      ).join('');
      input.onblur = () => setTimeout(() => dd?.remove(), 200);
    } catch(e) {}
  }, 250);
}

/* ── Demand summary ── */
export function updateS1Summary() {
  let items = 0, value = 0;
  const _suppIds = new Set();
  if (state.currentS1Path === 'catalog' || state.currentS1Path === 'marketplace') {
    Object.values(state._s1SelectedItems).forEach(it => {
      items++; value += it.qty * (it.price || 0);
      (it.suppliers || []).forEach(s => _suppIds.add(s.id));
    });
  } else if (state.currentS1Path === 'adhoc') {
    document.querySelectorAll('#s1AdhocBody tr').forEach(tr => {
      const inputs = tr.querySelectorAll('input');
      const qty = parseFloat(inputs[2]?.value) || 0;
      const price = parseFloat(inputs[4]?.value) || 0;
      if (qty > 0) { items++; value += qty * price; }
    });
  } else if (state.currentS1Path === 'cif') {
    items = parseInt($('s1SumItems')?.textContent) || 0;
    return;
  }
  const panel = $('s1DemandSummary');
  const oldFooterBtn = document.querySelector('#step-1 .step-footer .btn-next');
  if (items > 0) {
    panel.style.display = '';
    $('s1SumItems').textContent = items;
    $('s1SumValue').textContent = value.toFixed(2) + ' PLN';
    const suppInfoEl = $('s1SumSuppliers');
    if (suppInfoEl && state.currentS1Path === 'catalog' && _suppIds.size > 0) {
      suppInfoEl.textContent = _suppIds.size + ' dostawc' + (_suppIds.size === 1 ? 'a' : 'ow');
      suppInfoEl.style.display = '';
    } else if (suppInfoEl) {
      suppInfoEl.style.display = 'none';
    }
    if (oldFooterBtn) oldFooterBtn.style.display = 'none';
  } else {
    panel.style.display = 'none';
    if (oldFooterBtn) oldFooterBtn.style.display = '';
  }
  const footerHint = $('step1FooterHint');
  if (footerHint) {
    if (items > 0) {
      footerHint.innerHTML = '<span style="color:var(--ok);font-weight:600">&#10003; ' + items + ' pozycji w koszyku (' + value.toFixed(0) + ' PLN)</span> \u2014 przejdz dalej aby dobrac dostawcow';
    } else {
      footerHint.innerHTML = '<span style="color:#f59e0b">&#9888; Pusty koszyk</span> \u2014 dodaj produkty z katalogu, ad hoc lub CIF aby uzyskac realna optymalizacje';
    }
  }
}

/* Load demo demand data for step 1 preview */
export async function loadDemoDemand() {
  const el = $('cifResultContent');
  try {
    el.innerHTML = '<div style="text-align:center;padding:16px">Ladowanie danych demo...</div>';
    const data = await safeFetchJson(API + '/demo/' + state.currentDomain + '/demand');
    if (data && data.length) {
      let html = '<table style="width:100%;font-size:12px"><thead><tr><th style="text-align:left;padding:4px 8px">Produkt</th><th style="text-align:right;padding:4px 8px">Ilosc</th></tr></thead><tbody>';
      data.forEach(d => {
        html += '<tr><td style="padding:4px 8px">' + (d.product_id || d.name || '-') + '</td>';
        html += '<td style="padding:4px 8px;text-align:right;font-weight:600">' + (d.quantity || d.qty || '-') + '</td></tr>';
      });
      html += '</tbody></table>';
      html += '<div style="margin-top:8px;font-size:11px;color:var(--txt2)">' + data.length + ' pozycji w demo demand</div>';
      el.innerHTML = html;
    } else {
      el.innerHTML = '<div style="color:var(--txt2);text-align:center;padding:16px">Brak danych demo dla tej kategorii</div>';
    }
  } catch(e) {
    el.innerHTML = '<div style="color:var(--err);padding:8px">Blad: ' + e.message + '</div>';
  }
}

/* ── CIF Upload + UNSPSC Classification ── */
export function handleCifDrop(event) {
  const file = event.dataTransfer.files[0];
  if (file) handleCifUpload(file);
}

export async function handleCifUpload(file) {
  if (!file) return;
  const zone = $('cifDropZone');
  const res = $('cifResultContent');
  zone.style.borderColor = 'var(--gold)';
  res.innerHTML = '<div style="text-align:center;padding:16px"><b>Przetwarzanie ' + file.name + '...</b></div>';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const resp = await fetch(API + '/cif/upload', { method: 'POST', body: formData });
    const data = await resp.json();
    zone.style.borderColor = 'var(--border)';

    if (!data.success || !data.items || !data.items.length) {
      res.innerHTML = '<div style="color:var(--err);padding:8px">Blad parsowania pliku lub brak pozycji.</div>';
      return;
    }

    const c = data.classification;
    let html = '<div style="margin-bottom:12px">';
    html += '<div style="display:flex;gap:16px;margin-bottom:8px;font-size:12px">';
    html += '<span><b>' + data.total_items + '</b> pozycji</span>';
    html += '<span style="color:#2E7D32"><b>' + c.auto_classified + '</b> auto-klasyfikacja</span>';
    html += '<span style="color:#1565C0"><b>' + c.from_cif + '</b> z pliku CIF</span>';
    if (c.unclassified > 0) html += '<span style="color:#E65100"><b>' + c.unclassified + '</b> nieklasyfikowane</span>';
    html += '</div>';

    if (data.classification_summary && data.classification_summary.length) {
      html += '<div style="font-size:11px">';
      data.classification_summary.slice(0, 8).forEach(cat => {
        const pctVal = Math.round((cat.count / data.total_items) * 100);
        const isNone = cat.unspsc_code === '00000000';
        html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">';
        html += '<span style="width:80px;font-weight:700;color:' + (isNone ? 'var(--err)' : 'var(--navy)') + '">' + cat.unspsc_code + '</span>';
        html += '<div style="flex:1;background:#f1f5f9;border-radius:4px;height:16px;overflow:hidden">';
        html += '<div style="width:' + pctVal + '%;height:100%;background:' + (isNone ? '#FEE2E2' : 'var(--gold)') + ';border-radius:4px;min-width:2px"></div></div>';
        html += '<span style="width:28px;text-align:right;font-weight:600">' + cat.count + '</span>';
        html += '<span style="color:var(--txt2);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + (cat.unspsc_name || '') + '</span>';
        html += '</div>';
      });
      html += '</div>';
    }

    html += '<details style="margin-top:8px"><summary style="font-size:11px;font-weight:600;cursor:pointer;color:var(--navy)">Podglad pozycji (' + data.total_items + ')</summary>';
    html += '<table style="width:100%;font-size:11px;margin-top:6px"><thead><tr><th style="text-align:left;padding:3px 6px">Nazwa</th><th style="padding:3px 6px">UNSPSC</th><th style="padding:3px 6px">Klasyf.</th><th style="text-align:right;padding:3px 6px">Cena</th></tr></thead><tbody>';
    data.items.slice(0, 10).forEach(it => {
      html += '<tr><td style="padding:3px 6px">' + (it.name || '-').substring(0, 40) + '</td>';
      html += '<td style="padding:3px 6px;font-weight:600">' + it.unspsc_code + '</td>';
      html += '<td style="padding:3px 6px"><span style="font-size:10px;padding:1px 6px;border-radius:8px;background:' + (it.classified_by==='auto'?'#E8F5E9':it.classified_by==='cif'?'#E3F2FD':'#FEE2E2') + ';color:' + (it.classified_by==='auto'?'#2E7D32':it.classified_by==='cif'?'#1565C0':'#991B1B') + '">' + it.classified_by + '</span></td>';
      html += '<td style="padding:3px 6px;text-align:right">' + (it.price ? it.price.toFixed(2) + ' ' + it.currency : '-') + '</td></tr>';
    });
    if (data.total_items > 10) html += '<tr><td colspan="4" style="padding:3px 6px;color:var(--txt2);text-align:center">... i ' + (data.total_items - 10) + ' wiecej</td></tr>';
    html += '</tbody></table></details>';
    html += '</div>';
    res.innerHTML = html;

  } catch(e) {
    zone.style.borderColor = 'var(--border)';
    res.innerHTML = '<div style="color:var(--err);padding:8px">Blad: ' + e.message + '</div>';
  }
}

/* ── Marketplace: Allegro + PunchOut ── */
export function switchMktSource(src) {
  $('mktAllegroPanel').style.display = src === 'allegro' ? '' : 'none';
  $('mktPunchoutPanel').style.display = src === 'punchout' ? '' : 'none';
  $('mktSrcAllegro').style.background = src === 'allegro' ? 'var(--navy)' : '#fff';
  $('mktSrcAllegro').style.color = src === 'allegro' ? '#fff' : 'var(--txt2)';
  $('mktSrcPunchout').style.background = src === 'punchout' ? 'var(--navy)' : '#fff';
  $('mktSrcPunchout').style.color = src === 'punchout' ? '#fff' : 'var(--txt2)';
  if (src === 'punchout' && !state._mktPunchoutSessionId) mktPunchoutSetup();
}

export async function mktAllegroSearch() {
  const q = $('mktAllegroQuery').value.trim();
  if (!q) return;
  const grid = $('mktAllegroGrid');
  const btn = $('mktAllegroBtn');
  btn.classList.add('loading');
  grid.innerHTML = '<div style="color:var(--txt2);text-align:center;padding:24px;grid-column:1/-1"><span class="spin"></span> Szukam na Allegro: <b>' + q + '</b>...</div>';
  try {
    const data = await safeFetchJson(API + '/marketplace/allegro/search?q=' + encodeURIComponent(q) + '&limit=24');
    state._mktAllegroData = data.products || [];
    $('mktAllegroCount').textContent = state._mktAllegroData.length + ' wynikow';
    const src = data.source || 'allegro';
    if (src === 'allegro_mock') {
      $('mktAllegroStatus').innerHTML = '<span style="color:var(--warn)">&#9889; Tryb demo</span>'
        + ' <button class="btn btn-sm" style="font-size:10px;padding:2px 8px;margin-left:4px" onclick="mktAllegroAuth()">Polacz z Allegro</button>';
    } else {
      $('mktAllegroStatus').innerHTML = '<span style="color:var(--ok)">&#10003; Allegro API</span>';
    }
    renderMktAllegro(state._mktAllegroData);
  } catch(e) {
    grid.innerHTML = '<div style="color:var(--err);padding:12px;grid-column:1/-1">Blad: ' + e.message + '</div>';
  } finally { btn.classList.remove('loading'); }
}

export async function mktAllegroAuth() {
  try {
    const st = await apiGet('/marketplace/allegro/status');
    if (!st.configured) { alert('Allegro API nie skonfigurowane (brak FLOW_ALLEGRO_CLIENT_ID)'); return; }
    if (st.has_token) {
      $('mktAllegroStatus').innerHTML = '<span style="color:var(--ok)">&#10003; Allegro API polaczone!</span>';
      mktAllegroSearch();
      return;
    }
    const clientId = st.client_id;
    const redirectUri = encodeURIComponent(window.location.origin + '/api/v1/marketplace/allegro/callback');
    const authUrl = 'https://allegro.pl/auth/oauth/authorize?response_type=code&client_id=' + clientId + '&redirect_uri=' + redirectUri;
    $('mktAllegroStatus').innerHTML = '<span style="color:var(--gold)">&#9203; Przekierowuje do Allegro...</span>';
    window.open(authUrl, '_blank');
    const poller = setInterval(async () => {
      const poll = await apiGet('/marketplace/allegro/status');
      if (poll.has_token) {
        clearInterval(poller);
        $('mktAllegroStatus').innerHTML = '<span style="color:var(--ok)">&#10003; Allegro API polaczone!</span>';
        mktAllegroSearch();
      }
    }, 3000);
    setTimeout(() => clearInterval(poller), 300000);
  } catch(e) { alert('Blad: ' + e.message); }
}

export function renderMktAllegro(items) {
  const grid = $('mktAllegroGrid');
  if (!items.length) { grid.innerHTML = '<div style="color:var(--txt2);text-align:center;padding:24px;grid-column:1/-1">Brak wynikow</div>'; return; }
  grid.innerHTML = items.map(p => {
    const sel = state._s1SelectedItems[p.id];
    const qty = sel ? sel.qty : 0;
    const imgHtml = p.image_url
      ? '<img src="' + p.image_url + '" style="width:100%;height:100%;object-fit:contain;border-radius:8px" loading="lazy" onerror="this.parentElement.innerHTML=\'&#127968;\'">'
      : '&#127968;';
    const deliveryBadge = p.delivery_cost > 0
      ? '<span style="font-size:10px;color:var(--txt2)">+ ' + p.delivery_cost.toFixed(2) + ' dostawa</span>'
      : '<span style="font-size:10px;color:var(--ok)">Darmowa dostawa</span>';
    const supplierName = (p.suppliers && p.suppliers[0]) ? p.suppliers[0].name : 'Allegro';
    return '<div class="s1-catalog-item' + (qty > 0 ? ' selected' : '') + '" data-pid="' + p.id + '" style="cursor:pointer" onclick="if(!event.target.closest(\'.s1-qty-ctrl\'))openProductDetail(\'' + p.id + '\')">'
      + '<div class="s1-cat-img" style="font-size:28px">' + imgHtml + '</div>'
      + '<div class="s1-cat-body">'
      + '<div style="font-size:10px;color:#FF5A00;text-transform:uppercase;font-weight:700;display:flex;gap:6px;align-items:center">ALLEGRO</div>'
      + '<div class="s1-cat-name" style="font-size:12px">' + (p.name || p.id).substring(0, 60) + '</div>'
      + '<div class="s1-cat-price">' + (p.price || 0).toFixed(2) + ' ' + (p.currency || 'PLN') + ' <span class="s1-cat-unit">/ ' + (p.unit || 'szt') + '</span></div>'
      + '<div style="display:flex;gap:8px;align-items:center;margin-top:2px">'
      + '<div style="font-size:10px;color:#1565c0">&#9654; ' + supplierName + '</div>'
      + deliveryBadge
      + '</div>'
      + '<div class="s1-qty-ctrl">'
      + '<button onclick="mktQty(\'' + p.id + '\',-1)">-</button>'
      + '<input type="number" min="0" value="' + qty + '" style="width:40px" onchange="mktQtySet(\'' + p.id + '\',this.value)">'
      + '<button onclick="mktQty(\'' + p.id + '\',1)">+</button>'
      + '</div></div></div>';
  }).join('');
}

export function mktQty(pid, delta) {
  const item = state._mktAllegroData.find(p => p.id === pid) || state._mktPunchoutData.find(p => p.id === pid);
  if (!item) return;
  const cur = (state._s1SelectedItems[pid]?.qty || 0) + delta;
  if (cur <= 0) { delete state._s1SelectedItems[pid]; } else { state._s1SelectedItems[pid] = { ...item, qty: cur }; }
  if (state._mktAllegroData.length) renderMktAllegro(state._mktAllegroData);
  if (state._mktPunchoutData.length) renderMktPunchout(state._mktPunchoutData);
  updateS1Summary();
  updateGlobalCartBadge();
}

export function mktQtySet(pid, val) {
  const item = state._mktAllegroData.find(p => p.id === pid) || state._mktPunchoutData.find(p => p.id === pid);
  if (!item) return;
  const qty = parseInt(val) || 0;
  if (qty <= 0) { delete state._s1SelectedItems[pid]; } else { state._s1SelectedItems[pid] = { ...item, qty }; }
  if (state._mktAllegroData.length) renderMktAllegro(state._mktAllegroData);
  if (state._mktPunchoutData.length) renderMktPunchout(state._mktPunchoutData);
  updateS1Summary();
  updateGlobalCartBadge();
}

/* ── PunchOut (Allegro cXML) ── */
export function mktAutoLoad() {
  if (!state._mktPunchoutSessionId) {
    switchMktSource('punchout');
  }
}

export async function mktPunchoutSetup(category) {
  const status = $('mktPunchoutStatus');
  status.innerHTML = '<span class="spin" style="display:inline-block"></span> Nawiazywanie sesji cXML PunchOut z Allegro...';
  try {
    const data = await apiPost('/marketplace/punchout/setup', {});
    state._mktPunchoutSessionId = data.session_id;
    $('mktPunchoutSessionId').innerHTML = '<span style="color:var(--ok)">&#9989;</span> Sesja: ' + data.session_id;
    $('mktPunchoutReturnBtn').style.display = '';
    $('mktPunchoutXml').textContent = '<!-- cXML PunchOutSetupResponse -->\n' + data.cxml_response;
    await mktPunchoutLoadBrowse(category || '');
  } catch(e) {
    status.innerHTML = '<div style="color:var(--err)">Blad: ' + e.message + '</div>';
  }
}

export async function mktPunchoutLoadBrowse(category) {
  const status = $('mktPunchoutStatus');
  status.innerHTML = '<span class="spin" style="display:inline-block"></span> Pobieranie katalogu...';
  const catParam = category ? '?category=' + encodeURIComponent(category) : '';
  const browse = await safeFetchJson(API + '/marketplace/punchout/browse/' + state._mktPunchoutSessionId + catParam);
  state._mktPunchoutData = browse.products || [];
  status.innerHTML = '<span style="font-size:11px;color:var(--txt2)">' + state._mktPunchoutData.length + ' produktow'
    + (category ? ' w kategorii <b>' + category + '</b>' : ' (wszystkie kategorie)') + '</span>';
  renderMktPunchout(state._mktPunchoutData);
}

export async function mktPunchoutFilter(category) {
  state._mktPunchoutCategory = category;
  document.querySelectorAll('#mktPunchoutCategories button').forEach(btn => {
    const cat = btn.getAttribute('data-cat');
    btn.style.background = (cat === category) ? 'var(--navy)' : '#fff';
    btn.style.color = (cat === category) ? '#fff' : 'var(--txt2)';
  });
  if (!state._mktPunchoutSessionId) {
    await mktPunchoutSetup(category);
  } else {
    await mktPunchoutLoadBrowse(category);
  }
}

export function renderMktPunchout(items) {
  const grid = $('mktPunchoutGrid');
  if (!items.length) { grid.innerHTML = '<div style="color:var(--txt2);text-align:center;padding:20px;grid-column:1/-1">Brak produktow w tej kategorii</div>'; return; }
  grid.innerHTML = items.map(p => {
    const sel = state._s1SelectedItems[p.id];
    const qty = sel ? sel.qty : 0;
    const supplier = p.supplier_name || (p.suppliers && p.suppliers[0] ? p.suppliers[0].name : 'Allegro Seller');
    const contract = p.contract_no ? '<div style="font-size:10px;color:var(--ok);margin-top:2px">&#128196; ' + p.contract_no + '</div>' : '';
    const delivery = p.delivery_days != null ? '<span style="font-size:10px;color:var(--txt2);margin-left:6px">&#128666; ' + p.delivery_days + 'd</span>' : '';
    return '<div class="s1-catalog-item' + (qty > 0 ? ' selected' : '') + '" data-pid="' + p.id + '" style="cursor:pointer" onclick="if(!event.target.closest(\'.s1-qty-ctrl\'))openProductDetail(\'' + p.id + '\')">'
      + '<div class="s1-cat-img">&#127978;</div>'
      + '<div class="s1-cat-body">'
      + '<div style="font-size:10px;color:var(--purple);text-transform:uppercase;font-weight:700;display:flex;align-items:center;gap:6px">ALLEGRO PUNCHOUT</div>'
      + '<div class="s1-cat-name">' + (p.name || p.id) + '</div>'
      + '<div style="font-size:10px;color:var(--txt2);margin:2px 0">&#127970; ' + supplier + '</div>'
      + contract
      + '<div class="s1-cat-price">' + (p.price || 0).toFixed(2) + ' PLN <span class="s1-cat-unit">/ ' + (p.unit || 'szt') + '</span>' + delivery + '</div>'
      + '<div class="s1-qty-ctrl">'
      + '<button onclick="mktQty(\'' + p.id + '\',-1)">-</button>'
      + '<input type="number" min="0" value="' + qty + '" style="width:40px" onchange="mktQtySet(\'' + p.id + '\',this.value)">'
      + '<button onclick="mktQty(\'' + p.id + '\',1)">+</button>'
      + '</div></div></div>';
  }).join('');
}

export async function mktPunchoutReturn() {
  if (!state._mktPunchoutSessionId) return;
  const cartItems = Object.values(state._s1SelectedItems).filter(i => i.source === 'punchout');
  for (const ci of cartItems) {
    await apiPost('/marketplace/punchout/cart/' + state._mktPunchoutSessionId, {
      item_id: ci.id, name: ci.name, price: ci.price, qty: ci.qty
    });
  }
  const data = await apiPost('/marketplace/punchout/return/' + state._mktPunchoutSessionId, {});
  $('mktPunchoutXml').style.display = '';
  $('mktPunchoutXml').textContent = '<!-- cXML PunchOutOrderMessage -->\n' + (data.cxml_order_message || 'Brak danych');
  $('mktPunchoutStatus').innerHTML = '<div style="padding:8px 12px;background:#DBEAFE;border-radius:6px;font-size:12px;color:#1E40AF">'
    + '&#9989; Koszyk zwrocony jako cXML | ' + (data.cart_items || []).length + ' pozycji | '
    + (data.cart_total || 0).toFixed(2) + ' PLN</div>';
}

/* ── Global Cart Badge (imported by other modules) ── */
export function updateGlobalCartBadge() {
  const badge = document.getElementById('globalCartBadge');
  if (!badge) return;
  let count = state.obCart.reduce((sum, c) => sum + c.quantity, 0);
  if (count === 0) {
    count = Object.values(state._s1SelectedItems || {}).reduce((sum, i) => sum + (i.qty || 1), 0);
  }
  badge.textContent = count;
  badge.style.display = count > 0 ? 'flex' : 'none';
}
