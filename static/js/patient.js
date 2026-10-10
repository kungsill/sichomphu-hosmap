import { IsoMap } from './iso.js';
import { $, api, esc, liveStream, stateClass } from './common.js';

const token = decodeURIComponent(location.pathname.split('/').pop());
const iso = new IsoMap($('#map'), { padTop: 60, padBottom: 0, labelMode: 'names', walkSpeed: 2.4 });
let doc = null;
let view = null;
let stop = null;
let lastRouteKey = '';
let showHistory = false;

// ------------------------------------------------------------------ การตั้งค่าที่จำไว้ในเครื่อง
const pref = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const setPref = (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage ไม่พร้อม */ } };
let accessible = pref('nav.accessible', '0') === '1';
let lang = pref('nav.lang', (navigator.language || 'th').startsWith('th') ? 'th' : 'en');
let bigText = pref('nav.big', '0') === '1';

// ------------------------------------------------------------------ ข้อความ 2 ภาษา (ชื่อห้องเป็นภาษาไทยตามป้ายจริง)
const T = {
  th: {
    yourQueue: 'คิวของคุณ', guide: 'ใบนำทางผู้ป่วย', dest: 'ปลายทางของคุณ', exitLbl: 'ทางออก', exitName: 'ประตูทางเข้าโรงพยาบาล',
    waitAt: 'นั่งรอที่', queueNo: 'คิวที่', estWait: (m) => `คาดว่ารอประมาณ ${m} นาที`, follow: 'กรุณาปฏิบัติตามคำแนะนำของเจ้าหน้าที่',
    done: 'เสร็จสิ้นการรับบริการ', thanks: 'ขอบคุณที่ใช้บริการ ขอให้หายป่วยไว ๆ', next: 'รายการที่ต้องไปต่อ',
    examining: 'กำลังตรวจ', pendingExam: 'รอตรวจ', route: (m, min) => `เส้นทาง ~${m} เมตร (${min} นาที)`, wheel: 'รถเข็น',
    wheelRoute: 'เส้นทางสำหรับรถเข็น', routeTitle: 'เส้นทาง', history: 'ประวัติการรับบริการวันนี้', show: 'แสดง', hide: 'ซ่อน',
    foot: 'หน้านี้อัปเดตอัตโนมัติตามการส่งตรวจใน HOSxP ไม่ต้องรีเฟรช', approx: 'ภาพแผนที่เป็นแผนผังโดยประมาณ หากไม่แน่ใจกรุณาสอบถามเจ้าหน้าที่',
    loadErr: 'ไม่สามารถโหลดข้อมูลได้ กรุณาลองใหม่อีกครั้ง', badToken: 'ใบนำทางไม่ถูกต้องหรือหมดอายุ',
    contact: 'กรุณาติดต่อเจ้าหน้าที่ประชาสัมพันธ์ หรือสแกน QR Code ใหม่อีกครั้ง', campus: 'ภาพรวม รพ.', big: 'ตัวอักษรใหญ่',
    notOnMap: 'จุดบริการนี้ยังไม่มีในแผนที่ กรุณาสอบถามเจ้าหน้าที่ใกล้ตัวท่าน',
    stages: { register: 'ลงทะเบียน', screening: 'คัดกรอง', doctor: 'พบแพทย์', lab: 'LAB', xray: 'X-ray', other: 'รับบริการ', finance: 'การเงิน', pharmacy: 'รับยา', home: 'กลับบ้าน' },
  },
  en: {
    yourQueue: 'Your queue', guide: 'Patient navigation', dest: 'Your destination', exitLbl: 'Exit', exitName: 'Hospital main gate',
    waitAt: 'Wait at', queueNo: 'Queue', estWait: (m) => `Estimated wait ~${m} min`, follow: 'Please follow the staff instructions',
    done: 'Visit completed', thanks: 'Thank you. Get well soon!', next: 'Next stops',
    examining: 'in progress', pendingExam: 'pending', route: (m, min) => `Route ~${m} m (${min} min)`, wheel: 'Wheelchair',
    wheelRoute: 'Wheelchair-accessible route', routeTitle: 'Route', history: "Today's visit history", show: 'Show', hide: 'Hide',
    foot: 'This page updates automatically from HOSxP — no need to refresh.', approx: 'The map is approximate. If unsure, please ask our staff.',
    loadErr: 'Could not load data. Please try again.', badToken: 'This link is invalid or has expired.',
    contact: 'Please ask the information desk, or scan the QR code again.', campus: 'Hospital campus', big: 'Large text',
    notOnMap: 'This service point is not on the map yet. Please ask a nearby staff member.',
    stages: { register: 'Register', screening: 'Screening', doctor: 'Doctor', lab: 'LAB', xray: 'X-ray', other: 'Service', finance: 'Payment', pharmacy: 'Pharmacy', home: 'Home' },
  },
};
const t = () => T[lang];

