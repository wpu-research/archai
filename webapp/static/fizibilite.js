// Hesaplar ve senaryo kayıtları proje maliyetini / belgelerini değiştirmez.
export function createFizibilite({api, esc, tl, n2, getProject}) {
  let generation = 0;
  return {
    mount(out) {
      const current = ++generation, pid = getProject().id;
      out.innerHTML = `<section class="mk">
        <p class="sec-t">FİZİBİLİTE · SATIŞ SENARYOSU</p>
        <p class="note">Kayıtlı proje teklif bedelinden hesaplanır; piyasa verisi çekilmez. Satılabilir alanı ayrıca girin: brüt inşaat alanı satış alanı değildir. Hesapladıktan sonra senaryoyu adıyla kaydedebilirsiniz.</p>
        <form id="fi-form">
          <div class="grid2">
            <div><label for="fi-land">Arsa bedeli (₺)</label><input id="fi-land" name="arsa_bedeli_tl" type="number" min="0" max="1000000000000000" step="0.01" value="0" required></div>
            <div><label for="fi-price">KDV dahil satış m² fiyatı (₺/m²)</label><input id="fi-price" name="satis_m2_fiyati_tl" type="number" min="0.01" max="1000000000" step="0.01" required></div>
            <div><label for="fi-area">Satılabilir alan (m²)</label><input id="fi-area" name="satilabilir_alan_m2" type="number" min="0.01" max="100000000" step="0.01" required></div>
            <div><label for="fi-extra">İnşaat bedeli üzerinden ek gider (%)</label><input id="fi-extra" name="ek_gider_pct" type="number" min="0" max="100" step="0.01" value="0" required></div>
          </div>
          <button class="ghost" type="submit" style="margin-top:12px">FİZİBİLİTEYİ HESAPLA</button>
        </form>
        <p id="fi-error" class="err" role="alert" hidden></p>
        <div id="fi-result" aria-live="polite"></div>
        <div class="mk-row">
          <label for="fi-name">Senaryo adı</label><input id="fi-name" maxlength="80" placeholder="Ör. Temkinli satış">
          <button class="ghost" id="fi-save" type="button" disabled>SENARYOYU KAYDET</button>
        </div>
        <p id="fi-save-status" class="note" role="status"></p>
        <p class="sec-t">KAYITLI SENARYOLAR · KARŞILAŞTIR</p>
        <button class="ghost" id="fi-refresh" type="button">KAYITLARI YENİLE</button>
        <div id="fi-scenarios" aria-live="polite"></div>
      </section>`;
      const form = out.querySelector('#fi-form'), button = form.querySelector('button');
      const result = out.querySelector('#fi-result'), error = out.querySelector('#fi-error');
      const save = out.querySelector('#fi-save'), name = out.querySelector('#fi-name');
      const status = out.querySelector('#fi-save-status'), savedView = out.querySelector('#fi-scenarios');
      let busy = false, saving = false, revision = 0, calculation = null, loadSequence = 0;
      const alive = () => current === generation && getProject().id === pid && out.contains(form);
      const invalidate = () => { revision++; calculation = null; save.disabled = true; result.innerHTML = ''; error.hidden = true; status.textContent = ''; };
      // A changed assumption must never leave the previous result presented as current.
      form.addEventListener('input', invalidate);
      async function loadSaved() {
        const sequence = ++loadSequence;
        try {
          const data = await api(`/api/projects/${encodeURIComponent(pid)}/fizibilite/senaryolar`);
          if (!alive() || sequence !== loadSequence) return;
          const rows = data.senaryolar;
          if (!rows.length) { savedView.innerHTML = '<p class="note">Henüz kayıtlı senaryo yok.</p>'; return; }
          const options = rows.map((row, i) => `<option value="${i}">${esc(row.ad)}${row.guncel ? '' : ' — ESKİ PROJE'}</option>`).join('');
          savedView.innerHTML = `<p class="note">${rows.length} / ${data.limit} kayıt. Eski kayıtlar değiştirilmez; farklı proje sürümlerinin sonuçlarını doğrudan karşılaştırmayın. Senaryo, proje ve belgelerin tam yedeği değildir.</p>
            <div class="grid2"><div><label for="fi-a">Senaryo A</label><select id="fi-a">${options}</select></div>
            <div><label for="fi-b">Senaryo B</label><select id="fi-b">${options}</select></div></div>
            <div id="fi-comparison" style="overflow-x:auto;max-width:100%"></div>
            <button class="ghost" id="fi-use" type="button">A SENARYOSUNU FORMA AKTAR</button>`;
          const a = savedView.querySelector('#fi-a'), b = savedView.querySelector('#fi-b');
          b.value = String(Math.min(1, rows.length - 1));
          const compare = () => {
            const selected = [rows[Number(a.value)], rows[Number(b.value)]];
            const fields = [
              ['Kayıt tarihi (UTC)', row => row.kayit_zamani],
              ['Proje eşleşmesi', row => row.guncel ? 'Güncel projeyle eşleşiyor' : 'GÜNCEL PROJEYLE EŞLEŞMİYOR'],
              ['Proje sürümü', row => row.hesap.kaynak.proje_parmak_izi.slice(0, 12)],
              ['Arsa bedeli', row => tl(row.hesap.varsayimlar.arsa_bedeli_tl)],
              ['Satış m² fiyatı', row => tl(row.hesap.varsayimlar.satis_m2_fiyati_tl)],
              ['Satılabilir alan', row => n2(row.hesap.varsayimlar.satilabilir_alan_m2) + ' m²'],
              ['Ek gider oranı', row => n2(row.hesap.varsayimlar.ek_gider_pct) + ' %'],
              ['Toplam gider', row => tl(row.hesap.sonuc.toplam_gider_tl)],
              ['Satış geliri', row => tl(row.hesap.sonuc.satis_geliri_tl)],
              ['Tahmini kâr / zarar', row => tl(row.hesap.sonuc.tahmini_kar_tl)],
              ['Kâr marjı', row => n2(row.hesap.sonuc.kar_marji_pct) + ' %'],
              ['Başabaş fiyatı', row => tl(row.hesap.sonuc.basabas_m2_fiyati_tl) + ' /m²']
            ];
            savedView.querySelector('#fi-comparison').innerHTML = `<table style="width:100%;overflow-wrap:anywhere"><caption>Kaydedildiği andaki varsayım ve sonuçlar</caption><thead><tr><th>Ölçüt</th>${selected.map(row => `<th scope="col">${esc(row.ad)}</th>`).join('')}</tr></thead><tbody>${fields.map(([label, value]) => `<tr><th scope="row">${esc(label)}</th>${selected.map(row => `<td>${esc(value(row))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
          };
          a.onchange = b.onchange = compare;
          savedView.querySelector('#fi-use').onclick = () => {
            if (busy || saving) return;
            for (const [key, value] of Object.entries(rows[Number(a.value)].hesap.varsayimlar)) form.elements.namedItem(key).value = value;
            invalidate(); status.textContent = 'Varsayımlar aktarıldı. Güncel maliyetle yeniden hesaplayın.';
          };
          compare();
        } catch (e) {
          if (alive() && sequence === loadSequence) savedView.innerHTML = `<p class="err" role="alert">${esc(e.message || String(e))}</p>`;
        }
      }
      out.querySelector('#fi-refresh').onclick = loadSaved;
      save.onclick = async () => {
        if (!calculation || saving || busy) return;
        if (!name.value.trim()) { status.textContent = 'Senaryo adı girin.'; name.focus(); return; }
        const snapshot = calculation;
        saving = true; save.disabled = true; button.disabled = true; status.textContent = 'Kaydediliyor…';
        try {
          await api(`/api/projects/${encodeURIComponent(pid)}/fizibilite/senaryolar`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({...snapshot.varsayimlar, ad: name.value.trim(), proje_parmak_izi: snapshot.kaynak.proje_parmak_izi})
          });
          if (!alive()) return;
          status.textContent = 'Senaryo kaydedildi.';
          if (calculation === snapshot) calculation = null;
          await loadSaved();
        } catch (e) {
          if (alive()) { status.textContent = e.message || String(e); }
        } finally {
          saving = false; save.disabled = !calculation; button.disabled = busy;
        }
      };
      loadSaved();
      form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || saving || !form.reportValidity()) return;
        const started = revision;
        const body = Object.fromEntries([...new FormData(form)].map(([key, value]) => [key, Number(value)]));
        busy = true; calculation = null; save.disabled = true; button.disabled = true; error.hidden = true; result.innerHTML = ''; status.textContent = '';
        try {
          const data = await api(`/api/projects/${encodeURIComponent(pid)}/fizibilite`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
          });
          if (current !== generation || getProject().id !== pid || !out.contains(form) || started !== revision) return;
          calculation = data; save.disabled = false;
          const s = data.sonuc;
          const rows = [
            ['Kayıtlı inşaat teklif bedeli', tl(s.insaat_bedeli_tl)],
            ['Arsa bedeli', tl(data.varsayimlar.arsa_bedeli_tl)],
            ['Ek gider', tl(s.ek_gider_tl)], ['Toplam gider', tl(s.toplam_gider_tl)],
            ['Tahmini satış geliri', tl(s.satis_geliri_tl)], ['Tahmini kâr / zarar', tl(s.tahmini_kar_tl)],
            ['Gelire göre kâr marjı', n2(s.kar_marji_pct) + ' %'],
            ['Maliyete göre getiri', n2(s.maliyet_getirisi_pct) + ' %'],
            ['Başabaş satış fiyatı', tl(s.basabas_m2_fiyati_tl) + ' /m²']
          ];
          result.innerHTML = `<table style="width:100%;margin-top:16px"><caption>Girilen varsayımlarla fizibilite sonucu</caption><tbody>${rows.map(([label, value]) => `<tr><th scope="row" style="text-align:left">${esc(label)}</th><td>${esc(value)}</td></tr>`).join('')}</tbody></table>
            <p class="note">Kaynak proje: ${esc(data.proje_id)} · Sürüm: ${esc(data.kaynak.proje_parmak_izi.slice(0, 12))}</p>
            ${data.uyarilar.map(text => `<p class="note">${esc(text)}</p>`).join('')}`;
        } catch (e) {
          if (current !== generation || getProject().id !== pid || !out.contains(form) || started !== revision) return;
          error.textContent = e.message || String(e); error.hidden = false;
        } finally {
          busy = false; button.disabled = false;
        }
      });
    }
  };
}
