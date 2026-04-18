/**
 * step5-monitoring.js — Process mining (DFG), what-if scenarios, alerts, risk, predictive
 */
import { $, pct } from './ui.js';
import { API, safeFetchJson } from './api.js';
import { state } from './state.js';

function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

const STATUS_LABELS = {
  draft:'Szkic', pending_approval:'Oczekuje na zatwierdzenie', approved:'Zatwierdzone',
  po_generated:'PO wygenerowane', confirmed:'Potwierdzone', in_delivery:'W dostawie',
  delivered:'Dostarczone', cancelled:'Anulowane'
};

export function switchMonitorSection(id) {
  document.querySelectorAll('.monitor-section').forEach(s => s.classList.toggle('active', s.id === id));
  // Update buttons
  const parent = document.querySelector('#step-5 .subtab-btn')?.parentElement;
  if (parent) {
    parent.querySelectorAll('.subtab-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('onclick')?.includes(id));
    });
  }
}

/* Add CSS for monitor sections */
document.head.insertAdjacentHTML('beforeend', '<style>.monitor-section{display:none}.monitor-section.active{display:block}</style>');

/* Add CSS for monitor sections */
document.head.insertAdjacentHTML('beforeend', '<style>.monitor-section{display:none}.monitor-section.active{display:block}</style>');

export function switchMonSource(source) {
  state._monSource = source;
  // Update toggle buttons
  document.querySelectorAll('#monSourceToggle button').forEach(b => {
    b.classList.toggle('active', b.getAttribute('onclick')?.includes("'" + source + "'"));
  });
  // Show/hide selectors
  document.getElementById('monSupplierSelector').style.display = source === 'supplier' ? '' : 'none';
  document.getElementById('monDeptSelector').style.display = source === 'department' ? '' : 'none';
  // Update info text
  const info = document.getElementById('monSourceInfo');
  if (source === 'demo') {
    info.textContent = 'Dane demonstracyjne — przykladowe procesy P2P';
  } else if (source === 'supplier') {
    info.textContent = 'Wybierz dostawce aby zobaczyc jego postepowania i zamowienia';
    loadMonSupplierList();
  } else {
    info.textContent = 'Wybierz dzial aby zobaczyc procesy zakupowe i budzet';
  }
  // Show context panel
  document.getElementById('monContextPanel').style.display = source !== 'demo' ? '' : 'none';
  if (source === 'demo') { loadAlertsDemo(); }
}

export async function loadMonSupplierList() {
  if (state._monSuppliers.length > 0) return; // already loaded
  try {
    const r = await fetch('/api/v1/suppliers/');
    const data = await r.json();
    const suppliers = data.suppliers || data || [];
    state._monSuppliers = suppliers;
    const sel = document.getElementById('monSupplierSelect');
    sel.innerHTML = '<option value="">-- Wybierz dostawce --</option>';
    suppliers.forEach(s => {
      sel.innerHTML += '<option value="' + s.id + '">' + s.name + ' (' + s.id + ')</option>';
    });
  } catch(e) {
    console.error('Failed to load suppliers for monitoring:', e);
  }
}

