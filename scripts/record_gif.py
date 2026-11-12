"""Records docs/demo.gif from a live run.

Left: the Aloud console in its own Chrome window. Right: the Chrome the agent drives.
Bottom: what the console speaks. Needs scripts/demo.sh running first (agent Chrome on :9222,
console on :8000), plus ffmpeg.

    uv run --group demo python scripts/record_gif.py

Voice input is handed to the console through window.aloudHeard, the hook the microphone path
also ends in; everything after that (agent, Guardian, Chrome) is the live system. Stretches where
the agent is working are sped up and the frame says so.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "demo.gif"
CONSOLE = os.getenv("ALOUD_CONSOLE", "http://127.0.0.1:8000")
AGENT_CDP = os.getenv("ALOUD_BROWSER_URL", "http://127.0.0.1:9222")
BANK = os.getenv("ALOUD_DEMO_PAGE", "http://127.0.0.1:8770/bank.html")
CONSOLE_PORT = 9223
CHROME = os.getenv("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
WIDTH, PANEL_H, CAPTION_H, HEAD_H = 1280, 680, 92, 38
SPEEDUP = 3  # agent-working frames play this many times faster than real time

FONT = "/System/Library/Fonts/SFNS.ttf"
font = lambda size: ImageFont.truetype(FONT, size)  # noqa: E731

frames: list[dict] = []
note = {"text": ""}  # what the "user" is doing right now, shown in the caption bar


async def capture(console, agent, stop: asyncio.Event, workdir: Path) -> None:
    """Grabs both windows as often as the machine allows, with the console's state."""
    i = 0
    while not stop.is_set():
        t = time.monotonic()
        c, a = workdir / f"c{i:04d}.png", workdir / f"a{i:04d}.png"
        await asyncio.gather(console.screenshot(path=c), agent.screenshot(path=a))
        state = await console.evaluate("""() => ({
            busy: document.documentElement.dataset.busy === '1',
            status: document.getElementById('status').textContent,
            last: (() => { const li = [...document.querySelectorAll('#log li')].pop();
                           return li ? {cls: li.className, text: li.childNodes[1]?.textContent || ''} : null })()
        })""")
        frames.append({"t": t, "c": c, "a": a, "note": note["text"], **state})
        i += 1
        await asyncio.sleep(max(0, 0.18 - (time.monotonic() - t)))


def wrap(draw: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=f) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def compose(fr: dict, out: Path) -> None:
    c, a = Image.open(fr["c"]).convert("RGB"), Image.open(fr["a"]).convert("RGB")
    cw = int(c.width * PANEL_H / c.height)
    c = c.resize((cw, PANEL_H), Image.LANCZOS)
    aw = WIDTH - cw
    a = a.resize((aw, int(a.height * aw / a.width)), Image.LANCZOS).crop((0, 0, aw, PANEL_H))
    img = Image.new("RGB", (WIDTH, HEAD_H + PANEL_H + CAPTION_H), "#101114")
    d = ImageDraw.Draw(img)
    img.paste(c, (0, HEAD_H))
    img.paste(a, (cw, HEAD_H))
    d.line([(cw, HEAD_H), (cw, HEAD_H + PANEL_H)], fill="#101114", width=4)
    h = font(19)
    d.text((14, 9), "Aloud console: what the user hears and says", font=h, fill="#f4f4f6")
    d.text((cw + 14, 9), "Real Chrome, driven by the agent", font=h, fill="#f4f4f6")
    if fr["busy"]:
        tag = f"agent working, {SPEEDUP}x speed"
        tw = d.textlength(tag, font=font(17))
        d.rounded_rectangle([WIDTH - tw - 30, 7, WIDTH - 8, 31], 8, fill="#3d3200")
        d.text((WIDTH - tw - 19, 9), tag, font=font(17), fill="#ffe08a")
    y = HEAD_H + PANEL_H
    last = fr["last"] or {}
    if fr["note"]:
        label, text, color = "User", fr["note"], "#8ab4f8"
    elif fr["busy"] and last.get("cls") == "you":
        label, text, color = "Status", fr["status"], "#c4c7cf"
    elif last.get("cls") in ("aloud", "blocked", "confirm", "warning"):
        label, text = "Spoken", last["text"]
        color = {"blocked": "#ff8a80", "warning": "#ffb366", "confirm": "#ffb366"}.get(last["cls"], "#81c995")
    else:
        label, text, color = "", "", "#f4f4f6"
    if text:
        d.text((16, y + 12), label.upper(), font=font(16), fill=color)
        for k, ln in enumerate(wrap(d, text, font(25), WIDTH - 130)[:2]):
            d.text((100, y + 8 + k * 34), ln, font=font(25), fill="#f4f4f6")
    img.save(out)


