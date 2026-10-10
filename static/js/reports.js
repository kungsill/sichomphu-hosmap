// รายงานผู้บริหาร: กราฟ SVG (สีเดียว + ป้ายค่า + tooltip) และตารางสรุป
import { $, api, esc, toast } from './common.js';

let days = 1;
let data = null;
let sortKey = 'median_wait';
let sortDesc = true;
const NS = 'http://www.w3.org/2000/svg';

const thDate = (iso) => {
  const d = new Date(iso + 'T00:00:00');
  return `${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear() + 543}`;
};
const fmt = (v, unit = '') => (v == null ? '–' : `${Number.isInteger(v) ? v : v.toFixed(1)}${unit}`);

async function load() {
  document.querySelector('.wrap').classList.add('loading');
  try {
    data = await api(`/api/reports?days=${days}`);
    render();
  } catch (err) {
    toast('โหลดรายงานไม่สำเร็จ: ' + err.message, 5000);
  } finally {
    document.querySelector('.wrap').classList.remove('loading');
  }
}

document.querySelectorAll('.seg button').forEach((b) => {
  b.onclick = () => {
    days = Number(b.dataset.d);
    document.querySelectorAll('.seg button').forEach((x) => x.classList.toggle('on', x === b));
    $('#csv').href = `/api/reports.csv?days=${days}`;
    load();
  };
});

function render() {
  const d = data;
  $('#range').textContent = `${d.days === 1 ? 'วันนี้' : `${d.days} วัน`} · ${thDate(d.from)}${d.from !== d.to ? ` – ${thDate(d.to)}` : ''} · ข้อมูลจาก ${d.source === 'hosxp' ? 'HOSxP (opd_dep_queue)' : 'ระบบนำทาง'} · อัปเดต ${d.generated}`;
  const k = d.kpi;
  const tiles = [
    ['ผู้ป่วยทั้งหมด', fmt(k.visits), 'คน', d.days > 1 ? `เฉลี่ย ${fmt(k.per_day)} คน/วัน` : 'Visit ที่เปิดวันนี้'],
    ['รอรับบริการ (ค่ากลาง)', fmt(k.median_wait), 'นาที', `90% รอไม่เกิน ${fmt(k.p90_wait)} นาที`],
    ['เวลาให้บริการ (ค่ากลาง)', fmt(k.median_service), 'นาที', 'ตั้งแต่รับจนเสร็จที่แต่ละจุด'],
    ['อยู่ในโรงพยาบาล (ค่ากลาง)', fmt(k.median_stay), 'นาที', 'ตั้งแต่เปิด Visit ถึงจุดสุดท้าย'],
  ];
  $('#kpis').innerHTML = tiles.map(([t, v, u, s], i) => `<div class="kpi4 glass anim d${i + 1}"><div class="k">${t}</div><div class="v">${v}<small> ${u}</small></div><div class="s">${s}</div></div>`).join('');

  columnChart($('#hourly'), d.hourly.map((h) => ({ label: String(h.hour).padStart(2, '0'), value: h.avg, tip: `${String(h.hour).padStart(2, '0')}:00–${String(h.hour + 1).padStart(2, '0')}:00 · <b>${fmt(h.avg)}</b> คน/วัน` })));
  barChart($('#zones'), d.zones.map((z) => ({ label: z.name, value: z.n, valueText: z.n.toLocaleString('th-TH'), tip: `${esc(z.name)} · <b>${z.n.toLocaleString('th-TH')}</b> Visit` })));
  heatmap($('#heat'), d.heat, $('#heatLegend'));
  const top = d.services.filter((s) => s.median_wait != null && s.n >= Math.max(3, d.days)).sort((a, b) => b.median_wait - a.median_wait).slice(0, 15);
  barChart($('#waits'), top.map((s) => ({ label: s.name, value: s.median_wait, valueText: `${fmt(s.median_wait)} น.`,
    tip: `${esc(s.name)}<br>ค่ากลาง <b>${fmt(s.median_wait)}</b> นาที · P90 <b>${fmt(s.p90_wait)}</b> นาที · ${s.n.toLocaleString('th-TH')} ครั้ง` })), 230);
  table();
  $('#note').textContent = d.source === 'hosxp'
    ? 'เวลารอ = accept_datetime − queue_datetime, เวลาให้บริการ = finish_datetime − accept_datetime (ตัดค่าที่ติดลบหรือเกิน 10 ชั่วโมง) · จุดที่ไม่มีเวลารับ/เสร็จใน HOSxP จะไม่มีค่า'
    : `ข้อมูลจากเหตุการณ์ที่ระบบนำทางบันทึก${d.source_error ? ` (อ่าน HOSxP ไม่ได้: ${d.source_error})` : ''}`;
}

