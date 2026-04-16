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
  w.style.display = state.copilotOpen ? 'flex' : 'none';
  fab.style.display = state.copilotOpen ? 'none' : 'flex';
  if (state.copilotOpen && state.copilotHistory.length === 0) {
    loadCopilotSuggestions();
    addCopilotMsg('assistant', 'Witaj! Jestem Twoj asystent zakupowy. Wpisz pytanie, np.:\n\n- "Szukaj laptopa na Allegro"\n- "Pokaz katalog klocki hamulcowe"\n- "Porownaj dostawcow dla tej kategorii"\n- "Jak zlozyc zamowienie?"\n\nJak moge Ci pomoc?');
  }
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