function stepText(d) {
  if (lang === 'th') return null; // ใช้ข้อความไทยจากเซิร์ฟเวอร์
  const turn = d.turn === 'right' ? 'turn right' : d.turn === 'left' ? 'turn left' : '';
  switch (d.t) {
    case 'leave': return `Leave ${d.name}`;
    case 'start': return `Start at ${d.name}`;
    case 'walk': return `Walk straight about ${d.m} m${turn ? `, then ${turn}` : ''}${d.at ? ` at ${d.at}` : ''}`;
    case 'exit': return `Exit ${d.name} to the outdoor walkway`;
    case 'enter': return `Walk to and enter ${d.name}`;
    case 'vertical': return `Take the ${d.via === 'elevator' ? 'elevator' : d.via === 'ramp' ? 'ramp' : 'stairs'} to ${d.floor}`;
    default: return `Arrive at ${d.name}`;
  }
}

function statusLabel(v) {
  if (lang === 'th') return v.label;
  const name = v.dest_name || '';
  if (v.state === 'finished') return 'Heading home';
  if (v.state === 'in_service') return `Being served · ${name}`;
  if (v.state === 'service_done') return `Waiting for the next step · ${name}`;
  if (v.walking || v.label?.startsWith('เดินไป')) return `Please go to ${name}`;
  return v.pos ? `Waiting · ${name} · #${v.pos}` : `Waiting · ${name}`;
}

function stepper(stages) {
  return `<div class="stepper">${(stages || []).map((s) => `<div class="step ${s.status}"><i></i><span>${esc(t().stages[s.key] || s.label)}</span></div>`).join('')}</div>`;
}

function applyPrefs() {
  document.body.classList.toggle('bigtext', bigText);
  document.documentElement.lang = lang;
  $('#queueLbl').textContent = t().yourQueue;
  $('#guideLbl').textContent = t().guide;
  iso.opts.labelScale = bigText ? 1.25 : 1;
}

// ------------------------------------------------------------------ โหลดข้อมูล
async function init() {
  applyPrefs();
  try {
    const cfg = await api('/api/config');
    $('#hospital').textContent = cfg.hospital;
    doc = await api('/api/map');
    iso.setMap(doc);
    connect();
  } catch {
    fail(t().loadErr);
  }
}

function connect() {
  stop?.();
  api(`/api/t/${encodeURIComponent(token)}?accessible=${accessible ? 1 : 0}`)
    .then((v) => {
      onView(v);
      stop = liveStream(`/api/t/${encodeURIComponent(token)}/stream?accessible=${accessible ? 1 : 0}`, onView,
        (ok) => $('#dot').classList.toggle('bad', !ok));
    })
    .catch((err) => fail(err.message || t().badToken));
}

function fail(msg) {
  $('#sheet').innerHTML = `<div class="grab"></div><div class="notice"><img src="/static/img/logo.png" alt=""><h2>${esc(msg)}</h2>
    <p class="muted">${esc(t().contact)}</p></div>`;
}

