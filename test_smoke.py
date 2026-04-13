"""Smoke-test the EMCALI disponibilidad map.

Requires the site to be running on http://localhost:8765 (e.g. via
`python3 -m http.server 8765` in this directory).

Reads data/metadata.json to know the expected record count, then drives
the Playwright browser through the main filters and captures screenshots
to /tmp for visual inspection.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8765/"
SHOT_DIR = Path("/tmp")
METADATA_PATH = Path(__file__).parent / "data" / "metadata.json"
MONTHS_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def format_snapshot_date(raw_date: str) -> str:
    parsed = date.fromisoformat(raw_date)
    month = MONTHS_ES[parsed.month]
    return f"{parsed.day} de {month} de {parsed.year}"


def main() -> int:
    meta = json.loads(METADATA_PATH.read_text())
    expected_count = meta["record_count"]
    expected_date = format_snapshot_date(meta["snapshot_date"])
    print(f"[test] expected count={expected_count}, date={expected_date}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        page = ctx.new_page()

        console_msgs: list[tuple[str, str]] = []
        page.on("console", lambda m: console_msgs.append((m.type, m.text)))
        page.on("pageerror", lambda e: console_msgs.append(("pageerror", str(e))))

        print(f"[test] navigating to {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_load_state("networkidle", timeout=30000)

        # Wait for the loading overlay to receive the 'hidden' class.
        page.wait_for_function(
            "document.getElementById('map-loading').classList.contains('hidden')",
            timeout=15000,
        )
        page.wait_for_timeout(1000)

        print(f"[test] title: {page.title()}")
        page.screenshot(path=str(SHOT_DIR / "emcali_01_initial.png"))

        # ---- metadata populated in DOM ----
        banner_date = page.locator("#snapshot-bar .js-snapshot-date").first.inner_text()
        banner_count = page.locator("#snapshot-bar .js-record-count").first.inner_text()
        print(f"[test] snapshot-bar date={banner_date!r}, count={banner_count!r}")
        assert banner_date == expected_date, (
            f"snapshot-bar date mismatch: {banner_date!r} != {expected_date!r}"
        )

        # ---- summary stats ----
        stats = {}
        for stat_id in [
            "stat-count", "stat-rated", "stat-allocated", "stat-available",
            "stat-operational", "stat-approved",
        ]:
            stats[stat_id] = page.locator(f"#{stat_id}").inner_text()
            print(f"[test] {stat_id}: {stats[stat_id]}")

        stat_count_int = int(stats["stat-count"].replace(".", "").replace(",", ""))
        assert stat_count_int == expected_count, (
            f"stat-count mismatch: {stat_count_int} != {expected_count}"
        )

        # ---- substation dropdown ----
        sub_opts = page.locator("#filter-substation option").count()
        print(f"[test] substation options: {sub_opts}")
        assert sub_opts >= 2, "substation dropdown appears empty"

        # ---- only-projects filter ----
        print("[test] toggling 'only projects' filter")
        page.check("#filter-only-projects")
        page.wait_for_timeout(500)
        count_proj = int(
            page.locator("#stat-count").inner_text().replace(".", "")
        )
        op_after = page.locator("#stat-operational").inner_text()
        appr_after = page.locator("#stat-approved").inner_text()
        print(f"[test] only-projects: count={count_proj}, "
              f"operational={op_after}, approved={appr_after}")
        assert 0 < count_proj < expected_count, (
            f"only-projects count {count_proj} not in (0, {expected_count})"
        )
        page.screenshot(path=str(SHOT_DIR / "emcali_02_projects_only.png"))

        # ---- approved subfilter ----
        page.uncheck("#filter-only-projects")
        page.select_option("#filter-project-type", "approved")
        page.wait_for_timeout(500)
        count_appr = int(page.locator("#stat-count").inner_text().replace(".", ""))
        print(f"[test] project-type=approved: count={count_appr}")
        assert count_appr > 0

        # ---- substation filter ----
        page.click("#filter-reset")
        page.wait_for_timeout(300)
        first_sub = page.locator("#filter-substation option").nth(1).get_attribute("value")
        if first_sub:
            page.select_option("#filter-substation", first_sub)
            page.wait_for_timeout(500)
            sub_count_val = page.locator("#stat-count").inner_text()
            print(f"[test] substation {first_sub}: count={sub_count_val}")
            page.screenshot(path=str(SHOT_DIR / "emcali_03_one_substation.png"))

        # ---- popup + Google Maps link ----
        page.click("#filter-reset")
        page.wait_for_timeout(300)
        print("[test] opening a popup via JS to check Google Maps link")
        opened_code = page.evaluate(
            """() => {
                const entries = Array.from(state.markersByCode.entries());
                if (!entries.length) return null;
                const [code, marker] = entries[0];
                marker.openPopup();
                return code;
            }"""
        )
        assert opened_code, "no markers to open popup on"
        print(f"[test] popup opened for {opened_code}")

        page.wait_for_selector(".leaflet-popup-content .popup-gmaps", timeout=5000)
        gmaps_href = page.locator(".leaflet-popup-content .popup-gmaps").get_attribute("href")
        gmaps_text = page.locator(".leaflet-popup-content .popup-gmaps").inner_text()
        print(f"[test] Google Maps href: {gmaps_href}")
        print(f"[test] Google Maps text: {gmaps_text!r}")
        assert "google.com/maps" in (gmaps_href or ""), "popup missing google.com/maps URL"
        assert "Google Maps" in gmaps_text, "popup missing link label"
        print("[test] Google Maps link present in popup OK")
        page.wait_for_timeout(500)
        page.screenshot(path=str(SHOT_DIR / "emcali_04_popup.png"))

        # ---- console errors ----
        errors = [m for m in console_msgs if m[0] in ("error", "pageerror")]
        for typ, txt in errors[:10]:
            print(f"  [{typ}] {txt[:200]}")
        print(f"[test] total console messages: {len(console_msgs)}, errors: {len(errors)}")
        assert not errors, "browser console had errors"

        browser.close()

    print("\n[test] OK — all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
