// แผนที่ 3 มิติแบบ Isometric (วาดด้วย Canvas 2D) — ใช้ร่วมกันระหว่างหน้าจอเจ้าหน้าที่และใบนำทางผู้ป่วย
const COS30 = Math.cos(Math.PI / 6);
const SIN30 = 0.5;

const PAL = {
  ground: '#eef4f2',
  slabTop: '#ffffff',
  slabSide: '#d9e6e3',
  wallSide: '#e9eef0',
  wallTop: '#1f9e8f',
  innerTop: '#9fd8cf',
  corridor: '#f7f9fa',
  service: '#f3f6f8',
  counter: '#fdf1f6',
  waitLow: '#e3f4e6',
  waitMid: '#fbf0c9',
  waitHigh: '#fbdcd6',
  desk: '#f7f4ee',
  chair: '#2f74c8',
  bed: '#cfe6f7',
  staff: '#1f9e8f',
  skin: ['#f2c9a5', '#e9b48a', '#d9a077', '#f5d3b5'],
  clothes: ['#2f6fca', '#3b82d6', '#2a5fae', '#4a8fe0', '#2563b8'],
  route: '#e0479e',
  routeEdge: '#ffffff',
  pin: '#e0479e',
};

export function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
export function shade(hex, f) {
  const [r, g, b] = hexToRgb(hex);
  const m = (v) => Math.max(0, Math.min(255, Math.round(f >= 1 ? v + (255 - v) * (f - 1) : v * f)));
  return `rgb(${m(r)},${m(g)},${m(b)})`;
}
export function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
function rand(seed) { // ตัวสุ่มแบบกำหนดค่าได้
  let s = seed >>> 0 || 1;
  return () => { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return ((s >>> 0) % 100000) / 100000; };
}
export function centroid(poly) {
  let x = 0, y = 0;
  for (const p of poly) { x += p[0]; y += p[1]; }
  return [x / poly.length, y / poly.length];
}
export function pointInPoly(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function bbox(poly) {
  const xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]);
  return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
}
function signedArea(poly) {
  let a = 0;
  for (let i = 0; i < poly.length; i++) { const p = poly[i], q = poly[(i + 1) % poly.length]; a += p[0] * q[1] - q[0] * p[1]; }
  return a / 2;
}
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const FONT = '"IBM Plex Sans Thai", "Noto Sans Thai", "Leelawadee UI", Tahoma, sans-serif';
function convexHull(points) {
  const pts = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [], upper = [];
  for (const p of pts) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop(); lower.push(p); }
  for (let i = pts.length - 1; i >= 0; i--) { const p = pts[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop(); upper.push(p); }
  upper.pop(); lower.pop();
  return lower.concat(upper);
}
const easeOutBack = (t) => { const c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

export function densityColor(ratio) {
  if (ratio >= 0.8) return PAL.waitHigh;
  if (ratio >= 0.45) return PAL.waitMid;
  return PAL.waitLow;
}
export function densityText(ratio) {
  if (ratio >= 0.8) return '#d94a3a';
  if (ratio >= 0.45) return '#c98a12';
  return '#2a9d5c';
}

export class IsoMap {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.opts = { showLabels: true, showStaff: true, labelMode: 'all', ...opts };
    this.doc = null;
    this.floorId = null;
    this.angle = Math.PI / 4 * 0; // มุมหมุนปัจจุบัน
    this.targetAngle = this.angle;
    this.scale = 10;
    this.pan = [0, 0];
    this.center = [0, 0];
    this.persons = new Map();
    this.crowd = [];
    this.counts = {};
    this.route = null;
    this.highlightRoom = null;
    this.selected = null;
    this.showPlan = false;
    this.images = {};
    this.seatOwner = {};
    this.listeners = {};
    this.dirty = true;
    this.zMul = 0;          // ความสูงของวัตถุ (0→1 ตอนอาคารค่อย ๆ ยกขึ้น)
    this._rise = 0;
    this._countsVer = 0;
    this.hoverRoom = null;
    this.hoverVn = null;
    this._last = performance.now();
    this._dash = 0;
    this._pointers = new Map();
    this._bindEvents();
    new ResizeObserver(() => this.resize()).observe(canvas);
    this.resize();
    requestAnimationFrame((t) => this._frame(t));
  }

  on(name, fn) { (this.listeners[name] ||= []).push(fn); }
  emit(name, ...a) { (this.listeners[name] || []).forEach((fn) => fn(...a)); }

  // ------------------------------------------------------------------ data
  setMap(doc) {
    this.doc = doc;
    this.rooms = Object.fromEntries(doc.rooms.map((r) => [r.id, r]));
    this.floors = Object.fromEntries(doc.floors.map((f) => [f.id, f]));
    this.static = {};
    this.seats = {};
    for (const f of doc.floors) {
      this._buildFloor(f);
      if (f.plan_image && !this.images[f.plan_image]) {
        const img = new Image();
        img.onload = () => { this._layerKey = null; this.dirty = true; };
        img.src = f.plan_image;
        this.images[f.plan_image] = img;
      }
    }
    if (!this.floorId || !this.floors[this.floorId]) this.setFloor(doc.floors[0]?.id);
    this.dirty = true;
  }

  setFloor(id) {
    if (!id || !this.floors[id]) return;
    const changed = this.floorId !== id;
    this.floorId = id;
    const f = this.floors[id];
    this.center = [f.width / 2, f.height / 2];
    if (changed) { this.fit(); this._rise = 0; this.zMul = 0; this._layerKey = null; }
    if (f.plan_image && !this.images[f.plan_image]) {
      const img = new Image();
      img.onload = () => { this.dirty = true; };
      img.src = f.plan_image;
      this.images[f.plan_image] = img;
    }
    this.dirty = true;
    this.emit('floor', id);
  }

  setCounts(counts) {
    const next = counts || {};
    if (JSON.stringify(next) !== JSON.stringify(this.counts)) this._countsVer++;
    this.counts = next;
    this.dirty = true;
  }

  setRoute(route) { this.route = route && route.points ? route : null; this.dirty = true; }

  setSelected(vn) { this.selected = vn; this.dirty = true; }

  // ผู้ป่วยนิรนาม (ใช้ในหน้าผู้ป่วย เพื่อแสดงความหนาแน่นโดยไม่เปิดเผยข้อมูลผู้อื่น)
  setCrowd(counts, excludeRoom) {
    this.crowd = [];
    for (const [rid, n] of Object.entries(counts || {})) {
      const room = this.rooms?.[rid];
      if (!room) continue;
      const k = Math.max(0, Math.min(n - (rid === excludeRoom ? 1 : 0), 60));
      const seats = this.seats[rid] || [];
      const r = rand(hash(rid));
      for (let i = 0; i < k; i++) {
        let pos;
        if (seats.length) pos = seats[(i * 7 + Math.floor(r() * seats.length)) % seats.length];
        else pos = this._randomPoint(room, hash(rid + i));
        this.crowd.push({ floor: room.floor_id, x: pos[0], y: pos[1], seated: !!seats.length, seed: hash(rid + ':' + i) });
      }
    }
    this.dirty = true;
  }

  // รายชื่อผู้ป่วยจาก snapshot: {vn, room, route, route_id, state, walking, service_room, label, q}
  setPatients(list, initial = false) {
    const seen = new Set();
    for (const p of list) {
      seen.add(p.vn);
      let person = this.persons.get(p.vn);
      const isNew = !person;
      if (!person) {
        person = { vn: p.vn, seed: hash(p.vn), path: null, x: 0, y: 0, floor: null, routeId: p.route_id, room: null, alpha: 1 };
        this.persons.set(p.vn, person);
      }
      person.data = p;
      const roomChanged = person.room !== p.room || person.inService !== (p.state === 'in_service');
      if (isNew) {
        const target = this._placement(person, p);
        if (p.route && (p.walking || p.state === 'finished') && !initial) {
          person.path = this._buildPath(p.route[0], p.route, target);
        } else if (p.route && p.walking && initial) {
          person.path = this._buildPath(p.route[0], p.route, target);
          person.travel = this._pathLength(person.path) * 0.4;
        } else if (target) {
          Object.assign(person, { x: target[1], y: target[2], floor: target[0] });
        } else if (p.state === 'finished') {
          this.persons.delete(p.vn);
          continue;
        }
        person.routeId = p.route_id;
      } else if (p.route_id !== person.routeId) {
        person.routeId = p.route_id;
        this._release(person);
        const target = this._placement(person, p);
        const start = person.floor ? [person.floor, person.x, person.y] : p.route?.[0];
        if (p.route) person.path = this._buildPath(start, p.route.slice(1), target);
        else if (target) person.path = this._buildPath(start, [], target);
        person.travel = 0;
      } else if (roomChanged) {
        this._release(person);
        const target = this._placement(person, p);
        if (target && person.floor) person.path = this._buildPath([person.floor, person.x, person.y], [], target);
        person.travel = 0;
      }
      person.room = p.room;
      person.inService = p.state === 'in_service';
      person.leaving = p.state === 'finished';
    }
    for (const [vn, person] of this.persons) {
      if (!seen.has(vn)) { this._release(person); this.persons.delete(vn); }
    }
    this.dirty = true;
  }

  personPosition(vn) {
    const p = this.persons.get(vn);
    return p && p.floor ? { floor: p.floor, x: p.x, y: p.y } : null;
  }

  _buildPath(start, points, target) {
    const path = [];
    if (start) path.push(start);
    for (const pt of points || []) path.push(pt);
    if (target) path.push(target);
    // ตัดจุดซ้ำ
    return path.filter((p, i) => i === 0 || p[0] !== path[i - 1][0] || dist([p[1], p[2]], [path[i - 1][1], path[i - 1][2]]) > 0.05);
  }

  _pathLength(path) {
    let len = 0;
    for (let i = 1; i < path.length; i++) len += path[i][0] !== path[i - 1][0] ? 6 : dist([path[i][1], path[i][2]], [path[i - 1][1], path[i - 1][2]]);
    return len;
  }

  _release(person) {
    if (person.seat) {
      const owners = this.seatOwner[person.seat.room];
      if (owners && owners[person.seat.i] === person.vn) delete owners[person.seat.i];
      person.seat = null;
    }
  }

  _placement(person, p) {
    const room = this.rooms?.[p.room];
    if (!room) return null;
    const seats = this.seats[room.id] || [];
    if (p.state === 'in_service' && room.kind !== 'waiting') {
      const spot = this._serviceSpot(room, person.seed);
      return [room.floor_id, spot[0], spot[1]];
    }
    if (seats.length) {
      const owners = (this.seatOwner[room.id] ||= {});
      let i = person.seed % seats.length;
      for (let k = 0; k < seats.length && owners[i]; k++) i = (i + 7) % seats.length;
      if (!owners[i]) { owners[i] = person.vn; person.seat = { room: room.id, i }; }
      return [room.floor_id, seats[i][0], seats[i][1]];
    }
    const pt = this._randomPoint(room, person.seed);
    return [room.floor_id, pt[0], pt[1]];
  }

  _serviceSpot(room, seed) {
    const b = bbox(room.polygon);
    const r = rand(seed);
    if (room.kind === 'window') {
      const f = this._windowFrame(room);
      return f.at(f.c0 + r() * (f.c1 - f.c0), -0.9);
    }
    const beds = this.beds?.[room.id];
    if (beds?.length) return beds[seed % beds.length];
    const desk = this._deskRect(room);
    if (desk) {
      const cx = (desk.x1 + desk.x2) / 2, cy = (desk.y1 + desk.y2) / 2;
      const along = (desk.x2 - desk.x1) > (desk.y2 - desk.y1);
      const spread = (along ? desk.x2 - desk.x1 : desk.y2 - desk.y1) * 0.8;
      const off = (r() - 0.5) * spread;
      const front = { n: [0, 1], s: [0, -1], e: [-1, 0], w: [1, 0] }[room.desk] || [0, 1];
      return [cx + (along ? off : 0) + front[0] * 0.9, cy + (along ? 0 : off) + front[1] * 0.9];
    }
    return [b.x1 + 1 + r() * Math.max(0.1, b.x2 - b.x1 - 2), b.y1 + 1 + r() * Math.max(0.1, b.y2 - b.y1 - 2)];
  }

  _randomPoint(room, seed) {
    const b = bbox(room.polygon);
    const r = rand(seed);
    for (let k = 0; k < 20; k++) {
      const x = b.x1 + 0.8 + r() * Math.max(0.1, b.x2 - b.x1 - 1.6);
      const y = b.y1 + 0.8 + r() * Math.max(0.1, b.y2 - b.y1 - 1.6);
      if (pointInPoly(x, y, room.polygon)) return [x, y];
    }
    return centroid(room.polygon);
  }

  // ------------------------------------------------------------------ static geometry
  _deskRect(room) {
    if (!room.desk || room.kind === 'window') return null;
    const b = bbox(room.polygon);
    const w = b.x2 - b.x1, h = b.y2 - b.y1;
    const small = room.kind === 'service';
    const across = room.desk === 'n' || room.desk === 's' ? h : w;
    const along = room.desk === 'n' || room.desk === 's' ? w : h;
    if (across < 1.0 || along < 1.0) return null;
    // ห้องเล็ก (เช่น จุดหลังตรวจ/ซักประวัติ) ย่อโต๊ะและระยะห่างจากผนังตามขนาดห้อง
    const inset = Math.min(1.1, across * 0.38);
    const depth = Math.min(0.7, across * 0.3);
    const len = small ? Math.min(2.4, along - 0.5) : Math.max(0.8, along - Math.min(1.6, along * 0.25));
    if (room.desk === 'n' || room.desk === 's') {
      const x1 = (b.x1 + b.x2) / 2 - len / 2;
      const y1 = room.desk === 'n' ? b.y1 + inset : b.y2 - inset - depth;
      return { x1, y1, x2: x1 + len, y2: y1 + depth, inset, depth };
    }
    const y1 = (b.y1 + b.y2) / 2 - len / 2;
    const x1 = room.desk === 'w' ? b.x1 + inset : b.x2 - inset - depth;
    return { x1, y1, x2: x1 + depth, y2: y1 + len, inset, depth };
  }

  _buildFloor(f) {
    if (f.style === 'campus') return this._buildCampus(f);
    const items = [];
    const rooms = this.doc.rooms.filter((r) => r.floor_id === f.id);
    const nodes = this.doc.nodes.filter((n) => n.floor_id === f.id);
    const doors = nodes.filter((n) => n.kind === 'door' || n.kind === 'entrance' || n.kind === 'exit');
    const W = f.width, H = f.height;
    const wallKeys = new Set();

    const addWall = (a, b, h, top, thick, noDoors = false) => {
      const key = [a, b].map((p) => p.map((v) => v.toFixed(1)).join(',')).sort().join('|');
      if (wallKeys.has(key)) return;
      wallKeys.add(key);
      const len = dist(a, b);
      if (len < 0.05) return;
      // ช่องประตู
      const cuts = [];
      for (const d of noDoors ? [] : doors) {
        const t = ((d.x - a[0]) * (b[0] - a[0]) + (d.y - a[1]) * (b[1] - a[1])) / (len * len);
        if (t < -0.02 || t > 1.02) continue;
        const px = a[0] + t * (b[0] - a[0]), py = a[1] + t * (b[1] - a[1]);
        if (Math.hypot(px - d.x, py - d.y) < 0.9) {
          const half = (d.kind === 'entrance' || d.kind === 'exit' ? 2.2 : 0.85) / len;
          cuts.push([t - half, t + half]);
        }
      }
      cuts.sort((p, q) => p[0] - q[0]);
      let t0 = 0;
      const spans = [];
      for (const [c0, c1] of cuts) { if (c0 > t0) spans.push([t0, Math.min(1, c0)]); t0 = Math.max(t0, c1); }
      if (t0 < 1) spans.push([t0, 1]);
      for (const [s0, s1] of spans) {
        const segLen = (s1 - s0) * len;
        const n = Math.max(1, Math.ceil(segLen / 1.5));
        for (let i = 0; i < n; i++) {
          const u0 = s0 + ((s1 - s0) * i) / n, u1 = s0 + ((s1 - s0) * (i + 1)) / n;
          const p0 = [a[0] + u0 * (b[0] - a[0]), a[1] + u0 * (b[1] - a[1])];
          const p1 = [a[0] + u1 * (b[0] - a[0]), a[1] + u1 * (b[1] - a[1])];
          items.push({ type: 'prism', poly: this._thickLine(p0, p1, thick), z0: 0, z1: h, color: PAL.wallSide, top, cx: (p0[0] + p1[0]) / 2, cy: (p0[1] + p1[1]) / 2 });
        }
      }
    };

    // ผนังอาคาร
    const outer = [[0, 0], [W, 0], [W, H], [0, H]];
    for (let i = 0; i < 4; i++) addWall(outer[i], outer[(i + 1) % 4], 2.6, PAL.wallTop, 0.35);

    const onBoundary = (a, b) => (Math.abs(a[0] - b[0]) < 0.01 && (Math.abs(a[0]) < 0.3 || Math.abs(a[0] - W) < 0.3)) ||
      (Math.abs(a[1] - b[1]) < 0.01 && (Math.abs(a[1]) < 0.3 || Math.abs(a[1] - H) < 0.3));

    const seatsAll = {};
    for (const r of rooms) {
      const poly = r.polygon;
      if (r.kind === 'service') {
        for (let i = 0; i < poly.length; i++) {
          const a = poly[i], b = poly[(i + 1) % poly.length];
          if (!onBoundary(a, b)) addWall(a, b, 2.1, PAL.innerTop, 0.18);
        }
      }
      if (r.kind === 'window') this._buildWindowRoom(r, items, addWall, onBoundary);
      const desk = this._deskRect(r);
      if (desk) {
        const long = Math.max(desk.x2 - desk.x1, desk.y2 - desk.y1);
        const n = Math.max(1, Math.ceil(long / 1.6));
        const horiz = desk.x2 - desk.x1 >= desk.y2 - desk.y1;
        for (let i = 0; i < n; i++) {
          const d = horiz ? { x1: desk.x1 + ((desk.x2 - desk.x1) * i) / n, x2: desk.x1 + ((desk.x2 - desk.x1) * (i + 1)) / n, y1: desk.y1, y2: desk.y2 }
            : { y1: desk.y1 + ((desk.y2 - desk.y1) * i) / n, y2: desk.y1 + ((desk.y2 - desk.y1) * (i + 1)) / n, x1: desk.x1, x2: desk.x2 };
          items.push({ type: 'prism', poly: [[d.x1, d.y1], [d.x2, d.y1], [d.x2, d.y2], [d.x1, d.y2]], z0: 0, z1: 0.95, color: PAL.desk, top: '#ffffff', cx: (d.x1 + d.x2) / 2, cy: (d.y1 + d.y2) / 2 });
        }
        // คอมพิวเตอร์บนโต๊ะ + เจ้าหน้าที่หลังโต๊ะ
        const k = (desk.depth + desk.inset) / 2; // เจ้าหน้าที่อยู่กึ่งกลางระหว่างโต๊ะกับผนัง
        const back = { n: [0, -k], s: [0, k], e: [k, 0], w: [-k, 0] }[r.desk] || [0, -k];
        const staffN = r.kind === 'service' ? 1 : Math.max(1, Math.floor(long / 3));
        for (let i = 0; i < staffN; i++) {
          const t = (i + 0.5) / staffN;
          const sx = horiz ? desk.x1 + (desk.x2 - desk.x1) * t : (desk.x1 + desk.x2) / 2;
          const sy = horiz ? (desk.y1 + desk.y2) / 2 : desk.y1 + (desk.y2 - desk.y1) * t;
          items.push({ type: 'prism', poly: this._rect(sx - 0.25, sy - 0.08, 0.5, 0.16), z0: 0.95, z1: 1.35, color: '#3b4a5a', top: '#2b3743', cx: sx, cy: sy });
          if (this.opts.showStaff) items.push({ type: 'staff', x: sx + back[0], y: sy + back[1], seed: hash(r.id + i), cx: sx + back[0], cy: sy + back[1] });
        }
        const rb = bbox(poly);
        if (r.kind === 'service' && r.decor === 'dental' && Math.min(rb.x2 - rb.x1, rb.y2 - rb.y1) >= 2.5) {
          // เก้าอี้ทำฟัน + โคมไฟ + ถาดเครื่องมือ (กลางห้อง)
          const [cx, cy] = centroid(poly);
          const along = rb.x2 - rb.x1 >= rb.y2 - rb.y1;
          const L = 1.9, W2 = 0.35;
          const base = along ? this._rect(cx - L / 2, cy - W2, L, W2 * 2) : this._rect(cx - W2, cy - L / 2, W2 * 2, L);
          items.push({ type: 'prism', poly: base, z0: 0, z1: 0.55, color: '#5fb3d9', top: '#8fd0ec', cx, cy });
          const hx = along ? cx - L / 2 + 0.3 : cx, hy = along ? cy : cy - L / 2 + 0.3;
          items.push({ type: 'prism', poly: this._rect(hx - 0.3, hy - 0.3, 0.6, 0.6), z0: 0.55, z1: 1.05, color: '#5fb3d9', top: '#8fd0ec', cx: hx, cy: hy });
          const lx = along ? cx : cx + 0.9, ly = along ? cy + 0.9 : cy;
          items.push({ type: 'prism', poly: this._rect(lx - 0.05, ly - 0.05, 0.1, 0.1), z0: 0, z1: 1.9, color: '#b0bec5', top: '#cfd8dc', cx: lx, cy: ly });
          items.push({ type: 'prism', poly: this._rect(lx - 0.25, ly - 0.2, 0.5, 0.4), z0: 1.9, z1: 2.05, color: '#eceff1', top: '#ffffff', cx: lx, cy: ly });
          const tx = along ? cx + 0.6 : cx - 0.8, ty = along ? cy - 0.8 : cy + 0.6;
          items.push({ type: 'prism', poly: this._rect(tx - 0.25, ty - 0.2, 0.5, 0.4), z0: 0, z1: 0.9, color: '#cfd8dc', top: '#f5f5f5', cx: tx, cy: ty });
        } else if (r.kind === 'service' && Math.min(rb.x2 - rb.x1, rb.y2 - rb.y1) >= 3) {
          // เตียงตรวจ
          const b = bbox(poly);
          const bx = r.desk === 'n' || r.desk === 's' ? b.x1 + 0.5 : (b.x1 + b.x2) / 2 - 0.4;
          const by = r.desk === 'n' ? b.y2 - 2.3 : r.desk === 's' ? b.y1 + 0.4 : b.y1 + 0.5;
          items.push({ type: 'prism', poly: this._rect(bx, by, 0.8, 1.9), z0: 0, z1: 0.6, color: PAL.bed, top: '#e8f4fc', cx: bx + 0.4, cy: by + 0.95 });
        }
      }
      if (r.decor === 'beds') this._buildBeds(r, items);
      if (r.seats) {
        const seats = [];
        const b = bbox(poly);
        const margin = Math.max(0.45, Math.min(1.3, Math.min(b.x2 - b.x1, b.y2 - b.y1) * 0.25));
        for (let y = b.y1 + margin; y <= b.y2 - Math.min(1.0, margin); y += 2.0) {
          let col = 0;
          const strip = [];
          for (let x = b.x1 + margin; x <= b.x2 - margin + 0.01; x += 0.62) {
            if (col > 0 && col % 6 === 0) { x += 1.1; }
            col++;
            if (!pointInPoly(x, y, poly)) continue;
            seats.push([x, y + 0.05]);
            strip.push(x);
          }
          // รวมเก้าอี้เป็นแถวยาว (แถวละไม่เกิน 3 ที่นั่ง) เพื่อให้วาดเร็ว
          for (let i = 0; i < strip.length;) {
            let j = i;
            while (j + 1 < strip.length && strip[j + 1] - strip[j] < 0.7 && j - i < 2) j++;
            const x1 = strip[i] - 0.27, x2 = strip[j] + 0.27;
            items.push({ type: 'prism', poly: [[x1, y - 0.22], [x2, y - 0.22], [x2, y + 0.28], [x1, y + 0.28]], z0: 0.15, z1: 0.45, color: PAL.chair, top: '#4b8ddc', cx: (x1 + x2) / 2, cy: y });
            items.push({ type: 'prism', poly: [[x1, y - 0.3], [x2, y - 0.3], [x2, y - 0.18], [x1, y - 0.18]], z0: 0.15, z1: 0.7, color: PAL.chair, top: '#4b8ddc', cx: (x1 + x2) / 2, cy: y - 0.24 });
            i = j + 1;
          }
        }
        seatsAll[r.id] = seats;
      }
    }

    // ลิฟต์ / บันได
    for (const n of nodes) {
      if (n.kind === 'elevator') {
        items.push({ type: 'prism', poly: this._rect(n.x - 1.3, n.y - 2.6, 2.6, 1.6), z0: 0, z1: 2.5, color: '#cfd8dc', top: '#90a4ae', cx: n.x, cy: n.y - 1.8, icon: 'ลิฟต์' });
      } else if (n.kind === 'stairs') {
        for (let i = 0; i < 5; i++) {
          items.push({ type: 'prism', poly: this._rect(n.x - 1.2, n.y - 3.2 + i * 0.4, 2.4, 0.4), z0: 0, z1: 0.25 + (4 - i) * 0.3, color: '#dfe6e9', top: '#f5f7f8', cx: n.x, cy: n.y - 3 + i * 0.4 });
        }
      }
    }

    // ต้นไม้รอบอาคาร
    const r = rand(hash(f.id));
    for (let x = 4; x < W; x += 7) {
      if (r() < 0.75) items.push({ type: 'tree', x: x + r() * 2, y: -3.5 - r() * 2, s: 0.8 + r() * 0.5 });
      if (r() < 0.5 && Math.abs(x - W / 2) > 9) items.push({ type: 'tree', x: x + r() * 2, y: H + 3.5 + r() * 2, s: 0.8 + r() * 0.5 });
    }
    for (let y = 4; y < H; y += 8) {
      if (r() < 0.7) items.push({ type: 'tree', x: -3.5 - r() * 2, y: y + r() * 2, s: 0.8 + r() * 0.5 });
      if (r() < 0.7) items.push({ type: 'tree', x: W + 3.5 + r() * 2, y: y + r() * 2, s: 0.8 + r() * 0.5 });
    }
    for (const it of items) if (it.type === 'tree') { it.cx = it.x; it.cy = it.y; }

    this.static[f.id] = items;
    (this.shadows ||= {})[f.id] = items
      .filter((it) => it.type === 'prism' && it.z0 < 0.3 && it.z1 - it.z0 >= 0.25)
      .map((it) => ({ poly: it.poly, h: Math.min(it.z1, 2.4) }));
    Object.assign(this.seats, seatsAll);
  }

  _rect(x, y, w, h) { return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]; }

  _buildCampus(f) {
    const items = [];
    for (const r of this.doc.rooms.filter((x) => x.floor_id === f.id && x.kind === 'building')) {
      const b = bbox(r.polygon);
      const h = r.link_floor ? 6 : 4;                    // ตึกที่มีแผนที่ภายในสูงกว่าเล็กน้อย
      const n = Math.max(1, Math.ceil(Math.max(b.x2 - b.x1, b.y2 - b.y1) / 12));
      const horiz = b.x2 - b.x1 >= b.y2 - b.y1;
      for (let i = 0; i < n; i++) {                       // แบ่งเป็นช่วงเพื่อให้เรียงความลึกถูกต้อง
        const seg = horiz ? this._rect(b.x1 + ((b.x2 - b.x1) * i) / n, b.y1, (b.x2 - b.x1) / n, b.y2 - b.y1)
          : this._rect(b.x1, b.y1 + ((b.y2 - b.y1) * i) / n, b.x2 - b.x1, (b.y2 - b.y1) / n);
        const c = centroid(seg);
        items.push({ type: 'prism', poly: seg, z0: 0, z1: h, color: '#f4f6f6', top: r.color || '#cfd8dc', cx: c[0], cy: c[1] });
      }
    }
    this.static[f.id] = items;
    (this.shadows ||= {})[f.id] = items.map((it) => ({ poly: it.poly, h: it.z1 }));
  }

  // พื้นที่เตียงรักษา (เช่น เตียงกายภาพ): เตียงเรียงเป็นแถว มีม่านกั้นระหว่างเตียง
  _buildBeds(r, items) {
    const b = bbox(r.polygon);
    const w = b.x2 - b.x1, h = b.y2 - b.y1;
    const tall = h >= w;               // แถวเตียงเรียงตามด้านยาวของห้อง
    const across = tall ? w : h, along = tall ? h : w;
    const L = 2.0, Wd = 0.95, gap = 1.8;
    const cols = across >= 11 ? [0.6, across / 2 - L / 2, across - 0.6 - L] : across >= 6 ? [0.6, across - 0.6 - L] : [across / 2 - L / 2];
    const beds = [];
    const at = (u, v) => (tall ? [b.x1 + u, b.y1 + v] : [b.x1 + v, b.y1 + u]);
    const box = (u1, u2, v1, v2) => { const p = [at(u1, v1), at(u2, v1), at(u2, v2), at(u1, v2)]; return p; };
    const push = (poly, z0, z1, color, top) => {
      const cx = poly.reduce((s, p) => s + p[0], 0) / 4, cy = poly.reduce((s, p) => s + p[1], 0) / 4;
      items.push({ type: 'prism', poly, z0, z1, color, top, cx, cy });
    };
    for (const u of cols) {
      for (let v = 1.2; v + Wd <= along - 0.8; v += gap) {
        push(box(u, u + L, v, v + Wd), 0, 0.55, '#bbdefb', '#f3f8fd');
        const headAtStart = u < across / 2;
        const pu = headAtStart ? u + 0.08 : u + L - 0.45;
        push(box(pu, pu + 0.37, v + 0.15, v + Wd - 0.15), 0.55, 0.66, '#ffffff', '#ffffff');   // หมอน
        push(box(u, u + L, v + Wd + 0.35, v + Wd + 0.4), 0, 1.25, '#e1d8f0', '#f3eefa');    // ม่านกั้น
        beds.push(at(u + L / 2, v + Wd / 2));
      }
    }
    (this.beds ||= {})[r.id] = beds;
  }

  // ระบบพิกัดของห้องแบบช่องบริการ: u = ตามแนวผนังด้านช่องบริการ, v = ลึกเข้าไปในห้อง
  _windowFrame(room) {
    const b = bbox(room.polygon);
    const side = room.desk || 'w';
    const vertical = side === 'w' || side === 'e';
    const L = vertical ? b.y2 - b.y1 : b.x2 - b.x1;
    const D = vertical ? b.x2 - b.x1 : b.y2 - b.y1;
    const at = (u, v) => ({ w: [b.x1 + v, b.y1 + u], e: [b.x2 - v, b.y1 + u], n: [b.x1 + u, b.y1 + v], s: [b.x1 + u, b.y2 - v] }[side]);
    const box = (u1, u2, v1, v2) => [at(u1, v1), at(u2, v1), at(u2, v2), at(u1, v2)];
    const margin = Math.min(1.2, L * 0.12);
    return { side, L, D, at, box, c0: margin, c1: L - margin, b };
  }

  _buildWindowRoom(r, items, addWall, onBoundary) {
    const f = this._windowFrame(r);
    const { b, side, L, D, at, box } = f;
    const poly = r.polygon;
    const isFront = (a, c) => ({
      w: Math.abs(a[0] - b.x1) < 0.05 && Math.abs(c[0] - b.x1) < 0.05,
      e: Math.abs(a[0] - b.x2) < 0.05 && Math.abs(c[0] - b.x2) < 0.05,
      n: Math.abs(a[1] - b.y1) < 0.05 && Math.abs(c[1] - b.y1) < 0.05,
      s: Math.abs(a[1] - b.y2) < 0.05 && Math.abs(c[1] - b.y2) < 0.05,
    }[side]);
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], c = poly[(i + 1) % poly.length];
      if (isFront(a, c)) {
        // ผนังสองข้างช่องบริการ
        addWall(at(0, 0), at(f.c0, 0), 2.1, PAL.innerTop, 0.18, true);
        addWall(at(f.c1, 0), at(L, 0), 2.1, PAL.innerTop, 0.18, true);
      } else if (!onBoundary(a, c)) addWall(a, c, 2.1, PAL.innerTop, 0.18);
    }
    const push = (pts, z0, z1, color, top) => {
      const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
      items.push({ type: 'prism', poly: pts, z0, z1, color, top, cx, cy });
    };
    const span = f.c1 - f.c0;
    const segs = Math.max(1, Math.ceil(span / 1.5));
    for (let i = 0; i < segs; i++) {
      const u1 = f.c0 + (span * i) / segs, u2 = f.c0 + (span * (i + 1)) / segs;
      push(box(u1, u2, -0.15, 0.4), 0, 1.05, '#ece6da', '#ffffff');           // เคาน์เตอร์
      push(box(u1, u2, -0.09, 0.09), 1.85, 2.1, PAL.wallSide, PAL.innerTop);  // คานบนช่องบริการ
    }
    // เสากรอบช่อง + เจ้าหน้าที่ + จอคอมพิวเตอร์
    const windows = Math.max(1, Math.round(span / 2.6));
    for (let i = 0; i <= windows; i++) {
      const u = f.c0 + (span * i) / windows;
      push(box(u - 0.06, u + 0.06, -0.06, 0.06), 1.05, 1.85, '#cfd8dc', '#eceff1');
    }
    for (let i = 0; i < windows; i++) {
      const u = f.c0 + (span * (i + 0.5)) / windows;
      push(box(u - 0.25, u + 0.25, 0.15, 0.3), 1.05, 1.42, '#3b4a5a', '#2b3743');
      if (this.opts.showStaff) {
        const [x, y] = at(u, 0.95);
        items.push({ type: 'staff', x, y, seed: hash(r.id + 'w' + i), cx: x, cy: y });
      }
    }
    // ของตกแต่งภายใน
    const shelf = (u1, u2, v1, v2, h) => {
      const n = Math.max(1, Math.ceil((u2 - u1) / 1.5));
      for (let i = 0; i < n; i++) {
        const a = u1 + ((u2 - u1) * i) / n, c = u1 + ((u2 - u1) * (i + 1)) / n;
        push(box(a, c, v1, v2), 0, h, '#e9e2d3', '#fbf8f2');
        // กล่องยาหลากสีบนชั้น
        const rr = rand(hash(r.id + a.toFixed(1) + v1.toFixed(1)));
        const colors = ['#e0479e', '#17b6d8', '#79d27c', '#f2b84b', '#8e7cc3'];
        for (let k = 0; k < 3; k++) {
          const s0 = a + (c - a) * (k / 3) + 0.05, s1 = a + (c - a) * ((k + 1) / 3) - 0.05;
          push(box(s0, s1, v1 + 0.05, v2 - 0.05), h, h + 0.12 + rr() * 0.1, colors[Math.floor(rr() * colors.length)], '#ffffff');
        }
      }
    };
    if (r.decor === 'pharmacy') {
      shelf(0.4, L - 0.4, D - 0.75, D - 0.3, 1.9);                     // ชั้นวางยาชิดผนังด้านหลัง
      if (D >= 5) {
        for (const v of [D * 0.45, D * 0.68]) shelf(L * 0.2, L * 0.8, v, v + 0.5, 1.5);  // ชั้นวางกลางห้อง
      }
      if (D >= 3.5) push(box(L * 0.35, L * 0.65, 1.7, 2.3), 0, 0.9, '#f7f4ee', '#ffffff'); // โต๊ะจัดยา
    } else if (r.decor === 'cashier') {
      push(box(0.4, L - 0.4, D - 0.7, D - 0.3), 0, 1.3, '#d7ccc8', '#efebe9');   // ตู้เอกสาร
      push(box(L - 1.2, L - 0.5, D - 1.5, D - 0.8), 0, 0.75, '#455a64', '#607d8b'); // ตู้เซฟ
      if (D >= 3.5) push(box(L * 0.3, L * 0.7, 1.6, 2.2), 0, 0.9, '#f7f4ee', '#ffffff');
    }
  }
  _thickLine(a, b, t) {
    const len = dist(a, b) || 1;
    const nx = (-(b[1] - a[1]) / len) * (t / 2), ny = ((b[0] - a[0]) / len) * (t / 2);
    return [[a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny], [b[0] - nx, b[1] - ny], [a[0] - nx, a[1] - ny]];
  }

  // ------------------------------------------------------------------ camera
  resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.dpr = dpr;
    this.w = w; this.h = h;
    if (!this._fitted) this.fit();
    this.dirty = true;
  }

  fit(padding = 30) {
    const f = this.floors?.[this.floorId];
    if (!f || !this.w) return;
    this._fitted = true;
    const corners = [[-4, -4], [f.width + 4, -4], [f.width + 4, f.height + 4], [-4, f.height + 4]];
    let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
    for (const [x, y] of corners) {
      const [xr, yr] = this._rot(x, y, this.targetAngle);
      const sx = (xr - yr) * COS30, sy = (xr + yr) * SIN30;
      minX = Math.min(minX, sx); maxX = Math.max(maxX, sx); minY = Math.min(minY, sy); maxY = Math.max(maxY, sy - 3);
    }
    const top = this.opts.padTop || 0, bottom = this.opts.padBottom || 0;
    const availH = this.h - top - bottom - padding * 2;
    const s = Math.min((this.w - padding * 2) / (maxX - minX), availH / (maxY - minY));
    this.scale = Math.max(2, s);
    const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
    this.pan = [-midX * this.scale, -midY * this.scale + (top - bottom) / 2];
    this.dirty = true;
  }

  zoomBy(f, sx = this.w / 2, sy = this.h / 2) {
    const ns = Math.max(2, Math.min(80, this.scale * f));
    const k = ns / this.scale;
    const cx = this.w / 2 + this.pan[0], cy = this.h / 2 + this.pan[1];
    this.pan[0] += (sx - cx) * (1 - k);
    this.pan[1] += (sy - cy) * (1 - k);
    this.scale = ns;
    this.dirty = true;
  }

  zoomSmooth(f) { this._zoomAnim = { target: Math.max(2, Math.min(80, this.scale * f)) }; this.dirty = true; }

  rotate(dir) { this.targetAngle += (dir * Math.PI) / 2; this.dirty = true; }

  focus(x, y, zoom) {
    if (zoom) this.scale = Math.max(this.scale, zoom);
    this._focusTarget = [x, y];
    this.dirty = true;
  }

  resetView() {
    this.targetAngle = Math.round(this.angle / (Math.PI * 2)) * Math.PI * 2;
    this._focusTarget = null;
    this.fit();
  }

  _rot(x, y, a = this.angle) {
    const dx = x - this.center[0], dy = y - this.center[1];
    const c = Math.cos(a), s = Math.sin(a);
    return [dx * c - dy * s, dx * s + dy * c];
  }

  project(x, y, z = 0) {
    const [xr, yr] = this._rot(x, y);
    return [this.w / 2 + this.pan[0] + (xr - yr) * COS30 * this.scale, this.h / 2 + this.pan[1] + ((xr + yr) * SIN30 - z * this.zMul) * this.scale];
  }

  depth(x, y) { const [xr, yr] = this._rot(x, y); return xr + yr; }

  unproject(sx, sy) {
    const u = (sx - this.w / 2 - this.pan[0]) / (COS30 * this.scale);
    const v = (sy - this.h / 2 - this.pan[1]) / (SIN30 * this.scale);
    const xr = (u + v) / 2, yr = (v - u) / 2;
    const c = Math.cos(-this.angle), s = Math.sin(-this.angle);
    return [xr * c - yr * s + this.center[0], xr * s + yr * c + this.center[1]];
  }

  // ------------------------------------------------------------------ input
  _bindEvents() {
    const c = this.canvas;
    c.style.touchAction = 'none';
    let downAt = null, moved = 0, pinch = null;
    c.addEventListener('pointerdown', (e) => {
      c.setPointerCapture(e.pointerId);
      this._pointers.set(e.pointerId, [e.offsetX, e.offsetY]);
      downAt = [e.offsetX, e.offsetY]; moved = 0;
      if (this._pointers.size === 2) {
        const [a, b] = [...this._pointers.values()];
        pinch = { d: dist(a, b), s: this.scale };
      }
    });
    c.addEventListener('pointermove', (e) => {
      const prev = this._pointers.get(e.pointerId);
      if (!prev) { if (e.pointerType === 'mouse') this._hover(e.offsetX, e.offsetY); return; }
      const cur = [e.offsetX, e.offsetY];
      this._pointers.set(e.pointerId, cur);
      if (this._pointers.size === 2 && pinch) {
        const [a, b] = [...this._pointers.values()];
        const target = pinch.s * (dist(a, b) / pinch.d);
        this.zoomBy(target / this.scale, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
        moved += 10;
        return;
      }
      this.pan[0] += cur[0] - prev[0];
      this.pan[1] += cur[1] - prev[1];
      moved += Math.abs(cur[0] - prev[0]) + Math.abs(cur[1] - prev[1]);
      this._focusTarget = null;
      this.dirty = true;
    });
    const up = (e) => {
      this._pointers.delete(e.pointerId);
      if (this._pointers.size < 2) pinch = null;
      if (downAt && moved < 6 && this._pointers.size === 0) this._click(e.offsetX, e.offsetY);
      if (this._pointers.size === 0) downAt = null;
    };
    c.addEventListener('pointerup', up);
    c.addEventListener('pointerleave', () => { this.hoverRoom = null; this.hoverVn = null; c.style.cursor = ''; this.dirty = true; });
    c.addEventListener('pointercancel', up);
    c.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.zoomBy(Math.exp(-e.deltaY * 0.0015), e.offsetX, e.offsetY);
    }, { passive: false });
  }

  _hover(sx, sy) {
    let vn = null, bd = 16;
    for (const hit of this._hits || []) {
      const d = Math.hypot(hit.sx - sx, hit.sy - sy);
      if (d < bd) { bd = d; vn = hit.vn; }
    }
    let room = null;
    if (!vn && this.doc) {
      const [x, y] = this.unproject(sx, sy);
      room = this.doc.rooms.find((r) => r.floor_id === this.floorId && r.kind !== 'corridor' && pointInPoly(x, y, r.polygon))?.id || null;
    }
    if (vn !== this.hoverVn || room !== this.hoverRoom) {
      this.hoverVn = vn; this.hoverRoom = room; this.dirty = true;
      this.canvas.style.cursor = vn || room ? 'pointer' : '';
      this.emit('hover', { vn, room });
    }
  }

  _click(sx, sy) {
    let best = null, bd = 18;
    for (const hit of this._hits || []) {
      const d = Math.hypot(hit.sx - sx, hit.sy - sy);
      if (d < bd) { bd = d; best = hit; }
    }
    if (best) return this.emit('person', best.vn);
    const [x, y] = this.unproject(sx, sy);
    const room = this.doc?.rooms.find((r) => r.floor_id === this.floorId && pointInPoly(x, y, r.polygon) && r.kind !== 'corridor')
      || this.doc?.rooms.find((r) => r.floor_id === this.floorId && pointInPoly(x, y, r.polygon));
    this.emit('room', room ? room.id : null);
  }

  // ------------------------------------------------------------------ animation + render
  _frame(t) {
    const dt = Math.min(0.1, (t - this._last) / 1000);
    this._last = t;
    let animating = false;
    if (this.zMul < 1) {
      this._rise = Math.min(1, this._rise + dt / 0.9);
      this.zMul = this._rise >= 1 ? 1 : Math.max(0, easeOutBack(this._rise));
      animating = true;
    }
    if (this._zoomAnim) {
      const k = Math.min(1, dt * 9);
      const next = this.scale + (this._zoomAnim.target - this.scale) * k;
      this.zoomBy(next / this.scale);
      if (Math.abs(this._zoomAnim.target - this.scale) < 0.01) this._zoomAnim = null;
      animating = true;
    }
    // หมุนแบบนุ่มนวล
    if (Math.abs(this.targetAngle - this.angle) > 0.001) {
      this.angle += (this.targetAngle - this.angle) * Math.min(1, dt * 8);
      if (Math.abs(this.targetAngle - this.angle) < 0.002) this.angle = this.targetAngle;
      animating = true;
    }
    if (this._focusTarget) {
      const [x, y] = this._focusTarget;
      const [sx, sy] = this.project(x, y, 0);
      const dx = this.w / 2 - sx, dy = (this.h - (this.opts.padBottom || 0) + (this.opts.padTop || 0)) / 2 - sy;
      this.pan[0] += dx * Math.min(1, dt * 6);
      this.pan[1] += dy * Math.min(1, dt * 6);
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) this._focusTarget = null;
      animating = true;
    }
    // เดินตามเส้นทาง
    const speed = this.opts.walkSpeed || 3.2; // เมตร/วินาที (ภาพ)
    for (const [vn, p] of this.persons) {
      if (!p.path || p.path.length < 1) continue;
      animating = true;
      p.travel = (p.travel || 0) + speed * dt;
      let remain = p.travel;
      let placed = false;
      for (let i = 1; i < p.path.length; i++) {
        const a = p.path[i - 1], b = p.path[i];
        const cross = a[0] !== b[0];
        const len = cross ? 6 : dist([a[1], a[2]], [b[1], b[2]]);
        if (remain <= len) {
          if (cross) { p.floor = null; p.x = b[1]; p.y = b[2]; } // อยู่ในลิฟต์/บันได
          else { const k = len ? remain / len : 1; p.floor = a[0]; p.x = a[1] + (b[1] - a[1]) * k; p.y = a[2] + (b[2] - a[2]) * k; p.dir = Math.atan2(b[2] - a[2], b[1] - a[1]); }
          placed = true;
          break;
        }
        remain -= len;
      }
      if (!placed) {
        const end = p.path[p.path.length - 1];
        p.floor = end[0]; p.x = end[1]; p.y = end[2];
        p.path = null; p.travel = 0;
        if (p.leaving) { this.persons.delete(vn); }
      }
    }
    if (this.route) { this._dash = (this._dash + dt * 14) % 1000; animating = true; }
    if (this.selected || this.hoverVn || this.crowdedPulse) animating = true;
    if (animating || this.dirty) this.render();
    this.dirty = false;
    requestAnimationFrame((tt) => this._frame(tt));
  }

  render() {
    const ctx = this.ctx;
    const f = this.floors?.[this.floorId];
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (!f) return;
    const S = this.scale;
    const now = performance.now();
    const rooms = this.doc.rooms.filter((r) => r.floor_id === f.id);

    // ชั้นพื้น (สนามหญ้า ทางเดิน พื้นห้อง เงา) — แคชไว้ วาดใหม่เฉพาะเมื่อกล้องหรือข้อมูลเปลี่ยน
    ctx.drawImage(this._floorLayer(f, rooms), 0, 0);
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);

    // ไฮไลต์ห้องที่ชี้เมาส์ / ห้องที่เลือก / ห้องแออัด (กะพริบ)
    let crowded = false;
    for (const r of rooms) {
      if (r.kind === 'corridor') continue;
      const ratio = (this.counts[r.id] || 0) / Math.max(1, r.capacity || 20);
      if (r.id === this.highlightRoom || r.id === this.hoverRoom) {
        this._polyPath(ctx, r.polygon, r.kind === 'building' ? (r.link_floor ? 6 : 4) : 0.02);
        ctx.save();
        ctx.shadowColor = 'rgba(224,71,158,0.55)'; ctx.shadowBlur = 14;
        ctx.strokeStyle = r.id === this.highlightRoom ? 'rgba(224,71,158,0.95)' : 'rgba(224,71,158,0.55)';
        ctx.lineWidth = r.id === this.highlightRoom ? 3 : 2;
        ctx.stroke();
        ctx.restore();
      } else if (ratio >= 0.8 && (r.kind === 'waiting' || r.kind === 'counter') && f.style !== 'campus') {
        crowded = true;
        const a = 0.25 + 0.25 * Math.sin(now / 420);
        this._polyPath(ctx, r.polygon, 0.02);
        ctx.strokeStyle = `rgba(217,74,58,${a})`; ctx.lineWidth = 2.5; ctx.stroke();
      }
    }

    this.crowdedPulse = crowded;
    if (this.route) this._drawRoute(ctx, now);

    // วัตถุ 3 มิติ เรียงตามความลึก
    const draw = [];
    for (const it of this.static[f.id] || []) draw.push({ d: this.depth(it.cx, it.cy), it });
    const hits = [];
    for (const p of this.persons.values()) {
      if (p.floor !== f.id) continue;
      draw.push({ d: this.depth(p.x, p.y) + 0.3, it: { type: 'person', p } });
    }
    for (const c of this.crowd) if (c.floor === f.id) draw.push({ d: this.depth(c.x, c.y) + 0.3, it: { type: 'crowd', c } });
    draw.sort((a, b) => a.d - b.d);
    for (const { it } of draw) {
      if (it.type === 'prism') this._prism(ctx, it.poly, it.z0, it.z1, it.color, it.top);
      else if (it.type === 'tree') this._tree(ctx, it, now);
      else if (it.type === 'staff') this._figure(ctx, it.x, it.y, it.seed, { clothes: PAL.staff, now, idle: true });
      else if (it.type === 'crowd') this._figure(ctx, it.c.x, it.c.y, it.c.seed, { seated: it.c.seated, now });
      else if (it.type === 'person') {
        const p = it.p;
        const seated = !p.path && p.seat;
        const sel = this.selected === p.vn;
        p.alpha = Math.min(1, (p.alpha ?? 0) + 0.06);
        this._figure(ctx, p.x, p.y, p.seed, {
          seated, selected: sel, hover: this.hoverVn === p.vn, me: p.me, now,
          walk: p.path ? p.travel || 0 : null, alpha: p.alpha * (this.selected && !sel && this.opts.dimOthers ? 0.45 : 1),
        });
        const [sx, sy] = this.project(p.x, p.y, seated ? 1.1 : 1.5);
        hits.push({ vn: p.vn, sx, sy });
      }
    }
    this._hits = hits;

    // ป้ายชื่อห้อง (ค่อย ๆ ปรากฏตามการซูมและแอนิเมชันอาคาร)
    const labelAlpha = (f.style === 'campus' ? 1 : Math.min(1, Math.max(0, (S - 4) / 3))) * Math.min(1, this.zMul * 1.4);
    if (this.opts.showLabels && labelAlpha > 0.02) {
      ctx.save(); ctx.globalAlpha = labelAlpha; this._labels(ctx, rooms); ctx.restore();
    }
    const sel = this.selected && this.persons.get(this.selected);
    if (sel && sel.floor === f.id) {
      const [sx, sy] = this.project(sel.x, sel.y, 2.4);
      const text = sel.data ? `${sel.data.q} · ${sel.data.label}` : '';
      this._pill(ctx, sx, sy - 10 + Math.sin(now / 400) * 2, text, { bg: PAL.route, fg: '#fff', bold: true, arrow: true });
    } else if (this.hoverVn && this.persons.get(this.hoverVn)?.floor === f.id) {
      const h = this.persons.get(this.hoverVn);
      const [sx, sy] = this.project(h.x, h.y, 2.2);
      if (h.data) this._pill(ctx, sx, sy - 6, `${h.data.q} · ${h.data.label}`, { arrow: true, dark: true });
    }
    if (this.route && this.route.dest && this.route.dest[0] === f.id) this._pin(ctx, this.route.dest[1], this.route.dest[2], now);
  }

  // ------------------------------------------------------------------ ชั้นพื้น (แคช)
  _floorLayer(f, rooms) {
    const key = [f.id, this.angle.toFixed(4), this.scale.toFixed(3), this.pan[0].toFixed(1), this.pan[1].toFixed(1),
      this.canvas.width, this.canvas.height, this.zMul.toFixed(3), this._countsVer, this.showPlan,
      this.images[f.plan_image]?.complete].join('|');
    if (this._layerKey === key && this._layer) return this._layer;
    this._layerKey = key;
    const c = (this._layer ||= document.createElement('canvas'));
    if (c.width !== this.canvas.width || c.height !== this.canvas.height) { c.width = this.canvas.width; c.height = this.canvas.height; }
    const ctx = c.getContext('2d');
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    const W = f.width, H = f.height;
    const campusImg = f.style === 'campus' && this.images[f.plan_image];
    if (campusImg) {
      if (campusImg.complete && campusImg.naturalWidth) {
        const o = this.project(0, 0), ex = this.project(W, 0), ey = this.project(0, H);
        ctx.save();
        ctx.setTransform(this.dpr * (ex[0] - o[0]) / campusImg.width, this.dpr * (ex[1] - o[1]) / campusImg.width,
          this.dpr * (ey[0] - o[0]) / campusImg.height, this.dpr * (ey[1] - o[1]) / campusImg.height, this.dpr * o[0], this.dpr * o[1]);
        ctx.drawImage(campusImg, 0, 0);
        ctx.restore();
        // ทำภาพให้อ่อนลงเล็กน้อย ตึก 3 มิติจะเด่นขึ้น
        this._polyPath(ctx, [[0, 0], [W, 0], [W, H], [0, H]], 0);
        ctx.fillStyle = 'rgba(255,255,255,0.28)'; ctx.fill();
      }
      ctx.beginPath();
      for (const s of this.shadows?.[f.id] || []) {
        const dx = s.h * 0.45 * this.zMul, dy = s.h * 0.3 * this.zMul;
        const pts = [];
        for (const q of s.poly) { pts.push([q[0], q[1]]); pts.push([q[0] + dx, q[1] + dy]); }
        convexHull(pts).forEach((q, i) => { const [sx, sy] = this.project(q[0], q[1], 0); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); });
        ctx.closePath();
      }
      ctx.fillStyle = 'rgba(20,40,40,0.18)';
      ctx.fill('nonzero');
      return c;
    }

    // สนามหญ้า + ทางเท้ารอบอาคาร
    const M = 18;
    const lawn = [[-M, -M], [W + M, -M], [W + M, H + M], [-M, H + M]];
    const top = this.project(W / 2, -M), bottom = this.project(W / 2, H + M);
    const g = ctx.createLinearGradient(0, Math.min(top[1], bottom[1]), 0, Math.max(top[1], bottom[1]) + 1);
    g.addColorStop(0, '#e4f2e6'); g.addColorStop(1, '#d1e9d9');
    this._polyPath(ctx, lawn, 0); ctx.fillStyle = g; ctx.fill();
    // ลายหญ้าจาง ๆ
    ctx.fillStyle = 'rgba(80,150,100,0.08)';
    const rr = rand(hash(f.id + 'grass'));
    ctx.beginPath();
    for (let i = 0; i < 260; i++) {
      const gx = -M + rr() * (W + 2 * M), gy = -M + rr() * (H + 2 * M);
      if (gx > -3 && gx < W + 3 && gy > -3 && gy < H + 3) continue;
      const [sx, sy] = this.project(gx, gy, 0);
      ctx.moveTo(sx + 2.2, sy); ctx.ellipse(sx, sy, 2.2, 1.1, 0, 0, Math.PI * 2);
    }
    ctx.fill();
    this._polyPath(ctx, [[-2.6, -2.6], [W + 2.6, -2.6], [W + 2.6, H + 2.6], [-2.6, H + 2.6]], 0);
    ctx.fillStyle = '#eef1f0'; ctx.fill();
    ctx.strokeStyle = 'rgba(120,140,135,0.18)'; ctx.lineWidth = 1; ctx.stroke();
    // ทางเดินจากประตูทางเข้า-ออก
    for (const n of this.doc.nodes) {
      if (n.floor_id !== f.id || (n.kind !== 'entrance' && n.kind !== 'exit')) continue;
      const dl = n.x, dr = W - n.x, dt = n.y, db = H - n.y;
      const mn = Math.min(dl, dr, dt, db);
      const L = M - 1, hw = 1.7;
      let poly;
      if (mn === dl) poly = [[n.x, n.y - hw], [n.x - L, n.y - hw], [n.x - L, n.y + hw], [n.x, n.y + hw]];
      else if (mn === dr) poly = [[n.x, n.y - hw], [n.x + L, n.y - hw], [n.x + L, n.y + hw], [n.x, n.y + hw]];
      else if (mn === dt) poly = [[n.x - hw, n.y], [n.x - hw, n.y - L], [n.x + hw, n.y - L], [n.x + hw, n.y]];
      else poly = [[n.x - hw, n.y], [n.x - hw, n.y + L], [n.x + hw, n.y + L], [n.x + hw, n.y]];
      this._polyPath(ctx, poly, 0); ctx.fillStyle = '#e7ebe9'; ctx.fill();
      ctx.strokeStyle = 'rgba(31,158,143,0.28)'; ctx.setLineDash([4, 4]); ctx.stroke(); ctx.setLineDash([]);
    }

    // ฐานอาคาร
    this._prism(ctx, [[0, 0], [W, 0], [W, H], [0, H]], -0.6, 0, PAL.slabSide, PAL.slabTop);
    // ลายกระเบื้องพื้น
    ctx.beginPath();
    for (let x = 2; x < W; x += 2) { const a = this.project(x, 0), b = this.project(x, H); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
    for (let y = 2; y < H; y += 2) { const a = this.project(0, y), b = this.project(W, y); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
    ctx.strokeStyle = 'rgba(40,70,70,0.045)'; ctx.lineWidth = 1; ctx.stroke();

    // พื้นห้อง (ไล่เฉดอ่อน ๆ ให้มีมิติ)
    const order = { corridor: 0, waiting: 1, other: 1, counter: 2, service: 3, window: 3 };
    for (const r of [...rooms].sort((a, b) => (order[a.kind] ?? 1) - (order[b.kind] ?? 1))) {
      const ratio = (this.counts[r.id] || 0) / Math.max(1, r.capacity || 20);
      let fill = r.color || (r.kind === 'corridor' ? PAL.corridor : (r.kind === 'service' || r.kind === 'window') ? PAL.service : r.kind === 'counter' ? PAL.counter : PAL.waitLow);
      if (!r.color && (r.kind === 'waiting' || r.kind === 'counter') && this.opts.density !== false) fill = densityColor(ratio);
      this._polyPath(ctx, r.polygon, 0);
      if (r.kind === 'corridor') { ctx.fillStyle = fill; ctx.fill(); continue; }
      const b0 = bbox(r.polygon);
      const p0 = this.project(b0.x1, b0.y1), p1 = this.project(b0.x2, b0.y2);
      const gr = ctx.createLinearGradient(p0[0], p0[1], p1[0] + 0.1, p1[1] + 0.1);
      gr.addColorStop(0, shade(fill, 1.05)); gr.addColorStop(1, shade(fill, 0.97));
      ctx.fillStyle = gr; ctx.fill();
      ctx.strokeStyle = 'rgba(31,158,143,0.22)'; ctx.lineWidth = 1; ctx.stroke();
    }

    if (this.showPlan && f.plan_image && this.images[f.plan_image]?.complete) {
      const img = this.images[f.plan_image];
      const o = this.project(0, 0), ex = this.project(W, 0), ey = this.project(0, H);
      ctx.save();
      ctx.globalAlpha = f.plan_opacity ?? 0.5;
      ctx.setTransform(this.dpr * (ex[0] - o[0]) / img.width, this.dpr * (ex[1] - o[1]) / img.width,
        this.dpr * (ey[0] - o[0]) / img.height, this.dpr * (ey[1] - o[1]) / img.height, this.dpr * o[0], this.dpr * o[1]);
      ctx.drawImage(img, 0, 0);
      ctx.restore();
    }

    // เงาผนังและเฟอร์นิเจอร์ (แสงจากทิศตะวันตกเฉียงเหนือ) — วาดรวมเป็นเส้นทางเดียว เงาไม่ซ้อนเข้ม
    const k = this.zMul;
    ctx.beginPath();
    for (const s of this.shadows?.[f.id] || []) {
      const dx = s.h * 0.45 * k, dy = s.h * 0.3 * k;
      // เงา = รูปทรงที่ครอบฐานกับตำแหน่งที่เลื่อนไป (convex hull แบบง่ายของสี่เหลี่ยม 2 ชิ้น)
      const pts = [];
      for (const q of s.poly) { pts.push([q[0], q[1]]); pts.push([q[0] + dx, q[1] + dy]); }
      const hull = convexHull(pts);
      hull.forEach((q, i) => { const [sx, sy] = this.project(q[0], q[1], 0); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); });
      ctx.closePath();
    }
    ctx.fillStyle = 'rgba(30,60,60,0.075)';
    ctx.fill('nonzero');
    return c;
  }

  _polyPath(ctx, poly, z) {
    ctx.beginPath();
    poly.forEach((p, i) => { const [sx, sy] = this.project(p[0], p[1], z); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); });
    ctx.closePath();
  }

  _labels(ctx, rooms) {
    const placed = [];
    for (const r of rooms) {
      if (r.kind === 'corridor') continue;
      const n = this.counts[r.id] || 0;
      const [cx, cy] = centroid(r.polygon);
      const [sx, sy] = this.project(cx, cy, r.kind === 'building' ? 7.5 : 2.6);
      const name = r.short_name || r.name;
      const showCount = this.opts.labelMode !== 'names' && (r.kind === 'waiting' || r.kind === 'counter' || (r.kind === 'building' && r.link_floor));
      const ratio = n / Math.max(1, r.capacity || 20);
      const w = this._pillWidth(ctx, name + (showCount ? ` ${n} คน` : '')) + (showCount ? 12 : 0);
      // ห้องเล็กที่อยู่ติดกัน: ขยับป้ายขึ้น/ลงหลบกันแทนการซ่อน
      const hit = (y) => placed.some((p) => Math.abs(p[0] - sx) < (p[2] + w) / 2 + 2 && Math.abs(p[1] - y) < 27);
      const dy = [0, -29, 29, -58, 58, -87].find((d) => !hit(sy + d));
      if (dy === undefined) continue;
      const ly = sy + dy;
      placed.push([sx, ly, w]);
      if (dy) {
        ctx.strokeStyle = 'rgba(31,45,51,0.3)';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(sx, dy < 0 ? ly : ly - 25); ctx.lineTo(sx, sy - 6); ctx.stroke();
        ctx.fillStyle = 'rgba(31,45,51,0.4)';
        ctx.beginPath(); ctx.arc(sx, sy - 4, 2.5, 0, Math.PI * 2); ctx.fill();
      }
      this._pill(ctx, sx, ly, name, {
        count: showCount ? `${n} คน` : null, countColor: densityText(ratio), dot: showCount ? densityText(ratio) : null,
        highlight: this.highlightRoom === r.id || this.hoverRoom === r.id,
      });
    }
  }

  _pillWidth(ctx, text) {
    const fs = 12 * (this.opts.labelScale || 1);
    ctx.font = `600 ${fs}px ${FONT}`;
    return ctx.measureText(text).width + 22 * (this.opts.labelScale || 1);
  }

  _pill(ctx, x, y, text, o = {}) {
    if (!text) return;
    const ls = this.opts.labelScale || 1;
    const fs = 12 * ls;
    ctx.font = `${o.bold ? 700 : 600} ${fs}px ${FONT}`;
    const tw = ctx.measureText(text).width;
    let cw = 0;
    if (o.count) { ctx.font = `700 ${fs}px ${FONT}`; cw = ctx.measureText(o.count).width + 8; }
    const dotW = o.dot ? 12 : 0;
    const w = tw + cw + dotW + 20 * ls, h = 25 * ls;
    const x0 = x - w / 2, y0 = y - h;
    ctx.save();
    ctx.shadowColor = o.bg ? 'rgba(224,71,158,0.35)' : 'rgba(20,50,50,0.16)';
    ctx.shadowBlur = o.bg ? 14 : 10;
    ctx.shadowOffsetY = 3;
    if (o.bg) {
      const g = ctx.createLinearGradient(x0, y0, x0 + w, y0 + h);
      g.addColorStop(0, shade(o.bg, 1.12)); g.addColorStop(1, shade(o.bg, 0.88));
      ctx.fillStyle = g;
    } else ctx.fillStyle = o.dark ? 'rgba(31,45,51,0.92)' : o.highlight ? '#fff0f7' : 'rgba(255,255,255,0.97)';
    this._roundRect(ctx, x0, y0, w, h, 12.5);
    ctx.fill();
    ctx.restore();
    if (o.highlight && !o.bg) {
      ctx.strokeStyle = 'rgba(224,71,158,0.6)'; ctx.lineWidth = 1.5;
      this._roundRect(ctx, x0, y0, w, h, 12.5); ctx.stroke();
    }
    if (o.arrow) {
      ctx.fillStyle = o.bg ? shade(o.bg, 0.92) : o.dark ? 'rgba(31,45,51,0.92)' : '#fff';
      ctx.beginPath(); ctx.moveTo(x - 6, y - 0.5); ctx.lineTo(x + 6, y - 0.5); ctx.lineTo(x, y + 6); ctx.closePath(); ctx.fill();
    }
    let tx = x0 + 10;
    if (o.dot) {
      ctx.fillStyle = o.dot;
      ctx.beginPath(); ctx.arc(tx + 3.5, y0 + h / 2, 3.5, 0, Math.PI * 2); ctx.fill();
      tx += dotW;
    }
    ctx.fillStyle = o.fg || (o.dark ? '#fff' : '#23323a');
    ctx.textBaseline = 'middle';
    ctx.font = `${o.bold ? 700 : 600} ${fs}px ${FONT}`;
    ctx.fillText(text, tx, y0 + h / 2 + 1);
    if (o.count) {
      ctx.font = `700 ${fs}px ${FONT}`;
      ctx.fillStyle = o.countColor;
      ctx.fillText(o.count, tx + tw + 8, y0 + h / 2 + 1);
    }
  }

  _roundRect(ctx, x, y, w, h, r) {
    r = Math.max(0, Math.min(r, w / 2, h / 2));
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  _poly(ctx, poly, z, fill) {
    this._polyPath(ctx, poly, z);
    ctx.fillStyle = fill;
    ctx.fill();
  }

  _prism(ctx, poly, z0, z1, side, top) {
    const ccw = signedArea(poly) > 0;
    const n = poly.length;
    const c = Math.cos(this.angle), s = Math.sin(this.angle);
    for (let i = 0; i < n; i++) {
      const a = poly[i], b = poly[(i + 1) % n];
      // เวกเตอร์ตั้งฉากออกนอก (ในพิกัดที่หมุนแล้ว)
      let nx = b[1] - a[1], ny = -(b[0] - a[0]);
      if (!ccw) { nx = -nx; ny = -ny; }
      const rx = nx * c - ny * s, ry = nx * s + ny * c;
      if (rx + ry <= 0.0001) continue;
      // แสงนุ่ม: หน้าที่หันเข้าหาแสงสว่างกว่า
      const len = Math.hypot(rx, ry) || 1;
      const light = 0.8 + 0.15 * (rx / len);
      const p1 = this.project(a[0], a[1], z0), p2 = this.project(b[0], b[1], z0), p3 = this.project(b[0], b[1], z1), p4 = this.project(a[0], a[1], z1);
      ctx.beginPath(); ctx.moveTo(p1[0], p1[1]); ctx.lineTo(p2[0], p2[1]); ctx.lineTo(p3[0], p3[1]); ctx.lineTo(p4[0], p4[1]); ctx.closePath();
      ctx.fillStyle = shade(side, light);
      ctx.fill();
    }
    this._poly(ctx, poly, z1, top || side);
    if (z1 - z0 >= 1.5) {
      ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 1; ctx.stroke();  // ขอบบนผนังสว่าง
    }
  }

  _figure(ctx, x, y, seed, o = {}) {
    const S = this.scale;
    const r = rand(seed);
    const clothes = o.clothes || PAL.clothes[Math.floor(r() * PAL.clothes.length)];
    const skin = PAL.skin[Math.floor(r() * PAL.skin.length)];
    const hair = r() < 0.5 ? '#3a2a20' : '#5b4636';
    const pants = r() < 0.5 ? '#34495e' : '#4a4e69';
    const [bx, by] = this.project(x, y, 0);
    const walking = o.walk != null;
    const phase = walking ? o.walk * 3.2 : 0;
    const bob = walking ? Math.abs(Math.sin(phase)) * 0.05 * S : (o.idle ? Math.sin((o.now || 0) / 900 + seed) * 0.012 * S : 0);
    const bodyW = 0.42 * S;
    const seatZ = o.seated ? 0.45 * S : 0;
    ctx.save();
    if (o.alpha != null && o.alpha < 1) ctx.globalAlpha = o.alpha;
    // เงาใต้เท้า
    ctx.fillStyle = 'rgba(20,40,40,0.16)';
    ctx.beginPath(); ctx.ellipse(bx + 0.06 * S, by + 0.02 * S, bodyW * 0.8, bodyW * 0.38, 0, 0, Math.PI * 2); ctx.fill();
    if (o.selected || o.me || o.hover) {
      const pulse = 1 + 0.22 * Math.sin((o.now || 0) / 250);
      ctx.strokeStyle = o.hover && !o.selected && !o.me ? 'rgba(224,71,158,0.6)' : PAL.route;
      ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.ellipse(bx, by, bodyW * 1.5 * pulse, bodyW * 0.75 * pulse, 0, 0, Math.PI * 2); ctx.stroke();
      if (o.selected || o.me) {
        ctx.fillStyle = 'rgba(224,71,158,0.12)';
        ctx.beginPath(); ctx.ellipse(bx, by, bodyW * 1.5 * pulse, bodyW * 0.75 * pulse, 0, 0, Math.PI * 2); ctx.fill();
      }
    }
    const main = o.selected || o.me ? PAL.route : clothes;
    // ขา (ยืน/เดินสลับขา)
    const legH = 0.48 * S, legW = 0.13 * S;
    if (!o.seated) {
      const sw = walking ? Math.sin(phase) * 0.09 * S : 0;
      ctx.fillStyle = pants;
      this._roundRect(ctx, bx - 0.11 * S - legW / 2 + sw, by - legH - bob, legW, legH - Math.max(0, sw) * 0.3, legW / 2); ctx.fill();
      this._roundRect(ctx, bx + 0.11 * S - legW / 2 - sw, by - legH - bob, legW, legH - Math.max(0, -sw) * 0.3, legW / 2); ctx.fill();
    }
    // ลำตัว (ไล่เฉด)
    const torsoH = 0.62 * S;
    const torsoBottom = by - (o.seated ? seatZ : legH * 0.92) - bob;
    const top = torsoBottom - torsoH;
    const tg = ctx.createLinearGradient(bx - bodyW / 2, top, bx + bodyW / 2, torsoBottom);
    tg.addColorStop(0, shade(main, 1.12)); tg.addColorStop(1, shade(main, 0.88));
    ctx.fillStyle = tg;
    this._roundRect(ctx, bx - bodyW / 2, top, bodyW, torsoH + (o.seated ? seatZ * 0.25 : 0), bodyW * 0.42);
    ctx.fill();
    // แขนแกว่งตอนเดิน
    if (!o.seated) {
      const aw = walking ? Math.sin(phase) * 0.08 * S : 0;
      ctx.fillStyle = shade(main, 0.82);
      this._roundRect(ctx, bx - bodyW / 2 - 0.07 * S - aw * 0.4, top + 0.06 * S, 0.1 * S, torsoH * 0.82, 0.05 * S); ctx.fill();
      this._roundRect(ctx, bx + bodyW / 2 - 0.03 * S + aw * 0.4, top + 0.06 * S, 0.1 * S, torsoH * 0.82, 0.05 * S); ctx.fill();
    }
    // ศีรษะ + ผม
    const hr = 0.165 * S;
    const hy = top - hr * 0.55;
    ctx.fillStyle = skin;
    ctx.beginPath(); ctx.arc(bx, hy, hr, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = hair;
    ctx.beginPath(); ctx.arc(bx, hy - hr * 0.2, hr * 0.98, Math.PI * 1.02, Math.PI * 1.98); ctx.fill();
    ctx.restore();
  }

  _tree(ctx, t, now) {
    const S = this.scale;
    const k = this.zMul;
    const [bx, by] = this.project(t.x, t.y, 0);
    const sway = Math.sin(now / 1600 + t.x) * 0.06 * S;
    ctx.fillStyle = 'rgba(30,70,50,0.13)';
    ctx.beginPath(); ctx.ellipse(bx + 0.9 * S * t.s * k, by + 0.15 * S, 1.5 * S * t.s, 0.7 * S * t.s, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#8d6e52';
    ctx.fillRect(bx - 0.12 * S, by - 1.6 * S * t.s * k, 0.24 * S, 1.6 * S * t.s * k);
    const cy = by - 2.6 * S * t.s * k, rr = 1.25 * S * t.s * Math.max(0.2, k);
    const g = ctx.createRadialGradient(bx - rr * 0.4 + sway, cy - rr * 0.45, rr * 0.1, bx + sway, cy, rr * 1.05);
    g.addColorStop(0, '#a6e8a0'); g.addColorStop(0.55, '#5cc26c'); g.addColorStop(1, '#2f9a55');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(bx + sway, cy, rr, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.18)';
    ctx.beginPath(); ctx.arc(bx - rr * 0.35 + sway, cy - rr * 0.35, rr * 0.35, 0, Math.PI * 2); ctx.fill();
  }

  _drawRoute(ctx, now) {
    const pts = this.route.points;
    const f = this.floorId;
    const segs = [];
    let cur = [];
    for (const p of pts) {
      if (p[0] === f) cur.push(p);
      else if (cur.length) { segs.push(cur); cur = []; }
    }
    if (cur.length) segs.push(cur);
    const S = this.scale;
    for (const seg of segs) {
      if (seg.length < 2) continue;
      const scr = seg.map((p) => this.project(p[1], p[2], 0.05));
      const path = () => { ctx.beginPath(); scr.forEach(([sx, sy], i) => (i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy))); };
      ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      ctx.save();
      ctx.shadowColor = 'rgba(224,71,158,0.55)'; ctx.shadowBlur = 16;
      path(); ctx.strokeStyle = 'rgba(255,255,255,0.95)'; ctx.lineWidth = Math.max(7, S * 0.8); ctx.stroke();
      ctx.restore();
      path(); ctx.strokeStyle = PAL.route; ctx.lineWidth = Math.max(4, S * 0.5); ctx.stroke();
      // ลูกศรไหลตามทิศทางการเดิน
      const spacing = Math.max(26, S * 1.6);
      const shift = ((now / 1000) * 40) % spacing;
      const sz = Math.max(3.2, S * 0.2);
      ctx.fillStyle = 'rgba(255,255,255,0.95)';
      let walked = 0;
      for (let i = 1; i < scr.length; i++) {
        const [ax, ay] = scr[i - 1], [bx2, by2] = scr[i];
        const L = Math.hypot(bx2 - ax, by2 - ay);
        if (L < 1) continue;
        const ux = (bx2 - ax) / L, uy = (by2 - ay) / L;
        // ตำแหน่งลูกศรถัดไปบนเส้นรวม: shift, shift+spacing, ...
        let t = shift + Math.ceil((walked - shift) / spacing) * spacing - walked;
        for (; t < L; t += spacing) {
          if (t < 0) continue;
          const cx = ax + ux * t, cy = ay + uy * t;
          ctx.beginPath();
          ctx.moveTo(cx + ux * sz, cy + uy * sz);
          ctx.lineTo(cx - ux * sz - uy * sz * 0.9, cy - uy * sz + ux * sz * 0.9);
          ctx.lineTo(cx - ux * sz * 0.35, cy - uy * sz * 0.35);
          ctx.lineTo(cx - ux * sz + uy * sz * 0.9, cy - uy * sz - ux * sz * 0.9);
          ctx.closePath(); ctx.fill();
        }
        walked += L;
      }
    }
    // จุดเริ่ม (คลื่นกระจาย)
    const s0 = pts[0];
    if (s0 && s0[0] === f) {
      const [sx, sy] = this.project(s0[1], s0[2], 0.05);
      const k = (now % 1600) / 1600;
      ctx.strokeStyle = `rgba(224,71,158,${0.5 * (1 - k)})`; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.ellipse(sx, sy, 8 + k * 18, (8 + k * 18) * 0.5, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(sx, sy, 7, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = PAL.route; ctx.beginPath(); ctx.arc(sx, sy, 4.5, 0, Math.PI * 2); ctx.fill();
    }
    // จุดเปลี่ยนชั้น
    for (let i = 1; i < pts.length; i++) {
      if (pts[i][0] !== pts[i - 1][0]) {
        const here = pts[i - 1][0] === f ? pts[i - 1] : pts[i][0] === f ? pts[i] : null;
        if (here) {
          const other = this.floors[pts[i - 1][0] === f ? pts[i][0] : pts[i - 1][0]];
          const [sx, sy] = this.project(here[1], here[2], 3);
          this._pill(ctx, sx, sy, `ไป${other?.name || 'ชั้นอื่น'}`, { bg: '#1f9e8f', fg: '#fff', bold: true, arrow: true });
        }
      }
    }
  }

  _pin(ctx, x, y, now) {
    const [sx, sy] = this.project(x, y, 0);
    const bob = Math.sin(now / 300) * 3;
    const k = (now % 1800) / 1800;
    ctx.strokeStyle = `rgba(224,71,158,${0.55 * (1 - k)})`; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.ellipse(sx, sy, 6 + k * 22, (6 + k * 22) * 0.5, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = 'rgba(0,0,0,0.15)';
    ctx.beginPath(); ctx.ellipse(sx, sy, 8, 4, 0, 0, Math.PI * 2); ctx.fill();
    const top = sy - 36 + bob;
    ctx.save();
    ctx.shadowColor = 'rgba(224,71,158,0.5)'; ctx.shadowBlur = 12;
    const g = ctx.createLinearGradient(sx - 12, top - 12, sx + 12, top + 14);
    g.addColorStop(0, '#f06ab4'); g.addColorStop(1, '#c93d8f');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(sx, top, 12, Math.PI * 0.85, Math.PI * 0.15);
    ctx.lineTo(sx, sy - 4 + bob);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(sx, top, 5, 0, Math.PI * 2); ctx.fill();
  }

}
