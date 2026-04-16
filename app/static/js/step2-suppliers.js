/**
 * step2-suppliers.js — Supplier list, auto-match, VIES, detail, certs, contacts, assessment
 */
import { $ } from './ui.js';
import { state } from './state.js';
import { DOMAIN_CFG } from './step3-optimizer.js';

export let _suppCurrentId = null;

export function loadStep2Suppliers() {
  if (!state.step2Loaded) {
    const suppContent = $('tab-suppliers');
    const target = $('step2SupplierContent');
    if (suppContent && target) {
      while (suppContent.firstChild) {
        target.appendChild(suppContent.firstChild);
      }
      state.step2Loaded = true;
    }
  }

  const autoPanel = $('step2AutoSuppliers');
  const autoGrid = $('step2AutoSuppGrid');
  const fullList = $('step2FullSupplierList');
  const itemTable = $('step2ItemSupplierTable');
  const selected = Object.values(state._s1SelectedItems);

  if (selected.length > 0 && state.currentS1Path === 'catalog') {
    const suppMap = {};
    const noSuppItems = [];
    let tableHtml = '<table style="width:100%;border-collapse:collapse;font-size:12px">'
      + '<thead><tr style="background:var(--navy);color:#fff;text-align:left">'
      + '<th style="padding:8px 10px;border-radius:6px 0 0 0">Produkt</th>'
      + '<th style="padding:8px 10px">Ilosc</th>'
      + '<th style="padding:8px 10px">Dostawca</th>'
      + '<th style="padding:8px 10px">Cena jedn.</th>'
      + '<th style="padding:8px 10px;border-radius:0 6px 0 0">Wartosc</th>'
      + '</tr></thead><tbody>';

    selected.forEach(it => {
      const supps = it.suppliers || [];
      if (supps.length === 0) {
        noSuppItems.push(it.name || it.id);
        tableHtml += '<tr style="border-bottom:1px solid var(--border)">'
          + '<td style="padding:6px 10px;font-weight:600">' + (it.name || it.id) + '</td>'
          + '<td style="padding:6px 10px">' + it.qty + ' ' + (it.unit || 'szt') + '</td>'
          + '<td style="padding:6px 10px;color:#ef4444"><em>Brak \u2014 wybierz recznie</em></td>'
          + '<td style="padding:6px 10px">\u2014</td>'
          + '<td style="padding:6px 10px">\u2014</td>'
          + '</tr>';
      } else if (supps.length === 1) {
        const s = supps[0];
        const up = s.unit_price || it.price;
        if (!suppMap[s.id]) suppMap[s.id] = { id: s.id, name: s.name, items: [] };
        suppMap[s.id].items.push({ name: it.name || it.id, qty: it.qty, unitPrice: up });
        tableHtml += '<tr style="border-bottom:1px solid var(--border)">'
          + '<td style="padding:6px 10px;font-weight:600">' + (it.name || it.id) + '</td>'
          + '<td style="padding:6px 10px">' + it.qty + ' ' + (it.unit || 'szt') + '</td>'
          + '<td style="padding:6px 10px"><span style="background:#059669;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">\u2713 ' + s.name + '</span></td>'
          + '<td style="padding:6px 10px;font-weight:600">' + up.toFixed(2) + ' PLN</td>'
          + '<td style="padding:6px 10px;font-weight:700">' + (up * it.qty).toFixed(2) + ' PLN</td>'
          + '</tr>';
      } else {
        const sorted = [...supps].sort((a,b) => (a.unit_price||it.price) - (b.unit_price||it.price));
        const best = sorted[0];
        const bestUp = best.unit_price || it.price;
        supps.forEach(s => {
          if (!suppMap[s.id]) suppMap[s.id] = { id: s.id, name: s.name, items: [] };
          suppMap[s.id].items.push({ name: it.name || it.id, qty: it.qty, unitPrice: s.unit_price || it.price });
        });
        const altNames = sorted.slice(1).map(s => s.name + ' (' + (s.unit_price||it.price).toFixed(2) + ')').join(', ');
        tableHtml += '<tr style="border-bottom:1px solid var(--border)">'
          + '<td style="padding:6px 10px;font-weight:600">' + (it.name || it.id) + '</td>'
          + '<td style="padding:6px 10px">' + it.qty + ' ' + (it.unit || 'szt') + '</td>'
          + '<td style="padding:6px 10px">'
          +   '<span style="background:#2563eb;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">\u2605 ' + best.name + '</span>'
          +   '<div style="font-size:10px;color:var(--txt2);margin-top:3px">Tez dostepne: ' + altNames + '</div>'
          + '</td>'
          + '<td style="padding:6px 10px;font-weight:600">' + bestUp.toFixed(2) + ' PLN</td>'
          + '<td style="padding:6px 10px;font-weight:700">' + (bestUp * it.qty).toFixed(2) + ' PLN</td>'
          + '</tr>';
      }
    });

    const totalValue = selected.reduce((sum, it) => {
      const supps = it.suppliers || [];
      const bestPrice = supps.length > 0
        ? Math.min(...supps.map(s => s.unit_price || it.price))
        : it.price;
      return sum + bestPrice * it.qty;
    }, 0);

    tableHtml += '</tbody>'
      + '<tfoot><tr style="background:#f8fafc;font-weight:700">'
      + '<td style="padding:8px 10px" colspan="4">RAZEM</td>'
      + '<td style="padding:8px 10px;font-size:14px;color:var(--navy)">' + totalValue.toFixed(2) + ' PLN</td>'
      + '</tr></tfoot></table>';
    itemTable.innerHTML = tableHtml;

    const suppliers = Object.values(suppMap);
    if (suppliers.length > 0) {
      $('step2AutoSuppCount').textContent = suppliers.length + ' dostawc' + (suppliers.length === 1 ? 'a' : '\u00f3w') + ' \u00b7 ' + selected.length + ' pozycji';
      autoGrid.innerHTML = suppliers.map(s => {
        const totalVal = s.items.reduce((sum, it) => sum + it.unitPrice * it.qty, 0);
        return '<div style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:12px">'
          + '<div style="display:flex;justify-content:space-between;align-items:center">'
          + '<div><strong style="font-size:13px;color:var(--navy)">' + s.name + '</strong>'
          + '<div style="font-size:10px;color:var(--txt2)">' + s.id + ' \u00b7 ' + s.items.length + ' poz.</div></div>'
          + '<div style="font-size:15px;font-weight:800;color:var(--navy)">' + totalVal.toFixed(2) + ' PLN</div>'
          + '</div></div>';
      }).join('');

      const noteEl = $('step2AutoNote');
      if (noSuppItems.length > 0) {
        noteEl.style.display = '';
        noteEl.style.background = '#fef2f2';
        noteEl.style.color = '#991b1b';
        noteEl.innerHTML = '\u26a0\ufe0f <b>Brak przypisanego dostawcy:</b> ' + noSuppItems.join(', ') + '. Wybierz dostawce recznie ponizej.';
        fullList.style.display = 'block';
      } else if (suppliers.length === 1) {
        noteEl.style.display = '';
        noteEl.style.background = '#f0fdf4';
        noteEl.style.color = '#166534';
        noteEl.innerHTML = '\u2705 Jedyny dostawca <b>' + suppliers[0].name + '</b> \u2014 mozesz przejsc od razu do optymalizacji.';
        fullList.style.display = 'none';
        $('step2HeaderDesc').textContent = 'Dostawca przypisany automatycznie z katalogu. Mozesz od razu przejsc do optymalizacji.';
      } else {
        noteEl.style.display = '';
        noteEl.style.background = '#eff6ff';
        noteEl.style.color = '#1e40af';
        noteEl.innerHTML = '\ud83d\udcca ' + suppliers.length + ' dostawcow \u2014 <b>optymalizator automatycznie rozdzieli zamowienie</b> wg najlepszej ceny, czasu dostawy i jakosci.';
        fullList.style.display = 'none';
        $('step2HeaderDesc').textContent = 'Dostawcy dopasowani z katalogu. Optymalizator rozdzieli zamowienie optymalnie.';
      }
      autoPanel.style.display = '';
    } else {
      autoPanel.style.display = 'none';
      fullList.style.display = 'block';
      $('step2HeaderDesc').textContent = 'Wybierz dostawcow z bazy lub dodaj nowych.';
    }
  } else {
    autoPanel.style.display = 'none';
    fullList.style.display = 'block';
    $('step2HeaderDesc').textContent = 'Wybierz dostawcow z bazy lub dodaj nowych.';
  }

  if (typeof suppLoadList === 'function') suppLoadList();
}

