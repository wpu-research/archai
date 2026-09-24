// İç mekân: gerçekçi render (PBR + HDRI + gölge + AO) ve düzenleyici (zemin kaplaması, boya, nesne yerleştirme).
// Varlıklar Poly Haven CC0 (assets/LICENSES.json); vitrifiye/mutfak/yatak parametrik üretilir.
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RGBELoader} from 'three/addons/loaders/RGBELoader.js';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';
import {GTAOPass} from 'three/addons/postprocessing/GTAOPass.js';

export function createInterior(ctx) {
  const {THREE, V, $, $$, n2, api, getProject, toWorld, polyArea, centroid, inPoly, isWalking} = ctx;
  const A = 'assets/';
  const texLoader = new THREE.TextureLoader(), gltf = new GLTFLoader();

  // ------------------------------------------------------------------ katalog
  const FLOORS = [
    {id: 'laminate_floor_02', name: 'Laminat parke', tile: 2.0},
    {id: 'herringbone_parquet', name: 'Balıksırtı parke', tile: 1.6},
    {id: 'oak_wood_planks', name: 'Meşe masif', tile: 2.2},
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
    {id: 'dus', name: 'Duş kabini', cat: 'Banyo'}, {id: 'kuvet', name: 'Küvet', cat: 'Banyo'},
    {id: 'mutfak', name: 'Mutfak tezgâhı 2,4 m', cat: 'Mutfak'}, {id: 'buzdolabi', name: 'Buzdolabı', cat: 'Mutfak'},
    {id: 'yatak_cift', name: 'Çift kişilik yatak', cat: 'Yatak odası'}, {id: 'yatak_tek', name: 'Tek kişilik yatak', cat: 'Yatak odası'},
    {id: 'gardirop', name: 'Gardırop', cat: 'Yatak odası'},
    {id: 'sofa_03', name: 'Kanepe', cat: 'Salon', model: true}, {id: 'ArmChair_01', name: 'Berjer', cat: 'Salon', model: true},
    {id: 'CoffeeTable_01', name: 'Orta sehpa', cat: 'Salon', model: true}, {id: 'Television_01', name: 'Televizyon', cat: 'Salon', model: true},
    {id: 'modern_wooden_cabinet', name: 'TV ünitesi / dolap', cat: 'Salon', model: true},
    {id: 'WoodenTable_01', name: 'Yemek masası', cat: 'Salon', model: true}, {id: 'WoodenChair_01', name: 'Sandalye', cat: 'Salon', model: true},
    {id: 'side_table_01', name: 'Komodin', cat: 'Yatak odası', model: true}, {id: 'Ottoman_01', name: 'Puf', cat: 'Salon', model: true},
    {id: 'potted_plant_02', name: 'Saksı bitkisi', cat: 'Salon', model: true},
  ];
  const ICON = {klozet: '🚽', lavabo: '🪞', dus: '🚿', kuvet: '🛁', mutfak: '🍳', buzdolabi: '🧊', yatak_cift: '🛏', yatak_tek: '🛏', gardirop: '🚪'};

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
    return texCache[id] = new THREE.MeshStandardMaterial({map: load('diff', true), normalMap: load('nor_gl'), roughnessMap: load('rough'),
      roughness: 1, normalScale: new THREE.Vector2(.6, .6)});
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
    ground: new THREE.MeshStandardMaterial({color: 0x6f7a5c, roughness: 1}),
    paving: new THREE.MeshStandardMaterial({color: 0xb5b0a6, roughness: .9}),
  };
  const oakTex = texLoader.load(`${A}tex/oak_wood_planks/diff.jpg`); oakTex.colorSpace = THREE.SRGBColorSpace;
  oakTex.wrapS = oakTex.wrapT = THREE.RepeatWrapping; M.oak.map = oakTex; M.oak.color.set(0xffffff);

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
    dus() {
      const g = G();
      part(g, rb(.9, .05, .9, .01), M.ceramic, 0, .025, 0);
      part(g, bx(.9, 1.95, .008), M.glass, 0, 1.03, .445);
      part(g, bx(.008, 1.95, .9), M.glass, .445, 1.03, 0);
      part(g, bx(.9, .02, .02), M.chrome, 0, 2.0, .445);
      part(g, bx(.02, .02, .9), M.chrome, .445, 2.0, 0);
      part(g, cyl(.012, .012, 1.1, 12), M.chrome, -.35, 1.5, -.43);
      part(g, cyl(.11, .11, .015), M.chrome, -.35, 2.02, -.32);
      part(g, bx(.02, .2, .02), M.chrome, -.35, 2.03, -.38).rotation.x = Math.PI / 2;
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
    mutfak() {
      const g = G(), L = 2.4, D = .6;
      part(g, bx(L, .1, D - .06), M.black, 0, .05, -.03);
      for (let i = 0; i < 4; i++) {
        const x = -L / 2 + .3 + i * .6;
        part(g, bx(.6, .72, D - .02), M.lacquer, x, .46, -.01);
        part(g, bx(.594, .7, .02), M.lacquer, x, .47, D / 2 - .01);
        part(g, bx(.4, .015, .015), M.steel, x, .79, D / 2 + .01);
        part(g, bx(.6, .7, .35), M.lacquer, x, 1.85, -D / 2 + .175);
        part(g, bx(.594, .68, .02), M.lacquer, x, 1.85, -D / 2 + .36);
        part(g, bx(.015, .3, .015), M.steel, x + .25, 1.62, -D / 2 + .375);
      }
      part(g, bx(L + .02, .04, D + .02), M.quartz, 0, .86, 0);
      part(g, bx(.5, .005, .4), M.steel, -.3, .882, .02);
      part(g, bx(.44, .004, .34), M.black, -.3, .885, .02);
      part(g, cyl(.012, .012, .3, 12), M.chrome, -.3, 1.03, -.22);
      part(g, bx(.58, .008, .5), M.black, .6, .884, .02);
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
    yatak_cift() { return bed(1.6); },
    yatak_tek() { return bed(.9); },
    gardirop() {
      const g = G(), W = 1.8;
      part(g, bx(W, 2.4, .6), M.lacquer, 0, 1.2, 0);
      for (let i = 0; i < 3; i++) {
        const x = -W / 2 + W / 6 + i * W / 3;
        part(g, bx(W / 3 - .006, 2.36, .02), M.lacquer, x, 1.2, .31);
        part(g, bx(.015, .5, .015), M.steel, x + (i === 2 ? -.25 : .25), 1.15, .325);
      }
      return g;
    },
  };
  function bed(w) {
    const g = G();
    part(g, rb(w + .1, .3, 2.1, .02), M.oak, 0, .15, 0);
    part(g, rb(w, .22, 2.0, .06), M.linen, 0, .41, 0);
    part(g, rb(w + .04, .06, 1.4, .03), M.duvet, 0, .53, .3);
    for (const x of (w > 1.2 ? [-w / 4, w / 4] : [0])) part(g, rb(.58, .13, .38, .06), M.linen, x, .58, -.72);
    part(g, rb(w + .16, 1.05, .1, .03), M.fabric, 0, .55, -1.08);
    return g;
  }

  // ------------------------------------------------------------------ model yükleme
  const modelCache = {};
  function loadItem(kind) {
    const it = ITEMS.find(i => i.id === kind);
    if (!it) return Promise.reject(new Error('bilinmeyen nesne ' + kind));
    if (!it.model) return Promise.resolve(FACTORY[kind]());
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
    // pencere kasaları + kapı kasaları
    for (const w of els.filter(e => e.type === 'wall')) {
      const g = levelGroup(w.level); if (!g) continue;
      const [x0, y0] = w.start, [x1, y1] = w.end, L = Math.hypot(x1 - x0, y1 - y0); if (L < 1e-3) continue;
      const ux = (x1 - x0) / L, uy = (y1 - y0) / L, ang = Math.atan2(uy, ux), zb = w.base_z || 0, T = w.thickness || .2;
      for (const o of w.openings || []) {
        const a = o.offset, b = a + o.width, door = o.kind === 'door', sill = door ? 0 : (o.sill ?? .9), top = sill + (o.height ?? (door ? 2.1 : 1.4));
        const fw = door ? .06 : .055, fd = door ? T + .02 : .07, mat = door ? M.lacquer : M.frame;
        const put = (s, zc, lw, lh) => {
          const m = new THREE.Mesh(bx(lw, lh, fd), mat), cx = x0 + ux * s, cy = y0 + uy * s;
          m.position.set(cx, zb + zc, -cy); m.rotation.y = ang; m.castShadow = m.receiveShadow = true; g.add(m); S.extras.push(m);
        };
        put(a + fw / 2, (sill + top) / 2, fw, top - sill); put(b - fw / 2, (sill + top) / 2, fw, top - sill);
        put((a + b) / 2, top - fw / 2, o.width, fw);
        if (!door) { put((a + b) / 2, sill + fw / 2, o.width, fw); if (o.width > 1.2) put((a + b) / 2, (sill + top) / 2, .04, top - sill - .1); }
      }
    }
  }
  function clearExtras() {
    for (const m of [...S.floorMeshes, ...S.extras]) m.parent?.remove(m);
    S.floorMeshes = []; S.extras = [];
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
      buildExtras();
      if (!S.ao) { S.ao = new GTAOPass(V.S, V.C, 1, 1); S.ao.blendIntensity = .9; V.comp.insertPass(S.ao, 1); }
      S.ao.enabled = true; V.bloom.enabled = false; resizeAO();
      restoreObjects();
    } else {
      if (S.saved) { swapMaterials(S.saved.face, S.saved.slab, S.saved.glass); V.R.toneMapping = S.saved.tm; V.R.toneMappingExposure = S.saved.exp; V.S.fog.density = S.saved.fog; }
      V.S.environment = null; V.S.background = null; V.R.shadowMap.enabled = false;
      V.S.remove(S.sun, S.sun?.target, S.ground, S.fill);
      V.mat.site.opacity = .035; V.mat.site.color.set(0x3cffa6); V.mat.site.depthWrite = false;
      clearExtras(); clearObjects(); cancelTool(); select(null);
      if (S.ao) S.ao.enabled = false; V.bloom.enabled = true;
    }
  }
  function placeSun() {
    if (!S.sun || !V.box) return;
    const s = V.box.getSize(new THREE.Vector3()), R = Math.max(s.x, s.z, s.y) * .75 + 6;
    S.sun.position.set(-R * .9, R * 1.3, R * .8); S.sun.target.position.set(0, 0, 0);
    Object.assign(S.sun.shadow.camera, {left: -R, right: R, top: R, bottom: -R, near: 1, far: R * 5}); S.sun.shadow.camera.updateProjectionMatrix();
  }
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
    try { obj = await loadItem(o.kind); } catch (e) { console.warn('nesne yüklenemedi', o.kind, e); return null; }
    obj.position.set(o.x, levelZ(o.level) + (o.h || 0), -o.y); obj.rotation.y = o.rot || 0;
    obj.userData.item = o; obj.traverse(m => { if (m.isMesh) { m.castShadow = m.receiveShadow = true; m.userData.owner = obj; } });
    g.add(obj); S.objs.set(o.id, obj); return obj;
  }
  const levelZ = n => ((V.elements || []).find(e => e.type === 'slab' && e.role === 'floor' && e.level === n) || {z: 0}).z;
  function clearObjects() { for (const o of S.objs.values()) o.parent?.remove(o); S.objs.clear(); }
  async function restoreObjects() { clearObjects(); for (const o of S.design.objects) await spawnObject(o); }
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
    const h = pick(ev, [V.root]);
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
  async function onClick(ev) {
    if (!S.real || !S.tool) return false;
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
  async function autoFurnish(level) {
    level = level || currentLevel(); if (!level) return;
    S.design.objects = S.design.objects.filter(o => o.level !== level);
    const rooms = (V.elements || []).filter(e => e.type === 'room' && e.level === level), doors = doorPoints(level);
    const plan = [], dims = {};
    for (const k of ['sofa_03', 'modern_wooden_cabinet', 'Television_01', 'CoffeeTable_01', 'potted_plant_02', 'ArmChair_01', 'side_table_01'])
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
        add('sofa_03', against(b, long.e, .5, dep('sofa_03')));
        add('modern_wooden_cabinet', against(b, opp.e, .5, dep('modern_wooden_cabinet')));
        add('Television_01', against(b, opp.e, .5, dep('modern_wooden_cabinet')), dims.modern_wooden_cabinet?.y || .5);
        const c = {x: (b.x0 + b.x1) / 2, y: (b.y0 + b.y1) / 2};
        add('CoffeeTable_01', {...c, rot: against(b, long.e, .5, 1).rot});
        add('potted_plant_02', against(b, long.e, .08, dep('potted_plant_02')));
        if (/Açık Mutfak/.test(n)) { const s2 = solid[1] || long; add('mutfak', against(b, s2.e, .5, .62)); }
        else if (Math.min(W, D) > 3.2) add('ArmChair_01', against(b, solid[1]?.e || opp.e, .8, dep('ArmChair_01')));
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
    summary();
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
    el.innerHTML = Object.entries(tot).sort((a, b) => b[1] - a[1]).map(([id, a]) => `<div><span>${FLOORS.find(f => f.id === id)?.name || id}</span><b>${n2(a)} m²</b></div>`).join('')
      + `<div class="muted"><span>Yerleştirilen nesne</span><b>${S.design.objects.length}</b></div>`;
  }
  function renderSel() {
    const el = $('#isel'); if (!el) return;
    if (!S.sel) { el.innerHTML = ''; return; }
    const it = ITEMS.find(i => i.id === S.sel.userData.item.kind);
    el.innerHTML = `<div class="selbar"><b>${it?.name || ''}</b><button class="vbtn" id="irot">⟳ 90°</button><button class="vbtn" id="idel">✕ SİL</button></div>`;
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
        <p class="inote">Boya tüm duvar yüzeylerine uygulanır.</p>`;
      $$('[data-p]').forEach(b => b.onclick = () => { S.design.paint = b.dataset.p; applyPaint(); save(); renderPanel(); });
    } else {
      const cats = [...new Set(ITEMS.map(i => i.cat))];
      body.innerHTML = `<div class="irow"><button class="vbtn walkbtn" id="iauto">✦ ÖRNEK DÖŞE (BU KAT)</button><button class="vbtn" id="iclr">TEMİZLE</button></div>
        ${cats.map(c => `<p class="sec-t" style="margin:12px 0 6px">${c.toUpperCase()}</p><div class="sw obj">${ITEMS.filter(i => i.cat === c).map(i =>
          `<button data-i="${i.id}" class="${S.tool?.kind === i.id ? 'on' : ''}">${i.model ? `<img src="${A}models/${i.id}/thumb.png" alt="">` : `<em>${ICON[i.id] || '◻'}</em>`}<span>${i.name}</span></button>`).join('')}</div>`).join('')}
        <p class="inote">Seç → zemine tıkla. Shift+tık art arda yerleştirir. Nesneyi seçip sürükle; R döndür, Del sil.</p>`;
      $$('[data-i]').forEach(b => b.onclick = () => { armItem(b.dataset.i); renderPanel(); });
      $('#iauto').onclick = async e => { e.target.disabled = true; e.target.textContent = 'DÖŞENİYOR…'; await autoFurnish(); renderPanel(); };
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

  return {
    setReal, load, openPanel, resizeAO, autoFurnish,
    refreshHint() { if ($('#vp').classList.contains('editing') && !S.tool) editHint(); },
    active: () => !!(S.tool || S.sel || S.drag || $('#vp').classList.contains('editing')),
    onBuild() {
      S.floorMeshes = []; S.extras = []; S.objs.clear(); select(null);
      if (S.real) { V.root.traverse(o => { if (o.isLine || o.isLineSegments) o.visible = false; if (o.isMesh) o.castShadow = o.receiveShadow = true; }); placeSun(); buildExtras(); restoreObjects(); }
    },
    get real() { return S.real; },
  };
}
