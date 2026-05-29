"""Phase B+C — Tiled crawl + derived-field export.

Given Phase A findings (empirical envelope lat [3.217, 3.678], lng [-76.654,
-76.396]; ~16.7k records fit in one response; no observed cap), this script
tiles a padded envelope, fetches each tile, dedupes by codTrafo, writes raw
JSON and a CSV with derived fields.

Outputs (written to the repo's data/ directory, one level up):
  data/raw/tile_<...>.json      per-tile raw responses (resumable, gitignored)
  data/emcali_transformers.json deduped raw records (gitignored, large)
  data/emcali_transformers.csv  flat export with derived fields — consumed by
                                the webapp
  data/metadata.json            snapshot metadata (date, count, bbox) — single
                                source of truth consumed by the webapp
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
import time
from pathlib import Path

from emcali_session import EmcaliSession, bootstrap_session

# Scripts live in scripts/; data lives in the repo root data/ (one level up).
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_JSON = DATA_DIR / "emcali_transformers.json"
OUT_CSV = DATA_DIR / "emcali_transformers.csv"
OUT_METADATA = DATA_DIR / "metadata.json"

SOURCE_URL = (
    "https://www.emcali.com.co/web/servicios/autogeneracion/consultar-disponibilidad"
)

# Empirical envelope from probe_coverage.py, padded.
ENVELOPE_LAT = (3.20, 3.70)
ENVELOPE_LNG = (-76.70, -76.35)
TILE_SIZE = 0.05  # degrees — ~5.5 km; well under the demonstrated 16.7k cap headroom

SUBDIVIDE_THRESHOLD = 10_000  # if a tile returns >= this, recursively split
MIN_TILE_SIZE = 0.005  # hard floor for subdivision

REQUEST_DELAY = 1.5
JITTER = 0.5
REQUEST_TIMEOUT = 180.0

CSV_FIELDS = [
    "codTrafo", "dirTrafo", "latTrafo", "lngTrafo",
    "potencia", "potenciaDisponible", "potenciaSoliAprobadas", "potenciaNeta",
    "demandaEnergiaUno", "energiaEntregarHora", "energiaDisponible",
    "pctPotencia", "pctEnergia",
    "fases", "codCircuito", "circuito", "codSubE",
    "codBarrio", "codCiudad", "codPropietario", "formTrafo",
    "nodoTrafo", "codTrafoDis", "codigoTipoApoyo",
    "demandaEnergiaDos", "energiaEntregarHoraPico",
]


def tile_filename(min_lat: float, min_lng: float, max_lat: float, max_lng: float) -> Path:
    return RAW_DIR / f"tile_{min_lat:.5f}_{min_lng:.5f}_{max_lat:.5f}_{max_lng:.5f}.json"


def polite_sleep() -> None:
    time.sleep(REQUEST_DELAY + random.uniform(-JITTER, JITTER))


def fetch_tile_with_retry(
    es_ref: list[EmcaliSession],
    min_lat: float, min_lng: float, max_lat: float, max_lng: float,
) -> list[dict]:
    """Fetch one tile. On session-expiry failure, re-bootstrap once and retry."""
    cache = tile_filename(min_lat, min_lng, max_lat, max_lng)
    if cache.exists():
        return json.loads(cache.read_text()).get("trafos", [])

    for attempt in (1, 2):
        try:
            raw = es_ref[0].fetch_trafos(
                min_lat, min_lng, max_lat, max_lng, timeout=REQUEST_TIMEOUT
            )
            cache.write_text(json.dumps(raw, ensure_ascii=False))
            return raw.get("trafos", [])
        except Exception as e:
            print(f"    [warn] tile fetch failed (attempt {attempt}): {e}")
            if attempt == 2:
                raise
            print("    [warn] re-bootstrapping session...")
            es_ref[0] = bootstrap_session(verbose=False)
            time.sleep(2)
    return []


def crawl_tile_recursive(
    es_ref: list[EmcaliSession],
    min_lat: float, min_lng: float, max_lat: float, max_lng: float,
    accum: dict[str, dict],
    depth: int = 0,
    stats: dict | None = None,
) -> None:
    """Fetch a tile; if too dense, split into 4 sub-tiles and recurse."""
    if stats is None:
        stats = {}
    indent = "  " * depth
    lat_span = max_lat - min_lat
    lng_span = max_lng - min_lng

    print(f"{indent}[tile d{depth}] "
          f"({min_lat:.4f}, {min_lng:.4f}) -> ({max_lat:.4f}, {max_lng:.4f})")

    trafos = fetch_tile_with_retry(es_ref, min_lat, min_lng, max_lat, max_lng)
    stats["requests"] = stats.get("requests", 0) + 1
    n = len(trafos)
    print(f"{indent}  -> {n} records (running unique={len(accum)})")

    if n >= SUBDIVIDE_THRESHOLD and lat_span > MIN_TILE_SIZE and lng_span > MIN_TILE_SIZE:
        stats["subdivided"] = stats.get("subdivided", 0) + 1
        print(f"{indent}  subdividing (>= {SUBDIVIDE_THRESHOLD})")
        mid_lat = (min_lat + max_lat) / 2
        mid_lng = (min_lng + max_lng) / 2
        for (alo, blo, ahi, bhi) in [
            (min_lat, min_lng, mid_lat, mid_lng),
            (min_lat, mid_lng, mid_lat, max_lng),
            (mid_lat, min_lng, max_lat, mid_lng),
            (mid_lat, mid_lng, max_lat, max_lng),
        ]:
            polite_sleep()
            crawl_tile_recursive(es_ref, alo, blo, ahi, bhi, accum, depth + 1, stats)
        return

    for t in trafos:
        code = t.get("codTrafo")
        if code:
            accum[code] = t


def compute_derived(t: dict) -> None:
    """In-place add the derived fields per the API reference doc (§Derived Fields)."""
    pot = float(t.get("potencia") or 0.0)
    pot_total = pot * 0.5
    pot_approved = float(t.get("potenciaSoliAprobadas") or 0.0)
    dem1 = float(t.get("demandaEnergiaUno") or 0.0)
    ent_hora = float(t.get("energiaEntregarHora") or 0.0)

    t["potenciaDisponible"] = pot_total
    t["potenciaNeta"] = pot_total - pot_approved
    t["energiaDisponible"] = dem1 - ent_hora
    t["pctPotencia"] = (pot_approved / pot_total * 100.0) if pot_total > 0 else 0.0
    t["pctEnergia"] = (ent_hora / dem1 * 100.0) if dem1 > 0 else 0.0


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("[crawl] bootstrapping session...")
    es_ref = [bootstrap_session()]

    accum: dict[str, dict] = {}
    stats: dict = {}

    # Build tile grid.
    lat_lo, lat_hi = ENVELOPE_LAT
    lng_lo, lng_hi = ENVELOPE_LNG
    n_rows = int(round((lat_hi - lat_lo) / TILE_SIZE))
    n_cols = int(round((lng_hi - lng_lo) / TILE_SIZE))
    total_tiles = n_rows * n_cols
    print(f"[crawl] envelope lat [{lat_lo},{lat_hi}] lng [{lng_lo},{lng_hi}]")
    print(f"[crawl] {n_rows} rows x {n_cols} cols = {total_tiles} top-level tiles")

    t_start = time.monotonic()
    for i in range(n_rows):
        for j in range(n_cols):
            min_lat = lat_lo + i * TILE_SIZE
            min_lng = lng_lo + j * TILE_SIZE
            max_lat = min_lat + TILE_SIZE
            max_lng = min_lng + TILE_SIZE
            crawl_tile_recursive(
                es_ref, min_lat, min_lng, max_lat, max_lng, accum, stats=stats
            )
            polite_sleep()

    elapsed = time.monotonic() - t_start
    print(f"\n[crawl] done in {elapsed:.1f}s")
    print(f"[crawl] total requests: {stats.get('requests', 0)} "
          f"(subdivided {stats.get('subdivided', 0)} times)")
    print(f"[crawl] unique transformers: {len(accum)}")

    # Sanity: distributions.
    hist_ciudad: dict[str, int] = {}
    hist_prop: dict[str, int] = {}
    for t in accum.values():
        hist_ciudad[str(t.get("codCiudad"))] = hist_ciudad.get(str(t.get("codCiudad")), 0) + 1
        hist_prop[str(t.get("codPropietario"))] = hist_prop.get(str(t.get("codPropietario")), 0) + 1
    print(f"[crawl] codCiudad dist:     {hist_ciudad}")
    print(f"[crawl] codPropietario dist: {hist_prop}")

    lats = [t["latTrafo"] for t in accum.values() if t.get("latTrafo")]
    lngs = [t["lngTrafo"] for t in accum.values() if t.get("lngTrafo")]
    print(f"[crawl] observed lat range: [{min(lats):.5f}, {max(lats):.5f}]")
    print(f"[crawl] observed lng range: [{min(lngs):.5f}, {max(lngs):.5f}]")

    # Derive fields + export.
    for t in accum.values():
        compute_derived(t)

    OUT_JSON.write_text(
        json.dumps(list(accum.values()), ensure_ascii=False, indent=2)
    )
    print(f"[crawl] wrote {OUT_JSON} ({OUT_JSON.stat().st_size/1024:.1f} KB)")

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for t in accum.values():
            writer.writerow(t)
    print(f"[crawl] wrote {OUT_CSV} ({OUT_CSV.stat().st_size/1024:.1f} KB)")

    metadata = {
        "snapshot_date": dt.date.today().isoformat(),
        "record_count": len(accum),
        "bbox": {
            "min_lat": min(lats),
            "min_lng": min(lngs),
            "max_lat": max(lats),
            "max_lng": max(lngs),
        },
        "source": SOURCE_URL,
        "description": (
            "Copia de los datos del portal público 'Consultar Disponibilidad' "
            "de EMCALI. Reproducción no oficial para fines informativos."
        ),
    }
    OUT_METADATA.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(f"[crawl] wrote {OUT_METADATA}")


if __name__ == "__main__":
    main()
