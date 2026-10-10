// Map Builder: วาดห้อง ปักจุดนำทาง เชื่อมทางเดิน จับคู่รหัส HOSxP ทดสอบเส้นทาง และเผยแพร่
import { $, api, esc, toast } from './common.js';
import { centroid } from './iso.js';

const svg = $('#svg');
const KIND_LABEL = { service: 'ห้องบริการ (มีผนัง)', window: 'ห้องมีช่องบริการ (เช่น ห้องยา ห้องเก็บเงิน)', counter: 'เคาน์เตอร์บริการ (เปิดโล่ง)', building: 'ตึก (แผนที่ภาพรวม)', waiting: 'พื้นที่นั่งรอ', corridor: 'ทางเดิน/โถง', other: 'อื่น ๆ' };
const ROOM_FILL = { service: '#eef3f6', window: '#e9f1fb', building: '#cfd8dc', counter: '#fde7f1', waiting: '#e3f4e6', corridor: '#f7f9fa', other: '#f2f0ea' };
const NODE_KIND = { corridor: 'ทางเดิน', junction: 'ทางแยก', door: 'ประตู', entrance: 'ทางเข้าอาคาร', exit: 'ทางออกอาคาร', portal: 'หน้าตึก (เชื่อมโซน)', gate: 'ประตูใหญ่โรงพยาบาล', elevator: 'ลิฟต์', stairs: 'บันได', ramp: 'ทางลาด' };
const NODE_COLOR = { corridor: '#7c8b93', junction: '#1f9e8f', door: '#e0479e', entrance: '#c0392b', exit: '#7b1fa2', portal: '#0f766e', gate: '#b91c1c', elevator: '#2f74c8', stairs: '#8e5cc4', ramp: '#d08a12' };
const STAGES = { register: 'ลงทะเบียน', screening: 'คัดกรอง', doctor: 'พบแพทย์', lab: 'LAB', xray: 'X-ray', finance: 'การเงิน', pharmacy: 'รับยา', other: 'อื่น ๆ' };

let doc = null;
let versions = [];
let floorId = null;
let tool = 'select';
let sel = null; // {type, id}
let nodeKind = 'corridor';
let snap = true;
let dirty = false;
let tab = 'props';
let view = { x: -5, y: -5, w: 80, h: 60 };
let drag = null;
let draft = null; // รูปที่กำลังวาด
let edgeStart = null;
let testRoute = null;
let hosxpDeps = null;

