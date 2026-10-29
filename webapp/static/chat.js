/* Sohbet asistanı. İki mod:
   - Proje açıkken (adreste #<id>): projeyi okur, yeniden üretir, fiyat ve künye ayarlar.
   - Proje yokken (“Projeyi üret”ten önce): ihtiyaçlar ve ek özellikler sohbetle toplanır, asistan projeyi üretir.
   Mesaj ve proje özeti Anthropic'e yalnız onay kutusu işaretliyken gider. Planı değiştiren istekler yeni proje üretir. */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const store = {get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* özel pencere */ } }};
const pid = () => decodeURIComponent((location.hash || '').slice(1));
const HKEY = id => 'archai.chat.' + (id || 'yeni'), MAXH = 40;
const CHIPS_OPEN = ['Proje özetini ver', 'Çekmeleri 3 m yap', 'KDV’yi %10 yap', 'En pahalı kalemleri göster',
  'Teklifi firma bilgilerimle güncelle: '];
const CHIPS_NEW = ['Zemin katta işyeri, bodrum ve çatı katı olsun', 'Kat başına 4 daire', 'Emsal dışı alan 120 m²',
  'Formdaki değerlerle üret', 'Eklenecek özellik: '];
const FORM = {proje_adi: '#name', parsel_cephe: '#pw', parsel_derinlik: '#pd', taks: '#taks', kaks: '#kaks', on_cekme: '#fr',
  yan_cekme: '#sd', arka_cekme: '#rr', maks_kat: '#mf', kat_yuksekligi: '#fh', yencok: '#mh', emsal_disi_m2: '#ed',
  daire_tipi: '#ut', kat_basi_daire: '#upf', hizli_m2: '#qa', hizli_kat: '#qf'};
let hist = [], busy = false, attach = null;

const md = t => {                       // güvenli mini işaretleme: **kalın**, `kod`, "- " maddeleri, satır sonları
  const lines = esc(t).split('\n'); let out = '', ul = false;
  for (const l of lines) {
    const m = /^\s*[-•*]\s+(.*)$/.exec(l);
    if (m) { if (!ul) { out += '<ul>'; ul = true; } out += `<li>${m[1]}</li>`; continue; }
    if (ul) { out += '</ul>'; ul = false; }
    out += l + '<br>';
  }
  if (ul) out += '</ul>';
  return out.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/(<br>)+$/, '');
};

function build() {
  document.body.insertAdjacentHTML('beforeend', `
<button id="chatfab" type="button" aria-label="Asistanı aç">◆ ASİSTAN</button>
<aside id="chatpanel" aria-label="Proje asistanı">
  <header><div><b id="chattitle">ASİSTAN</b><small id="chatproj"></small></div><span class="sp"></span>
    <button id="chatclear" title="Sohbeti temizle" type="button">⟲</button><button id="chatclose" title="Kapat" type="button">✕</button></header>
  <label id="chatconsent"><input type="checkbox" id="chatok"><span>Mesajlarım ve proje özeti (parsel, imar, maliyet) yanıt için Anthropic’in Claude hizmetine gönderilir.</span></label>
  <div id="chatmsgs" role="log" aria-live="polite"></div>
  <div id="chatattach"></div>
  <div id="chatchips"></div>
  <form id="chatform"><button id="chatclip" type="button" title="Parsel dosyası yükle (DXF / GeoJSON / KML)" aria-label="Parsel DXF yükle">📎</button>
    <input type="file" id="chatfile" accept=".dxf,.geojson,.json,.kml" hidden>
    <textarea id="chatin" rows="2"></textarea>
    <button id="chatsend" type="submit">GÖNDER</button></form>
</aside>`);
}

const isNew = () => !pid();
function add(cls, html, extra) {
  const d = document.createElement('div'); d.className = 'm ' + cls; d.innerHTML = html;
  if (extra) d.append(extra);
  const box = $('#chatmsgs'); box.append(d); box.scrollTop = box.scrollHeight; return d;
}
function render() {
  $('#chatmsgs').innerHTML = '';
  if (!hist.length) add('s', isNew()
    ? 'Projeyi üretmeden önce ihtiyaçlarınızı ve ek özelliklerinizi yazın; yeterli bilgi olunca projeyi ben üretirim.'
    : 'Projeyle ilgili ayrıntıları yazın; ben uygularım.');
  hist.forEach(m => add(m.role === 'user' ? 'u' : 'a', m.role === 'user' ? esc(m.content).replace(/\n/g, '<br>') : md(m.content)));
}
function modeUi() {
  $('#chattitle').textContent = isNew() ? 'YENİ PROJE · ASİSTAN' : 'ASİSTAN';
  $('#chatin').placeholder = isNew()
    ? 'Ek özellikleri yazın… (ör. “zemin katta 4 dükkân, 6 normal kat, kat başı 4 daire, bodrum sığınak”)'
    : 'Ayrıntıları yazın… (ör. “parsel cephe 18, derinlik 30, TAKS 0,40, 5 kat”)';
  $('#chatchips').innerHTML = (isNew() ? CHIPS_NEW : CHIPS_OPEN).map(c => `<button type="button">${esc(c)}</button>`).join('');
  $('#chatclip').style.display = isNew() ? '' : 'none';
  showAttach();
}
function showAttach() {
  $('#chatattach').innerHTML = attach && isNew()
    ? `<span class="chip2">📎 parsel DXF · ${esc(attach.area)} m² · ${attach.polygon.length} köşe <button type="button" id="chatdetach" aria-label="Kaldır">✕</button></span>` : '';
  const d = $('#chatdetach'); if (d) d.onclick = () => { attach = null; showAttach(); };
}
function naming() {                    // proje adı sayfa yüklenince gelir: birkaç kez dene
  const set = () => { const t = $('#hname')?.textContent?.trim(); $('#chatproj').textContent = pid() ? (t || pid()) : 'proje henüz üretilmedi'; return !!t || !pid(); };
  let n = 0; const tick = setInterval(() => { if (set() || ++n > 20) clearInterval(tick); }, 500); set();
}
function load() {
  try { hist = JSON.parse(store.get(HKEY(pid())) || '[]'); } catch { hist = []; }
  modeUi(); naming(); render();
}
const save = (id = pid()) => store.set(HKEY(id), JSON.stringify(hist.slice(-MAXH)));