function onView(v) {
  if (!v) return;
  view = v;
  $('#queue').textContent = v.q;
  $('#clock').textContent = v.time || '';
  document.title = `${lang === 'th' ? 'คิว' : 'Queue'} ${v.q} — ${t().guide}`;

  // แผนที่: แสดงผู้อื่นแบบนิรนาม + ตัวเราสีชมพู
  iso.setCounts(v.rooms);
  iso.setCrowd(v.rooms, v.room);
  const route = v.route && v.route.ok ? v.route : null;
  const me = { vn: 'me', q: v.q, label: statusLabel(v), room: v.room, state: v.state, walking: !!route,
    route: route ? route.points : null, route_id: route ? hashKey(route.points) : 0, service_room: v.service_room };
  iso.setPatients(v.state === 'finished' && !route ? [] : [me], false);
  const person = iso.persons.get('me');
  if (person) person.me = true;
  iso.setSelected(null);
  iso.setRoute(route ? { points: route.points, dest: route.points[route.points.length - 1] } : null);

  const key = route ? route.points.map((p) => p.join(',')).join(';') : `room:${v.room}`;
  if (key !== lastRouteKey) {
    lastRouteKey = key;
    focusRoute(route);
  }
  renderFloors(route);
  renderSheet();
}

function hashKey(points) {
  let h = 0;
  for (const p of points) for (const c of p.join(',')) h = (h * 31 + c.charCodeAt(0)) | 0;
  return h;
}

function focusRoute(route) {
  const pts = route?.points;
  let floor = pts?.[0]?.[0];
  if (!floor && view?.room) floor = doc.rooms.find((r) => r.id === view.room)?.floor_id;
  if (floor) iso.setFloor(floor);
  iso.fit(24);
  if (pts?.length) {
    const here = pts.filter((p) => p[0] === iso.floorId);
    const xs = here.map((p) => p[1]), ys = here.map((p) => p[2]);
    if (xs.length) {
      iso.focus((Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2);
      const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 12);
      iso.scale = Math.max(iso.scale, Math.min(26, (iso.w * 0.75) / (span * 1.2)));
    }
  }
}

function floorLabel(id) {
  const f = doc.floors.find((x) => x.id === id);
  if (f?.style === 'campus') return t().campus;
  const b = doc.buildings.find((x) => x.id === f?.building_id);
  const many = doc.floors.filter((x) => x.building_id === f?.building_id).length > 1;
  return many ? `${b?.name || ''} ${f?.name || ''}` : (b?.name || f?.name || id);
}

function renderFloors(route) {
  const floors = route ? [...new Set(route.points.map((p) => p[0]))] : [];
  const tabs = $('#floorTabs');
  if (floors.length < 2) { tabs.classList.add('hidden'); return; }
  tabs.classList.remove('hidden');
  tabs.innerHTML = floors.map((id, i) => `<button data-f="${esc(id)}" class="${iso.floorId === id ? 'active' : ''}">${i + 1}. ${esc(floorLabel(id))}</button>`).join('');
  tabs.onclick = (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    iso.setFloor(b.dataset.f);
    [...tabs.children].forEach((x) => x.classList.toggle('active', x === b));
  };
}

