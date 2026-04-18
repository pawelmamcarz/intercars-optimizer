/**
 * step3-optimizer.js — Slider controls, domain switching, optimization runner,
 *                      chart rendering, DOMAIN_CFG, data source, what-if, risk
 */
import { $, fmt, pct, COLORS } from './ui.js';
import { API, safeFetchJson, apiPost } from './api.js';
import { state } from './state.js';

/* ─── Domain config ─── */
export function domainUrls(d) {
  return {
    labelsUrl:    `/demo/${d}/labels`,
    suppliersUrl: `/demo/${d}/suppliers`,
    demandUrl:    `/demo/${d}/demand`,
  };
}

export const DOMAIN_CFG = {
  parts: { ...domainUrls('parts'), unspsc:'25101500', label:'Hamulce i uklady',
    weights:{w_cost:0.40,w_time:0.30,w_compliance:0.15,w_esg:0.15},
    compLabel:'Compliance', esgLabel:'ESG', radarLabels:['Koszt','Lead-time','Compliance','ESG / Green'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca', thProduct:'Indeks / Produkt',
    thCost:'Koszt jedn.', thSLA:'Compliance', thESG:'ESG', tableTitle:'UNSPSC 25101500 — Hamulce i uklady',
    radarTitle:'Profile Radarowe Dostawcow', barCompLabel:'Compliance', barEsgLabel:'ESG / Green' },
  oe_components: { ...domainUrls('oe_components'), unspsc:'25102000', label:'Elektryka silnikowa OE',
    weights:{w_cost:0.35,w_time:0.25,w_compliance:0.25,w_esg:0.15},
    compLabel:'Jakosc OE', esgLabel:'ESG', radarLabels:['Koszt','Lead-time','Jakosc OE','ESG'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca OE', thProduct:'Komponent OE',
    thCost:'Cena OE', thSLA:'Jakosc', thESG:'ESG', tableTitle:'UNSPSC 25102000 — Elektryka silnikowa OE',
    radarTitle:'Profile Dostawcow OE', barCompLabel:'Jakosc OE', barEsgLabel:'ESG' },
  oils: { ...domainUrls('oils'), unspsc:'15121500', label:'Smary i oleje',
    weights:{w_cost:0.45,w_time:0.25,w_compliance:0.15,w_esg:0.15},
    compLabel:'Certyfikat', esgLabel:'Ekologia', radarLabels:['Koszt','Dostawa','Certyfikat API/ACEA','Ekologia'],
    costUnit:'PLN/l', timeUnit:'d', thSupplier:'Producent oleju', thProduct:'Produkt',
    thCost:'Cena/l', thSLA:'Cert.', thESG:'Eko', tableTitle:'UNSPSC 15121500 — Smary i oleje',
    radarTitle:'Profile Producentow', barCompLabel:'Certyfikat API/ACEA', barEsgLabel:'Ekologia' },
  batteries: { ...domainUrls('batteries'), unspsc:'25172000', label:'Akumulatory pojazdowe',
    weights:{w_cost:0.35,w_time:0.30,w_compliance:0.15,w_esg:0.20},
    compLabel:'Gwarancja', esgLabel:'Recykling', radarLabels:['Koszt','Dostawa','Gwarancja','Recykling / ESG'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Producent', thProduct:'Akumulator',
    thCost:'Cena', thSLA:'Gwar.', thESG:'Recykling', tableTitle:'UNSPSC 25172000 — Akumulatory pojazdowe',
    radarTitle:'Profile Producentow', barCompLabel:'Gwarancja', barEsgLabel:'Recykling / ESG' },
  it_services: { ...domainUrls('it_services'), unspsc:'43211500', label:'Komputery i serwery',
    weights:{w_cost:0.35,w_time:0.25,w_compliance:0.20,w_esg:0.20},
    compLabel:'SLA', esgLabel:'Niezaw.', radarLabels:['Koszt','Kickoff','SLA (%)','Niezawodnosc'],
    costUnit:'PLN/h', timeUnit:'dni', thSupplier:'Integrator', thProduct:'Projekt',
    thCost:'Stawka', thSLA:'SLA', thESG:'Niezaw.', tableTitle:'UNSPSC 43211500 — Uslugi IT',
    radarTitle:'Profile Integratorow', barCompLabel:'SLA (%)', barEsgLabel:'Niezawodnosc' },
  logistics: { ...domainUrls('logistics'), unspsc:'78101800', label:'Uslugi transportowe',
    weights:{w_cost:0.30,w_time:0.40,w_compliance:0.15,w_esg:0.15},
    compLabel:'Terminowosc', esgLabel:'Eko-flota', radarLabels:['Koszt/km','Czas dostawy','Terminowosc','Eko-flota'],
    costUnit:'PLN/pacz.', timeUnit:'d', thSupplier:'Przewoznik', thProduct:'Trasa / Usluga',
    thCost:'Koszt', thSLA:'Term.', thESG:'Eko', tableTitle:'UNSPSC 78101800 — Logistyka i Transport',
    radarTitle:'Profile Przewoznikow', barCompLabel:'Terminowosc', barEsgLabel:'Eko-flota' },
  packaging: { ...domainUrls('packaging'), unspsc:'24112400', label:'Materialy opakowaniowe',
    weights:{w_cost:0.45,w_time:0.20,w_compliance:0.10,w_esg:0.25},
    compLabel:'Jakosc', esgLabel:'Sustain.', radarLabels:['Koszt','Dostawa','Jakosc','Sustainability'],
    costUnit:'PLN/szt.', timeUnit:'d', thSupplier:'Dostawca', thProduct:'Material',
    thCost:'Cena/szt.', thSLA:'Jakosc', thESG:'Sustain.', tableTitle:'UNSPSC 24112400 — Opakowania',
    radarTitle:'Profile Dostawcow', barCompLabel:'Jakosc', barEsgLabel:'Sustainability' },
  mro: { ...domainUrls('mro'), unspsc:'27111700', label:'Narzedzia reczne',
    weights:{w_cost:0.40,w_time:0.25,w_compliance:0.20,w_esg:0.15},
    compLabel:'Certyfikat', esgLabel:'ESG', radarLabels:['Koszt','Dostawa','Certyfikat BHP','ESG'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca MRO', thProduct:'Artykul',
    thCost:'Cena', thSLA:'Cert.', thESG:'ESG', tableTitle:'UNSPSC 27111700 — MRO',
    radarTitle:'Profile Dostawcow MRO', barCompLabel:'Certyfikat BHP', barEsgLabel:'ESG' },
  tires: { ...domainUrls('tires'), unspsc:'25171500', label:'Opony',
    weights:{w_cost:0.35,w_time:0.30,w_compliance:0.15,w_esg:0.20},
    compLabel:'Homologacja', esgLabel:'Eko-produkcja', radarLabels:['Koszt','Dostawa','Homologacja','Eko-produkcja'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Producent opon', thProduct:'Opona',
    thCost:'Cena', thSLA:'Homol.', thESG:'Eko', tableTitle:'UNSPSC 25171500 — Opony',
    radarTitle:'Profile Producentow Opon', barCompLabel:'Homologacja', barEsgLabel:'Eko-produkcja' },
  bodywork: { ...domainUrls('bodywork'), unspsc:'26101100', label:'Oswietlenie i nadwozie',
    weights:{w_cost:0.40,w_time:0.25,w_compliance:0.20,w_esg:0.15},
    compLabel:'Jakosc OE', esgLabel:'Recykling', radarLabels:['Koszt','Dostawa','Jakosc OE','Recykling'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca czesci', thProduct:'Element nadwozia',
    thCost:'Cena', thSLA:'Jakosc', thESG:'Recykl.', tableTitle:'UNSPSC 26101100 — Nadwozie i Oswietlenie',
    radarTitle:'Profile Dostawcow Nadwoziowych', barCompLabel:'Jakosc OE', barEsgLabel:'Recykling' },
  facility_management: { ...domainUrls('facility_management'), unspsc:'27111700', label:'Facility Management',
    weights:{w_cost:0.40,w_time:0.25,w_compliance:0.20,w_esg:0.15},
    compLabel:'Certyfikat', esgLabel:'ESG', radarLabels:['Koszt','Dostawa','Certyfikat BHP','ESG'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca FM', thProduct:'Artykul / Usluga',
    thCost:'Cena', thSLA:'Cert.', thESG:'ESG', tableTitle:'UNSPSC 27111700 — Facility Management',
    radarTitle:'Profile Dostawcow FM', barCompLabel:'Certyfikat BHP', barEsgLabel:'ESG' },
  // ── Extended domains (catalog-only, no optimizer backend) ──
  vehicles: { ...domainUrls('parts'), unspsc:'251010', label:'Pojazdy silnikowe',
    weights:{w_cost:0.35,w_time:0.30,w_compliance:0.20,w_esg:0.15},
    compLabel:'Homologacja', esgLabel:'Emisja CO2', radarLabels:['Koszt','Dostawa','Homologacja','Emisja CO2'],
    costUnit:'PLN', timeUnit:'tyg', thSupplier:'Dealer / Importer', thProduct:'Pojazd',
    thCost:'Cena', thSLA:'Homol.', thESG:'CO2', tableTitle:'UNSPSC 2510 — Pojazdy silnikowe',
    radarTitle:'Profile Dostawcow Pojazdow', barCompLabel:'Homologacja', barEsgLabel:'Emisja CO2', catalogOnly:true },
  fleet_svc: { ...domainUrls('logistics'), unspsc:'801515', label:'Fleet Management',
    weights:{w_cost:0.35,w_time:0.25,w_compliance:0.20,w_esg:0.20},
    compLabel:'SLA', esgLabel:'Eko-flota', radarLabels:['Koszt','Czas','SLA','Eko-flota'],
    costUnit:'PLN/msc', timeUnit:'dni', thSupplier:'Operator flotowy', thProduct:'Usluga flotowa',
    thCost:'Rata', thSLA:'SLA', thESG:'Eko', tableTitle:'UNSPSC 8015 — Fleet Management',
    radarTitle:'Profile Operatorow Flotowych', barCompLabel:'SLA', barEsgLabel:'Eko-flota', catalogOnly:true },
  chemicals: { ...domainUrls('oils'), unspsc:'12', label:'Srodki chemiczne',
    weights:{w_cost:0.40,w_time:0.25,w_compliance:0.20,w_esg:0.15},
    compLabel:'REACH', esgLabel:'Ekologia', radarLabels:['Koszt','Dostawa','REACH/CLP','Ekologia'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Producent chemii', thProduct:'Srodek chemiczny',
    thCost:'Cena', thSLA:'REACH', thESG:'Eko', tableTitle:'UNSPSC 12 — Srodki chemiczne',
    radarTitle:'Profile Producentow Chemii', barCompLabel:'REACH/CLP', barEsgLabel:'Ekologia', catalogOnly:true },
  safety: { ...domainUrls('mro'), unspsc:'46', label:'Srodki BHP',
    weights:{w_cost:0.35,w_time:0.25,w_compliance:0.25,w_esg:0.15},
    compLabel:'Certyfikat', esgLabel:'ESG', radarLabels:['Koszt','Dostawa','Certyfikat CE','ESG'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca BHP', thProduct:'Srodek ochrony',
    thCost:'Cena', thSLA:'Cert.', thESG:'ESG', tableTitle:'UNSPSC 46 — Srodki BHP i ochrony',
    radarTitle:'Profile Dostawcow BHP', barCompLabel:'Certyfikat CE', barEsgLabel:'ESG', catalogOnly:true },
  medical: { ...domainUrls('parts'), unspsc:'42', label:'Sprzet medyczny',
    weights:{w_cost:0.30,w_time:0.30,w_compliance:0.25,w_esg:0.15},
    compLabel:'CE/MDR', esgLabel:'Sustain.', radarLabels:['Koszt','Dostawa','CE/MDR','Sustainability'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Producent med.', thProduct:'Wyrob medyczny',
    thCost:'Cena', thSLA:'CE', thESG:'Sustain.', tableTitle:'UNSPSC 42 — Sprzet medyczny',
    radarTitle:'Profile Producentow Med.', barCompLabel:'CE/MDR', barEsgLabel:'Sustainability', catalogOnly:true },
  electrical: { ...domainUrls('batteries'), unspsc:'26', label:'Elektryka i kable',
    weights:{w_cost:0.40,w_time:0.25,w_compliance:0.20,w_esg:0.15},
    compLabel:'Certyfikat', esgLabel:'RoHS', radarLabels:['Koszt','Dostawa','Certyfikat','RoHS'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Producent', thProduct:'Komponent elektryczny',
    thCost:'Cena', thSLA:'Cert.', thESG:'RoHS', tableTitle:'UNSPSC 26 — Elektryka i kable',
    radarTitle:'Profile Producentow', barCompLabel:'Certyfikat', barEsgLabel:'RoHS', catalogOnly:true },
  office: { ...domainUrls('packaging'), unspsc:'44', label:'Art. biurowe',
    weights:{w_cost:0.50,w_time:0.20,w_compliance:0.10,w_esg:0.20},
    compLabel:'Jakosc', esgLabel:'Eko', radarLabels:['Koszt','Dostawa','Jakosc','Eko'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca', thProduct:'Artykul biurowy',
    thCost:'Cena', thSLA:'Jakosc', thESG:'Eko', tableTitle:'UNSPSC 44 — Artykuly biurowe',
    radarTitle:'Profile Dostawcow', barCompLabel:'Jakosc', barEsgLabel:'Eko', catalogOnly:true },
  electronics: { ...domainUrls('it_services'), unspsc:'43', label:'Komputery i elektronika',
    weights:{w_cost:0.35,w_time:0.25,w_compliance:0.20,w_esg:0.20},
    compLabel:'Gwarancja', esgLabel:'RoHS', radarLabels:['Koszt','Dostawa','Gwarancja','RoHS'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dystrybutor IT', thProduct:'Sprzet',
    thCost:'Cena', thSLA:'Gwar.', thESG:'RoHS', tableTitle:'UNSPSC 43 — Komputery i elektronika',
    radarTitle:'Profile Dystrybutorów IT', barCompLabel:'Gwarancja', barEsgLabel:'RoHS', catalogOnly:true },
  steel: { ...domainUrls('parts'), unspsc:'30', label:'Stal i materialy budowlane',
    weights:{w_cost:0.45,w_time:0.25,w_compliance:0.15,w_esg:0.15},
    compLabel:'Atest', esgLabel:'ESG', radarLabels:['Koszt','Dostawa','Atest','ESG'],
    costUnit:'PLN/t', timeUnit:'d', thSupplier:'Hurtownia', thProduct:'Material',
    thCost:'Cena', thSLA:'Atest', thESG:'ESG', tableTitle:'UNSPSC 30 — Stal i materialy budowlane',
    radarTitle:'Profile Dostawcow Stali', barCompLabel:'Atest', barEsgLabel:'ESG', catalogOnly:true },
  furniture: { ...domainUrls('facility_management'), unspsc:'49', label:'Meble',
    weights:{w_cost:0.45,w_time:0.25,w_compliance:0.10,w_esg:0.20},
    compLabel:'Jakosc', esgLabel:'FSC', radarLabels:['Koszt','Dostawa','Jakosc','FSC/Eko'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Producent mebli', thProduct:'Mebel',
    thCost:'Cena', thSLA:'Jakosc', thESG:'FSC', tableTitle:'UNSPSC 49 — Meble',
    radarTitle:'Profile Producentow Mebli', barCompLabel:'Jakosc', barEsgLabel:'FSC/Eko', catalogOnly:true },
  food: { ...domainUrls('packaging'), unspsc:'50', label:'Zywnosc i napoje',
    weights:{w_cost:0.45,w_time:0.30,w_compliance:0.15,w_esg:0.10},
    compLabel:'HACCP', esgLabel:'Bio', radarLabels:['Koszt','Dostawa','HACCP','Bio/Eko'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dystrybutor', thProduct:'Produkt spozywczy',
    thCost:'Cena', thSLA:'HACCP', thESG:'Bio', tableTitle:'UNSPSC 50 — Zywnosc i napoje',
    radarTitle:'Profile Dystrybutorów', barCompLabel:'HACCP', barEsgLabel:'Bio/Eko', catalogOnly:true },
  cleaning: { ...domainUrls('facility_management'), unspsc:'47', label:'Srodki czystosci',
    weights:{w_cost:0.45,w_time:0.20,w_compliance:0.15,w_esg:0.20},
    compLabel:'Certyfikat', esgLabel:'Eko', radarLabels:['Koszt','Dostawa','Certyfikat','Eko'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca', thProduct:'Srodek czystosci',
    thCost:'Cena', thSLA:'Cert.', thESG:'Eko', tableTitle:'UNSPSC 47 — Srodki czystosci',
    radarTitle:'Profile Dostawcow', barCompLabel:'Certyfikat', barEsgLabel:'Eko', catalogOnly:true },
  hvac: { ...domainUrls('facility_management'), unspsc:'40', label:'HVAC i klimatyzacja',
    weights:{w_cost:0.35,w_time:0.30,w_compliance:0.20,w_esg:0.15},
    compLabel:'F-gaz', esgLabel:'EnEff', radarLabels:['Koszt','Dostawa','F-gaz','Efektywnosc energ.'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Instalator HVAC', thProduct:'Urzadzenie HVAC',
    thCost:'Cena', thSLA:'F-gaz', thESG:'EnEff', tableTitle:'UNSPSC 40 — HVAC i klimatyzacja',
    radarTitle:'Profile Dostawcow HVAC', barCompLabel:'F-gaz', barEsgLabel:'Efektywnosc energ.', catalogOnly:true },
  fuels: { ...domainUrls('oils'), unspsc:'15', label:'Paliwa',
    weights:{w_cost:0.50,w_time:0.25,w_compliance:0.10,w_esg:0.15},
    compLabel:'Norma', esgLabel:'Emisja', radarLabels:['Koszt','Dostawa','Norma','Emisja CO2'],
    costUnit:'PLN/l', timeUnit:'d', thSupplier:'Dostawca paliw', thProduct:'Paliwo',
    thCost:'Cena/l', thSLA:'Norma', thESG:'Emisja', tableTitle:'UNSPSC 15 — Paliwa',
    radarTitle:'Profile Dostawcow Paliw', barCompLabel:'Norma', barEsgLabel:'Emisja CO2', catalogOnly:true },
  consulting: { ...domainUrls('it_services'), unspsc:'80', label:'Uslugi doradcze',
    weights:{w_cost:0.35,w_time:0.25,w_compliance:0.20,w_esg:0.20},
    compLabel:'Referencje', esgLabel:'CSR', radarLabels:['Koszt','Czas','Referencje','CSR'],
    costUnit:'PLN/h', timeUnit:'dni', thSupplier:'Firma doradcza', thProduct:'Usluga',
    thCost:'Stawka', thSLA:'Ref.', thESG:'CSR', tableTitle:'UNSPSC 80 — Uslugi doradcze',
    radarTitle:'Profile Firm Doradczych', barCompLabel:'Referencje', barEsgLabel:'CSR', catalogOnly:true },
  construction_svc: { ...domainUrls('facility_management'), unspsc:'72', label:'Uslugi budowlane',
    weights:{w_cost:0.40,w_time:0.30,w_compliance:0.20,w_esg:0.10},
    compLabel:'Licencja', esgLabel:'ESG', radarLabels:['Koszt','Czas','Licencja budowl.','ESG'],
    costUnit:'PLN', timeUnit:'tyg', thSupplier:'Wykonawca', thProduct:'Usluga budowlana',
    thCost:'Cena', thSLA:'Lic.', thESG:'ESG', tableTitle:'UNSPSC 72 — Uslugi budowlane',
    radarTitle:'Profile Wykonawcow', barCompLabel:'Licencja budowlana', barEsgLabel:'ESG', catalogOnly:true },
  transport_svc: { ...domainUrls('logistics'), unspsc:'78', label:'Uslugi transportowe',
    weights:{w_cost:0.30,w_time:0.40,w_compliance:0.15,w_esg:0.15},
    compLabel:'Terminowosc', esgLabel:'Eko-flota', radarLabels:['Koszt','Czas','Terminowosc','Eko-flota'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Przewoznik', thProduct:'Usluga transportowa',
    thCost:'Koszt', thSLA:'Term.', thESG:'Eko', tableTitle:'UNSPSC 78 — Uslugi transportowe',
    radarTitle:'Profile Przewoznikow', barCompLabel:'Terminowosc', barEsgLabel:'Eko-flota', catalogOnly:true },
  raw_materials: { ...domainUrls('parts'), unspsc:'11', label:'Surowce',
    weights:{w_cost:0.45,w_time:0.25,w_compliance:0.15,w_esg:0.15},
    compLabel:'Atest', esgLabel:'ESG', radarLabels:['Koszt','Dostawa','Atest','ESG'],
    costUnit:'PLN/t', timeUnit:'d', thSupplier:'Dostawca surowcow', thProduct:'Surowiec',
    thCost:'Cena', thSLA:'Atest', thESG:'ESG', tableTitle:'UNSPSC 11 — Surowce',
    radarTitle:'Profile Dostawcow Surowcow', barCompLabel:'Atest', barEsgLabel:'ESG', catalogOnly:true },
  bearings: { ...domainUrls('parts'), unspsc:'31', label:'Lozyska i elementy zlaczne',
    weights:{w_cost:0.40,w_time:0.25,w_compliance:0.20,w_esg:0.15},
    compLabel:'Jakosc', esgLabel:'ESG', radarLabels:['Koszt','Dostawa','Jakosc','ESG'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Producent', thProduct:'Lozysko / zlaczka',
    thCost:'Cena', thSLA:'Jakosc', thESG:'ESG', tableTitle:'UNSPSC 31 — Lozyska i elementy zlaczne',
    radarTitle:'Profile Producentow', barCompLabel:'Jakosc', barEsgLabel:'ESG', catalogOnly:true },
  semiconductors: { ...domainUrls('it_services'), unspsc:'32', label:'Polprzewodniki',
    weights:{w_cost:0.35,w_time:0.30,w_compliance:0.20,w_esg:0.15},
    compLabel:'Spec', esgLabel:'RoHS', radarLabels:['Koszt','Lead-time','Specyfikacja','RoHS'],
    costUnit:'PLN', timeUnit:'tyg', thSupplier:'Dystrybutor', thProduct:'Komponent',
    thCost:'Cena', thSLA:'Spec', thESG:'RoHS', tableTitle:'UNSPSC 32 — Polprzewodniki',
    radarTitle:'Profile Dystrybutorów', barCompLabel:'Specyfikacja', barEsgLabel:'RoHS', catalogOnly:true },
};

export function getWeights() {
  const slider = document.getElementById('lambdaSlider');
  return { lambda_param: parseFloat(slider.value), w_cost: parseFloat($('wCost').value),
    w_time: parseFloat($('wTime').value), w_compliance: parseFloat($('wComp').value),
    w_esg: parseFloat($('wEsg').value) };
}
export function getMode() { return $('modeSelect').value; }
export function getMaxVendorShare() { return parseFloat($('maxVendorShare').value) / 100; }

export function switchSubtab(id) {
  document.querySelectorAll('.subtab-btn').forEach((b, i) => {
    const panels = document.querySelectorAll('.subtab-panel');
    b.classList.toggle('active', panels[i]?.id === id);
  });
  document.querySelectorAll('.subtab-panel').forEach(p => p.classList.toggle('active', p.id === id));
}

/* ─── Slider setup ─── */
export function initSliders() {
  const slider = document.getElementById('lambdaSlider');
  const lambdaVal = document.getElementById('lambdaVal');
  if (slider && lambdaVal) {
    slider.addEventListener('input', () => { lambdaVal.textContent = parseFloat(slider.value).toFixed(2); });
  }
  /* What-if sliders */
  [1,2,3].forEach(i => {
    const ls = $('wi_lambda'+i); const ms = $('wi_mvs'+i);
    if(ls) ls.addEventListener('input', () => { $('wi_lambda'+i+'_val').textContent = parseFloat(ls.value).toFixed(2); });
    if(ms) ms.addEventListener('input', () => { $('wi_mvs'+i+'_val').textContent = ms.value + '%'; });
  });
  /* Mode select */
  const modeSelect = $('modeSelect');
  if (modeSelect) modeSelect.addEventListener('change', updateModeExplainer);
}

const MODE_INFO = {
  continuous: { cls:'lp', icon:'\ud83d\udcca', title:'Elastyczna alokacja',
    body:'System rozdziela zamowienie proporcjonalnie miedzy wielu dostawcow \u2014 optymalizuje koszt i czas przy zachowaniu dywersyfikacji.',
    pro:'Zalety: dywersyfikacja ryzyka, optymalne ceny', con:'Uwaga: wiecej dostaw do koordynacji' },
  mip: { cls:'mip', icon:'\ud83c\udfaf', title:'Dokladna alokacja',
    body:'System przypisuje kazdego dostawce do konkretnych pozycji \u2014 prostsza logistyka, mniej faktur.',
    pro:'Zalety: prostsza logistyka, jeden kontrahent per pozycja', con:'Uwaga: wyzsze ryzyko, brak dywersyfikacji' },
};
export function updateModeExplainer() {
  const info = MODE_INFO[getMode()];
  $('modeExplainer').className = 'mode-explainer ' + info.cls;
  $('modeExTitle').innerHTML = '<span class="icon">' + info.icon + '</span> ' + info.title;
  $('modeExBody').innerHTML = info.body + '<div class="mode-vs"><div class="mode-vs-item pro">' + info.pro + '</div><div class="mode-vs-item con">' + info.con + '</div></div>';
}

export function _makeGenericCfg(domain) {
  const seg = (_UNSPSC_SEGMENT_DOMAINS && Object.keys(_UNSPSC_SEGMENT_DOMAINS).find(s => {
    const cats = _UNSPSC_SEGMENT_DOMAINS[s];
    return cats && cats.includes(domain);
  })) || '';
  return { ...domainUrls('parts'), unspsc: seg, label: domain.replace(/_/g,' '),
    weights:{w_cost:0.40,w_time:0.25,w_compliance:0.20,w_esg:0.15},
    compLabel:'Compliance', esgLabel:'ESG', radarLabels:['Koszt','Dostawa','Compliance','ESG'],
    costUnit:'PLN', timeUnit:'d', thSupplier:'Dostawca', thProduct:'Produkt',
    thCost:'Cena', thSLA:'Compl.', thESG:'ESG', tableTitle:'UNSPSC ' + seg + ' — ' + domain.replace(/_/g,' '),
    radarTitle:'Profile Dostawcow', barCompLabel:'Compliance', barEsgLabel:'ESG', catalogOnly:true };
}

export function switchDomain(domain) {
  state.currentDomain = domain;
  document.querySelectorAll('.domain-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.domain === domain));
  const cfg = DOMAIN_CFG[domain] || _makeGenericCfg(domain);
  $('domainBadge').textContent = (cfg.unspsc || '') + ' ' + (cfg.label || domain);
  $('wCost').value = cfg.weights.w_cost; $('wTime').value = cfg.weights.w_time;
  $('wComp').value = cfg.weights.w_compliance; $('wEsg').value = cfg.weights.w_esg;
  $('wCompLabel').textContent = cfg.compLabel; $('wEsgLabel').textContent = cfg.esgLabel;
  if ($('thSupplier')) $('thSupplier').innerHTML = cfg.thSupplier + ' <span class="sort-arrow">-</span>';
  if ($('thProduct')) $('thProduct').innerHTML = cfg.thProduct + ' <span class="sort-arrow">-</span>';
  if ($('thCost')) $('thCost').innerHTML = cfg.thCost + ' <span class="sort-arrow">-</span>';
  if ($('thSLA')) $('thSLA').innerHTML = cfg.thSLA + ' <span class="sort-arrow">-</span>';
  if ($('thESG')) $('thESG').innerHTML = cfg.thESG + ' <span class="sort-arrow">-</span>';
  if ($('tableTitle')) $('tableTitle').textContent = cfg.tableTitle;
  if ($('radarTitle')) $('radarTitle').textContent = cfg.radarTitle;
  if ($('barCompLabel')) $('barCompLabel').textContent = cfg.barCompLabel;
  if ($('barEsgLabel')) $('barEsgLabel').textContent = cfg.barEsgLabel;
  updateModeExplainer();
  // Skip optimizer data loading for catalog-only domains or when on Step 1
  if (cfg.catalogOnly && state.currentStep === 1) return;
  if (state.dataSource === 'db') loadDbSummary();
  loadDataAndRun();
}

/* ─── Load domain data + run ─── */
/* ── Optimization presets ── */

export function setOptPreset(preset) {
  const presets = {
    balanced: { lambda: 0.50, wCost: 0.40, wTime: 0.30, wComp: 0.15, wEsg: 0.15, mvs: 60 },
    cheapest: { lambda: 0.95, wCost: 0.60, wTime: 0.15, wComp: 0.15, wEsg: 0.10, mvs: 80 },
    fastest: { lambda: 0.10, wCost: 0.15, wTime: 0.60, wComp: 0.15, wEsg: 0.10, mvs: 60 },
    green:   { lambda: 0.40, wCost: 0.20, wTime: 0.15, wComp: 0.25, wEsg: 0.40, mvs: 50 },
  };
  const p = presets[preset];
  if (!p) return;
  $('lambdaSlider').value = p.lambda; $('lambdaVal').textContent = p.lambda.toFixed(2);
  $('wCost').value = p.wCost; $('wTime').value = p.wTime; $('wComp').value = p.wComp; $('wEsg').value = p.wEsg;
  $('maxVendorShare').value = p.mvs;
  // Highlight active preset
  ['presetBalanced','presetCheapest','presetFastest','presetGreen'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.style.background = id === 'preset' + preset.charAt(0).toUpperCase() + preset.slice(1) ? 'var(--navy)' : ''; el.style.color = id === 'preset' + preset.charAt(0).toUpperCase() + preset.slice(1) ? '#fff' : ''; }
  });
  // Auto-run
  runAll();
}

export async function loadDataAndRun() {
  const cfg = DOMAIN_CFG[state.currentDomain] || _makeGenericCfg(state.currentDomain);
  if (cfg.catalogOnly) { console.log('Catalog-only domain:', state.currentDomain, '— skipping optimizer'); return; }
  try {
    const [labels, suppliers, demand] = await Promise.all([
      safeFetchJson(API + cfg.labelsUrl), safeFetchJson(API + cfg.suppliersUrl), safeFetchJson(API + cfg.demandUrl)
    ]);
    state.productLabels = labels.products || {};
    state.demandMap = {}; demand.forEach(x => { state.demandMap[x.product_id] = x.demand_qty; });
    state.totalSuppliers = suppliers.length;
    await runOptimization(suppliers, demand);
  } catch(e) { console.error('Load error:', e); }
}

/* ═══ MAIN RUN ═══ */
export async function runAll() {
  const cfg = DOMAIN_CFG[state.currentDomain] || _makeGenericCfg(state.currentDomain);
  if (cfg.catalogOnly) { alert('Ta kategoria nie posiada danych optymalizacyjnych.\nWybierz kategorie z zakladki Optymalizacja.'); return; }
  $('runBtn').classList.add('loading'); $('runLabel').innerHTML = '<span class="spin"></span>';
  try {
    const [suppliers, demand] = await Promise.all([
      safeFetchJson(API + cfg.suppliersUrl), safeFetchJson(API + cfg.demandUrl)
    ]);
    state.totalSuppliers = suppliers.length;
    await runOptimization(suppliers, demand);
  } catch (e) {
    alert('Blad: ' + e.message);
    $('statusBadge').textContent = '● ERROR'; $('statusBadge').style.background = '#EF4444';
  } finally {
    $('runBtn').classList.remove('loading'); $('runLabel').textContent = 'Optymalizuj';
  }
}

async function runOptimization(suppliers, demand) {
  const weights = getWeights(), mode = getMode(), maxVS = getMaxVendorShare();
  const body = { suppliers, demand, weights, mode, pareto_steps: 21, max_vendor_share: maxVS };
  // Stash for B2: MC re-solve reuses the same inputs
  state._lastOptimizeReq = { suppliers, demand };
  const dash = await apiPost('/dashboard', body);
  state.lastOptDemand = demand;
  state.lastOptAllocation = dash.current_allocation;
  renderKPIs(dash.current_allocation); renderBars(dash.current_allocation.objective);
  renderAllocTable(dash.current_allocation.allocations);
  state.lastParetoPoints = dash.pareto_front;
  renderParetoChart(dash.pareto_front); renderRadarChart(dash.supplier_profiles);
  renderShadowPrices(dash.current_allocation.shadow_prices || []);
  $('statusBadge').textContent = '● OPTIMAL'; $('statusBadge').style.background = '#10B981';
  renderCreateOrderBtn();
}


export function renderShadowPrices(prices) {
  const card = document.getElementById('shadowPricesCard');
  const listEl = document.getElementById('shadowPricesList');
  if (!card || !listEl) return;
  // Only keep binding (slack ≈ 0) constraints — non-binding have no
  // decision-making value for the buyer.
  const binding = (prices || []).filter(p => Math.abs(p.slack) < 1e-3);
  if (!binding.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = '';
  listEl.innerHTML = binding.slice(0, 12).map(p => {
    const magnitude = Math.abs(p.value);
    const formatted = magnitude < 0.001
      ? p.value.toExponential(2)
      : p.value.toFixed(magnitude > 100 ? 0 : 3);
    return '<div class="sp-row">'
      + '<span class="sp-kind ' + (p.kind || 'demand') + '">' + (p.kind || '?') + '</span>'
      + '<span class="sp-label">' + _escapeSp(p.label || p.constraint_id) + '</span>'
      + '<span class="sp-value">' + formatted + '</span>'
      + '<span class="sp-slack">' + (Math.abs(p.slack) < 1e-6 ? 'BINDING' : 'slack=' + p.slack.toFixed(2)) + '</span>'
    + '</div>';
  }).join('');
}

function _escapeSp(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}


export function renderCreateOrderBtn() {
  const bar = $('optToOrderBar');
  if (!state.lastOptAllocation || !state.lastOptAllocation.allocations || state.lastOptAllocation.allocations.length === 0) {
    bar.style.display = 'none'; return;
  }
  const totalCost = state.lastOptAllocation.allocations.reduce((s,a) => s + a.allocated_qty * (a.unit_cost + a.logistics_cost), 0);
  const domainLabel = (DOMAIN_CFG[state.currentDomain] || {}).label || state.currentDomain;
  bar.style.display = 'flex';
  bar.style.cssText = 'display:flex;align-items:center;gap:12px;padding:10px 16px;background:linear-gradient(135deg,#F0FDF4,#ECFDF5);border:1px solid #BBF7D0;border-radius:8px;margin-bottom:20px';
  bar.innerHTML = '<button onclick="createOrderFromOptimizer()" style="background:var(--ok);color:#fff;border:none;border-radius:6px;padding:8px 20px;font-weight:700;cursor:pointer;font-size:13px;white-space:nowrap">Zloz zamowienie</button>'
    + '<span style="font-size:12px;color:var(--txt2)">Utworz zamowienie w module Buying z biezacej alokacji <strong>'+domainLabel+'</strong> (koszt: <strong>'+Math.round(totalCost).toLocaleString('pl')+' PLN</strong>)</span>';
}

export async function createOrderFromOptimizer() {
  if (!state.lastOptAllocation) return;
  const bar = $('optToOrderBar');
  const btn = bar.querySelector('button');
  btn.disabled = true; btn.textContent = 'Tworzenie...'; btn.style.opacity = '0.6';

  try {
    const result = await safeFetchJson(API + '/buying/order-from-optimizer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        domain: state.currentDomain,
        allocations: state.lastOptAllocation.allocations,
        demand: state.lastOptDemand,
        objective: state.lastOptAllocation.objective || {},
        solver_stats: state.lastOptAllocation.solver_stats || {},
      })
    });

    if (result.success) {
      const isApproval = result.requires_manager_approval;
      // Cart became stale the moment we turned it into an order — wipe the
      // localStorage snapshot so a refresh doesn't re-offer the same items.
      if (typeof window.clearPersistedCart === 'function') window.clearPersistedCart();
      bar.style.background = 'linear-gradient(135deg,#F0FDF4,#DCFCE7)';
      bar.style.border = '1px solid #86EFAC';
      bar.innerHTML = '<div style="font-size:13px">'
        + '<strong style="color:var(--ok)">&#10003; Zamowienie utworzone z alokacji solvera!</strong> '
        + 'Nr: <strong style="color:var(--navy)">'+result.order_id+'</strong> '
        + (isApproval
          ? '<span class="ob-status-badge pending_approval" style="font-size:11px">Oczekuje na zatwierdzenie</span>'
          : '<span class="ob-status-badge approved" style="font-size:11px">Zatwierdzone</span>')
        + ' <button onclick="switchTab(\'buying\');setTimeout(()=>obShowOrderDetail(&quot;'+result.order_id+'&quot;),300)" '
        + 'style="background:var(--navy);color:#fff;border:none;border-radius:5px;padding:6px 16px;font-size:12px;font-weight:700;cursor:pointer;margin-left:8px">Przejdz do checkoutu &#10140;</button>'
        + '<div style="font-size:11px;color:var(--txt2);margin-top:4px">Automatyczne przejscie za 2s...</div>'
        + '</div>';
      // Auto-navigate to the order detail so user sees the checkout without extra click.
      setTimeout(() => {
        if (typeof window.switchTab === 'function') window.switchTab('buying');
        setTimeout(() => {
          if (typeof window.obShowOrderDetail === 'function') window.obShowOrderDetail(result.order_id);
        }, 300);
      }, 2000);
    } else {
      bar.innerHTML = '<div style="color:var(--err);font-size:13px">Blad: '+result.message+'</div>';
    }
  } catch(e) {
    btn.disabled = false; btn.textContent = 'Zloz zamowienie'; btn.style.opacity = '1';
    bar.insertAdjacentHTML('beforeend', '<span style="color:var(--err);font-size:12px;margin-left:8px">'+e.message+'</span>');
  }
}

/* ═══ KPIs ═══ */

export function renderKPIs(r) {
  $('kObjTotal').textContent = fmt(r.objective.total, 6);
  $('kSolveTime').textContent = r.solver_stats.solve_time_ms.toFixed(1) + ' ms';
  const uniq = new Set(r.allocations.map(a => a.supplier_id));
  $('kSuppliers').textContent = uniq.size + ' / ' + state.totalSuppliers;
  $('kProducts').textContent = r.allocations.length;
  const db = $('diversBadge');
  if (r.solver_stats.diversification_active) {
    db.style.display = 'inline-flex'; db.className = 'divers-badge active mt-16';
    db.innerHTML = 'Dywersyfikacja: <=' + (r.solver_stats.max_vendor_share * 100).toFixed(0) + '%';
  } else { db.style.display = 'inline-flex'; db.className = 'divers-badge mt-16'; db.innerHTML = 'Dywersyfikacja wylaczona'; }
}

export function renderBars(o) {
  const max = Math.max(o.cost_component, o.time_component, o.compliance_component, o.esg_component, 0.001);
  $('bCost').textContent = fmt(o.cost_component, 6); $('bTime').textContent = fmt(o.time_component, 6);
  $('bComp').textContent = fmt(o.compliance_component, 6); $('bEsg').textContent = fmt(o.esg_component, 6);
  $('bCostBar').style.width = (o.cost_component/max*100)+'%'; $('bTimeBar').style.width = (o.time_component/max*100)+'%';
  $('bCompBar').style.width = (o.compliance_component/max*100)+'%'; $('bEsgBar').style.width = (o.esg_component/max*100)+'%';
}

/* ═══ Allocation table ═══ */
export function renderAllocTable(allocs) { state.currentAllocs = [...allocs]; state.sortState = { key: null, dir: 'asc' }; updateSortHeaders(); applyFiltersAndSort(); }
export function getFilteredAllocs() {
  const fSup=($('filterSupplier').value||'').toLowerCase().trim(), fProd=($('filterProduct').value||'').toLowerCase().trim();
  const fMin=parseFloat($('filterMinFraction').value), fMax=parseFloat($('filterMaxFraction').value);
  return state.currentAllocs.filter(a => {
    if (fSup && !a.supplier_name.toLowerCase().includes(fSup) && !a.supplier_id.toLowerCase().includes(fSup)) return false;
    if (fProd) { const pLabel=(state.productLabels[a.product_id]||'').toLowerCase(); if(!a.product_id.toLowerCase().includes(fProd) && !pLabel.includes(fProd)) return false; }
    const pctVal=a.allocated_fraction*100;
    if (!isNaN(fMin)&&pctVal<fMin) return false; if (!isNaN(fMax)&&pctVal>fMax) return false; return true;
  });
}
export function sortVal(a, key) {
  switch(key) { case 'supplier':return a.supplier_name; case 'product':return a.product_id; case 'demand':return state.demandMap[a.product_id]||0;
    case 'alloc':return a.allocated_qty; case 'fraction':return a.allocated_fraction; case 'cost':return a.unit_cost+a.logistics_cost;
    case 'lead':return a.lead_time_days; case 'sla':return a.compliance_score; case 'esg':return a.esg_score; default:return 0; }
}
export function cmpVals(va,vb,dir) { if(typeof va==='string') return dir*va.localeCompare(vb,'pl'); return dir*(va-vb); }
export function applySorting(allocs) {
  if(!state.sortState.key) return allocs; const dir=state.sortState.dir==='asc'?1:-1, pk=state.sortState.key;
  return [...allocs].sort((a,b)=>{ const p=cmpVals(sortVal(a,pk),sortVal(b,pk),dir); if(p!==0) return p; if(pk!=='fraction') return -(a.allocated_fraction-b.allocated_fraction); return 0; });
}
export function applyFiltersAndSort() { const f=getFilteredAllocs(), s=applySorting(f); renderAllocRows(s);
  const h=$('sortHint'); if(state.sortState.key&&state.sortState.key!=='fraction') h.textContent='udzial '+state.sortState.dir.toUpperCase()+', potem udzial'; else if(state.sortState.key==='fraction') h.textContent='udzial '+state.sortState.dir.toUpperCase(); else h.textContent=''; }
export function applyFilters() { applyFiltersAndSort(); }
export function clearFilters() { $('filterSupplier').value=''; $('filterProduct').value=''; $('filterMinFraction').value=''; $('filterMaxFraction').value=''; applyFiltersAndSort(); }

export function renderAllocRows(allocs) {
  const cfg=DOMAIN_CFG[state.currentDomain]; const total=state.currentAllocs.length, shown=allocs.length;
  $('allocCount').textContent = shown<total ? shown+' / '+total+' alokacji' : total+' alokacji';
  $('allocBody').innerHTML = allocs.map(a => {
    const dq=state.demandMap[a.product_id]||'?';
    const slaTag=a.compliance_score>=0.95?'tag-green':a.compliance_score>=0.85?'tag-amber':'tag-blue';
    const esgTag=a.esg_score>=0.90?'tag-green':a.esg_score>=0.75?'tag-amber':'tag-blue';
    const pLabel=state.productLabels[a.product_id]||'';
    const costStr=cfg.costUnit==='PLN/h'?a.unit_cost.toFixed(0)+' PLN/h':(a.unit_cost+a.logistics_cost).toFixed(2)+' PLN';
    return '<tr><td><strong>'+a.supplier_name+'</strong><br><a href="#" onclick="event.preventDefault();switchTab(\'suppliers\');setTimeout(()=>suppShowDetail(\''+a.supplier_id+'\'),200)" style="font-size:11px;color:#1565c0;cursor:pointer">'+a.supplier_id+'</a></td>'
      +'<td><strong>'+a.product_id+'</strong><br><span style="font-size:11px;color:var(--txt2)">'+pLabel+'</span></td>'
      +'<td style="text-align:right">'+Number(dq).toLocaleString('pl')+'</td>'
      +'<td style="text-align:right;font-weight:700">'+Number(a.allocated_qty).toLocaleString('pl')+'</td>'
      +'<td style="text-align:right">'+pct(a.allocated_fraction)+'</td>'
      +'<td style="text-align:right">'+costStr+'</td>'
      +'<td style="text-align:right">'+a.lead_time_days+' '+cfg.timeUnit+'</td>'
      +'<td><span class="tag '+slaTag+'">'+pct(a.compliance_score)+'</span></td>'
      +'<td><span class="tag '+esgTag+'">'+pct(a.esg_score)+'</span></td></tr>';
  }).join('');
}
export function sortAllocTable(key) { if(state.sortState.key===key) state.sortState.dir=state.sortState.dir==='asc'?'desc':'asc'; else { state.sortState.key=key; state.sortState.dir='asc'; } updateSortHeaders(); applyFiltersAndSort(); }
export function updateSortHeaders() { document.querySelectorAll('th.sortable').forEach(th => { th.classList.remove('sort-asc','sort-desc'); const a=th.querySelector('.sort-arrow'); if(a) a.textContent='-'; if(th.dataset.sort===state.sortState.key) { th.classList.add(state.sortState.dir==='asc'?'sort-asc':'sort-desc'); if(a) a.textContent=state.sortState.dir==='asc'?'A':'V'; } }); }

/* ═══ Pareto chart — interactive ═══ */

export function renderParetoChart(points) {
  const cfg = DOMAIN_CFG[state.currentDomain];
  if (state.paretoChartInst) state.paretoChartInst.destroy();
  const ctx = $('paretoChart').getContext('2d');
  state.paretoChartInst = new Chart(ctx, {
    type: 'line',
    data: {
      labels: points.map(p => 'L=' + p.lambda_param.toFixed(2)),
      datasets: [
        { label:'Koszt', data:points.map(p=>p.cost_component), borderColor:'#1B2A4A', backgroundColor:'rgba(27,42,74,.1)', tension:.3, fill:true, pointRadius:3 },
        { label:'Czas', data:points.map(p=>p.time_component), borderColor:'#D4A843', backgroundColor:'rgba(212,168,67,.1)', tension:.3, fill:true, pointRadius:3 },
        { label:cfg.barCompLabel, data:points.map(p=>p.compliance_component), borderColor:'#6366F1', borderDash:[5,3], tension:.3, pointRadius:2 },
        { label:cfg.barEsgLabel, data:points.map(p=>p.esg_component), borderColor:'#10B981', borderDash:[5,3], tension:.3, pointRadius:2 },
        { label:'TOTAL', data:points.map(p=>p.objective_total), borderColor:'#EF4444', borderWidth:2.5, tension:.3, pointRadius:4, pointBackgroundColor:'#EF4444' },
      ]
    },
    options: {
      responsive:true,
      plugins:{ legend:{ position:'bottom', labels:{ boxWidth:12, font:{size:11} } }, tooltip:{ mode:'index', intersect:false } },
      scales:{ x:{ grid:{display:false}, ticks:{font:{size:10}, maxRotation:45} }, y:{ grid:{color:'#F0F0F0'}, ticks:{font:{size:10}} } },
      interaction:{ mode:'nearest', axis:'x', intersect:false },
      onClick: (evt, elements) => {
        if (elements.length > 0 && state.lastParetoPoints.length > 0) {
          const idx = elements[0].index;
          const lambda = state.lastParetoPoints[idx].lambda_param;
          slider.value = lambda; lambdaVal.textContent = lambda.toFixed(2);
          loadDataAndRun();
        }
      }
    }
  });
}

/* ═══ Pareto + Monte Carlo (B2) ═══ */

export async function runParetoMc() {
  const btn = document.getElementById('paretoMcRunBtn');
  const empty = document.getElementById('paretoMcEmpty');
  const content = document.getElementById('paretoMcContent');
  const statsEl = document.getElementById('paretoMcStats');
  const iterSel = document.getElementById('mcIterSelect');
  if (!btn) return;

  const iters = iterSel ? parseInt(iterSel.value, 10) || 50 : 50;
  btn.disabled = true;
  btn.textContent = '⏳ Liczenie...';
  if (empty) empty.style.display = '';
  if (empty) empty.innerHTML = 'Symulacja Monte Carlo (~' + iters + ' iteracji × ' + (state.lastParetoPoints?.length || 11) + ' punktow)...';

  try {
    // Reuse the data we already have in memory (suppliers + demand from last
    // optimize run). If not available fall back to demo.
    const suppliers = state._lastOptimizeReq?.suppliers || null;
    const demand = state._lastOptimizeReq?.demand || null;
    let data;
    if (suppliers && demand) {
      const body = {
        suppliers, demand,
        weights: getWeights(), mode: getMode(),
        pareto_steps: 11, max_vendor_share: getMaxVendorShare(),
      };
      data = await apiPost('/dashboard/pareto-xy-mc?mc_iterations=' + iters, body);
    } else {
      data = await safeFetchJson(
        API + '/dashboard/pareto-xy-mc/demo?domain=' + encodeURIComponent(state.currentDomain)
          + '&mc_iterations=' + iters,
      );
    }
    const points = data.points || [];
    if (!points.length) {
      if (empty) empty.textContent = 'Brak wynikow — sprawdz czy problem jest feasibilny.';
      return;
    }
    _renderParetoMcChart(points);
    if (empty) empty.style.display = 'none';
    if (content) content.style.display = '';

    // Summary: highest-dispersion point + highest-mean point
    const spread = points.map(p => ({ p, range: p.cost_p95_pln - p.cost_p5_pln }));
    spread.sort((a, b) => b.range - a.range);
    const worst = spread[0].p;
    const cheap = points.reduce((a, b) => (a.cost_mean_pln < b.cost_mean_pln ? a : b));
    if (statsEl) {
      statsEl.innerHTML =
        '<div><b>Najbardziej niestabilny:</b> λ=' + worst.lambda_param.toFixed(2)
          + ' &mdash; rozpietosc ' + _plnShort(spread[0].range) + ' (P5..P95)</div>'
        + '<div><b>Najtanszy srednio:</b> λ=' + cheap.lambda_param.toFixed(2)
          + ' &mdash; ' + _plnShort(cheap.cost_mean_pln) + '</div>'
        + '<div><b>Iteracje:</b> ' + (points[0].mc_iterations || iters) + ' na punkt</div>';
    }
  } catch (e) {
    if (empty) empty.textContent = 'Blad: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '&#9889; Odpal MC';
  }
}

function _plnShort(v) {
  if (!v) return '0 PLN';
  if (v >= 1e6) return (v / 1e6).toFixed(2).replace('.', ',') + ' mln PLN';
  if (v >= 1e3) return Math.round(v / 1e3) + ' tys. PLN';
  return Math.round(v) + ' PLN';
}

function _renderParetoMcChart(points) {
  const canvas = document.getElementById('paretoMcChart');
  if (!canvas) return;
  if (state.paretoMcInst) state.paretoMcInst.destroy();
  const ctx = canvas.getContext('2d');
  const labels = points.map(p => 'λ=' + p.lambda_param.toFixed(2));
  state.paretoMcInst = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'P5 (najlepszy przypadek)',
          data: points.map(p => p.cost_p5_pln),
          borderColor: '#10B981',
          backgroundColor: 'rgba(16,185,129,.08)',
          borderWidth: 1.5,
          pointRadius: 2,
          tension: .2,
          fill: false,
        },
        {
          label: 'P95 (najgorszy przypadek)',
          data: points.map(p => p.cost_p95_pln),
          borderColor: '#EF4444',
          backgroundColor: 'rgba(239,68,68,.15)',
          borderWidth: 1.5,
          pointRadius: 2,
          tension: .2,
          fill: '-1', // fill between P5 and P95 → confidence band
        },
        {
          label: 'Srednia MC',
          data: points.map(p => p.cost_mean_pln),
          borderColor: '#6366F1',
          backgroundColor: '#6366F1',
          borderWidth: 2,
          pointRadius: 3,
          tension: .2,
          fill: false,
        },
        {
          label: 'Baseline (solver)',
          data: points.map(p => p.total_cost_pln),
          borderColor: '#1B2A4A',
          borderDash: [6, 4],
          backgroundColor: '#1B2A4A',
          borderWidth: 2,
          pointRadius: 4,
          tension: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
        tooltip: {
          mode: 'index',
          intersect: false,
          callbacks: {
            label: (ctx) => ctx.dataset.label + ': ' + _plnShort(ctx.parsed.y),
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 } } },
        y: {
          grid: { color: '#F0F0F0' },
          ticks: {
            font: { size: 10 },
            callback: (v) => _plnShort(v),
          },
          title: { display: true, text: 'Koszt (PLN)', font: { size: 11 } },
        },
      },
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
    },
  });
}


/* ═══ Radar chart ═══ */
export function renderRadarChart(profiles) {
  const cfg = DOMAIN_CFG[state.currentDomain];
  if (state.radarChartInst) state.radarChartInst.destroy();
  const ctx = $('radarChart').getContext('2d');
  const active = profiles.filter(p => p.total_allocated_fraction > 0.001);
  const datasets = active.map((p, idx) => ({
    label:p.supplier_name, data:[p.cost_norm,p.time_norm,p.compliance_norm,p.esg_norm],
    borderColor:COLORS[idx%COLORS.length], backgroundColor:COLORS[idx%COLORS.length]+'22',
    borderWidth:2, pointRadius:4, pointBackgroundColor:COLORS[idx%COLORS.length],
  }));
  state.radarChartInst = new Chart(ctx, {
    type:'radar', data:{ labels:cfg.radarLabels, datasets },
    options:{responsive:true,scales:{r:{min:0,max:1,ticks:{stepSize:0.25,font:{size:10}},pointLabels:{font:{size:11,weight:'600'}},grid:{color:'#E5E7EB'}}},
      plugins:{legend:{position:'bottom',labels:{boxWidth:12,font:{size:11}}}}}
  });
}

/* ═══ Stealth mode ═══ */

export async function runStealth() {
  const cfg = DOMAIN_CFG[state.currentDomain];
  $('stealthContent').innerHTML = '<div style="color:var(--gold)">Uruchamianie diagnostyki...</div>';
  try {
    const [suppliers,demand] = await Promise.all([safeFetchJson(API+cfg.suppliersUrl), safeFetchJson(API+cfg.demandUrl)]);
    const body = { suppliers, demand, weights:getWeights(), mode:getMode(), max_vendor_share:getMaxVendorShare() };
    const s = await apiPost('/stealth', body);
    let html = '<div class="stealth-box">';
    html += '<span class="hl">=== FLOW PROCUREMENT SOLVER DIAGNOSTICS ['+state.currentDomain.toUpperCase()+'] ===</span>\n';
    html += 'Solver:  <span class="ok">'+s.solver_name+'</span>\nStatus:  <span class="ok">'+s.solver_status+'</span>\n';
    html += 'Time:    <span class="num">'+s.solve_time_ms.toFixed(2)+' ms</span>\nObj:     <span class="num">'+s.objective_value.toFixed(8)+'</span>\n\n';
    html += '<span class="hl">--- VARIABLES (non-zero) ---</span>\n';
    s.variables.filter(v=>v.value>1e-6).forEach(v=>{ html+='  '+v.name+' = <span class="num">'+v.value.toFixed(6)+'</span>\n'; });
    html += '\n<span class="hl">--- CONSTRAINTS ('+s.constraints.length+') ---</span>\n';
    s.constraints.slice(0,15).forEach(c=>{ html+='  ['+c.name+'] '+c.bound+'\n'; });
    if(s.constraints.length>15) html+='  ... +'+(s.constraints.length-15)+' more\n';
    if(s.raw_log) { html+='\n<span class="hl">--- RAW LOG ---</span>\n'+escapeHtml(s.raw_log.slice(0,2000)); }
    html += '</div>';
    $('stealthContent').innerHTML = html;
  } catch(e) { $('stealthContent').innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>'; }
}
export function escapeHtml(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

/* ═══ CSV Templates ═══ */

export function downloadTemplate(type) {
  const T = { suppliers:{ fn:'szablon_dostawcy.csv', h:'supplier_id,name,unit_cost,logistics_cost,lead_time_days,compliance_score,esg_score,min_order_qty,max_capacity,served_regions',
    r:['SUP-001,AutoParts Krakow,120.50,15.00,3.0,0.92,0.85,100,5000,"PL-MA,PL-SL"','SUP-002,TechMotors Wroclaw,135.00,12.00,2.5,0.88,0.90,50,3000,"PL-DS,PL-MA"'] },
    demand:{ fn:'szablon_zapotrzebowanie.csv', h:'product_id,demand_qty,destination_region', r:['IDX-10042,500,PL-MA','IDX-10043,300,PL-SL'] },
    p2p:{ fn:'szablon_log_p2p.csv', h:'case_id,activity,timestamp,resource,cost',
      r:['REQ-001,Utworzenie Zapotrzebowania,2026-03-01T08:00:00,Jan Kowalski,0','REQ-001,Sprawdzenie Budzetu,2026-03-01T10:30:00,Anna Nowak,0'] } };
  const tpl=T[type]; if(!tpl) return;
  const csv=tpl.h+'\n'+tpl.r.join('\n')+'\n';
  const blob=new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8;'}); const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=tpl.fn; a.click(); URL.revokeObjectURL(url);
}

/* ═══ Data source ═══ */
export async function checkDbStatus() { try { const d=await safeFetchJson(API+'/db/status'); state.dbAvailable=d.db_available; const b=$('dbBadge'); if(state.dbAvailable) { b.className='db-badge on'; b.textContent='● Baza polaczona'; } else { b.className='db-badge off'; b.textContent='● Brak bazy'; } } catch(e) { state.dbAvailable=false; } }
export function switchDataSource(src) { state.dataSource=src; $('dsDemo').classList.toggle('active',src==='demo'); $('dsDb').classList.toggle('active',src==='db'); $('uploadSection').classList.toggle('hidden',src==='demo'); $('dbSummary').classList.toggle('hidden',src==='demo'); $('historySection').classList.toggle('hidden',src==='demo'); if(src==='db') { if(!state.dbAvailable) $('dbSummaryText').textContent='Baza danych nie jest skonfigurowana.'; else { loadDbSummary(); loadHistory(); } } }
export async function loadDbSummary() { if(!state.dbAvailable) return; try { const [sup,dem]=await Promise.all([fetch(API+'/db/suppliers?domain='+encodeURIComponent(state.currentDomain)).then(r=>r.ok?r.json():{count:0}).catch(()=>({count:0})),fetch(API+'/db/demand?domain='+encodeURIComponent(state.currentDomain)).then(r=>r.ok?r.json():{count:0}).catch(()=>({count:0}))]); $('dbSummaryText').textContent='Domena "'+state.currentDomain+'": '+sup.count+' dostawcow, '+dem.count+' pozycji.'; } catch(e) { $('dbSummaryText').textContent='Blad ladowania danych.'; } }
export async function handleUpload(type, file) { if(!file) return; const rEl=$('result'+type.charAt(0).toUpperCase()+type.slice(1)); if(!rEl) return; rEl.innerHTML='<div class="upload-result" style="background:#DBEAFE;color:#1E40AF">Wysylanie...</div>'; const fd=new FormData(); fd.append('file',file); let url; const enc=encodeURIComponent(state.currentDomain); if(type==='suppliers') url=API+'/db/suppliers/upload?domain='+enc+'&replace=true'; else if(type==='demand') url=API+'/db/demand/upload?domain='+enc+'&replace=true'; else url=API+'/db/p2p-events/upload?dataset_name='+enc+'&replace=true'; try { const d=await safeFetchJson(url,{method:'POST',body:fd}); rEl.innerHTML='<div class="upload-result ok">OK: '+d.inserted+' wierszy z "'+d.filename+'"</div>'; loadDbSummary(); } catch(e) { rEl.innerHTML='<div class="upload-result err">'+e.message+'</div>'; } }
export async function seedDemoData() { if(!state.dbAvailable) { $('seedResult').textContent='Baza nie skonfigurowana.'; return; } $('seedResult').textContent='Seedowanie...'; try { const r1=await safeFetchJson(API+'/db/seed/'+encodeURIComponent(state.currentDomain),{method:'POST'}); const r2=await safeFetchJson(API+'/db/seed-p2p?dataset_name=demo',{method:'POST'}); $('seedResult').textContent='OK: Dostawcy: '+r1.suppliers_inserted+', popyt: '+r1.demand_inserted+', P2P: '+r2.events_inserted; loadDbSummary(); } catch(e) { $('seedResult').textContent=e.message; } }
export async function loadHistory() { if(!state.dbAvailable) return; try { const d=await safeFetchJson(API+'/db/results?domain='+encodeURIComponent(state.currentDomain)+'&limit=10'); if(!d.results||d.results.length===0) { $('historyContent').textContent='Brak wynikow.'; return; } let h='<table style="width:100%;font-size:12px"><thead><tr><th>ID</th><th>Data</th><th>Tryb</th><th>L</th><th>Cel</th><th>Alokacji</th></tr></thead><tbody>'; d.results.forEach(r=>{ const date=r.created_at?new Date(r.created_at).toLocaleString('pl'):'--'; h+='<tr style="cursor:pointer" onclick="loadHistoryResult('+r.id+')"><td>'+r.id+'</td><td>'+date+'</td><td><span class="tag tag-blue">'+(r.mode||'--')+'</span></td><td>'+(r.lambda_param!=null?r.lambda_param.toFixed(2):'--')+'</td><td style="font-weight:700">'+(r.objective_total!=null?r.objective_total.toFixed(6):'--')+'</td><td>'+(r.allocations_count||'--')+'</td></tr>'; }); h+='</tbody></table>'; $('historyContent').innerHTML=h; } catch(e) { $('historyContent').textContent='Blad: '+e.message; } }
export async function loadHistoryResult(id) { try { const d=await safeFetchJson(API+'/db/results/'+id); if(d.allocations) renderAllocTable(d.allocations); if(d.objective) { renderBars(d.objective); $('kObjTotal').textContent=fmt(d.objective.total,6); } } catch(e) { console.error(e); } }

/* ═══════════════════════════════════════════════════════════════════ */


/* ═══ WHAT-IF ═══ */
export async function loadWhatIfDemo() {
  $('whatifResult').innerHTML = '<div style="color:var(--gold)">Uruchamianie 3 scenariuszy demo...</div>';
  try {
    const data = await safeFetchJson(API + '/whatif/scenarios/demo?domain=' + state.currentDomain);
    renderWhatIfResult(data);
  } catch(e) {
    $('whatifResult').innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>';
  }
}

export async function runWhatIfCustom() {
  $('whatifResult').innerHTML = '<div style="color:var(--gold)">Uruchamianie scenariuszy...</div>';
  const cfg = DOMAIN_CFG[state.currentDomain];
  try {
    const [suppliers, demand] = await Promise.all([safeFetchJson(API+cfg.suppliersUrl), safeFetchJson(API+cfg.demandUrl)]);
    const scenarios = [1,2,3].map(i => ({
      label: $('scenarioColumns').children[i-1].querySelector('h4').textContent.replace('Scenariusz '+i+': ',''),
      lambda_param: parseFloat($('wi_lambda'+i).value),
      w_cost: parseFloat($('wi_wc'+i).value), w_time: parseFloat($('wi_wt'+i).value),
      w_compliance: parseFloat($('wi_ws'+i).value), w_esg: parseFloat($('wi_we'+i).value),
      mode: 'continuous', max_vendor_share: parseFloat($('wi_mvs'+i).value)/100,
    }));
    const data = await apiPost('/whatif/scenarios', { suppliers, demand, scenarios });
    renderWhatIfResult(data);
  } catch(e) { $('whatifResult').innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>'; }
}

export function renderWhatIfResult(data) {
  if (!data.scenarios || data.scenarios.length === 0) { $('whatifResult').innerHTML='Brak wynikow.'; return; }
  const sc = data.scenarios;
  const best = data.best_scenario;

  let html = '<div style="margin-bottom:12px;font-size:13px"><strong>Najlepszy scenariusz:</strong> <span style="color:var(--ok);font-weight:800">'+best+'</span> | Czas: '+data.total_time_ms+' ms</div>';

  // Comparison table
  html += '<div class="tbl-wrap"><table class="comparison-table"><thead><tr><th>Metryka</th>';
  sc.forEach(s => { html += '<th style="text-align:right">'+(s.label===best?'<span style="color:var(--ok)">★</span> ':'')+s.label+'</th>'; });
  html += '</tr></thead><tbody>';

  const metrics = [
    { key:'objective_total', label:'Funkcja celu', lower:true },
    { key:'cost_component', label:'Koszt', lower:true },
    { key:'time_component', label:'Czas', lower:true },
    { key:'total_cost_pln', label:'Koszt calkowity (PLN)', lower:true, fmtFn: v=>Number(v).toLocaleString('pl')+' PLN' },
    { key:'suppliers_used', label:'Dostawcow', lower:false },
    { key:'products_covered', label:'Produktow', lower:false },
    { key:'solve_time_ms', label:'Czas optymalizacji (ms)', lower:true },
  ];

  metrics.forEach(m => {
    const vals = sc.map(s => s[m.key] || 0);
    const bestVal = m.lower ? Math.min(...vals) : Math.max(...vals);
    const worstVal = m.lower ? Math.max(...vals) : Math.min(...vals);
    html += '<tr><td><strong>'+m.label+'</strong></td>';
    sc.forEach((s, i) => {
      const v = vals[i];
      const cls = v === bestVal ? 'best' : v === worstVal ? 'worst' : '';
      const display = m.fmtFn ? m.fmtFn(v) : (typeof v === 'number' ? v.toFixed(4) : v);
      html += '<td class="'+cls+'" style="text-align:right">'+display+'</td>';
    });
    html += '</tr>';
  });

  html += '</tbody></table></div>';
  $('whatifResult').innerHTML = html;
}


export async function loadWhatifDemo() {
  $('whatifInlineResult').innerHTML = '<div style="color:var(--gold)">Uruchamianie 3 scenariuszy...</div>';
  try {
    const data = await safeFetchJson(API + '/whatif/scenarios/demo?domain=' + state.currentDomain);
    renderWhatIfResult(data);
    $('whatifInlineResult').innerHTML = $('whatifResult').innerHTML;
  } catch(e) {
    $('whatifInlineResult').innerHTML = '<div style="color:var(--err)">Blad: '+e.message+'</div>';
  }
}


/* ═══ B3 — Chain What-If (cumulative scenarios) ═══ */

export async function runWhatifChainDemo() {
  const el = $('whatifChainResult');
  if (!el) return;
  el.innerHTML = '<div style="color:var(--gold)">Uruchamianie lancucha scenariuszy...</div>';
  try {
    const data = await safeFetchJson(API + '/whatif/chain/demo?domain=' + state.currentDomain);
    el.innerHTML = _renderWhatifChain(data);
  } catch (e) {
    el.innerHTML = '<div style="color:var(--err)">Blad: ' + e.message + '</div>';
  }
}

function _wicPln(v) {
  if (!v) return '0 PLN';
  if (v >= 1e6) return (v / 1e6).toFixed(2).replace('.', ',') + ' mln PLN';
  if (v >= 1e3) return Math.round(v / 1e3) + ' tys. PLN';
  return Math.round(v) + ' PLN';
}

function _renderWhatifChain(data) {
  const chain = data.chain || [];
  if (!chain.length) return '<div style="color:var(--txt2);font-size:12px">Brak wynikow.</div>';
  const steps = chain.map((step, i) => {
    const res = step.result || {};
    const costDelta = (step.delta_vs_prev || {}).total_cost_pln;
    const objDelta = (step.delta_vs_prev || {}).objective_total;
    let cls = 'start';
    let arrowHtml = '';
    let summary = i === 0
      ? 'Punkt startowy &mdash; reszta kroku porownuje sie wzgledem tego'
      : '';

    if (i > 0 && costDelta) {
      if (costDelta.direction === 'down') cls = 'better';
      else if (costDelta.direction === 'up') cls = 'worse';
      else cls = 'flat';
      const sign = costDelta.pct > 0 ? '+' : '';
      const arrow = costDelta.direction === 'up' ? '↑'
        : costDelta.direction === 'down' ? '↓' : '→';
      arrowHtml = '<span class="wic-arrow ' + costDelta.direction + '">'
        + arrow + ' ' + sign + costDelta.pct.toFixed(1) + '%</span>';
      const deltaParts = [];
      if (Object.keys(step.applied_delta || {}).length) {
        deltaParts.push('Zmiana: ' + _fmtDelta(step.applied_delta));
      }
      if (objDelta) {
        const objSign = objDelta.pct > 0 ? '+' : '';
        deltaParts.push('obj ' + objSign + objDelta.pct.toFixed(1) + '%');
      }
      summary = deltaParts.join(' &middot; ');
    }

    return '<div class="wic-step ' + cls + '">'
      + '<div class="wic-index">' + (i + 1) + '</div>'
      + '<div class="wic-body">'
        + '<div class="wic-label">' + _escWic(step.label) + '</div>'
        + '<div class="wic-delta-summary">' + summary + '</div>'
      + '</div>'
      + '<div class="wic-metric">'
        + '<div><span class="wic-cost">' + _wicPln(res.total_cost_pln) + '</span> ' + arrowHtml + '</div>'
        + '<div style="font-size:10px;color:var(--txt2)">dostawcow: ' + (res.suppliers_used || 0) + '</div>'
      + '</div>'
    + '</div>';
  }).join('');
  return '<div class="wic-list">' + steps + '</div>'
    + '<div style="font-size:10px;color:var(--txt2);margin-top:8px">'
    + chain.length + ' krokow &middot; ' + (data.total_time_ms || 0) + 'ms'
    + '</div>';
}

function _fmtDelta(d) {
  return Object.entries(d).map(([k, v]) => {
    if (typeof v === 'number') return k + '=' + (Number.isInteger(v) ? v : v.toFixed(2));
    return k + '=' + v;
  }).join(', ');
}

function _escWic(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}


/* ═══ ADVANCED CHARTS ═══ */
export async function loadXYPareto() {
  try {
    const data = await safeFetchJson(API + '/dashboard/pareto-xy/demo?domain=' + state.currentDomain);
    if (!data.points || data.points.length === 0) return;
    if (state.xyParetoInst) state.xyParetoInst.destroy();
    const ctx = $('chartXYPareto').getContext('2d');
    state.xyParetoInst = new Chart(ctx, {
      type: 'scatter',
      data: { datasets: [{
        label: 'Pareto Front (Koszt vs Jakosc)',
        data: data.points.map(p => ({ x: p.total_cost_pln, y: p.weighted_quality, lambda: p.lambda_param })),
        backgroundColor: data.points.map((_, i) => COLORS[i % COLORS.length]),
        borderColor: '#1B2A4A', borderWidth: 1, pointRadius: 7, pointHoverRadius: 10,
      }]},
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            label: ctx => 'L=' + ctx.raw.lambda.toFixed(2) + ' | Koszt: ' + Math.round(ctx.raw.x).toLocaleString('pl') + ' PLN | Jakosc: ' + ctx.raw.y.toFixed(4)
          }}
        },
        scales: {
          x: { title: { display: true, text: 'Koszt calkowity (PLN)', font: { size: 11 } }, ticks: { callback: v => (v/1000).toFixed(0)+'k' } },
          y: { title: { display: true, text: 'Srednia jakosc (compliance+ESG)', font: { size: 11 } } }
        }
      }
    });
  } catch(e) { console.error('XY Pareto error:', e); }
}

export async function loadDonut() {
  try {
    const data = await safeFetchJson(API + '/dashboard/donut/demo?domain=' + state.currentDomain);
    if (!data.segments || data.segments.length === 0) return;
    if (state.donutInst) state.donutInst.destroy();
    const ctx = $('chartDonut').getContext('2d');
    state.donutInst = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.segments.map(s => s.supplier_name),
        datasets: [{ data: data.segments.map(s => s.total_cost_pln), backgroundColor: COLORS.slice(0, data.segments.length),
                      borderWidth: 2, borderColor: '#fff' }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'right', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: { callbacks: { label: ctx => ctx.label + ': ' + Math.round(ctx.parsed).toLocaleString('pl') + ' PLN (' + (data.segments[ctx.dataIndex].fraction * 100).toFixed(1) + '%)' } }
        }
      }
    });
  } catch(e) { console.error('Donut error:', e); }
}

export async function loadSankey() {
  try {
    const data = await safeFetchJson(API + '/dashboard/sankey/demo?domain=' + state.currentDomain);
    if (!data.links || data.links.length === 0) { $('sankeyContainer').innerHTML='Brak danych.'; return; }
    const W = $('sankeyContainer').clientWidth || 700, H = 320;
    const leftNodes = data.nodes.filter(n => n.type === 'supplier');
    const rightNodes = data.nodes.filter(n => n.type === 'product');
    const maxFlow = Math.max(...data.links.map(l => l.value), 1);
    const lGap = H / (leftNodes.length + 1);
    const rGap = H / (rightNodes.length + 1);
    const nodePos = {};
    leftNodes.forEach((n, i) => { nodePos[n.id] = { x: 30, y: lGap * (i + 1) }; });
    rightNodes.forEach((n, i) => { nodePos[n.id] = { x: W - 120, y: rGap * (i + 1) }; });
    let svg = '<svg width="'+W+'" height="'+H+'" xmlns="http://www.w3.org/2000/svg">';
    // Links
    data.links.forEach((l, i) => {
      const s = nodePos[l.source], t = nodePos[l.target];
      if (!s || !t) return;
      const sw = Math.max(2, (l.value / maxFlow) * 20);
      const col = COLORS[i % COLORS.length] + '66';
      svg += '<path d="M'+(s.x+60)+','+s.y+' C'+(W/2)+','+s.y+' '+(W/2)+','+t.y+' '+(t.x-10)+','+t.y+'" fill="none" stroke="'+col+'" stroke-width="'+sw+'"/>';
    });
    // Nodes
    leftNodes.forEach(n => {
      const p = nodePos[n.id];
      svg += '<rect x="'+(p.x-10)+'" y="'+(p.y-12)+'" width="70" height="24" rx="4" fill="#1B2A4A"/>';
      svg += '<text x="'+(p.x+25)+'" y="'+(p.y+4)+'" fill="#fff" font-size="9" text-anchor="middle" font-weight="600">'+n.label.substring(0,10)+'</text>';
    });
    rightNodes.forEach(n => {
      const p = nodePos[n.id];
      svg += '<rect x="'+(p.x-10)+'" y="'+(p.y-12)+'" width="110" height="24" rx="4" fill="#D4A843"/>';
      svg += '<text x="'+(p.x+45)+'" y="'+(p.y+4)+'" fill="#1B2A4A" font-size="9" text-anchor="middle" font-weight="600">'+n.label.substring(0,14)+'</text>';
    });
    svg += '</svg>';
    $('sankeyContainer').innerHTML = svg;
  } catch(e) { $('sankeyContainer').innerHTML='<div style="color:var(--err)">'+e.message+'</div>'; }
}


export async function loadRiskHeatmap() {
  $('riskHeatmapContent').innerHTML = '<div style="color:var(--gold)">Ladowanie heatmap...</div>';
  try {
    const data = await safeFetchJson(API + '/risk/heatmap/demo?domain=' + state.currentDomain);
    if (!data.cells || data.cells.length === 0) { $('riskHeatmapContent').innerHTML='Brak danych.'; return; }
    const riskColor = s => s === 'critical' ? '#7C3AED' : s === 'high' ? '#EF4444' : s === 'medium' ? '#F59E0B' : '#10B981';
    const riskBg = s => s === 'critical' ? '#F3E8FF' : s === 'high' ? '#FEE2E2' : s === 'medium' ? '#FEF3C7' : '#D1FAE5';
    let html = '<div style="margin-bottom:12px;font-size:13px">';
    html += '<span style="font-weight:700">Ogolne ryzyko:</span> <span style="font-weight:800;color:'+riskColor(data.overall_risk_score>=0.75?'critical':data.overall_risk_score>=0.5?'high':data.overall_risk_score>=0.25?'medium':'low')+'">' + data.overall_risk_score.toFixed(4) + '</span>';
    html += ' | <span style="color:#7C3AED">●</span> Krytyczne: '+data.critical_count;
    html += ' | <span style="color:#EF4444">●</span> Wysokie: '+data.high_count+'</div>';
    html += '<div class="tbl-wrap"><table><thead><tr><th>Dostawca</th><th>Produkt</th><th style="text-align:right">Ryzyko</th><th style="text-align:right">Single-src</th><th style="text-align:right">Kapacytet</th><th style="text-align:right">ESG risk</th><th>Poziom</th></tr></thead><tbody>';
    data.cells.forEach(c => {
      html += '<tr style="background:'+riskBg(c.risk_label)+'"><td><a href="#" onclick="event.preventDefault();switchTab(\'suppliers\');setTimeout(()=>suppShowDetail(\''+(c.supplier_id||'')+'\'),200)" style="color:inherit;font-weight:700;text-decoration:underline dotted">'+c.supplier_name+'</a></td><td>'+c.product_id+'</td>';
      html += '<td style="text-align:right;font-weight:700;color:'+riskColor(c.risk_label)+'">'+c.risk_score.toFixed(4)+'</td>';
      html += '<td style="text-align:right">'+c.single_source_risk.toFixed(2)+'</td>';
      html += '<td style="text-align:right">'+c.capacity_utilization.toFixed(2)+'</td>';
      html += '<td style="text-align:right">'+c.esg_risk.toFixed(2)+'</td>';
      html += '<td><span style="background:'+riskColor(c.risk_label)+';color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700">'+c.risk_label.toUpperCase()+'</span></td></tr>';
    });
    html += '</tbody></table></div>';
    $('riskHeatmapContent').innerHTML = html;
  } catch(e) { $('riskHeatmapContent').innerHTML='<div style="color:var(--err)">'+e.message+'</div>'; }
}

export async function loadMonteCarlo() {
  $('mcStats').innerHTML = '<span style="color:var(--gold)">Symulacja Monte Carlo...</span>';
  try {
    const data = await safeFetchJson(API + '/risk/monte-carlo/demo?domain=' + state.currentDomain + '&n_iterations=500');
    // Histogram
    if (state.mcHistInst) state.mcHistInst.destroy();
    const ctx = $('chartMonteCarlo').getContext('2d');
    const bins = data.cost_histogram || [];
    const p5 = data.cost_p5_pln, p95 = data.cost_p95_pln;
    const binW = bins.length > 0 ? (p95 - p5) / bins.length : 1;
    state.mcHistInst = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: bins.map((_, i) => Math.round(p5 + i * binW).toLocaleString('pl')),
        datasets: [{ label: 'Prawdopodobienstwo', data: bins.map(b => +(b * 100).toFixed(1)),
          backgroundColor: bins.map((_, i) => i < bins.length * 0.05 || i > bins.length * 0.95 ? '#EF444488' : '#D4A84388'),
          borderColor: '#1B2A4A', borderWidth: 1 }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ctx.parsed.y.toFixed(1) + '%' } } },
        scales: { x: { title: { display: true, text: 'Koszt (PLN)', font: { size: 10 } }, ticks: { maxRotation: 45, font: { size: 9 } } },
                  y: { title: { display: true, text: 'Czestotliwosc (%)', font: { size: 10 } } } }
      }
    });
    // Stats
    $('mcStats').innerHTML = '<strong>N='+data.n_iterations+'</strong> | Feasible: '+pct(data.feasible_rate)
      +' | Koszt: <strong>'+data.cost_mean_pln.toLocaleString('pl')+' PLN</strong> (std: '+data.cost_std_pln.toLocaleString('pl')+')'
      +' | P5: '+data.cost_p5_pln.toLocaleString('pl')+' | P95: '+data.cost_p95_pln.toLocaleString('pl')
      +' | <span style="color:var(--ok);font-weight:700">Stabilnosc portfela: '+pct(data.robustness_score)+'</span>';
    // Stability chart
    if (state.stabilityInst) state.stabilityInst.destroy();
    const stab = data.supplier_stability || [];
    if (stab.length > 0) {
      const ctx2 = $('chartStability').getContext('2d');
      state.stabilityInst = new Chart(ctx2, {
        type: 'bar',
        data: {
          labels: stab.map(s => s.supplier_name),
          datasets: [{ label: 'Wskaznik wyboru', data: stab.map(s => +(s.selection_rate * 100).toFixed(1)),
            backgroundColor: stab.map((_, i) => COLORS[i % COLORS.length]), borderWidth: 0 }]
        },
        options: {
          indexAxis: 'y', responsive: true,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ctx.parsed.x.toFixed(1) + '% iteracji' } } },
          scales: { x: { max: 100, title: { display: true, text: 'Wybor (%)', font: { size: 10 } } } }
        }
      });
    }
  } catch(e) { $('mcStats').innerHTML='<span style="color:var(--err)">'+e.message+'</span>'; }
}

