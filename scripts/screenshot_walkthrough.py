#!/usr/bin/env python3
"""Automated walkthrough screenshots of the Asculto web app.

Starts the FastAPI server if it is not already reachable, then uses Playwright
(system Chromium) to capture the key surfaces into docs/walkthrough/.

Usage:
  python scripts/screenshot_walkthrough.py
  ASCULTO_URL=http://localhost:8010 python scripts/screenshot_walkthrough.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "walkthrough")
BASE = os.environ.get("ASCULTO_URL", "http://localhost:8010")
CHROME = os.environ.get("CHROME_PATH", "/usr/bin/chromium-browser")


def _reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(url + "/health", timeout=timeout)
        return True
    except Exception:
        return False


def _wait(url: str, timeout: float = 60.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _reachable(url):
            return
        time.sleep(1.0)
    raise RuntimeError(f"server at {url} not reachable")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    proc = None
    if not _reachable(BASE):
        print(f"[shots] starting server on {BASE}")
        env = dict(os.environ, ASCULTO_DEVICE=os.environ.get("ASCULTO_DEVICE", "cpu"))
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "webapp.app.main:app", "--host", "0.0.0.0", "--port", "8010"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _wait(BASE)
    print(f"[shots] capturing from {BASE} -> {OUT}")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=1)

        def goto(path, wait_ms=1500):
            page.goto(BASE + path, wait_until="load", timeout=90000)
            page.wait_for_timeout(wait_ms)

        def full(path, name):
            goto(path)
            page.screenshot(path=os.path.join(OUT, name), full_page=True)
            print("  ", name)

        def viewport(path, name, wait_ms=1500):
            goto(path, wait_ms)
            page.screenshot(path=os.path.join(OUT, name), full_page=False)
            print("  ", name)

        def at_text(path, text, name, wait_ms=2500):
            goto(path, wait_ms)
            try:
                page.get_by_text(text, exact=False).first.scroll_into_view_if_needed()
                page.wait_for_timeout(600)
            except Exception:
                pass
            page.screenshot(path=os.path.join(OUT, name), full_page=False)
            print("  ", name)

        def at_last_image(path, name, wait_ms=2500):
            goto(path, wait_ms)
            try:
                imgs = page.locator("img")
                imgs.nth(imgs.count() - 1).scroll_into_view_if_needed()
                page.wait_for_timeout(600)
            except Exception:
                pass
            page.screenshot(path=os.path.join(OUT, name), full_page=False)
            print("  ", name)

        # 1. landing / upload
        full("/", "01_landing.png")
        # 2. report top (summary + predictions)
        viewport("/demo/report", "02_report_summary.png", wait_ms=4000)
        # 3. report figures section
        at_text("/demo/report", "Figures", "03_report_figures.png", wait_ms=4000)
        # 4. report synchronized timeline (last figure on the page)
        at_last_image("/demo/report", "04_report_timeline.png", wait_ms=4000)
        # 5. batch table
        full("/demo/batch?n=4", "05_batch.png", )
        # 6. game
        full("/game", "06_game.png")
        browser.close()

    if proc is not None:
        proc.terminate()
    print("[shots] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