export async function loadMonitoringForSource() {
  const panel = document.getElementById('monContextContent');
  const ctx = document.getElementById('monContextPanel');

  if (state._monSource === 'supplier') {
    const suppId = document.getElementById('monSupplierSelect').value;
    if (!suppId) { ctx.style.display = 'none'; return; }
    ctx.style.display = '';
    panel.innerHTML = '<div style="color:var(--txt2);font-size:13px;padding:12px">Ladowanie danych dostawcy...</div>';

    try {
      // Load supplier details + orders
      const [suppRes, ordRes, aucRes] = await Promise.all([
        fetch('/api/v1/suppliers/' + suppId).then(r => r.json()),
        fetch('/api/v1/buying/orders?supplier=' + suppId).then(r => r.json()).catch(() => ({orders:[]})),
        fetch('/api/v1/auctions?supplier=' + suppId).then(r => r.json()).catch(() => ({auctions:[]})),
      ]);
      const supp = suppRes.supplier || suppRes;
      const orders = ordRes.orders || [];
      const auctions = aucRes.auctions || [];

      let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
        + '<div><h3 style="margin:0;font-size:16px;color:var(--navy)">' + (supp.name || suppId) + '</h3>'
        + '<div style="font-size:11px;color:var(--txt2)">' + (supp.nip || '') + ' | ' + (supp.city || '') + ', ' + (supp.country || 'PL') + '</div></div>'
        + '<div style="display:flex;gap:8px">'
        + '<div style="text-align:center;padding:8px 16px;background:var(--gold-bg);border-radius:8px"><div style="font-size:18px;font-weight:700;color:var(--gold)">' + orders.length + '</div><div style="font-size:10px;color:var(--txt2)">Zamowien</div></div>'
        + '<div style="text-align:center;padding:8px 16px;background:#EEF2FF;border-radius:8px"><div style="font-size:18px;font-weight:700;color:#4F46E5">' + auctions.length + '</div><div style="font-size:10px;color:var(--txt2)">Postepowania</div></div>'
        + '</div></div>';

      // Orders table
      if (orders.length > 0) {
        html += '<div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--navy);margin:12px 0 6px">Zamowienia</div>';
        html += '<table style="width:100%;border-collapse:collapse;font-size:11px"><thead><tr style="background:#F8FAFC"><th style="padding:6px 8px;text-align:left">ID</th><th>Data</th><th>Status</th><th style="text-align:right">Wartosc</th></tr></thead><tbody>';
        orders.slice(0, 10).forEach(o => {
          html += '<tr style="border-bottom:1px solid #F1F5F9"><td style="padding:6px 8px;font-weight:600">' + o.order_id + '</td>'
            + '<td>' + new Date(o.created_at).toLocaleDateString('pl') + '</td>'
            + '<td><span class="ob-status-badge ' + o.status + '">' + (STATUS_LABELS[o.status] || o.status) + '</span></td>'
            + '<td style="text-align:right;font-weight:600">' + (o.total || 0).toLocaleString('pl') + ' PLN</td></tr>';
        });
        html += '</tbody></table>';
      }

      // Auctions
      if (auctions.length > 0) {
        html += '<div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--navy);margin:12px 0 6px">Postepowania / Aukcje</div>';
        html += '<table style="width:100%;border-collapse:collapse;font-size:11px"><thead><tr style="background:#F8FAFC"><th style="padding:6px 8px;text-align:left">Tytul</th><th>Status</th><th>Typ</th><th style="text-align:right">Oferty</th></tr></thead><tbody>';
        auctions.slice(0, 10).forEach(a => {
          html += '<tr style="border-bottom:1px solid #F1F5F9"><td style="padding:6px 8px;font-weight:600">' + a.title + '</td>'
            + '<td>' + a.status + '</td><td>' + a.auction_type + '</td>'
            + '<td style="text-align:right">' + (a.total_bids || 0) + '</td></tr>';
        });
        html += '</tbody></table>';
      }

      if (orders.length === 0 && auctions.length === 0) {
        html += '<div style="text-align:center;padding:20px;color:var(--txt2);font-size:13px">Brak historii zamowien i postepowań dla tego dostawcy.</div>';
      }

      panel.innerHTML = html;
      document.getElementById('monSourceInfo').textContent = 'Dostawca: ' + (supp.name || suppId);
    } catch(e) {
      panel.innerHTML = '<div style="color:var(--err);font-size:13px;padding:12px">Blad: ' + e.message + '</div>';
    }

  } else if (state._monSource === 'department') {
    const dept = document.getElementById('monDeptSelect').value;
    if (!dept) { ctx.style.display = 'none'; return; }
    ctx.style.display = '';
    panel.innerHTML = '<div style="color:var(--txt2);font-size:13px;padding:12px">Ladowanie danych dzialu...</div>';

    try {
      // Load orders + projects for department
      const [ordRes, projRes] = await Promise.all([
        fetch('/api/v1/buying/orders').then(r => r.json()).catch(() => ({orders:[]})),
        fetch('/api/v1/projects?department=' + encodeURIComponent(dept)).then(r => r.json()).catch(() => ({projects:[]})),
      ]);
      const orders = ordRes.orders || [];
      const projects = projRes.projects || [];

      // Calculate department KPIs
      const totalSpend = orders.reduce((s, o) => s + (o.total || 0), 0);
      const activeOrders = orders.filter(o => !['delivered','cancelled'].includes(o.status));
      const budgetUsed = totalSpend;
      const deptBudgets = {
        zakupy: 500000, logistyka: 300000, it: 250000, produkcja: 800000,
        marketing: 150000, finanse: 100000, hr: 80000
      };
      const budget = deptBudgets[dept] || 200000;
      const budgetPct = Math.min(100, (budgetUsed / budget * 100)).toFixed(1);
      const budgetColor = budgetPct > 80 ? 'var(--err)' : budgetPct > 60 ? 'var(--warn)' : 'var(--ok)';

      let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
        + '<h3 style="margin:0;font-size:16px;color:var(--navy)">Dzial: ' + dept.charAt(0).toUpperCase() + dept.slice(1) + '</h3></div>';

      // Budget bar
      html += '<div style="margin-bottom:16px">'
        + '<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px"><span style="font-weight:700;color:var(--navy)">Budzet roczny</span><span style="color:' + budgetColor + ';font-weight:700">' + budgetPct + '% wykorzystane</span></div>'
        + '<div style="background:#E2E8F0;border-radius:4px;height:8px;overflow:hidden"><div style="background:' + budgetColor + ';height:100%;width:' + budgetPct + '%;border-radius:4px;transition:width .5s"></div></div>'
        + '<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--txt2);margin-top:2px"><span>Wydano: ' + budgetUsed.toLocaleString('pl') + ' PLN</span><span>Limit: ' + budget.toLocaleString('pl') + ' PLN</span></div>'
        + '</div>';

      // KPI row
      html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px">'
        + '<div style="background:#F8FAFC;border-radius:8px;padding:10px;text-align:center"><div style="font-size:18px;font-weight:700;color:var(--navy)">' + orders.length + '</div><div style="font-size:10px;color:var(--txt2)">Zamowien</div></div>'
        + '<div style="background:#F8FAFC;border-radius:8px;padding:10px;text-align:center"><div style="font-size:18px;font-weight:700;color:var(--gold)">' + activeOrders.length + '</div><div style="font-size:10px;color:var(--txt2)">Aktywnych</div></div>'
        + '<div style="background:#F8FAFC;border-radius:8px;padding:10px;text-align:center"><div style="font-size:18px;font-weight:700;color:#6366F1">' + projects.length + '</div><div style="font-size:10px;color:var(--txt2)">Projektow</div></div>'
        + '<div style="background:#F8FAFC;border-radius:8px;padding:10px;text-align:center"><div style="font-size:18px;font-weight:700;color:' + budgetColor + '">' + (budget - budgetUsed > 0 ? (budget - budgetUsed).toLocaleString('pl') : '0') + '</div><div style="font-size:10px;color:var(--txt2)">Dostepny budzet PLN</div></div>'
        + '</div>';

      // Active projects
      if (projects.length > 0) {
        html += '<div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--navy);margin:8px 0 6px">Projekty zakupowe</div>';
        html += '<table style="width:100%;border-collapse:collapse;font-size:11px"><thead><tr style="background:#F8FAFC"><th style="padding:6px 8px;text-align:left">Tytul</th><th>Status</th><th>Budzet</th></tr></thead><tbody>';
        projects.slice(0, 8).forEach(p => {
          html += '<tr style="border-bottom:1px solid #F1F5F9"><td style="padding:6px 8px;font-weight:600">' + (p.title || p.project_id) + '</td>'
            + '<td>' + p.status + '</td>'
            + '<td style="text-align:right">' + (p.budget_limit || 0).toLocaleString('pl') + ' PLN</td></tr>';
        });
        html += '</tbody></table>';
      }

      // Active orders
      if (activeOrders.length > 0) {
        html += '<div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--navy);margin:12px 0 6px">Aktywne zamowienia</div>';
        html += '<table style="width:100%;border-collapse:collapse;font-size:11px"><thead><tr style="background:#F8FAFC"><th style="padding:6px 8px;text-align:left">ID</th><th>Status</th><th style="text-align:right">Wartosc</th></tr></thead><tbody>';
        activeOrders.slice(0, 8).forEach(o => {
          html += '<tr style="border-bottom:1px solid #F1F5F9"><td style="padding:6px 8px;font-weight:600">' + o.order_id + '</td>'
            + '<td><span class="ob-status-badge ' + o.status + '">' + (STATUS_LABELS[o.status] || o.status) + '</span></td>'
            + '<td style="text-align:right;font-weight:600">' + (o.total || 0).toLocaleString('pl') + ' PLN</td></tr>';
        });
        html += '</tbody></table>';
      }

      panel.innerHTML = html;
      document.getElementById('monSourceInfo').textContent = 'Dzial: ' + dept.charAt(0).toUpperCase() + dept.slice(1) + ' | Budzet: ' + budgetPct + '% wykorzystane';
    } catch(e) {
      panel.innerHTML = '<div style="color:var(--err);font-size:13px;padding:12px">Blad: ' + e.message + '</div>';
    }
  }
}