export async function loadNegotiation() {
  $('negotiationContent').innerHTML = '<div style="color:var(--gold)">Analiza negocjacyjna...</div>';
  try {
    const data = await safeFetchJson(API + '/risk/negotiation/demo?domain=' + state.currentDomain);
    if (!data.targets || data.targets.length === 0) { $('negotiationContent').innerHTML='Brak celow.'; return; }
    const prioColor = p => p === 'high' ? '#EF4444' : p === 'medium' ? '#F59E0B' : '#10B981';
    let html = '<div style="margin-bottom:12px;font-size:13px">';
    html += '<span style="font-weight:700">Szacowane oszczednosci:</span> <span style="font-weight:800;color:var(--ok)">'+data.total_estimated_savings_pln.toLocaleString('pl')+' PLN</span>';
    html += ' | Analizowano: '+data.analyzed_suppliers+' dostawcow</div>';
    html += '<div class="tbl-wrap"><table><thead><tr><th>Dostawca</th><th style="text-align:right">Udzial</th><th style="text-align:right">Koszt</th><th style="text-align:right">Cel redukcji</th><th style="text-align:right">Oszczednosci</th><th>Priorytet</th><th>Uzasadnienie</th></tr></thead><tbody>';
    data.targets.forEach(t => {
      html += '<tr><td><strong>'+t.supplier_name+'</strong></td>';
      html += '<td style="text-align:right">'+t.current_share_pct.toFixed(1)+'%</td>';
      html += '<td style="text-align:right">'+t.current_total_cost_pln.toLocaleString('pl')+' PLN</td>';
      html += '<td style="text-align:right;font-weight:700">-'+t.target_reduction_pct.toFixed(1)+'%</td>';
      html += '<td style="text-align:right;color:var(--ok);font-weight:700">'+t.estimated_saving_pln.toLocaleString('pl')+' PLN</td>';
      html += '<td><span style="background:'+prioColor(t.negotiation_priority)+';color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700">'+t.negotiation_priority.toUpperCase()+'</span></td>';
      html += '<td style="font-size:12px;color:var(--txt2)">'+t.rationale+'</td></tr>';
    });
    html += '</tbody></table></div>';
    $('negotiationContent').innerHTML = html;
  } catch(e) { $('negotiationContent').innerHTML='<div style="color:var(--err)">'+e.message+'</div>'; }
}

/* ═══════════════════════════════════════════════════════════════════ */
/* OPTIMIZED BUYING MODULE                                             */
/* ═══════════════════════════════════════════════════════════════════ */

let obCatalog = [];
let obCategories = [];
let obCart = []; // [{id, quantity}]
let obCartState = null;
let obActiveCategory = 'all';

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