function formValues() {
  const out = {};
  for (const [k, sel] of Object.entries(FORM)) { const el = $(sel); if (el && String(el.value ?? '').trim() !== '') out[k] = el.value; }
  return out;
}

async function send(text) {
  const id = pid();
  if (busy || !text.trim()) return;
  if (!$('#chatok').checked) { add('e', 'Önce onay kutusunu işaretleyin: mesajlar Claude’a gönderilir.'); return; }
  busy = true; $('#chatsend').disabled = true;
  const prior = hist.slice(-20).map(({role, content}) => ({role, content}));
  hist.push({role: 'user', content: text}); add('u', esc(text).replace(/\n/g, '<br>'));
  const wait = add('a', '<span class="typing"><i></i><i></i><i></i></span>');
  try {
    const body = {message: text, history: prior, consent: true};
    if (!id) { body.form = formValues(); if (attach) body.parsel = {polygon: attach.polygon}; }
    const r = await fetch(id ? `/api/projects/${encodeURIComponent(id)}/chat` : '/api/chat',
      {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    const j = await r.json().catch(() => ({}));
    wait.remove();
    if (!r.ok) { add('e', esc(j.detail || r.statusText)); hist.pop(); save(); return; }
    hist.push({role: 'assistant', content: j.reply}); save();
    const extra = document.createElement('div');
    for (const a of (j.actions || []).filter(x => !x.ok)) extra.insertAdjacentHTML('beforeend', `<span class="act" title="${esc(a.error)}">⚠ ${esc(a.tool)}</span>`);
    add('a', md(j.reply), extra);
    if (j.new_project) {                          // sohbet yeni projede sürsün: geçmişi taşı, projeyi aç
      save(j.new_project);
      if (!id) store.set(HKEY(''), null);
      const b = document.createElement('button'); b.className = 'act'; b.type = 'button'; b.textContent = 'YENİ PROJEYİ AÇ →';
      const go = () => { location.hash = '#' + j.new_project; location.reload(); };
      b.onclick = go; extra.append(b); setTimeout(go, 1600);
    } else if (j.updated) {
      add('s', 'Güncellendi — sayfa yenileniyor…'); setTimeout(() => location.reload(), 1400);
    }
  } catch (e) {
    wait.remove(); add('e', 'Asistana ulaşılamadı: ' + esc(e.message)); hist.pop(); save();
  } finally { busy = false; $('#chatsend').disabled = false; }
}

async function upload(file) {
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await fetch('/api/parcel/dxf', {method: 'POST', body: fd});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { add('e', esc(j.detail || 'DXF okunamadı')); return; }
    attach = {polygon: j.polygon, area: j.area}; showAttach();
    add('s', `Parsel yüklendi: ${j.polygon.length} köşe, ≈${j.area} m². ${esc(j.note || '')}`);
  } catch (e) { add('e', 'DXF yüklenemedi: ' + esc(e.message)); }
}

function wire() {
  const panel = $('#chatpanel'), fab = $('#chatfab'), inp = $('#chatin');
  const open = on => { panel.classList.toggle('on', on); fab.classList.toggle('on', on); store.set('archai.chat.open', on ? '1' : null); if (on) inp.focus(); };
  window.archaiChatOpen = () => open(true);
  fab.onclick = () => open(true); $('#chatclose').onclick = () => open(false);
  $('#chatclear').onclick = () => { hist = []; save(); render(); };
  const ok = $('#chatok'); ok.checked = store.get('archai.chat.consent') === '1';
  ok.onchange = () => store.set('archai.chat.consent', ok.checked ? '1' : null);
  $('#chatform').onsubmit = e => { e.preventDefault(); const t = inp.value; inp.value = ''; inp.style.height = ''; send(t); };
  inp.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#chatform').requestSubmit(); } };
  inp.oninput = () => { inp.style.height = 'auto'; inp.style.height = Math.min(120, inp.scrollHeight) + 'px'; };
  $('#chatclip').onclick = () => $('#chatfile').click();
  $('#chatfile').onchange = e => { const f = e.target.files[0]; e.target.value = ''; if (f) upload(f); };
  $('#chatchips').onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    const t = b.textContent;
    if (t.endsWith(': ')) { inp.value = t; inp.focus(); } else send(t);
  };
  addEventListener('hashchange', load);
  if (store.get('archai.chat.open') === '1') open(true);
}

fetch('/api/chat/status').then(r => r.json()).then(s => {
  build(); wire(); load();
  if (!s.available) add('e', 'Claude kimlik bilgisi bulunamadı: sunucuyu ANTHROPIC_API_KEY ile başlatın ya da <code>ant auth login</code> çalıştırın.');
}).catch(() => { /* sohbet yoksa uygulama aynen çalışır */ });
