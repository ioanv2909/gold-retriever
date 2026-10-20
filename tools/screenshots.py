#!/usr/bin/env python3
"""Take README screenshots of the demo account (needs the app running).

    docker run --rm --network host -v "$PWD":/w mcr.microsoft.com/playwright/python:v1.49.0-noble \
        sh -c "python /w/tools/screenshots.py && chown -R 1000:1000 /w/docs"
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)


def to_english(page):
    try:
        page.get_by_text("EN", exact=True).first.click(timeout=3000)
        page.wait_for_timeout(1500)
    except Exception:
        pass


with sync_playwright() as p:
    browser = p.chromium.launch()
    for scheme in ("dark", "light"):
        ctx = browser.new_context(viewport={"width": 1500, "height": 3000}, color_scheme=scheme)
        page = ctx.new_page()
        page.goto(URL)
        page.wait_for_selector("input[type=password]", timeout=90000)
        to_english(page)
        page.screenshot(path=os.path.join(OUT, "login-%s.png" % scheme), clip={"x": 0, "y": 0, "width": 1500, "height": 900})

        page.locator("input[type=text]").first.fill("demo")
        pw = page.locator("input[type=password]").first
        pw.fill("demo")
        pw.press("Enter")

        page.wait_for_selector("text=/Demo account|Cont demo/", timeout=120000)
        to_english(page)
        page.wait_for_timeout(25000)  # charts, tables and prices finish loading
        try:
            box = page.locator('[data-testid="stMainBlockContainer"]').bounding_box()
            height = int(min(3000, box["y"] + box["height"] + 40))
        except Exception:
            height = 2000
        page.screenshot(path=os.path.join(OUT, "main-%s.png" % scheme),
                        clip={"x": 0, "y": 0, "width": 1500, "height": height})
        print("saved", scheme)
        ctx.close()
    browser.close()