async def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found")
    work = Path(tempfile.mkdtemp(prefix="aloud-rec-"))
    profile = work / "console-profile"
    chrome = subprocess.Popen(
        [CHROME, f"--remote-debugging-port={CONSOLE_PORT}", f"--user-data-dir={profile}",
         "--no-first-run", "--no-default-browser-check", "--window-size=720,1000", f"--app={CONSOLE}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with async_playwright() as pw:
            for _ in range(50):
                try:
                    cb = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CONSOLE_PORT}")
                    break
                except Exception:
                    await asyncio.sleep(0.3)
            ab = await pw.chromium.connect_over_cdp(AGENT_CDP)
            agent = next(p for ctx in ab.contexts for p in ctx.pages if p.url.startswith("http"))
            await agent.goto(BANK)
            console = next(p for p in cb.contexts[0].pages if p.url.startswith(CONSOLE))
            await console.wait_for_selector("#talk")
            # The GIF has no sound; captions carry the speech, so keep the machine quiet.
            await console.evaluate("""() => { for (const id of ['speak', 'sounds']) {
                const el = document.getElementById(id); el.checked = false; el.dispatchEvent(new Event('change')); } }""")

            async def turn(text: str, pause: float = 2.5) -> None:
                note["text"] = f'says "{text}"'
                await console.evaluate("(t) => { window.aloudHeard(t); }", text)
                await asyncio.sleep(1.4)
                note["text"] = ""
                await console.wait_for_function("document.documentElement.dataset.busy === '0'", timeout=300_000)
                await asyncio.sleep(pause)

            stop = asyncio.Event()
            grab = asyncio.create_task(capture(console, agent, stop, work))
            await asyncio.sleep(1.5)
            await turn("where am I")
            await turn("read the form", 3.5)
            await turn("pay my November rent to jane@rent.example, 1200 dollars at most", 3)
            note["text"] = 'presses Enter on "Yes, do it"'
            await console.keyboard.press("Enter")
            await asyncio.sleep(1.2)
            note["text"] = ""
            await console.wait_for_function("document.documentElement.dataset.busy === '0'", timeout=300_000)
            await asyncio.sleep(3.5)
            stop.set()
            await grab
    finally:
        chrome.terminate()

    # Per-frame durations from real time, sped up while the agent works.
    lines = []
    for i, fr in enumerate(frames):
        nxt = frames[i + 1]["t"] if i + 1 < len(frames) else fr["t"] + 0.5
        dur = (nxt - fr["t"]) / (SPEEDUP if fr["busy"] else 1)
        png = work / f"f{i:04d}.png"
        compose(fr, png)
        lines += [f"file '{png}'", f"duration {dur:.3f}"]
    lines.append(f"file '{work / f'f{len(frames) - 1:04d}.png'}'")
    (work / "list.txt").write_text("\n".join(lines))
    OUT.parent.mkdir(exist_ok=True)
    vf = "fps=8,scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"),
                    "-vf", vf, str(OUT)], check=True)
    mp4 = OUT.with_suffix(".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"),
                    "-vf", "fps=24,scale=1280:-2", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
    total = sum(float(x.split()[1]) for x in lines if x.startswith("duration"))
    print(f"{OUT} and {mp4}: {len(frames)} frames, {total:.1f} s, {OUT.stat().st_size / 1e6:.1f} MB")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
