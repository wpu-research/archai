// Proje araçları sekmeleri: 10 KAT İRTİFAKI · 11 STATİK · 12 KARŞILAŞTIR · 13 ÇAPRAZ DOĞRULAMA. Sunucu: webapp/araclar_routes.py.
// Sunucudan gelen her metin esc() ile kaçışlanır.
export function createAraclar(ctx) {
  const {$, api, esc, tl, n2, getProject, reload} = ctx;
  const fmt = v => (v == null ? '—' : typeof v === 'number' ? n2(v) : esc(v));
  const sign = v => (v == null ? '—' : (v > 0 ? '+' : '') + n2(v));
  const pctCell = p => (p == null ? '' : `<span class="mono" style="color:${p > 0 ? 'var(--warn)' : 'var(--ok)'}"> %${(p > 0 ? '+' : '') + p}</span>`);
  const S = {cmp: null};
  const wait = (out, t = 'hesaplanıyor…') => { out.innerHTML = `<p class="note">${esc(t)}</p>`; };
  const fail = (out, e) => { out.innerHTML = `<p class="err">${esc(e.message || e)}</p>`; };
  const damga = d => `<p class="note mono" style="color:var(--warn)">${esc(d)}</p>`;

  async function kat(out) {
    wait(out);
    try {
      const P = getProject(), D = await api(`/api/projects/${P.id}/kat-irtifaki`), o = D.ozet;
      out.innerHTML = `${damga(D.damga)}<p class="note">${esc(D.not)}</p>
        <div class="kpis"><div><small>BAĞIMSIZ BÖLÜM</small><b>${esc(o.bolum_sayisi)}</b></div><div><small>KONUT / İŞYERİ</small><b>${esc(o.konut)} / ${esc(o.isyeri)}</b></div>
        <div><small>TOPLAM NET</small><b>${n2(o.net_toplam)} m²</b></div><div><small>TOPLAM BRÜT</small><b>${n2(o.brut_toplam)} m²</b></div></div>
        <div class="mk-row"><a class="ghost" href="${esc(D.dosya)}">↓ KAT İRTİFAKI .XLSX</a></div>
        <div class="scroll"><table><tr><th>No</th><th>Kat</th><th>Bölüm</th><th>Tip</th><th class="n">Net m²</th><th class="n">Brüt m²</th><th class="n">Ortak pay m²</th><th class="n">Toplam brüt</th><th class="n">Arsa payı</th></tr>
        ${D.bolumler.map(b => `<tr><td>${b.no}</td><td>${esc(b.kat)}</td><td>${esc(b.ad)} <small class="mono">${esc(b.tur)}</small></td><td class="mono">${esc(b.tip)}</td>
          <td class="n">${n2(b.net)}</td><td class="n">${n2(b.kat_brut)}</td><td class="n">${n2(b.ortak_pay)}</td><td class="n">${n2(b.toplam_brut)}</td><td class="n"><b>${esc(b.arsa_payi_metin)}</b></td></tr>`).join('')}</table></div>
        ${D.ortak_alanlar.length ? `<p class="sec-t">BAĞIMSIZ BÖLÜM DIŞI ORTAK ALANLAR</p><p class="note">${D.ortak_alanlar.map(a => `${esc(a.kat)}: ${n2(a.alan)} m²`).join(' · ')}</p>` : ''}
        ${D.uyarilar.map(w => `<div class="warnbox">⚠ ${esc(w)}</div>`).join('')}`;
    } catch (e) { fail(out, e); }
  }

  async function statik(out, sigma) {
    wait(out);
    try {
      const P = getProject(), D = await api(`/api/projects/${P.id}/statik${sigma ? `?sigma=${encodeURIComponent(sigma)}` : ''}`);
      const k = D.kolon_kesiti, b = D.kiris, m = D.miktar, r = D.radye;
      out.innerHTML = `${damga(D.damga)}<div class="warnbox">${esc(D.not)}</div>
        <div class="kpis"><div><small>KOLON</small><b>${D.kolon_sayisi} adet · ${Math.round(k.b * 100)}×${Math.round(k.h * 100)}</b></div>
          <div><small>KİRİŞ</small><b>${Math.round(b.b * 100)}×${Math.round(b.h * 100)} · açıklık ${n2(b.en_buyuk_aciklik)} m</b></div>
          <div><small>RADYE ÖNERİSİ</small><b>${n2(r.oneri_kalinlik)} m</b></div><div><small>TEMEL GERİLMESİ</small><b>${r.ortalama_gerilme_kPa} / ${r.emniyet_kPa} kPa</b></div></div>
        <div class="mk-row"><label class="mono" style="margin:0">Zemin emniyet gerilmesi (kPa) <input id="st-sig" type="number" value="${esc(r.emniyet_kPa)}" style="width:90px"></label>
          <button class="ghost" id="st-re">↻ YENİDEN HESAPLA</button><a class="ghost" href="${esc(D.dosya)}">↓ ÖN BOYUTLANDIRMA .XLSX</a></div>
        <p class="sec-t">BETONARME MİKTARI</p>
        <div class="scroll"><table><tr><th>Kalem</th><th class="n">Miktar</th></tr>
          <tr><td>Kolon betonu</td><td class="n">${n2(m.kolon_m3)} m³</td></tr><tr><td>Kiriş betonu</td><td class="n">${n2(m.kiris_m3)} m³</td></tr>
          <tr><td>Çekirdek perdesi</td><td class="n">${n2(m.cekirdek_perde_m3)} m³</td></tr><tr><td>Bodrum çevre perdesi</td><td class="n">${n2(m.bodrum_perde_m3)} m³</td></tr>
          <tr><td><b>Toplam beton</b></td><td class="n"><b>${n2(m.beton_m3)} m³</b></td></tr><tr><td>Donatı (B500C)</td><td class="n">${n2(m.donati_ton)} ton</td></tr>
          <tr><td>Kalıp</td><td class="n">${n2(m.kalip_m2)} m²</td></tr></table></div>
        <p class="sec-t">MALİYETTEKİ AVAN ORANI ↔ ÖN BOYUTLANDIRMA</p>
        <div class="scroll"><table><tr><th>Kod</th><th>Kalem</th><th>Birim</th><th class="n">Avan oranı</th><th class="n">Ön boyutlandırma</th></tr>
          ${D.kiyas.map(x => `<tr><td class="code">${esc(x.kod)}</td><td>${esc(x.ad)}</td><td class="mono">${esc(x.birim)}</td><td class="n">${fmt(x.avan_orani)}</td><td class="n">${fmt(x.on_boyutlandirma)}</td></tr>`).join('')}</table></div>
        <div class="mk-row"><button class="ghost" id="st-ap">✓ MALİYETE UYGULA</button><span class="mono" id="st-msg"></span></div>
        ${D.uyarilar.map(w => `<div class="warnbox">⚠ ${esc(w)}</div>`).join('')}`;
      $('#st-re').onclick = () => statik(out, $('#st-sig').value);
      $('#st-ap').onclick = async () => {
        $('#st-msg').textContent = 'uygulanıyor…';
        try { const R = await api(`/api/projects/${P.id}/statik/uygula`, {method: 'POST'}); $('#st-msg').textContent = `uygulandı · yeni toplam ${tl(R.maliyet.total)}`; setTimeout(reload, 900); }
        catch (e) { $('#st-msg').textContent = e.message; }
      };
    } catch (e) { fail(out, e); }
  }

  async function cmpView(out) {
    const P = getProject();
    let list = [];
    try { list = (await api('/api/projects')).filter(p => p.id !== P.id); } catch (e) { fail(out, e); return; }
    out.innerHTML = `<div class="mk-row"><label class="mono" style="margin:0">Bu proje ↔ <select id="cm-sel" style="min-width:260px"><option value="">— karşılaştırılacak proje —</option>
      ${list.map(p => `<option value="${esc(p.id)}" ${S.cmp === p.id ? 'selected' : ''}>${esc(p.name)} · ${esc(tl(p.total))}</option>`).join('')}</select></label>
      <button class="ghost" id="cm-alt" title="Bu projeden bağımsız bir alternatif oluştur (kat/daire tipi değişikliği ile)">⧉ ALTERNATİF OLUŞTUR</button></div>
      <div id="cm-alt-form" style="display:none;margin-top:12px"></div><div id="cm-out"></div>`;

    // Alternatif oluşturma formu
    $('#cm-alt').onclick = () => {
      const form = $('#cm-alt-form');
      const isHidden = form.style.display === 'none';
      form.style.display = isHidden ? 'block' : 'none';
      if (isHidden) {
        form.innerHTML = `<div class="warnbox">⚠ <b>ÖNEMLİ:</b> Alternatif proje <b>kaydedilen girdilerden (briften) yeniden üretilir</b>.<br>
          Manuel geometri düzenlemeleri (cephe düzeltmesi, iç mekân değişiklikleri vb.) <b>KOPYALANMAZ</b>.<br>
          Onay kayıtları, fizibilite senaryoları, tasarım setleri <b>kopyalanmaz</b>.</div>
          <div class="mk-row"><label class="mono" style="margin:0">Alternatif adı <input id="alt-name" type="text" placeholder="Örn: 4 Katlı Alternatif" style="min-width:220px"></label></div>
          <div class="mk-row"><label class="mono" style="margin:0">Kat sayısı <input id="alt-floors" type="number" min="1" max="30" style="width:80px" placeholder="boş = kaynak aynı"></label>
            <label class="mono" style="margin:0">Daire tipi <select id="alt-ut" style="width:120px"><option value="">kaynak aynı</option><option>1+1</option><option>2+1</option><option>3+1</option><option>4+1</option></select></label>
            <label class="mono" style="margin:0">Kat başına daire <select id="alt-upf" style="width:120px"><option value="">kaynak aynı</option><option value="auto">Otomatik</option><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option></select></label></div>
          <label class="check" style="margin:10px 0"><input type="checkbox" id="alt-ack"> Manuel geometri düzenlemelerinin kopyalanmadığını, kayıtlı girdilerden yeniden üretileceğini onaylıyorum</label>
          <div class="mk-row"><button class="primary" id="alt-go" style="width:auto">⧉ ALTERNATİFİ OLUŞTUR</button><span class="mono" id="alt-msg"></span></div>`;
        $('#alt-go').onclick = createAlternative;
      }
    };

    let creatingAlternative = false;
    async function createAlternative() {
      if (creatingAlternative) return;
      const name = $('#alt-name').value.trim();
      const floors = $('#alt-floors').value ? Number($('#alt-floors').value) : null;
      const unit_type = $('#alt-ut').value || null;
      const selectedUnits = $('#alt-upf').value;
      const units_per_floor = selectedUnits === 'auto' ? 'auto' : selectedUnits ? Number(selectedUnits) : null;
      const acknowledgement = $('#alt-ack').checked;
      const msg = $('#alt-msg');
      if (!name) { msg.textContent = 'alternatif adı gerekli'; return; }
      if (!acknowledgement) { msg.textContent = 'onay kutusunu işaretleyin'; return; }
      if (floors !== null && (!Number.isInteger(floors) || floors < 1 || floors > 30)) {
        msg.textContent = 'Kat sayısı 1–30 arasında tam sayı olmalı'; return;
      }
      creatingAlternative = true;
      const controls = [...$('#cm-alt-form').querySelectorAll('input, select, button'), $('#cm-alt')];
      controls.forEach(control => { control.disabled = true; });
      msg.textContent = 'oluşturuluyor…';
      try {
        const R = await api(`/api/projects/${P.id}/alternatif`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name, floors, unit_type, units_per_floor, acknowledgement})
        });
        msg.textContent = `oluşturuldu: ${R.alternative.name} (${R.alternative.id})`;
        // Navigate to new project
        setTimeout(() => {
          window.location.href = `/#${encodeURIComponent(R.alternative.id)}`;
          // Aynı sayfada yalnız hash değişirse index.html openP'yi tekrar çalıştırmaz.
          window.location.reload();
        }, 1200);
      } catch (e) {
        msg.textContent = e.message || 'hata';
        creatingAlternative = false;
        controls.forEach(control => { control.disabled = false; });
      }
    }

    const draw = async id => {
      const box = $('#cm-out'); if (!id) { box.innerHTML = ''; return; }
      S.cmp = id; wait(box);
      try {
        const D = await api(`/api/projects/${P.id}/karsilastir/${encodeURIComponent(id)}`);
        const row = x => `<tr><td>${esc(x.ad)}</td><td class="n">${fmt(x.a)}</td><td class="n">${fmt(x.b)}</td><td class="n">${sign(x.fark)}${pctCell(x.yuzde)}</td></tr>`;
        box.innerHTML = `<p class="note mono">A: ${esc(D.a.ad)} &nbsp;→&nbsp; B: ${esc(D.b.ad)} (bu proje A, seçilen B)</p>
          <p class="sec-t">GİRDİ FARKLARI</p>${D.girdiler.length ? `<div class="scroll"><table><tr><th>Girdi</th><th class="n">A</th><th class="n">B</th></tr>${D.girdiler.map(g => `<tr><td class="mono">${esc(g.anahtar)}</td><td class="n">${fmt(g.a)}</td><td class="n">${fmt(g.b)}</td></tr>`).join('')}</table></div>` : '<p class="note">girdi farkı yok</p>'}
          <p class="sec-t">ÜRETİLEN DEĞERLER</p><div class="scroll"><table><tr><th></th><th class="n">A</th><th class="n">B</th><th class="n">Fark</th></tr>${D.rapor.map(row).join('')}</table></div>
          <p class="sec-t">MALİYET</p><div class="scroll"><table><tr><th></th><th class="n">A</th><th class="n">B</th><th class="n">Fark</th></tr>${D.maliyet.map(row).join('')}${D.maliyet_gruplari.filter(g => g.fark).map(row).join('')}</table></div>
          <p class="sec-t">EN ÇOK DEĞİŞEN KALEMLER</p><div class="scroll"><table><tr><th>Kod</th><th>Kalem</th><th class="n">Miktar A</th><th class="n">Miktar B</th><th class="n">Tutar farkı</th></tr>
          ${D.kalemler.map(k => `<tr><td class="code">${esc(k.kod)}</td><td>${esc(k.ad)}</td><td class="n">${fmt(k.miktar_a)}</td><td class="n">${fmt(k.miktar_b)}</td><td class="n">${sign(k.fark)} TL</td></tr>`).join('')}</table></div>
          ${D.yeni_uyarilar.map(w => `<div class="warnbox">⚠ yeni: ${esc(w)}</div>`).join('')}`;
      } catch (e) { fail(box, e); }
    };
    $('#cm-sel').onchange = e => draw(e.target.value);
    if (S.cmp) draw(S.cmp);
  }

  async function capraz(out) {
    wait(out);
    try {
      const P = getProject(), D = await api(`/api/projects/${P.id}/capraz-dogrulama`);
      const ST = {uygun: ['UYGUN', 'ok'], uyari: ['UYARI', ''], ihlal: ['İHLAL', 'bad'], bilgi: ['BİLGİ', '']};
      out.innerHTML = `${damga(D.damga)}<div class="kpis"><div><small>UYGUN</small><b>${D.ozet.uygun}</b></div><div><small>UYARI</small><b>${D.ozet.uyari}</b></div><div><small>İHLAL</small><b class="hl">${D.ozet.ihlal}</b></div></div>
        <div class="scroll"><table><tr><th>Durum</th><th>Kontrol</th><th>Ölçülen</th><th>Sınır / karşılaştırma</th><th>Kaynak</th></tr>
        ${D.kontroller.map(k => { const [t, c] = ST[k.durum] || [k.durum, '']; return `<tr><td><span class="flag ${c}">${esc(t)}</span></td><td>${esc(k.ad)}<div class="mono" style="font-size:10.5px;color:var(--mute)">${esc(k.aciklama || '')}</div></td><td class="n">${esc(k.olculen)}</td><td>${esc(k.sinir)}</td><td class="mono" style="font-size:10.5px">${esc(k.kaynak)}</td></tr>`; }).join('')}</table></div>`;
    } catch (e) { fail(out, e); }
  }

  async function odeme(out, q) {
    wait(out);
    try {
      const P = getProject(), D = await api(`/api/projects/${P.id}/odeme-plani${q || ''}`), v = D.varsayimlar, max = Math.max(...D.tablo.map(r => r.net_odeme), 1);
      out.innerHTML = `${damga(D.damga)}<div class="warnbox">${esc(D.not)}</div>
        <div class="mk-row"><label class="mono" style="margin:0">Süre (ay) <input id="od-ay" type="number" min="3" max="60" value="${esc(D.sure_ay)}" style="width:70px"></label>
          <label class="mono" style="margin:0">Avans % <input id="od-av" type="number" min="0" max="50" value="${esc(v.avans_pct)}" style="width:70px"></label>
          <label class="mono" style="margin:0">Teminat % <input id="od-te" type="number" min="0" max="20" value="${esc(v.teminat_pct)}" style="width:70px"></label>
          <button class="ghost" id="od-go">↻ HESAPLA</button><a class="ghost" href="${esc(D.dosya)}">↓ ÖDEME PLANI .XLSX</a></div>
        <div class="kpis"><div><small>TOPLAM (KDV HARİÇ)</small><b>${tl(D.toplam_kdv_haric)}</b></div><div><small>TOPLAM (KDV DAHİL)</small><b class="hl">${tl(D.toplam_kdv_dahil)}</b></div>
          <div><small>SÜRE</small><b>${D.sure_ay} ay</b></div><div><small>KDV</small><b>%${esc(v.kdv_pct)}</b></div></div>
        <div class="scroll"><table><tr><th>Ay</th><th class="n">İlerleme %</th><th class="n">Hakediş</th><th class="n">Avans mahs.</th><th class="n">Teminat</th><th class="n">KDV</th><th class="n">Net ödeme</th><th></th><th class="n">Kümülatif</th></tr>
        ${D.tablo.map(r => `<tr><td>${r.ay}${r.not ? ` <small class="mono">${esc(r.not)}</small>` : ''}</td><td class="n">${n2(r.is_orani)}</td><td class="n">${tl(r.hakedis)}</td><td class="n">${tl(r.avans_mahsubu)}</td><td class="n">${tl(r.teminat_kesintisi)}</td><td class="n">${tl(r.kdv)}</td><td class="n"><b>${tl(r.net_odeme)}</b></td>
          <td style="width:120px"><div style="height:8px;border-radius:4px;background:linear-gradient(90deg,var(--cy),var(--blue));width:${Math.max(2, Math.round(r.net_odeme / max * 100))}%"></div></td><td class="n">${tl(r.kumulatif_odeme)}</td></tr>`).join('')}</table></div>`;
      $('#od-go').onclick = () => odeme(out, `?ay=${encodeURIComponent($('#od-ay').value)}&avans=${encodeURIComponent($('#od-av').value)}&teminat=${encodeURIComponent($('#od-te').value)}`);
    } catch (e) { fail(out, e); }
  }

  const CS = {kat: null, ayni: true};
  async function cephe(out) {
    wait(out);
    try {
      const P = getProject(), D = await api(`/api/projects/${P.id}/cephe`);
      const katlar = [...new Set(D.duvarlar.map(w => w.kat))];
      if (!CS.kat || !katlar.includes(CS.kat)) CS.kat = katlar.find(k => k.startsWith('Kat ')) || katlar[0];
      const walls = D.duvarlar.filter(w => w.kat === CS.kat);
      const f = (cls, v, st = 0.05) => `<input class="num ${cls}" type="number" step="${st}" value="${esc(v ?? '')}" style="width:74px">`;
      out.innerHTML = `${damga(D.damga)}<p class="note">${esc(D.not)}</p>
        <div class="mk-row"><label class="mono" style="margin:0">Kat <select id="ce-kat">${katlar.map(k => `<option ${k === CS.kat ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select></label>
          <label class="check" style="margin:0"><input type="checkbox" id="ce-ayni" ${CS.ayni ? 'checked' : ''}> aynı plandaki normal katlara da uygula</label><span class="mono" id="ce-msg"></span></div>
        ${walls.map(w => `<p class="sec-t">${esc(w.yon_ad)} CEPHE · ${esc(w.duvar)} · ${n2(w.uzunluk)} m × ${n2(w.yukseklik)} m</p>
          <div class="scroll"><table><tr><th>Tür</th><th>Yerleşim (m)</th><th>Genişlik</th><th>Alt kot</th><th>Yükseklik</th><th></th></tr>
          ${w.acikliklar.map(o => `<tr data-w="${esc(w.duvar)}" data-i="${o.index}"><td><select class="ce-k"><option value="window" ${o.kind === 'window' ? 'selected' : ''}>pencere</option><option value="door" ${o.kind === 'door' ? 'selected' : ''}>kapı</option></select></td>
            <td>${f('ce-o', o.offset)}</td><td>${f('ce-w', o.width)}</td><td>${f('ce-s', o.sill)}</td><td>${f('ce-h', o.height)}</td>
            <td><button class="ghost ce-ap">✓ UYGULA</button> <button class="ghost ce-del">✕ SİL</button></td></tr>`).join('') || '<tr><td colspan="6" class="note">açıklık yok</td></tr>'}
          <tr data-w="${esc(w.duvar)}" data-new="1"><td><select class="ce-k"><option value="window">pencere</option><option value="door">kapı</option></select></td><td>${f('ce-o', '')}</td><td>${f('ce-w', '1.2')}</td><td>${f('ce-s', '0.9')}</td><td>${f('ce-h', '')}</td>
            <td><button class="ghost ce-add">+ EKLE</button></td></tr></table></div>`).join('')}`;
      const num = (tr, c) => { const v = tr.querySelector(c).value; return v === '' ? undefined : +v; };
      const send = async (op, tr) => {
        $('#ce-msg').textContent = 'uygulanıyor…';
        try { const R = await api(`/api/projects/${P.id}/cephe`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({islemler: [{...op, ayni_katlar: $('#ce-ayni').checked}]})});
          $('#ce-msg').textContent = `uygulandı (${R.uygulanan} duvar) · yeni toplam ${tl(R.maliyet.total)}`; setTimeout(reload, 900); }
        catch (e) { $('#ce-msg').textContent = e.message; }
      };
      $('#ce-kat').onchange = e => { CS.kat = e.target.value; cephe(out); };
      $('#ce-ayni').onchange = e => { CS.ayni = e.target.checked; };
      out.querySelectorAll('.ce-ap').forEach(b => b.onclick = () => { const tr = b.closest('tr'); send({duvar: tr.dataset.w, islem: 'degistir', index: +tr.dataset.i, kind: tr.querySelector('.ce-k').value,
        offset: num(tr, '.ce-o'), width: num(tr, '.ce-w'), sill: tr.querySelector('.ce-k').value === 'door' ? undefined : num(tr, '.ce-s'), height: num(tr, '.ce-h')}); });
      out.querySelectorAll('.ce-del').forEach(b => b.onclick = () => { const tr = b.closest('tr'); send({duvar: tr.dataset.w, islem: 'sil', index: +tr.dataset.i}); });
      out.querySelectorAll('.ce-add').forEach(b => b.onclick = () => { const tr = b.closest('tr'); send({duvar: tr.dataset.w, islem: 'ekle', kind: tr.querySelector('.ce-k').value,
        offset: num(tr, '.ce-o'), width: num(tr, '.ce-w'), sill: num(tr, '.ce-s'), height: num(tr, '.ce-h')}); });
    } catch (e) { fail(out, e); }
  }

  async function sponsor(out) {
    wait(out);
    try {
      const D = await api('/api/sponsorlar'), P = getProject(), proj = P ? await api(`/api/projects/${P.id}/sponsorlar`).catch(() => ({sponsorlar: []})) : {sponsorlar: []};
      let list = D.sponsorlar;
      const save = async () => { await api('/api/sponsorlar', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({sponsorlar: list})}); sponsor(out); };
      out.innerHTML = `<p class="note">${esc(D.not)}</p>
        <div class="scroll"><table><tr><th>Firma (katalogdaki tedarikçi adı)</th><th>Kategori</th><th>Web</th><th>Not</th><th></th></tr>
        ${list.map((x, i) => `<tr><td>${esc(x.ad)}</td><td class="mono">${esc((x.kategoriler || []).join(', '))}</td><td class="mono">${esc(x.web)}</td><td>${esc(x.not)}</td><td><button class="ghost sp-del" data-i="${i}">✕ SİL</button></td></tr>`).join('') || '<tr><td colspan="5" class="note">sponsor tanımlı değil</td></tr>'}
        <tr><td><input id="sp-ad" placeholder="Firma adı" style="width:100%"></td><td><input id="sp-kat" placeholder="mutfak, banyo" style="width:100%"></td><td><input id="sp-web" placeholder="https://…" style="width:100%"></td><td><input id="sp-not" placeholder="not" style="width:100%"></td><td><button class="ghost" id="sp-add">+ EKLE</button></td></tr></table></div>
        <span class="mono" id="sp-msg"></span>
        <p class="sec-t">BU PROJEDE KULLANILAN SPONSOR ÜRÜNLERİ</p>
        ${proj.sponsorlar.length ? `<div class="scroll"><table><tr><th>Sponsor</th><th>Kalem · ürün</th></tr>${proj.sponsorlar.map(x => `<tr><td>${esc(x.sponsor)}</td><td>${x.urunler.map(u => `${esc(u.kod)}: ${esc(u.ad)}`).join('<br>')}</td></tr>`).join('')}</table></div>`
          : '<p class="note">Bu projede sponsor kataloğundan ürün seçilmedi (Maliyet · Fiyat ve Poz · Katalog sekmelerinden katalog seçimi yapılır).</p>'}`;
      $('#sp-add').onclick = async () => {
        const ad = $('#sp-ad').value.trim(); if (!ad) return;
        list = [...list, {ad, kategoriler: $('#sp-kat').value.split(',').map(t => t.trim().toLowerCase()).filter(Boolean), web: $('#sp-web').value.trim(), not: $('#sp-not').value.trim()}];
        try { await save(); } catch (e) { $('#sp-msg').textContent = e.message; list = list.slice(0, -1); }
      };
      out.querySelectorAll('.sp-del').forEach(b => b.onclick = async () => { list = list.filter((_, i) => i !== +b.dataset.i); await save(); });
    } catch (e) { fail(out, e); }
  }

  return {mountSponsor: out => sponsor(out), mountCephe: out => cephe(out), mountOdeme: out => odeme(out), mountKat: kat, mountStatik: out => statik(out), mountKarsilastir: cmpView, mountCapraz: capraz};
}