/* ─── CIF Upload + UNSPSC Classification ─── */


/* ═══ PROCESS MINING ═══ */
export async function loadPMDemo() {
  try {
    $('pmBottlenecksContent').innerHTML = '<div style="color:var(--gold)">Ladowanie...</div>';
    state.pmReport = await safeFetchJson(API + '/process-digging/demo/full-report?top_n=10');
    renderDFG(state.pmReport, state.dfgView);
    renderPMBottlenecks(state.pmReport.bottlenecks);
    renderPMConformance(state.pmReport.conformance);
    renderPMVariants(state.pmReport.variants);
    renderPMRework(state.pmReport.rework);
    renderPMSLA(state.pmReport.sla_monitor);
    renderPMAnomalies(state.pmReport.anomalies);
  } catch(e) {
    $('pmBottlenecksContent').innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>';
  }
}

export function switchDFGView(view) {
  state.dfgView = view;
  $('dfgFreqBtn').classList.toggle('active', view==='frequency');
  $('dfgPerfBtn').classList.toggle('active', view==='performance');
  if (state.pmReport) renderDFG(state.pmReport, view);
}

export function renderDFG(report, type) {
  const dfgData = type === 'frequency' ? report.dfg_frequency : report.dfg_performance;
  if (!dfgData || !dfgData.edges || dfgData.edges.length === 0) {
    $('dfg-container').innerHTML = '<div style="padding:40px;text-align:center;color:var(--txt2)">Brak danych DFG</div>';
    return;
  }

  // Build node set with event counts
  const nodeCounts = {};
  dfgData.edges.forEach(e => {
    nodeCounts[e.source] = (nodeCounts[e.source] || 0) + (e.frequency || 1);
    nodeCounts[e.target] = (nodeCounts[e.target] || 0) + (e.frequency || 1);
  });
  const maxCount = Math.max(...Object.values(nodeCounts), 1);

  const nodes = Object.keys(nodeCounts).map(id => ({
    data: { id, label: id.replace(/_/g,' '), count: nodeCounts[id], size: 30 + (nodeCounts[id]/maxCount)*40 }
  }));

  // Edge weights + bottleneck highlighting.
  // `bottleneck_transitions` from /process-digging comes with p95_hours —
  // treat top-5 slowest (or p95 > 48h) as red; next tier as amber. This is
  // overlayed on top of the perf-based coloring so bottleneck edges are
  // visible even in frequency view (where perf thresholds don't apply).
  const bottleneckKey = (s, t) => `${s}||${t}`;
  const bottlenecks = (report.bottlenecks && report.bottlenecks.bottleneck_transitions) || [];
  const criticalSet = new Set();
  const warningSet = new Set();
  bottlenecks.forEach((b, i) => {
    const key = bottleneckKey(b.source, b.target);
    if (b.p95_hours > 48 || i < 3) criticalSet.add(key);
    else if (b.p95_hours > 12 || i < 8) warningSet.add(key);
  });

  const maxW = Math.max(...dfgData.edges.map(e => e.frequency || e.avg_hours || 1), 1);
  const edges = dfgData.edges.map(e => {
    const w = e.frequency || e.avg_hours || 1;
    let label = type === 'frequency' ? (e.frequency || 0) + 'x' : (e.avg_hours || 0).toFixed(1) + 'h';
    let color = '#10B981';
    if (type === 'performance') {
      if ((e.avg_hours||0) > 8) color = '#EF4444';
      else if ((e.avg_hours||0) > 1) color = '#F59E0B';
    }
    const key = bottleneckKey(e.source, e.target);
    if (criticalSet.has(key)) color = '#EF4444';
    else if (warningSet.has(key) && color === '#10B981') color = '#F59E0B';
    return { data: { source: e.source, target: e.target, label, weight: 1+(w/maxW)*6, color } };
  });

  if (state.cyInstance) state.cyInstance.destroy();
  state.cyInstance = cytoscape({
    container: $('dfg-container'),
    elements: [...nodes, ...edges],
    style: [
      { selector: 'node', style: {
        'label': 'data(label)', 'background-color': '#1B2A4A', 'color': '#fff',
        'text-valign': 'center', 'text-halign': 'center', 'font-size': '9px', 'font-weight': '600',
        'width': 'data(size)', 'height': 'data(size)', 'shape': 'round-rectangle',
        'text-wrap': 'wrap', 'text-max-width': '80px', 'padding': '6px'
      }},
      { selector: 'edge', style: {
        'label': 'data(label)', 'width': 'data(weight)', 'line-color': 'data(color)',
        'target-arrow-color': 'data(color)', 'target-arrow-shape': 'triangle',
        'curve-style': 'bezier', 'font-size': '8px', 'color': '#333',
        'text-background-color': '#fff', 'text-background-opacity': 0.8, 'text-background-padding': '2px'
      }}
    ],
    layout: { name: 'breadthfirst', directed: true, spacingFactor: 1.5, avoidOverlap: true }
  });
}

