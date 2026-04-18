/**
 * copilot.js — AI copilot widget
 */
import { $ } from './ui.js';
import { API } from './api.js';
import { state } from './state.js';

function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

export function toggleCopilot() {
  state.copilotOpen = !state.copilotOpen;
  const w = document.getElementById('copilotWidget');
  const fab = document.getElementById('copilotFab');
  // In assistant mode the widget lives inside dashAssistantSlot and stays open.
  if (w.classList.contains('assistant-mode')) {
    state.copilotOpen = true;
    w.style.display = 'flex';
    fab.style.display = 'none';
    return;
  }
  w.style.display = state.copilotOpen ? 'flex' : 'none';
  fab.style.display = state.copilotOpen ? 'none' : 'flex';
  if (state.copilotOpen && state.copilotHistory.length === 0) {
    loadCopilotSuggestions();
    addCopilotMsg('assistant', 'Witaj! Jestem Twoj asystent zakupowy. Wpisz pytanie, np.:\n\n- "Szukaj laptopa na Allegro"\n- "Pokaz katalog klocki hamulcowe"\n- "Porownaj dostawcow dla tej kategorii"\n- "Jak zlozyc zamowienie?"\n\nJak moge Ci pomoc?');
  }
}

export function enableAssistantMode() {
  const w = document.getElementById('copilotWidget');
  const fab = document.getElementById('copilotFab');
  const slot = document.getElementById('dashAssistantSlot');
  if (!w || !slot) return;
  // Only re-parent on first entry — DOM move is idempotent here thanks to
  // the explicit parent check.
  if (w.parentElement !== slot) slot.appendChild(w);
  w.classList.add('assistant-mode');
  w.style.display = 'flex';
  if (fab) fab.classList.add('assistant-hidden');
  state.copilotOpen = true;
  if (state.copilotHistory.length === 0) {
    loadCopilotSuggestions();
    addCopilotMsg('assistant',
      'Jestem Twoim asystentem zakupowym. Po prawej widzisz rzeczy, ktore wymagaja uwagi dzisiaj — klik w karte przenosi Cie do wlasciwego miejsca.\n\nMozesz tez napisac do mnie po polsku, np.:\n- "dodaj 10 filtrow oleju do koszyka"\n- "pokaz najlepszych dostawcow opon"\n- "wyjasnij front Pareto"');
  }
}

export function disableAssistantMode() {
  const w = document.getElementById('copilotWidget');
  const fab = document.getElementById('copilotFab');
  if (!w) return;
  w.classList.remove('assistant-mode');
  // Return widget to <body> so it renders as floating again
  if (w.parentElement && w.parentElement.id === 'dashAssistantSlot') {
    document.body.appendChild(w);
  }
  w.style.display = 'none';
  state.copilotOpen = false;
  if (fab) {
    fab.classList.remove('assistant-hidden');
    fab.style.display = 'flex';
  }
}

export function toggleAssistantMode() {
  const w = document.getElementById('copilotWidget');
  if (!w) return;
  if (w.classList.contains('assistant-mode')) {
    disableAssistantMode();
    try { localStorage.setItem('assistantModePref', 'mini'); } catch (e) {}
  } else {
    enableAssistantMode();
    try { localStorage.setItem('assistantModePref', 'panel'); } catch (e) {}
  }
}