// ------------------------------------------------------------------ ตัวช่วยกราฟ
function svgEl(tag, attrs = {}, parent) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  parent?.appendChild(el);
  return el;
}
function tooltip(box) {
  let tip = box.querySelector('.tip');
  if (!tip) { tip = document.createElement('div'); tip.className = 'tip'; box.appendChild(tip); }
  return {
    show(html, x, y) { tip.innerHTML = html; tip.style.left = `${x}px`; tip.style.top = `${y}px`; tip.style.display = 'block'; },
    hide() { tip.style.display = 'none'; },
  };
}
const niceMax = (v) => {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v);
};
// แท่งมุมมนเฉพาะปลายข้อมูล (ฐานแท่งเป็นมุมฉาก)
const roundTop = (x, y, w, h, r) => (h <= 0 ? '' : `M${x},${y + h}V${y + Math.min(r, h)}Q${x},${y} ${x + Math.min(r, w / 2)},${y}H${x + w - Math.min(r, w / 2)}Q${x + w},${y} ${x + w},${y + Math.min(r, h)}V${y + h}Z`);
const roundRight = (x, y, w, h, r) => (w <= 0 ? '' : `M${x},${y}H${x + w - Math.min(r, w)}Q${x + w},${y} ${x + w},${y + Math.min(r, h / 2)}V${y + h - Math.min(r, h / 2)}Q${x + w},${y + h} ${x + w - Math.min(r, w)},${y + h}H${x}Z`);

function columnChart(box, items) {
  box.innerHTML = '';
  const W = Math.max(320, box.clientWidth || 640), H = 260, L = 36, B = 24, T = 18;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'กราฟแท่งผู้ป่วยมาถึงรายชั่วโมง' }, box);
  const max = niceMax(Math.max(...items.map((i) => i.value), 0));
  const ih = H - T - B, step = (W - L) / items.length, bw = Math.max(4, step - 2);
  const ticks = [5, 4, 2].find((n) => Number.isInteger(max / n)) || 4;
  for (let g = 0; g <= ticks; g++) {
    const y = T + ih - (ih * g) / ticks;
    svgEl('line', { x1: L, x2: W, y1: y, y2: y, stroke: 'var(--grid)' }, svg);
    svgEl('text', { x: L - 6, y: y + 4, 'text-anchor': 'end' }, svg).textContent = +((max * g) / ticks).toFixed(1);
  }
  const tip = tooltip(box);
  const bars = [];
  const peak = items.reduce((a, b) => (b.value > a.value ? b : a), items[0]);
  items.forEach((it, i) => {
    const h = (it.value / max) * ih, x = L + i * step + 1, y = T + ih - h;
    const bar = svgEl('path', { d: roundTop(x, y, bw, h, 4), class: 'bar' }, svg);
    bars.push(bar);
    svgEl('text', { x: x + bw / 2, y: H - 6, 'text-anchor': 'middle' }, svg).textContent = it.label;
    if (it === peak && it.value > 0) svgEl('text', { x: x + bw / 2, y: y - 6, 'text-anchor': 'middle', class: 'val' }, svg).textContent = fmt(it.value);
    const hit = svgEl('rect', { x: L + i * step, y: T, width: step, height: ih, fill: 'transparent' }, svg);
    hit.addEventListener('pointerenter', () => {
      bars.forEach((b) => b.classList.toggle('dim', b !== bar));
      const r = box.getBoundingClientRect(), sr = svg.getBoundingClientRect();
      tip.show(it.tip, ((x + bw / 2) / W) * sr.width + (sr.left - r.left), (y / H) * sr.height + (sr.top - r.top));
    });
    hit.addEventListener('pointerleave', () => { bars.forEach((b) => b.classList.remove('dim')); tip.hide(); });
  });
}

function barChart(box, items, labelW = 170) {
  box.innerHTML = '';
  if (!items.length) { box.innerHTML = '<div class="note">ไม่มีข้อมูลในช่วงนี้</div>'; return; }
  const W = Math.max(320, box.clientWidth || 640), rowH = 26, gap = 6, R = 64, H = items.length * (rowH + gap);
  labelW = Math.min(labelW, W * 0.42);
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'กราฟแท่งแนวนอน' }, box);
  const max = niceMax(Math.max(...items.map((i) => i.value), 0));
  const iw = W - labelW - R;
  const tip = tooltip(box);
  const bars = [];
  items.forEach((it, i) => {
    const y = i * (rowH + gap), w = (it.value / max) * iw;
    const name = it.label.length > 24 ? it.label.slice(0, 23) + '…' : it.label;
    svgEl('text', { x: labelW - 10, y: y + rowH / 2 + 4, 'text-anchor': 'end' }, svg).textContent = name;
    svgEl('rect', { x: labelW, y, width: iw, height: rowH, fill: 'var(--grid)', rx: 4, opacity: 0.45 }, svg);
    const bar = svgEl('path', { d: roundRight(labelW, y, Math.max(w, 2), rowH, 4), class: 'bar' }, svg);
    bars.push(bar);
    svgEl('text', { x: labelW + Math.max(w, 2) + 8, y: y + rowH / 2 + 4, class: 'val' }, svg).textContent = it.valueText;
    const hit = svgEl('rect', { x: 0, y, width: W, height: rowH, fill: 'transparent' }, svg);
    hit.addEventListener('pointerenter', () => {
      bars.forEach((b) => b.classList.toggle('dim', b !== bar));
      const r = box.getBoundingClientRect(), sr = svg.getBoundingClientRect();
      tip.show(it.tip, ((labelW + Math.max(w, 2) / 2) / W) * sr.width + (sr.left - r.left), (y / H) * sr.height + (sr.top - r.top));
    });
    hit.addEventListener('pointerleave', () => { bars.forEach((b) => b.classList.remove('dim')); tip.hide(); });
  });
}

