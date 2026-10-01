/* Müşteri videosu: seçenek paneli → ilerleme çubuğu → oynatıcı + indir.
   index.html'e yalnız #vidbtn düğmesi ve bu dosyanın <script> satırı eklenir; panel burada kurulur. */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const STAGES = {kuyruk: 'Sırada', plan: 'Proje okunuyor', hazirlik: 'İç mekân hazırlanıyor', cekim: 'Sahneler çekiliyor', cycles: 'Fotogerçekçi render (Cycles)',
  muzik: 'Müzik', montaj: 'Video kodlanıyor', bitis: 'Tamamlanıyor'};
const css = `
#vidpanel{position:fixed;inset:0;z-index:40;display:none;align-items:center;justify-content:center;background:rgba(2,5,9,.72);backdrop-filter:blur(6px)}
#vidpanel.on{display:flex}
#vidpanel .vbox{width:min(760px,94vw);max-height:92vh;overflow:auto;padding:22px 24px;background:var(--glass,rgba(8,16,26,.94));border:1px solid var(--line-hi,#1c4a5a);border-radius:14px;box-shadow:0 30px 90px rgba(0,0,0,.6)}
#vidpanel h2{margin:0 0 4px;font:600 15px var(--mono,monospace);letter-spacing:.16em;color:var(--cy,#3ee8ff)}
#vidpanel p.sub{margin:0 0 16px;color:var(--mute,#8aa);font-size:13px}
#vidpanel .vgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px 18px}
#vidpanel fieldset{border:1px solid var(--line,#183040);border-radius:10px;padding:10px 12px;margin:0}
#vidpanel legend{font:500 10.5px var(--mono,monospace);letter-spacing:.14em;color:var(--cy,#3ee8ff);padding:0 6px}
#vidpanel label{display:flex;align-items:center;gap:8px;padding:4px 0;cursor:pointer;font-size:13.5px}
#vidpanel label.dis{opacity:.45;cursor:not-allowed}
#vidpanel input[type=radio],#vidpanel input[type=checkbox]{accent-color:var(--cy,#3ee8ff);width:16px;height:16px}
#vidpanel .vact{display:flex;gap:10px;margin-top:16px;align-items:center;flex-wrap:wrap}
#vidpanel .vbar{height:10px;border-radius:6px;background:rgba(62,232,255,.12);overflow:hidden;margin:10px 0 6px}
#vidpanel .vbar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--cy,#3ee8ff),var(--blue,#3d7bff));transition:width .4s}
#vidpanel .vmsg{font:500 12px var(--mono,monospace);color:var(--mute,#8aa);min-height:18px}
#vidpanel .vwarn{margin:10px 0 0;padding:8px 10px;border-radius:8px;background:rgba(255,181,71,.1);border:1px solid rgba(255,181,71,.35);color:#ffcf8a;font-size:12.5px}
#vidpanel .verr{margin:10px 0 0;padding:8px 10px;border-radius:8px;background:rgba(255,93,108,.1);border:1px solid rgba(255,93,108,.4);color:#ff9aa4;font-size:13px}
#vidpanel video{width:100%;border-radius:10px;background:#000;margin-top:6px;aspect-ratio:16/9}
#vidpanel .vold{margin-top:14px;font-size:12.5px;color:var(--mute,#8aa)}
#vidpanel .vold a{color:var(--cy,#3ee8ff);margin-right:12px}
@media (max-width:640px){#vidpanel .vgrid{grid-template-columns:1fr}}`;

let cap = null, job = null, timer = null;
const pid = () => decodeURIComponent((location.hash || '').slice(1));
const store = {get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* özel pencere */ } }};

async function j(url, opt) {
  const r = await fetch(url, opt);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.detail || r.statusText), {status: r.status, body});
  return body;
}

function build() {
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
  const el = document.createElement('div');
  el.id = 'vidpanel'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'vidtitle');
  el.innerHTML = '<div class="vbox"><h2 id="vidtitle">MÜŞTERİ VİDEOSU</h2><p class="sub" id="vidsub"></p><div id="vidbody"></div></div>';
  document.body.appendChild(el);
  el.addEventListener('click', e => { if (e.target === el) close(); });
  addEventListener('keydown', e => { if (e.key === 'Escape' && el.classList.contains('on')) close(); });
}

function close() { $('#vidpanel').classList.remove('on'); clearTimeout(timer); timer = null; }