export async function loadDashActionCards() {
  const el = document.getElementById('dashActionCards');
  if (!el) return;
  try {
    const r = await fetch(API + '/copilot/recommendations?step=0');
    const data = await r.json();
    const cards = data.cards || [];
    if (!cards.length) {
      el.innerHTML = '<div class="section-label">Brak rekomendacji.</div>';
      return;
    }
    const html = [
      '<div class="section-label">Co wymaga Twojej uwagi</div>',
    ];
    cards.forEach((c, i) => {
      const clickable = !!c.action;
      const classes = ['action-card', c.urgency === 'urgent' ? 'urgent' : 'info'];
      if (!clickable) classes.push('no-action');
      const a11y = clickable
        ? ` onclick="window.dispatchActionCard(${i})"`
          + ` onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();window.dispatchActionCard(${i})}"`
          + ' tabindex="0" role="button"'
          + ' aria-label="' + escHtml((c.title || '') + '. ' + (c.cta || '')) + '"'
        : '';
      html.push(
        '<div class="' + classes.join(' ') + '"' + a11y + '>'
          + '<div class="ac-icon" aria-hidden="true">' + (c.icon || '💡') + '</div>'
          + '<div class="ac-body">'
            + '<div class="ac-title">' + escHtml(c.title || '') + '</div>'
            + '<div class="ac-desc">' + escHtml(c.desc || '') + '</div>'
            + (c.cta ? '<span class="ac-cta">' + escHtml(c.cta) + ' →</span>' : '')
          + '</div>'
        + '</div>'
      );
    });
    el.innerHTML = html.join('');
    // Stash cards on window so onclick can pull the action object back.
    window.__dashCards = cards;
  } catch (e) {
    el.innerHTML = '<div class="section-label">Nie udalo sie wczytac rekomendacji.</div>';
  }
}

export function dispatchActionCard(index) {
  const cards = window.__dashCards || [];
  const c = cards[index];
  if (!c || !c.action) return;
  if (typeof window.executeCopilotAction === 'function') {
    window.executeCopilotAction(c.action);
  }
}

/* ─── Document paste widget (MVP-2a) ─── */

export function toggleDocPasteWidget() {
  const w = document.getElementById('docPasteWidget');
  if (!w) return;
  w.style.display = w.style.display === 'none' ? 'block' : 'none';
  if (w.style.display === 'block') {
    const ta = document.getElementById('docPasteText');
    if (ta) ta.focus();
  }
}

export function docPasteClear() {
  const ta = document.getElementById('docPasteText');
  const res = document.getElementById('docPasteResults');
  const status = document.getElementById('docPasteStatus');
  if (ta) ta.value = '';
  if (res) res.innerHTML = '';
  if (status) status.textContent = '';
}

