import { IsoMap, densityText } from './iso.js';
import { $, api, esc, liveStream, sexAge, stateClass, stepperHtml, toast } from './common.js';

const iso = new IsoMap($('#map'), { padTop: 0, padBottom: 0, dimOthers: false });
let doc = null;
let snap = null;
let first = true;
let selected = null;
let selectedRoom = null;
let streamOk = true;
let floorBuilding = {};

const narrow = () => window.innerWidth < 900;
function updatePadding() {
  iso.opts.padTop = narrow() ? 250 : 0;
  iso.opts.padBottom = narrow() ? 190 : 0;
}
updatePadding();
window.addEventListener('resize', updatePadding);

// ตัวเลขนับขึ้น/ลงแบบนุ่มนวล
function animateNumber(el, to) {
  const from = Number(el.dataset.v ?? el.textContent) || 0;
  el.dataset.v = to;
  if (from === to) { el.textContent = to; return; }
  const t0 = performance.now(), dur = 700;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

async function init() {
  const cfg = await api('/api/config');
  $('#hospital').textContent = cfg.hospital;
  $('#loaderName').textContent = cfg.hospital;
  document.title = `แผนที่ผู้ป่วย — ${cfg.hospital}`;
  if (cfg.demo) $('#rushWrap').classList.remove('hidden');
  setDoc(await api('/api/map'));
  liveStream('/api/stream', onSnapshot, (ok) => { streamOk = ok; updateHealth(); });
}

function setDoc(d) {
  doc = d;
  floorBuilding = Object.fromEntries(doc.floors.map((f) => [f.id, f.building_id]));
  iso.setMap(doc);
  renderZones();
}

// ------------------------------------------------------------------ โซน
function zoneName(f) {
  if (!f) return '';
  const b = doc.buildings.find((x) => x.id === f.building_id);
  if (doc.buildings.length < 2) return f.name;
  const many = doc.floors.filter((x) => x.building_id === f.building_id).length > 1;
  return many ? `${b?.name || ''} ${f.name}` : (b?.name || f.name);
}

let floorListener = false;
function renderZones() {
  const box = $('#zones');
  box.innerHTML = doc.floors.map((f) => `<button class="zone" data-f="${esc(f.id)}"><span>${esc(zoneName(f))}</span><span class="n" data-count="${esc(f.id)}">0</span></button>`).join('');
  box.onclick = (e) => {
    const b = e.target.closest('.zone');
    if (b) iso.setFloor(b.dataset.f);
  };
  if (!floorListener) { iso.on('floor', onFloorChange); floorListener = true; }
  onFloorChange(iso.floorId);
  if (snap) updateZoneCounts();
}

function onFloorChange(id) {
  const f = doc.floors.find((x) => x.id === id);
  const b = doc.buildings.find((x) => x.id === f?.building_id);
  $('#floorLabel').textContent = f ? `${b ? b.name : ''} · ${f.name}` : '';
  $('#svcZone').textContent = b ? `· ${b.name}` : '';
  [...$('#zones').children].forEach((el) => {
    const on = el.dataset.f === id;
    el.classList.toggle('active', on);
    if (on) el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  });
  if (snap) renderServices();
}

function updateZoneCounts() {
  const counts = {};
  const roomFloor = Object.fromEntries(doc.rooms.map((r) => [r.id, r.floor_id]));
  for (const p of snap.patients) {
    if (p.state === 'finished' || !p.room) continue;
    const fl = roomFloor[p.room];
    if (fl) counts[fl] = (counts[fl] || 0) + 1;
  }
  document.querySelectorAll('[data-count]').forEach((el) => animateNumber(el, counts[el.dataset.count] || 0));
}

function updateHealth() {
  const h = snap?.health || {};
  const ok = streamOk && h.ok;
  $('#dot').classList.toggle('bad', !ok);
  $('#clockCard').classList.toggle('bad', !ok);
  $('#clockCard').title = ok ? `เชื่อมต่อ HOSxP ปกติ (${h.mode === 'mock' ? 'โหมดสาธิต' : 'HOSxP'})`
    : `ขาดการเชื่อมต่อ: ${!streamOk ? 'เซิร์ฟเวอร์ระบบนำทาง' : (h.error || 'HOSxP')}`;
}

function onSnapshot(s) {
  if (!s || !s.patients) return;
  if (doc && s.map_version && s.map_version !== doc.version) {
    api('/api/map').then((d) => { setDoc(d); toast('มีการอัปเดตแผนที่ใหม่'); });
  }
  snap = s;
  $('#clock').textContent = s.time;
  animateNumber($('#sIn'), s.stats.in_hospital);
  animateNumber($('#sWait'), s.stats.avg_wait);
  animateNumber($('#sDen'), s.stats.density);
  const lv = $('#sLevel');
  lv.textContent = s.stats.density_level;
  lv.className = 'level ' + (s.stats.density < 35 ? 'low' : s.stats.density < 70 ? 'mid' : 'high');
  $('#rush').checked = !!s.rush;
  updateHealth();
  iso.setCounts(s.rooms);
  iso.setPatients(s.patients, first);
  if (first) {
    first = false;
    setTimeout(() => $('#loader').classList.add('done'), 250);
  }
  updateZoneCounts();
  renderServices();
  if (selected) renderPatient(true);
  if (selectedRoom) renderRoom();
  if ($('#search').value) renderResults();
}

// ------------------------------------------------------------------ จุดบริการ (เฉพาะโซนที่เปิดอยู่)
function renderServices() {
  const zone = floorBuilding[iso.floorId];
  const list = snap.services.filter((s) => !s.floor || floorBuilding[s.floor] === zone);
  const box = $('#services');
  if (!list.length) { box.innerHTML = '<div class="muted" style="padding:6px 2px">ยังไม่มีจุดบริการที่จับคู่ HOSxP ในโซนนี้</div>'; box.dataset.keys = ''; return; }
  const keys = list.map((s) => s.depcode + '@' + (s.zone || '')).join();
  const item = (s) => {
    const ratio = s.waiting / Math.max(1, s.capacity);
    return {
      title: `${s.name} — รอ ${s.waiting} คน, กำลังรับบริการ ${s.serving} คน`,
      meta: `<span><b>${s.waiting}</b> รอ · ${s.serving} รับบริการ</span><span>~${s.est} น.</span>`,
      width: `${Math.min(100, Math.max(2, Math.round(ratio * 100)))}%`, color: densityText(ratio),
    };
  };
  if (box.dataset.keys !== keys) {
    box.innerHTML = list.map((s) => {
      const it = item(s);
      return `<button class="svc" data-room="${esc(s.wait_room)}" title="${esc(it.title)}">
        <div class="t">${esc(s.name)}</div><div class="m">${it.meta}</div>
        <div class="bar"><i style="width:0%;background:${it.color}"></i></div></button>`;
    }).join('');
    box.dataset.keys = keys;
  }
  // อัปเดตเฉพาะค่า เพื่อให้แถบเลื่อนนุ่ม (transition) ทำงาน
  requestAnimationFrame(() => list.forEach((s, i) => {
    const el = box.children[i];
    if (!el) return;
    const it = item(s);
    el.title = it.title;
    el.querySelector('.m').innerHTML = it.meta;
    const bar = el.querySelector('.bar i');
    bar.style.width = it.width; bar.style.background = it.color;
  }));
}
$('#services').addEventListener('click', (e) => {
  const b = e.target.closest('.svc');
  if (b) selectRoom(b.dataset.room);
});

// ------------------------------------------------------------------ ผู้ป่วยที่เลือก
function selectPatient(vn) {
  selected = vn;
  selectedRoom = null;
  iso.highlightRoom = null;
  $('#rcard').classList.add('hidden');
  iso.setSelected(vn);
  renderPatient(false);
}

function replay(el) { el.style.animation = 'none'; void el.offsetWidth; el.style.animation = ''; }

function renderPatient(update) {
  const p = snap?.patients.find((x) => x.vn === selected);
  const card = $('#pcard');
  if (!p) {
    if (update) clearSelection();
    return;
  }
  $('#legend').classList.add('hidden');
  const wasHidden = card.classList.contains('hidden');
  card.classList.remove('hidden');
  const histOpen = update && !wasHidden && $('#ptl') && !$('#ptl').classList.contains('hidden');
  const keep = histOpen ? $('#ptl').innerHTML : null;
  const cls = stateClass(p);
  const v = p.vitals || {};
  const vit = [
    v.bw ? `<span>น้ำหนัก <b>${v.bw}</b> กก.</span>` : '',
    v.bps ? `<span>ความดัน <b>${Math.round(v.bps)}/${Math.round(v.bpd || 0)}</b></span>` : '',
    v.temperature ? `<span>อุณหภูมิ <b>${Number(v.temperature).toFixed(1)}</b> °C</span>` : '',
  ].join('');
  card.innerHTML = `
    <button class="close" aria-label="ปิด" id="pclose">×</button>
    <div class="head">
      <div class="qbadge">${esc(p.q)}</div>
      <div style="flex:1;min-width:0;padding-right:28px">
        <div class="name">${esc(p.dest_name || '')}</div>
        <div class="meta">HN ${esc(p.hn)} · ${esc(sexAge(p))}</div>
        <div style="margin-top:6px"><span class="chip ${cls}">${esc(p.label)}</span></div>
      </div>
    </div>
    ${stepperHtml(p.stages)}
    <div class="infogrid">
      <div class="info"><div class="k">รอที่จุดนี้</div><div class="v">${p.since}<small> นาที</small></div></div>
      <div class="info"><div class="k">${p.pos ? `คิวที่ ${p.pos} · รออีก` : 'คาดรออีก'}</div><div class="v">${p.est != null ? `~${p.est}` : '–'}<small> นาที</small></div></div>
      <div class="info"><div class="k">อยู่ใน รพ.</div><div class="v">${p.stay}<small> นาที</small></div></div>
    </div>
    ${vit ? `<div class="vitals">${vit}</div>` : ''}
    ${p.pending?.length ? `<div class="pending">${p.pending.map((x) => `<span class="${x.status}">${esc(x.name)} · ${x.status === 'done' ? 'เสร็จแล้ว' : x.status === 'received' ? 'กำลังตรวจ' : 'ค้างตรวจ'}</span>`).join('')}</div>` : ''}
    <div class="actions">
      <a class="btn primary" href="/slip/${encodeURIComponent(p.vn)}" target="_blank" rel="noopener">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V3h12v6M6 18H4v-7h16v7h-2"/><path d="M6 14h12v7H6z"/></svg>พิมพ์ใบนำทาง QR</a>
      <button class="btn" id="pfocus"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>ดูตำแหน่ง</button>
      <button class="btn ghost" id="phist">ประวัติวันนี้</button>
    </div>
    <ul class="timeline hidden" id="ptl"></ul>`;
  if (!update) replay(card);
  if (keep != null) { $('#ptl').innerHTML = keep; $('#ptl').classList.remove('hidden'); }
  $('#pclose').onclick = clearSelection;
  $('#pfocus').onclick = () => focusPatient(p);
  $('#phist').onclick = () => loadHistory(p.vn);
  if (p.route) iso.setRoute({ points: p.route, dest: p.route[p.route.length - 1] });
  else iso.setRoute(null);
  if (!update) focusPatient(p);
}

function focusPatient(p) {
  const pos = iso.personPosition(p.vn);
  const room = doc.rooms.find((r) => r.id === p.room);
  const floor = pos?.floor || room?.floor_id;
  if (floor) iso.setFloor(floor);
  if (pos) iso.focus(pos.x, pos.y, 14);
  else if (room) iso.focus(...centroidOf(room), 14);
}

async function loadHistory(vn) {
  const ul = $('#ptl');
  if (!ul.classList.contains('hidden')) { ul.classList.add('hidden'); return; }
  try {
    const v = await api(`/api/visits/${encodeURIComponent(vn)}`);
    ul.innerHTML = v.events.slice().reverse().map((e) => `<li><time>${esc(e.time)}</time><span>${esc(e.text)}</span></li>`).join('') || '<li><span>ไม่มีประวัติ</span></li>';
    ul.classList.remove('hidden');
  } catch (err) { toast(err.message); }
}

function clearSelection() {
  selected = null;
  selectedRoom = null;
  iso.setSelected(null);
  iso.setRoute(null);
  iso.highlightRoom = null;
  iso.dirty = true;
  $('#pcard').classList.add('hidden');
  $('#rcard').classList.add('hidden');
  const lg = $('#legend');
  if (lg.classList.contains('hidden')) { lg.classList.remove('hidden'); replay(lg); }
}

// ------------------------------------------------------------------ ห้อง/พื้นที่
const centroidOf = (r) => {
  const xs = r.polygon.map((p) => p[0]), ys = r.polygon.map((p) => p[1]);
  return [xs.reduce((a, b) => a + b) / xs.length, ys.reduce((a, b) => a + b) / ys.length];
};

function selectRoom(id) {
  const r = doc.rooms.find((x) => x.id === id);
  if (!r) return;
  selected = null;
  iso.setSelected(null);
  iso.setRoute(null);
  $('#pcard').classList.add('hidden');
  selectedRoom = id;
  iso.highlightRoom = id;
  iso.setFloor(r.floor_id);
  iso.focus(...centroidOf(r), 12);
  renderRoom(true);
}

function renderRoom(fresh) {
  const r = doc.rooms.find((x) => x.id === selectedRoom);
  if (!r || !snap) return;
  $('#legend').classList.add('hidden');
  const card = $('#rcard');
  card.classList.remove('hidden');
  const people = snap.patients.filter((p) => p.room === r.id && p.state !== 'finished');
  const n = people.length;
  const ratio = n / Math.max(1, r.capacity || 20);
  const svcs = snap.services.filter((s) => s.wait_room === r.id || s.room === r.id);
  people.sort((a, b) => (a.pos ?? 999) - (b.pos ?? 999));
  card.innerHTML = `
    <button class="close" aria-label="ปิด" id="rclose">×</button>
    <div class="head">
      <div class="qbadge teal" style="font-size:22px">${n}</div>
      <div style="flex:1;min-width:0;padding-right:28px">
        <div class="name">${esc(r.name)}</div>
        <div class="meta">${esc(zoneName(doc.floors.find((f) => f.id === r.floor_id)))} · รองรับ ${r.capacity || '-'} คน · ${Math.round(ratio * 100)}%</div>
        <div class="bar" style="margin-top:8px"><i style="width:${Math.min(100, Math.round(ratio * 100))}%;background:${densityText(ratio)}"></i></div>
      </div>
    </div>
    ${svcs.map((s) => `<div class="infogrid">
      <div class="info"><div class="k">${esc(s.name)}</div><div class="v">${s.waiting}<small> รอ</small></div></div>
      <div class="info"><div class="k">รับบริการ</div><div class="v">${s.serving}<small> คน</small></div></div>
      <div class="info"><div class="k">คาดรอ</div><div class="v">~${s.est}<small> นาที</small></div></div></div>`).join('')}
    <div class="pending" style="margin-top:10px">${people.slice(0, 40).map((p) => `<span role="button" tabindex="0" data-vn="${esc(p.vn)}" style="cursor:pointer">${esc(p.q)}${p.pos ? ` #${p.pos}` : ''}</span>`).join('')}${people.length > 40 ? `<span>+${people.length - 40}</span>` : ''}</div>`;
  if (fresh) replay(card);
  $('#rclose').onclick = clearSelection;
  card.querySelectorAll('[data-vn]').forEach((el) => { el.onclick = () => selectPatient(el.dataset.vn); });
}

iso.on('person', selectPatient);
iso.on('room', (id) => { if (id) selectRoom(id); else clearSelection(); });

// ------------------------------------------------------------------ ค้นหา
function renderResults() {
  const q = $('#search').value.trim().toLowerCase();
  const box = $('#results');
  if (!q || !snap) { box.classList.add('hidden'); return; }
  const pts = snap.patients.filter((p) => [p.q, p.hn, p.vn, p.dest_name].some((v) => String(v || '').toLowerCase().includes(q))).slice(0, 8);
  const rooms = doc.rooms.filter((r) => r.kind !== 'corridor' && (r.name.toLowerCase().includes(q) || (r.short_name || '').toLowerCase().includes(q) || r.code.toLowerCase().includes(q))).slice(0, 6);
  box.innerHTML = pts.map((p) => `<button data-vn="${esc(p.vn)}"><span class="qbadge sm">${esc(p.q)}</span><span><b>HN ${esc(p.hn)}</b><br><small class="muted">${esc(p.label)}</small></span></button>`).join('')
    + rooms.map((r) => `<button data-room="${esc(r.id)}"><span class="qbadge sm teal">ห้อง</span><span><b>${esc(r.name)}</b><br><small class="muted">${esc(zoneName(doc.floors.find((f) => f.id === r.floor_id)))} · ${snap.rooms[r.id] || 0} คน</small></span></button>`).join('')
    || '<div class="muted" style="padding:12px">ไม่พบข้อมูล</div>';
  box.classList.remove('hidden');
}
$('#search').addEventListener('input', renderResults);
$('#search').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('#results button')?.click();
  if (e.key === 'Escape') { e.target.value = ''; renderResults(); e.target.blur(); }
});
$('#results').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.vn) selectPatient(b.dataset.vn);
  if (b.dataset.room) selectRoom(b.dataset.room);
  $('#search').value = '';
  renderResults();
});