export function renderPMBottlenecks(data) {
  if (!data || !data.bottleneck_transitions) { $('pmBottlenecksContent').innerHTML='Brak danych.'; return; }
  let html = '<table><thead><tr><th>Przejscie</th><th style="text-align:right">Srednia (h)</th><th style="text-align:right">Mediana (h)</th><th style="text-align:right">P95 (h)</th><th style="text-align:right">Czestotliwosc</th></tr></thead><tbody>';
  data.bottleneck_transitions.forEach(b => {
    const cls = b.p95_hours > 48 ? 'style="background:#FEE2E2"' : '';
    html += '<tr '+cls+'><td><strong>'+b.source+'</strong> -> '+b.target+'</td><td style="text-align:right">'+b.avg_hours.toFixed(1)+'</td><td style="text-align:right">'+b.median_hours.toFixed(1)+'</td><td style="text-align:right">'+b.p95_hours.toFixed(1)+'</td><td style="text-align:right">'+b.frequency+'</td></tr>';
  });
  html += '</tbody></table>';
  $('pmBottlenecksContent').innerHTML = html;
}

export function renderPMConformance(data) {
  if (!data) { $('pmConformanceContent').innerHTML='Brak danych.'; return; }
  let html = '<div class="grid-3 mb-16"><div class="card kpi"><div class="kpi-value '+(data.conformance_rate>=0.5?'gold':'')+'">'+(data.conformance_rate*100).toFixed(1)+'%</div><div class="kpi-label">Wskaznik zgodnosci</div></div>';
  html += '<div class="card kpi"><div class="kpi-value">'+data.total_cases+'</div><div class="kpi-label">Casow</div></div>';
  html += '<div class="card kpi"><div class="kpi-value">'+data.conforming_cases+'</div><div class="kpi-label">Zgodnych</div></div></div>';
  if (data.cases && data.cases.length > 0) {
    html += '<table><thead><tr><th>Case ID</th><th style="text-align:right">Fitness</th><th>Brakujace</th><th>Dodatkowe</th></tr></thead><tbody>';
    data.cases.forEach(c => {
      const tag = c.fitness >= 0.8 ? 'tag-green' : c.fitness >= 0.5 ? 'tag-amber' : 'tag-red';
      html += '<tr><td>'+c.case_id+'</td><td style="text-align:right"><span class="tag '+tag+'">'+c.fitness.toFixed(2)+'</span></td><td>'+(c.activities_missing||[]).join(', ')+'</td><td>'+(c.activities_extra||[]).join(', ')+'</td></tr>';
    });
    html += '</tbody></table>';
  }
  $('pmConformanceContent').innerHTML = html;
}

