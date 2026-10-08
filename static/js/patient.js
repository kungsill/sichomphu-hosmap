import { IsoMap } from './iso.js';
import { $, api, esc, liveStream, stateClass, stepperHtml } from './common.js';

const token = decodeURIComponent(location.pathname.split('/').pop());
const iso = new IsoMap($('#map'), { padTop: 60, padBottom: 0, labelMode: 'names', walkSpeed: 2.4 });
let doc = null;
let view = null;
let accessible = false;
try { accessible = localStorage.getItem('nav.accessible') === '1'; } catch { /* storage ไม่พร้อม */ }
let stop = null;
let lastRouteKey = '';
let showHistory = false;

async function init() {
  try {
    const cfg = await api('/api/config');
    $('#hospital').textContent = cfg.hospital;
    doc = await api('/api/map');
    iso.setMap(doc);
    connect();
  } catch (err) {
    fail('ไม่สามารถโหลดข้อมูลได้ กรุณาลองใหม่อีกครั้ง');
  }
}

function connect() {
  stop?.();
  // ตรวจสอบ token ก่อนเปิดการเชื่อมต่อสด
  api(`/api/t/${encodeURIComponent(token)}?accessible=${accessible ? 1 : 0}`)
    .then((v) => {
      onView(v);
      stop = liveStream(`/api/t/${encodeURIComponent(token)}/stream?accessible=${accessible ? 1 : 0}`, onView,
        (ok) => $('#dot').classList.toggle('bad', !ok));
    })
    .catch((err) => fail(err.message || 'ใบนำทางไม่ถูกต้องหรือหมดอายุ'));
}

function fail(msg) {
  $('#sheet').innerHTML = `<div class="grab"></div><div class="notice"><img src="/static/img/logo.png" alt=""><h2>${esc(msg)}</h2>
    <p class="muted">กรุณาติดต่อเจ้าหน้าที่ประชาสัมพันธ์ หรือสแกน QR Code บนใบนำทางใหม่อีกครั้ง</p></div>`;
}