// ------------------------------------------------------------------ ปุ่มควบคุม + คีย์ลัด
$('#zin').onclick = () => iso.zoomSmooth(1.35);
$('#zout').onclick = () => iso.zoomSmooth(1 / 1.35);
$('#rotl').onclick = () => iso.rotate(-1);
$('#rotr').onclick = () => iso.rotate(1);
$('#home').onclick = () => iso.resetView();
$('#builderLink').onclick = () => { location.href = '/builder'; };
$('#rush').onchange = async (e) => {
  try { await api('/api/demo/rush', { method: 'POST', body: JSON.stringify({ on: e.target.checked }) }); toast(e.target.checked ? 'จำลองช่วงเร่งด่วน: ผู้ป่วยมาเพิ่มขึ้น' : 'กลับสู่ปกติ'); } catch (err) { toast(err.message); }
};
document.addEventListener('keydown', (e) => {
  if (e.target.matches('input, textarea')) return;
  if (e.key === '/') { e.preventDefault(); $('#search').focus(); }
  else if (e.key === 'Escape') clearSelection();
  else if (e.key === '+' || e.key === '=') iso.zoomSmooth(1.35);
  else if (e.key === '-') iso.zoomSmooth(1 / 1.35);
  else if (e.key === '[') iso.rotate(-1);
  else if (e.key === ']') iso.rotate(1);
  else if (/^[1-9]$/.test(e.key) && doc?.floors[Number(e.key) - 1]) iso.setFloor(doc.floors[Number(e.key) - 1].id);
});

init().catch((err) => { $('#loader').classList.add('done'); toast('โหลดข้อมูลไม่สำเร็จ: ' + err.message, 6000); });