function heatmap(box, heat, legend) {
  box.innerHTML = '';
  const hours = [...new Set(heat.cells.map((c) => c.hour))];
  const daysL = heat.days;
  const max = Math.max(1, ...heat.cells.map((c) => c.n));
  const ramp = ['--heat-0', '--heat-1', '--heat-2', '--heat-3', '--heat-4', '--heat-5'];
  const step = (n) => (n === 0 ? 0 : Math.min(5, 1 + Math.floor((n / max) * 4.999)));
  const W = Math.max(320, box.clientWidth || 640);
  const L = 74, T = 6, cw = (W - L) / hours.length, ch = daysL.length > 14 ? 16 : 26, H = T + daysL.length * ch + 22;
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'ตารางความร้อนผู้ป่วยมาถึง วันกับชั่วโมง' }, box);
  const tip = tooltip(box);
  const byKey = Object.fromEntries(heat.cells.map((c) => [`${c.day}|${c.hour}`, c.n]));
  daysL.forEach((d, r) => {
    const dt = new Date(d + 'T00:00:00');
    const lbl = `${['อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส'][dt.getDay()]} ${dt.getDate()}/${dt.getMonth() + 1}`;
    if (daysL.length <= 14 || r % 2 === 0) svgEl('text', { x: L - 8, y: T + r * ch + ch / 2 + 4, 'text-anchor': 'end' }, svg).textContent = lbl;
    hours.forEach((h, c) => {
      const n = byKey[`${d}|${h}`] || 0;
      const x = L + c * cw, y = T + r * ch;
      const cell = svgEl('rect', { x: x + 1, y: y + 1, width: cw - 2, height: ch - 2, rx: 3, fill: `var(${ramp[step(n)]})` }, svg);
      cell.addEventListener('pointerenter', () => {
        cell.setAttribute('stroke', 'var(--text-primary)'); cell.setAttribute('stroke-width', '1.5');
        const rr = box.getBoundingClientRect(), sr = svg.getBoundingClientRect();
        tip.show(`${lbl} · ${String(h).padStart(2, '0')}:00 น. · <b>${n}</b> คน`, ((x + cw / 2) / W) * sr.width + (sr.left - rr.left), (y / H) * sr.height + (sr.top - rr.top));
      });
      cell.addEventListener('pointerleave', () => { cell.removeAttribute('stroke'); tip.hide(); });
    });
  });
  hours.forEach((h, c) => {
    if (c % 2 === 0) svgEl('text', { x: L + c * cw + cw / 2, y: H - 6, 'text-anchor': 'middle' }, svg).textContent = String(h).padStart(2, '0');
  });
  legend.innerHTML = `น้อย ${ramp.map((v) => `<i style="background:var(${v})"></i>`).join('')} มาก (สูงสุด ${max} คน/ชั่วโมง)`;
}

function table() {
  const cols = [
    ['depcode', 'รหัส'], ['name', 'หน่วยบริการ'], ['n', 'จำนวนครั้ง'], ['median_wait', 'รอ ค่ากลาง (นาที)'],
    ['p90_wait', 'รอ P90 (นาที)'], ['median_service', 'ให้บริการ ค่ากลาง (นาที)'],
  ];
  const rows = [...data.services].sort((a, b) => {
    const x = a[sortKey] ?? -1, y = b[sortKey] ?? -1;
    return (typeof x === 'string' ? x.localeCompare(y, 'th') : x - y) * (sortDesc ? -1 : 1);
  });
  $('#tbl').innerHTML = `<thead><tr>${cols.map(([k, t]) => `<th data-k="${k}">${t}${k === sortKey ? (sortDesc ? ' ▼' : ' ▲') : ''}</th>`).join('')}</tr></thead>
    <tbody>${rows.map((s) => `<tr><td>${esc(s.depcode)}</td><td>${esc(s.name)}</td><td>${s.n.toLocaleString('th-TH')}</td><td>${fmt(s.median_wait)}</td><td>${fmt(s.p90_wait)}</td><td>${fmt(s.median_service)}</td></tr>`).join('')}</tbody>`;
  $('#tbl').querySelectorAll('th').forEach((th) => {
    th.onclick = () => {
      if (sortKey === th.dataset.k) sortDesc = !sortDesc; else { sortKey = th.dataset.k; sortDesc = true; }
      table();
    };
  });
}

let rz;
window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => data && render(), 150); });
load();
