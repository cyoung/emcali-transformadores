# EMCALI Transformer Availability Map — API Reference

## Overview

The EMCALI "Consultar Disponibilidad" page displays an interactive Leaflet map of electrical
transformers in Cali, Colombia. Each pin represents a transformer with data about its power
capacity, energy availability, and connection request status. The data is loaded dynamically
via AJAX as the user pans/zooms the map.

This document describes how to programmatically extract all transformer data from the
underlying API.

---

## Architecture

- **Platform:** Liferay Portal (Java)
- **Portlet:** `SolicitudCregPortlet_INSTANCE_ztkc` (module: `emcali.tramite.creg`)
- **Map library:** Leaflet.js with OpenStreetMap tiles
- **Data loading:** jQuery AJAX (POST), triggered on map `move` and `zoom` events
- **Default zoom level:** 18 (street level)
- **Default center:** Approximately 3.4506, -76.5325 (downtown Cali)

---

## API Endpoints

### 1. `showMapTrafos` — Fetch transformers in a bounding box

This is the primary endpoint. It returns all transformers whose coordinates fall within the
given geographic bounding box.

**URL:**

```
POST https://www.emcali.com.co/web/servicios/autogeneracion/consultar-disponibilidad
```

**Query parameters (appended to URL):**

| Parameter             | Value                                    |
|----------------------|------------------------------------------|
| `p_p_id`             | `SolicitudCregPortlet_INSTANCE_ztkc`     |
| `p_p_lifecycle`      | `2`                                      |
| `p_p_state`          | `normal`                                 |
| `p_p_mode`           | `view`                                   |
| `p_p_resource_id`    | `showMapTrafos`                          |
| `p_p_cacheability`   | `cacheLevelPage`                         |

**POST body (form-data or x-www-form-urlencoded):**

| Parameter | Type   | Description                          | Example     |
|-----------|--------|--------------------------------------|-------------|
| `minLat`  | float  | Southwest corner latitude            | `3.43`      |
| `minLng`  | float  | Southwest corner longitude           | `-76.55`    |
| `maxLat`  | float  | Northeast corner latitude            | `3.46`      |
| `maxLng`  | float  | Northeast corner longitude           | `-76.51`    |

**Response:** JSON

```json
{
  "trafos": [
    {
      "codTrafo": "E7860",
      "dirTrafo": "CALLE 12 N? 12-47",
      "latTrafo": 3.44507,
      "lngTrafo": -76.530136,
      "potencia": 225,
      "potenciaSoliAprobadas": 0,
      "demandaEnergiaUno": 40.08,
      "demandaEnergiaDos": 40.08,
      "energiaEntregarHora": 0,
      "energiaEntregarHoraPico": 0,
      "nodoTrafo": 1057405,
      "codTrafoDis": 329,
      "codCircuito": "01 307",
      "circuito": 7,
      "codSubE": "01 ",
      "codBarrio": "039",
      "codCiudad": "01",
      "codPropietario": "E",
      "codigoTipoApoyo": "02",
      "fases": 3,
      "formTrafo": "NIVELII"
    }
  ]
}
```

### 2. `relocateTrans` — Look up a specific transformer by code

Used by the search/query form to locate a single transformer.

**URL:** Same base URL with:

| Parameter             | Value              |
|----------------------|--------------------|
| `p_p_resource_id`    | `relocateTrans`    |

**POST body:**

| Parameter                                                    | Type   | Description         |
|-------------------------------------------------------------|--------|---------------------|
| `_SolicitudCregPortlet_INSTANCE_ztkc_idTransformador`       | string | Transformer code    |

---

## Response Field Reference

### Raw API Fields

