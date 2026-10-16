from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 2400})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("https://racsoturtle.github.io/Dynasty-Advisor/trades.html?v=3")
    h = pg.query_selector("h2:has-text('Spare 2nd')")
    print(h.inner_text())
    print(" ".join(pg.inner_text("h2:has-text('Spare 2nd') + .card").split()))
    for c in pg.query_selector_all(".pick-offer"):
        print("-", " ".join(c.inner_text().split())[:260])
    h.scroll_into_view_if_needed(); pg.screenshot(path="out/spare.png")
    print("scrollWidth", pg.evaluate("document.documentElement.scrollWidth"), "errors", errs)
    print("updated:", pg.inner_text(".meta"))
    b.close()
