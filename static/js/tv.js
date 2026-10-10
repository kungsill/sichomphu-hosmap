// จอทีวีหน้าห้องรอ: แผนที่สดของโซน + คิวที่กำลังให้บริการ + คิวถัดไป (แสดงเฉพาะเลขคิว)
import { IsoMap } from './iso.js';
import { $, api, esc, liveStream } from './common.js';

const params = new URLSearchParams(location.search);
const floorId = params.get('f');
const voice = params.get('voice') === '1';

async function picker() {
  const m = await api('/api/map');
  const bsort = Object.fromEntries(m.buildings.map((b) => [b.id, b.sort ?? 0]));
  const floors = m.floors.filter((f) => f.style !== 'campus').sort((a, b) => bsort[a.building_id] - bsort[b.building_id]);
  $('#zones').innerHTML = floors.map((f) => {
    const b = m.buildings.find((x) => x.id === f.building_id);
    return `<a href="/tv?f=${encodeURIComponent(f.id)}">${esc(b?.name || '')} · ${esc(f.name)}</a>`;
  }).join('');
  $('#picker').classList.remove('hidden');
}

async function start() {
  $('#tv').classList.remove('hidden');
  const iso = new IsoMap($('#map'), { walkSpeed: 2.6, labelScale: 1.15 });
  const doc = await api('/api/map');
  iso.setMap(doc);
  iso.setFloor(floorId);
  let first = true;
  let seen = new Set();
  let mapVersion = doc.version;
  // หมุนมุมมองช้า ๆ ทุก 2 นาที ให้เห็นทุกด้าน
  setInterval(() => iso.rotate(1), 120000);

  liveStream(`/api/tv/${encodeURIComponent(floorId)}/stream`, async (v) => {
    if (v.map_version !== mapVersion) {
      mapVersion = v.map_version;
      iso.setMap(await api('/api/map'));
      iso.setFloor(floorId);
    }
    $('#zone').textContent = v.zone;
    $('#hosp').textContent = v.hospital;
    $('#clock').textContent = v.time || '';
    document.title = `จอแสดงคิว · ${v.zone}`;
    iso.setCounts(v.rooms);
    iso.setPatients(v.patients, first);

    const fresh = v.calling.filter((c) => !seen.has(c.q));
    $('#calling').innerHTML = v.calling.length
      ? v.calling.map((c) => `<div class="call ${!first && fresh.includes(c) ? 'new' : ''}"><span class="q">${esc(c.q)}</span><span class="w">${esc(c.where || '')}</span></div>`).join('')
      : '<div class="empty">ยังไม่มีผู้รับบริการขณะนี้</div>';
    if (voice && !first) fresh.forEach((c) => speak(c));
    seen = new Set(v.calling.map((c) => c.q));

    // จุดที่มีคนรอขึ้นก่อน จุดที่ว่างไปท้าย
    const svcs = [...v.services].sort((a, b) => (b.waiting + b.serving > 0) - (a.waiting + a.serving > 0) || b.waiting - a.waiting);
    $('#svcs').innerHTML = svcs.length ? svcs.map((s) => `<div class="svc-row">
        <div class="top">${esc(s.name)}<span>รอ ${s.waiting} คน · ~${s.est} นาที</span></div>
        <div class="chips">${s.next.map((q) => `<b>${esc(q)}</b>`).join('') || '<span class="muted">ไม่มีคิวรอ</span>'}</div></div>`).join('')
      : '<div class="empty">ไม่มีจุดบริการในโซนนี้</div>';
    first = false;
  });
}

// เสียงเรียกคิวภาษาไทย (อ่านตัวอักษร/ตัวเลขทีละตัว)
function speak(c) {
  if (!('speechSynthesis' in window)) return;
  const q = String(c.q || '').split('').join(' ');
  const u = new SpeechSynthesisUtterance(`ขอเชิญหมายเลข ${q} ที่ ${c.where || ''} ค่ะ`);
  u.lang = 'th-TH';
  u.rate = 0.9;
  speechSynthesis.speak(u);
}

(floorId ? start() : picker()).catch((err) => { document.body.insertAdjacentHTML('beforeend', `<p style="padding:20px">${esc(err.message)}</p>`); });