const uid = (p) => `${p}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const round = (v) => Math.round(v * 100) / 100;
const snapV = (v) => (snap ? Math.round(v * 2) / 2 : round(v));
const floor = () => doc.floors.find((f) => f.id === floorId);
const roomById = (id) => doc.rooms.find((r) => r.id === id);
const nodeById = (id) => doc.nodes.find((n) => n.id === id);

function markDirty() { dirty = true; $('#dirtyMark').textContent = '● มีการแก้ไขที่ยังไม่บันทึก'; }
window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });

// ------------------------------------------------------------------ โหลด/บันทึก
async function load() {
  const cfg = await api('/api/config');
  $('#hospital').textContent = cfg.hospital;
  const data = await api('/api/admin/map');
  doc = data.draft;
  versions = data.versions;
  for (const r of doc.rooms) r.seats = !!r.seats;
  floorId = floorId && doc.floors.some((f) => f.id === floorId) ? floorId : doc.floors[0]?.id;
  dirty = false;
  $('#dirtyMark').textContent = '';
  fillSelectors();
  fitView();
  render();
  renderPanel();
}

async function save() {
  try {
    await api('/api/admin/map', { method: 'PUT', body: JSON.stringify(doc) });
    dirty = false;
    $('#dirtyMark').textContent = 'บันทึกแล้ว';
    toast('บันทึกแผนที่ฉบับร่างแล้ว (ยังไม่เผยแพร่)');
  } catch (err) { toast('บันทึกไม่สำเร็จ: ' + err.message, 5000); }
}

async function publish() {
  const problems = checkMap();
  const note = prompt(`${problems.length ? `พบข้อควรตรวจ ${problems.length} รายการ (ดูแท็บทดสอบเส้นทาง)\n` : ''}หมายเหตุการเผยแพร่ (เช่น ย้ายห้อง LAB):`, '');
  if (note === null) return;
  try {
    const r = await api('/api/admin/publish', { method: 'POST', body: JSON.stringify({ doc, note }) });
    dirty = false;
    toast(`เผยแพร่แผนที่ฉบับที่ ${r.version} แล้ว หน้าจอทั้งหมดจะอัปเดตอัตโนมัติ`);
    await load();
  } catch (err) { toast('เผยแพร่ไม่สำเร็จ: ' + err.message, 5000); }
}

$('#saveBtn').onclick = save;
$('#pubBtn').onclick = publish;

// ------------------------------------------------------------------ อาคาร/ชั้น
function fillSelectors() {
  const f = floor();
  $('#bSel').innerHTML = doc.buildings.map((b) => `<option value="${esc(b.id)}" ${f?.building_id === b.id ? 'selected' : ''}>${esc(b.name)}</option>`).join('');
  const bid = $('#bSel').value;
  $('#fSel').innerHTML = doc.floors.filter((x) => x.building_id === bid).sort((a, b) => a.level - b.level)
    .map((x) => `<option value="${esc(x.id)}" ${x.id === floorId ? 'selected' : ''}>${esc(x.name)}</option>`).join('');
}
$('#bSel').onchange = () => {
  const first = doc.floors.filter((x) => x.building_id === $('#bSel').value).sort((a, b) => a.level - b.level)[0];
  floorId = first?.id || null;
  sel = null; fillSelectors(); fitView(); render(); renderPanel();
};
$('#fSel').onchange = () => { floorId = $('#fSel').value; sel = null; testRoute = null; fitView(); render(); renderPanel(); };

// ------------------------------------------------------------------ มุมมอง
function fitView() {
  const f = floor();
  if (!f) return;
  const rect = svg.getBoundingClientRect();
  const aspect = rect.width / Math.max(1, rect.height) || 1.4;
  let w = f.width + 8, h = f.height + 8;
  if (w / h < aspect) w = h * aspect; else h = w / aspect;
  view = { x: f.width / 2 - w / 2, y: f.height / 2 - h / 2, w, h };
  applyView();
}
function applyView() { svg.setAttribute('viewBox', `${view.x} ${view.y} ${view.w} ${view.h}`); }
function toWorld(e) {
  const pt = svg.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  return [p.x, p.y];
}
new ResizeObserver(() => { if (doc) { const old = view; fitView(); if (old.w) { view.x = old.x; view.y = old.y; view.w = old.w; view.h = old.w * (view.h / view.w); applyView(); } } }).observe(svg);

// ------------------------------------------------------------------ วาด SVG
function render() {
  const f = floor();
  if (!f) { svg.innerHTML = ''; return; }
  const rooms = doc.rooms.filter((r) => r.floor_id === f.id);
  const nodes = doc.nodes.filter((n) => n.floor_id === f.id);
  const nodeSet = new Set(nodes.map((n) => n.id));
  const edges = doc.edges.filter((e) => nodeSet.has(e.node_a) || nodeSet.has(e.node_b));
  const selRoom = sel?.type === 'room' ? roomById(sel.id) : null;
  const doors = new Set(rooms.map((r) => r.door_node_id).filter(Boolean));
  let out = `<defs>
    <pattern id="g1" width="1" height="1" patternUnits="userSpaceOnUse"><path d="M1 0H0V1" fill="none" stroke="#e3ebe9" stroke-width="0.03"/></pattern>
    <pattern id="g5" width="5" height="5" patternUnits="userSpaceOnUse"><rect width="5" height="5" fill="url(#g1)"/><path d="M5 0H0V5" fill="none" stroke="#cfdcd9" stroke-width="0.06"/></pattern>
  </defs>
  <rect x="0" y="0" width="${f.width}" height="${f.height}" fill="#fff" stroke="#1f9e8f" stroke-width="0.3"/>`;
  if (f.plan_image) out += `<image href="${esc(f.plan_image)}" x="0" y="0" width="${f.width}" height="${f.height}" preserveAspectRatio="none" opacity="${f.plan_opacity ?? 0.5}" style="pointer-events:none"/>`;
  out += `<rect x="0" y="0" width="${f.width}" height="${f.height}" fill="url(#g5)" style="pointer-events:none"/>`;
  const order = { corridor: 0, waiting: 1, other: 1, counter: 2, service: 3, window: 3 };
  for (const r of [...rooms].sort((a, b) => (order[a.kind] ?? 1) - (order[b.kind] ?? 1))) {
    const pts = r.polygon.map((p) => p.join(',')).join(' ');
    const isSel = selRoom?.id === r.id;
    out += `<polygon data-room="${esc(r.id)}" points="${pts}" fill="${esc(r.color || ROOM_FILL[r.kind] || '#eee')}" fill-opacity="${f.plan_image ? 0.65 : 1}"
      stroke="${isSel ? '#e0479e' : r.kind === 'service' || r.kind === 'window' ? '#5d6d74' : '#9fb3b0'}" stroke-width="${isSel ? 3 : r.kind === 'service' || r.kind === 'window' ? 2 : 1}" vector-effect="non-scaling-stroke"/>`;
  }
  for (const r of rooms) {
    const [cx, cy] = centroid(r.polygon);
    const mapped = doc.mapping.some((m) => m.room_id === r.id || m.wait_room_id === r.id);
    out += `<text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="middle" font-size="0.95" font-weight="700" fill="#23323a" style="pointer-events:none">${esc(r.short_name || r.name)}</text>`;
    out += `<text x="${cx}" y="${cy + 1.1}" text-anchor="middle" font-size="0.7" fill="${mapped ? '#1f9e8f' : '#9aa8ae'}" style="pointer-events:none">${esc(r.code)}${mapped ? ' · HOSxP ✓' : ''}</text>`;
  }
  for (const e of edges) {
    const a = nodeById(e.node_a), b = nodeById(e.node_b);
    if (!a || !b || a.floor_id !== f.id || b.floor_id !== f.id) continue;
    const isSel = sel?.type === 'edge' && sel.id === e.id;
    const color = e.kind === 'stairs' ? '#8e5cc4' : e.kind === 'ramp' ? '#d08a12' : '#1f9e8f';
    out += `<line data-edge="${esc(e.id)}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="transparent" stroke-width="12" vector-effect="non-scaling-stroke"/>`;
    out += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="${isSel ? '#e0479e' : color}" stroke-width="${isSel ? 5 : 3}" ${e.accessible === false || e.kind === 'stairs' ? 'stroke-dasharray="6 4"' : ''} vector-effect="non-scaling-stroke" style="pointer-events:none"/>`;
  }
  if (testRoute?.ok) {
    let seg = [];
    const segs = [];
    for (const p of testRoute.points) { if (p[0] === f.id) seg.push(p); else if (seg.length) { segs.push(seg); seg = []; } }
    if (seg.length) segs.push(seg);
    for (const s of segs) out += `<polyline points="${s.map((p) => `${p[1]},${p[2]}`).join(' ')}" fill="none" stroke="#e0479e" stroke-width="7" stroke-opacity="0.75" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" style="pointer-events:none"/>`;
  }
  for (const n of nodes) {
    const isSel = (sel?.type === 'node' && sel.id === n.id) || edgeStart === n.id;
    const isDoorOfSel = selRoom && selRoom.door_node_id === n.id;
    const r = ['elevator', 'stairs', 'entrance', 'exit'].includes(n.kind) ? 0.75 : 0.45;
    if (isSel || isDoorOfSel) out += `<circle cx="${n.x}" cy="${n.y}" r="${r + 0.45}" fill="none" stroke="#e0479e" stroke-width="2.5" vector-effect="non-scaling-stroke" style="pointer-events:none"/>`;
    out += `<circle data-node="${esc(n.id)}" cx="${n.x}" cy="${n.y}" r="${r}" fill="${NODE_COLOR[n.kind] || '#777'}" stroke="#fff" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;
    if (doors.has(n.id)) out += `<circle cx="${n.x}" cy="${n.y}" r="0.18" fill="#fff" style="pointer-events:none"/>`;
    if (n.kind === 'elevator' || n.kind === 'stairs') out += `<text x="${n.x}" y="${n.y - 1.1}" text-anchor="middle" font-size="0.7" font-weight="700" fill="${NODE_COLOR[n.kind]}" style="pointer-events:none">${esc(NODE_KIND[n.kind])}${n.link_group ? ` (${esc(n.link_group)})` : ''}</text>`;
  }
  if (selRoom && tool === 'select') {
    selRoom.polygon.forEach((p, i) => { out += `<rect data-vertex="${i}" x="${p[0] - 0.35}" y="${p[1] - 0.35}" width="0.7" height="0.7" fill="#fff" stroke="#e0479e" stroke-width="2" vector-effect="non-scaling-stroke"/>`; });
  }
  if (draft?.type === 'rect' && draft.b) {
    const x = Math.min(draft.a[0], draft.b[0]), y = Math.min(draft.a[1], draft.b[1]);
    out += `<rect x="${x}" y="${y}" width="${Math.abs(draft.b[0] - draft.a[0])}" height="${Math.abs(draft.b[1] - draft.a[1])}" fill="rgba(224,71,158,.15)" stroke="#e0479e" stroke-width="2" stroke-dasharray="6 4" vector-effect="non-scaling-stroke"/>
      <text x="${x + Math.abs(draft.b[0] - draft.a[0]) / 2}" y="${y - 0.4}" text-anchor="middle" font-size="0.8" fill="#e0479e">${round(Math.abs(draft.b[0] - draft.a[0]))} × ${round(Math.abs(draft.b[1] - draft.a[1]))} ม.</text>`;
  }
  if (draft?.type === 'poly' && draft.pts.length) {
    const pts = [...draft.pts, draft.hover].filter(Boolean).map((p) => p.join(',')).join(' ');
    out += `<polyline points="${pts}" fill="rgba(224,71,158,.12)" stroke="#e0479e" stroke-width="2" stroke-dasharray="6 4" vector-effect="non-scaling-stroke"/>`;
  }
  if (edgeStart && draft?.hover) {
    const a = nodeById(edgeStart);
    if (a && a.floor_id === f.id) out += `<line x1="${a.x}" y1="${a.y}" x2="${draft.hover[0]}" y2="${draft.hover[1]}" stroke="#e0479e" stroke-width="2" stroke-dasharray="5 4" vector-effect="non-scaling-stroke" style="pointer-events:none"/>`;
  }
  if (tool === 'node' && sel?.type === 'node' && draft?.hover) {
    const a = nodeById(sel.id);
    if (a && a.floor_id === f.id) out += `<line x1="${a.x}" y1="${a.y}" x2="${draft.hover[0]}" y2="${draft.hover[1]}" stroke="#1f9e8f" stroke-width="2" stroke-dasharray="5 4" vector-effect="non-scaling-stroke" style="pointer-events:none"/>`;
  }
  svg.innerHTML = out;
}

// ------------------------------------------------------------------ เครื่องมือ
const HINTS = {
  select: 'คลิกเพื่อเลือก · ลากห้อง/จุดเพื่อย้าย · ลากจุดมุมสี่เหลี่ยมเพื่อปรับขอบเขต · ลากพื้นที่ว่างเพื่อเลื่อน',
  rect: 'ลากเพื่อวาดขอบเขตห้อง (ปรับเข้ากริด 0.5 ม.)',
  poly: 'คลิกเพื่อเพิ่มมุม · ดับเบิลคลิกหรือ Enter เพื่อจบ · Esc ยกเลิก',
  node: 'คลิกเพื่อปักจุด — ถ้ามีจุดที่เลือกอยู่ จะเชื่อมทางเดินให้อัตโนมัติ (วาดต่อเนื่องได้) · Esc หยุดเชื่อม',
  edge: 'คลิกจุดแรก แล้วคลิกจุดที่สองเพื่อเชื่อมทางเดิน',
  door: 'เลือกห้องก่อน แล้วคลิกจุดนำทางที่เป็นประตูของห้องนั้น',
};
function setTool(t) {
  tool = t;
  draft = null;
  edgeStart = null;
  document.querySelectorAll('.tools [data-tool]').forEach((b) => b.classList.toggle('active', b.dataset.tool === t));
  $('#stage').className = `stage tool-${t}`;
  $('#hint').textContent = HINTS[t];
  render();
  if (tab === 'props') renderPanel();
}
document.querySelectorAll('.tools [data-tool]').forEach((b) => { b.onclick = () => setTool(b.dataset.tool); });
$('#delBtn').onclick = deleteSelected;
$('#fitBtn').onclick = fitView;

function select(type, id) { sel = type ? { type, id } : null; render(); if (tab !== 'props') switchTab('props'); else renderPanel(); }

function addEdge(a, b, kind = 'walk') {
  if (a === b) return;
  if (doc.edges.some((e) => (e.node_a === a && e.node_b === b) || (e.node_a === b && e.node_b === a))) return;
  doc.edges.push({ id: uid('e'), node_a: a, node_b: b, kind, accessible: kind !== 'stairs' });
  markDirty();
}

function deleteSelected() {
  if (!sel) return;
  if (sel.type === 'room') {
    doc.rooms = doc.rooms.filter((r) => r.id !== sel.id);
    doc.mapping.forEach((m) => { if (m.room_id === sel.id) m.room_id = null; if (m.wait_room_id === sel.id) m.wait_room_id = null; });
  } else if (sel.type === 'node') {
    doc.nodes = doc.nodes.filter((n) => n.id !== sel.id);
    doc.edges = doc.edges.filter((e) => e.node_a !== sel.id && e.node_b !== sel.id);
    doc.rooms.forEach((r) => { if (r.door_node_id === sel.id) r.door_node_id = null; });
  } else if (sel.type === 'edge') {
    doc.edges = doc.edges.filter((e) => e.id !== sel.id);
  }
  sel = null;
  markDirty();
  render();
  renderPanel();
}

// ------------------------------------------------------------------ เมาส์
svg.addEventListener('pointerdown', (e) => {
  if (!floor()) return;
  const p = toWorld(e);
  const sp = [snapV(p[0]), snapV(p[1])];
  const t = e.target.dataset || {};
  svg.setPointerCapture(e.pointerId);
  if (e.button === 1 || e.button === 2 || (e.button === 0 && e.shiftKey && tool !== 'select')) {
    drag = { type: 'pan', start: [e.clientX, e.clientY], view: { ...view } };
    return;
  }
  if (tool === 'select') {
    if (t.vertex !== undefined && sel?.type === 'room') { drag = { type: 'vertex', i: Number(t.vertex) }; return; }
    if (t.node) { select('node', t.node); drag = { type: 'node', id: t.node, moved: false }; return; }
    if (t.edge) { select('edge', t.edge); return; }
    if (t.room) {
      select('room', t.room);
      drag = { type: 'room', id: t.room, start: sp, orig: roomById(t.room).polygon.map((q) => [...q]), moved: false };
      return;
    }
    if (sel) select(null);
    drag = { type: 'pan', start: [e.clientX, e.clientY], view: { ...view } };
  } else if (tool === 'rect') {
    draft = { type: 'rect', a: sp, b: null };
  } else if (tool === 'poly') {
    if (!draft) draft = { type: 'poly', pts: [] };
    const last = draft.pts[draft.pts.length - 1];
    if (!last || last[0] !== sp[0] || last[1] !== sp[1]) draft.pts.push(sp);
    render();
  } else if (tool === 'node') {
    if (t.node) {
      if (sel?.type === 'node' && sel.id !== t.node) addEdge(sel.id, t.node);
      select('node', t.node);
      return;
    }
    const n = { id: uid('n'), floor_id: floorId, kind: nodeKind, x: sp[0], y: sp[1], name: null, link_group: null };
    doc.nodes.push(n);
    if (sel?.type === 'node' && nodeById(sel.id)?.floor_id === floorId) addEdge(sel.id, n.id);
    markDirty();
    select('node', n.id);
  } else if (tool === 'edge') {
    if (!t.node) { edgeStart = null; render(); return; }
    if (!edgeStart) { edgeStart = t.node; render(); return; }
    addEdge(edgeStart, t.node);
    edgeStart = null;
    render();
  } else if (tool === 'door') {
    if (t.room) { select('room', t.room); $('#hint').textContent = 'คลิกจุดนำทางที่เป็นประตูของห้องนี้'; return; }
    if (t.node && sel?.type === 'room') {
      roomById(sel.id).door_node_id = t.node;
      const n = nodeById(t.node);
      if (n.kind === 'corridor' || n.kind === 'junction') n.kind = 'door';
      markDirty(); render(); renderPanel();
      toast('กำหนดประตูห้องแล้ว');
    }
  }
});

svg.addEventListener('pointermove', (e) => {
  if (!floor()) return;
  const p = toWorld(e);
  const sp = [snapV(p[0]), snapV(p[1])];
  $('#coords').textContent = `${sp[0]}, ${sp[1]} ม.`;
  if (drag?.type === 'pan') {
    const k = view.w / svg.clientWidth;
    view.x = drag.view.x - (e.clientX - drag.start[0]) * k;
    view.y = drag.view.y - (e.clientY - drag.start[1]) * k;
    applyView();
    return;
  }
  if (drag?.type === 'node') {
    const n = nodeById(drag.id);
    if (n.x !== sp[0] || n.y !== sp[1]) { n.x = sp[0]; n.y = sp[1]; drag.moved = true; markDirty(); render(); }
    return;
  }
  if (drag?.type === 'room') {
    const dx = sp[0] - drag.start[0], dy = sp[1] - drag.start[1];
    if (dx || dy || drag.moved) {
      roomById(drag.id).polygon = drag.orig.map((q) => [round(q[0] + dx), round(q[1] + dy)]);
      drag.moved = true; markDirty(); render();
    }
    return;
  }
  if (drag?.type === 'vertex') {
    const P = roomById(sel.id).polygon;
    const i = drag.i;
    const old = [...P[i]];
    const axisAligned = P.length === 4 && P.every((p, k) => { const q = P[(k + 1) % 4]; return p[0] === q[0] || p[1] === q[1]; });
    if (axisAligned) {
      // ห้องสี่เหลี่ยม: ขยับมุมข้างเคียงตามเพื่อรักษามุมฉาก
      for (const j of [(i + 3) % 4, (i + 1) % 4]) {
        if (P[j][0] === old[0]) P[j][0] = sp[0];
        else if (P[j][1] === old[1]) P[j][1] = sp[1];
      }
    }
    P[i] = sp;
    markDirty(); render();
    return;
  }
  if (draft?.type === 'rect' && draft.a) { draft.b = sp; render(); return; }
  if (draft?.type === 'poly' || edgeStart || (tool === 'node' && sel?.type === 'node')) {
    draft = draft || { type: 'hover' };
    draft.hover = sp;
    render();
  }
});

svg.addEventListener('pointerup', () => {
  if (draft?.type === 'rect' && draft.b) {
    const x1 = Math.min(draft.a[0], draft.b[0]), y1 = Math.min(draft.a[1], draft.b[1]);
    const x2 = Math.max(draft.a[0], draft.b[0]), y2 = Math.max(draft.a[1], draft.b[1]);
    if (x2 - x1 >= 1 && y2 - y1 >= 1) newRoom([[x1, y1], [x2, y1], [x2, y2], [x1, y2]]);
    draft = null;
    render();
  } else if (draft?.type === 'rect') draft = null;
  drag = null;
});
svg.addEventListener('dblclick', () => { if (tool === 'poly') finishPoly(); });
svg.addEventListener('contextmenu', (e) => e.preventDefault());
svg.addEventListener('wheel', (e) => {
  e.preventDefault();
  const [mx, my] = toWorld(e);
  const k = Math.exp(e.deltaY * 0.0015);
  const nw = Math.max(5, Math.min(400, view.w * k));
  const f = nw / view.w;
  view = { x: mx - (mx - view.x) * f, y: my - (my - view.y) * f, w: nw, h: view.h * f };
  applyView();
}, { passive: false });

function finishPoly() {
  if (draft?.type === 'poly') {
    const pts = draft.pts.filter((p, i, a) => i === 0 || p[0] !== a[i - 1][0] || p[1] !== a[i - 1][1]);
    if (pts.length >= 3) newRoom(pts);
  }
  draft = null;
  render();
}

function newRoom(poly) {
  const n = doc.rooms.filter((r) => r.floor_id === floorId).length + 1;
  const r = { id: uid('r'), floor_id: floorId, code: `RM${n}`, name: `ห้องใหม่ ${n}`, short_name: null, kind: 'service', polygon: poly,
    door_node_id: null, color: null, capacity: 10, seats: false, desk: null };
  doc.rooms.push(r);
  markDirty();
  setTool('select');
  select('room', r.id);
  toast('สร้างห้องแล้ว: ตั้งชื่อและกำหนดประตูห้องในแผงด้านขวา');
}

document.addEventListener('keydown', (e) => {
  if (e.target.matches('input, textarea, select')) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); save(); return; }
  const k = e.key.toLowerCase();
  if (k === 'delete' || k === 'backspace') { e.preventDefault(); deleteSelected(); }
  else if (k === 'escape') { if (draft || edgeStart) { draft = null; edgeStart = null; render(); } else select(null); }
  else if (k === 'enter' && tool === 'poly') finishPoly();
  else if ({ v: 'select', r: 'rect', p: 'poly', n: 'node', e: 'edge', d: 'door' }[k]) setTool({ v: 'select', r: 'rect', p: 'poly', n: 'node', e: 'edge', d: 'door' }[k]);
  else if (k === 'f') fitView();
});

// ------------------------------------------------------------------ แผงด้านขวา
document.querySelectorAll('.tabs button').forEach((b) => { b.onclick = () => switchTab(b.dataset.tab); });
function switchTab(t) {
  tab = t;
  document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === t));
  renderPanel();
}

function renderPanel() {
  if (!doc) return;
  const body = $('#pbody');
  if (tab === 'props') body.innerHTML = propsHtml();
  else if (tab === 'mapping') body.innerHTML = mappingHtml();
  else if (tab === 'route') body.innerHTML = routeHtml();
  else body.innerHTML = floorHtml();
  bindPanel(body);
}

const opt = (v, label, cur) => `<option value="${esc(v)}" ${String(cur ?? '') === String(v) ? 'selected' : ''}>${esc(label)}</option>`;
const roomOptions = (cur, blank = '— ไม่ระบุ —') => opt('', blank, cur) + doc.floors.map((f) =>
  `<optgroup label="${esc(f.name)}">${doc.rooms.filter((r) => r.floor_id === f.id && r.kind !== 'corridor').map((r) => opt(r.id, r.name, cur)).join('')}</optgroup>`).join('');

function propsHtml() {
  let h = '';
  if (tool === 'node') {
    h += `<div class="ptitle">ชนิดจุดที่จะปัก</div><div class="field"><select data-ui="nodeKind">${Object.entries(NODE_KIND).map(([k, v]) => opt(k, v, nodeKind)).join('')}</select></div>`;
  }
  const r = sel?.type === 'room' ? roomById(sel.id) : null;
  const n = sel?.type === 'node' ? nodeById(sel.id) : null;
  const e = sel?.type === 'edge' ? doc.edges.find((x) => x.id === sel.id) : null;
  if (r) {
    const maps = doc.mapping.filter((m) => m.room_id === r.id || m.wait_room_id === r.id);
    const door = nodeById(r.door_node_id);
    h += `<div class="ptitle">ห้อง / พื้นที่ <button class="btn ghost" data-act="del">ลบ</button></div>
      <label class="field"><span>ชื่อห้อง</span><input data-room="name" value="${esc(r.name)}"></label>
      <div class="grid2">
        <label class="field"><span>ชื่อย่อบนแผนที่</span><input data-room="short_name" value="${esc(r.short_name || '')}"></label>
        <label class="field"><span>รหัสห้อง</span><input data-room="code" value="${esc(r.code)}"></label>
      </div>
      <label class="field"><span>ประเภท</span><select data-room="kind">${Object.entries(KIND_LABEL).map(([k, v]) => opt(k, v, r.kind)).join('')}</select></label>
      <div class="grid2">
        <label class="field"><span>รองรับ (คน)</span><input type="number" min="1" data-room="capacity" value="${r.capacity ?? 10}"></label>
        <label class="field"><span>${r.kind === 'window' ? 'ด้านช่องบริการ' : 'โต๊ะ/เคาน์เตอร์'}</span><select data-room="desk">${opt('', 'ไม่มี', r.desk)}${opt('n', 'ด้านบน', r.desk)}${opt('s', 'ด้านล่าง', r.desk)}${opt('w', 'ด้านซ้าย', r.desk)}${opt('e', 'ด้านขวา', r.desk)}</select></label>
      </div>
      ${r.kind === 'building' ? `<label class="field"><span>คลิกตึกนี้แล้วเปิดโซน</span><select data-room="link_floor">${opt('', '— ไม่มีแผนที่ภายใน —', r.link_floor)}${doc.floors.filter((x) => x.style !== 'campus').map((x) => opt(x.id, `${doc.buildings.find((b) => b.id === x.building_id)?.name || ''} ${x.name}`, r.link_floor)).join('')}</select></label>` : ''}
      <label class="check"><input type="checkbox" data-room="seats" ${r.seats ? 'checked' : ''}> วาดเก้าอี้นั่งรอ</label>
      <label class="field"><span>ของตกแต่งภายใน</span><select data-room="decor">${opt('', 'ไม่มี', r.decor)}${opt('pharmacy', 'ชั้นวางยา (ห้องยา)', r.decor)}${opt('cashier', 'ตู้เอกสาร/ตู้เซฟ (ห้องเก็บเงิน)', r.decor)}${opt('dental', 'เก้าอี้ทำฟัน (ห้องทันตกรรม)', r.decor)}${opt('beds', 'เตียงรักษา (เช่น เตียงกายภาพ)', r.decor)}</select></label>
      <div class="grid2">
        <label class="field"><span>สีพื้น (เว้นว่าง = อัตโนมัติ)</span><input type="color" data-room="color" value="${esc(r.color || ROOM_FILL[r.kind] || '#eeeeee')}"></label>
        <div class="field"><span>&nbsp;</span><button class="btn ghost" data-act="clearColor">ใช้สีอัตโนมัติ</button></div>
      </div>
      <div class="field"><span>ประตูห้อง (จุดเริ่ม/สิ้นสุดเส้นทาง)</span>
        ${door ? `<div class="okmsg">${esc(door.name || NODE_KIND[door.kind])} (${door.x}, ${door.y})</div>` : '<div class="warn">ยังไม่กำหนด — ใช้เครื่องมือ "ประตูห้อง" แล้วคลิกจุดนำทาง (ระบบจะใช้จุดที่ใกล้ที่สุดแทน)</div>'}
        <button class="btn" data-act="doorTool">กำหนดประตูห้อง</button></div>
      <div class="field"><span>หน่วยบริการ HOSxP ที่ผูกกับห้องนี้</span>
        ${maps.length ? `<div class="list">${maps.map((m) => `<div><b>${esc(m.depcode)}</b> ${esc(m.dep_name || '')} <span class="muted">${m.room_id === r.id ? 'ห้องบริการ' : 'จุดรอ'}</span></div>`).join('')}</div>` : '<div class="muted">ยังไม่มี — จับคู่ได้ที่แท็บ "จับคู่ HOSxP"</div>'}
      </div>`;
  } else if (n) {
    const deg = doc.edges.filter((x) => x.node_a === n.id || x.node_b === n.id).length;
    h += `<div class="ptitle">จุดนำทาง <button class="btn ghost" data-act="del">ลบ</button></div>
      <label class="field"><span>ชนิด</span><select data-node="kind">${Object.entries(NODE_KIND).map(([k, v]) => opt(k, v, n.kind)).join('')}</select></label>
      <label class="field"><span>ชื่อจุด (ใช้ในคำแนะนำการเดิน เช่น "หน้าลิฟต์")</span><input data-node="name" value="${esc(n.name || '')}"></label>
      ${['elevator', 'stairs', 'ramp', 'entrance', 'exit', 'portal'].includes(n.kind) ? `<label class="field"><span>กลุ่มเชื่อมข้ามชั้น/โซน (ชื่อเดียวกัน = เชื่อมกัน เช่น LIFT_A, Z_OPD)</span><input data-node="link_group" value="${esc(n.link_group || '')}"></label>` : ''}
      <div class="grid2">
        <label class="field"><span>X (ม.)</span><input type="number" step="0.5" data-node="x" value="${n.x}"></label>
        <label class="field"><span>Y (ม.)</span><input type="number" step="0.5" data-node="y" value="${n.y}"></label>
      </div>
      <div class="${deg ? 'okmsg' : 'warn'}">เชื่อมกับทางเดิน ${deg} เส้น</div>`;
  } else if (e) {
    const a = nodeById(e.node_a), b = nodeById(e.node_b);
    const len = a && b ? Math.hypot(a.x - b.x, a.y - b.y).toFixed(1) : '-';
    h += `<div class="ptitle">ทางเดิน <button class="btn ghost" data-act="del">ลบ</button></div>
      <div class="muted" style="margin-bottom:10px">ระยะ ${len} เมตร</div>
      <label class="field"><span>ชนิด</span><select data-edge="kind">${opt('walk', 'ทางเดินปกติ', e.kind)}${opt('ramp', 'ทางลาด', e.kind)}${opt('stairs', 'ขั้นบันได', e.kind)}</select></label>
      <label class="check"><input type="checkbox" data-edge="accessible" ${e.accessible !== false && e.kind !== 'stairs' ? 'checked' : ''} ${e.kind === 'stairs' ? 'disabled' : ''}> รถเข็นผ่านได้</label>`;
  } else {
    const f = floor();
    h += `<div class="ptitle">${esc(f?.name || '')}</div>
      <div class="list">
        <div>ห้อง/พื้นที่ <b style="margin-left:auto">${doc.rooms.filter((x) => x.floor_id === floorId).length}</b></div>
        <div>จุดนำทาง <b style="margin-left:auto">${doc.nodes.filter((x) => x.floor_id === floorId).length}</b></div>
      </div>
      <label class="check"><input type="checkbox" data-ui="snap" ${snap ? 'checked' : ''}> ปรับตำแหน่งเข้ากริด 0.5 เมตร</label>
      <div class="ptitle">ขั้นตอนสร้างแผนที่</div>
      <ol style="padding-left:18px;font-size:13px;line-height:1.7;margin:0">
        <li>อัปโหลดแปลนอาคาร (แท็บ อาคาร/ชั้น) และตั้งขนาดชั้นเป็นเมตร</li>
        <li>วาดขอบเขตห้องด้วย <b>R</b> / <b>P</b> แล้วตั้งชื่อ ประเภท</li>
        <li>ปักจุดทางเดินด้วย <b>N</b> — คลิกต่อเนื่องเพื่อวาดเส้นทาง</li>
        <li>ปักลิฟต์/บันได/ทางลาด และตั้งกลุ่มเชื่อมข้ามชั้น</li>
        <li>กำหนดประตูห้องด้วย <b>D</b></li>
        <li>จับคู่รหัสหน่วยบริการ HOSxP</li>
        <li>ทดสอบเส้นทาง แล้วกด <b>เผยแพร่แผนที่</b></li>
      </ol>
      <p class="kbd" style="margin-top:12px">ลัด: V เลือก · R ห้อง · P หลายเหลี่ยม · N จุด · E เชื่อม · D ประตู · Del ลบ · F พอดีจอ · Ctrl+S บันทึก · คลิกขวา/Shift+ลาก เลื่อนแผนที่</p>`;
  }
  return h;
}

function mappingHtml() {
  const stageOpts = (cur) => Object.entries(STAGES).map(([k, v]) => opt(k, v, cur)).join('');
  let h = `<div class="ptitle">จับคู่หน่วยบริการ HOSxP กับห้อง <button class="btn" data-act="addMap">+ เพิ่ม</button></div>
    <p class="muted" style="font-size:13px;margin-top:0">ใช้รหัสจริงจาก HOSxP (kskdepartment.depcode) ถ้าแผนกเดียวมีหลายห้อง ให้เพิ่มหลายแถวรหัสเดียวกัน และใส่ "รหัสห้องย่อย" ที่ HOSxP บันทึก — ถ้าไม่มีข้อมูลห้องย่อย ระบบจะพาไปพื้นที่รอของแผนกแทนการเดา</p>
    <button class="btn ghost" data-act="loadDeps" style="margin-bottom:10px">ดึงรายชื่อหน่วยบริการจาก HOSxP</button>`;
  if (hosxpDeps) {
    const used = new Set(doc.mapping.map((m) => m.depcode));
    h += `<div class="list" style="max-height:200px;overflow:auto">${hosxpDeps.map((d) => `<div><b>${esc(d.depcode)}</b> ${esc(d.name)}${used.has(d.depcode) ? ' <span class="muted" style="margin-left:auto">✓ ใช้แล้ว</span>' : ` <button class="btn ghost" style="margin-left:auto;padding:2px 8px" data-act="addDep" data-dep="${esc(d.depcode)}" data-name="${esc(d.name)}">+ เพิ่ม</button>`}</div>`).join('')}</div>`;
  }
  doc.mapping.forEach((m, i) => {
    h += `<div class="maprow">
      <div class="grid2">
        <label class="field"><span>รหัส HOSxP</span><input data-map="${i}" data-k="depcode" value="${esc(m.depcode)}"></label>
        <label class="field"><span>ชื่อหน่วยบริการ</span><input data-map="${i}" data-k="dep_name" value="${esc(m.dep_name || '')}"></label>
      </div>
      <label class="field"><span>ห้องบริการ</span><select data-map="${i}" data-k="room_id">${roomOptions(m.room_id)}</select></label>
      <label class="field"><span>พื้นที่นั่งรอ</span><select data-map="${i}" data-k="wait_room_id">${roomOptions(m.wait_room_id, '— ใช้ห้องบริการ —')}</select></label>
      <label class="field"><span>ใช้เฉพาะผู้ป่วยแผนกหลัก (main_dep) — เว้นว่าง = ทุกคน · ใช้เมื่อรหัสเดียวกันอยู่หลายโซน เช่น 047</span><input data-map="${i}" data-k="for_main_dep" placeholder="เช่น 047 หรือ 047,024" value="${esc(m.for_main_dep || '')}"></label>
      <div class="grid3">
        <label class="field"><span>ขั้นตอน</span><select data-map="${i}" data-k="stage">${stageOpts(m.stage)}</select></label>
        <label class="field"><span>ห้องย่อย</span><input data-map="${i}" data-k="room_hint" value="${esc(m.room_hint || '')}"></label>
        <label class="field"><span>อักษรคิว</span><input data-map="${i}" data-k="queue_prefix" maxlength="3" value="${esc(m.queue_prefix || '')}"></label>
        <label class="field"><span>ลำดับงานค้าง</span><input type="number" data-map="${i}" data-k="priority" value="${m.priority ?? 50}"></label>
        <label class="field"><span>ช่องบริการ</span><input type="number" min="1" data-map="${i}" data-k="servers" value="${m.servers ?? 1}"></label>
        <label class="field"><span>นาที/คน</span><input type="number" min="0.5" step="0.5" data-map="${i}" data-k="avg_service_min" value="${m.avg_service_min ?? 5}"></label>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <label class="check" style="margin:0"><input type="checkbox" data-map="${i}" data-k="is_default" ${m.is_default ? 'checked' : ''}> ห้องหลักของแผนก</label>
        <button class="btn ghost" data-act="delMap" data-i="${i}">ลบ</button>
      </div></div>`;
  });
  return h;
}

function routeHtml() {
  const rooms = (cur) => doc.floors.map((f) => `<optgroup label="${esc(f.name)}">${doc.rooms.filter((r) => r.floor_id === f.id && r.kind !== 'corridor').map((r) => opt(r.id, r.name, cur)).join('')}</optgroup>`).join('');
  const st = routeHtml.state ||= { from: '', to: '', acc: false };
  const problems = checkMap();
  let h = `<div class="ptitle">ทดสอบคำนวณเส้นทาง</div>
    <label class="field"><span>จาก</span><select data-rt="from">${opt('', 'ประตูทางเข้าอาคาร', st.from)}${rooms(st.from)}</select></label>
    <label class="field"><span>ไป</span><select data-rt="to">${opt('', '— เลือกห้อง —', st.to)}${rooms(st.to)}</select></label>
    <label class="check"><input type="checkbox" data-rt="acc" ${st.acc ? 'checked' : ''}> เส้นทางสำหรับรถเข็น (เลี่ยงบันได)</label>
    <button class="btn primary" data-act="runRoute">คำนวณเส้นทาง</button>`;
  if (testRoute) {
    h += testRoute.ok
      ? `<div class="okmsg" style="margin-top:10px">ระยะ ${testRoute.distance} เมตร · ประมาณ ${testRoute.minutes} นาที · ผ่าน ${testRoute.floors.length} ชั้น</div><ol class="steps-text">${testRoute.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>`
      : `<div class="warn" style="margin-top:10px">${esc(testRoute.reason)}</div>`;
  }
  h += `<div class="ptitle" style="margin-top:18px">ตรวจความพร้อมของแผนที่</div>`;
  h += problems.length ? problems.map((p) => `<div class="warn">${esc(p)}</div>`).join('') : '<div class="okmsg">ไม่พบปัญหา ทุกห้องที่จับคู่ HOSxP เดินถึงได้จากทางเข้า</div>';
  return h;
}

function floorHtml() {
  const f = floor();
  const b = doc.buildings.find((x) => x.id === f?.building_id);
  let h = '';
  if (b) {
    h += `<div class="ptitle">อาคาร <button class="btn" data-act="addBuilding">+ อาคาร</button></div>
      <div class="grid2"><label class="field"><span>ชื่ออาคาร</span><input data-b="name" value="${esc(b.name)}"></label>
      <label class="field"><span>รหัส</span><input data-b="code" value="${esc(b.code)}"></label></div>`;
  }
  if (f) {
    h += `<div class="ptitle">ชั้น <span><button class="btn" data-act="addFloor">+ ชั้น</button> <button class="btn ghost" data-act="delFloor">ลบชั้น</button></span></div>
      <div class="grid2">
        <label class="field"><span>ชื่อชั้น</span><input data-f="name" value="${esc(f.name)}"></label>
        <label class="field"><span>ระดับชั้น</span><input type="number" data-f="level" value="${f.level}"></label>
        <label class="field"><span>ความกว้าง (ม.)</span><input type="number" min="5" data-f="width" value="${f.width}"></label>
        <label class="field"><span>ความยาว (ม.)</span><input type="number" min="5" data-f="height" value="${f.height}"></label>
      </div>
      <div class="field"><span>แปลนอาคาร (PNG/JPG/SVG) — ภาพจะถูกยืดให้เต็มขนาดชั้น</span>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" data-act="upload">อัปโหลดแปลน</button>${f.plan_image ? '<button class="btn ghost" data-act="rmPlan">นำออก</button>' : ''}</div></div>
      ${f.plan_image ? `<label class="field"><span>ความโปร่งใสของแปลน ${Math.round((f.plan_opacity ?? 0.5) * 100)}%</span><input type="range" min="0.1" max="1" step="0.05" data-f="plan_opacity" value="${f.plan_opacity ?? 0.5}"></label>` : ''}`;
  }
  h += `<div class="ptitle" style="margin-top:16px">ประวัติการเผยแพร่</div><div class="list">${versions.map((v) => `<div><b>ฉบับที่ ${v.id}</b> <span class="muted">${esc(String(v.published_at).replace('T', ' ').slice(0, 16))}</span> <span style="margin-left:auto">${esc(v.note || '')}</span></div>`).join('') || '<div class="muted">ยังไม่เคยเผยแพร่</div>'}</div>`;
  return h;
}

function bindPanel(body) {
  body.querySelectorAll('[data-room]').forEach((el) => {
    el.onchange = el.oninput = () => {
      const r = roomById(sel.id);
      const k = el.dataset.room;
      r[k] = el.type === 'checkbox' ? el.checked : el.type === 'number' ? Number(el.value) : (el.value || (k === 'name' || k === 'code' ? r[k] : null));
      markDirty(); render();
      if (el.tagName === 'SELECT' && k === 'kind') renderPanel();
    };
  });
  body.querySelectorAll('[data-node]').forEach((el) => {
    el.onchange = () => {
      const n = nodeById(sel.id);
      const k = el.dataset.node;
      n[k] = el.type === 'number' ? Number(el.value) : (el.value || null);
      markDirty(); render(); if (k === 'kind') renderPanel();
    };
  });
  body.querySelectorAll('[data-edge]').forEach((el) => {
    el.onchange = () => {
      const e = doc.edges.find((x) => x.id === sel.id);
      if (el.dataset.edge === 'kind') { e.kind = el.value; if (e.kind === 'stairs') e.accessible = false; else if (e.accessible === false && el.value !== 'stairs') e.accessible = true; }
      else e.accessible = el.checked;
      markDirty(); render(); renderPanel();
    };
  });
  body.querySelectorAll('[data-map]').forEach((el) => {
    el.onchange = () => {
      const m = doc.mapping[Number(el.dataset.map)];
      const k = el.dataset.k;
      m[k] = el.type === 'checkbox' ? el.checked : el.type === 'number' ? Number(el.value) : (el.value.trim() || null);
      markDirty(); render();
    };
  });
  body.querySelectorAll('[data-b]').forEach((el) => {
    el.onchange = () => { const b = doc.buildings.find((x) => x.id === floor().building_id); b[el.dataset.b] = el.value; markDirty(); fillSelectors(); };
  });
  body.querySelectorAll('[data-f]').forEach((el) => {
    el.onchange = el.oninput = () => {
      const f = floor();
      f[el.dataset.f] = el.type === 'number' || el.type === 'range' ? Number(el.value) : el.value;
      markDirty(); render();
      if (el.type !== 'range') fillSelectors();
    };
  });
  body.querySelectorAll('[data-rt]').forEach((el) => {
    el.onchange = () => { routeHtml.state[el.dataset.rt] = el.type === 'checkbox' ? el.checked : el.value; };
  });
  body.querySelectorAll('[data-ui]').forEach((el) => {
    el.onchange = () => { if (el.dataset.ui === 'snap') snap = el.checked; else nodeKind = el.value; };
  });
  body.querySelectorAll('[data-act]').forEach((el) => { el.onclick = () => action(el.dataset.act, el); });
}

async function action(act, el) {
  if (act === 'del') deleteSelected();
  else if (act === 'clearColor') { roomById(sel.id).color = null; markDirty(); render(); renderPanel(); }
  else if (act === 'doorTool') { const keep = sel; setTool('door'); sel = keep; render(); $('#hint').textContent = 'คลิกจุดนำทางที่เป็นประตูของห้องนี้'; }
  else if (act === 'addMap') { doc.mapping.push({ id: uid('m'), depcode: '', dep_name: '', room_id: null, wait_room_id: null, room_hint: null, for_main_dep: null, is_default: true, stage: 'other', priority: 50, queue_prefix: null, servers: 1, avg_service_min: 5 }); markDirty(); renderPanel(); }
  else if (act === 'addDep') { doc.mapping.push({ id: uid('m'), depcode: el.dataset.dep, dep_name: el.dataset.name, room_id: null, wait_room_id: null, room_hint: null, for_main_dep: null, is_default: true, stage: 'other', priority: 50, queue_prefix: null, servers: 1, avg_service_min: 5 }); markDirty(); renderPanel(); }
  else if (act === 'delMap') { doc.mapping.splice(Number(el.dataset.i), 1); markDirty(); renderPanel(); }
  else if (act === 'loadDeps') {
    try {
      const res = await api('/api/admin/hosxp-departments');
      hosxpDeps = Array.isArray(res) ? res : [];
      renderPanel();
    } catch (err) { toast('อ่านรายชื่อจาก HOSxP ไม่สำเร็จ: ' + err.message, 5000); }
  } else if (act === 'runRoute') {
    const st = routeHtml.state;
    if (!st.to) { toast('เลือกห้องปลายทาง'); return; }
    try {
      testRoute = await api('/api/admin/route-test', { method: 'POST', body: JSON.stringify({ doc, from: st.from || null, to: st.to, accessible: st.acc }) });
      if (testRoute.ok && testRoute.points.length && !testRoute.points.some((p) => p[0] === floorId)) {
        floorId = testRoute.points[0][0]; fillSelectors(); fitView();
      }
    } catch (err) { testRoute = { ok: false, reason: err.message }; }
    render(); renderPanel();
  } else if (act === 'upload') $('#planFile').click();
  else if (act === 'rmPlan') { floor().plan_image = null; markDirty(); render(); renderPanel(); }
  else if (act === 'addBuilding') {
    const b = { id: uid('b'), code: `B${doc.buildings.length + 1}`, name: `อาคารใหม่ ${doc.buildings.length + 1}`, sort: doc.buildings.length + 1 };
    doc.buildings.push(b);
    const f = { id: uid('f'), building_id: b.id, level: 1, name: 'ชั้น 1', width: 60, height: 40, plan_image: null, plan_opacity: 0.5 };
    doc.floors.push(f);
    floorId = f.id; markDirty(); fillSelectors(); fitView(); render(); renderPanel();
  } else if (act === 'addFloor') {
    const cur = floor();
    const levels = doc.floors.filter((x) => x.building_id === cur.building_id).map((x) => x.level);
    const lv = Math.max(...levels) + 1;
    const f = { id: uid('f'), building_id: cur.building_id, level: lv, name: `ชั้น ${lv}`, width: cur.width, height: cur.height, plan_image: null, plan_opacity: 0.5 };
    doc.floors.push(f);
    floorId = f.id; markDirty(); fillSelectors(); render(); renderPanel();
  } else if (act === 'delFloor') {
    const f = floor();
    const used = doc.rooms.some((r) => r.floor_id === f.id) || doc.nodes.some((n) => n.floor_id === f.id);
    if (doc.floors.length <= 1) { toast('ต้องมีอย่างน้อย 1 ชั้น'); return; }
    if (used && !confirm(`ชั้นนี้มีห้องหรือจุดนำทางอยู่ ต้องการลบ "${f.name}" ทั้งหมดหรือไม่?`)) return;
    const nodeIds = new Set(doc.nodes.filter((n) => n.floor_id === f.id).map((n) => n.id));
    const roomIds = new Set(doc.rooms.filter((r) => r.floor_id === f.id).map((r) => r.id));
    doc.nodes = doc.nodes.filter((n) => !nodeIds.has(n.id));
    doc.edges = doc.edges.filter((e) => !nodeIds.has(e.node_a) && !nodeIds.has(e.node_b));
    doc.rooms = doc.rooms.filter((r) => !roomIds.has(r.id));
    doc.mapping.forEach((m) => { if (roomIds.has(m.room_id)) m.room_id = null; if (roomIds.has(m.wait_room_id)) m.wait_room_id = null; });
    doc.floors = doc.floors.filter((x) => x.id !== f.id);
    if (!doc.floors.some((x) => x.building_id === f.building_id)) doc.buildings = doc.buildings.filter((b) => b.id !== f.building_id);
    floorId = doc.floors[0].id; markDirty(); fillSelectors(); fitView(); render(); renderPanel();
  }
}

$('#planFile').onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/api/admin/plan-image', { method: 'POST', body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const { path } = await res.json();
    const f = floor();
    f.plan_image = path;
    // ปรับสัดส่วนชั้นตามภาพ (คงความกว้างไว้)
    const img = new Image();
    img.onload = () => {
      if (img.width && img.height) f.height = Math.round((f.width * img.height) / img.width);
      markDirty(); fitView(); render(); renderPanel();
    };
    img.src = path;
    toast('อัปโหลดแปลนแล้ว ปรับความกว้าง/ยาวของชั้นให้ตรงกับขนาดจริง (เมตร)');
  } catch (err) { toast('อัปโหลดไม่สำเร็จ: ' + err.message, 5000); }
  e.target.value = '';
};

// ------------------------------------------------------------------ ตรวจความถูกต้อง
function checkMap() {
  const out = [];
  const adj = new Map(doc.nodes.map((n) => [n.id, []]));
  for (const e of doc.edges) { adj.get(e.node_a)?.push(e.node_b); adj.get(e.node_b)?.push(e.node_a); }
  const groups = {};
  for (const n of doc.nodes) if (n.link_group && ['elevator', 'stairs', 'ramp'].includes(n.kind)) (groups[n.link_group] ||= []).push(n.id);
  for (const ids of Object.values(groups)) for (const a of ids) for (const b of ids) if (a !== b) adj.get(a).push(b);
  // ตรวจทีละอาคาร/โซน: ทุกห้องต้องเดินถึงจากทางเข้าของโซนนั้น
  const floorBuilding = Object.fromEntries(doc.floors.map((f) => [f.id, f.building_id]));
  const reach = new Set();
  const hasEntrance = new Set();
  for (const n of doc.nodes) {
    if (n.kind !== 'entrance') continue;
    hasEntrance.add(floorBuilding[n.floor_id]);
    const stack = [n.id];
    while (stack.length) { const u = stack.pop(); if (reach.has(u)) continue; reach.add(u); for (const v of adj.get(u) || []) stack.push(v); }
  }
  for (const b of doc.buildings) if (!hasEntrance.has(b.id)) out.push(`"${b.name}" ยังไม่มีจุด "ทางเข้าอาคาร" (ใช้เป็นจุดเริ่มต้นเมื่อผู้ป่วยมาถึง)`);
  const nearestNode = (r) => {
    if (r.door_node_id) return r.door_node_id;
    const [cx, cy] = centroid(r.polygon);
    let best = null, bd = 1e9;
    for (const n of doc.nodes) if (n.floor_id === r.floor_id) { const d = Math.hypot(n.x - cx, n.y - cy); if (d < bd) { bd = d; best = n.id; } }
    return best;
  };
  for (const r of doc.rooms) {
    if (r.kind === 'corridor') continue;
    if (!r.door_node_id) out.push(`ห้อง "${r.name}" ยังไม่กำหนดประตู`);
    const n = nearestNode(r);
    if (hasEntrance.has(floorBuilding[r.floor_id]) && n && !reach.has(n)) out.push(`ห้อง "${r.name}" เดินไปไม่ถึงจากทางเข้า (ตรวจเส้นทางเชื่อม)`);
  }
  for (const n of doc.nodes) if (!(adj.get(n.id) || []).length) out.push(`จุด ${n.name || NODE_KIND[n.kind]} (${n.x}, ${n.y}) ยังไม่เชื่อมกับทางเดิน`);
  for (const m of doc.mapping) {
    if (!m.depcode) out.push('มีรายการจับคู่ที่ไม่มีรหัส HOSxP');
    else if (!m.room_id && !m.wait_room_id) out.push(`รหัส ${m.depcode} ยังไม่ได้เลือกห้อง`);
  }
  return out.slice(0, 30);
}

load().catch((err) => toast('โหลดแผนที่ไม่สำเร็จ: ' + err.message, 6000));
