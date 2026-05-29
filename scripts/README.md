# Data-pulling scripts

These scripts re-pull the EMCALI transformer dataset from the public
[Consultar Disponibilidad](https://www.emcali.com.co/web/servicios/autogeneracion/consultar-disponibilidad)
portal and regenerate the files the webapp consumes:

- `data/emcali_transformers.csv` — flat export with derived fields (loaded by `app.js`)
- `data/metadata.json` — snapshot date, record count, bbox (single source of truth)

## How it works

The portal loads transformers via a Liferay portlet AJAX endpoint
(`showMapTrafos`) that returns every transformer inside a lat/lng bounding box.
There's no public list endpoint, so we tile the Cali metro envelope and dedupe
by `codTrafo`. Full protocol details are in
[`emcali-transformer-api-reference.md`](./emcali-transformer-api-reference.md).

| File | Role |
|---|---|
| `emcali_session.py` | Boots a Playwright browser to establish a session (cookies), then exposes `fetch_trafos(bbox)` over a `requests.Session`. |
| `probe_coverage.py` | **Phase A** — probes wide/neighboring/control regions to confirm the dataset's true geographic bounds and check for a per-response cap. Writes `data/coverage_probe.md`. Optional; only needed if you suspect the coverage envelope changed. |
| `crawl_emcali.py` | **Phase B+C** — tiles the envelope, fetches+caches each tile (recursively subdividing dense tiles), dedupes, computes derived fields, and writes the CSV + JSON + metadata. |

## Setup

```bash
cd scripts
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run the pull

```bash
# from scripts/ (with the venv active)
python crawl_emcali.py
```

Outputs land in the repo's `data/` directory (one level up). The crawl is
**resumable**: per-tile responses are cached under `data/raw/`, so re-running
skips already-fetched tiles. Delete `data/raw/` to force a clean pull.

To re-check coverage bounds first:

```bash
python probe_coverage.py   # writes data/coverage_probe.md
```

## Notes

- Be polite: there's a built-in ~1.5s ± 0.5s delay between requests.
- If requests start returning empty bodies, the session expired — the crawler
  re-bootstraps automatically once per tile. If the portlet instance ID
  (`SolicitudCregPortlet_INSTANCE_ztkc`) ever changes after a site redeploy,
  update it in `emcali_session.py`.
- `data/emcali_transformers.json` (~11 MB) and the `data/raw*` caches are
  gitignored; only the CSV and `metadata.json` are committed.