export async function docPasteSubmit() {
  const ta = document.getElementById('docPasteText');
  const btn = document.getElementById('docPasteSubmitBtn');
  const status = document.getElementById('docPasteStatus');
  const results = document.getElementById('docPasteResults');
  if (!ta || !btn || !status || !results) return;

  const text = (ta.value || '').trim();
  if (text.length < 10) {
    status.textContent = 'Tekst za krotki';
    return;
  }
  btn.disabled = true;
  status.textContent = 'AI analizuje...';
  results.innerHTML = '';

  try {
    const r = await fetch(API + '/copilot/document/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await r.json();
    const items = data.items || [];
    if (!items.length) {
      status.textContent = 'Nie wykryto pozycji w tekscie';
      results.innerHTML = '<div style="font-size:11px;color:var(--txt2);padding:8px">Sprobuj bardziej konkretnego tekstu z nazwami produktow i ilosciami.</div>';
      return;
    }
    status.textContent = `Znaleziono ${items.length} pozycji`;
    window.__docPasteItems = items;
    const html = items.map((it, i) => {
      const hit = it.matched_id
        ? `<div class="di-match">✓ ${escHtml(it.matched_name)}${it.matched_price ? ` (${it.matched_price.toFixed(0)} PLN)` : ''}</div>`
        : '<div class="di-match miss">× Brak w katalogu — pozostanie jako ad-hoc</div>';
      const note = it.note ? `<div class="di-note">${escHtml(it.note)}</div>` : '';
      return ''
        + '<div class="doc-item-review">'
          + '<span class="di-qty">' + it.qty + ' ' + escHtml(it.unit || 'szt') + '</span>'
          + '<div class="di-name">'
            + '<div><b>' + escHtml(it.name) + '</b></div>'
            + hit
            + note
          + '</div>'
        + '</div>';
    }).join('');
    const cta = '<button class="doc-add-all" onclick="docAddAllToCart()">🛒 Dodaj wszystkie (' + items.length + ') do koszyka</button>';
    results.innerHTML = html + cta;
  } catch (e) {
    status.textContent = 'Blad: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

export async function docFileSubmit(file) {
  const btn = document.getElementById('docPasteSubmitBtn');
  const status = document.getElementById('docPasteStatus');
  const results = document.getElementById('docPasteResults');
  if (!file || !status || !results) return;

  const MAX = 5 * 1024 * 1024;
  if (file.size > MAX) {
    status.textContent = 'Plik zbyt duzy (max 5 MB)';
    return;
  }

  if (btn) btn.disabled = true;
  status.textContent = 'Parsuje ' + file.name + '...';
  results.innerHTML = '';

  try {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(API + '/copilot/document/extract-file', { method: 'POST', body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({detail: r.statusText}));
      status.textContent = 'Blad: ' + (err.detail || r.statusText);
      return;
    }
    const data = await r.json();
    const items = data.items || [];
    const fmt = data.format ? ' [' + data.format.toUpperCase() + ']' : '';
    if (!items.length) {
      status.textContent = 'Brak pozycji' + fmt;
      results.innerHTML = '<div style="font-size:11px;color:var(--txt2);padding:8px">'
        + (data.message || 'AI nie znalazl pozycji zakupowych w pliku. Moze to skan? Sprobuj innego formatu.')
        + '</div>';
      return;
    }
    status.textContent = 'Znaleziono ' + items.length + ' pozycji' + fmt;
    window.__docPasteItems = items;
    const html = items.map((it) => {
      const hit = it.matched_id
        ? '<div class="di-match">&#10003; ' + escHtml(it.matched_name) + (it.matched_price ? ' (' + it.matched_price.toFixed(0) + ' PLN)' : '') + '</div>'
        : '<div class="di-match miss">&#215; Brak w katalogu &mdash; pozostanie jako ad-hoc</div>';
      const note = it.note ? '<div class="di-note">' + escHtml(it.note) + '</div>' : '';
      return '<div class="doc-item-review">'
        + '<span class="di-qty">' + it.qty + ' ' + escHtml(it.unit || 'szt') + '</span>'
        + '<div class="di-name">'
          + '<div><b>' + escHtml(it.name) + '</b></div>'
          + hit + note
        + '</div>'
      + '</div>';
    }).join('');
    results.innerHTML = html
      + '<button class="doc-add-all" onclick="docAddAllToCart()">\ud83d\udecd\ufe0f Dodaj wszystkie (' + items.length + ') do koszyka</button>';
  } catch (e) {
    status.textContent = 'Blad: ' + e.message;
  } finally {
    if (btn) btn.disabled = false;
    // Reset file input so the same file can be re-picked if needed
    const fi = document.getElementById('docFileInput');
    if (fi) fi.value = '';
  }
}

export function docAddAllToCart() {
  const items = window.__docPasteItems || [];
  if (!items.length) return;

  const matched = items.filter(it => it.matched_id);
  const unmatched = items.filter(it => !it.matched_id);

  const matchedPayload = matched.map(it => ({
    id: it.matched_id,
    name: it.matched_name || it.name,
    qty: it.qty,
    price: it.matched_price || 0,
  }));

  let added = 0;
  if (matchedPayload.length && typeof window.s1AddToCartFromCopilot === 'function') {
    added = window.s1AddToCartFromCopilot(matchedPayload);
  }

  const res = document.getElementById('docPasteResults');
  if (!res) return;

  const parts = [];
  if (matchedPayload.length) {
    parts.push(
      '<div style="padding:10px;background:#ECFDF5;border-left:3px solid var(--ok);'
      + 'color:var(--ok);font-weight:600;font-size:12px;border-radius:4px;margin-bottom:8px">'
      + '&#10003; Dodano ' + added + ' szt. z ' + matchedPayload.length + ' dopasowanych pozycji'
      + '</div>'
    );
  }

  if (unmatched.length) {
    const rows = unmatched.map(it =>
      '<li style="padding:4px 0">'
      + '<b>' + escHtml(it.name) + '</b>'
      + ' <span style="color:var(--txt2);font-size:11px">(' + it.qty + ' ' + escHtml(it.unit || 'szt') + ')</span>'
      + '</li>'
    ).join('');
    window.__docPasteUnmatched = unmatched;
    parts.push(
      '<div style="padding:10px;background:#FEF3C7;border-left:3px solid #D97706;'
      + 'font-size:12px;border-radius:4px">'
      + '<div style="font-weight:600;color:#92400E;margin-bottom:6px">'
      + '&#9888; ' + unmatched.length + ' pozycji bez dopasowania w katalogu'
      + '</div>'
      + '<ul style="margin:4px 0 8px 16px;color:var(--txt)">' + rows + '</ul>'
      + '<button onclick="docAddUnmatchedAsAdhoc()" '
      + 'style="padding:6px 12px;background:#D97706;color:#fff;border:0;border-radius:4px;'
      + 'font-size:11px;font-weight:600;cursor:pointer">'
      + '+ Dodaj jako ad-hoc (Step 1)'
      + '</button>'
      + '</div>'
    );
  }

  if (!parts.length) {
    parts.push('<div style="padding:12px;text-align:center;color:var(--txt2)">Brak pozycji do dodania</div>');
  }

  res.innerHTML = parts.join('');

  if (window.toast) {
    if (matchedPayload.length && unmatched.length) {
      window.toast('🛒 Dodano ' + added + ' dopasowanych, ' + unmatched.length + ' wymagaja ad-hoc');
    } else if (matchedPayload.length) {
      window.toast('🛒 Dodano ' + added + ' szt.');
    } else {
      window.toast('Zadna pozycja nie ma dopasowania — uzyj ad-hoc');
    }
  }
}

export function docAddUnmatchedAsAdhoc() {
  const unmatched = window.__docPasteUnmatched || [];
  if (!unmatched.length) return;
  if (typeof window.s1AddAdhocItems === 'function') {
    window.s1AddAdhocItems(unmatched);
    if (window.toast) window.toast('+ ' + unmatched.length + ' pozycji w ad-hoc na Step 1');
    if (typeof window.goStep === 'function') window.goStep(1);
  } else {
    // Graceful fallback: navigate to Step 1 and let user manually enter ad-hoc.
    if (typeof window.goStep === 'function') window.goStep(1);
    if (window.toast) window.toast('Dodaj pozycje recznie jako ad-hoc na Step 1');
  }
  window.__docPasteUnmatched = [];
}

export function addCopilotMsg(role, text) {
  state.copilotHistory.push({role, content: text});
  renderCopilotChat();
}

export function renderCopilotChat() {
  const el = document.getElementById('copilotMessages');
  el.innerHTML = state.copilotHistory.map(m => {
    const isUser = m.role === 'user';
    return '<div style="display:flex;justify-content:' + (isUser ? 'flex-end' : 'flex-start') + ';margin-bottom:10px">'
      + '<div style="max-width:85%;padding:10px 14px;border-radius:' + (isUser ? '14px 14px 4px 14px' : '14px 14px 14px 4px')
      + ';background:' + (isUser ? 'var(--navy)' : '#F1F5F9') + ';color:' + (isUser ? '#fff' : 'var(--txt)')
      + ';font-size:13px;line-height:1.5;white-space:pre-wrap">' + escHtml(m.content) + '</div></div>';
  }).join('');
  el.scrollTop = el.scrollHeight;
}

export async function sendCopilotMsg() {
  const inp = document.getElementById('copilotInput');
  const msg = inp.value.trim();
  if (!msg) return;
  inp.value = '';
  addCopilotMsg('user', msg);

  const typing = document.getElementById('copilotTyping');
  typing.style.display = 'flex';

  try {
    const r = await fetch(API + '/copilot/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        message: msg,
        context: {
          step: state.currentStep,
          domain: state.currentDomain,
          category_selected: state.categorySelected,
          cart_items: Object.values(state._s1SelectedItems || {}).map(it => ({id: it.id, name: it.name, qty: it.qty, price: it.price})),
          cart_total: Object.values(state._s1SelectedItems || {}).reduce((s, it) => s + (it.qty || 0) * (it.price || 0), 0),
          unspsc_code: state._selectedUnspscCode || '',
        },
        history: state.copilotHistory.slice(-8)
      })
    });
    const data = await r.json();
    typing.style.display = 'none';
    addCopilotMsg('assistant', data.reply || 'Nie udalo sie przetworzyc zapytania.');

    if (data.actions && data.actions.length > 0) {
      data.actions.forEach(a => executeCopilotAction(a));
    }
    if (data.suggestions && data.suggestions.length > 0) {
      const sugEl = document.getElementById('copilotSuggestions');
      sugEl.innerHTML = data.suggestions.map(s =>
        '<button onclick="fillCopilotSuggestion(this.textContent)" style="padding:4px 10px;border:1px solid var(--gold);border-radius:12px;background:var(--gold-bg);color:var(--navy);font-size:11px;cursor:pointer;font-family:inherit">' + escHtml(s) + '</button>'
      ).join('');
      sugEl.style.display = 'flex';
    }
  } catch(e) {
    typing.style.display = 'none';
    addCopilotMsg('assistant', 'Blad polaczenia: ' + e.message);
  }
}

