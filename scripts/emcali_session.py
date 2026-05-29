"""Session bootstrap helper for the EMCALI 'Consultar Disponibilidad' portal.

Uses Playwright to load the page, dismiss the entregaExcedentes modal, and
return cookies + user-agent suitable for a requests.Session that can call the
showMapTrafos portlet resource endpoint.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

PORTAL_URL = (
    "https://www.emcali.com.co/web/servicios/autogeneracion/consultar-disponibilidad"
)

SHOW_MAP_TRAFOS_URL = (
    f"{PORTAL_URL}"
    "?p_p_id=SolicitudCregPortlet_INSTANCE_ztkc"
    "&p_p_lifecycle=2"
    "&p_p_state=normal"
    "&p_p_mode=view"
    "&p_p_resource_id=showMapTrafos"
    "&p_p_cacheability=cacheLevelPage"
)


@dataclass
class EmcaliSession:
    session: requests.Session
    user_agent: str

    def fetch_trafos(
        self,
        min_lat: float,
        min_lng: float,
        max_lat: float,
        max_lng: float,
        timeout: float = 30.0,
    ) -> dict:
        """POST to showMapTrafos for a bounding box. Returns parsed JSON.

        Raises RuntimeError on empty body (session expired) or HTTP errors.
        """
        resp = self.session.post(
            SHOW_MAP_TRAFOS_URL,
            data={
                "minLat": f"{min_lat}",
                "minLng": f"{min_lng}",
                "maxLat": f"{max_lat}",
                "maxLng": f"{max_lng}",
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        if not resp.text.strip():
            raise RuntimeError("empty response body — session likely expired")
        try:
            return resp.json()
        except ValueError as e:
            raise RuntimeError(
                f"non-JSON response: {resp.text[:200]}"
            ) from e


def bootstrap_session(headless: bool = True, verbose: bool = True) -> EmcaliSession:
    """Launch Playwright, load the portal, dismiss modal, return EmcaliSession."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="es-CO",
        )
        page = context.new_page()
        if verbose:
            print(f"[session] loading {PORTAL_URL}")
        page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60000)

        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except PlaywrightTimeoutError:
            if verbose:
                print("[session] networkidle timeout (continuing)")

        # Try to dismiss the entregaExcedentes modal. Several possible selectors.
        dismissed = False
        for selector in [
            "button:has-text('SI')",
            "button:has-text('Si')",
            "a:has-text('SI')",
            "#modalExcedentes button",
            ".modal.show button.btn-primary",
        ]:
            try:
                el = page.wait_for_selector(selector, timeout=3000, state="visible")
                if el:
                    el.click()
                    if verbose:
                        print(f"[session] clicked modal with selector {selector!r}")
                    dismissed = True
                    break
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

        if verbose and not dismissed:
            print("[session] no modal dismissed (may be fine — flag is client-side only)")

        time.sleep(2)

        user_agent = page.evaluate("navigator.userAgent")
        raw_cookies = context.cookies()
        browser.close()

    if verbose:
        print(f"[session] captured {len(raw_cookies)} cookies: "
              f"{sorted({c['name'] for c in raw_cookies})}")

    s = requests.Session()
    s.headers.update({
        "User-Agent": user_agent,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://www.emcali.com.co",
        "Referer": PORTAL_URL,
    })
    for c in raw_cookies:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain"))

    return EmcaliSession(session=s, user_agent=user_agent)


if __name__ == "__main__":
    es = bootstrap_session()
    print("\n[test] fetching small bbox around downtown Cali...")
    result = es.fetch_trafos(3.44, -76.54, 3.46, -76.52)
    trafos = result.get("trafos", [])
    print(f"[test] got {len(trafos)} transformers")
    if trafos:
        t = trafos[0]
        print(f"[test] first: codTrafo={t.get('codTrafo')} "
              f"dirTrafo={t.get('dirTrafo')!r} "
              f"potencia={t.get('potencia')}")