export function renderPMVariants(data) {
  if (!data || !data.variants) { $('pmVariantsContent').innerHTML='Brak danych.'; return; }
  let html = '<div style="margin-bottom:12px;font-size:13px"><strong>'+data.total_variants+'</strong> unikalnych wariantow procesowych</div>';
  html += '<table><thead><tr><th>#</th><th>Sciezka</th><th style="text-align:right">Czestotliwosc</th><th style="text-align:right">%</th><th style="text-align:right">Sredni czas (h)</th></tr></thead><tbody>';
  data.variants.forEach((v,i) => {
    html += '<tr><td>'+(i+1)+'</td><td style="font-size:11px">'+v.variant+'</td><td style="text-align:right;font-weight:700">'+v.frequency+'</td><td style="text-align:right">'+v.percentage+'%</td><td style="text-align:right">'+(v.avg_duration_hours||0).toFixed(1)+'</td></tr>';
  });
  html += '</tbody></table>';
  $('pmVariantsContent').innerHTML = html;
}

export function renderPMRework(data) {
  if (!data) { $('pmReworkContent').innerHTML='Brak danych.'; return; }
  let html = '<div class="grid-3 mb-16"><div class="card kpi"><div class="kpi-value '+(data.rework_rate>0.3?'':'gold')+'">'+(data.rework_rate*100).toFixed(1)+'%</div><div class="kpi-label">Wskaznik rework</div></div>';
  html += '<div class="card kpi"><div class="kpi-value">'+data.cases_with_rework+'</div><div class="kpi-label">Casow z rework</div></div>';
  html += '<div class="card kpi"><div class="kpi-value">'+(data.total_rework_cost||0).toFixed(0)+' PLN</div><div class="kpi-label">Dodatkowy koszt</div></div></div>';
  if (data.most_reworked_activities && data.most_reworked_activities.length > 0) {
    html += '<div class="card-title">Najczesciej powtarzane aktywnosci</div><table><thead><tr><th>Aktywnosc</th><th style="text-align:right">Powtorzenia</th><th style="text-align:right">W ilu casach</th></tr></thead><tbody>';
    data.most_reworked_activities.forEach(a => { html += '<tr><td>'+a.activity+'</td><td style="text-align:right">'+a.rework_count+'</td><td style="text-align:right">'+a.case_count+'</td></tr>'; });
    html += '</tbody></table>';
  }
  $('pmReworkContent').innerHTML = html;
}

