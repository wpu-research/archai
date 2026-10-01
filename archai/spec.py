"""Teknik şartname: maliyet satırlarından kalem kalem şartname metni.

Metinler şablondur; firma kendi şartname kütüphanesiyle değiştirmeli/genişletmelidir.
"Ölçü ve ödeme" bölümü, kalemin metraj kuralıyla aynı yöntemi anlatır.
"""

from .notice import AVAN_NOTE, IMAR_NOTE

GENERAL = [
    AVAN_NOTE,
    IMAR_NOTE,
    "Bu şartname, projede yer alan imalatların malzeme, uygulama, ölçü ve ödeme esaslarını tanımlar.",
    "Tüm imalatlar onaylı uygulama projelerine, yürürlükteki yönetmeliklere ve ilgili TS / TS EN standartlarına uygun yapılacaktır.",
    "Kullanılacak malzemelerin numuneleri ve teknik föyleri uygulamadan önce idare/mal sahibi onayına sunulacaktır.",
    "Miktarlar plan üzerinden hesaplanan ön metrajdır; kesin hesap yerinde ölçüm ile yapılacaktır.",
    "Birim fiyatlara malzeme, işçilik, nakliye, iskele ve yardımcı malzemeler dahildir (aksi belirtilmedikçe).",
]

ITEMS = {
    "BET-01": {
        "malzeme": "Beton sınıfı projesinde belirtilen sınıfta (en az C30/37) hazır beton kullanılacak, TS EN 206'ya uygun olacaktır. Donatı B500C nervürlü çelik olacaktır.",
        "uygulama": "Kalıp, donatı ve pas payları projeye ve TS 500'e göre kontrol edilmeden beton dökülmeyecek; beton vibratörle yerleştirilip en az 7 gün kür edilecektir.",
        "olcum": "Döşeme alanı × döşeme kalınlığı ile hacim (m³) olarak hesaplanır; kalıp ve donatı birim fiyata dahildir.",
    },
    "DUV-01": {
        "malzeme": "Dış duvarlar projede belirtilen kalınlıkta yatay delikli tuğla, gazbeton veya bims blok ile örülecektir; kâgir birimler TS EN 771 serisine uygun olacaktır.",
        "uygulama": "Duvarlar şaşırtmalı örülecek, derzler tam doldurulacak, betonarme elemanlarla birleşimlerde filiz/file uygulanacaktır. Lento ve hatıllar projeye göre yapılacaktır.",
        "olcum": "Yalnız dış cepheye bakan duvarlar: aks uzunluğu × duvar yüksekliğinden pencere ve kapı boşlukları düşülerek net duvar alanı (m²) üzerinden ödenir. Aks ölçüsü T/L birleşimlerinde ~%1–2 fazla sayım içerir.",
    },
    "DUV-02": {
        "malzeme": "İç bölme duvarları projede belirtilen kalınlıkta tuğla/gazbeton veya onaylı hafif bölme sistemi ile yapılacaktır.",
        "uygulama": "Duvarlar döşemeye ve tavana rijit bağlanacak, ıslak hacim duvarlarında su yalıtımı için uygun yüzey hazırlanacaktır.",
        "olcum": "Net duvar alanı (m²), boşluklar düşülerek hesaplanır.",
    },
    "DUV-03": {
        "malzeme": "Masif tomruk (log) duvar: fırınlanmış, nem oranı ≤ %18 iğne yapraklı ağaç; profil ve kalınlık projeye göre. Emprenye ve UV koruyucu yüzey işlemi dahildir.",
        "uygulama": "Tomruklar köşelerde geçmeli (çentikli) birleşim ve kat arası yalıtım bandı ile örülecek; oturma payı bırakılacak, kapı-pencere kasaları kayar profil ile monte edilecektir.",
        "olcum": "Aks uzunluğu × duvar yüksekliğinden boşluklar düşülerek net duvar alanı (m²) üzerinden ödenir.",
    },
    "CAT-02": {
        "malzeme": "Ahşap makas/mertek sistemi, OSB veya ahşap kaplama, nefes alan su yalıtım örtüsü, çıta ve çatı örtüsü (shingle veya metal); ısı yalıtımı dahildir.",
        "uygulama": "Eğim projeye göre; mahya ve saçak havalandırması bırakılacak, baca ve tesisat geçişlerinde etek/sızdırmazlık yapılacaktır.",
        "olcum": "Eğimli çatı yüzey alanı (m²) üzerinden ödenir; saçak çıkmaları dahildir.",
    },
    "YAL-01": {
        "malzeme": "Isı yalıtım levhaları (EPS/XPS/taş yünü) TS 825 hesabına göre belirlenen kalınlıkta olacak; yapıştırıcı, dübel, file ve sıva aynı sistemin bileşenleri olacaktır.",
        "uygulama": "Levhalar şaşırtmalı yapıştırılıp dübellenecek, köşelerde köşe profili, pencere çevrelerinde damlalık ve file takviyesi yapılacaktır.",
        "olcum": "Dış duvar net alanı (m²) üzerinden ödenir; pencere söve dönüşleri birim fiyata dahildir.",
    },
    "CAT-01": {
        "malzeme": "Bitümlü polimer esaslı membran (iki kat) veya onaylı sıvı yalıtım sistemi kullanılacaktır.",
        "uygulama": "Eğim betonu üzerine astar sürülecek, bindirmeler en az 10 cm yapılacak, parapetlere en az 30 cm dönülecektir. Uygulama sonrası su tutma testi yapılacaktır.",
        "olcum": "Çatı döşeme alanı (m²) üzerinden ödenir; parapet dönüşleri dahildir.",
    },
    "SIV-01": {
        "malzeme": "Kaba sıva çimento/kireç esaslı hazır sıva, üzerine saten alçı ve iki kat su bazlı iç cephe boyası.",
        "uygulama": "Yüzeyler tozdan arındırılıp astarlanacak, köşelere köşe profili konacaktır. Boya en az iki kat, tam örtücü uygulanacaktır.",
        "olcum": "Mahal çevresi × mahal yüksekliğinden, mahalin yüzündeki kapı ve pencere boşlukları düşülerek duvar yüzeyi (m²) olarak hesaplanır (iç kapı her iki mahalde, pencere ve dış kapı tek yüzde düşülür). Asansör kuyusu ve şaftlar dahil değildir.",
    },
    "SIV-02": {
        "malzeme": "Mantolama sisteminin son kat dekoratif sıvası ve silikonlu dış cephe boyası.",
        "uygulama": "Sistem üreticisinin talimatlarına uygun, en az iki kat boya ile uygulanacaktır.",
        "olcum": "Dış duvar net alanı (m²) üzerinden ödenir.",
    },
    "TAV-01": {
        "malzeme": "Saten alçı ve iki kat su bazlı tavan boyası; ıslak hacimlerde neme dayanıklı boya.",
        "uygulama": "Tavan yüzeyleri düzeltilip astarlanarak uygulanacaktır.",
        "olcum": "Mahal net alanı (m²) üzerinden ödenir.",
    },
    "SAP-01": {
        "malzeme": "Çimento esaslı şap, TS EN 13813'e uygun, en az 5 cm kalınlıkta.",
        "uygulama": "Kotlar lazerle alınacak, derzler bırakılacak, ıslak hacimlerde süzgece doğru eğim verilecektir.",
        "olcum": "Mahal net alanı (m²) üzerinden ödenir.",
    },
    "ZEM-01": {
        "malzeme": "Zemin kaplaması: {variant}. Malzeme numunesi ve renk onayı alınacaktır.",
        "uygulama": "Şap kuruduktan ve nem ölçümü yapıldıktan sonra üretici talimatına göre uygulanacak; seramik/taş kaplamalarda TS EN 12004'e uygun yapıştırıcı kullanılacaktır.",
        "olcum": "Daire içi mahallerin net alanı (m²) üzerinden ödenir; ortak alanlar (ORT-01), merdiven, asansör kuyusu ve şaftlar dahil değildir. Fire birim fiyata dahildir.",
    },
    "ORT-01": {
        "malzeme": "Ortak alan (kat holü, giriş holü) zemin kaplaması: granit veya yüksek aşınma dayanımlı (PEI 5) porselen seramik; kaymazlık sınıfı R10.",
        "uygulama": "Şap üzerine TS EN 12004'e uygun yapıştırıcı ile; asansör ve merdiven eşiklerinde kot farkı bırakılmadan döşenecektir.",
        "olcum": "Ortak mahallerin (merdiven evi ve asansör kuyusu hariç) net alanı (m²) üzerinden ödenir.",
    },
    "HAF-01": {
        "malzeme": "Temel çukuru kazısı, her cins zeminde; kazı fazlası toprağın döküm alanına nakli dahil.",
        "uygulama": "Kazı şevleri ve iksa zemin etüdü raporuna göre yapılacak; temel altı tesviye ve sıkıştırma dahildir.",
        "olcum": "AVAN yaklaşık: bina oturum alanı × (radye kalınlığı + 1,0 m) hacim (m³). Kesin miktar zemin etüdü ve temel projesine göre belirlenir.",
    },
    "TEM-01": {
        "malzeme": "Radye temel betonarmesi (en az C30/37, B500C donatı), grobeton, temel altı su yalıtımı ve koruma betonu dahil.",
        "uygulama": "Statik projeye göre; yalıtım bindirmeleri ve perde dönüşleri tutanakla kontrol edilecektir.",
        "olcum": "AVAN yaklaşık: bina oturum alanı × radye kalınlığı (0,30 + 0,04 × kat adedi m) hacim (m³). Kesin statik ve temel projesi sonrası kesinleşir.",
    },
    "TEM-02": {
        "malzeme": "Tekil beton pabuç + taş/beton ayak; ahşap taban kirişlerine ankraj dahil.",
        "uygulama": "Don derinliğinin altına oturtulacak; ayak üst kotları nivo ile kontrol edilecektir.",
        "olcum": "AVAN yaklaşık: bina oturum alanı (m²) üzerinden götürü. Kesin temel projesine göre kesinleşir.",
    },
    "KOL-01": {
        "malzeme": "Kolon, kiriş ve perde betonarmesi (en az C30/37, B500C donatı, kalıp dahil).",
        "uygulama": "TS 500 ve Türkiye Bina Deprem Yönetmeliği'ne uygun statik projeye göre yapılacaktır.",
        "olcum": "AVAN yaklaşık: betonarme kat döşemesi alanı × 0,12 m³/m² (döşeme betonu BET-01'de ayrıca sayılır). Kesin statik proje sonrası kesinleşir.",
    },
    "MER-01": {
        "malzeme": "Betonarme merdiven kolu ve sahanlığı; basamak ve rıhtlarda granit/doğal taş kaplama; korkuluk ve küpeşte.",
        "uygulama": "Rıht yüksekliği tüm kolda eşit; basamak kaymaz kenarlı olacaktır.",
        "olcum": "Basamak sayısı × kol genişliği (m, basamak uzunluğu) üzerinden; sahanlık birim fiyata dahildir. AVAN yaklaşık, statik projeye göre kesinleşir.",
    },
    "MER-02": {
        "malzeme": "Kurutulmuş masif ahşap limonluk ve basamak; korkuluk ve küpeşte dahil.",
        "uygulama": "Limonluklar döşemeye ankrajlanacak, basamaklar gıcırtı önleyici bağlantıyla monte edilecektir.",
        "olcum": "Basamak sayısı × merdiven genişliği (m) üzerinden ödenir.",
    },
    "DUV-04": {
        "malzeme": "Çekirdek ve daire ayırma duvarları: en az 20 cm yatay delikli tuğla / gazbeton; yangın ve ses yalıtım gereklerini sağlayacak.",
        "uygulama": "Duvarlar betonarme elemanlara filiz ile bağlanacak; tesisat geçişleri yangın durdurucu ile kapatılacaktır.",
        "olcum": "İç (dış cepheye bakmayan) ≥20 cm duvarların net alanı (m²), boşluklar düşülerek hesaplanır.",
    },
    "ASN-01": {
        "malzeme": "Elektrikli asansör (TS EN 81-20/50), kabin, makine, ray, kumanda ve kat kapıları; ilk periyodik kontrol dahil.",
        "uygulama": "Asansör Yönetmeliği'ne uygun; kuyu ölçüleri ve makine yeri üretici projesine göre.",
        "olcum": "AVAN yaklaşık: durak (kat) başına adet. Kesin bedel kabin kapasitesi ve üretici teklifine göre belirlenir.",
    },
    "SUP-01": {
        "malzeme": "Zemin kaplamasıyla uyumlu süpürgelik.",
        "uygulama": "Duvara düz ve derzsiz monte edilecek, köşeler gönyesinde kesilecektir.",
        "olcum": "Mahal çevre uzunluğundan kapı genişlikleri düşülerek (m) ödenir; merdiven evi, asansör kuyusu ve şaftlar dahil değildir.",
    },
    "PEN-01": {
        "malzeme": "Pencere sistemi: {variant}. Yalıtım camı TS EN 1279'a uygun olacak; ısıl geçirgenlik değerleri TS 825 hesabını sağlayacaktır.",
        "uygulama": "Doğramalar ankrajla tespit edilecek, kasa-duvar birleşimi yalıtım bantları ile sızdırmaz yapılacaktır.",
        "olcum": "Pencere boşluk alanı (genişlik × yükseklik, m²) üzerinden ödenir.",
    },
    "PEN-02": {
        "malzeme": "Doğal taş veya kompozit denizlik, dış cephede damlalıklı.",
        "uygulama": "Dışa doğru eğimli ve derzleri sızdırmaz şekilde monte edilecektir.",
        "olcum": "Pencere genişliği toplamı (m) üzerinden ödenir.",
    },
    "KAP-01": {
        "malzeme": "Kapı kasası, pervazı ve kanadı onaylı numuneye uygun; kilit, menteşe ve kolları dahil.",
        "uygulama": "Kasalar terazisinde ve şakülünde montajlanacak, kanat boşlukları eşit bırakılacaktır.",
        "olcum": "Adet olarak ödenir.",
    },
    "HAV-01": {
        "malzeme": "Su geçirimsiz betonarme havuz teknesi, havuz seramiği/mozaik, filtrasyon ve pompa sistemi.",
        "uygulama": "Tekne su testi yapılmadan kaplamaya geçilmeyecektir; tesisat projesine uygun makine dairesi kurulacaktır.",
        "olcum": "Havuz su yüzeyi alanı (m²) üzerinden götürü birim fiyatla ödenir.",
    },
    "PEY-01": {
        "malzeme": "Dış mekâna ve dona dayanıklı, kaymaz yüzeyli doğal taş.",
        "uygulama": "Eğimli harç yatak veya yükseltilmiş sistem üzerine, derzleri doldurularak döşenecektir.",
        "olcum": "Kaplama alanı (m²) üzerinden ödenir.",
    },
    "TES-01": {
        "malzeme": "Sıhhi tesisat, ısıtma ve havalandırma; mekanik tesisat projesine göre.",
        "uygulama": "Onaylı mekanik projeye ve ilgili yönetmeliklere uygun yapılacak, basınç testleri tutanakla teslim edilecektir.",
        "olcum": "Brüt inşaat alanı (m²) üzerinden götürü ödenir.",
    },
    "TES-02": {
        "malzeme": "Kuvvetli ve zayıf akım tesisatı; elektrik projesine göre.",
        "uygulama": "Onaylı elektrik projesine uygun yapılacak, topraklama ve yalıtım ölçümleri raporlanacaktır.",
        "olcum": "Brüt inşaat alanı (m²) üzerinden götürü ödenir.",
    },
}


