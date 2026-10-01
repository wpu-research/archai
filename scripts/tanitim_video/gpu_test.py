import os
import time
from playwright.sync_api import sync_playwright
SETS = {
 "gl-egl": ["--use-gl=angle", "--use-angle=gl-egl", "--ignore-gpu-blocklist", "--disable-gpu-sandbox", "--enable-gpu-rasterization"],
 "gl": ["--use-gl=angle", "--use-angle=gl", "--ignore-gpu-blocklist", "--disable-gpu-sandbox"],
 "vulkan": ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist", "--disable-gpu-sandbox", "--disable-vulkan-surface"],
 "egl-native": ["--use-gl=egl", "--ignore-gpu-blocklist", "--disable-gpu-sandbox"],
}
JS = """() => { const c = document.createElement('canvas'); const g = c.getContext('webgl2'); if (!g) return 'webgl yok';
  const e = g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER); }"""
with sync_playwright() as p:
    for k, a in SETS.items():
        try:
            b = p.chromium.launch(args=a, timeout=60000); pg = b.new_page(); pg.goto("about:blank")
            print(k, "→", pg.evaluate(JS)); b.close()
        except Exception as ex:
            print(k, "HATA", str(ex)[:120])
