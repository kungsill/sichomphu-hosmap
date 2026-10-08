export const $ = (sel, root = document) => root.querySelector(sel);

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export async function api(url, opts = {}) {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (res.status === 401 && !location.pathname.startsWith('/t/')) {
    location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    throw new Error('กรุณาเข้าสู่ระบบ');
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch { /* ไม่ใช่ JSON */ }
    throw new Error(msg);
  }
  return res.json();
}

export function stepperHtml(stages) {
  return `<div class="stepper">${(stages || []).map((s) => `<div class="step ${s.status}"><i></i><span>${esc(s.label)}</span></div>`).join('')}</div>`;
}

export function stateClass(p) {
  if (!p) return '';
  if (p.state === 'finished') return 'done';
  if (p.walking || (p.dest && p.dep && p.dest !== p.dep) || p.label?.startsWith('เดินไป')) return 'walk';
  if (p.state === 'waiting' || p.state === 'service_done') return 'wait';
  return '';
}

export function sexAge(p) {
  const sex = p.sex === '1' ? 'ชาย' : p.sex === '2' ? 'หญิง' : '';
  return [sex, p.age != null ? `อายุ ${p.age} ปี` : ''].filter(Boolean).join(' ');
}

export function vitalsText(v) {
  if (!v) return '';
  const parts = [];
  if (v.bw) parts.push(`น้ำหนัก <b>${v.bw}</b> กก.`);
  if (v.bps) parts.push(`ความดัน <b>${Math.round(v.bps)}/${Math.round(v.bpd || 0)}</b>`);
  if (v.temperature) parts.push(`อุณหภูมิ <b>${Number(v.temperature).toFixed(1)}</b> °C`);
  return parts.join(' ');
}

export function toast(msg, ms = 2600) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

// EventSource ที่ต่อใหม่อัตโนมัติ
export function liveStream(url, onData, onState) {
  let es, retry = 1000;
  const connect = () => {
    es = new EventSource(url);
    es.onopen = () => { retry = 1000; onState?.(true); };
    es.onmessage = (e) => { try { onData(JSON.parse(e.data)); } catch (err) { console.error(err); } };
    es.onerror = () => {
      onState?.(false);
      es.close();
      setTimeout(connect, retry);
      retry = Math.min(retry * 2, 15000);
    };
  };
  connect();
  return () => es?.close();
}
