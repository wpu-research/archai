/* Sohbet asistanı: sağdaki panelden proje ayrıntıları verilir (parsel, imar, kat/daire, fiyat, künye).
   Mesaj ve proje özeti Anthropic'e yalnız onay kutusu işaretliyken gider. Planı değiştiren istekler yeni proje üretir. */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const store = {get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* özel pencere */ } }};
const pid = () => decodeURIComponent((location.hash || '').slice(1));
const HKEY = id => 'archai.chat.' + id, MAXH = 40;
const CHIPS = ['Proje özetini ver', 'Çekmeleri 3 m yap', 'KDV’yi %10 yap', 'En pahalı kalemleri göster',
  'Teklifi firma bilgilerimle güncelle: '];
let hist = [], busy = false;

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
  <header><div><b>ASİSTAN</b><small id="chatproj"></small></div><span class="sp"></span>
    <button id="chatclear" title="Sohbeti temizle" type="button">⟲</button><button id="chatclose" title="Kapat" type="button">✕</button></header>
  <label id="chatconsent"><input type="checkbox" id="chatok"><span>Mesajlarım ve proje özeti (parsel, imar, maliyet) yanıt için Anthropic’in Claude hizmetine gönderilir.</span></label>
  <div id="chatmsgs" role="log" aria-live="polite"></div>
  <div id="chatchips"></div>
  <form id="chatform"><textarea id="chatin" rows="1" placeholder="Ayrıntıları yazın… (ör. “parsel cephe 18, derinlik 30, TAKS 0,40, 5 kat”)"></textarea>
    <button id="chatsend" type="submit">GÖNDER</button></form>
</aside>`);
  $('#chatchips').innerHTML = CHIPS.map(c => `<button type="button">${esc(c)}</button>`).join('');
}

function add(cls, html, extra) {
  const d = document.createElement('div'); d.className = 'm ' + cls; d.innerHTML = html;
  if (extra) d.append(extra);
  const box = $('#chatmsgs'); box.append(d); box.scrollTop = box.scrollHeight; return d;
}
function render() {
  $('#chatmsgs').innerHTML = '';
  if (!hist.length) add('s', pid() ? 'Projeyle ilgili ayrıntıları yazın; ben uygularım.' : 'Önce bir proje açın (soldaki listeden ya da “Projeyi üret”).');
  hist.forEach(m => add(m.role === 'user' ? 'u' : 'a', m.role === 'user' ? esc(m.content).replace(/\n/g, '<br>') : md(m.content)));
}
function load() {
  const id = pid();
  try { hist = JSON.parse(store.get(HKEY(id)) || '[]'); } catch { hist = []; }
  naming();
  render();
}
function naming() {                    // proje adı sayfa yüklenince gelir: birkaç kez dene
  const set = () => { const t = $('#hname')?.textContent?.trim(); $('#chatproj').textContent = pid() ? (t || pid()) : 'proje açık değil'; return !!t; };
  let n = 0; const tick = setInterval(() => { if (set() || ++n > 20) clearInterval(tick); }, 500); set();
}
const save = (id = pid()) => store.set(HKEY(id), JSON.stringify(hist.slice(-MAXH)));

async function send(text) {
  const id = pid();
  if (busy || !text.trim() || !id) return;
  if (!$('#chatok').checked) { add('e', 'Önce onay kutusunu işaretleyin: mesajlar Claude’a gönderilir.'); return; }
  busy = true; $('#chatsend').disabled = true;
  const prior = hist.slice(-20).map(({role, content}) => ({role, content}));
  hist.push({role: 'user', content: text}); add('u', esc(text).replace(/\n/g, '<br>'));
  const wait = add('a', '<span class="typing"><i></i><i></i><i></i></span>');
  try {
    const r = await fetch(`/api/projects/${encodeURIComponent(id)}/chat`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, history: prior, consent: true})});
    const j = await r.json().catch(() => ({}));
    wait.remove();
    if (!r.ok) { add('e', esc(j.detail || r.statusText)); hist.pop(); save(); return; }
    hist.push({role: 'assistant', content: j.reply}); save();
    const extra = document.createElement('div');
    for (const a of (j.actions || []).filter(x => !x.ok)) extra.insertAdjacentHTML('beforeend', `<span class="act" title="${esc(a.error)}">⚠ ${esc(a.tool)}</span>`);
    add('a', md(j.reply), extra);
    if (j.new_project) {                          // sohbet yeni projede sürsün: geçmişi taşı, projeyi aç
      save(j.new_project);
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

function wire() {
  const panel = $('#chatpanel'), fab = $('#chatfab'), inp = $('#chatin');
  const open = on => { panel.classList.toggle('on', on); fab.classList.toggle('on', on); store.set('archai.chat.open', on ? '1' : null); if (on) inp.focus(); };
  fab.onclick = () => open(true); $('#chatclose').onclick = () => open(false);
  $('#chatclear').onclick = () => { hist = []; save(); render(); };
  const ok = $('#chatok'); ok.checked = store.get('archai.chat.consent') === '1';
  ok.onchange = () => store.set('archai.chat.consent', ok.checked ? '1' : null);
  $('#chatform').onsubmit = e => { e.preventDefault(); const t = inp.value; inp.value = ''; inp.style.height = ''; send(t); };
  inp.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#chatform').requestSubmit(); } };
  inp.oninput = () => { inp.style.height = 'auto'; inp.style.height = Math.min(120, inp.scrollHeight) + 'px'; };
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