export function renderPMSLA(data) {
  if (!data) { $('pmSLAContent').innerHTML='Brak danych.'; return; }
  const brPct = (data.breach_rate*100).toFixed(1);
  let html = '<div class="grid-4 mb-16"><div class="card kpi"><div class="kpi-value gold">'+data.target_hours.toFixed(0)+'h</div><div class="kpi-label">Cel SLA</div></div>';
  html += '<div class="card kpi"><div class="kpi-value">'+data.total_cases+'</div><div class="kpi-label">Casow</div></div>';
  html += '<div class="card kpi"><div class="kpi-value" style="color:'+(data.breach_rate>0.3?'var(--err)':'var(--ok)')+'">'+brPct+'%</div><div class="kpi-label">Wskaznik naruszen</div></div>';
  html += '<div class="card kpi"><div class="kpi-value">'+data.breach_count+'</div><div class="kpi-label">Naruszen SLA</div></div></div>';
  if (data.breaches && data.breaches.length > 0) {
    html += '<table><thead><tr><th>Case ID</th><th style="text-align:right">Czas trwania (h)</th><th style="text-align:right">Cel (h)</th><th style="text-align:right">Przekroczenie (h)</th></tr></thead><tbody>';
    data.breaches.forEach(b => { html += '<tr style="background:#FEF2F2"><td>'+b.case_id+'</td><td style="text-align:right">'+b.duration_hours.toFixed(1)+'</td><td style="text-align:right">'+b.target_hours.toFixed(1)+'</td><td style="text-align:right;font-weight:700;color:var(--err)">+'+b.excess_hours.toFixed(1)+'</td></tr>'; });
    html += '</tbody></table>';
  }
  $('pmSLAContent').innerHTML = html;
}