def build_spec(project_name, qres, cost):
    """Şartname yapısı: {"title", "general", "summary", "items": [...]} — raporlayıcılar kullanır."""
    s = qres["summary"]
    summary = [
        ("Brüt inşaat alanı", f'{s["gross_floor_area"]:.2f} m²'),
        ("Net kullanım alanı (mahaller)", f'{s["net_room_area"]:.2f} m²'),
        ("Kat sayısı", str(len({l["level"] for l in qres["lines"] if l["type"] == "slab" and l["role"] == "floor"}))),
        ("Toplam duvar aks uzunluğu", f'{s["wall_length"]:.2f} m'),
        ("Pencere", f'{int(s["window_count"])} adet / {s["window_area"]:.2f} m²'),
        ("Kapı", f'{int(s["door_count"])} adet'),
    ]
    items = []
    for r in cost["rows"]:
        if not r["enabled"] or not r["quantity"]:
            continue
        t = ITEMS.get(r["code"])
        variant = next((v["name"] for v in r["variants"] if v["id"] == r["variant"]), "")
        if t is None:
            t = {"malzeme": "Bu kalem için şartname metni tanımlanmamıştır; idare ile belirlenecektir.",
                 "uygulama": "—", "olcum": "Miktar ve birim üzerinden ödenir."}
        items.append({"code": r["code"], "name": r["name"], "quantity": r["quantity"], "unit": r["unit"],
                      **{k: v.format(variant=variant or "onaylı numuneye uygun") for k, v in t.items()}})
    return {"title": f"{project_name} — Teknik Şartname", "general": GENERAL, "summary": summary,
            "rooms": qres["rooms"], "items": items}
