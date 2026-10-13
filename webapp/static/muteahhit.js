// Müteahhit katmanı sekmeleri: 08 POZ · KEŞİF, 09 ONAY. Sunucu: webapp/muteahhit_routes.py.
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

  return {
    mountPoz(out) { S.poz = null; S.msg = S.err = ''; drawPoz(out); loadPoz(out); },
  };
}
