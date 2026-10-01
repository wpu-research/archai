// Tasarım ajanı sekmesi: foto + metin → 3–5 alternatif → "Bunu seç" ile iç mekâna uygula.
// Sunucu: webapp/design_routes.py. Kullanıcı ve ajan kaynaklı her metin esc() ile kaçışlanır.
export function createDesigns(ctx) {
  const {$, $$, api, esc, tl, getProject, applied} = ctx;
  const MAX_PHOTOS = 5, MAX_BYTES = 12 * 1024 * 1024;
  const S = {pid: null, files: [], brief: '', n: 4, provider: 'kural', consent: false, furnish: true,
             sets: [], providers: {kural: true, claude: false, http: false}, notice: '', cur: null,
             busy: false, err: '', msg: '', urls: new Map()};
  const color = c => /^#[0-9a-fA-F]{6}$/.test(String(c)) ? c : '#888888';
  const money = v => v == null ? '—' : tl(v);
  const urlOf = f => { if (!S.urls.has(f)) S.urls.set(f, URL.createObjectURL(f)); return S.urls.get(f); };

  function card(set, v) {
    const sel = set.selected === v.id, d = v.cost?.delta;
    return `<div class="card ${sel ? 'sel' : ''}" data-v="${esc(v.id)}">
      <img src="${esc(v.preview)}" alt="${esc(v.title)} önizleme" loading="lazy">
      <div class="b"><h4>${esc(v.title)}</h4>
        <div class="pal" aria-label="Renk paleti">${(v.palette || []).map(c => `<i style="background:${color(c)}" title="${esc(c)}"></i>`).join('')}</div>
        <p>${esc(v.summary)}</p>
        <div class="facts"><span>ZEMİN <b>${esc(v.floor_name)}</b></span><span>ISLAK HACİM <b>${esc(v.wet_name)}</b></span>
          <span>DUVAR <b>${esc(v.paint_name)}</b></span><span>MOBİLYA <b>${esc(v.style_name)}</b>${v.decor ? ' · <b>dekor</b>' : ''}</span></div>
        <div class="cost ${d > 0 ? 'up' : d < 0 ? 'down' : ''}">${esc(money(v.cost?.total))}${d ? ` <small>(${d > 0 ? '+' : ''}${esc(money(d))})</small>` : ''}</div>
        <button class="pick" data-pick="${esc(v.id)}" ${S.busy ? 'disabled' : ''}>${sel ? '✓ UYGULANDI' : 'BUNU SEÇ'}</button></div></div>`;
  }

  function draw(out) {
    const set = S.sets.find(s => s.id === S.cur) || S.sets[0];
    const pv = S.providers;
    out.innerHTML = `<div class="da">
      <p class="sec-t">TASARIM AJANI</p>
      <p class="note" style="margin-top:0">Mekân/ilham fotoğrafları ve isteklerinizi yazın; ajan 3–5 tasarım alternatifi üretir. Seçtiğiniz alternatif zemin, duvar boyası, mobilya stili ve dekor olarak projeye uygulanır; maliyet güncellenir.</p>
      <label for="da-files">Fotoğraflar · en çok ${MAX_PHOTOS} (png / jpg / webp)</label>
      <input id="da-files" type="file" accept="image/png,image/jpeg,image/webp" multiple ${S.busy ? 'disabled' : ''}>
      <div class="thumbs">${S.files.map((f, i) => `<figure><img src="${esc(urlOf(f))}" alt="${esc(f.name)}"><button data-rm="${i}" aria-label="Fotoğrafı kaldır">✕</button></figure>`).join('')}</div>
      <label for="da-brief">İstekleriniz · stil, renk, bütçe, kullanım, eşya</label>
      <textarea id="da-brief" maxlength="4000" placeholder="Örn: Sıcak ama modern bir salon. Açık gri duvar, meşe zemin, bütçe dostu. Kitaplık ve çalışma köşesi lazım.">${esc(S.brief)}</textarea>
      <div class="row"><div><label for="da-n">Alternatif sayısı</label><select id="da-n">${[3, 4, 5].map(k => `<option ${k === S.n ? 'selected' : ''}>${k}</option>`).join('')}</select></div>
        <div><label for="da-prov">Sağlayıcı</label><select id="da-prov">
          <option value="kural" ${S.provider === 'kural' ? 'selected' : ''}>Kural tabanlı (çevrimdışı)</option>
          <option value="claude" ${S.provider === 'claude' ? 'selected' : ''} ${pv.claude ? '' : 'disabled'}>Claude ${pv.claude ? '' : '(kimlik yok)'}</option>
          <option value="http" ${S.provider === 'http' ? 'selected' : ''} ${pv.http ? '' : 'disabled'}>Dış ajan ${pv.http ? '' : '(tanımlı değil)'}</option></select></div></div>
      ${S.provider === 'claude' ? `<label class="check"><input id="da-consent" type="checkbox" ${S.consent ? 'checked' : ''}> Fotoğraflarım ve metnim Anthropic'e gönderilsin (onaylıyorum)</label>` : ''}
      ${S.provider === 'http' ? '<p class="note">Fotoğraflar ve metin sunucuda tanımlı dış ajana (ARCHAI_DESIGN_AGENT_URL) gönderilir.</p>' : ''}
      <label class="check"><input id="da-furnish" type="checkbox" ${S.furnish ? 'checked' : ''}> Seçince mobilya yoksa örnek döşe (stil mobilyaya uygulanır)</label>
      <button class="go" id="da-go" ${S.busy ? 'disabled' : ''}>${S.busy ? 'ÇALIŞIYOR…' : '✦ ALTERNATİF ÜRET'}</button>
      ${S.err ? `<div class="err" role="alert">⚠ ${esc(S.err)}</div>` : ''}${S.msg ? `<div class="ok" role="status">${esc(S.msg)}</div>` : ''}
      ${set ? `<p class="sec-t" style="margin-top:24px">ALTERNATİFLER · ${esc(String(set.provider).toUpperCase())} · ${esc(set.variants.length)} ADET</p>
        ${(set.warnings || []).map(w => `<div class="warnbox">⚠ ${esc(w)}</div>`).join('')}
        ${set.brief ? `<p class="note mono" style="margin-top:0">“${esc(set.brief.slice(0, 200))}${set.brief.length > 200 ? '…' : ''}”</p>` : ''}
        <div class="cards">${set.variants.map(v => card(set, v)).join('')}</div>
        ${S.sets.length > 1 ? `<p class="sec-t" style="margin-top:22px">ÖNCEKİ SETLER</p><div class="prev">${S.sets.map(s =>
          `<button class="vbtn ${s.id === set.id ? 'on' : ''}" data-set="${esc(s.id)}">${esc(String(s.created).slice(5, 16).replace('T', ' '))} · ${esc(s.variants.length)}</button>`).join('')}</div>` : ''}
        <p class="note mono">${esc(S.notice)}</p>` : '<div class="empty">HENÜZ ALTERNATİF YOK</div>'}</div>`;
    wire(out);
  }

  function wire(out) {
    const redraw = () => draw(out);
    $('#da-files').onchange = e => {
      const add = [...e.target.files].filter(f => {
        if (!/^image\/(png|jpeg|webp)$/.test(f.type)) { S.err = `${f.name}: yalnız png/jpg/webp`; return false; }
        if (f.size > MAX_BYTES) { S.err = `${f.name}: en fazla ${MAX_BYTES / 1048576} MB`; return false; }
        return true;
      });
      S.files = [...S.files, ...add].slice(0, MAX_PHOTOS); if (add.length) S.err = ''; S.brief = $('#da-brief').value; redraw();
    };
    $$('[data-rm]').forEach(b => b.onclick = () => { const [f] = S.files.splice(+b.dataset.rm, 1); if (f) { URL.revokeObjectURL(S.urls.get(f)); S.urls.delete(f); } S.brief = $('#da-brief').value; redraw(); });
    $('#da-brief').oninput = e => { S.brief = e.target.value; };
    $('#da-n').onchange = e => { S.n = +e.target.value; };
    $('#da-prov').onchange = e => { S.provider = e.target.value; S.brief = $('#da-brief').value; redraw(); };
    $('#da-furnish').onchange = e => { S.furnish = e.target.checked; };
    if ($('#da-consent')) $('#da-consent').onchange = e => { S.consent = e.target.checked; };
    $('#da-go').onclick = () => generate(out);
    $$('[data-pick]').forEach(b => b.onclick = () => pick(out, b.dataset.pick));
    $$('[data-set]').forEach(b => b.onclick = () => { S.cur = b.dataset.set; S.msg = ''; redraw(); });
  }

  async function generate(out) {
    S.brief = $('#da-brief').value; S.err = ''; S.msg = '';
    if (!S.brief.trim() && !S.files.length) { S.err = 'En az bir fotoğraf veya metin girin'; draw(out); return; }
    if (S.provider === 'claude' && !S.consent) { S.err = 'Claude için gönderim onayını işaretleyin'; draw(out); return; }
    const fd = new FormData();
    S.files.forEach(f => fd.append('photos', f, f.name));
    fd.append('brief', S.brief); fd.append('n', String(S.n)); fd.append('provider', S.provider);
    fd.append('claude_consent', S.provider === 'claude' && S.consent ? 'true' : 'false');
    S.busy = true; draw(out);
    try {
      const set = await api(`/api/projects/${S.pid}/designs`, {method: 'POST', body: fd});
      S.sets = [set, ...S.sets.filter(s => s.id !== set.id)]; S.cur = set.id;
      S.msg = `${set.variants.length} alternatif hazır`;
    } catch (e) { S.err = e.message || String(e); }
    S.busy = false; if (out.isConnected) draw(out);
  }

  async function pick(out, vid) {
    const set = S.sets.find(s => s.id === S.cur) || S.sets[0]; if (!set) return;
    S.err = ''; S.msg = ''; S.busy = true; draw(out);
    try {
      const sel = () => api(`/api/projects/${S.pid}/designs/${set.id}/select`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({variant: vid})});
      await applied(await sel(), sel, S.furnish);
      set.selected = vid;
      S.msg = `“${set.variants.find(v => v.id === vid)?.title}” uygulandı · maliyet güncellendi`;
    } catch (e) { S.err = e.message || String(e); }
    S.busy = false; if (out.isConnected) draw(out);
  }

  async function mount(out) {
    const P = getProject();
    if (S.pid !== P.id) Object.assign(S, {pid: P.id, sets: [], cur: null, err: '', msg: '', loaded: false});
    draw(out);
    if (!S.loaded) {
      S.loaded = true;
      try {
        const r = await api(`/api/projects/${P.id}/designs`);
        S.sets = r.sets; S.providers = r.providers; S.notice = r.notice_short || r.notice || ''; S.cur = S.sets[0]?.id ?? null;
      } catch (e) { S.err = e.message || String(e); }
      if (out.isConnected && S.pid === P.id) draw(out);
    }
  }
  return {mount};
}
