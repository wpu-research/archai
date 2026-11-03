// Müteahhit katmanı sekmeleri: 08 POZ · KATALOG, 09 ONAY ve arazi formundaki imar belgesi okuma. Sunucu: webapp/muteahhit_routes.py.
// Kullanıcı, dosya ve liste kaynaklı her metin esc() ile kaçışlanır.
export function createContractor(ctx) {
  const {$, $$, api, esc, tl, n2, getProject, setProject} = ctx;
  const ST = {eslesti: ['EŞLEŞTİ', 'ok'], birim_uyusmaz: ['BİRİM UYUŞMAZ', 'bad'], listede_yok: ['LİSTEDE YOK', 'bad'],
              poz_yok: ['POZ YOK', ''], liste_yok: ['LİSTE YÜKLENMEDİ', '']};
  const S = {poz: null, err: '', msg: '', busy: false, onlyOpen: false};

  async function loadPoz(out) {
    const P = getProject();
    try { S.poz = await api(`/api/projects/${P.id}/poz`); S.err = ''; } catch (e) { S.err = e.message || String(e); }
    drawPoz(out);
  }

  function badge(d) { const [t, c] = ST[d] || [d, '']; return `<span class="flag ${c}">${esc(t)}</span>`; }

  function drawPoz(out) {
    const D = S.poz;
    if (!D) { out.innerHTML = `<p class="note">${S.err ? esc(S.err) : 'yükleniyor…'}</p>`; return; }
    const L = D.list, sm = D.summary || {};
    const rows = D.rows.filter(r => !S.onlyOpen || r.durum !== 'eslesti');
    out.innerHTML = `<div class="mk">
      <p class="sec-t">RESMÎ POZ LİSTESİ</p>
      <p class="note" style="margin-top:0">ÇŞB birim fiyatları ArchAI ile dağıtılmaz (Bakanlık listeleri izinsiz çoğaltmaya kapalı, lisanslı dağıtım AMP'de).
        Kendi lisanslı listenizi AMP / Oska / birimfiyat.net'ten <b>Excel veya CSV</b> olarak dışa aktarıp yükleyin; liste yalnız bu makinede tutulur.</p>
      <div class="mk-row">${L ? `<span class="mono">${esc(L.institution || '')} ${esc(L.year || '')} · <b>${esc(n2(L.count))}</b> poz · ${esc(L.source)} · ${esc(String(L.imported_at || '').replace('T', ' '))}</span>
          <button class="ghost" id="pz-del">LİSTEYİ SİL</button>` : '<span class="mono" style="color:var(--warn)">LİSTE YÜKLENMEDİ — poz numaraları yine de keşif özetine yazılır, fiyatlar katalogdan gelir</span>'}</div>
      <div class="mk-row"><input id="pz-file" type="file" accept=".xlsx,.xlsm,.csv,.txt"><input id="pz-year" type="number" placeholder="Yıl" style="width:90px" value="${new Date().getFullYear()}">
        <button class="ghost" id="pz-up" ${S.busy ? 'disabled' : ''}>↑ LİSTE YÜKLE</button></div>
      <p class="sec-t">KALEM ↔ POZ EŞLEMESİ</p>
      <div class="mk-row mono">${Object.entries(sm).map(([k, v]) => `${badge(k)} ${esc(v)}`).join(' &nbsp; ')}</div>
      <div class="mk-row"><label class="check" style="margin:0"><input type="checkbox" id="pz-open" ${S.onlyOpen ? 'checked' : ''}> yalnız eşleşmeyenler</label>
        <button class="ghost" id="pz-apply" ${!L || S.busy ? 'disabled' : ''} title="Birimi uyuşan eşleşmelerin liste fiyatını birim fiyat olarak yazar">✓ EŞLEŞEN FİYATLARI UYGULA</button>
        ${D.files.kesif_xlsx ? `<a class="ghost" href="${esc(D.files.kesif_xlsx)}">↓ KEŞİF ÖZETİ .XLSX</a><a class="ghost" href="${esc(D.files.kesif_csv)}">↓ .CSV (AMP/OSKA)</a>` : ''}</div>
      ${S.err ? `<p class="err">${esc(S.err)}</p>` : ''}${S.msg ? `<p class="ok">${esc(S.msg)}</p>` : ''}
      <div class="scroll"><table><tr><th>Kod</th><th>İmalat</th><th>Birim</th><th>Poz No</th><th>Durum</th><th>Liste</th><th class="n">Liste fiyatı</th></tr>
      ${rows.map(r => `<tr style="${r.enabled ? '' : 'opacity:.45'}"><td class="code">${esc(r.code)}</td><td>${esc(r.name)}</td><td class="mono">${esc(r.unit)}</td>
        <td><input class="num pz-in" data-pz="${esc(r.code)}" value="${esc(r.poz || '')}" placeholder="—" style="width:120px">
          <div class="mono" style="font-size:10px;color:var(--mute)">${r.kaynak === 'proje' ? 'PROJE' : r.kaynak === 'öneri' ? 'ÖNERİ · DOĞRULANMADI' : ''}</div></td>
        <td>${badge(r.durum)}${r.applied ? ' <span class="flag ok">FİYAT UYGULANDI</span>' : ''}</td>
        <td style="font-size:11.5px">${r.liste_tanim ? esc(r.liste_tanim) + ` <span class="mono">(${esc(r.liste_birim)})</span>` :
          (r.adaylar || []).map(a => `<button class="ghost pz-cand" data-code="${esc(r.code)}" data-poz="${esc(a.poz)}" title="${esc(a.tanim)}">${esc(a.poz)} · ${esc(a.tanim.slice(0, 48))}… (${esc(a.birim)}, ${esc(tl(a.fiyat))})</button>`).join('<br>')}</td>
        <td class="n">${r.liste_fiyat != null ? esc(tl(r.liste_fiyat)) : ''}</td></tr>`).join('')}</table></div>
      <p class="note">Önerilen poz numaraları resmî listeyle doğrulanmadı; keşif özetinde "öneri — doğrulanmadı" diye işaretlenir. Poz numarasını yazdığınız kalem "proje" kaynağıyla kayda geçer.
        Keşif özeti CSV'si AMP/Oska'nın Excel'den aktarım ekranına yapıştırılabilir; programların kendi dosya biçimleri üretilmez.</p></div>`;
    $('#pz-open').onchange = e => { S.onlyOpen = e.target.checked; drawPoz(out); };
    $('#pz-up').onclick = async () => {
      const f = $('#pz-file').files[0]; if (!f) { S.err = 'önce bir .xlsx/.csv seçin'; drawPoz(out); return; }
      const fd = new FormData(); fd.append('file', f); if ($('#pz-year').value) fd.append('year', $('#pz-year').value);
      await act(out, async () => { const r = await api('/api/poz/list', {method: 'POST', body: fd}); S.msg = `${n2(r.list.count)} poz içe aktarıldı (${r.list.skipped} satır fiyatsız atlandı)`; });
    };
    if ($('#pz-del')) $('#pz-del').onclick = () => act(out, async () => { await api('/api/poz/list', {method: 'DELETE'}); S.msg = 'liste silindi'; });
    $('#pz-apply').onclick = () => save(out, {}, true);
    $$('.pz-in').forEach(i => i.onchange = () => save(out, {[i.dataset.pz]: i.value.trim() || null}, false));
    $$('.pz-cand').forEach(b => b.onclick = () => save(out, {[b.dataset.code]: b.dataset.poz}, false));
  }

  async function act(out, fn) {
    S.busy = true; S.err = S.msg = '';
    try { await fn(); } catch (e) { S.err = e.message || String(e); }
    S.busy = false; await loadPoz(out);
  }

  function save(out, map, apply) {
    return act(out, async () => {
      const r = await api(`/api/projects/${getProject().id}/poz`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({poz: map, apply_prices: apply})});
      setProject(r.project);
      S.msg = apply ? `${r.applied} kalemin birim fiyatı listeden alındı; belgeler yeniden üretildi` : 'poz kaydedildi; keşif özeti yenilendi';
    });
  }

  // ---- 2. adım: imar durum belgesinden arazi formunu doldur
  const LAB = {taks: 'TAKS', kaks: 'KAKS / emsal', front: 'ön çekme', side: 'yan çekme', rear: 'arka çekme',
               max_floors: 'kat adedi', max_height: 'yençok (m)', parcel_area: 'parsel alanı (m²)', nizam: 'nizam',
               ada: 'ada', parsel: 'parsel', pafta: 'pafta'};
  const FORM = {taks: '#taks', kaks: '#kaks', front: '#fr', side: '#sd', rear: '#rr', max_floors: '#mf', max_height: '#mh'};
  const SITE = {il: '#s_il', ilce: '#s_ilce', mahalle: '#s_mah', pafta: '#s_pafta', ada: '#s_ada', parsel: '#s_parsel'};
  function bindImar() {
    const go = $('#im-go'); if (!go) return;
    go.onclick = async () => {
      const f = $('#im-file').files[0], out = $('#im-out');
      if (!f) { out.innerHTML = '<p class="err">önce belgeyi seçin</p>'; return; }
      const fd = new FormData(); fd.append('file', f); fd.append('consent', $('#im-ok').checked ? 'true' : 'false');
      go.disabled = true; out.innerHTML = '<p class="note mono">okunuyor…</p>';
      try {
        const r = await api('/api/imar/read', {method: 'POST', body: fd});
        for (const [k, sel] of Object.entries(FORM)) if (r.zoning[k] != null) $(sel).value = r.zoning[k];
        for (const [k, sel] of Object.entries(SITE)) if (r.site?.[k] && $(sel)) $(sel).value = r.site[k];
        const A = r.values?.parcel_area, W = parseFloat($('#pw').value);
        if (A && W > 0) $('#pd').value = Math.round(A / W * 100) / 100;     // alan korunur, cephe kullanıcıda
        const ev = Object.entries(r.evidence || {});
        out.innerHTML = `<p class="note mono" style="margin:8px 0 4px">YÖNTEM: ${esc(String(r.method).toUpperCase())} · ${esc(Object.keys(r.zoning).length)} İMAR ALANI DOLDURULDU</p>
          ${ev.length ? `<table>${ev.map(([k, t]) => `<tr><td class="mono">${esc(LAB[k] || k)}</td><td style="font-size:11px">“${esc(t)}”</td></tr>`).join('')}</table>` : ''}
          ${(r.notes || []).map(n => `<div class="warnbox">ℹ ${esc(n)}</div>`).join('')}
          ${(r.warnings || []).map(w => `<div class="warnbox">⚠ ${esc(w)}</div>`).join('')}
          ${A && W > 0 ? `<p class="note mono">Parsel derinliği alan ÷ cephe = ${esc(n2(A / W))} m olarak ayarlandı; cepheyi kontrol edin.</p>` : ''}`;
      } catch (e) { out.innerHTML = `<p class="err">${esc(e.message || e)}</p>`; }
      go.disabled = false;
    };
  }

  // ---- 4. adım: tedarikçi kataloğu
  const C = {d: null, err: '', msg: '', busy: false};
  async function loadCat(out) {
    try { C.d = await api(`/api/projects/${getProject().id}/catalog`); C.err = ''; } catch (e) { C.err = e.message || String(e); }
    drawCat(out);
  }
  function drawCat(out) {
    const d = C.d;
    if (!d) { out.innerHTML = C.err ? `<p class="err">${esc(C.err)}</p>` : ''; return; }
    out.innerHTML = `<div class="mk"><p class="sec-t" style="margin-top:22px">TEDARİKÇİ KATALOĞU · GERÇEK ÜRÜN FİYATI</p>
      <p class="note" style="margin-top:0">Yapı market / bayi fiyat listesini (CSV/XLSX: Ürün Adı, Birim, Fiyat, Kalem, isteğe bağlı İşçilik, Fire %, Varyant, KDV Dahil) yükleyin.
        Uygulanmış birim fiyat = KDV hariç malzeme × (1 + fire) + işçilik. Biçim örneği: <span class="mono">examples/katalog_ornek.csv</span>.</p>
      <div class="mk-row">${d.catalogs.map(k => `<span class="flag">${esc(k.supplier)} · ${esc(k.count)} ürün</span><button class="ghost" data-catdel="${esc(k.id)}">✕</button>`).join(' ') || '<span class="mono" style="color:var(--mute)">KATALOG YOK</span>'}</div>
      <div class="mk-row"><input id="ct-file" type="file" accept=".xlsx,.xlsm,.csv,.txt"><input id="ct-sup" placeholder="Tedarikçi adı (dosyada yoksa)" maxlength="60" style="width:200px">
        <button class="ghost" id="ct-up" ${C.busy ? 'disabled' : ''}>↑ KATALOG YÜKLE</button></div>
      ${C.err ? `<p class="err">${esc(C.err)}</p>` : ''}${C.msg ? `<p class="ok">${esc(C.msg)}</p>` : ''}
      ${d.rows.length ? `<div class="scroll"><table><tr><th>Kalem</th><th class="n">Miktar</th><th class="n">Güncel birim</th><th>Ürün seç</th></tr>
      ${d.rows.map(r => `<tr><td><span class="code">${esc(r.code)}</span> ${esc(r.name)}</td><td class="n">${esc(n2(r.quantity))} ${esc(r.unit)}</td><td class="n">${esc(tl(r.unit_price))}</td>
        <td><select data-cat="${esc(r.code)}"><option value="">— katalog dışı (katalog / varyant fiyatı) —</option>
          ${r.products.map(p => `<option value="${esc(p.catalog)}|${esc(p.id)}" ${r.selected && r.selected.sku === p.sku && r.selected.supplier === p.supplier ? 'selected' : ''}>${esc(p.name)} · ${esc(p.supplier)} · ${esc(tl(p.unit_price))}/${esc(r.unit)}${p.labor == null ? ' · yalnız malzeme!' : ''}</option>`).join('')}</select>
          ${r.selected?.material_only ? '<div class="mono" style="color:var(--warn);font-size:10px">İŞÇİLİK YOK: birim fiyat yalnız malzeme</div>' : ''}</td></tr>`).join('')}</table></div>` :
        '<p class="note">Bu projenin kalemleri için katalogda ürün yok' + (d.catalogs.length ? ' (ürünler mevcut varyanta göre süzülür).' : '.') + '</p>'}</div>`;
    $('#ct-up').onclick = async () => {
      const f = $('#ct-file').files[0]; if (!f) { C.err = 'önce bir katalog dosyası seçin'; drawCat(out); return; }
      const fd = new FormData(); fd.append('file', f); fd.append('supplier', $('#ct-sup').value.trim());
      await catAct(out, async () => { const r = await api('/api/catalogs', {method: 'POST', body: fd});
        C.msg = `${r.catalog.supplier}: ${r.catalog.count} ürün yüklendi` + (r.catalog.skipped ? `, ${r.catalog.skipped} satır atlandı (${r.catalog.warnings.slice(0, 3).join('; ')})` : ''); });
    };
    $$('[data-catdel]').forEach(b => b.onclick = () => catAct(out, async () => { await api('/api/catalogs/' + encodeURIComponent(b.dataset.catdel), {method: 'DELETE'}); C.msg = 'katalog silindi'; }));
    $$('[data-cat]').forEach(sel => sel.onchange = () => catAct(out, async () => {
      const [catalog, product] = sel.value.split('|');
      const r = await api(`/api/projects/${getProject().id}/catalog`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({select: {[sel.dataset.cat]: sel.value ? {catalog, product} : null}})});
      setProject(r.project); C.msg = 'maliyet ve belgeler güncellendi';
    }));
  }
  async function catAct(out, fn) {
    C.busy = true; C.err = C.msg = '';
    try { await fn(); } catch (e) { C.err = e.message || String(e); }
    C.busy = false; await loadCat(out);
  }

  // ---- 3. adım: mimar / mühendis onayı
  const OST = {taslak: ['TASLAK', 'warn'], onaylandi: ['ONAYLI', 'ok'], gecersiz: ['ONAY GEÇERSİZ', 'bad'],
               degistirilmis: ['BELGE DEĞİŞTİRİLMİŞ', 'bad'], geri_alindi: ['ONAY GERİ ALINDI', 'warn']};
  const O = {d: null, err: '', busy: false, refinalizeBusy: false};
  async function loadOnay(out) {
    try { O.d = await api(`/api/projects/${getProject().id}/onay`); O.err = ''; } catch (e) { O.err = e.message || String(e); }
    drawOnay(out);
  }
  function drawOnay(out) {
    const d = O.d;
    if (!d) { out.innerHTML = `<p class="note">${O.err ? esc(O.err) : 'yükleniyor…'}</p>`; return; }
    const [t, c] = OST[d.status] || [d.status, ''], sg = d.signer || {};
    const opt = (list, v) => list.map(x => `<option ${x === v ? 'selected' : ''}>${esc(x)}</option>`).join('');
    const docs = d.documents || [];
    const showRefinalize = ['gecersiz', 'degistirilmis', 'geri_alindi', 'taslak'].includes(d.status);
    out.innerHTML = `<div class="mk">
      <div class="stamp ${c === 'ok' ? 'ok' : 'bad'}"><span class="flag ${c}">${esc(t)}</span>
        <p class="mono" style="margin:8px 0 0;font-size:12px">${esc(d.text)}</p>
        ${d.date ? `<p class="note" style="margin:6px 0 0">Kayıt: ${esc(sg.name)} · ${esc(sg.title)} · ${esc(sg.chamber)} ${esc(sg.reg_no)} · ${esc(String(d.date).replace('T', ' '))}</p>` : ''}</div>
      ${docs.length ? `<table><tr><th>Belge</th><th>SHA-256</th><th>Bütünlük</th></tr>${docs.map(x => `<tr><td>${d.files[x.key] ? `<a href="${esc(d.files[x.key])}">${esc(x.file)}</a>` : esc(x.file)}</td>
        <td class="mono" style="font-size:10px">${esc(x.sha256.slice(0, 24))}…</td><td>${x.ok ? '<span class="flag ok">SAĞLAM</span>' : '<span class="flag bad">DEĞİŞMİŞ</span>'}</td></tr>`).join('')}</table>` : ''}
      ${d.files.onay_tutanagi_docx ? `<p><a class="ghost" href="${esc(d.files.onay_tutanagi_docx)}">↓ ONAY TUTANAĞI .DOCX</a></p>` : ''}
      ${showRefinalize ? `<div class="mk-row" style="margin-top:10px">
        <button class="ghost" id="on-refinalize" ${O.busy || O.refinalizeBusy ? 'disabled' : ''} style="background:var(--warn);color:var(--bg)">
          ⟳ METRAJ VE BELGELERİ YENİLE
        </button>
        <span class="note" style="font-size:11px;color:var(--mute);margin-left:8px">
          Güncel fiyat kataloğu maliyeti değiştirebilir; çizim/belgeler yeniden üretilir; tekrar onay gerekebilir.
        </span>
      </div>` : ''}
      ${d.status === 'onaylandi' || d.status === 'degistirilmis' ? `<div class="mk-row"><input id="on-why" placeholder="Geri alma nedeni" maxlength="300" style="flex:1"><button class="ghost" id="on-rev" ${O.busy || O.refinalizeBusy ? 'disabled' : ''}>ONAYI GERİ AL</button></div>` : `
      <p class="sec-t">${d.status === 'gecersiz' ? 'YENİDEN ONAYLA' : 'ONAYLA'}</p>
      <div class="grid2"><div><label for="on-name">Ad soyad</label><input id="on-name" maxlength="120" value="${esc(sg.name || '')}"></div>
        <div><label for="on-title">Unvan</label><select id="on-title">${opt(d.titles, sg.title || 'Mimar')}</select></div>
        <div><label for="on-ch">Meslek odası</label><select id="on-ch">${opt(d.chambers, sg.chamber || d.chambers[0])}</select></div>
        <div><label for="on-reg">Oda sicil no</label><input id="on-reg" maxlength="20" value="${esc(sg.reg_no || '')}"></div></div>
      <label for="on-note">Not (isteğe bağlı)</label><input id="on-note" maxlength="1000">
      <label class="check"><input type="checkbox" id="on-st"> ${esc(d.statement)}</label>
      <button class="ghost" id="on-go" style="margin-top:10px" ${O.busy || O.refinalizeBusy ? 'disabled' : ''}>✓ ONAYLA VE BELGELERİ DAMGALA</button>`}
      ${O.err ? `<p class="err">${esc(O.err)}</p>` : ''}
      <p class="note">Onay avan seviyede iç inceleme kaydıdır: e-imza, ruhsat projesi imzası veya yapı denetim onayı değildir. Proje (fiyat, poz, iç mekân…) değişince onay kendiliğinden düşer ve belgeler yeniden TASLAK damgası alır. Onaylanan dosyalar SHA-256 özetiyle izlenir.</p></div>`;
    const run = async (url, body) => {
      if (O.busy || O.refinalizeBusy) return;
      O.busy = true; O.err = ''; drawOnay(out);
      try { const r = await api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        if (r.project) setProject(r.project); O.d = r; } catch (e) { O.err = e.message || String(e); }
      O.busy = false; drawOnay(out);
    };
    if ($('#on-go')) $('#on-go').onclick = () => run(`/api/projects/${getProject().id}/onay`, {name: $('#on-name').value.trim(),
      title: $('#on-title').value, chamber: $('#on-ch').value, reg_no: $('#on-reg').value.trim(), note: $('#on-note').value.trim(),
      statement: $('#on-st').checked});
    if ($('#on-rev')) $('#on-rev').onclick = () => run(`/api/projects/${getProject().id}/onay/revoke`, {reason: $('#on-why').value.trim()});
    if ($('#on-refinalize')) {
      $('#on-refinalize').onclick = async () => {
        if (O.busy || O.refinalizeBusy) return;
        const confirmed = confirm(
          'Metraj ve belgeler yeniden üretilecek.\n\n' +
          '• Güncel fiyat kataloğu maliyeti değiştirebilir\n' +
          '• Çizimler ve belgeler (teklif, metraj, şartname, keşif, çizimler) yeniden üretilir\n' +
          '• Onay durumu yeniden değerlendirilir; tekrar onay gerekebilir\n\n' +
          'Devam etmek istiyor musunuz?'
        );
        if (!confirmed) return;
        O.refinalizeBusy = true; O.err = ''; drawOnay(out);
        try {
          const r = await api(`/api/projects/${getProject().id}/refinalize`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
          if (r.project) setProject(r.project);
          O.d = r;
          O.err = '';
        } catch (e) {
          O.err = e.message || String(e);
        }
        O.refinalizeBusy = false; drawOnay(out);
      };
    }
  }

  return {
    mountOnay(out) { O.d = null; O.err = ''; drawOnay(out); loadOnay(out); },
    bindImar,
    mountPoz(out) {
      out.innerHTML = '<div id="mk-poz"></div><div id="mk-cat"></div>';
      S.poz = null; S.msg = S.err = ''; drawPoz($('#mk-poz')); loadPoz($('#mk-poz'));
      C.d = null; C.msg = C.err = ''; drawCat($('#mk-cat')); loadCat($('#mk-cat'));
    },
  };
}