| Field                      | Type    | Description                                              |
|---------------------------|---------|----------------------------------------------------------|
| `codTrafo`                | string  | Unique transformer code (e.g., `E7860`, `P9527`)        |
| `dirTrafo`                | string  | Street address of the transformer                        |
| `latTrafo`                | float   | Latitude coordinate                                      |
| `lngTrafo`                | float   | Longitude coordinate                                     |
| `potencia`                | float   | Rated power capacity in KVA                              |
| `potenciaSoliAprobadas`   | float   | Power already allocated to approved connection requests (kWp) |
| `demandaEnergiaUno`       | float   | Energy demand metric #1 (kWh)                            |
| `demandaEnergiaDos`       | float   | Energy demand metric #2 (kWh)                            |
| `energiaEntregarHora`     | float   | Hourly energy being delivered to grid (kWh)              |
| `energiaEntregarHoraPico` | float   | Peak-hour energy being delivered to grid (kWh)           |
| `nodoTrafo`               | int     | Network node ID                                          |
| `codTrafoDis`             | int     | Distribution transformer code                            |
| `codCircuito`             | string  | Circuit code (e.g., `01 307`)                            |
| `circuito`                | int     | Circuit number                                           |
| `codSubE`                 | string  | Substation code                                          |
| `codBarrio`               | string  | Neighborhood code                                        |
| `codCiudad`               | string  | City code                                                |
| `codPropietario`          | string  | Owner code (`E` = EMCALI, `P` = private, etc.)          |
| `codigoTipoApoyo`         | string  | Support/pole type code                                   |
| `fases`                   | int     | Number of electrical phases (1 or 3)                     |
| `formTrafo`               | string  | Transformer form/level (`NIVELII`, etc.)                 |

### Derived Fields (computed client-side)

The popup (infowindow) shown when clicking a pin computes these values from the raw fields:

| Derived Field              | Formula                                                            | Unit |
|---------------------------|--------------------------------------------------------------------|------|
| Potencia disponible        | `potencia * 0.5`                                                   | KVA  |
| Potencia instalada         | `potenciaSoliAprobadas`                                            | kWp  |
| Energía máxima disponible  | `demandaEnergiaUno`                                                | kWh  |
| Energía instalada          | `energiaEntregarHora`                                              | kWh  |
| Potencia neta disponible   | `(potencia * 0.5) - potenciaSoliAprobadas`                         | KVA  |
| Energía neta disponible    | `demandaEnergiaUno - energiaEntregarHora`                          | kWh  |
| % Potencia instalada       | `(potenciaSoliAprobadas / (potencia * 0.5)) * 100`                 | %    |
| % Energía instalada        | `(energiaEntregarHora / demandaEnergiaUno) * 100`                  | %    |

### Traffic-Light Indicator Thresholds

The map uses color-coded indicators for both power and energy saturation:

**Power saturation (`indicadorPotencia` = % potencia instalada):**

| Condition              | Color    | Meaning                       |
|-----------------------|----------|-------------------------------|
| `>= 100%`             | 🔴 Red    | Fully saturated / unavailable |
| `> 50%`               | 🔴 Red    | High saturation               |
| `> 40% and <= 50%`    | 🟠 Orange | Moderate-high saturation      |
| `> 30% and <= 40%`    | 🟡 Yellow | Moderate saturation           |
| `<= 30%`              | 🟢 Green  | Available capacity            |

**Energy saturation (`enerEntregable` = % energía instalada):**

Same thresholds as power: green ≤30%, yellow 30–40%, orange 40–50%, red >50% or ≥100%.

### Effect of `entregaExcedentes` flag

The yes/no modal on the page asks whether the project will deliver surplus energy to the
local distribution network (SDL). This sets a hidden form field `entregaExcedentes`:

- **`true` (SI):** The popup includes "Porcentaje de potencia instalada" and
  "Porcentaje de energía instalada" fields.
- **`false` (NO):** Those percentage fields are hidden from the popup.

This flag only affects the client-side display; the API response data is the same either way.

---

## Session & Authentication Requirements

The API is served through a Liferay portlet resource URL. Key session details:

| Cookie / Token     | Description                                         |
|-------------------|-----------------------------------------------------|
| `JSESSIONID`      | Java servlet session cookie (httpOnly, not visible to JS) |
| `LFR_SESSION_STATE_*` | Liferay session state cookie                   |
| `AWSALB` / `AWSALBCORS` | AWS Application Load Balancer stickiness cookies |

**Important:** The API returns empty responses without a valid session. You must first load the
page in a browser context to establish a session before making API calls.

No `p_auth` CSRF token is required for the `showMapTrafos` resource call.

---

## Implementation Strategy

### Approach: Tiled Bounding-Box Crawl

Since the API returns transformers within a geographic bounding box, you can systematically
tile the entire EMCALI service area and collect all unique transformers.

#### Step 1: Establish a session

Use a headless browser (Playwright or Selenium) to:

1. Navigate to the page URL.
2. Dismiss the confirmation modal (click either SI or NO).
3. Extract session cookies from the browser context.

```python
# Pseudocode (Playwright)
page = browser.new_page()
page.goto("https://www.emcali.com.co/web/servicios/autogeneracion/consultar-disponibilidad")
page.wait_for_selector("button:has-text('SI')")
page.click("button:has-text('SI')")
cookies = context.cookies()
```