export async function suppLoadList() {
  const search = document.getElementById('suppSearch')?.value?.trim() || '';
  const domain = document.getElementById('suppDomainFilter')?.value || '';
  let url = '/api/v1/suppliers/?';
  if (search) url += 'search=' + encodeURIComponent(search) + '&';
  if (domain) url += 'domain=' + encodeURIComponent(domain) + '&';
  try {
    const res = await fetch(url);
    const data = await res.json();
    const suppliers = data.suppliers || data;
    const grid = document.getElementById('suppGrid');
    if (!suppliers.length) {
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:2rem 0">'
        + '<p style="color:var(--txt2);margin-bottom:16px">Brak dostawcow spelniajacych kryteria.</p>'
        + (search ? '<button class="btn btn-gold" onclick="suppGoToVies(\'' + search.replace(/'/g,"\\'") + '\')" style="padding:8px 20px">Dodaj nowego dostawce &rarr; VIES</button>' : '')
        + '</div>';
      return;
    }
    grid.innerHTML = suppliers.map(s => {
      const certCount = (s.certificates || []).length;
      const score = s.self_assessment ? s.self_assessment.overall_score.toFixed(1) : '\u2014';
      const domains = (s.domains || []).map(d => '<span style="background:#e3f2fd;color:#1565c0;padding:2px 6px;border-radius:4px;font-size:12px">' + d + '</span>').join(' ');
      const vatBadge = s.vat_valid ? '<span style="color:#2e7d32;font-weight:600" title="VIES zweryfikowany">&#10003; VAT</span>' : '<span style="color:#999">VAT?</span>';
      return '<div onclick="suppShowDetail(\'' + s.supplier_id + '\')" style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;cursor:pointer;transition:box-shadow .2s" onmouseover="this.style.boxShadow=\'0 2px 8px rgba(0,0,0,.12)\'" onmouseout="this.style.boxShadow=\'none\'">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><strong style="font-size:1.05rem">' + s.name + '</strong>' + vatBadge + '</div>'
        + '<div style="color:var(--txt2);font-size:12px;margin-bottom:8px">NIP: ' + (s.nip || '\u2014') + ' | ' + (s.country_code || 'PL') + '</div>'
        + '<div style="margin-bottom:8px">' + domains + '</div>'
        + '<div style="display:flex;gap:16px;font-size:12px;color:var(--txt2)">'
        + '<span title="Certyfikaty">&#128196; ' + certCount + ' cert.</span>'
        + '<span title="Samoocena">&#9733; ' + score + '</span>'
        + '<span title="Kontakty">&#128100; ' + (s.contacts || []).length + '</span>'
        + '</div></div>';
    }).join('');
  } catch (e) {
    const grid = document.getElementById('suppGrid');
    if (grid) grid.innerHTML = '<p style="color:#c62828">Blad ladowania listy: ' + e.message + '</p>';
  }
}

export function suppShowAddForm() {
  document.getElementById('suppListView').style.display = 'none';
  document.getElementById('suppAddForm').style.display = 'block';
  document.getElementById('suppNipInput').value = '';
  document.getElementById('suppNameInput').value = '';
  document.getElementById('suppViesResult').style.display = 'none';
}
export function suppHideAddForm() {
  document.getElementById('suppAddForm').style.display = 'none';
  document.getElementById('suppListView').style.display = 'block';
}

export async function suppViesLookup() {
  const nip = document.getElementById('suppNipInput').value.trim().replace(/[\s-]/g, '');
  if (nip.length !== 10) { alert('NIP musi miec 10 cyfr'); return; }
  const box = document.getElementById('suppViesResult');
  box.style.display = 'block';
  box.innerHTML = '<em>Sprawdzanie w VIES...</em>';
  try {
    const res = await fetch('/api/v1/suppliers/vies-lookup', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({country_code: 'PL', vat_number: nip})
    });
    const data = await res.json();
    if (data.valid) {
      box.style.background = '#e8f5e9';
      box.innerHTML = '<strong style="color:#2e7d32">&#10003; Podmiot aktywny w VIES</strong><br><strong>' + (data.name || '') + '</strong><br>' + (data.address || '') + '<br><span style="font-size:11px;color:var(--txt2)">Data zapytania: ' + (data.request_date || '') + '</span>';
      if (data.name && !document.getElementById('suppNameInput').value) {
        document.getElementById('suppNameInput').value = data.name;
      }
    } else {
      box.style.background = '#fce4ec';
      box.innerHTML = '<strong style="color:#c62828">&#10007; NIP nieaktywny lub nieznaleziony w VIES</strong>';
    }
  } catch (e) {
    box.style.background = '#fff3e0';
    box.innerHTML = '<strong style="color:#e65100">&#9888; VIES niedostepny</strong><br><span style="font-size:12px">Mozesz kontynuowac recznie.</span>';
  }
}

export async function suppCreateFromNip() {
  const nip = document.getElementById('suppNipInput').value.trim().replace(/[\s-]/g, '');
  if (nip.length !== 10) { alert('Podaj poprawny NIP (10 cyfr)'); return; }
  const nameOverride = document.getElementById('suppNameInput').value.trim() || undefined;
  const checks = document.querySelectorAll('#suppDomainChecks input:checked');
  const domains = Array.from(checks).map(c => c.value);
  try {
    const res = await fetch('/api/v1/suppliers/', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({nip, name_override: nameOverride, domains})
    });
    if (!res.ok) { const err = await res.json(); alert('Blad: ' + (err.detail || JSON.stringify(err))); return; }
    const data = await res.json();
    suppHideAddForm();
    suppLoadList();
    suppShowDetail(data.supplier_id);
  } catch (e) { alert('Blad tworzenia dostawcy: ' + e.message); }
}

