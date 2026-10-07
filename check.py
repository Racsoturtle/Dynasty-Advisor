import time
from playwright.sync_api import sync_playwright
BASE = "https://racsoturtle.github.io/Dynasty-Advisor/"
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 1400}, timezone_id="America/New_York")
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("dialog", lambda d: (errs.append("ALERT " + d.message), d.accept()))
    pg.goto(BASE + "waivers.html")
    print("morning header:", pg.inner_text(".meta"))
    t = time.time()
    pg.click("#refresh-btn")
    pg.wait_for_function("(document.getElementById('refresh-btn')||{textContent:''}).textContent.match(/rebuilt|checked/)", timeout=180000)
    print("refresh took", round(time.time() - t, 1), "s")
    print("button:", pg.inner_text("#refresh-btn"), "| rebuilt page:", pg.evaluate("!!window.__refreshed"))
    print("banner:", pg.inner_text("#live-banner").replace("\n", " | "))
    pg.screenshot(path="out/waivers.png", full_page=True)
    for page in ("index.html", "lineup.html", "trades.html", "log.html", "league.html", "checker.html"):
        pg.goto(BASE + page); pg.wait_for_timeout(1500)
        print(page, "rebuilt:", pg.evaluate("!!window.__refreshed"), "| offers shown:",
              pg.eval_on_selector_all(".offer", "cs => cs.filter(c => !c.hidden).length"),
              "| scrollWidth", pg.evaluate("document.documentElement.scrollWidth"))
        pg.screenshot(path=f"out/{page}.png")
    print("storage KB", pg.evaluate("Math.round(JSON.stringify(localStorage).length/1024)"))
    print("errors:", errs)
    b.close()
