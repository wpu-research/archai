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
    "GEN-01": {
        "malzeme": "Şantiye ofisi, depo, WC-duş konteynerleri, çevre çiti, tabela ve geçici elektrik ile su bağlantıları.",
        "uygulama": "İdarenin onayladığı şantiye yerleşim planına göre kurulacak; iş bitiminde sökülüp saha eski haline getirilecektir.",
        "olcum": "AVAN yaklaşık: brüt inşaat alanı (m²) üzerinden götürü ödenir.",
    },
    "GEN-02": {
        "malzeme": "6331 sayılı İş Sağlığı ve Güvenliği Kanunu'na uygun kişisel koruyucu donanım, güvenlik ağları, kenar korkulukları, uyarı levhaları, ilk yardım malzemesi.",
        "uygulama": "İSG planına göre uygulanacak; çalışan eğitimleri ve iş güvenliği uzmanı hizmeti sözleşme süresince sürdürülecektir.",
        "olcum": "AVAN yaklaşık: brüt inşaat alanı (m²) üzerinden götürü ödenir.",
    },
    "GEN-03": {
        "malzeme": "Çelik borulu veya modüler cephe iskelesi; korkuluk, ara platform, güvenlik ağı ve bağlantı elemanları dahil.",
        "uygulama": "Zemin taşıma kapasitesi kontrol edilerek kurulacak, cepheye ankrajlanacak, iş sonunda sökülecektir. Kurulum, kira ve söküm birim fiyata dahildir.",
        "olcum": "Dış cephe duvarlarının brüt alanı (aks uzunluğu × yükseklik, m²) üzerinden ödenir.",
    },
    "GEN-04": {
        "malzeme": "Beton küp numune ve basınç deneyleri, donatı çekme/eğme deneyleri, zemin sıkışma deneyleri, kot ve aplikasyon ölçümleri.",
        "uygulama": "Numuneler akredite laboratuvarda deneye tabi tutulacak, raporlar yapı denetim ve idareye verilecektir.",
        "olcum": "AVAN yaklaşık: brüt inşaat alanı (m²) üzerinden götürü ödenir.",
    },
    "GEN-05": {
        "malzeme": "İnşaat all-risk sigortası ve işveren mali sorumluluk sigortası; poliçe bedeli dahil.",
        "uygulama": "Poliçeler iş başlangıcında yapılacak, sözleşme süresince geçerli tutulacaktır.",
        "olcum": "AVAN yaklaşık: brüt inşaat alanı (m²) üzerinden götürü ödenir.",
    },
    "GEN-06": {
        "malzeme": "Moloz konteynerleri, nakliye ve döküm ücretleri; ince temizlik malzemesi ve işçiliği.",
        "uygulama": "Moloz düzenli taşınarak ruhsatlı döküm sahasına atılacak; teslimden önce cam, doğrama ve zeminler dahil tüm mahaller temizlenecektir.",
        "olcum": "AVAN yaklaşık: brüt inşaat alanı (m²) üzerinden götürü ödenir.",
    },
    "HAF-01": {
        "malzeme": "Temel çukuru kazısı, her cins zeminde; kazı fazlası toprağın döküm alanına nakli dahil.",
        "uygulama": "Kazı şevleri ve iksa zemin etüdü raporuna göre yapılacak; temel altı tesviye ve sıkıştırma dahildir.",
        "olcum": "AVAN yaklaşık: bina oturum alanı × (radye kalınlığı + 1,0 m) hacim (m³). Kesin miktar zemin etüdü ve temel projesine göre belirlenir.",
    },
    "HAF-02": {
        "malzeme": "Seçme granüler dolgu malzemesi (temiz, don yapmayan, organik madde içermeyen).",
        "uygulama": "Dolgu 20-30 cm tabakalar halinde serilip optimum nemde sıkıştırılacak, sıkışma deneyi ile kontrol edilecektir.",
        "olcum": "AVAN yaklaşık: bina çevresi × 1,0 m çalışma payı × (radye kalınlığı + 0,5 m) hacim (m³). Kesin miktar temel projesine göre belirlenir.",
    },
    "GRO-01": {
        "malzeme": "C16/20 hazır beton, TS EN 206'ya uygun.",
        "uygulama": "Temel altı hazırlanmış ve sıkıştırılmış zemin üzerine, 10 cm kalınlıkta, kotlarında dökülecektir.",
        "olcum": "AVAN yaklaşık: bina oturum alanı × 0,10 m hacim (m³) üzerinden ödenir.",
    },
    "TEM-03": {
        "malzeme": "Bitümlü polimer esaslı membran (iki kat) veya onaylı eşdeğer sistem; koruma levhası veya koruma betonu.",
        "uygulama": "Grobeton üzerine astar sürülüp membran bindirmeli yapıştırılacak; perde dönüşleri ve köşelerde takviye bandı kullanılacaktır. Yalıtım bindirmeleri tutanakla kontrol edilecektir.",
        "olcum": "AVAN yaklaşık: oturum alanı + bina çevresi × (radye kalınlığı + 0,3 m) alan (m²) üzerinden ödenir.",
    },
    "YAL-03": {
        "malzeme": "TS EN 13164'e uygun ekstrüde polistiren (XPS) levha, 5 cm; TS 825 hesabına göre kalınlık teyit edilecektir.",
        "uygulama": "Levhalar sıkı birleşimli, şaşırtmalı serilecek; üzeri PE örtü ile korunacaktır.",
        "olcum": "Zemin kat oturum alanı (m²) üzerinden ödenir.",
    },
    "DRN-01": {
        "malzeme": "Delikli drenaj borusu, geotekstil filtre kumaşı ve temiz çakıl dolgu.",
        "uygulama": "Boru en az %1 eğimle döşenecek, kontrol rögarlarına ve yağmur suyu hattına bağlanacaktır.",
        "olcum": "AVAN yaklaşık: bina çevresi (m) üzerinden ödenir.",
    },
    "TEM-01": {
        "malzeme": "Radye temel betonu: TS EN 206'ya uygun C30/37 hazır beton, nakliye ve pompa dahil; donatı DON-03'te, kalıp KAL-03'te ayrıca sayılır.",
        "uygulama": "Statik projeye göre; beton vibratörle yerleştirilecek ve en az 7 gün kür edilecektir.",
        "olcum": "AVAN yaklaşık: bina oturum alanı × radye kalınlığı (0,30 + 0,04 × kat adedi m) hacim (m³). Kesin statik ve temel projesi sonrası kesinleşir.",
    },
    "DON-03": {
        "malzeme": "TS 708'e uygun B500C nervürlü inşaat çeliği; kesim, bükme, bağlama ve fire dahil.",
        "uygulama": "Statik projedeki demir listesine göre; pas payları ve bindirme boyları kontrol edilmeden beton dökülmeyecektir.",
        "olcum": "AVAN yaklaşık: radye betonu (m³) × 110 kg/m³ ağırlık (ton). Kesin miktar statik projedeki demir metrajına göre belirlenir.",
    },
    "KAL-03": {
        "malzeme": "Radye kenar kalıbı: plywood veya çelik kalıp, destek ve ankrajlar.",
        "uygulama": "Kalıp kotlarda ve şakülünde kurulup beton sonrası sökülecek; kalıp ayırıcı kullanılacaktır.",
        "olcum": "AVAN yaklaşık: bina çevresi × radye kalınlığı (m²) üzerinden ödenir.",
    },
    "TEM-02": {
        "malzeme": "Tekil beton pabuç + taş/beton ayak; ahşap taban kirişlerine ankraj dahil.",
        "uygulama": "Don derinliğinin altına oturtulacak; ayak üst kotları nivo ile kontrol edilecektir.",
        "olcum": "AVAN yaklaşık: bina oturum alanı (m²) üzerinden götürü. Beton, donatı ve kalıp birim fiyata dahildir; kesin temel projesine göre kesinleşir.",
    },
    "BET-01": {
        "malzeme": "Döşeme betonu: TS EN 206'ya uygun C30/37 hazır beton, nakliye ve pompa dahil; donatı DON-01'de, kalıp KAL-01'de ayrıca sayılır.",
        "uygulama": "Kalıp, donatı ve pas payları projeye ve TS 500'e göre kontrol edilmeden beton dökülmeyecek; beton vibratörle yerleştirilip en az 7 gün kür edilecektir.",
        "olcum": "Döşeme alanı × döşeme kalınlığı ile hacim (m³) olarak hesaplanır.",
    },
    "KOL-01": {
        "malzeme": "Kolon, kiriş ve perde betonu: TS EN 206'ya uygun C30/37 hazır beton, nakliye ve pompa dahil; donatı DON-02'de, kalıp KAL-02'de ayrıca sayılır.",
        "uygulama": "TS 500 ve Türkiye Bina Deprem Yönetmeliği'ne uygun statik projeye göre yapılacaktır.",
        "olcum": "AVAN yaklaşık: betonarme kat döşemesi alanı × 0,12 m³/m² (döşeme betonu BET-01'de ayrıca sayılır). Kesin statik proje sonrası kesinleşir.",
    },
    "DON-01": {
        "malzeme": "TS 708'e uygun B500C nervürlü inşaat çeliği; kesim, bükme, bağlama ve fire dahil.",
        "uygulama": "Statik projedeki demir listesine göre; paspayı ve bindirme boyları kontrol edilmeden beton dökülmeyecektir.",
        "olcum": "AVAN yaklaşık: döşeme betonu (m³) × 85 kg/m³ ağırlık (ton). Kesin miktar statik projedeki demir metrajına göre belirlenir.",
    },
    "DON-02": {
        "malzeme": "TS 708'e uygun B500C nervürlü inşaat çeliği; etriye, kesim, bükme, bağlama ve fire dahil.",
        "uygulama": "Statik projeye ve deprem yönetmeliğindeki sık etriye bölgesi kurallarına uygun yapılacaktır.",
        "olcum": "AVAN yaklaşık: kolon-kiriş-perde betonu (m³) × 140 kg/m³ ağırlık (ton). Kesin miktar statik projedeki demir metrajına göre belirlenir.",
    },
    "KAL-01": {
        "malzeme": "Plywood veya alüminyum döşeme kalıbı, kalıp iskelesi ve ayırıcı yağ.",
        "uygulama": "Kalıp kotlarında ve terazisinde kurulacak, sökme süreleri TS 500'e uyacak; mesnet iskeleleri yeterli rijitlikte olacaktır.",
        "olcum": "Döşeme alt yüzey alanı (m²) üzerinden ödenir; kurulum, söküm ve iskele birim fiyata dahildir.",
    },
    "KAL-02": {
        "malzeme": "Plywood veya çelik kalıp; kolon, kiriş ve perde kalıbı, destek ve ankrajlar.",
        "uygulama": "Kalıplar şakülünde ve ölçüsünde kurulacak; beton sonrası uygun sürede sökülecektir.",
        "olcum": "AVAN yaklaşık: betonarme kat döşemesi alanı × 0,9 m²/m² kalıp yüzeyi (m²). Kesin miktar statik projeye göre belirlenir.",
    },
    "MER-01": {
        "malzeme": "Betonarme merdiven kolu ve sahanlığı; basamak ve rıhtlarda granit/doğal taş kaplama. Korkuluk ve küpeşte KRK-01'de ayrıca sayılır.",
        "uygulama": "Rıht yüksekliği tüm kolda eşit; basamak kaymaz kenarlı olacaktır.",
        "olcum": "Basamak sayısı × kol genişliği (m, basamak uzunluğu) üzerinden; sahanlık birim fiyata dahildir. AVAN yaklaşık, statik projeye göre kesinleşir.",
    },
    "KRK-01": {
        "malzeme": "Çelik veya paslanmaz çelik merdiven korkuluğu ve küpeşte; yükseklik ≥ 100 cm, dikmeler arası boşluk ≤ 10 cm.",
        "uygulama": "Korkuluk betonarmeye ankrajlı monte edilecek, kaynaklar taşlanıp boyanacaktır.",
        "olcum": "Merdiven eğim boyu (basamak sayısı × derinlik ve yükseklikten, m) üzerinden ödenir.",
    },
    "MER-02": {
        "malzeme": "Kurutulmuş masif ahşap limonluk ve basamak; korkuluk ve küpeşte dahil.",
        "uygulama": "Limonluklar döşemeye ankrajlanacak, basamaklar gıcırtı önleyici bağlantıyla monte edilecektir.",
        "olcum": "Basamak sayısı × merdiven genişliği (m) üzerinden ödenir.",
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
    "DUV-04": {
        "malzeme": "Çekirdek ve daire ayırma duvarları: en az 20 cm yatay delikli tuğla / gazbeton; yangın ve ses yalıtım gereklerini sağlayacak.",
        "uygulama": "Duvarlar betonarme elemanlara filiz ile bağlanacak; tesisat geçişleri yangın durdurucu ile kapatılacaktır.",
        "olcum": "İç (dış cepheye bakmayan) ≥20 cm duvarların net alanı (m²), boşluklar düşülerek hesaplanır.",
    },
    "DUV-03": {
        "malzeme": "Masif tomruk (log) duvar: fırınlanmış, nem oranı ≤ %18 iğne yapraklı ağaç; profil ve kalınlık projeye göre. Emprenye ve UV koruyucu yüzey işlemi dahildir.",
        "uygulama": "Tomruklar köşelerde geçmeli (çentikli) birleşim ve kat arası yalıtım bandı ile örülecek; oturma payı bırakılacak, kapı-pencere kasaları kayar profil ile monte edilecektir.",
        "olcum": "Aks uzunluğu × duvar yüksekliğinden boşluklar düşülerek net duvar alanı (m²) üzerinden ödenir.",
    },
    "YAL-01": {
        "malzeme": "TS EN 13163'e uygun EPS veya taş yünü yalıtım levhası; kalınlık TS 825 hesabına göre belirlenecek. Sistemin yapıştırıcısı ve plastik çivili dübelleri aynı üreticiye ait olacaktır.",
        "uygulama": "Levhalar şaşırtmalı yapıştırılıp dübellenecek; pencere çevrelerinde damlalık ve takviye uygulanacak, ilk sıra altında sistem profili kullanılacaktır.",
        "olcum": "Dış duvar net alanı (m²) üzerinden ödenir; pencere söve dönüşleri birim fiyata dahildir.",
    },
    "YAL-04": {
        "malzeme": "Mantolama sistemine ait taban sıvası, alkali dayanımlı donatı filesi, köşe ve damlalık profilleri, astar.",
        "uygulama": "Taban sıvası file gömülerek iki tabakada uygulanacak; köşe ve açıklık dönüşlerine çapraz file takviyesi yapılacaktır.",
        "olcum": "Dış duvar net alanı (m²) üzerinden ödenir.",
    },
    "CEP-01": {
        "malzeme": "Kompozit panel, doğal taş, seramik veya ahşap cephe kaplaması; taşıyıcı alt konstrüksiyon dahil. Seçime göre birim fiyat idarece belirlenir.",
        "uygulama": "Alt konstrüksiyon ankrajlı ve terazide kurulacak; kaplama derzleri ve genleşme payları üretici detayına göre bırakılacaktır.",
        "olcum": "AVAN yaklaşık: dış duvar net alanının %25'i (m²); kapladığı alan kadar YAL-04/SIV-02/BOY-02 miktarı kalem bazında düşülmelidir. Opsiyonel kalemdir.",
    },
    "CAT-03": {
        "malzeme": "Hafif (perlitli/köpük) eğim betonu, ortalama 8 cm; en az %1,5 eğim.",
        "uygulama": "Süzgeç ve dere noktalarına doğru eğim verilecek, üzeri düzeltme şapı ile kapatılacaktır.",
        "olcum": "AVAN yaklaşık: teras çatı alanı × 0,08 m hacim (m³) üzerinden ödenir.",
    },
    "CAT-04": {
        "malzeme": "TS EN 13164'e uygun XPS levha, 8 cm; kalınlık TS 825 hesabına göre teyit edilecektir.",
        "uygulama": "Levhalar su yalıtımı üzerinde sıkı birleşimli serilecek, üzerine ayırıcı tabaka konacaktır.",
        "olcum": "Teras çatı alanı (m²) üzerinden ödenir.",
    },
    "CAT-01": {
        "malzeme": "Bitümlü polimer esaslı membran (iki kat) veya onaylı sıvı yalıtım sistemi kullanılacaktır.",
        "uygulama": "Eğim betonu üzerine astar sürülecek, bindirmeler en az 10 cm yapılacak, parapetlere en az 30 cm dönülecektir. Uygulama sonrası su tutma testi yapılacaktır.",
        "olcum": "Çatı döşeme alanı (m²) üzerinden ödenir; parapet dönüşleri dahildir.",
    },
    "CAT-05": {
        "malzeme": "Su yalıtımı üzerine koruma şapı; üzerine çakıl balast veya dona dayanıklı seramik/beton kaplama.",
        "uygulama": "Koruma şapı derzlenecek; kaplama su tahliyesini engellemeyecek şekilde döşenecektir.",
        "olcum": "Teras çatı alanı (m²) üzerinden ödenir.",
    },
    "CAT-06": {
        "malzeme": "Parapet duvarı, parapet üst kapağı (taş veya alüminyum) ve iç yüz kaplaması.",
        "uygulama": "Parapet yüksekliği ≥ 100 cm (korkuluk yerine geçiyorsa); kapak damlalıklı ve eğimli monte edilecektir.",
        "olcum": "Teras çatı çevresi (m) üzerinden ödenir.",
    },
    "CAT-07": {
        "malzeme": "Galvaniz/PVC yağmur oluğu veya dere, iniş boruları, tutucular ve bağlantı parçaları.",
        "uygulama": "Eğimler süzgeçlere doğru verilecek; iniş boruları kontrol rakorlu ve zemin hattına bağlı olacaktır.",
        "olcum": "Teras çatı çevresi (m) üzerinden ödenir.",
    },
    "CAT-02": {
        "malzeme": "Ahşap makas/mertek sistemi, OSB veya ahşap kaplama, nefes alan su yalıtım örtüsü, çıta ve çatı örtüsü (shingle veya metal); ısı yalıtımı dahildir.",
        "uygulama": "Eğim projeye göre; mahya ve saçak havalandırması bırakılacak, baca ve tesisat geçişlerinde etek/sızdırmazlık yapılacaktır.",
        "olcum": "Eğimli çatı yüzey alanı (m²) üzerinden ödenir; saçak çıkmaları dahildir.",
    },
    "SIV-01": {
        "malzeme": "Çimento/kireç esaslı hazır sıva, TS EN 998-1'e uygun; makine ile uygulanır.",
        "uygulama": "Yüzeyler tozdan arındırılıp ıslatılacak, köşelere köşe profili konacak, kaba ve ince sıva düzgün ve çatlaksız tamamlanacaktır.",
        "olcum": "Mahal çevresi × mahal yüksekliğinden, mahalin yüzündeki kapı ve pencere boşlukları düşülerek duvar yüzeyi (m²) olarak hesaplanır (iç kapı her iki mahalde, pencere ve dış kapı tek yüzde düşülür). Asansör kuyusu ve şaftlar dahil değildir; banyo/WC duvarları dahildir.",
    },
    "ALC-01": {
        "malzeme": "Saten alçı; köşe profili ve file dahil.",
        "uygulama": "Sıva kuruduktan sonra uygulanacak, yüzey zımparalanarak boyaya hazır hale getirilecektir.",
        "olcum": "Banyo/WC hariç mahallerin duvar yüzeyi (m²), SIV-01 yöntemiyle ölçülür.",
    },
    "BOY-01": {
        "malzeme": "Su bazlı, silinebilir iç cephe plastik boyası; astar ve en az iki kat boya.",
        "uygulama": "Yüzeyler tozdan arındırılıp astarlanacak; boya tam örtücü, tek tonda uygulanacaktır.",
        "olcum": "Banyo/WC hariç mahallerin duvar yüzeyi (m²), SIV-01 yöntemiyle ölçülür.",
    },
    "TAV-01": {
        "malzeme": "Tavan sıvası ve saten alçı.",
        "uygulama": "Tavan yüzeyleri düzeltilerek, çatlak ve şap izi bırakmadan uygulanacaktır.",
        "olcum": "Mahal net alanı (m²) üzerinden ödenir.",
    },
    "TAV-02": {
        "malzeme": "Su bazlı tavan boyası, astar ve iki kat; ıslak hacimlerde neme dayanıklı boya.",
        "uygulama": "Tavan yüzeyleri astarlanarak uygulanacaktır.",
        "olcum": "Mahal net alanı (m²) üzerinden ödenir.",
    },
    "TAV-03": {
        "malzeme": "Alçı kartonpiyer veya tavan kornişi; profil onaylı numuneye uygun.",
        "uygulama": "Alçı veya yapıştırıcı ile tavan-duvar birleşimine derzsiz monte edilecek, boya öncesi macunlanacaktır.",
        "olcum": "Daire içi mahallerin (banyo/WC hariç) çevre uzunluğu (m) üzerinden ödenir. Opsiyonel kalemdir.",
    },
    "SIV-02": {
        "malzeme": "Mantolama sisteminin son kat mineral veya dekoratif ince sıvası; sistem üreticisinin ürünü.",
        "uygulama": "Taban sıvası kuruduktan sonra astar sürülüp sistem talimatına uygun tek renkte uygulanacaktır.",
        "olcum": "Dış duvar net alanı (m²) üzerinden ödenir.",
    },
    "BOY-02": {
        "malzeme": "Silikonlu veya akrilik dış cephe boyası; astar ve en az iki kat.",
        "uygulama": "Sistem üreticisinin talimatlarına uygun uygulanacak; iskele hareketinde boya izi bırakılmayacaktır.",
        "olcum": "Dış duvar net alanı (m²) üzerinden ödenir.",
    },
    "SAP-01": {
        "malzeme": "Çimento esaslı şap, TS EN 13813'e uygun, en az 5 cm kalınlıkta.",
        "uygulama": "Kotlar lazerle alınacak, derzler bırakılacak, ıslak hacimlerde süzgece doğru eğim verilecektir.",
        "olcum": "Mahal net alanı (m²) üzerinden ödenir.",
    },
    "SAP-02": {
        "malzeme": "Kat arası darbe ses yalıtımı: PE köpük veya elastikleştirilmiş EPS levha, çevre bandı.",
        "uygulama": "Şap altına kesintisiz serilecek, duvar kenarlarında çevre bandı ile şap ayrılacaktır.",
        "olcum": "Mahal net alanı (m²) üzerinden ödenir.",
    },
    "ZEM-01": {
        "malzeme": "Zemin kaplaması: {variant}. Malzeme numunesi ve renk onayı alınacaktır.",
        "uygulama": "Şap kuruduktan ve nem ölçümü yapıldıktan sonra üretici talimatına göre uygulanacak; seramik/taş kaplamalarda TS EN 12004'e uygun yapıştırıcı kullanılacaktır.",
        "olcum": "Daire içi mahallerin net alanı (m²) üzerinden ödenir; banyo/WC (SER-01), balkon (BAL-01), ortak alanlar (ORT-01), merdiven, asansör kuyusu ve şaftlar dahil değildir. Fire birim fiyata dahildir.",
    },
    "SUP-01": {
        "malzeme": "Zemin kaplamasıyla uyumlu süpürgelik.",
        "uygulama": "Duvara düz ve derzsiz monte edilecek, köşeler gönyesinde kesilecektir.",
        "olcum": "Mahal çevre uzunluğundan kapı genişlikleri düşülerek (m) ödenir; banyo/WC (seramik duvar), merdiven evi, asansör kuyusu ve şaftlar dahil değildir.",
    },
    "SER-03": {
        "malzeme": "Esnek çimento esaslı veya poliüretan sürülebilir su yalıtımı; köşelerde yalıtım bandı.",
        "uygulama": "Zemin ve duvarda 30 cm yüksekliğe dönülecek, süzgeç ve boru geçişleri manşetle sızdırmaz yapılacak; seramikten önce su tutma testi yapılacaktır.",
        "olcum": "Taban alanı + çevre × 0,30 m (m²) üzerinden banyo/WC mahalleri için ödenir.",
    },
    "SER-01": {
        "malzeme": "TS EN 14411'e uygun kaymaz (R10 veya üstü) seramik/porselen karo; uyumlu yapıştırıcı ve derz dolgusu.",
        "uygulama": "Süzgece doğru eğim korunarak döşenecek; derzler su itici dolgu ile kapatılacaktır. Numune ve renk onayı alınacaktır.",
        "olcum": "Banyo/WC net zemin alanı (m²) üzerinden ödenir.",
    },
    "SER-02": {
        "malzeme": "TS EN 14411'e uygun duvar seramiği/porselen; yapıştırıcı, derz dolgusu ve köşe profilleri.",
        "uygulama": "Su yalıtımı üzerinden tavana kadar, çizgi ve kotlarda döşenecek; armatür delikleri temiz kesilecektir.",
        "olcum": "Banyo/WC duvar yüzeyi (SIV-01 yöntemiyle, boşluklar düşülerek, m²) üzerinden ödenir.",
    },
    "SER-04": {
        "malzeme": "Tezgâh arası seramik veya temperli cam panel; yapıştırıcı ve derz dahil.",
        "uygulama": "Tezgâh ile üst dolap arasında, priz ve armatür boşlukları işlenerek uygulanacaktır.",
        "olcum": "AVAN yaklaşık: mutfak başına 3 m² (m²) üzerinden ödenir.",
    },
    "BAL-01": {
        "malzeme": "Dona dayanıklı, kaymaz (R11) seramik veya porselen karo; dış mekân yapıştırıcısı.",
        "uygulama": "Eğim dışa doğru verilecek, su yalıtımı üzerine döşenecek; genleşme derzleri bırakılacaktır.",
        "olcum": "Balkon/teras net alanı (m²) üzerinden ödenir.",
    },
    "BAL-02": {
        "malzeme": "Çelik veya alüminyum balkon korkuluğu, yükseklik ≥ 100 cm, boşluklar ≤ 10 cm; boyalı/eloksal yüzey.",
        "uygulama": "Betonarmeye ankrajla bağlanacak; dikmeler şakülünde, el küpeşte düzgün monte edilecektir.",
        "olcum": "AVAN yaklaşık: balkon çevresinin %60'ı (m) üzerinden ödenir; gerçek korkuluk boyu mimari projeye göre kesinleşir.",
    },
    "ORT-01": {
        "malzeme": "Ortak alan (kat holü, giriş holü) zemin kaplaması: granit veya yüksek aşınma dayanımlı (PEI 5) porselen seramik; kaymazlık sınıfı R10.",
        "uygulama": "Şap üzerine TS EN 12004'e uygun yapıştırıcı ile; asansör ve merdiven eşiklerinde kot farkı bırakılmadan döşenecektir.",
        "olcum": "Ortak mahallerin (merdiven evi ve asansör kuyusu hariç) net alanı (m²) üzerinden ödenir.",
    },
    "MUT-01": {
        "malzeme": "Mutfak alt ve üst dolapları (MDF/lake veya laminat), menteşe ve çekmece donanımı, tezgâh (kompakt laminat veya kuvars).",
        "uygulama": "Dolaplar duvara terazide sabitlenecek, tezgâh derzsiz birleştirilecek, tesisat ve ankastre boşlukları ölçüye göre bırakılacaktır.",
        "olcum": "AVAN yaklaşık: mutfak başına 4,5 m dolap uzunluğu (m) üzerinden ödenir; ankastre cihazlar dahil değildir.",
    },
    "MUT-02": {
        "malzeme": "Paslanmaz çelik eviye, tek kollu batarya, sifon ve bağlantı armatürleri.",
        "uygulama": "Tezgâha sızdırmaz monte edilecek; su ve gider bağlantıları basınç testinden geçecektir.",
        "olcum": "Adet olarak ödenir.",
    },
    "VIT-01": {
        "malzeme": "Banyo takımı: klozet, lavabo ve dolap, duşakabin veya küvet, bataryalar, ayna ve aksesuarlar; TS EN 997, TS EN 31 ve ilgili standartlara uygun, onaylı numune.",
        "uygulama": "Cihazlar su yalıtımı ve seramik tamamlandıktan sonra, ölçülerinde ve terazide monte edilecek; bağlantılar sızdırmazlık testinden geçirilecektir.",
        "olcum": "Banyo mahalli başına takım olarak ödenir.",
    },
    "VIT-02": {
        "malzeme": "WC / lavabo takımı: klozet, lavabo, batarya ve aksesuar; onaylı numune.",
        "uygulama": "Cihazlar seramik sonrası terazide monte edilecek, bağlantılar sızdırmazlık testinden geçirilecektir.",
        "olcum": "WC mahalli başına takım olarak ödenir.",
    },
    "PEN-01": {
        "malzeme": "Pencere doğraması: {variant}. Doğrama TS EN 14351-1'e uygun, projedeki ısıl geçirgenlik değerini (TS 825) sağlayacaktır; hırdavat ve montaj dahildir.",
        "uygulama": "Doğramalar ankrajla tespit edilecek, kasa-duvar birleşimi yalıtım bantları ile sızdırmaz yapılacaktır.",
        "olcum": "Pencere boşluk alanı (genişlik × yükseklik, m²) üzerinden ödenir; cam PEN-03'te ayrıca sayılır.",
    },
    "PEN-03": {
        "malzeme": "Yalıtım camı: {variant}; TS EN 1279'a uygun, camlar temperli/lamine gereken yerlerde güvenlik camı.",
        "uygulama": "Camlar uygun takoz ve contalarla yerleştirilecek, çıta ve conta eksiksiz montajlanacaktır.",
        "olcum": "AVAN yaklaşık: pencere boşluk alanının %85'i (cam alanı, m²) üzerinden ödenir.",
    },
    "PEN-02": {
        "malzeme": "Doğal taş veya kompozit denizlik, dış cephede damlalıklı.",
        "uygulama": "Dışa doğru eğimli ve derzleri sızdırmaz şekilde monte edilecektir.",
        "olcum": "Pencere genişliği toplamı (m) üzerinden ödenir.",
    },
    "PEN-04": {
        "malzeme": "PVC veya alüminyum panjur/kepenk, kutu, kasa ve kumanda; motorlu seçenek idare onayıyla.",
        "uygulama": "Kutu cepheye ısı köprüsü yaratmayacak şekilde yerleştirilecek, bağlantılar sızdırmaz olacaktır.",
        "olcum": "Pencere boşluk alanı (m²) üzerinden ödenir. Opsiyonel kalemdir.",
    },
    "KAP-01": {
        "malzeme": "İç kapı: kasa, pervaz, kanat, kilit, menteşe ve kollar dahil; onaylı numuneye uygun (lake/laminat kaplı).",
        "uygulama": "Kasalar terazisinde ve şakülünde montajlanacak, kanat boşlukları eşit bırakılacaktır.",
        "olcum": "Adet olarak ödenir; ≥20 cm duvardaki kapılar KAP-02'de, dış kapılar KAP-03'te sayılır.",
    },
    "KAP-02": {
        "malzeme": "Çelik kapı: TS EN 14351-1; ≥1,5 mm sac, çok noktalı kilit, kasa ve kaplama; yangın/ses yalıtım değerleri projeye göre.",
        "uygulama": "Çelik kasa duvara ankrajla sabitlenecek, kanat boşlukları eşit ve kapı serbest çalışır halde teslim edilecektir.",
        "olcum": "Adet olarak ödenir; ≥20 cm iç duvarlardaki kapılar (daire / çekirdek girişleri) için.",
    },
    "KAP-03": {
        "malzeme": "Bina dış kapısı: alüminyum-cam veya çelik; kasa, kanat, kilit ve kapı kolu dahil.",
        "uygulama": "Kasa sızdırmaz ve ısı köprüsüz monte edilecek, otomatik kapatıcı ve eşik ile tamamlanacaktır.",
        "olcum": "Adet olarak ödenir.",
    },
    "KAP-04": {
        "malzeme": "Mermer veya granit kapı eşiği; kaymaz yüzey, onaylı numune.",
        "uygulama": "Zeminle ve duvarla düz, kot farksız yerleştirilecek, yapıştırıcı ve derz dahildir.",
        "olcum": "Kapı genişlikleri toplamı (m) üzerinden ödenir.",
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
    "CEV-01": {
        "malzeme": "Bahçe duvarı (briket/betonarme) ve üzerine demir çit/panel; araç ve yaya kapıları dahil.",
        "uygulama": "Temelli yapılacak, duvar sıvalı ve boyalı, çitler paslanmaza karşı boyalı/galvaniz olacaktır.",
        "olcum": "Parsel çevresi (m) üzerinden ödenir; opsiyonel kalemdir, gerçek uzunluk imar durumuna göre kesinleşir.",
    },
    "CEV-02": {
        "malzeme": "Bitkisel toprak, çim veya bitki örtüsü, ağaç ve çalılar, damlama sulama sistemi.",
        "uygulama": "Toprak en az 30 cm kalınlıkta serilecek, sulama hatları döşenip basınç testi yapılacak, bitkiler tutana kadar bakım yapılacaktır.",
        "olcum": "AVAN yaklaşık: parsel alanı − bina oturum alanı − kaplama alanı (m²) üzerinden ödenir.",
    },
    "SIH-01": {
        "malzeme": "PPR temiz su ve PVC/polipropilen pis su boruları, vana ve bağlantı parçaları; sayaç ve bağlantı parçaları. Vitrifiye VIT kalemlerinde ayrıca sayılır. TS EN 806 ve TS EN 12056 esas alınır.",
        "uygulama": "Mekanik projeye göre; basınç testi ve sızdırmazlık tutanakla teslim edilecektir.",
        "olcum": "Banyo, WC ve mutfak mahalli başına adet olarak ödenir.",
    },
    "SIH-02": {
        "malzeme": "Hidrofor grubu, su deposu, bina ana kolon boruları ve vanaları.",
        "uygulama": "Hidrofor titreşimden yalıtımlı bağlanacak, kolonlar bağlantı testlerinden geçirilecektir.",
        "olcum": "AVAN yaklaşık: bina başına bir takım (adet) üzerinden götürü ödenir; kapasite mekanik projeye göre kesinleşir.",
    },
    "ISI-01": {
        "malzeme": "Isıtma tesisatı: {variant}; boru, kolektör, vana, termostat ve ısıtıcılar dahil.",
        "uygulama": "Onaylı mekanik projeye göre yapılacak, boru hatları basınç ve sızdırmazlık testinden geçirilecektir.",
        "olcum": "Isıtılan daire içi mahallerin net alanı (m²) üzerinden ödenir; ortak alanlar hariçtir.",
    },
    "ISI-02": {
        "malzeme": "Yoğuşmalı kombi, baca bağlantısı ve montaj; CE belgeli.",
        "uygulama": "Kombi ve bacası üretici talimatı ve gaz dağıtım şirketi şartnamesine uygun monte edilecektir.",
        "olcum": "Konut birimi başına adet olarak ödenir.",
    },
    "DOG-01": {
        "malzeme": "Doğalgaz iç tesisat boruları, vana, sayaç yeri, kolon hattı; gaz dağıtım şirketi şartnamesine uygun malzeme.",
        "uygulama": "Tesisat projeye göre yapılacak, şirket gözetiminde basınç testinden geçirilip gaza açılacaktır.",
        "olcum": "Konut birimi başına adet olarak ödenir.",
    },
    "HVA-01": {
        "malzeme": "Banyo/WC/mutfak havalandırma fanı, galvaniz veya PVC kanal, menfez; şaft bağlantıları dahil.",
        "uygulama": "Kanallar eğimli ve yoğuşma suyu geri dönmeyecek şekilde döşenecek, fan çıkışları dışarıya açılacaktır.",
        "olcum": "Banyo, WC ve mutfak mahalli başına adet olarak ödenir.",
    },
    "ELK-01": {
        "malzeme": "Kuvvetli akım iç tesisatı: kablo (halojensiz), boru, buat, kanal ve montaj; TS HD 60364'e uygun.",
        "uygulama": "Onaylı elektrik projesine uygun yapılacak, yalıtım ve süreklilik ölçümleri raporlanacaktır.",
        "olcum": "Brüt inşaat alanı (m²) üzerinden ödenir.",
    },
    "ELK-02": {
        "malzeme": "Anahtar, priz, ışıklık ve armatür bağlantı elemanları; standart seri, onaylı numune.",
        "uygulama": "Elemanlar terazisinde ve çerçeveleri duvarla bütün montajlanacak, her devre etiketlenecektir.",
        "olcum": "Brüt inşaat alanı (m²) üzerinden ödenir.",
    },
    "ELK-03": {
        "malzeme": "Daire / kat sigorta panosu: kaçak akım rölesi, otomatik sigortalar, pano kutusu.",
        "uygulama": "Pano şeması projeye uygun, devreler etiketli ve ölçüm raporu ile teslim edilecektir.",
        "olcum": "Konut birimi başına adet olarak ödenir.",
    },
    "ELK-04": {
        "malzeme": "TV/uydu, data/telefon kabloları ve prizleri, görüntülü diyafon ünitesi ve zili.",
        "uygulama": "Kablolar elektrik hatlarından ayrı güzergâhta çekilecek, sinyal ölçümü yapılacaktır.",
        "olcum": "Konut birimi başına adet olarak ödenir.",
    },
    "ELK-05": {
        "malzeme": "Ana dağıtım panosu, sayaç panoları, bina kolon hattı ve kablo kanalı.",
        "uygulama": "Elektrik dağıtım şirketi şartnamesi ve onaylı projeye göre yapılacak, devreye alma ölçümleri yapılacaktır.",
        "olcum": "AVAN yaklaşık: bina başına götürü adet; kapasite elektrik projesine göre kesinleşir.",
    },
    "ELK-06": {
        "malzeme": "Temel topraklaması (galvaniz şerit/bakır), paratoner ve inme iletkenleri; TS EN 62305 esas alınır.",
        "uygulama": "Topraklama direnci ölçülüp ≤ 5 Ω olduğu raporlanacaktır; bağlantılar korozyona karşı korunacaktır.",
        "olcum": "Bina oturum alanı (m²) üzerinden ödenir.",
    },
    "YAN-01": {
        "malzeme": "Yangın algılama ve ihbar, acil aydınlatma, yönlendirme levhaları, el tipi söndürücüler ve gerekiyorsa yangın dolabı; Binaların Yangından Korunması Hakkında Yönetmelik esas alınır.",
        "uygulama": "Cihazlar yangın projesine göre yerleştirilecek, devreye alma ve fonksiyon testleri tutanakla teslim edilecektir.",
        "olcum": "Ortak alan (kat holü ve merdiven evi) net alanı (m²) üzerinden ödenir.",
    },
    "ASN-01": {
        "malzeme": "Elektrikli asansör (TS EN 81-20/50), kabin, makine, ray, kumanda ve kat kapıları; ilk periyodik kontrol dahil.",
        "uygulama": "Asansör Yönetmeliği'ne uygun; kuyu ölçüleri ve makine yeri üretici projesine göre.",
        "olcum": "AVAN yaklaşık: durak (kat) başına adet. Kesin bedel kabin kapasitesi ve üretici teklifine göre belirlenir.",
    },
    "HIZ-01": {
        "malzeme": "Zemin etüdü: sondaj, laboratuvar deneyleri ve jeolojik-jeoteknik rapor (akredite kuruluş).",
        "uygulama": "Rapor temel projesinin dayanağı olacak, yapı denetim onayına sunulacaktır.",
        "olcum": "Götürü ödenir; kapsam teklif dışıdır (varsayılan kapalı).",
    },
    "HIZ-02": {
        "malzeme": "Mimari, statik, mekanik ve elektrik uygulama projeleri; yetkili mimar ve mühendis imzalı.",
        "uygulama": "Projeler ruhsat ve uygulama aşamalarına uygun hazırlanacaktır.",
        "olcum": "AVAN yaklaşık: brüt inşaat alanı (m²) üzerinden; teklif dışıdır (varsayılan kapalı).",
    },
    "HIZ-03": {
        "malzeme": "Yapı denetim kuruluşu hizmet bedeli.",
        "uygulama": "Denetim hizmeti yürürlükteki yapı denetimi mevzuatına göre sürdürülecektir.",
        "olcum": "AVAN yaklaşık: brüt inşaat alanı (m²) üzerinden; teklif dışıdır (varsayılan kapalı).",
    },
    "HIZ-04": {
        "malzeme": "Ruhsat harcı, iskân, katılım payı ve diğer belediye bedelleri.",
        "uygulama": "Belediye tarifelerine göre idare tarafından ödenecektir.",
        "olcum": "AVAN yaklaşık: brüt inşaat alanı (m²) üzerinden; teklif dışıdır (varsayılan kapalı).",
    },
    "HIZ-05": {
        "malzeme": "Elektrik, su, doğalgaz ve kanal abonelik, bağlantı ve katılım bedelleri.",
        "uygulama": "İdare tarafından ilgili kurumlara ödenecektir.",
        "olcum": "AVAN yaklaşık: konut birimi başına adet; teklif dışıdır (varsayılan kapalı).",
    },
    "HIZ-06": {
        "malzeme": "Beyaz eşya, ankastre set, mobilya ve dekorasyon.",
        "uygulama": "Mal sahibi tarafından ayrıca temin edilir.",
        "olcum": "AVAN yaklaşık: konut birimi başına adet; teklif dışıdır (varsayılan kapalı).",
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