function optionsView() {
  const d = cap.defaults, noBl = !cap.blender;
  $('#vidsub').textContent = 'Bu projeden tek tıkla, müşteriye sunulacak tanıtım videosu (mp4) üretilir.';
  $('#vidbody').innerHTML = `
    <div class="vgrid">
      <fieldset><legend>SÜRE</legend>
        <label><input type="radio" name="vprof" value="short" ${d.profile === 'short' ? 'checked' : ''}> Kısa · ≈ 30 sn</label>
        <label><input type="radio" name="vprof" value="standard" ${d.profile === 'standard' ? 'checked' : ''}> Standart · 60–90 sn</label></fieldset>
      <fieldset><legend>ÇÖZÜNÜRLÜK</legend>
        <label><input type="radio" name="vres" value="720p" ${d.resolution === '720p' ? 'checked' : ''}> 720p (hızlı, küçük dosya)</label>
        <label><input type="radio" name="vres" value="1080p" ${d.resolution === '1080p' ? 'checked' : ''}> 1080p (Full HD)</label></fieldset>
      <fieldset><legend>FOTOGERÇEKÇİ (CYCLES)</legend>
        <label class="${noBl ? 'dis' : ''}"><input type="checkbox" id="vcy" ${noBl ? 'disabled' : ''}> Cycles görüntüleri ekle</label>
        <label class="${noBl ? 'dis' : ''}" id="vcyq" style="display:none"><select id="vcyqs"><option value="fast">Hızlı (1920 px)</option><option value="good">İyi (2560 px, daha yavaş)</option></select></label>
        <div class="vmsg" id="vcynote">${noBl ? 'Blender bulunamadı.' : 'Her görüntü dakikalar sürebilir; varsayılan kapalı.'}</div></fieldset>
      <fieldset><legend>İÇERİK</legend>
        <label><input type="checkbox" id="vmus" ${d.music ? 'checked' : ''}> Müzik</label>
        <label><input type="checkbox" id="vsub" ${d.subtitles ? 'checked' : ''}> Türkçe altyazı</label>
        <label><input type="checkbox" id="vnight" ${d.night ? 'checked' : ''}> Gün-gece sahnesi</label></fieldset>
    </div>
    <div class="vact"><button class="primary" id="vgo" style="width:auto;margin:0;padding:12px 22px">▶ VİDEOYU ÜRET</button>
      <button class="ghost" id="vcl">KAPAT</button><span class="vmsg" id="vtime"></span></div>
    <div id="vold"></div>`;
  $('#vcy').onchange = e => { $('#vcyq').style.display = e.target.checked ? 'flex' : 'none'; };
  $('#vgo').onclick = start;
  $('#vcl').onclick = close;
  fillOld();
}

async function fillOld() {
  try {
    const l = await j(`/api/projects/${encodeURIComponent(pid())}/video`);
    if (!l.length) return;
    $('#vold').innerHTML = '<div class="vold">Önceki videolar: ' + l.map((x, i) =>
      `<a href="#" data-v="${esc(x.id)}">${i + 1}. video${x.result?.duration ? ' · ' + Math.round(x.result.duration) + ' sn' : ''}</a>`).join('') + '</div>';
    document.querySelectorAll('#vold [data-v]').forEach(a => a.onclick = ev => { ev.preventDefault(); job = l.find(x => x.id === a.dataset.v); doneView(job); });
  } catch { /* liste yoksa sessiz */ }
}

function getOpts() {
  const v = n => document.querySelector(`input[name=${n}]:checked`).value;
  const cy = $('#vcy').checked;
  return {profile: v('vprof'), resolution: v('vres'), cycles: cy, cycles_quality: cy ? $('#vcyqs').value : 'fast',
    music: $('#vmus').checked, subtitles: $('#vsub').checked, night: $('#vnight').checked};
}

async function start() {
  $('#vgo').disabled = true;
  try {
    job = await j(`/api/projects/${encodeURIComponent(pid())}/video`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(getOpts())});
  } catch (e) {
    if (e.status === 409 && e.body?.job) job = e.body.job;
    else { $('#vgo').disabled = false; $('#vtime').textContent = ''; showErr(e.message); return; }
  }
  store.set('vid:' + pid(), job.id);
  progressView();
}

function showErr(msg) {
  let box = $('#vid-err');
  if (!box) { box = document.createElement('div'); box.id = 'vid-err'; box.className = 'verr'; $('#vidbody').appendChild(box); }
  box.textContent = msg;
}