#### Step 2: Define the tile grid

EMCALI serves the Cali metropolitan area. A reasonable bounding box for the entire service area:

```
Northwest: approx  3.52, -76.58
Southeast: approx  3.35, -76.47
```

Divide this into tiles. At zoom level 18, the visible viewport covers roughly
0.008° latitude × 0.012° longitude. Using slightly larger tiles (e.g., 0.02° × 0.02°)
should work. This gives approximately:

- Latitude range: 0.17° / 0.02° = ~9 rows
- Longitude range: 0.11° / 0.02° = ~6 columns
- Total tiles: ~54 requests

#### Step 3: Fetch each tile

```python
import requests

session = requests.Session()
# Set cookies from Step 1
for cookie in cookies:
    session.cookies.set(cookie["name"], cookie["value"])

BASE_URL = (
    "https://www.emcali.com.co/web/servicios/autogeneracion/consultar-disponibilidad"
    "?p_p_id=SolicitudCregPortlet_INSTANCE_ztkc"
    "&p_p_lifecycle=2"
    "&p_p_state=normal"
    "&p_p_mode=view"
    "&p_p_resource_id=showMapTrafos"
    "&p_p_cacheability=cacheLevelPage"
)

all_trafos = {}

for min_lat in [3.35 + i * 0.02 for i in range(9)]:
    for min_lng in [-76.58 + j * 0.02 for j in range(6)]:
        data = {
            "minLat": min_lat,
            "minLng": min_lng,
            "maxLat": min_lat + 0.02,
            "maxLng": min_lng + 0.02,
        }
        resp = session.post(BASE_URL, data=data)
        if resp.text:
            result = resp.json()
            for trafo in result.get("trafos", []):
                all_trafos[trafo["codTrafo"]] = trafo

print(f"Total unique transformers: {len(all_trafos)}")
```

#### Step 4: Compute derived fields

```python
import csv

for trafo in all_trafos.values():
    pot_total = trafo["potencia"] * 0.5
    trafo["potenciaDisponible"] = pot_total
    trafo["potenciaNeta"] = pot_total - trafo["potenciaSoliAprobadas"]
    trafo["energiaDisponible"] = trafo["demandaEnergiaUno"] - trafo["energiaEntregarHora"]
    trafo["pctPotencia"] = (
        (trafo["potenciaSoliAprobadas"] / pot_total * 100) if pot_total > 0 else 0
    )
    trafo["pctEnergia"] = (
        (trafo["energiaEntregarHora"] / trafo["demandaEnergiaUno"] * 100)
        if trafo["demandaEnergiaUno"] > 0 else 0
    )
```

#### Step 5: Export

```python
fields = [
    "codTrafo", "dirTrafo", "latTrafo", "lngTrafo",
    "potencia", "potenciaDisponible", "potenciaSoliAprobadas", "potenciaNeta",
    "demandaEnergiaUno", "energiaEntregarHora", "energiaDisponible",
    "pctPotencia", "pctEnergia",
    "fases", "codCircuito", "circuito", "codSubE",
    "codBarrio", "codCiudad", "codPropietario", "formTrafo",
    "nodoTrafo", "codTrafoDis", "codigoTipoApoyo",
    "demandaEnergiaDos", "energiaEntregarHoraPico",
]

with open("emcali_transformers.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(all_trafos.values())
```

---

## Deduplication

The API returns transformers based on coordinates falling within the requested bounding box.
When tiles overlap (recommended for safety), you will receive duplicates.
Use `codTrafo` as the unique key to deduplicate.

---

## Rate Limiting & Politeness

- The page fires a new request on every map pan/zoom, so the server is accustomed to
  frequent calls from a single session.
- A 1–2 second delay between tile requests is a sensible courtesy.
- The portlet instance ID (`SolicitudCregPortlet_INSTANCE_ztkc`) may change if the site
  is redeployed. If requests suddenly fail, re-check the page source for the current ID.

---

## Troubleshooting

| Symptom                     | Cause / Fix                                              |
|----------------------------|----------------------------------------------------------|
| Empty response body         | Session expired — re-establish via headless browser       |
| HTTP 200 but no `trafos`    | Bounding box may be outside EMCALI service area           |
| Portlet ID not found        | Site redeployed — inspect page for new instance ID        |
| `403 Forbidden`             | Missing session cookies or IP-based rate limiting         |