export function renderPMAnomalies(data) {
  if (!data) { $('pmAnomaliesContent').innerHTML='Brak danych.'; return; }
  let html = '<div class="grid-4 mb-16"><div class="card kpi"><div class="kpi-value">'+data.mean_hours.toFixed(1)+'h</div><div class="kpi-label">Sredni czas</div></div>';
  html += '<div class="card kpi"><div class="kpi-value">'+data.std_hours.toFixed(1)+'h</div><div class="kpi-label">Odchylenie std.</div></div>';
  html += '<div class="card kpi"><div class="kpi-value gold">'+data.threshold_hours.toFixed(1)+'h</div><div class="kpi-label">Prog anomalii</div></div>';
  html += '<div class="card kpi"><div class="kpi-value" style="color:'+(data.anomaly_rate>0?'var(--err)':'var(--ok)')+'">'+(data.anomaly_rate*100).toFixed(1)+'%</div><div class="kpi-label">Wskaznik anomalii</div></div></div>';
  if (data.anomalies && data.anomalies.length > 0) {
    html += '<table><thead><tr><th>Case ID</th><th style="text-align:right">Czas (h)</th><th style="text-align:right">Z-score</th><th style="text-align:right">Odchylenie (h)</th></tr></thead><tbody>';
    data.anomalies.forEach(a => { html += '<tr style="background:#FEF2F2"><td>'+a.case_id+'</td><td style="text-align:right">'+a.duration_hours.toFixed(1)+'</td><td style="text-align:right;font-weight:700">'+a.z_score.toFixed(2)+'</td><td style="text-align:right">+'+a.deviation_hours.toFixed(1)+'</td></tr>'; });
    html += '</tbody></table>';
  }
  $('pmAnomaliesContent').innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════ */


/* ═══ ALERTS ═══ */
export async function loadAlertsDemo() {
  $('alertsContent').innerHTML = '<div style="color:var(--gold)">Generowanie alertow...</div>';
  $('alertsSummary').style.display = 'none';
  try {
    const data = await safeFetchJson(API + '/whatif/alerts/demo?domain=' + state.currentDomain);
    renderAlerts(data);
  } catch(e) {
    $('alertsContent').innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>';
  }
}

export function renderAlerts(data) {
  const summary = data.summary;
  // Summary pills
  let sh = '<div class="a-pill crit">'+summary.critical+' krytycznych</div>';
  sh += '<div class="a-pill warn">'+summary.warning+' ostrzezen</div>';
  sh += '<div class="a-pill infop">'+summary.info+' informacji</div>';
  $('alertsSummary').innerHTML = sh;
  $('alertsSummary').style.display = 'flex';

  if (!data.alerts || data.alerts.length === 0) {
    $('alertsContent').innerHTML = '<div style="color:var(--ok);font-size:14px;font-weight:700;text-align:center;padding:40px">Brak alertow — wszystko w porzadku!</div>';
    return;
  }

  let html = '';
  data.alerts.forEach(a => {
    html += '<div class="alert-card '+a.severity+'">';
    html += '<div class="alert-title">'+severityIcon(a.severity)+' '+a.title+'</div>';
    html += '<div class="alert-desc">'+a.description+'</div>';
    html += '<div class="alert-meta">';
    html += '<span>Kategoria: <strong>'+a.category+'</strong></span>';
    if (a.metric_value) html += '<span>Wartosc: <strong>'+a.metric_value+'</strong></span>';
    if (a.threshold) html += '<span>Prog: <strong>'+a.threshold+'</strong></span>';
    if (a.entity_id) html += '<span>ID: '+a.entity_id+'</span>';
    html += '</div></div>';
  });
  $('alertsContent').innerHTML = html;
}

export function severityIcon(s) {
  if (s==='critical') return '<span style="color:var(--err)">●</span>';
  if (s==='warning') return '<span style="color:var(--warn)">●</span>';
  return '<span style="color:#3B82F6">●</span>';
}

/* ═══════════════════════════════════════════════════════════════════ */
/* ── Advanced charts: scatter, donut, sankey, heatmap, monte carlo, negotiation ── */
/* ═══════════════════════════════════════════════════════════════════ */



/* ═══ PREDICTIVE ANALYTICS ═══ */
export async function loadPredictiveDemo() {
  try {
    const r = await fetch(API + '/predictions/demo');
    const data = await r.json();
    // Alerts
    if (data.alerts && data.alerts.length > 0) {
      const sumEl = document.getElementById('predAlertsSummary');
      const crit = data.alerts.filter(a=>a.severity==='critical').length;
      const high = data.alerts.filter(a=>a.severity==='high').length;
      const med = data.alerts.filter(a=>a.severity==='medium').length;
      sumEl.innerHTML = '<div class="a-pill crit">'+crit+' krytycznych</div>'
        + '<div class="a-pill warn">'+high+' wysokich</div>'
        + '<div class="a-pill infop">'+med+' srednich</div>';
      sumEl.style.display = 'flex';

      document.getElementById('predAlertsContent').innerHTML = data.alerts.map(a => {
        const cls = a.severity === 'critical' ? 'critical' : (a.severity === 'high' ? 'warning' : 'info');
        return '<div class="alert-card '+cls+'">'
          + '<div class="alert-title">'+escHtml(a.title)+'</div>'
          + '<div class="alert-desc">'+escHtml(a.description)+'</div>'
          + '<div class="alert-meta"><span>Dostawca: '+escHtml(a.supplier_id)+'</span><span>Poziom: '+a.severity+'</span></div></div>';
      }).join('');
    }
    // Predictions table
    if (data.predictions && data.predictions.length > 0) {
      document.getElementById('predTableWrap').style.display = 'block';
      document.getElementById('predTablePlaceholder').style.display = 'none';
      document.getElementById('predTableBody').innerHTML = data.predictions.map((p,i) => {
        const pct = ((p.probability_delay||p.delay_probability||0) * 100).toFixed(0);
        const color = p.risk_level === 'high' ? 'var(--err)' : (p.risk_level === 'medium' ? 'var(--warn)' : 'var(--ok)');
        const tagCls = p.risk_level === 'high' ? 'tag-red' : (p.risk_level === 'medium' ? 'tag-amber' : 'tag-green');
        const factors = (p.factors||[]).map(f => typeof f === 'string' ? f : (f.factor||'')).join(', ');
        return '<tr><td style="font-weight:600">ORD-'+(i+1)+'</td><td>'+escHtml(p.supplier_id||'-')+'</td>'
          + '<td>'+escHtml(p.product_id||p.product||'-')+'</td><td>'+(p.predicted_delay_days||'-')+' dni</td>'
          + '<td><div class="pbar" style="width:100px;display:inline-block;vertical-align:middle"><div class="pbar-fill" style="width:'+pct+'%;background:'+color+'"></div></div> <b style="color:'+color+'">'+pct+'%</b></td>'
          + '<td><span class="tag '+tagCls+'">'+p.risk_level+'</span></td>'
          + '<td style="font-size:11px;color:var(--txt2)">'+escHtml(factors)+'</td></tr>';
      }).join('');
    }
    // Profiles chart
    if (data.profiles) {
      renderPredProfilesChart(data.profiles);
    }
  } catch(e) { document.getElementById('predAlertsContent').innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>'; }
}

export async function loadPredictiveProfiles() {
  try {
    const r = await fetch(API + '/predictions/profiles');
    const data = await r.json();
    if (data.profiles) renderPredProfilesChart(data.profiles);
  } catch(e) { document.getElementById('predProfilesContent').innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>'; }
}

export function renderPredProfilesChart(profiles) {
  const canvas = document.getElementById('chartPredProfiles');
  canvas.style.display = 'block';
  document.getElementById('predProfilesContent').innerHTML = '';
  const labels = Object.keys(profiles);
  const onTime = labels.map(k => ((profiles[k].on_time_rate||0)*100).toFixed(1));
  const avgDelay = labels.map(k => profiles[k].avg_delay_days||0);

  if (state.predProfilesChart) state.predProfilesChart.destroy();
  state.predProfilesChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'On-time rate (%)', data: onTime, backgroundColor: 'rgba(16,185,129,.7)', yAxisID: 'y' },
        { label: 'Avg delay (days)', data: avgDelay, backgroundColor: 'rgba(239,68,68,.7)', yAxisID: 'y1' }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'top' } },
      scales: {
        y: { position:'left', title:{display:true,text:'On-time %'}, min:0, max:100 },
        y1: { position:'right', title:{display:true,text:'Avg delay (days)'}, min:0, grid:{drawOnChartArea:false} }
      }
    }
  });
}