function renderSheet() {
  const v = view;
  if (!v) return;
  const L = t();
  const cls = stateClass({ ...v, dep: v.dest });
  const dest = v.destination;
  let statusText = statusLabel(v);
  let sub = '';
  if (v.state === 'waiting' && v.pos) sub = L.estWait(v.est ?? '-');
  if (v.state === 'in_service') sub = L.follow;
  if (v.state === 'finished') { statusText = L.done; sub = L.thanks; }
  const route = v.route && v.route.ok ? v.route : null;
  const pend = (v.pending || []).filter((p) => p.status !== 'done');
  const steps = route ? (route.steps_data && lang !== 'th' ? route.steps_data.map(stepText) : route.steps) : [];
  $('#sheet').innerHTML = `
    <div class="grab"></div>
    <div class="prefs">
      <button class="pref ${lang === 'th' ? 'on' : ''}" data-lang="th">ไทย</button>
      <button class="pref ${lang === 'en' ? 'on' : ''}" data-lang="en">EN</button>
      <button class="pref ${bigText ? 'on' : ''}" id="bigBtn" aria-pressed="${bigText}" title="${esc(L.big)}">ก<span style="font-size:1.3em">ก</span> ${esc(L.big)}</button>
    </div>
    <div class="dest">
      <div class="icon"><svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z"/></svg></div>
      <div style="min-width:0">
        <div class="lbl">${v.state === 'finished' ? L.exitLbl : L.dest}</div>
        <div class="nm">${esc(v.state === 'finished' ? L.exitName : (dest?.name || v.dest_name || '-'))}</div>
        ${dest ? `<div class="fl">${esc(dest.floor)}${dest.wait_room && dest.wait_room !== dest.name ? ` · ${L.waitAt} ${esc(dest.wait_room)}` : ''}</div>` : ''}
      </div>
    </div>
    <div class="bigstatus ${cls}"><span>${esc(statusText)}${sub ? `<br><small>${esc(sub)}</small>` : ''}</span>${v.pos ? `<span class="qpos"><small>${L.queueNo}</small><b>${v.pos}</b></span>` : ''}</div>
    ${!v.room && v.state !== 'finished' ? `<div class="notice-inline">${esc(L.notOnMap)}</div>` : ''}
    ${stepper(v.stages)}
    ${pend.length ? `<div class="section-title">${L.next}</div><div class="pending">${pend.map((p) => `<span class="${p.status}">${esc(p.name)} · ${p.status === 'received' ? L.examining : L.pendingExam}</span>`).join('')}</div>` : ''}
    ${route ? `<div class="section-title"><span>${L.route(route.distance, route.minutes)}</span>
      <label class="toggle"><input type="checkbox" id="acc" ${accessible ? 'checked' : ''}><span class="sw"></span>${L.wheel}</label></div>
      <ol class="steps-text">${steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>`
      : (v.route && !v.route.ok ? `<div class="section-title">${L.routeTitle}</div><div class="muted">${esc(v.route.reason)}</div>
      <label class="toggle" style="margin-top:8px"><input type="checkbox" id="acc" ${accessible ? 'checked' : ''}><span class="sw"></span>${L.wheelRoute}</label>` : '')}
    <div class="section-title"><span>${L.history}</span><button class="btn ghost" id="hist">${showHistory ? L.hide : L.show}</button></div>
    <ul class="timeline ${showHistory ? '' : 'hidden'}">${(v.events || []).slice().reverse().map((e) => `<li><time>${esc(e.time)}</time><span>${esc(e.text)}</span></li>`).join('')}</ul>
    <p class="muted" style="font-size:12px;margin-top:14px">HN ${esc(v.hn_masked)} · ${L.foot}<br>${L.approx}</p>`;
  const acc = $('#acc');
  if (acc) acc.onchange = (e) => {
    accessible = e.target.checked;
    setPref('nav.accessible', accessible ? '1' : '0');
    lastRouteKey = '';
    connect();
  };
  $('#hist').onclick = () => { showHistory = !showHistory; renderSheet(); };
  document.querySelectorAll('[data-lang]').forEach((b) => {
    b.onclick = () => { lang = b.dataset.lang; setPref('nav.lang', lang); applyPrefs(); onView(view); };
  });
  $('#bigBtn').onclick = () => { bigText = !bigText; setPref('nav.big', bigText ? '1' : '0'); applyPrefs(); renderSheet(); iso.dirty = true; };
}

$('#zin').onclick = () => iso.zoomSmooth(1.35);
$('#zout').onclick = () => iso.zoomSmooth(1 / 1.35);
$('#rotr').onclick = () => iso.rotate(1);
$('#home').onclick = () => { iso.resetView(); focusRoute(view?.route?.ok ? view.route : null); };

init();