export async function suppShowDetail(id) {
  _suppCurrentId = id;
  document.getElementById('suppListView').style.display = 'none';
  document.getElementById('suppAddForm').style.display = 'none';
  document.getElementById('suppDetailView').style.display = 'block';
  const box = document.getElementById('suppDetailContent');
  box.innerHTML = '<em>Ladowanie...</em>';
  try {
    const res = await fetch('/api/v1/suppliers/' + id);
    if (!res.ok) throw new Error('Nie znaleziono');
    const s = await res.json();
    const vatBadge = s.vat_valid
      ? '<span style="background:#e8f5e9;color:#2e7d32;padding:3px 8px;border-radius:4px;font-weight:600">&#10003; VIES aktywny</span>'
      : '<span style="background:#fce4ec;color:#c62828;padding:3px 8px;border-radius:4px">Niezweryfikowany</span>';

    let certsHtml = '<p style="color:var(--txt2);font-size:13px">Brak certyfikatow</p>';
    if (s.certificates && s.certificates.length) {
      certsHtml = '<table style="width:100%;border-collapse:collapse;font-size:13px"><tr style="background:#f5f5f5"><th style="padding:6px;text-align:left">Typ</th><th>Wystawca</th><th>Waznosc do</th><th>Status</th><th></th></tr>'
        + s.certificates.map(c => {
          const exp = new Date(c.expiry_date);
          const now = new Date();
          const daysLeft = Math.ceil((exp - now) / 86400000);
          let statusColor = '#2e7d32', statusText = 'Aktywny';
          if (daysLeft < 0) { statusColor = '#c62828'; statusText = 'Wygasly'; }
          else if (daysLeft < 90) { statusColor = '#e65100'; statusText = daysLeft + ' dni'; }
          return '<tr style="border-bottom:1px solid var(--border)"><td style="padding:6px;font-weight:600">' + c.cert_type + '</td><td style="padding:6px">' + (c.issuer || '\u2014') + '</td><td style="padding:6px">' + c.expiry_date + '</td><td style="padding:6px;color:' + statusColor + ';font-weight:600">' + statusText + '</td><td style="padding:6px"><button onclick="suppRemoveCert(\'' + id + '\',\'' + c.cert_id + '\')" style="color:#c62828;background:none;border:none;cursor:pointer" title="Usun">&#10005;</button></td></tr>';
        }).join('')
        + '</table>';
    }

    let contactsHtml = '<p style="color:var(--txt2);font-size:13px">Brak kontaktow</p>';
    if (s.contacts && s.contacts.length) {
      contactsHtml = '<table style="width:100%;border-collapse:collapse;font-size:13px"><tr style="background:#f5f5f5"><th style="padding:6px;text-align:left">Imie i nazwisko</th><th>Rola</th><th>Email</th><th>Telefon</th><th></th></tr>'
        + s.contacts.map(c => '<tr style="border-bottom:1px solid var(--border)"><td style="padding:6px">' + c.name + (c.is_primary ? ' <span style="color:#1565c0;font-size:12px">&#9733; Glowny</span>' : '') + '</td><td style="padding:6px">' + c.role + '</td><td style="padding:6px"><a href="mailto:' + c.email + '">' + c.email + '</a></td><td style="padding:6px">' + (c.phone || '\u2014') + '</td><td style="padding:6px"><button onclick="suppRemoveContact(\'' + id + '\',\'' + c.contact_id + '\')" style="color:#c62828;background:none;border:none;cursor:pointer" title="Usun">&#10005;</button></td></tr>').join('')
        + '</table>';
    }

    let assessHtml = '';
    if (s.self_assessment) {
      const sa = s.self_assessment;
      const cats = sa.category_scores || {};
      assessHtml = '<div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:8px"><div><strong>' + sa.overall_score.toFixed(2) + '</strong><span style="color:var(--txt2);font-size:12px"> / 5.0 ogolna</span></div>'
        + Object.entries(cats).map(([k,v]) => '<div style="font-size:13px"><span style="color:var(--txt2)">' + k + ':</span> <strong>' + v.toFixed(2) + '</strong></div>').join('') + '</div>';
    } else {
      assessHtml = '<button onclick="suppShowAssessmentForm(\'' + id + '\')" style="padding:6px 12px;background:var(--purple);color:#fff;border:none;border-radius:var(--radius);cursor:pointer;font-size:13px">Wypelnij samoocene</button>';
    }

    box.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;margin-bottom:1.5rem"><div><h3 style="margin:0 0 .25rem">' + s.name + '</h3><div style="color:var(--txt2);font-size:13px">NIP: ' + (s.nip || '\u2014') + ' | ' + (s.country_code || 'PL') + ' | ID: ' + s.supplier_id + '</div>' + (s.address ? '<div style="font-size:13px;margin-top:4px">' + s.address + '</div>' : '') + (s.website ? '<div style="font-size:13px"><a href="' + s.website + '" target="_blank">' + s.website + '</a></div>' : '') + '</div><div style="display:flex;gap:8px;align-items:center">' + vatBadge + '<button onclick="suppDelete(\'' + id + '\')" style="padding:4px 10px;background:#fce4ec;color:#c62828;border:1px solid #ef9a9a;border-radius:var(--radius);cursor:pointer;font-size:12px">Usun</button></div></div>'
      + '<div style="display:flex;gap:8px;margin-bottom:1.5rem;flex-wrap:wrap">' + (s.domains || []).map(d => '<span class="pill" style="background:#DBEAFE;color:#1E40AF">' + d + '</span>').join('') + '</div>'
      + '<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:16px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h4 style="margin:0">Certyfikaty</h4><button onclick="suppShowCertForm(\'' + id + '\')" style="padding:3px 8px;background:var(--accent);color:#fff;border:none;border-radius:var(--radius);cursor:pointer;font-size:12px">+ Dodaj</button></div>' + certsHtml + '<div id="suppCertForm-' + id + '" style="display:none;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)"></div></div>'
      + '<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:16px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h4 style="margin:0">Osoby kontaktowe</h4><button onclick="suppShowContactForm(\'' + id + '\')" style="padding:3px 8px;background:var(--accent);color:#fff;border:none;border-radius:var(--radius);cursor:pointer;font-size:12px">+ Dodaj</button></div>' + contactsHtml + '<div id="suppContactForm-' + id + '" style="display:none;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)"></div></div>'
      + '<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:16px"><h4 style="margin:0 0 .5rem">Samoocena dostawcy</h4>' + assessHtml + '<div id="suppAssessForm-' + id + '" style="display:none;margin-top:12px"></div></div>'
      + '<div style="background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:16px"><div style="display:flex;justify-content:space-between;align-items:center"><h4 style="margin:0">Optymalizator</h4><button onclick="suppRunOptimization(\'' + id + '\')" style="padding:5px 12px;background:var(--ok);color:#fff;border:none;border-radius:var(--radius);cursor:pointer;font-weight:600;font-size:13px">&#9654; Uruchom optymalizacje</button></div><div id="suppOptResult-' + id + '" style="margin-top:12px"></div></div>';
  } catch (e) { box.innerHTML = '<p style="color:#c62828">Blad: ' + e.message + '</p>'; }
}

export function suppBackToList() {
  document.getElementById('suppDetailView').style.display = 'none';
  document.getElementById('suppListView').style.display = 'block';
  suppLoadList();
}

export async function suppDelete(id) {
  if (!confirm('Na pewno usunac tego dostawce?')) return;
  await fetch('/api/v1/suppliers/' + id, {method: 'DELETE'});
  suppBackToList();
}

export function suppShowCertForm(id) {
  const box = document.getElementById('suppCertForm-' + id);
  box.style.display = 'block';
  box.innerHTML = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><select id="certType-' + id + '" style="padding:6px;border:1px solid var(--border);border-radius:var(--radius)"><option value="iso_9001">ISO 9001</option><option value="iso_14001">ISO 14001</option><option value="iatf_16949">IATF 16949</option><option value="iso_45001">ISO 45001</option><option value="iso_50001">ISO 50001</option><option value="emas">EMAS</option><option value="other">Inny</option></select><input id="certIssuer-' + id + '" placeholder="Wystawca" style="padding:6px;border:1px solid var(--border);border-radius:var(--radius)"><input id="certIssueDate-' + id + '" type="date" style="padding:6px;border:1px solid var(--border);border-radius:var(--radius)"><input id="certExpDate-' + id + '" type="date" style="padding:6px;border:1px solid var(--border);border-radius:var(--radius)"></div><div style="margin-top:8px;display:flex;gap:8px"><button onclick="suppAddCert(\'' + id + '\')" style="padding:6px 12px;background:var(--accent);color:#fff;border:none;border-radius:var(--radius);cursor:pointer">Zapisz</button><button onclick="document.getElementById(\'suppCertForm-' + id + '\').style.display=\'none\'" style="padding:6px 12px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);cursor:pointer">Anuluj</button></div>';
}

export async function suppAddCert(id) {
  const body = {
    cert_type: document.getElementById('certType-' + id).value,
    issuer: document.getElementById('certIssuer-' + id).value || 'N/A',
    issue_date: document.getElementById('certIssueDate-' + id).value || '2024-01-01',
    expiry_date: document.getElementById('certExpDate-' + id).value || '2026-12-31'
  };
  const res = await fetch('/api/v1/suppliers/' + id + '/certificates', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  if (res.ok) suppShowDetail(id); else alert('Blad dodawania certyfikatu');
}

export async function suppRemoveCert(suppId, certId) {
  if (!confirm('Usunac certyfikat?')) return;
  await fetch('/api/v1/suppliers/' + suppId + '/certificates/' + certId, {method: 'DELETE'});
  suppShowDetail(suppId);
}

export function suppShowContactForm(id) {
  const box = document.getElementById('suppContactForm-' + id);
  box.style.display = 'block';
  box.innerHTML = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><input id="conName-' + id + '" placeholder="Imie i nazwisko" style="padding:6px;border:1px solid var(--border);border-radius:var(--radius)"><select id="conRole-' + id + '" style="padding:6px;border:1px solid var(--border);border-radius:var(--radius)"><option value="sales">Sales</option><option value="key_account">Key Account</option><option value="quality">Quality</option><option value="logistics">Logistics</option><option value="management">Management</option><option value="other">Inny</option></select><input id="conEmail-' + id + '" placeholder="Email" type="email" style="padding:6px;border:1px solid var(--border);border-radius:var(--radius)"><input id="conPhone-' + id + '" placeholder="Telefon" style="padding:6px;border:1px solid var(--border);border-radius:var(--radius)"></div><div style="margin-top:8px;display:flex;gap:8px"><button onclick="suppAddContact(\'' + id + '\')" style="padding:6px 12px;background:var(--accent);color:#fff;border:none;border-radius:var(--radius);cursor:pointer">Zapisz</button><button onclick="document.getElementById(\'suppContactForm-' + id + '\').style.display=\'none\'" style="padding:6px 12px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);cursor:pointer">Anuluj</button></div>';
}

export async function suppAddContact(id) {
  const body = { name: document.getElementById('conName-' + id).value, role: document.getElementById('conRole-' + id).value, email: document.getElementById('conEmail-' + id).value, phone: document.getElementById('conPhone-' + id).value || null, is_primary: false };
  if (!body.name || !body.email) { alert('Imie i email sa wymagane'); return; }
  const res = await fetch('/api/v1/suppliers/' + id + '/contacts', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
  if (res.ok) suppShowDetail(id); else alert('Blad dodawania kontaktu');
}

export async function suppRemoveContact(suppId, conId) {
  if (!confirm('Usunac kontakt?')) return;
  await fetch('/api/v1/suppliers/' + suppId + '/contacts/' + conId, {method: 'DELETE'});
  suppShowDetail(suppId);
}

export async function suppShowAssessmentForm(id) {
  const box = document.getElementById('suppAssessForm-' + id);
  box.style.display = 'block';
  box.innerHTML = '<em>Ladowanie pytan...</em>';
  try {
    const res = await fetch('/api/v1/suppliers/assessment/questions');
    const data = await res.json();
    const questions = data.questions || data;
    box.innerHTML = '<div style="font-size:13px">' + questions.map((q, i) => '<div style="margin-bottom:12px;padding:8px;background:#fafafa;border-radius:var(--radius)"><div style="margin-bottom:.25rem"><strong>' + (q.question_id || 'Q' + (i+1)) + '.</strong> ' + (q.question_text || q.question || '') + ' <span style="color:var(--txt2);font-size:11px">[' + q.category + ']</span></div><div style="display:flex;gap:.3rem;align-items:center">' + [1,2,3,4,5].map(n => '<label style="cursor:pointer"><input type="radio" name="assess-' + id + '-' + (q.question_id || i) + '" value="' + n + '"> ' + n + '</label>').join('') + '</div></div>').join('') + '</div><button onclick="suppSubmitAssessment(\'' + id + '\', ' + JSON.stringify(questions).replace(/"/g, '&quot;') + ')" style="padding:8px 16px;background:var(--purple);color:#fff;border:none;border-radius:var(--radius);cursor:pointer;font-weight:600;margin-top:8px">Wyslij samoocene</button>';
  } catch (e) { box.innerHTML = '<p style="color:#c62828">Blad: ' + e.message + '</p>'; }
}

export async function suppSubmitAssessment(id, questions) {
  const answers = questions.map((q, i) => {
    const qid = q.question_id || ('Q' + (i + 1));
    const checked = document.querySelector('input[name="assess-' + id + '-' + qid + '"]:checked');
    return { question_id: qid, score: checked ? parseInt(checked.value) : 3, comment: '' };
  });
  try {
    const res = await fetch('/api/v1/suppliers/' + id + '/assessment', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({supplier_id: id, answers}) });
    if (res.ok) suppShowDetail(id); else { const err = await res.json(); alert('Blad: ' + (err.detail || '')); }
  } catch (e) { alert('Blad wysylania: ' + e.message); }
}

export async function suppRunOptimization(id) {
  const box = document.getElementById('suppOptResult-' + id);
  box.innerHTML = '<em>Uruchamianie optymalizacji...</em>';
  try {
    const res = await fetch('/api/v1/suppliers/' + id + '/run-optimization', {method: 'POST'});
    const data = await res.json();
    if (data.error) { box.innerHTML = '<p style="color:#c62828">' + data.error + '</p>'; return; }
    const r = data.result || data;
    box.innerHTML = '<div style="background:#e8f5e9;padding:12px;border-radius:var(--radius);font-size:13px"><strong style="color:#2e7d32">Optymalizacja zakonczona</strong><br>Status: ' + (r.status || 'ok') + '<br>Koszt: <strong>' + (r.total_cost || 0).toFixed(2) + ' PLN</strong> | Czas: <strong>' + (r.total_time || 0).toFixed(1) + ' h</strong> | Compliance: <strong>' + ((r.avg_compliance || 0) * 100).toFixed(0) + '%</strong> | ESG: <strong>' + ((r.avg_esg || 0) * 100).toFixed(0) + '%</strong></div>';
  } catch (e) { box.innerHTML = '<p style="color:#c62828">Blad: ' + e.message + '</p>'; }
}

export function suppGoToVies(searchText) {
  suppShowAddForm();
  const nipInput = document.getElementById('suppNipInput');
  if (nipInput) {
    const cleaned = searchText.replace(/[^0-9]/g, '');
    if (cleaned.length >= 7) nipInput.value = cleaned;
  }
  const form = document.getElementById('suppAddForm');
  if (form) form.scrollIntoView({behavior:'smooth'});
}