function onView(v) {
  if (!v) return;
  view = v;
  $('#queue').textContent = v.q;
  $('#clock').textContent = v.time || '';
  document.title = `คิว ${v.q} — ใบนำทาง`;

  // แผนที่: แสดงผู้อื่นแบบนิรนาม + ตัวเราสีชมพู
  iso.setCounts(v.rooms);
  iso.setCrowd(v.rooms, v.room);
  const route = v.route && v.route.ok ? v.route : null;
  const me = { vn: 'me', q: v.q, label: v.label, room: v.room, state: v.state, walking: !!route,
    route: route ? route.points : null, route_id: route ? hashKey(route.points) : 0, service_room: v.service_room };
  iso.setPatients(v.state === 'finished' && !route ? [] : [me], false);
  const person = iso.persons.get('me');
  if (person) { person.me = true; }
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

function renderFloors(route) {
  const floors = route ? [...new Set(route.points.map((p) => p[0]))] : [];
  const tabs = $('#floorTabs');
  if (floors.length < 2) { tabs.classList.add('hidden'); return; }
  tabs.classList.remove('hidden');
  tabs.innerHTML = floors.map((id, i) => {
    const f = doc.floors.find((x) => x.id === id);
    const b = doc.buildings.find((x) => x.id === f?.building_id);
    const label = doc.buildings.length > 1 ? `${b?.name || ''} ${f?.name || ''}` : (f?.name || id);
    return `<button data-f="${esc(id)}" class="${iso.floorId === id ? 'active' : ''}">${i + 1}. ${esc(label)}</button>`;
  }).join('');
  tabs.onclick = (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    iso.setFloor(b.dataset.f);
    [...tabs.children].forEach((x) => x.classList.toggle('active', x === b));
  };
}

function renderSheet() {
  const v = view;
  const cls = stateClass({ ...v, dep: v.dest });
  const dest = v.destination;
  let statusText = v.label;
  let sub = '';
  if (v.state === 'waiting' && v.pos) sub = `คาดว่ารอประมาณ ${v.est ?? '-'} นาที`;
  if (v.state === 'in_service') sub = 'กรุณาปฏิบัติตามคำแนะนำของเจ้าหน้าที่';
  if (v.state === 'finished') { statusText = 'เสร็จสิ้นการรับบริการ'; sub = 'ขอบคุณที่ใช้บริการ ขอให้หายป่วยไว ๆ'; }
  const route = v.route && v.route.ok ? v.route : null;
  const pend = (v.pending || []).filter((p) => p.status !== 'done');
  $('#sheet').innerHTML = `
    <div class="grab"></div>
    <div class="dest">
      <div class="icon"><svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6a2.5 2.5 0 0 1 0 5.5z"/></svg></div>
      <div style="min-width:0">
        <div class="lbl">${v.state === 'finished' ? 'ทางออก' : 'ปลายทางของคุณ'}</div>
        <div class="nm">${esc(v.state === 'finished' ? 'ประตูทางเข้าหลัก' : (dest?.name || v.dest_name || '-'))}</div>
        ${dest ? `<div class="fl">${esc(dest.floor)}${dest.wait_room && dest.wait_room !== dest.name ? ` · นั่งรอที่${esc(dest.wait_room)}` : ''}</div>` : ''}
      </div>
    </div>
    <div class="bigstatus ${cls}"><span>${esc(statusText)}${sub ? `<br><small>${esc(sub)}</small>` : ''}</span>${v.pos ? `<span class="qpos"><small>คิวที่</small><b>${v.pos}</b></span>` : ''}</div>
    ${stepperHtml(v.stages)}
    ${pend.length ? `<div class="section-title">รายการที่ต้องไปต่อ</div><div class="pending">${pend.map((p) => `<span class="${p.status}">${esc(p.name)} · ${p.status === 'received' ? 'กำลังตรวจ' : 'รอตรวจ'}</span>`).join('')}</div>` : ''}
    ${route ? `<div class="section-title"><span>เส้นทาง ~${route.distance} เมตร (${route.minutes} นาที)</span>
      <label class="toggle"><input type="checkbox" id="acc" ${accessible ? 'checked' : ''}><span class="sw"></span>รถเข็น</label></div>
      <ol class="steps-text">${route.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>`
      : (v.route && !v.route.ok ? `<div class="section-title">เส้นทาง</div><div class="muted">${esc(v.route.reason)}</div>
      <label class="toggle" style="margin-top:8px"><input type="checkbox" id="acc" ${accessible ? 'checked' : ''}><span class="sw"></span>เส้นทางสำหรับรถเข็น</label>` : '')}
    <div class="section-title"><span>ประวัติการรับบริการวันนี้</span><button class="btn ghost" id="hist">${showHistory ? 'ซ่อน' : 'แสดง'}</button></div>
    <ul class="timeline ${showHistory ? '' : 'hidden'}">${(v.events || []).slice().reverse().map((e) => `<li><time>${esc(e.time)}</time><span>${esc(e.text)}</span></li>`).join('')}</ul>
    <p class="muted" style="font-size:12px;margin-top:14px">HN ${esc(v.hn_masked)} · หน้านี้อัปเดตอัตโนมัติตามการส่งตรวจใน HOSxP ไม่ต้องรีเฟรช<br>ภาพแผนที่เป็นแผนผังโดยประมาณ หากไม่แน่ใจกรุณาสอบถามเจ้าหน้าที่</p>`;
  const acc = $('#acc');
  if (acc) acc.onchange = (e) => {
    accessible = e.target.checked;
    try { localStorage.setItem('nav.accessible', accessible ? '1' : '0'); } catch { /* ไม่เป็นไร */ }
    lastRouteKey = '';
    connect();
  };
  $('#hist').onclick = () => { showHistory = !showHistory; renderSheet(); };
}

$('#zin').onclick = () => iso.zoomSmooth(1.35);
$('#zout').onclick = () => iso.zoomSmooth(1 / 1.35);
$('#rotr').onclick = () => iso.rotate(1);
$('#home').onclick = () => { iso.resetView(); focusRoute(view?.route?.ok ? view.route : null); };

init();
