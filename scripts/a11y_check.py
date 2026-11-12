"""Runs axe-core (WCAG 2.2 A/AA + best practice) on the console in headless Chrome, light and dark.

Needs the console on :8000 (scripts/demo.sh). Exits 1 on any violation.

    uv run --group demo python scripts/a11y_check.py
"""
import asyncio, json, subprocess, time, tempfile
from playwright.async_api import async_playwright
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
async def main():
    p=subprocess.Popen([CH,"--remote-debugging-port=9224",f"--user-data-dir={tempfile.mkdtemp()}","--no-first-run","--headless=new","http://127.0.0.1:8000"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        async with async_playwright() as pw:
            for _ in range(50):
                try: b=await pw.chromium.connect_over_cdp("http://127.0.0.1:9224"); break
                except Exception: await asyncio.sleep(0.3)
            await asyncio.sleep(1)
            pg=b.contexts[0].pages[0]
            await pg.wait_for_selector("#talk")
            out={}
            for scheme in ("light","dark"):
                await pg.emulate_media(color_scheme=scheme)
                await pg.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4.10.2/axe.min.js")
                r=await pg.evaluate("axe.run(document,{runOnly:['wcag2a','wcag2aa','wcag21aa','wcag22aa','best-practice']})")
                out[scheme]={"violations":[(v["id"],v["impact"],len(v["nodes"]),v["nodes"][0]["target"]) for v in r["violations"]],"passes":len(r["passes"])}
            print(json.dumps(out,indent=1))
            if any(v["violations"] for v in out.values()): raise SystemExit(1)
    finally: p.terminate()
asyncio.run(main())
