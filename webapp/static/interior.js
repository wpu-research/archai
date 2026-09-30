// İç mekân: gerçekçi render (PBR + HDRI + gölge + AO) ve düzenleyici (zemin kaplaması, boya, nesne yerleştirme).
// Varlıklar Poly Haven CC0 (assets/LICENSES.json); vitrifiye/mutfak/yatak parametrik üretilir.
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RGBELoader} from 'three/addons/loaders/RGBELoader.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';
import {GTAOPass} from 'three/addons/postprocessing/GTAOPass.js';

export function createInterior(ctx) {
  // innerHTML'e giren kayıt kaynaklı değerler için HTML kaçışı (XSS)
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const {THREE, V, $, $$, n2, api, getProject, toWorld, polyArea, centroid, inPoly, isWalking} = ctx;
  const A = 'assets/';
  const texLoader = new THREE.TextureLoader(), gltf = new GLTFLoader();

  // ------------------------------------------------------------------ katalog
  const FLOORS = [
    {id: 'laminate_floor_02', name: 'Laminat parke', tile: 2.0},
    {id: 'herringbone_parquet', name: 'Balıksırtı parke', tile: 1.6},
    {id: 'oak_wood_planks', name: 'Meşe masif', tile: 2.2},
    {id: 'weathered_planks', name: 'Eskimiş çam (deck)', tile: 2.4},
    {id: 'rough_wood', name: 'Ham tomruk', tile: 1.6},
    {id: 'wood_floor', name: 'Koyu ahşap', tile: 2.0},
    {id: 'marble_tiles', name: 'Mermer', tile: 1.8},
    {id: 'large_grey_tiles', name: 'Porselen 60×60', tile: 2.4},
    {id: 'terrazzo_tiles', name: 'Terrazzo', tile: 1.5},
    {id: 'long_white_tiles', name: 'Beyaz seramik', tile: 1.2},
  ];
  const PAINTS = [
    {id: 'kirik_beyaz', name: 'Kırık beyaz', c: 0xf1ede4}, {id: 'saf_beyaz', name: 'Saf beyaz', c: 0xfafafa},
    {id: 'bej', name: 'Kum beji', c: 0xe3d5bf}, {id: 'acik_gri', name: 'Açık gri', c: 0xd5d7d8},
    {id: 'adacayi', name: 'Adaçayı', c: 0xb9c4ae}, {id: 'gok', name: 'Buz mavisi', c: 0xc9d8e2},
    {id: 'terakota', name: 'Terakota', c: 0xd29b7f}, {id: 'antrasit', name: 'Antrasit', c: 0x55595e},
  ];
  const ITEMS = [
    {id: 'klozet', name: 'Klozet', cat: 'Banyo'}, {id: 'lavabo', name: 'Lavabo + ayna', cat: 'Banyo'},
    {id: 'dus', name: 'Duş kabini', cat: 'Banyo'}, {id: 'kuvet', name: 'Küvet', cat: 'Banyo'}, {id: 'havlu', name: 'Havlu askısı', cat: 'Banyo'},
    {id: 'mutfak', name: 'Mutfak tezgâhı 2,4 m', cat: 'Mutfak'}, {id: 'ada', name: 'Mutfak adası', cat: 'Mutfak'},
    {id: 'buzdolabi', name: 'Buzdolabı', cat: 'Mutfak'}, {id: 'bar_taburesi', name: 'Bar taburesi', cat: 'Mutfak'},
    {id: 'kanepe_l', name: 'L koltuk', cat: 'Salon'}, {id: 'kanepe', name: '3\'lü kanepe', cat: 'Salon'},
    {id: 'kanepe_2li', name: '2\'li kanepe', cat: 'Salon'}, {id: 'sehpa_yuvarlak', name: 'Yuvarlak sehpa', cat: 'Salon'},
    {id: 'modern_arm_chair_01', name: 'Berjer', cat: 'Salon', model: true}, {id: 'mid_century_lounge_chair', name: 'Tasarım koltuk', cat: 'Salon', model: true},
    {id: 'modern_coffee_table_01', name: 'Orta sehpa', cat: 'Salon', model: true}, {id: 'tv_unitesi', name: 'TV ünitesi', cat: 'Salon'},
    {id: 'tv', name: 'Duvar TV 65"', cat: 'Salon'}, {id: 'hali', name: 'Halı', cat: 'Salon'}, {id: 'tablo', name: 'Tablo', cat: 'Salon'},
    {id: 'yemek_masasi', name: 'Yemek masası', cat: 'Salon'}, {id: 'sandalye', name: 'Yemek sandalyesi', cat: 'Salon'},
    {id: 'dining_chair_02', name: 'Deri sandalye', cat: 'Salon', model: true}, {id: 'Ottoman_01', name: 'Puf', cat: 'Salon', model: true},
    {id: 'potted_plant_02', name: 'Saksı bitkisi', cat: 'Salon', model: true}, {id: 'potted_plant_04', name: 'Büyük bitki', cat: 'Salon', model: true},
    {id: 'yatak_cift', name: 'Çift kişilik yatak', cat: 'Yatak odası'}, {id: 'yatak_tek', name: 'Tek kişilik yatak', cat: 'Yatak odası'},
    {id: 'gardirop', name: 'Gardırop', cat: 'Yatak odası'}, {id: 'side_table_01', name: 'Komodin', cat: 'Yatak odası', model: true},
    {id: 'komodin', name: 'Komodin + abajur', cat: 'Yatak odası'}, {id: 'yatak_ortusu', name: 'Yatak örtüsü', cat: 'Yatak odası'},
    {id: 'calisma_masasi', name: 'Çalışma masası', cat: 'Çalışma'}, {id: 'kitaplik', name: 'Kitaplık', cat: 'Çalışma'},
    {id: 'sezlong', name: 'Şezlong', cat: 'Dış mekân'}, {id: 'outdoor_table_chair_set_01', name: 'Bahçe masa takımı', cat: 'Dış mekân', model: true},
  ];
  const ICON = {klozet: '🚽', lavabo: '🪞', dus: '🚿', kuvet: '🛁', mutfak: '🍳', ada: '🔲', buzdolabi: '🧊', bar_taburesi: '🪑', kanepe_l: '🛋',
    kanepe: '🛋', tv_unitesi: '▭', tv: '📺', hali: '▦', yemek_masasi: '🍽', sandalye: '🪑', yatak_cift: '🛏', yatak_tek: '🛏', gardirop: '🚪', kanepe_2li: '🛋', sehpa_yuvarlak: '◯', komodin: '💡', yatak_ortusu: '▬', tablo: '🖼', havlu: '🧺',
    calisma_masasi: '🖥', kitaplik: '📚', sezlong: '⛱'};

  // ------------------------------------------------------------------ malzemeler
  const texCache = {};
  function floorMat(id) {
    if (texCache[id]) return texCache[id];
    const f = FLOORS.find(x => x.id === id) || FLOORS[0];
    const load = (k, srgb) => {
      const t = texLoader.load(`${A}tex/${f.id}/${k}.jpg`);
      t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(1 / f.tile, 1 / f.tile);
      t.anisotropy = 8; if (srgb) t.colorSpace = THREE.SRGBColorSpace; return t;
    };
    const fm = new THREE.MeshStandardMaterial({map: load('diff', true), normalMap: load('nor_gl'), roughnessMap: load('rough'),
      roughness: 1, normalScale: new THREE.Vector2(.6, .6)});
    fm.name = 'archai_floor_' + f.id;
    return texCache[id] = fm;
  }
  const plaster = (() => {
    const t = k => { const x = texLoader.load(`${A}tex/painted_plaster_wall/${k}.jpg`); x.wrapS = x.wrapT = THREE.RepeatWrapping; return x; };
    // renk tamamen boyadan gelir; doku yalnız sıva pürüzü (normal harita) olarak
    return new THREE.MeshStandardMaterial({color: 0xf1ede4, normalMap: t('nor_gl'), roughness: .9, normalScale: new THREE.Vector2(.35, .35)});
  })();
  const M = {
    ceramic: new THREE.MeshPhysicalMaterial({color: 0xffffff, roughness: .07, clearcoat: 1, clearcoatRoughness: .04}),
    chrome: new THREE.MeshStandardMaterial({color: 0xf2f2f2, metalness: 1, roughness: .1}),
    lacquer: new THREE.MeshStandardMaterial({color: 0xf0eee9, roughness: .32}),
    anth: new THREE.MeshStandardMaterial({color: 0x3b3f45, roughness: .45}),
    oak: new THREE.MeshStandardMaterial({color: 0xc49a6c, roughness: .55}),
    quartz: new THREE.MeshPhysicalMaterial({color: 0xe7e4de, roughness: .18, clearcoat: .6}),
    steel: new THREE.MeshStandardMaterial({color: 0xc9cdd1, metalness: .85, roughness: .28}),
    black: new THREE.MeshStandardMaterial({color: 0x151618, roughness: .25, metalness: .2}),
    linen: new THREE.MeshStandardMaterial({color: 0xefebe3, roughness: .95}),
    fabric: new THREE.MeshStandardMaterial({color: 0x7d858f, roughness: .95}),
    duvet: new THREE.MeshStandardMaterial({color: 0x51637a, roughness: .9}),
    glass: new THREE.MeshPhysicalMaterial({color: 0xe8f4f8, roughness: .03, metalness: 0, transparent: true, opacity: .18, side: THREE.DoubleSide, depthWrite: false}),
    mirror: new THREE.MeshStandardMaterial({color: 0xffffff, metalness: 1, roughness: .02}),
    frame: new THREE.MeshStandardMaterial({color: 0x2e3135, metalness: .6, roughness: .35}),
    ceiling: new THREE.MeshStandardMaterial({color: 0xf7f6f3, roughness: .95}),
    metal: new THREE.MeshStandardMaterial({color: 0x1f2022, metalness: .6, roughness: .4}),
    sofa: new THREE.MeshStandardMaterial({color: 0x9a968f, roughness: .96}),
    cushion: new THREE.MeshStandardMaterial({color: 0xb8b2a7, roughness: .97}),
    rug: new THREE.MeshStandardMaterial({color: 0xcdbfa6, roughness: 1}),
    screen: new THREE.MeshPhysicalMaterial({color: 0x050608, roughness: .08, clearcoat: 1}),
    books: [0x7a4b3a, 0x2f4a5e, 0xb89b5e, 0x5d6b52, 0x8c2f2f, 0xd6cfc2].map(c => new THREE.MeshStandardMaterial({color: c, roughness: .8})),
    ground: new THREE.MeshStandardMaterial({color: 0x6f7a5c, roughness: 1}),
    water: new THREE.MeshPhysicalMaterial({color: 0x2f9fc0, roughness: .04, clearcoat: 1, transparent: true, opacity: .9, emissive: 0x0b4a5c, emissiveIntensity: .35}),
    roof: new THREE.MeshStandardMaterial({color: 0xb9b6b0, roughness: .95}),
    shingle: new THREE.MeshStandardMaterial({color: 0x4e4239, roughness: .95}),
    stone: new THREE.MeshStandardMaterial({color: 0x8c877d, roughness: .95}),
    bark: new THREE.MeshStandardMaterial({color: 0x5a4636, roughness: 1}),
    leaves: [0x4f6b3a, 0x5d7a43, 0x445f33].map(c => new THREE.MeshStandardMaterial({color: c, roughness: .9, flatShading: true})),
    paving: new THREE.MeshStandardMaterial({color: 0xb5b0a6, roughness: .9}),
  };
  for (const [k, m] of Object.entries(M)) if (m.isMaterial) m.name = 'archai_' + k;  // Cycles tarafı adla tanır
  plaster.name = 'archai_plaster';
  const oakTex = texLoader.load(`${A}tex/oak_wood_planks/diff.jpg`); oakTex.colorSpace = THREE.SRGBColorSpace;
  oakTex.wrapS = oakTex.wrapT = THREE.RepeatWrapping; M.oak.map = oakTex; M.oak.color.set(0xffffff);
  // tomruk ev ahşabı: UV'leri metre cinsinden ölçeklenmiş kirişler/tomruklar için doku tekrarı 1 birim = 1 m
  const timberTex = (id, k, srgb) => { const t = texLoader.load(`${A}tex/${id}/${k}.jpg`); t.wrapS = t.wrapT = THREE.RepeatWrapping; if (srgb) t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; };
  M.log = new THREE.MeshStandardMaterial({map: timberTex('rough_wood', 'diff', true), normalMap: timberTex('rough_wood', 'nor_gl'), roughnessMap: timberTex('rough_wood', 'rough'), roughness: 1, color: 0xd9c4a6});
  M.timber = new THREE.MeshStandardMaterial({map: timberTex('weathered_planks', 'diff', true), normalMap: timberTex('weathered_planks', 'nor_gl'), roughnessMap: timberTex('weathered_planks', 'rough'), roughness: 1});
  M.concrete = new THREE.MeshStandardMaterial({color: 0x9d9a94, roughness: .95});
  M.log.name = 'archai_log'; M.timber.name = 'archai_timber'; M.concrete.name = 'archai_concrete';

  // ------------------------------------------------------------------ parametrik nesneler (yerel: taban merkezde, +z ön)
  const G = () => new THREE.Group();
  function part(g, geo, mat, x, y, z, sx = 1, sy = 1, sz = 1) {
    const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.scale.set(sx, sy, sz); m.castShadow = m.receiveShadow = true; g.add(m); return m;
  }
  const rb = (w, h, d, r = .02) => new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2 - 1e-3, h / 2 - 1e-3, d / 2 - 1e-3));
  const bx = (w, h, d) => new THREE.BoxGeometry(w, h, d);
  const cyl = (r1, r2, h, n = 32) => new THREE.CylinderGeometry(r1, r2, h, n);
  const FACTORY = {
    klozet() {
      const g = G();
      part(g, cyl(.15, .19, .38), M.ceramic, 0, .19, .06, 1, 1, 1.35);
      part(g, cyl(.19, .17, .07), M.ceramic, 0, .41, .08, 1, 1, 1.45);
      part(g, cyl(.19, .19, .025), M.lacquer, 0, .457, .08, 1, 1, 1.45);
      part(g, rb(.38, .38, .17, .03), M.ceramic, 0, .62, -.2);
      part(g, cyl(.035, .035, .012), M.chrome, 0, .815, -.2);
      return g;
    },
    lavabo() {
      const g = G();
      part(g, rb(.8, .45, .46, .015), M.oak, 0, .58, -.02);
      part(g, rb(.82, .04, .48, .01), M.quartz, 0, .82, -.02);
      part(g, cyl(.2, .15, .13), M.ceramic, 0, .905, 0, 1, 1, .78);
      part(g, cyl(.012, .012, .22, 12), M.chrome, 0, .95, -.19);
      part(g, cyl(.01, .01, .13, 12), M.chrome, 0, 1.05, -.13).rotation.x = Math.PI / 2;
      part(g, bx(.72, .82, .015), M.mirror, 0, 1.55, -.235);
      part(g, bx(.76, .86, .01), M.frame, 0, 1.55, -.243);
      return g;
    },
    dus(o = {}) {
      const g = G(), W = o.w ?? .9, D = o.d ?? .9, sd = o.side ?? 1, hx = -sd * (W / 2 - .1);
      part(g, rb(W, .05, D, .01), M.ceramic, 0, .025, 0);
      part(g, bx(W, 1.95, .008), M.glass, 0, 1.03, D / 2 - .005);
      part(g, bx(.008, 1.95, D), M.glass, sd * (W / 2 - .005), 1.03, 0);
      part(g, bx(W, .02, .02), M.chrome, 0, 2.0, D / 2 - .005);
      part(g, bx(.02, .02, D), M.chrome, sd * (W / 2 - .005), 2.0, 0);
      part(g, cyl(.012, .012, 1.1, 12), M.chrome, hx, 1.5, -(D / 2 - .02));
      part(g, cyl(.11, .11, .015), M.chrome, hx, 2.02, -(D / 2 - .13));
      part(g, bx(.02, .2, .02), M.chrome, hx, 2.03, -(D / 2 - .07)).rotation.x = Math.PI / 2;
      return g;
    },
    kuvet() {
      const g = G(), L = 1.7, W = .75, H = .56, t = .07;
      part(g, rb(L, .08, W, .02), M.ceramic, 0, .04, 0);
      part(g, rb(L, H, t, .03), M.ceramic, 0, H / 2, (W - t) / 2);
      part(g, rb(L, H, t, .03), M.ceramic, 0, H / 2, -(W - t) / 2);
      part(g, rb(t, H, W, .03), M.ceramic, (L - t) / 2, H / 2, 0);
      part(g, rb(t, H, W, .03), M.ceramic, -(L - t) / 2, H / 2, 0);
      part(g, cyl(.015, .015, .18, 12), M.chrome, -.72, H + .05, -.2);
      return g;
    },
    mutfak(o = {}) {
      const g = G(), L = o.w ?? 2.4, D = o.d ?? .6, n = Math.max(1, Math.round(L / .6)), m = L / n;
      const ev = o.evye ?? -.3, oc = o.ocak ?? .6;
      part(g, bx(L, .1, D - .06), M.black, 0, .05, -.03);
      for (let i = 0; i < n; i++) {
        const x = -L / 2 + m / 2 + i * m;
        part(g, bx(m, .72, D - .02), M.lacquer, x, .46, -.01);
        part(g, bx(m - .006, .7, .02), M.lacquer, x, .47, D / 2 - .01);
        part(g, bx(.4, .015, .015), M.steel, x, .79, D / 2 + .01);
        part(g, bx(m, .7, .35), M.lacquer, x, 1.85, -D / 2 + .175);
        part(g, bx(m - .006, .68, .02), M.lacquer, x, 1.85, -D / 2 + .36);
        part(g, bx(.015, .3, .015), M.steel, x + m / 2 - .05, 1.62, -D / 2 + .375);
      }
      part(g, bx(L + .02, .04, D + .02), M.quartz, 0, .86, 0);
      part(g, bx(.5, .005, .4), M.steel, ev, .882, .02);
      part(g, bx(.44, .004, .34), M.black, ev, .885, .02);
      if (o.suluk) part(g, bx(.45, .006, .4), M.steel, ev + Math.sign(o.suluk) * .48, .883, .02);  // damlalık
      part(g, cyl(.012, .012, .3, 12), M.chrome, ev, 1.03, -D / 2 + .08);
      part(g, bx(.58, .008, .5), M.black, oc, .884, .02);
      part(g, bx(.56, .44, .012), M.black, oc, .52, D / 2 + .006);                               // ankastre fırın camı
      part(g, bx(.44, .014, .014), M.steel, oc, .78, D / 2 + .02);
      part(g, bx(.6, .1, .34), M.steel, oc, 1.45, -D / 2 + .19);                                  // davlumbaz
      for (const [dx, dz] of [[-.14, -.12], [.14, -.12], [-.14, .14], [.14, .14]]) part(g, cyl(.08, .08, .004, 24), M.steel, oc + dx, .89, .02 + dz);
      part(g, bx(L, .6, .01), M.quartz, 0, 1.18, -D / 2 + .005);
      return g;
    },
    buzdolabi() {
      const g = G();
      part(g, rb(.7, 1.9, .68, .02), M.steel, 0, .95, 0);
      part(g, bx(.702, .006, .02), M.black, 0, 1.25, .34);
      part(g, bx(.02, .5, .03), M.chrome, .3, 1.55, .36);
      part(g, bx(.02, .4, .03), M.chrome, .3, .95, .36);
      return g;
    },
    kanepe_l() {
      const g = G(), W = 2.9;
      part(g, rb(W, .38, .95, .04), M.sofa, 0, .27, 0);
      part(g, rb(.95, .38, .9, .04), M.sofa, W / 2 - .475, .27, .92);
      for (const x of [-W / 2 + .5, -W / 2 + 1.4, -W / 2 + 2.3]) part(g, rb(.88, .14, .82, .06), M.cushion, x + .05, .52, .04);
      part(g, rb(.88, .14, .88, .06), M.cushion, W / 2 - .475, .52, .92);
      part(g, rb(W, .45, .2, .06), M.sofa, 0, .66, -.38);
      part(g, rb(.2, .3, .95, .05), M.sofa, -W / 2 + .1, .55, 0);
      for (const x of [-W / 2 + .7, 0, W / 2 - .9]) part(g, rb(.55, .42, .14, .06), M.cushion, x, .78, -.25).rotation.x = -.18;
      for (const [x, z] of [[-W / 2 + .08, -.4], [W / 2 - .08, -.4], [-W / 2 + .08, .4], [W / 2 - .08, 1.3]]) part(g, bx(.05, .08, .05), M.metal, x, .04, z);
      return g;
    },
    kanepe(o = {}) {
      const g = G(), W = o.w ?? 2.3, n = W >= 2.2 ? 3 : 2, st = (W - .14) / n;
      part(g, rb(W, .38, .92, .04), M.sofa, 0, .27, 0);
      for (let i = 0; i < n; i++) part(g, rb(st - .02, .14, .8, .06), M.cushion, (i - (n - 1) / 2) * st, .52, .05);
      part(g, rb(W, .45, .2, .06), M.sofa, 0, .66, -.36);
      for (const x of [-W / 2 + .1, W / 2 - .1]) part(g, rb(.2, .3, .92, .05), M.sofa, x, .55, 0);
      for (const [x, z] of [[-1, -.38], [1, -.38], [-1, .38], [1, .38]]) part(g, bx(.05, .08, .05), M.metal, x * (W / 2 - .07), .04, z);
      if (o.p) { const k = part(g, rb(.42, .42, .12, .06), M.linen, o.p * (W / 2 - .45), .76, -.2); k.rotation.set(-.25, 0, o.p * .5); }  // kırlent
      return g;
    },
    kanepe_2li(o = {}) { return FACTORY.kanepe({w: 1.8, ...o}); },
    sehpa_yuvarlak(o = {}) {
      const g = G(), d = o.d ?? .9, h = d >= .8 ? .42 : .55;
      part(g, cyl(d / 2, d / 2, .04, 48), M.oak, 0, h - .02, 0);
      part(g, cyl(.035, .035, h - .04, 16), M.metal, 0, (h - .04) / 2, 0);
      part(g, cyl(d * .22, d * .25, .02, 32), M.metal, 0, .01, 0);
      if (o.kitap) part(g, rb(.16, .04, .24, .01), M.linen, .05, h + .02, .02);  // üstteki kitap/tepsi
      return g;
    },
    komodin() {
      const g = G();
      part(g, rb(.45, .44, .42, .015), M.oak, 0, .28, 0);
      for (const [x, z] of [[-.19, -.17], [.19, -.17], [-.19, .17], [.19, .17]]) part(g, cyl(.012, .01, .06, 8), M.black, x, .03, z);  // ayak
      M.oakDark ??= Object.assign(M.oak.clone(), {color: M.oak.color.clone().multiplyScalar(.82)});
      for (const y of [.18, .38]) {                                                         // çekmece önleri + düğme
        part(g, rb(.41, .18, .012, .006), M.oakDark, 0, y, .211);
        part(g, cyl(.012, .012, .02, 12), M.steel, 0, y, .222).rotation.x = Math.PI / 2;
      }
      part(g, cyl(.06, .08, .03, 24), M.chrome, 0, .515, 0);
      part(g, cyl(.012, .012, .2, 10), M.chrome, 0, .63, 0);
      M.shade ??= Object.assign(M.linen.clone(), {side: THREE.DoubleSide});
      part(g, new THREE.CylinderGeometry(.1, .14, .18, 32, 1, true), M.shade, 0, .78, 0);
      return g;
    },
    yemek_masasi(o = {}) {
      const g = G(), W = o.w ?? 2.0, D = o.d ?? 1.0;
      part(g, rb(W, .05, D, .01), M.oak, 0, .745, 0);
      for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) part(g, bx(.06, .72, .06), M.metal, x * (W / 2 - .1), .36, z * (D / 2 - .1));
      if (o.orta) { part(g, cyl(.3, .3, .006, 48), M.linen, 0, .773, 0); part(g, cyl(.06, .08, .24, 24), M.ceramic, 0, .896, 0); }
      return g;
    },
    sandalye() {
      const g = G();
      part(g, rb(.44, .045, .44, .012), M.oak, 0, .44, 0);                                  // oturak tablası
      part(g, rb(.42, .05, .4, .02), M.cushion, 0, .488, .01);                                // döşeme
      for (const x of [-.2, .2]) part(g, cyl(.014, .016, .44, 10), M.oak, x, .69, -.205);     // sırt dikmeleri
      part(g, rb(.44, .07, .03, .012), M.oak, 0, .88, -.21);                                  // üst kayıt
      for (const x of [-.09, 0, .09]) part(g, bx(.035, .3, .014), M.oak, x, .7, -.208);       // çıtalar
      for (const [x, z] of [[-.2, -.2], [.2, -.2], [-.2, .2], [.2, .2]]) part(g, cyl(.015, .012, .44, 10), M.oak, x, .22, z);
      return g;
    },
    tv() {
      const g = G();
      part(g, bx(1.46, .84, .03), M.screen, 0, 1.27, -.05);
      part(g, bx(1.47, .85, .02), M.metal, 0, 1.27, -.07);
      return g;
    },
    tv_unitesi() {
      const g = G();
      part(g, bx(2.0, .4, .42), M.anth, 0, .26, 0);
      part(g, bx(2.02, .03, .44), M.oak, 0, .475, 0);
      for (const x of [-.5, 0, .5]) part(g, bx(.004, .36, .005), M.black, x, .26, .212);
      return g;
    },
    hali(o = {}) {
      const g = G(), W = o.w ?? 2.4, D = o.d ?? 1.7;
      const m = part(g, rb(W, .012, D, .005), M.rug, 0, .006, 0); m.castShadow = false;
      if (o.w) { const b = part(g, rb(W - .16, .004, D - .16, .002), M.rugIn ??= Object.assign(M.rug.clone(), {color: new THREE.Color(0xdcd2c0)}), 0, .014, 0); b.castShadow = false; }
      return g;
    },
    tablo(o = {}) {
      const g = G(), W = o.w ?? 1.2, H = o.hy ?? .8, seed = o.v ?? 0;
      part(g, bx(W + .06, H + .06, .035), M.frame, 0, H / 2, -.0125);
      const c = document.createElement('canvas'); c.width = 256; c.height = Math.round(256 * H / W);
      const x = c.getContext('2d'), P = [['#e9e2d4', '#b7a58a', '#6f7a63', '#2f3237', '#c98f6b'], ['#efe9df', '#8e9a86', '#d2b48c', '#3b3f45', '#a26b4f']][seed % 2];
      x.fillStyle = P[0]; x.fillRect(0, 0, c.width, c.height);
      let r = seed * 9301 + 49297; const rnd = () => (r = (r * 9301 + 49297) % 233280) / 233280;
      for (let i = 0; i < 5; i++) { x.fillStyle = P[1 + i % 4]; x.globalAlpha = .85; x.beginPath();
        if (i % 2) x.arc(rnd() * c.width, rnd() * c.height, 20 + rnd() * 60, 0, Math.PI * 2); else x.rect(rnd() * c.width * .7, rnd() * c.height * .7, 40 + rnd() * 90, 20 + rnd() * 70);
        x.fill(); }
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
      part(g, bx(W, H, .01), new THREE.MeshStandardMaterial({map: t, roughness: .9}), 0, H / 2, .01);
      return g;
    },
    havlu() {  // krom askı + iki katlı havlu (beyaz ve adaçayı)
      const g = G(), a = M.towelA ??= new THREE.MeshStandardMaterial({color: 0xf1ede6, roughness: 1}), b = M.towelB ??= new THREE.MeshStandardMaterial({color: 0x9aa58c, roughness: 1});
      part(g, cyl(.01, .01, .62, 12), M.chrome, 0, .55, .04).rotation.z = Math.PI / 2;
      for (const sx of [-1, 1]) part(g, bx(.02, .02, .05), M.chrome, sx * .3, .55, .015);
      part(g, rb(.26, .5, .03, .01), a, -.14, .3, .05); part(g, rb(.26, .5, .03, .01), b, .14, .3, .05);
      return g;
    },
    yatak_ortusu(o = {}) {  // ayak ucunda katlı örtü: üstte şerit + iki yanda sarkan kenar (yerel +z ayak tarafı)
      const g = G(), W = o.w ?? 1.7, mat = M.throw ??= new THREE.MeshStandardMaterial({color: 0x7f8a6c, roughness: .95});
      part(g, rb(W, .03, .6, .012), mat, 0, .55, 0);
      for (const x of [-1, 1]) part(g, rb(.02, .28, .6, .008), mat, x * (W / 2 - .01), .42, 0);
      return g;
    },
    calisma_masasi() {
      const g = G();
      part(g, rb(1.4, .04, .7, .01), M.oak, 0, .74, 0);
      for (const x of [-.66, .66]) { part(g, bx(.04, .72, .04), M.metal, x, .36, -.3); part(g, bx(.04, .72, .04), M.metal, x, .36, .3); }
      part(g, bx(.5, .02, .3), M.screen, .1, 1.05, -.2);
      part(g, bx(.04, .28, .04), M.metal, .1, .9, -.24);
      return g;
    },
    kitaplik() {
      const g = G(), W = 1.2, H = 2.0, D = .35;
      for (const x of [-W / 2 + .015, W / 2 - .015]) part(g, bx(.03, H, D), M.oak, x, H / 2, 0);
      for (let i = 0; i < 6; i++) part(g, bx(W, .025, D), M.oak, 0, .04 + i * .38, 0);
      let n = 0;
      for (let r = 0; r < 5; r++) for (let x = -W / 2 + .06; x < W / 2 - .1; x += .05 + (n % 3) * .012) {
        if ((n * 7 + r) % 11 === 0) { x += .12; n++; continue; }
        const h = .22 + ((n * 13) % 7) * .012;
        part(g, bx(.035 + (n % 3) * .01, h, .24), M.books[n % M.books.length], x, .06 + r * .38 + h / 2, .02); n++;
      }
      return g;
    },
    ada() {
      const g = G();
      part(g, bx(2.2, .88, .9), M.lacquer, 0, .44, -.05);
      part(g, bx(2.3, .04, 1.2), M.quartz, 0, .9, .1);
      return g;
    },
    bar_taburesi() {
      const g = G();
      part(g, cyl(.19, .19, .06), M.cushion, 0, .76, 0);
      part(g, cyl(.025, .025, .7, 12), M.chrome, 0, .38, 0);
      part(g, cyl(.2, .22, .02), M.chrome, 0, .01, 0);
      part(g, new THREE.TorusGeometry(.17, .01, 8, 24), M.chrome, 0, .3, 0).rotation.x = Math.PI / 2;
      return g;
    },
    sezlong() {
      const g = G();
      part(g, bx(.7, .06, 1.95), M.oak, 0, .3, 0);
      for (const [x, z] of [[-.3, -.85], [.3, -.85], [-.3, .85], [.3, .85]]) part(g, bx(.05, .28, .05), M.oak, x, .14, z);
      part(g, rb(.64, .07, 1.3, .03), M.linen, 0, .37, .3);
      const back = part(g, rb(.64, .07, .7, .03), M.linen, 0, .52, -.62); back.rotation.x = .75;
      return g;
    },
    yatak_cift(o = {}) { return bed(o.w ?? 1.6, o.d); },
    yatak_tek(o = {}) { return bed(o.w ?? .9, o.d); },
    gardirop(o = {}) {
      const g = G(), W = o.w ?? 1.8, n = Math.max(2, Math.round(W / .6)), dw = W / n;
      part(g, bx(W, 2.4, .6), M.lacquer, 0, 1.2, 0);
      part(g, bx(W - .02, .08, .012), M.black, 0, .04, .305);                                    // geri çekik baza
      part(g, bx(W + .01, .03, .61), M.oak, 0, 2.385, .005);                                    // taç
      for (let i = 0; i < n; i++) {
        const x = -W / 2 + dw / 2 + i * dw, hx = x + (i % 2 ? -1 : 1) * (dw / 2 - .05);
        part(g, bx(dw - .008, 2.26, .02), M.lacquer, x, 1.21, .31);
        part(g, bx(.014, .9, .016), M.steel, hx, 1.2, .325);                                    // boy kulp
      }
      for (let i = 1; i < n; i++) part(g, bx(.006, 2.26, .004), M.black, -W / 2 + i * dw, 1.21, .322);   // kapak derzi
      return g;
    },
  };
  function bed(w, d) {  // d: başlık dahil toplam boy (varsayılan 2,18 m); merkeze göre ölçeklenir (layout_check ile aynı)
    const g = G(), k = G();
    part(g, rb(w + .1, .3, 2.1, .02), M.oak, 0, .15, 0);
    part(g, rb(w, .22, 2.0, .06), M.linen, 0, .41, 0);
    part(g, rb(w + .04, .06, 1.4, .03), M.duvet, 0, .53, .3);
    for (const x of (w > 1.2 ? [-w / 4, w / 4] : [0])) part(g, rb(.58, .13, .38, .06), M.linen, x, .58, -.72);
    part(g, rb(w + .16, 1.05, .05, .02), M.fabric, 0, .55, -1.105);                              // başlık gövdesi
    const np = Math.max(3, Math.round((w + .1) / .3)), pw = (w + .08) / np;
    M.fabricDark ??= Object.assign(M.fabric.clone(), {color: M.fabric.color.clone().multiplyScalar(.9)});
    for (let i = 0; i < np; i++) part(g, rb(pw - .012, .72, .05, .022), M.fabricDark, -(w + .08) / 2 + pw * (i + .5), .66, -1.065);   // dikey döşeme panelleri
    part(g, rb(w + .06, .05, .2, .02), M.linen, 0, .56, -.39);                                   // çarşaf kıvrımı
    part(g, bx(w, .06, 1.9), M.black, 0, .03, .02);                                            // geri çekik baza gölgesi
    if (d) g.scale.z = d / 2.18;
    k.add(g); return k;
  }

  // ------------------------------------------------------------------ model yükleme
  const modelCache = {};
  function loadItem(kind, params = {}) {
    const it = ITEMS.find(i => i.id === kind);
    if (!it) return Promise.reject(new Error('bilinmeyen nesne ' + kind));
    if (!it.model) return Promise.resolve(FACTORY[kind](params));
    modelCache[kind] ??= new Promise((ok, no) => gltf.load(`${A}models/${kind}/${kind}.gltf`, d => {
      d.scene.traverse(o => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; } });
      const b = new THREE.Box3().setFromObject(d.scene), c = b.getCenter(new THREE.Vector3());
      d.scene.position.set(-c.x, -b.min.y, -c.z);  // tabanı yerel orijine al
      const w = G(); w.add(d.scene); ok(w);
    }, undefined, e => { delete modelCache[kind]; no(e); }));  // başarısız yükleme önbellekte kalmasın, sonra yeniden denensin
    return modelCache[kind].then(w => w.clone(true));
  }
  const footprint = obj => { const b = new THREE.Box3().setFromObject(obj); return b.getSize(new THREE.Vector3()); };

  // ------------------------------------------------------------------ durum
  const S = {real: false, design: {floors: {}, paint: 'kirik_beyaz', objects: []}, floorMeshes: [], extras: [], objs: new Map(),
             tool: null, ghost: null, sel: null, drag: null, pid: null, saveT: null, env: null, ao: null, ground: null};

  // ------------------------------------------------------------------ gerçekçi mod
  function ensureEnv() {
    if (S.env) return Promise.resolve(S.env);
    return new Promise(ok => new RGBELoader().load(`${A}hdri/sky_1k.hdr`, t => {
      const pm = new THREE.PMREMGenerator(V.R);
      t.mapping = THREE.EquirectangularReflectionMapping;
      S.env = {tex: t, pmrem: pm.fromEquirectangular(t).texture}; ok(S.env);
    }));
  }
  const defaultFloor = name => /Banyo|Mutfak|Kat Holü|Merdiven|Şaft|Asansör/.test(name) ? 'large_grey_tiles' : 'laminate_floor_02';
  function levelGroup(level) { const i = (V.nLv || []).indexOf(level); return V.levels.filter(L => !L.site)[i]?.group; }

  // taşıyıcı: elemanda işaretliyse o, yoksa ≥ 18 cm (dış, perde, bölücü duvar); bölme duvarlar yıkılabilir
  const structural = w => w.structural ?? ((w.thickness || .2) >= .18);
  const isDemolished = w => !!w && (S.design.demolished || []).includes(w.name);
  function applyDemolish() {
    V.root.traverse(o => { if (typeof o.userData.wall === 'string') o.visible = !(S.design.demolished || []).includes(o.userData.wall); });
  }
  function demolishedArea() {
    return (V.elements || []).filter(e => e.type === 'wall' && isDemolished(e)).reduce((a, w) => {
      const L = Math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1]);
      const op = (w.openings || []).reduce((s, o) => s + o.width * (o.height ?? 2.1), 0);
      return a + L * (w.height || 2.8) - op;
    }, 0);
  }
  function buildExtras() {
    clearExtras();
    const els = V.elements || [];
    for (const r of els.filter(e => e.type === 'room')) {
      const g = levelGroup(r.level); if (!g) continue;
      const sh = new THREE.Shape(); r.points.forEach(([x, y], i) => i ? sh.lineTo(x, y) : sh.moveTo(x, y)); sh.closePath();
      const m = new THREE.Mesh(new THREE.ShapeGeometry(sh), floorMat(S.design.floors[r.name] || defaultFloor(r.name)));
      m.rotation.x = -Math.PI / 2; m.position.y = (r.z || 0) + .004; m.receiveShadow = true;
      m.userData.room = r; g.add(m); S.floorMeshes.push(m);
    }
    // pencere kasaları + kapı kasaları + süpürgelik
    M.skirt ??= new THREE.MeshStandardMaterial({color: 0xbdb3a4, roughness: .6});
    const roomsBy = {};
    for (const w of els.filter(e => e.type === 'wall' && !isDemolished(e))) {
      const g = levelGroup(w.level); if (!g) continue;
      const [x0, y0] = w.start, [x1, y1] = w.end, L = Math.hypot(x1 - x0, y1 - y0); if (L < 1e-3) continue;
      const ux = (x1 - x0) / L, uy = (y1 - y0) / L, ang = Math.atan2(uy, ux), zb = w.base_z || 0, T = w.thickness || .2;
      if (w.tag !== 'wood' && !w.profile) {
        const rooms = roomsBy[w.level] ??= els.filter(e => e.type === 'room' && e.level === w.level);
        const doorsW = (w.openings || []).filter(o => o.kind === 'door').map(o => [o.offset, o.offset + o.width]).sort((a, b) => a[0] - b[0]);
        const spans = []; let c0 = 0;
        for (const [a, b] of doorsW) { spans.push([c0, a]); c0 = b; }
        spans.push([c0, L]);
        for (const sg of [-1, 1]) {
          const nx = -uy * sg, ny = ux * sg;
          for (const [a, b] of spans) {
            if (b - a < .05) continue;
            const m = (a + b) / 2, px = x0 + ux * m + nx * (T / 2 + .25), py = y0 + uy * m + ny * (T / 2 + .25);
            if (!rooms.some(r => inPoly([px, py], r.points))) continue;       // dış yüz: süpürgelik yok
            const k = new THREE.Mesh(bx(b - a, .08, .014), M.skirt), cx = x0 + ux * m + nx * (T / 2 + .007), cy = y0 + uy * m + ny * (T / 2 + .007);
            k.position.set(cx, zb + .04, -cy); k.rotation.y = ang; k.receiveShadow = true; g.add(k); S.extras.push(k);
          }
        }
      }
      for (const o of w.openings || []) {
        const a = o.offset, b = a + o.width, door = o.kind === 'door', sill = door ? 0 : (o.sill ?? .9), top = sill + (o.height ?? (door ? 2.1 : 1.4));
        const timber = w.tag === 'wood';
        const fw = door ? .06 : .055, fd = door ? T + .02 : .07, mat = timber ? M.timber : door ? M.lacquer : M.frame;
        if (door && timber && o.leaf) {  // ahşap kapı kanadı (üstte küçük cam)
          const cx = x0 + ux * (a + b) / 2, cy = y0 + uy * (a + b) / 2, lw = o.width - 2 * fw;
          const leaf = new THREE.Mesh(bx(lw, top - fw, .045), M.timber); leaf.position.set(cx, zb + (top - fw) / 2, -cy); leaf.rotation.y = ang;
          leaf.castShadow = leaf.receiveShadow = true; g.add(leaf); S.extras.push(leaf);
          const gl = new THREE.Mesh(bx(lw * .6, .5, .05), M.glass); gl.position.set(cx, zb + top - .55, -cy); gl.rotation.y = ang; g.add(gl); S.extras.push(gl);
        }
        const put = (s, zc, lw, lh) => {
          const m = new THREE.Mesh(bx(lw, lh, fd), mat), cx = x0 + ux * s, cy = y0 + uy * s;
          m.position.set(cx, zb + zc, -cy); m.rotation.y = ang; m.castShadow = m.receiveShadow = true; g.add(m); S.extras.push(m);
        };
        put(a + fw / 2, (sill + top) / 2, fw, top - sill); put(b - fw / 2, (sill + top) / 2, fw, top - sill);
        put((a + b) / 2, top - fw / 2, o.width, fw);
        if (!door) { put((a + b) / 2, sill + fw / 2, o.width, fw); if (o.width > 1.2) put((a + b) / 2, (sill + top) / 2, .04, top - sill - .1); }
      }
    }
    roomLamps(!!S.night); applyDemolish();
  }
  function surfaceMaterials(on) {
    const stone = floorMat('large_grey_tiles'), deck = floorMat('weathered_planks');
    V.root.traverse(o => {
      if (!o.isMesh) return;
      const sf = o.userData.surf;
      if (on) {
        let m = null;
        if (o.userData.tree) { o.visible = false; return; }
        // tomruk duvar, açık makaslı çatı ve parmaklıklı korkuluk: kutu yerine buildTimber() gerçek ahşabı kurar
        if ((sf?.role === 'wall' && sf.tag === 'wood') || (o.userData.roof?.structure === 'open') || sf?.style === 'baluster') { o.userData.hidReal = true; o.visible = false; return; }
        if (sf?.tag === 'water') m = M.water;
        else if (sf?.role === 'paving') m = stone;
        else if (sf?.role === 'deck') m = deck;
        else if (sf?.role === 'roof') m = sf.tag === 'wood' ? M.timber : o.userData.pitched ? M.shingle : M.roof;
        else if (sf?.role === 'site') return;
        else if (sf?.role === 'wall') return;
        else if (sf?.role === 'stairs') m = sf.tag === 'wood' ? M.timber : M.stone;
        else if (sf?.role === 'box' && sf.tag === 'metal') m = M.metal;
        else if (sf?.role === 'box' && sf.tag === 'wood') m = M.timber;
        else if (sf?.role === 'box' && sf.tag === 'stone') m = M.stone;
        else if (sf?.role === 'box' && sf.tag === 'concrete') m = M.concrete;
        if (m) { o.userData.preReal ??= o.material; o.material = m; }
      } else {
        if (o.userData.tree) o.visible = true;
        if (o.userData.hidReal) { o.visible = true; delete o.userData.hidReal; }
        if (o.userData.preReal) { o.material = o.userData.preReal; delete o.userData.preReal; }
      }
    });
  }
  // ------------------------------------------------------------------ tomruk ev: gerçek ahşap strüktür
  function anyGroup(level) { return levelGroup(level) || V.levels.find(L => L.site)?.group; }
  function scaleUV(geo, u, v) { const a = geo.attributes.uv; for (let i = 0; i < a.count; i++) a.setXY(i, a.getX(i) * u, a.getY(i) * v); return geo; }
  // p0→p1 (plan x, y, z) arası kiriş: kesit h (yükseklik) × w (genişlik); cyl=true ise tomruk (çap h)
  function beam(g, p0, p1, h, w, mat, cyl = false) {
    const a = new THREE.Vector3(p0[0], p0[2], -p0[1]), b = new THREE.Vector3(p1[0], p1[2], -p1[1]), d = b.clone().sub(a), L = d.length(); if (L < 1e-3) return null;
    const geo = cyl ? scaleUV(new THREE.CylinderGeometry(h / 2, h / 2, L, 14).rotateZ(Math.PI / 2), 1, L) : scaleUV(bx(L, h, w), L, 1);
    const m = new THREE.Mesh(geo, mat); m.position.copy(a).add(b).multiplyScalar(.5);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), d.normalize());
    m.castShadow = m.receiveShadow = true; g.add(m); S.extras.push(m); return m;
  }
  function buildTimber() {
    const els = V.elements || [];
    // --- tomruk duvarlar: yatay kütükler, açıklıklar atlanır, dış duvarlarda köşe taşkını
    for (const w of els.filter(e => e.type === 'wall' && e.tag === 'wood')) {
      const g = anyGroup(w.level); if (!g) continue;
      const [x0, y0] = w.start, [x1, y1] = w.end, L = Math.hypot(x1 - x0, y1 - y0); if (L < 1e-3) continue;
      const ux = (x1 - x0) / L, uy = (y1 - y0) / L, T = w.thickness || .2, H = w.height || 2.8, zb = w.base_z || 0;
      const d = Math.max(.12, T), n = Math.max(1, Math.round(H / d)), dd = H / n, ext = T >= .2 ? .3 : 0, gable = w.profile === 'gable';
      const P = (s, z) => [x0 + ux * s, y0 + uy * s, z];
      for (let k = 0; k < n; k++) {
        const zc = zb + (k + .5) * dd;
        let spans = [[-ext, L + ext]];
        if (gable) { const f = 1 - (k + .5) / n; spans = [[L / 2 - L * f / 2, L / 2 + L * f / 2]]; }
        for (const o of w.openings || []) {
          const door = o.kind === 'door', sill = door ? 0 : (o.sill ?? .9), top = sill + (o.height ?? (door ? 2.1 : 1.4));
          if (zc <= sill || zc >= top) continue;
          const a = o.offset, b = a + o.width, next = [];
          for (const [s0, s1] of spans) { if (b <= s0 || a >= s1) { next.push([s0, s1]); continue; } if (a > s0) next.push([s0, a]); if (b < s1) next.push([b, s1]); }
          spans = next;
        }
        for (const [s0, s1] of spans) beam(g, P(s0, zc), P(s1, zc), dd * .98, dd, M.log, true);
      }
    }
    // --- açık çatı makası: taban kirişi, aşıklar, mahya, mertekler, döşeme kirişleri
    for (const r of els.filter(e => e.type === 'roof' && e.structure === 'open')) {
      const g = anyGroup(r.level); if (!g) continue;
      const ax = (r.axis || 'x') === 'x', z = r.z || 0, rh = r.ridge ?? 1.5, f = r.ridge_at ?? .5;
      const [s0, s1] = ax ? [r.y0, r.y1] : [r.x0, r.x1], [a0, a1] = ax ? [r.x0, r.x1] : [r.y0, r.y1], sm = s0 + (s1 - s0) * f;
      const Q = (a, s, zz) => ax ? [a, s, zz] : [s, a, zz];
      const prof = [[s0, z], [sm, z + rh], [s1, z]].filter((p, i, arr) => !i || Math.abs(p[0] - arr[i - 1][0]) > 1e-6);
      for (const [s, zz] of prof) beam(g, Q(a0, s, zz + .1), Q(a1, s, zz + .1), .2, .2, M.timber);              // taban kirişleri + mahya
      for (let i = 0; i + 1 < prof.length; i++) {                                                               // aşıklar (her eğimde 2)
        const [sa, za] = prof[i], [sb, zb] = prof[i + 1];
        for (const t of [1 / 3, 2 / 3]) beam(g, Q(a0, sa + (sb - sa) * t, za + (zb - za) * t + .12), Q(a1, sa + (sb - sa) * t, za + (zb - za) * t + .12), .14, .14, M.timber);
      }
      const nr = Math.max(2, Math.round((a1 - a0) / .6));                                                       // mertekler
      for (let i = 0; i <= nr; i++) {
        const a = a0 + (a1 - a0) * i / nr;
        for (let j = 0; j + 1 < prof.length; j++) beam(g, Q(a, prof[j][0], prof[j][1] + .25), Q(a, prof[j + 1][0], prof[j + 1][1] + .25), .18, .08, M.timber);
      }
      const nj = Math.max(1, Math.round((a1 - a0) / 1.2));                                                      // taban (bağ) kirişleri
      for (let i = 1; i < nj; i++) { const a = a0 + (a1 - a0) * i / nj; beam(g, Q(a, s0, z - .02), Q(a, s1, z - .02), .2, .12, M.timber); }
    }
    // --- parmaklıklı korkuluk: üst/alt küpeşte, babalar, parmaklıklar
    for (const b of els.filter(e => e.type === 'box' && e.style === 'baluster')) {
      const g = anyGroup(b.level); if (!g) continue;
      const [ox, oy, oz] = b.origin, [sx, sy, sz] = b.size, alongX = sx >= sy, L = alongX ? sx : sy;
      const P = (s, zz) => alongX ? [ox + s, oy + sy / 2, oz + zz] : [ox + sx / 2, oy + s, oz + zz];
      beam(g, P(0, sz - .04), P(L, sz - .04), .08, .1, M.timber); beam(g, P(0, .12), P(L, .12), .06, .06, M.timber);
      for (const s of [0, L]) beam(g, P(s, 0), P(s, sz + .06), .1, .1, M.timber);
      const nb = Math.max(1, Math.round(L / .13));
      for (let i = 1; i < nb; i++) beam(g, P(L * i / nb, .15), P(L * i / nb, sz - .08), .035, .035, M.timber);
    }
  }
  function buildTrees() {
    const site = V.levels.find(L => L.site)?.group; if (!site) return;
    for (const t of (V.elements || []).filter(e => e.type === 'tree')) {
      const [x, y] = t.position, h = t.height || 5, z = t.base_z || 0;
      const add = (geo, mat, px, py, pz) => { const m = new THREE.Mesh(geo, mat); m.position.set(px, py, pz); m.castShadow = m.receiveShadow = true; site.add(m); S.extras.push(m); return m; };
      add(cyl(h * .035, h * .05, h * .55, 8), M.bark, x, z + h * .275, -y);
      const seed = Math.abs(Math.sin(x * 12.9 + y * 78.2)) * 1000;
      for (let i = 0; i < 5; i++) {
        const a = seed + i * 2.4, r = h * (.16 + (i % 3) * .04), d = i ? h * .14 : 0;
        add(new THREE.IcosahedronGeometry(r, 1), M.leaves[i % 3], x + Math.cos(a) * d, z + h * (.62 + (i % 2) * .1), -y + Math.sin(a) * d);
      }
    }
  }
  function clearExtras() {
    for (const m of [...S.floorMeshes, ...S.extras, ...(S.leaves || []), ...(S.lamps || [])]) m.parent?.remove(m);
    S.floorMeshes = []; S.extras = []; S.leaves = []; S.lamps = [];
  }
  // kapı kanadı: hol/koridor değil oda tarafına açılır (iki taraf da oda ya da hol ise küçük odaya);
  // menteşe duvar ucuna yakın kasada; kanat mobilyaya çarparsa açı daralır
  const HALLISH = /Hol|Koridor|Ortak|Giriş|Antre/;
  const angDiff = (a, b) => Math.atan2(Math.sin(a - b), Math.cos(a - b));
  function tick(dt) {  // kapı kanatları hedef açıya döner (≈ 150°/s)
    for (const p of S.leaves || []) {
      const d = p.userData.door; if (!d) continue;
      const e = angDiff(d.tgt, d.cur); if (Math.abs(e) < 1e-3) continue;
      d.cur += Math.sign(e) * Math.min(Math.abs(e), dt * 2.6); p.rotation.y = d.cur;
    }
  }
  function toggleDoor() {  // ekran ortasındaki (≤ 2,5 m) kapıyı aç/kapa
    if (!S.leaves?.length) return false;
    ray.setFromCamera(new THREE.Vector2(0, 0), V.C);
    const h = ray.intersectObjects(S.leaves, true).find(x => x.object.userData.door && shown(x.object));
    if (!h || h.distance > 2.5) return false;
    const d = h.object.userData.door; d.tgt = Math.abs(angDiff(d.tgt, d.th0)) < 1e-3 ? d.th1 : d.th0;
    return true;
  }
  function doorSegs(level) {  // (neredeyse) kapalı kanat gezintide duvar gibi engel
    return (S.leaves || []).map(p => p.userData.door).filter(d => d && d.level === level && Math.abs(angDiff(d.cur, d.th0)) < .35)
      .map(d => [d.hx, d.hy, d.hx + Math.cos(d.cur) * d.lw, d.hy + Math.sin(d.cur) * d.lw, .03]);
  }
  function buildLeaves() {
    for (const m of S.leaves || []) m.parent?.remove(m);
    S.leaves = [];
    const els = V.elements || [], byLevel = {};
    for (const w of els.filter(e => e.type === 'wall' && e.tag !== 'wood' && !isDemolished(e))) {
      const doorsHere = (w.openings || []).filter(o => o.kind === 'door' && o.leaf);
      if (!doorsHere.length) continue;
      const g = levelGroup(w.level); if (!g) continue;
      const boxes = byLevel[w.level] ??= planBoxes(w.level), rooms = els.filter(e => e.type === 'room' && e.level === w.level);
      const [x0, y0] = w.start, [x1, y1] = w.end, L = Math.hypot(x1 - x0, y1 - y0); if (L < 1e-3) continue;
      const ux = (x1 - x0) / L, uy = (y1 - y0) / L, nx = -uy, ny = ux, zb = w.base_z || 0, T = w.thickness || .2;
      for (const o of doorsHere) {
        const fw = .06, lw = o.width - 2 * fw, top = o.height ?? 2.1, sm = o.offset + o.width / 2, mx_ = x0 + ux * sm, my = y0 + uy * sm;
        const side = sg => rooms.find(r => inPoly([mx_ + nx * sg * .5, my + ny * sg * .5], r.points));
        const A = side(1), B = side(-1);
        let sg = 1;
        if (A && B) { const ha = HALLISH.test(A.name), hb = HALLISH.test(B.name); sg = ha !== hb ? (ha ? -1 : 1) : (polyArea(A.points) <= polyArea(B.points) ? 1 : -1); }
        else sg = A ? 1 : -1;
        const hingeAtStart = o.offset <= L - (o.offset + o.width);             // duvar ucuna yakın kasa
        const hs = hingeAtStart ? o.offset + fw : o.offset + o.width - fw, dir = hingeAtStart ? 1 : -1;
        const hx = x0 + ux * hs + nx * sg * T / 2, hy = y0 + uy * hs + ny * sg * T / 2;
        let ang = THREE.MathUtils.degToRad(80);
        for (const a of [80, 55, 30].map(d => THREE.MathUtils.degToRad(d))) {
          ang = a; const ex = hx + (ux * dir * Math.cos(a) + nx * sg * Math.sin(a)) * lw, ey = hy + (uy * dir * Math.cos(a) + ny * sg * Math.sin(a)) * lw;
          const mxp = (hx + ex) / 2, myp = (hy + ey) / 2;
          if (!boxes.some(b => [[ex, ey], [mxp, myp]].some(([px, py]) => px > b.x0 - .03 && px < b.x1 + .03 && py > b.y0 - .03 && py < b.y1 + .03))) break;
        }
        const piv = new THREE.Group(); piv.position.set(hx, zb, -hy);
        // kapalı kanat duvar boyunca (dir·u), açılma sg·n yönüne: plan açısı θ = atan2(dir·u + sg·n·tan) → three'de rotation.y = plan açısı
        const th = Math.atan2(uy * dir * Math.cos(ang) + ny * sg * Math.sin(ang), ux * dir * Math.cos(ang) + nx * sg * Math.sin(ang));
        const th0 = Math.atan2(uy * dir, ux * dir);                       // kapalı: duvar hattında
        piv.rotation.y = th;
        piv.userData.door = {level: w.level, hx, hy, lw, th0, th1: th, cur: th, tgt: th};
        const leaf = new THREE.Mesh(bx(lw, top - fw - .01, .04), M.oak); leaf.position.set(lw / 2, (top - fw) / 2, 0);
        const knob = new THREE.Mesh(cyl(.02, .02, .14, 12), M.chrome); knob.rotation.x = Math.PI / 2; knob.position.set(lw - .07, 1.0, 0);
        leaf.castShadow = leaf.receiveShadow = true; piv.add(leaf, knob); g.add(piv); S.leaves.push(piv);
        leaf.userData.door = knob.userData.door = piv.userData.door;
      }
    }
  }
  function applyPaint() { plaster.color.set((PAINTS.find(p => p.id === S.design.paint) || PAINTS[0]).c); }

  async function setReal(on) {
    if (on === S.real) return;
    S.real = on;
    V.root.traverse(o => { if (o.isLine || o.isLineSegments) o.visible = !on; });
    V.S.children.forEach(o => { if (o.isGridHelper) o.visible = !on; });
    if (on) {
      const env = await ensureEnv();
      if (!S.real) return;
      S.saved = {face: V.mat.face, slab: V.mat.slab, glass: V.mat.glass, tm: V.R.toneMapping, exp: V.R.toneMappingExposure, fog: V.S.fog.density};
      V.S.environment = env.pmrem; V.S.background = env.tex; V.S.backgroundIntensity = 1; V.S.environmentIntensity = .9;
      V.S.fog.density = 0; V.R.toneMapping = THREE.ACESFilmicToneMapping; V.R.toneMappingExposure = 1.3; V.S.environmentIntensity = 1.25;
      V.R.shadowMap.enabled = true; V.R.shadowMap.type = THREE.PCFSoftShadowMap;
      swapMaterials(plaster, M.ceiling, M.glass);
      applyPaint();
      if (!S.sun) {
        S.sun = new THREE.DirectionalLight(0xfff1dc, 3.2); S.sun.castShadow = true;
        S.sun.shadow.mapSize.set(2048, 2048); S.sun.shadow.bias = -.0004; S.sun.shadow.normalBias = .03;
        S.fill = new THREE.HemisphereLight(0xfff8ee, 0xb8a890, .55);  // iç mekân dolgu ışığı (tavan/zemin sekmesi)
        S.ground = new THREE.Mesh(new THREE.PlaneGeometry(800, 800), M.ground); S.ground.rotation.x = -Math.PI / 2; S.ground.position.y = -.25; S.ground.receiveShadow = true;
      }
      placeSun();
      V.S.add(S.sun, S.sun.target, S.ground, S.fill);
      V.mat.site.opacity = 1; V.mat.site.color.set(0x7d8a66); V.mat.site.depthWrite = true;
      V.root.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
      buildExtras(); surfaceMaterials(true); buildTrees(); buildTimber();
      if (!S.ao) { S.ao = new GTAOPass(V.S, V.C, 1, 1); S.ao.blendIntensity = .9; V.comp.insertPass(S.ao, 1); }
      S.ao.enabled = true; V.bloom.enabled = false; resizeAO();
      restoreObjects();
    } else {
      if (S.saved) { swapMaterials(S.saved.face, S.saved.slab, S.saved.glass); V.R.toneMapping = S.saved.tm; V.R.toneMappingExposure = S.saved.exp; V.S.fog.density = S.saved.fog; }
      V.S.environment = null; V.S.background = null; V.R.shadowMap.enabled = false;
      V.S.remove(S.sun, S.sun?.target, S.ground, S.fill);
      for (const [o, i0] of S.baseLights || []) o.intensity = i0;
      V.mat.site.opacity = .035; V.mat.site.color.set(0x3cffa6); V.mat.site.depthWrite = false;
      surfaceMaterials(false); clearExtras(); clearObjects(); cancelTool(); select(null);
      if (S.ao) S.ao.enabled = false; V.bloom.enabled = true;
    }
  }
  function placeSun() {
    if (!S.sun || !V.box) return;
    const s = V.box.getSize(new THREE.Vector3()), R = Math.max(s.x, s.z, s.y) * .75 + 6;
    // saat 6 → doğu (+x), 12 → güney-tepe, 18 → batı; plan kuzeyi −Z, güneş güneyden (+Z)
    const t = Math.min(1, Math.max(0, ((S.hour ?? 11) - 6) / 12)), el = Math.sin(Math.PI * t);
    const dir = new THREE.Vector3(Math.cos(Math.PI * t), el * 1.25 + .18, .55).normalize();
    S.sun.position.copy(dir.multiplyScalar(R * 1.8)); S.sun.target.position.set(0, 0, 0);
    Object.assign(S.sun.shadow.camera, {left: -R, right: R, top: R, bottom: -R, near: 1, far: R * 5}); S.sun.shadow.camera.updateProjectionMatrix();
    const night = !!S.night, warm = 1 - el;
    // görüntüleyicinin kendi ışıkları (şematik mod için): gece kısılır, gündüz asıl değerine döner
    S.baseLights ??= V.S.children.filter(o => (o.isDirectionalLight || o.isHemisphereLight) && o !== S.sun && o !== S.fill).map(o => [o, o.intensity]);
    for (const [o, i0] of S.baseLights) o.intensity = night ? i0 * .04 : i0;
    S.sun.color.setHSL(.09, .35 + warm * .45, .93 - warm * .1);
    S.sun.intensity = night ? .04 : 1.2 + 2.2 * el;
    if (S.fill) S.fill.intensity = night ? .06 : .55;
    V.S.environmentIntensity = night ? .06 : 1.25;
    if (S.real && S.env) V.S.background = night ? (S.nightSky ??= new THREE.Color(0x0b1020)) : S.env.tex;
    V.R.toneMappingExposure = night ? 1.5 : 1.3;
    if (S.real) V.mat.site.color.set(night ? 0x1b2119 : 0x7d8a66);   // arsa yüzeyi ışıksız malzeme: gece elle koyulaşır
    roomLamps(night);
  }
  function roomLamps(on) {  // gece: her odada tavan ışığı (sıcak beyaz)
    for (const l of S.lamps || []) l.parent?.remove(l);
    S.lamps = [];
    if (!on || !S.real) return;
    for (const r of (V.elements || []).filter(e => e.type === 'room' && !/Asansör|Şaft/.test(e.name))) {
      const g = levelGroup(r.level); if (!g) continue;
      const [cx, cy] = centroid(r.points), a = polyArea(r.points);
      const l = new THREE.PointLight(0xffd6a0, 3 + Math.min(6, a * .35), Math.sqrt(a) * 2.2 + 3, 1.7);
      l.position.set(cx, (r.z || 0) + (r.height || 2.8) - .3, -cy); g.add(l); S.lamps.push(l);
    }
  }
  function setSun(hour, night) { S.hour = hour; S.night = night; if (S.sun) placeSun(); }
  function swapMaterials(face, slab, glass) {
    const f0 = V.mat.face, s0 = V.mat.slab, g0 = V.mat.glass;
    V.root.traverse(o => { if (!o.isMesh) return; if (o.material === f0) o.material = face; else if (o.material === s0) o.material = slab; else if (o.material === g0) o.material = glass; });
    V.mat.face = face; V.mat.slab = slab; V.mat.glass = glass;
  }
  function resizeAO() { if (S.ao) { const r = V.R.getSize(new THREE.Vector2()); S.ao.setSize(r.x, r.y); } }

  // ------------------------------------------------------------------ nesneler
  async function spawnObject(o) {
    const g = levelGroup(o.level); if (!g) return null;
    let obj;
    try { obj = await loadItem(o.kind, o); } catch (e) { console.warn('nesne yüklenemedi', o.kind, e); return null; }
    obj.position.set(o.x, levelZ(o.level) + (o.h || 0), -o.y); obj.rotation.y = o.rot || 0;
    obj.userData.item = o; obj.traverse(m => { if (m.isMesh) { m.castShadow = m.receiveShadow = true; m.userData.owner = obj; } });
    obj.scale.y = Math.max(.001, S.growK ?? 1);
    g.add(obj); S.objs.set(o.id, obj); return obj;
  }
  const levelZ = n => ((V.elements || []).find(e => e.type === 'slab' && e.role === 'floor' && e.level === n) || {z: 0}).z;
  function grow(k) { S.growK = k; for (const o of S.objs.values()) o.scale.y = Math.max(.001, k); for (const p of S.leaves || []) p.visible = k > .5; }
  function clearObjects() { for (const o of S.objs.values()) o.parent?.remove(o); S.objs.clear(); }
  // paralel yükle; render dışa aktarımı S.restoring bitene kadar bekler (yarım sahne gönderilmesin)
  function restoreObjects() {
    clearObjects();
    const token = S.restoreToken = {};
    S.restoring = Promise.all(S.design.objects.map(async o => {
      const obj = await spawnObject(o);
      if (obj && S.restoreToken !== token) { obj.parent?.remove(obj); S.objs.delete(o.id); }  // daha yeni bir yükleme başladıysa at
    })).then(() => { if (S.restoreToken === token && S.real) buildLeaves(); });
    return S.restoring;
  }
  const uid = () => Math.random().toString(36).slice(2, 10);

  // ------------------------------------------------------------------ ışın / etkileşim
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  function pick(ev, targets) {
    const rc = V.R.domElement.getBoundingClientRect();
    if (document.pointerLockElement) ndc.set(0, 0);
    else ndc.set(((ev.clientX - rc.left) / rc.width) * 2 - 1, -((ev.clientY - rc.top) / rc.height) * 2 + 1);
    ray.setFromCamera(ndc, V.C);
    return ray.intersectObjects(targets.filter(shown), true).find(h => shown(h.object));
  }
  // three.js Raycaster görünmez objeleri de vurur: zinciri kökten kontrol et
  const shown = o => { for (let x = o; x; x = x.parent) if (!x.visible) return false; return true; };
  const floorTargets = () => S.floorMeshes.filter(shown);
  // zemin seçimi: duvar/döşeme/çatı/nesne engel sayılır; ilk vurulan yüzey oda zemini değilse sonuç yok
  function pickFloor(ev) {
    const rc = V.R.domElement.getBoundingClientRect();
    if (document.pointerLockElement) ndc.set(0, 0);
    else ndc.set(((ev.clientX - rc.left) / rc.width) * 2 - 1, -((ev.clientY - rc.top) / rc.height) * 2 + 1);
    ray.setFromCamera(ndc, V.C);
    // mobilya/halı zemini örtmesin: nesne yüzeylerini atla, ilk yapı yüzeyi oda zemini olmalı
    const h = ray.intersectObject(V.root, true).find(x => shown(x.object) && !x.object.userData.owner);
    return h && h.object.userData.room ? h : null;
  }
  function hitToPlan(h) { const p = h.point.clone(); V.root.worldToLocal(p); return {x: p.x, y: -p.z, level: h.object.userData.room.level, room: h.object.userData.room}; }

  function armFloor(id) { cancelTool(); S.tool = {type: 'floor', id}; hint(`${FLOORS.find(f => f.id === id).name}: döşemek için bir odaya tıklayın`); }
  async function armItem(kind) {
    cancelTool(); S.tool = {type: 'item', kind, rot: 0};
    S.ghost = await loadItem(kind); S.ghost.traverse(m => { if (m.isMesh) { m.material = m.material.clone(); m.material.transparent = true; m.material.opacity = .55; m.castShadow = false; } });
    S.ghost.visible = false; S.ghost.traverse(m => { m.raycast = () => {}; }); V.S.add(S.ghost);
    hint(`${ITEMS.find(i => i.id === kind).name}: yerleştirmek için tıklayın · R döndür · Esc vazgeç`);
  }
  function cancelTool() { if (S.ghost) V.S.remove(S.ghost); S.ghost = null; S.tool = null; hint(''); highlight(null); if ($('#vp').classList.contains('editing')) editHint(); }
  function highlight(mesh) {
    if (S.hl === mesh) return;
    if (S.hl) S.hl.material = S.hl.userData.baseMat;
    S.hl = mesh;
    if (mesh) { mesh.userData.baseMat = mesh.material; const m = mesh.material.clone(); m.emissive = new THREE.Color(0x3ee8ff); m.emissiveIntensity = .18; mesh.material = m; }
  }
  function select(obj) {
    if (S.selBox) { V.S.remove(S.selBox); S.selBox = null; }
    S.sel = obj;
    if (obj) { S.selBox = new THREE.BoxHelper(obj, 0x3ee8ff); S.selBox.raycast = () => {}; V.S.add(S.selBox); }
    renderSel();
  }
  function rotateSel(d = Math.PI / 2) {
    if (S.tool?.type === 'item') { S.tool.rot += d; if (S.ghost) S.ghost.rotation.y = S.tool.rot; return; }
    if (!S.sel) return; S.sel.rotation.y += d; S.sel.userData.item.rot = S.sel.rotation.y; S.selBox?.update(); save();
  }
  function deleteSel() {
    if (!S.sel) return; const it = S.sel.userData.item;
    S.design.objects = S.design.objects.filter(o => o.id !== it.id); S.sel.parent?.remove(S.sel); S.objs.delete(it.id); select(null); save(); summary();
  }

  function onMove(ev) {
    if (!S.real) return;
    if (S.drag && S.sel) {
      const h = pickFloor(ev); if (!h) return; const p = hitToPlan(h);
      if (p.level !== S.sel.userData.item.level) return;
      S.sel.position.set(p.x - S.drag.dx, S.sel.position.y, -(p.y - S.drag.dy)); S.selBox?.update(); return;
    }
    if (!S.tool) return;
    if (S.tool.type === 'demolish') {
      const hw = pick(ev, wallMeshes()), m = hw?.object || null; highlight(m);
      if (m) { m.material.emissive.set(structural(m.userData.wall) ? 0xff3030 : 0xffa040); m.material.emissiveIntensity = .4; }
      return;
    }
    const h = pickFloor(ev);
    if (S.tool.type === 'floor') { highlight(h?.object || null); return; }
    if (S.ghost) {
      if (!h) { S.ghost.visible = false; return; }
      const p = h.point; S.ghost.position.copy(p); S.ghost.rotation.y = S.tool.rot; S.ghost.visible = true;
    }
  }
  function onDown(ev) {
    if (!S.real || S.tool || ev.button !== 0) return;
    const h = pick(ev, [...S.objs.values()].filter(shown));
    if (h) {
      let o = h.object; while (o && !o.userData.item) o = o.parent;
      if (o) {
        select(o); V.O.enabled = false;
        const f = pickFloor(ev);
        if (f) { const p = hitToPlan(f); S.drag = {dx: p.x - o.position.x, dy: p.y + o.position.z}; }
        ev.stopPropagation();
      }
    }
  }
  function onUp() {
    if (S.drag && S.sel) { const it = S.sel.userData.item; it.x = S.sel.position.x; it.y = -S.sel.position.z; save(); }
    S.drag = null; if (!isWalking()) V.O.enabled = true;
  }
  function wallMeshes() { const a = []; V.root.traverse(o => { if (o.isMesh && typeof o.userData.wall === 'object') a.push(o); }); return a; }
  function toggleDemolish(w) {
    const d = S.design.demolished ??= [], i = d.indexOf(w.name);
    if (i >= 0) d.splice(i, 1); else d.push(w.name);
    highlight(null); buildExtras(); buildLeaves(); save(); renderPanel();
  }
  async function onClick(ev) {
    if (!S.real || !S.tool) return false;
    if (S.tool.type === 'demolish') {
      const hw = pick(ev, wallMeshes());
      if (!hw) { hint('Yıkmak için bir bölme duvara tıklayın · Esc bitir'); return true; }
      const w = hw.object.userData.wall;
      if (structural(w)) { hint('Taşıyıcı duvar yıkılamaz — statik proje ve mühendis onayı gerekir'); return true; }
      toggleDemolish(w); hint(`Bölme duvar yıkıldı · toplam ${n2(demolishedArea())} m² — Esc bitir`); return true;
    }
    const h = pickFloor(ev);
    if (!h) { hint('Bir odanın zeminine tıklayın — başka kat için KESİT kaydırıcısını kullanın'); return true; }
    const p = hitToPlan(h);
    if (S.tool.type === 'floor') { setFloor([p.room], S.tool.id); return true; }
    if (S.tool.type === 'item') {
      const o = {id: uid(), kind: S.tool.kind, level: p.level, x: p.x, y: p.y, rot: S.tool.rot};
      S.design.objects.push(o); const obj = await spawnObject(o); select(obj); save(); summary();
      if (!ev.shiftKey) cancelTool();  // Shift ile art arda yerleştir
    }
    return true;
  }
  function setFloor(rooms, id) {
    for (const r of rooms) {
      S.design.floors[r.name] = id;
      const m = S.floorMeshes.find(x => x.userData.room === r); if (m) { if (S.hl === m) highlight(null); m.material = floorMat(id); }
    }
    save(); summary();
  }
  function currentLevel() {
    if (isWalking()) return ctx.walkLevel();
    const lv = V.nLv || [], i = +$('#lv').value - 1; const floors = lv.filter(n => (V.elements || []).some(e => e.type === 'slab' && e.role === 'floor' && e.level === n));
    return floors.includes(lv[i]) ? lv[i] : floors[floors.length - 1];
  }

  // ------------------------------------------------------------------ örnek döşeme
  function doorPoints(level) {
    const pts = [];
    for (const w of (V.elements || []).filter(e => e.type === 'wall' && e.level === level)) {
      const [x0, y0] = w.start, [x1, y1] = w.end, L = Math.hypot(x1 - x0, y1 - y0) || 1, ux = (x1 - x0) / L, uy = (y1 - y0) / L;
      for (const o of (w.openings || []).filter(o => o.kind === 'door')) { const s = o.offset + o.width / 2; pts.push([x0 + ux * s, y0 + uy * s]); }
    }
    return pts;
  }
  const ROT = {S: Math.PI, N: 0, W: Math.PI / 2, E: -Math.PI / 2};  // kenara sırtını veren nesnenin önü oda içine
  function edgesOf(r, doors) {
    const xs = r.points.map(p => p[0]), ys = r.points.map(p => p[1]);
    const b = {x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys)};
    const near = (e) => doors.some(([x, y]) => e === 'S' ? Math.abs(y - b.y0) < .35 && x > b.x0 - .1 && x < b.x1 + .1 : e === 'N' ? Math.abs(y - b.y1) < .35 && x > b.x0 - .1 && x < b.x1 + .1
      : e === 'W' ? Math.abs(x - b.x0) < .35 && y > b.y0 - .1 && y < b.y1 + .1 : Math.abs(x - b.x1) < .35 && y > b.y0 - .1 && y < b.y1 + .1);
    const len = e => (e === 'S' || e === 'N') ? b.x1 - b.x0 : b.y1 - b.y0;
    return {b, edges: ['S', 'N', 'W', 'E'].map(e => ({e, len: len(e), door: near(e)}))};
  }
  function against(b, e, t, depth, rot0 = 0) {  // e kenarına sırtını ver, kenar boyunca t∈[0,1]
    const m = .02;
    if (e === 'S') return {x: b.x0 + (b.x1 - b.x0) * t, y: b.y0 + depth / 2 + m, rot: ROT.S + rot0};
    if (e === 'N') return {x: b.x0 + (b.x1 - b.x0) * t, y: b.y1 - depth / 2 - m, rot: ROT.N + rot0};
    if (e === 'W') return {x: b.x0 + depth / 2 + m, y: b.y0 + (b.y1 - b.y0) * t, rot: ROT.W + rot0};
    return {x: b.x1 - depth / 2 - m, y: b.y0 + (b.y1 - b.y0) * t, rot: ROT.E + rot0};
  }
  const opposite = {S: 'N', N: 'S', W: 'E', E: 'W'};
  // ------------------------------------------------------------------ otomatik dekor: planı değiştirmez, ayrı katman (decor: true)
  const SOFA_W = {kanepe: 2.3, kanepe_2li: 1.8, kanepe_l: 2.9}, TABLE_H = {sehpa_yuvarlak: .42, modern_coffee_table_01: .39};
  const front = o => [Math.sin(o.rot || 0), -Math.cos(o.rot || 0)];  // nesnenin önü (plan)
  function planBoxes(level) {  // yerleşik nesnelerin plan sınır kutuları (seviye grubunun yerel x, −z)
    const out = [];
    for (const o of S.design.objects.filter(o => o.level === level && !o.decor && o.kind !== 'hali')) {
      const obj = S.objs.get(o.id); if (!obj?.parent) continue;
      const b = new THREE.Box3().setFromObject(obj), a = obj.parent.worldToLocal(b.min.clone()), c = obj.parent.worldToLocal(b.max.clone());
      out.push({x0: Math.min(a.x, c.x), x1: Math.max(a.x, c.x), y0: Math.min(-a.z, -c.z), y1: Math.max(-a.z, -c.z), top: Math.max(a.y, c.y) - levelZ(level)});
    }
    return out;
  }
  async function autoDecor(level) {
    level = level || currentLevel(); if (!level) return;
    S.design.objects = S.design.objects.filter(o => !(o.decor && o.level === level));
    await restoreObjects();
    const rooms = (V.elements || []).filter(e => e.type === 'room' && e.level === level), doors = doorPoints(level), boxes = planBoxes(level);
    const objs = S.design.objects.filter(o => o.level === level), plan = [];
    const add = (kind, x, y, rot = 0, h = 0, extra = {}) => plan.push({id: uid(), kind, level, x: +x.toFixed(3), y: +y.toFixed(3), rot: +rot.toFixed(4), h, decor: true, ...extra});
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    for (const r of rooms) {
      const n = r.name.split('/').pop(), mine = objs.filter(o => inPoly([o.x, o.y], r.points));
      // oturma grubu: halı sehpanın altında, ana kanepeye paralel; sehpaya küçük bitki
      const sofas = mine.filter(o => SOFA_W[o.kind]).sort((a, b) => (b.w ?? SOFA_W[b.kind]) - (a.w ?? SOFA_W[a.kind]));
      const table = mine.find(o => TABLE_H[o.kind] && (o.kind !== 'sehpa_yuvarlak' || (o.d ?? .9) >= .8));
      if (sofas.length) {
        const s = sofas[0], [fx, fy] = front(s), sw = s.w ?? SOFA_W[s.kind];
        const c = table ? [table.x, table.y] : [s.x + fx * 1.2, s.y + fy * 1.2];
        const dist = Math.abs((c[0] - s.x) * fx + (c[1] - s.y) * fy);
        add('hali', c[0], c[1], s.rot || 0, 0, {w: +clamp(sw + .6, 2, 3.4).toFixed(2), d: +clamp(dist * 2 + .2, 1.6, 3.2).toFixed(2)});
        if (table) add('potted_plant_04', table.x + .12, table.y - .1, 0, TABLE_H[table.kind]);
      }
      // yemek masası: ortada süs yoksa küçük bitki
      for (const t of mine.filter(o => o.kind === 'yemek_masasi' && !o.orta)) add('potted_plant_04', t.x, t.y, 0, .77);
      // yatak: altında halı (ayak tarafına kaydırılmış), ayak ucunda örtü
      for (const b of mine.filter(o => o.kind === 'yatak_cift' || o.kind === 'yatak_tek')) {
        const [fx, fy] = front(b), bw = (b.w ?? (b.kind === 'yatak_cift' ? 1.6 : .9)) + .1, L = (b.d ?? 2.18);
        add('hali', b.x + fx * .35, b.y + fy * .35, b.rot || 0, 0, {w: +(bw + 1.2).toFixed(2), d: b.kind === 'yatak_cift' ? 2.2 : 1.8});
        add('yatak_ortusu', b.x + fx * (L / 2 - .45), b.y + fy * (L / 2 - .45), b.rot || 0, 0, {w: +(bw + .04).toFixed(2)});
      }
      // boş köşeye saksı bitkisi (salon 2, yatak odası 1): köşe nesnesiz, kapıdan uzak, oda içinde
      const want = /Salon/.test(n) ? 2 : /Yatak|Oda/.test(n) ? 1 : 0;
      if (want) {
        const xs = r.points.map(p => p[0]), ys = r.points.map(p => p[1]), m = .38;
        const corners = [[Math.min(...xs) + m, Math.min(...ys) + m], [Math.max(...xs) - m, Math.min(...ys) + m], [Math.max(...xs) - m, Math.max(...ys) - m], [Math.min(...xs) + m, Math.max(...ys) - m]];
        let placed = 0;
        for (const [x, y] of corners) {
          if (placed >= want || !inPoly([x, y], r.points)) continue;
          if (doors.some(([dx, dy]) => Math.hypot(dx - x, dy - y) < 1.1)) continue;
          if (boxes.some(b => x > b.x0 - .32 && x < b.x1 + .32 && y > b.y0 - .32 && y < b.y1 + .32)) continue;
          add('potted_plant_02', x, y, (placed * 1.7) % 6.28); placed++;
          boxes.push({x0: x - .35, x1: x + .35, y0: y - .35, y1: y + .35});  // TV ünitesi vb. sonraki dekor buna çarpmasın
        }
      }
    }
    for (const r of rooms) wallDecor(r, level, boxes, doors, add);
    S.design.objects.push(...plan);
    await restoreObjects(); save(); summary();
    return plan.length;
  }
  // duvardaki açıklıklar: bir noktanın etrafında [s−hw, s+hw] aralığı kapı/pencereyle kesişiyor mu (duvar ekseni 0,25 m içinde)
  function wallBlocked(level, x, y, hw, windows = true) {
    for (const w of (V.elements || []).filter(e => e.type === 'wall' && e.level === level)) {
      const [x0, y0] = w.start, [x1, y1] = w.end, L = Math.hypot(x1 - x0, y1 - y0) || 1, ux = (x1 - x0) / L, uy = (y1 - y0) / L;
      const s = (x - x0) * ux + (y - y0) * uy, n = -(x - x0) * uy + (y - y0) * ux;
      if (Math.abs(n) > (w.thickness || .2) / 2 + .25 || s < -hw || s > L + hw) continue;
      if ((w.openings || []).some(o => (windows || o.kind === 'door') && o.offset < s + hw + .1 && o.offset + o.width > s - hw - .1)) return true;
    }
    return false;
  }
  // (x,y)'den (dx,dy) yönünde oda poligonunun ilk kenarı
  function rayWall(r, x, y, dx, dy) {
    let best = null;
    const P = r.points;
    for (let i = 0; i < P.length; i++) {
      const [ax, ay] = P[i], [bx_, by] = P[(i + 1) % P.length], ex = bx_ - ax, ey = by - ay, den = dx * ey - dy * ex;
      if (Math.abs(den) < 1e-9) continue;
      const t = ((ax - x) * ey - (ay - y) * ex) / den, u = ((ax - x) * dy - (ay - y) * dx) / den;
      if (t > .05 && u >= 0 && u <= 1 && (!best || t < best.t)) { const L = Math.hypot(ex, ey); best = {t, x: x + dx * t, y: y + dy * t, ux: ex / L, uy: ey / L}; }
    }
    return best;
  }
  function wallDecor(r, level, boxes, doors, add) {
    const n = r.name.split('/').pop(), mine = S.design.objects.filter(o => o.level === level && !o.decor && inPoly([o.x, o.y], r.points));
    const hit = (x, y, hw, hd, above = 0) => boxes.some(b => (b.top ?? 9) > above && x + hw > b.x0 && x - hw < b.x1 && y + hd > b.y0 && y - hd < b.y1);
    const sofa = mine.filter(o => SOFA_W[o.kind]).sort((a, b) => (b.w ?? SOFA_W[b.kind]) - (a.w ?? SOFA_W[a.kind]))[0];
    let art = 0;
    if (sofa) {
      const [fx, fy] = front(sofa), table = mine.find(o => TABLE_H[o.kind]) || {x: sofa.x + fx * 1.2, y: sofa.y + fy * 1.2};
      // TV: kanepenin karşı duvarı, sehpa hizasında; kapı/pencereye denk gelirse duvar boyunca kaydır
      const wl = rayWall(r, table.x, table.y, fx, fy);
      if (wl) for (const off of [0, .3, -.3, .6, -.6, .9, -.9, 1.2, -1.2]) {
        const cx = wl.x + wl.ux * off, cy = wl.y + wl.uy * off, rot = (sofa.rot || 0) + Math.PI;
        const px = cx - fx * .24, py = cy - fy * .24, alongX = Math.abs(wl.ux) > .5, hw = alongX ? 1.01 : .24, hd = alongX ? .24 : 1.01;
        if (!inPoly([px, py], r.points) || wallBlocked(level, cx, cy, .75)) continue;
        const unit = !wallBlocked(level, cx, cy, 1.05, false) && !hit(px, py, hw, hd) && !doors.some(([dx, dy]) => Math.hypot(dx - px, dy - py) < 1.5);
        if (unit) add('tv_unitesi', px, py, rot);
        add('tv', cx - fx * .08, cy - fy * .08, rot, unit ? 0 : .1);
        break;
      }
      // tablo: kanepenin sırtındaki duvara
      const back = .46 + .02, wx = sofa.x - fx * back, wy = sofa.y - fy * back;
      if (!wallBlocked(level, wx, wy, .7)) { add('tablo', wx + fx * .015, wy + fy * .015, sofa.rot || 0, 1.25, {w: 1.2, hy: .75, v: art++}); }
    }
    for (const b of mine.filter(o => o.kind === 'yatak_cift' || o.kind === 'yatak_tek')) {
      const [fx, fy] = front(b), back = 1.13 * (b.d ?? 2.18) / 2.18 + .02, wx = b.x - fx * back, wy = b.y - fy * back;
      const w = b.kind === 'yatak_cift' ? 1.0 : .6;
      if (!wallBlocked(level, wx, wy, w / 2 + .05)) add('tablo', wx + fx * .015, wy + fy * .015, b.rot || 0, 1.3, {w, hy: .6, v: art++});
    }
    if (/Banyo/.test(n)) {
      // havlu askısı lavabonun yanında aynı duvarda; duşun önüne paspas
      const lav = mine.find(o => o.kind === 'lavabo');
      if (lav) {
        const [fx, fy] = front(lav), ux = -fy, uy = fx, wx = lav.x - fx * .24, wy = lav.y - fy * .24;
        for (const [side, d] of [[1, .8], [-1, .8], [1, .65], [-1, .65]]) {  // askı 0,8–1,3 m: altındaki klozet engel değil
          const cx = wx + ux * side * d, cy = wy + uy * side * d;
          if (!inPoly([cx + fx * .1, cy + fy * .1], r.points) || wallBlocked(level, cx, cy, .35) || hit(cx + fx * .06, cy + fy * .06, .3, .1, .85)) continue;
          add('havlu', cx, cy, lav.rot || 0, .75); break;
        }
      }
      const dus = mine.find(o => o.kind === 'dus');
      if (dus) { const [fx, fy] = front(dus), d = (dus.d ?? .9) / 2 + .32; add('hali', dus.x + fx * d, dus.y + fy * d, dus.rot || 0, 0, {w: .8, d: .5}); }
    }
  }
  async function clearDecor(level) {
    level = level || currentLevel();
    S.design.objects = S.design.objects.filter(o => !(o.decor && o.level === level));
    await restoreObjects(); select(null); save(); summary();
  }
  async function autoFurnish(level) {
    level = level || currentLevel(); if (!level) return;
    S.design.objects = S.design.objects.filter(o => o.level !== level);
    const rooms = (V.elements || []).filter(e => e.type === 'room' && e.level === level), doors = doorPoints(level);
    const plan = [], dims = {};
    for (const k of ['kanepe_l', 'tv_unitesi', 'modern_coffee_table_01', 'potted_plant_02', 'modern_arm_chair_01', 'side_table_01'])
      try { dims[k] = footprint(await loadItem(k)); } catch { /* model yoksa varsayılan derinlik */ }
    const dep = k => dims[k] ? Math.min(dims[k].x, dims[k].z) : .6;
    const add = (kind, p, h = 0) => plan.push({id: uid(), kind, level, x: p.x, y: p.y, rot: p.rot, h});
    for (const r of rooms) {
      const n = r.name.split('/').pop(), {b, edges} = edgesOf(r, doors);
      const solid = edges.filter(x => !x.door).sort((a, c) => c.len - a.len);
      const W = b.x1 - b.x0, D = b.y1 - b.y0;
      const pick = (pref) => pref.find(Boolean) || edges[0];
      if (/Salon/.test(n)) {
        const long = pick(solid), opp = edges.find(x => x.e === opposite[long.e]);
        add('kanepe_l', against(b, long.e, .5, .95));
        add('tv_unitesi', against(b, opp.e, .5, .42));
        add('tv', against(b, opp.e, .5, .1));
        const c = {x: (b.x0 + b.x1) / 2, y: (b.y0 + b.y1) / 2};
        add('hali', {...c, rot: against(b, long.e, .5, 1).rot}); add('modern_coffee_table_01', {...c, rot: against(b, long.e, .5, 1).rot});
        add('potted_plant_02', against(b, long.e, .08, dep('potted_plant_02')));
        if (/Açık Mutfak/.test(n)) { const s2 = solid[1] || long; add('mutfak', against(b, s2.e, .5, .62)); }
        else if (Math.min(W, D) > 3.2) add('modern_arm_chair_01', against(b, solid[1]?.e || opp.e, .8, dep('modern_arm_chair_01')));
      } else if (/Yatak/.test(n)) {
        const doorE = edges.find(x => x.door)?.e, head = doorE ? opposite[doorE] : pick(solid).e;
        const dbl = Math.min(W, D) >= 2.9;
        add(dbl ? 'yatak_cift' : 'yatak_tek', against(b, head, .5, 2.1));
        add('side_table_01', against(b, head, dbl ? .12 : .8, dep('side_table_01')));
        const side = edges.find(x => x.e !== head && x.e !== opposite[head] && !x.door) || edges.find(x => x.e !== head);
        if (side && side.len > 2) add('gardirop', against(b, side.e, .75, .6));
      } else if (/Banyo/.test(n)) {
        const doorE = edges.find(x => x.door)?.e, back = doorE ? opposite[doorE] : pick(solid).e;
        const sides = edges.filter(x => x.e !== back && x.e !== opposite[back]);
        add('klozet', against(b, back, .25, .66));
        add('lavabo', against(b, back, .72, .48));
        const s = sides.find(x => !x.door) || sides[0];
        if (Math.max(W, D) > 2.6 && Math.min(W, D) > 1.6) add('kuvet', against(b, s.e, .3, .75)); else add('dus', against(b, s.e, .25, .9));
      } else if (/Mutfak/.test(n)) {
        const doorE = edges.find(x => x.door)?.e, wall = (doorE ? edges.find(x => x.e === opposite[doorE]) : null) || pick(solid);
        add('mutfak', against(b, wall.e, wall.len > 3.2 ? .42 : .5, .62));
        if (wall.len > 3.2) add('buzdolabi', against(b, wall.e, .9, .7));
        else { const s = solid.find(x => x.e !== wall.e); if (s) add('buzdolabi', against(b, s.e, .85, .7)); }
      }
    }
    for (const r of rooms) S.design.floors[r.name] ??= /Salon|Yatak/.test(r.name) ? 'herringbone_parquet' : defaultFloor(r.name);
    for (const m of S.floorMeshes) m.material = floorMat(S.design.floors[m.userData.room.name] || defaultFloor(m.userData.room.name));
    S.design.objects.push(...plan);
    await restoreObjects(); save(); summary();
  }

  // ------------------------------------------------------------------ kayıt
  function save() {
    clearTimeout(S.saveT);
    S.saveT = setTimeout(() => { if (S.pid) api(`/api/projects/${S.pid}/interior`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(S.design)}).catch(() => {}); }, 400);
  }
  async function load(pid) {
    S.pid = pid;
    try { S.design = {floors: {}, paint: 'kirik_beyaz', objects: [], ...(await api(`/api/projects/${pid}/interior`))}; }
    catch { S.design = {floors: {}, paint: 'kirik_beyaz', objects: []}; }
    if (S.real) { buildExtras(); applyPaint(); await restoreObjects(); }
    applyDemolish(); summary();
  }

  // ------------------------------------------------------------------ panel
  let tab = 'zemin';
  function editHint() { const lv = currentLevel(); if (lv && !isWalking()) hint(`Düzenlenen kat: ${lv.startsWith('Kat ') ? lv.split(' ')[1] + '. normal kat' : lv} — kat değiştirmek için KESİT`); }
  function hint(t) { const h = $('#ihint'); if (h) { h.textContent = t; h.style.display = t ? 'block' : 'none'; } }
  function summary() {
    const el = $('#isum'); if (!el) return;
    const tot = {};
    for (const r of (V.elements || []).filter(e => e.type === 'room')) {
      const id = S.design.floors[r.name] || defaultFloor(r.name); tot[id] = (tot[id] || 0) + polyArea(r.points);
    }
    el.innerHTML = Object.entries(tot).sort((a, b) => b[1] - a[1]).map(([id, a]) => `<div><span>${esc(FLOORS.find(f => f.id === id)?.name || id)}</span><b>${n2(a)} m²</b></div>`).join('')
      + `<div class="muted"><span>Yerleştirilen nesne</span><b>${S.design.objects.length}</b></div>`;
  }
  function renderSel() {
    const el = $('#isel'); if (!el) return;
    if (!S.sel) { el.innerHTML = ''; return; }
    const it = ITEMS.find(i => i.id === S.sel.userData.item.kind);
    el.innerHTML = `<div class="selbar"><b>${esc(it?.name || '')}</b><button class="vbtn" id="irot">⟳ 90°</button><button class="vbtn" id="idel">✕ SİL</button></div>`;
    $('#irot').onclick = () => rotateSel(); $('#idel').onclick = deleteSel;
  }
  function renderPanel() {
    const body = $('#ibody'); if (!body) return;
    $$('#itabs button').forEach(b => b.classList.toggle('on', b.dataset.it === tab));
    if (tab === 'zemin') {
      body.innerHTML = `<div class="sw">${FLOORS.map(f => `<button data-f="${f.id}" class="${S.tool?.id === f.id ? 'on' : ''}"><img src="${A}tex/${f.id}/thumb.jpg" alt=""><span>${f.name}</span></button>`).join('')}</div>
        <div class="irow"><button class="vbtn" id="iall1">BU KATA UYGULA</button><button class="vbtn" id="iallA">TÜM KATLARA</button></div>
        <p class="inote">Kaplamayı seçin, sonra odanın zeminine tıklayın.</p><p class="sec-t" style="margin-top:12px">KAPLAMA METRAJI</p><div class="isum" id="isum"></div>`;
      $$('[data-f]').forEach(b => b.onclick = () => { armFloor(b.dataset.f); renderPanel(); });
      const bulk = all => { const id = S.tool?.type === 'floor' ? S.tool.id : null; if (!id) { hint('Önce bir kaplama seçin'); return; }
        const lv = currentLevel(); setFloor((V.elements || []).filter(e => e.type === 'room' && (all || e.level === lv)), id); };
      $('#iall1').onclick = () => bulk(false); $('#iallA').onclick = () => bulk(true);
      summary();
    } else if (tab === 'duvar') {
      body.innerHTML = `<div class="sw paint">${PAINTS.map(p => `<button data-p="${p.id}" class="${S.design.paint === p.id ? 'on' : ''}"><i style="background:#${p.c.toString(16).padStart(6, '0')}"></i><span>${p.name}</span></button>`).join('')}</div>
        <p class="inote">Boya tüm duvar yüzeylerine uygulanır.</p>
        <p class="sec-t" style="margin-top:14px">YIKIM · BÖLME DUVAR</p>
        <div class="irow"><button class="vbtn walkbtn ${S.tool?.type === 'demolish' ? 'on' : ''}" id="idemo">⛏ DUVAR YIK</button><button class="vbtn" id="idemu">TÜMÜNÜ GERİ AL</button></div>
        <p class="inote">Duvarın üstüne gelin: taşıyıcı (dış, perde, ≥ 18 cm) <b style="color:#ff6060">kırmızı</b> yanar ve yıkılamaz, bölme duvar <b style="color:#ffb060">turuncu</b> yanar.
        Yıkılan: ${(S.design.demolished || []).length} duvar · ${n2(demolishedArea())} m². Statik kararlar mimar/mühendis onayı gerektirir.</p>`;
      $$('[data-p]').forEach(b => b.onclick = () => { S.design.paint = b.dataset.p; applyPaint(); save(); renderPanel(); });
      $('#idemo').onclick = () => { if (S.tool?.type === 'demolish') cancelTool(); else { cancelTool(); S.tool = {type: 'demolish'}; hint('Yıkmak için bölme duvara tıklayın · Esc bitir'); } renderPanel(); };
      $('#idemu').onclick = () => { S.design.demolished = []; buildExtras(); buildLeaves(); applyDemolish(); save(); renderPanel(); };
    } else {
      const cats = [...new Set(ITEMS.map(i => i.cat))];
      body.innerHTML = `<div class="irow"><button class="vbtn walkbtn" id="iauto">✦ ÖRNEK DÖŞE (BU KAT)</button><button class="vbtn" id="iclr">TEMİZLE</button></div>
        <div class="irow"><button class="vbtn walkbtn" id="idecor">❀ DEKOR EKLE (BU KAT)</button><button class="vbtn" id="idclr">DEKORU KALDIR</button></div>
        <p class="inote">Dekor planı değiştirmez: halı, bitki, TV, tablo, havlu, yatak örtüsü, masa/sehpa süsü ayrı katmandır.</p>
        ${cats.map(c => `<p class="sec-t" style="margin:12px 0 6px">${c.toUpperCase()}</p><div class="sw obj">${ITEMS.filter(i => i.cat === c).map(i =>
          `<button data-i="${i.id}" class="${S.tool?.kind === i.id ? 'on' : ''}">${i.model ? `<img src="${A}models/${i.id}/thumb.png" alt="">` : `<em>${ICON[i.id] || '◻'}</em>`}<span>${i.name}</span></button>`).join('')}</div>`).join('')}
        <p class="inote">Seç → zemine tıkla. Shift+tık art arda yerleştirir. Nesneyi seçip sürükle; R döndür, Del sil.</p>`;
      $$('[data-i]').forEach(b => b.onclick = () => { armItem(b.dataset.i); renderPanel(); });
      $('#iauto').onclick = async e => { e.target.disabled = true; e.target.textContent = 'DÖŞENİYOR…'; await autoFurnish(); renderPanel(); };
      $('#idecor').onclick = async e => { e.target.disabled = true; e.target.textContent = 'EKLENİYOR…'; const k = await autoDecor(); hint(`${k} dekor nesnesi eklendi`); renderPanel(); };
      $('#idclr').onclick = async () => { await clearDecor(); renderPanel(); };
      $('#iclr').onclick = () => { const lv = currentLevel(); S.design.objects = S.design.objects.filter(o => o.level !== lv); restoreObjects(); select(null); save(); summary(); };
    }
  }
  function openPanel(on) {
    $('#vp').classList.toggle('editing', on);
    if (on) { ctx.setModeReal(); ctx.openInterior?.(); ctx.focusEdit?.(); ctx.viewOffset?.(true); renderPanel(); editHint(); }
    else { ctx.viewOffset?.(false); cancelTool(); select(null); }
  }

  // ------------------------------------------------------------------ olaylar
  const cv = V.R.domElement;
  cv.addEventListener('pointermove', onMove);
  cv.addEventListener('pointerdown', onDown, true);
  window.addEventListener('pointerup', onUp);
  cv.addEventListener('click', async ev => { if (await onClick(ev)) { ev.stopImmediatePropagation(); renderPanel(); } }, true);
  document.addEventListener('keydown', ev => {
    if (!S.real || ['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
    if (ev.code === 'KeyR' && (S.sel || S.tool?.type === 'item')) { rotateSel(ev.shiftKey ? -Math.PI / 12 : Math.PI / 2); ev.preventDefault(); }
    if ((ev.code === 'Delete' || ev.code === 'Backspace') && S.sel) { deleteSel(); ev.preventDefault(); }
    if (ev.code === 'Escape' && (S.tool || S.sel)) { cancelTool(); select(null); renderPanel(); }
  });
  $$('#itabs button').forEach(b => b.onclick = () => { tab = b.dataset.it; cancelTool(); renderPanel(); });
  $('#iclose').onclick = () => openPanel(false);

  // ------------------------------------------------------------------ Cycles'a gönderim: sahne GLB + iş tanımı
  // maket: seçili kat ve altı, çatısız; duvar başında koyu kesit kapağı, bej taş zemin, binaya oturan ~66° eğik kuşbakışı kamera
  function maketStage() {
    const lv = currentLevel(), names = V.nLv || [], keep = names.slice(0, names.indexOf(lv) + 1);
    const cut = V.levels.filter(L => !L.site && !keep.includes(L.name)).map(L => ({L, par: L.group.parent}));
    cut.forEach(({L, par}) => par?.remove(L.group));
    const capMat = new THREE.MeshStandardMaterial({color: 0x34373b, roughness: .85}), caps = [];
    for (const w of (V.elements || []).filter(e => e.type === 'wall' && keep.includes(e.level))) {
      const g = levelGroup(w.level); if (!g) continue;
      const [x0, y0] = w.start, [x1, y1] = w.end, L = Math.hypot(x1 - x0, y1 - y0), t = w.thickness || .2; if (L < 1e-3) continue;
      const m = new THREE.Mesh(bx(L + t, .025, t + .004), capMat);
      m.position.set((x0 + x1) / 2, (w.base_z || 0) + (w.height || 2.8) + .0125, -(y0 + y1) / 2); m.rotation.y = Math.atan2(y1 - y0, x1 - x0);
      g.add(m); caps.push(m);
    }
    const stone = new THREE.MeshStandardMaterial({color: 0xcdbba0, roughness: .9}), gMat = S.ground?.material, siteC = V.mat.site.color.getHex();
    if (S.ground) S.ground.material = stone;
    V.mat.site.color.set(0xcdbba0);
    // kamera: kalan katların sınır kutusuna güneyden ~60° eğimle, 16:9 kadraja sığdır
    const box = new THREE.Box3(); V.levels.filter(L => !L.site && keep.includes(L.name)).forEach(L => box.expandByObject(L.group));
    const c = box.getCenter(new THREE.Vector3()), sz = box.getSize(new THREE.Vector3()), el = THREE.MathUtils.degToRad(66), fov = 35, asp = 16 / 9;
    const tv = Math.tan(THREE.MathUtils.degToRad(fov / 2)), halfV = (sz.z * Math.sin(el) + sz.y * Math.cos(el)) / 2 * 1.12, halfH = sz.x / 2 * 1.1;
    const dist = Math.max(halfV / tv, halfH / (tv * asp)) + sz.y;
    const cam = new THREE.PerspectiveCamera(fov, asp, .1, 1000); c.y = box.min.y;
    cam.position.set(c.x, c.y + dist * Math.sin(el), c.z + dist * Math.cos(el)); cam.lookAt(c); cam.updateMatrixWorld();
    const R = Math.max(sz.x, sz.z) * 1.5 + 10;
    const job = {camera: {matrix: cam.matrixWorld.elements.slice(), fov, aspect: asp}, ...(S.night ? {} : {lights: [], sun_energy: 2.8, exposure: .85}), hq: true, preset: 'maket',
      ...(S.night ? {} : {sun: {pos: [c.x - R * .8, c.y + R * 1.2, c.z - R * .5], target: [c.x, c.y, c.z]}})};
    const undo = () => { caps.forEach(m => m.parent?.remove(m)); cut.forEach(({L, par}) => par?.add(L.group)); if (S.ground) S.ground.material = gMat; V.mat.site.color.set(siteC); };
    return {job, undo};
  }
  async function exportForRender(kind, opts = {}) {
    if (!S.real) await setReal(true);
    await S.restoring;  // tüm mobilya yüklenmeden sahne gönderme
    const {GLTFExporter} = await import('three/addons/exporters/GLTFExporter.js');
    const vis = V.levels.map(L => L.group.visible);
    V.levels.forEach(L => { L.group.visible = true; L.group.position.y = 0; L.group.scale.y = 1; });  // tavanlar dahil tüm katlar
    const stage = opts.maket ? maketStage() : null;
    const aux = [S.selBox, S.ghost, S.hl].filter(Boolean); const auxVis = aux.map(o => o.visible);
    if (S.hl) highlight(null);
    aux.forEach(o => o.visible = false);
    V.root.updateMatrixWorld(true);
    // userData döngüsel referans içerir (nesne ↔ sahibi); exporter JSON'a çevirmeye çalışıp binlerce kez hata üretir → geçici boşalt
    const ud = []; [V.root, S.ground].forEach(r => r.traverse(o => { ud.push([o, o.userData]); o.userData = {}; }));
    let glb;
    try { glb = await new GLTFExporter().parseAsync([V.root, S.ground], {binary: true, onlyVisible: true, maxTextureSize: 2048}); }
    finally { ud.forEach(([o, d]) => o.userData = d); stage?.undo(); V.levels.forEach((L, i) => L.group.visible = vis[i]); aux.forEach((o, i) => o.visible = auxVis[i]); }
    const rooms = (V.elements || []).filter(e => e.type === 'room');
    const W3 = (x, y, z) => toWorld(x, y, z).toArray().map(v => +v.toFixed(4));
    const lights = rooms.filter(r => !/Merdiven|Şaft|Asansör/.test(r.name)).map(r => {
      const xs = r.points.map(p => p[0]), ys = r.points.map(p => p[1]), [cx, cy] = centroid(r.points);
      return {pos: W3(cx, cy, (r.z || 0) + (r.height || 2.8) - .02), w: Math.max(...xs) - Math.min(...xs), d: Math.max(...ys) - Math.min(...ys)};
    });
    const job = {kind, sun: S.sun ? {pos: S.sun.position.toArray(), target: S.sun.target.position.toArray()} : null, lights};
    if (S.night) Object.assign(job, {sun_energy: .03, sky: .04, room_light: 16, exposure: 1.0});
    if (kind === 'still') { V.C.updateMatrixWorld(); job.camera = {matrix: V.C.matrixWorld.elements.slice(), fov: V.C.fov, aspect: V.C.aspect}; }
    if (stage) Object.assign(job, stage.job);
    return {glb, job};
  }

  return {
    setReal, load, openPanel, resizeAO, autoFurnish, autoDecor, clearDecor, exportForRender,
    grow, tick, toggleDoor, doorSegs, isDemolished, setSun,
    async measure(kind) { const b = new THREE.Box3().setFromObject(await loadItem(kind)); const r = v => +v.toFixed(3);
      return {min: [r(b.min.x), r(b.min.y), r(b.min.z)], max: [r(b.max.x), r(b.max.y), r(b.max.z)]}; },
    items: () => ITEMS.map(i => i.id),
    refreshHint() { if ($('#vp').classList.contains('editing') && !S.tool) editHint(); },
    active: () => !!(S.tool || S.sel || S.drag || $('#vp').classList.contains('editing')),
    onBuild() {
      S.floorMeshes = []; S.extras = []; S.leaves = []; S.objs.clear(); select(null);
      if (S.real) { V.root.traverse(o => { if (o.isLine || o.isLineSegments) o.visible = false; if (o.isMesh) o.castShadow = o.receiveShadow = true; }); placeSun(); buildExtras(); surfaceMaterials(true); buildTrees(); restoreObjects(); }
    },
    get real() { return S.real; },
  };
}