function progressView() {
  $('#vidsub').textContent = 'Video hazırlanıyor — bu pencereyi kapatsanız da üretim sürer; geri dönünce kaldığı yerden izlersiniz.';
  $('#vidbody').innerHTML = `<div class="vmsg" id="vstage">—</div><div class="vbar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><i id="vfill"></i></div>
    <div class="vmsg" id="vpct">0%</div><div id="vwarns"></div>
    <div class="vact"><button class="ghost" id="vcancel">İPTAL ET</button><button class="ghost" id="vhide">ARKA PLANA AL</button></div>`;
  $('#vcancel').onclick = async () => { try { await j(`/api/video-jobs/${job.id}/cancel`, {method: 'POST'}); } catch (e) { showErr(e.message); } };
  $('#vhide').onclick = close;
  poll();
}

async function poll() {
  clearTimeout(timer);
  try { job = await j(`/api/video-jobs/${encodeURIComponent(job.id)}`); } catch (e) { timer = setTimeout(poll, 3000); return; }
  if (!$('#vfill')) return;
  const pct = Math.round(job.percent || 0);
  $('#vfill').style.width = pct + '%'; $('#vfill').parentElement.setAttribute('aria-valuenow', pct);
  $('#vstage').textContent = (STAGES[job.stage] || job.stage || '') + (job.message && job.message !== STAGES[job.stage] ? ' · ' + job.message : '');
  $('#vpct').textContent = job.status === 'queued' ? `Sırada (önünde ${job.queued_ahead ?? 0} iş)` : `%${pct}`;
  $('#vwarns').innerHTML = (job.warnings || []).map(w => `<div class="vwarn">${esc(w)}</div>`).join('');
  if (job.status === 'done') { store.set('vid:' + pid(), null); doneView(job); return; }
  if (job.status === 'error' || job.status === 'cancelled') {
    store.set('vid:' + pid(), null);
    $('#vidbody').innerHTML = `<div class="${job.status === 'error' ? 'verr' : 'vwarn'}">${esc(job.status === 'error' ? 'Video üretilemedi: ' + (job.error || 'bilinmeyen hata') : 'Üretim iptal edildi.')}</div>
      <div class="vact"><button class="primary" id="vagain" style="width:auto;margin:0;padding:10px 18px">YENİDEN DENE</button><button class="ghost" id="vcl">KAPAT</button></div>`;
    $('#vagain').onclick = optionsView; $('#vcl').onclick = close;
    return;
  }
  timer = setTimeout(poll, 1500);
}

function doneView(jb) {
  const r = jb.result || {};
  $('#vidsub').textContent = [r.duration ? Math.round(r.duration) + ' sn' : '', r.size ? r.size[1] + 'p' : '', r.bytes ? (r.bytes / 1e6).toFixed(1) + ' MB' : ''].filter(Boolean).join(' · ') || 'Hazır';
  $('#vidbody').innerHTML = `<video controls preload="metadata" poster="${esc(jb.cover)}" src="${esc(jb.video)}"></video>
    <div class="vact"><a class="ghost" href="${esc(jb.download)}" download>↓ MP4 İNDİR</a><a class="ghost" href="${esc(jb.srt)}" download>↓ ALTYAZI (.srt)</a>
      <button class="ghost" id="vnew">YENİ VİDEO</button><button class="ghost" id="vcl">KAPAT</button></div>
    ${(jb.warnings || []).map(w => `<div class="vwarn">${esc(w)}</div>`).join('')}`;
  $('#vnew').onclick = optionsView; $('#vcl').onclick = close;
}

async function open() {
  if (!pid()) return;
  if (!$('#vidpanel')) build();
  $('#vidpanel').classList.add('on');
  try { cap = await j('/api/video-capabilities'); } catch (e) { $('#vidbody').textContent = e.message; return; }
  if (!cap.ok) {
    $('#vidsub').textContent = '';
    $('#vidbody').innerHTML = `<div class="verr">Video için eksik sistem bileşeni: ${esc(cap.missing.join(', '))}</div><div class="vact"><button class="ghost" id="vcl">KAPAT</button></div>`;
    $('#vcl').onclick = close; return;
  }
  const last = store.get('vid:' + pid());
  if (last) {                                    // yarım kalan iş varsa izlemeye devam
    try { job = await j('/api/video-jobs/' + encodeURIComponent(last)); if (job.status === 'queued' || job.status === 'running') { progressView(); return; } } catch { /* yok */ }
    store.set('vid:' + pid(), null);
  }
  optionsView();
}

const btn = $('#vidbtn');
if (btn) {
  const sync = () => { btn.style.display = pid() ? '' : 'none'; };
  sync(); addEventListener('hashchange', sync); setInterval(sync, 1500);
  btn.onclick = open;
}
