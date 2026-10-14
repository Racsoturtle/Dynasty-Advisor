from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page()
    pg.goto("https://racsoturtle.github.io/Dynasty-Advisor/checker.html?v=2"); pg.wait_for_selector("#mine input")
    v = pg.eval_on_selector("#partner", "s => [...s.options].find(o => o.text.includes('Monkey Neva Cramp')).value")
    pg.select_option("#partner", v); pg.dispatch_event("#partner", "change"); pg.wait_for_timeout(300)
    pg.click("#mine label:has-text('Rhamondre Stevenson') input"); pg.click("#theirs label:has-text('Germie Bernard') input")
    print(" ".join(pg.inner_text("#verdict").split()))
    print("updated:", pg.inner_text(".meta"))
    b.close()