export function fillCopilotSuggestion(text) {
  document.getElementById('copilotInput').value = text;
  document.getElementById('copilotSuggestions').style.display = 'none';
  sendCopilotMsg();
}

export function executeCopilotAction(action) {
  if (!action || !action.action_type) return;
  // goStep and selectCategory are on window (set by bootstrap)
  switch(action.action_type) {
    case 'navigate':
      if (action.params.step != null && window.goStep) window.goStep(action.params.step);
      // Contract-expiry card: highlight which supplier brought user here.
      // Step 2 has no built-in filter input, so we surface the supplier name via
      // toast so the user knows who to look for in the grid.
      if (action.params.supplier_filter && typeof window.toast === 'function') {
        setTimeout(() => {
          window.toast('Sprawdz dostawce: ' + action.params.supplier_filter);
        }, 400);
      }
      break;
    case 'optimize':
      if (action.params.domain && window.selectCategory) {
        const btn = document.querySelector('[data-domain="'+action.params.domain+'"]');
        if (btn) { window.selectCategory(action.params.domain, btn); }
      }
      if (action.params.step != null && window.goStep) window.goStep(action.params.step);
      break;
    case 'filter':
      if (window.goStep) window.goStep(2);
      break;
    case 'add_to_cart':
      if (Array.isArray(action.params?.items) && window.s1AddToCartFromCopilot) {
        const added = window.s1AddToCartFromCopilot(action.params.items);
        if (added > 0 && typeof window.toast === 'function') {
          const names = action.params.items
            .map(i => i.qty + '\u00d7 ' + (i.name || i.id))
            .join(', ');
          window.toast('\ud83d\udecd\ufe0f Dodano: ' + names);
        }
      }
      break;
  }
}

export async function loadCopilotSuggestions() {
  try {
    const r = await fetch(API + '/copilot/suggestions?step=' + state.currentStep + '&domain=' + state.currentDomain);
    const data = await r.json();
    const sugEl = document.getElementById('copilotSuggestions');
    if (data.suggestions && data.suggestions.length) {
      sugEl.innerHTML = data.suggestions.map(s =>
        '<button onclick="fillCopilotSuggestion(this.textContent)" style="padding:4px 10px;border:1px solid var(--gold);border-radius:12px;background:var(--gold-bg);color:var(--navy);font-size:11px;cursor:pointer;font-family:inherit">' + escHtml(s) + '</button>'
      ).join('');
      sugEl.style.display = 'flex';
    }
  } catch(e) {}
}
