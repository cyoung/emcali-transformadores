/* EMCALI Disponibilidad — client-side map + filters
 *
 * Loads the full transformer snapshot, renders it on a canvas-based Leaflet
 * map, and lets the user filter by saturation, owner, substation, voltage,
 * and project status (operational / approved). All 16k points are rendered
 * at once via preferCanvas — no clustering needed at this scale.
 */

// ---------- Config ----------

const CSV_URL = "data/emcali_transformers.csv";
const METADATA_URL = "data/metadata.json";

const CALI_CENTER = [3.44, -76.53];
const CALI_ZOOM = 12;

const COLORS = {
  satNone: "#86efac",
  satLow:  "#22c55e",
  satMed:  "#eab308",
  satHigh: "#f97316",
  satFull: "#ef4444",

  projectOperational: "#6366f1",
  projectApproved:    "#a855f7",
};

const NUMERIC_FIELDS = [
  "latTrafo", "lngTrafo",
  "potencia", "potenciaDisponible", "potenciaSoliAprobadas", "potenciaNeta",
  "demandaEnergiaUno", "energiaEntregarHora", "energiaDisponible",
  "pctPotencia", "pctEnergia",
  "fases", "circuito", "nodoTrafo", "codTrafoDis",
  "demandaEnergiaDos", "energiaEntregarHoraPico",
];

const OWNER_LABELS = {
  "E": "EMCALI",
  "P": "Privado",
  "1": "Otro (1)",
  "2": "Otro (2)",
  "N": "Otro (N)",
  "T": "Otro (T)",
};

const VOLTAGE_LABELS = {
  "NIVELII": "Nivel II (media tensión)",
  "NIVELI":  "Nivel I (baja tensión)",
  "":        "Sin clasificar",
  "NULL":    "Sin clasificar",
};

// ---------- State ----------

const state = {
  allTransformers: [],
  filtered: [],
  map: null,
  layer: null,
  markersByCode: new Map(),
};

// ---------- Utilities ----------

const fmtInt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const fmtDec = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });
const fmtLongDate = new Intl.DateTimeFormat("es-CO", {
  dateStyle: "long",
  timeZone: "UTC",
});

function fmt(n) {
  if (n == null || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1000) return fmtInt.format(Math.round(n));
  return fmtDec.format(n);
}

function formatSnapshotDate(dateStr) {
  if (!dateStr) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
  if (!match) return dateStr;
  const [, year, month, day] = match;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return fmtLongDate.format(date);
}

function parseRow(row) {
  const out = { ...row };
  for (const key of NUMERIC_FIELDS) {
    const v = out[key];
    if (v === "" || v == null) {
      out[key] = null;
    } else {
      const n = Number(v);
      out[key] = Number.isNaN(n) ? null : n;
    }
  }
  out.codSubE = (out.codSubE || "").trim();
  out.isOperational =
    (out.energiaEntregarHora || 0) > 0;
  out.isApproved =
    (out.potenciaSoliAprobadas || 0) > 0;
  out.hasProject = out.isOperational || out.isApproved;
  return out;
}

function saturationBucket(t) {
  const p = t.pctPotencia || 0;
  if (p === 0)   return "none";
  if (p <= 30)   return "low";
  if (p <= 40)   return "med";
  if (p <= 50)   return "high";
  return "full";
}

function colorFor(t) {
  switch (saturationBucket(t)) {
    case "none": return COLORS.satNone;
    case "low":  return COLORS.satLow;
    case "med":  return COLORS.satMed;
    case "high": return COLORS.satHigh;
    default:     return COLORS.satFull;
  }
}

function markerStyle(t) {
  const fill = colorFor(t);
  if (t.isOperational) {
    return {
      radius: 6,
      fillColor: fill,
      color: COLORS.projectOperational,
      weight: 3,
      fillOpacity: 0.95,
      opacity: 1,
    };
  }
  if (t.isApproved) {
    return {
      radius: 6,
      fillColor: fill,
      color: COLORS.projectApproved,
      weight: 3,
      fillOpacity: 0.95,
      opacity: 1,
    };
  }
  return {
    radius: 3,
    fillColor: fill,
    color: fill,
    weight: 0.5,
    fillOpacity: 0.75,
    opacity: 0.75,
  };
}

function googleMapsUrl(lat, lng) {
  return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
}

function popupHTML(t) {
  const badges = [];
  if (t.isOperational) {
    badges.push(`<span class="popup-project-badge operational">Operativo</span>`);
  }
  if (t.isApproved) {
    badges.push(`<span class="popup-project-badge approved">Aprobado</span>`);
  }

  const rows = [
    ["Código",                t.codTrafo],
    ["Dirección",             t.dirTrafo || "Sin dirección registrada"],
    ["Propietario",           OWNER_LABELS[t.codPropietario] || t.codPropietario || "—"],
    ["Subestación",           t.codSubE || "—"],
    ["Circuito",              t.codCircuito || "—"],
    ["Nivel de tensión",      VOLTAGE_LABELS[t.formTrafo] || t.formTrafo || "Sin clasificar"],
    ["Fases",                 t.fases != null ? t.fases : "—"],
    ["Potencia nominal",      `${fmt(t.potencia)} kVA`],
    ["Disponible al 50 %",    `${fmt(t.potenciaDisponible)} kVA`],
    ["Potencia asignada",     `${fmt(t.potenciaSoliAprobadas)} kWp`],
    ["Potencia neta disponible", `${fmt(t.potenciaNeta)} kVA`],
    ["Saturación de potencia", `${fmt(t.pctPotencia)} %`],
    ["Demanda de energía",    `${fmt(t.demandaEnergiaUno)} kWh`],
    ["Energía entregada",     `${fmt(t.energiaEntregarHora)} kWh`],
  ];
  const tableRows = rows
    .map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`)
    .join("");

  const gmapsLink =
    t.latTrafo != null && t.lngTrafo != null
      ? `<a class="popup-gmaps" href="${googleMapsUrl(t.latTrafo, t.lngTrafo)}"
            target="_blank" rel="noopener noreferrer">
           Ver en Google Maps ↗
         </a>`
      : "";

  return `
    <p class="popup-title">${t.codTrafo}</p>
    <p class="popup-subtitle">${badges.join(" ")}</p>
    <table class="popup-table">${tableRows}</table>
    ${gmapsLink}
  `;
}

// ---------- Map ----------

function initMap() {
  const map = L.map("map", {
    preferCanvas: true,
    center: CALI_CENTER,
    zoom: CALI_ZOOM,
    minZoom: 10,
    maxZoom: 19,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  state.map = map;
  state.layer = L.layerGroup().addTo(map);
}

function renderMarkers(records) {
  if (state.layer) {
    state.layer.clearLayers();
  }
  state.markersByCode.clear();

  // Draw non-project markers first so project rings sit on top.
  const projects = [];
  const regular = [];
  for (const t of records) {
    if (t.hasProject) projects.push(t);
    else regular.push(t);
  }

  for (const t of regular) addMarker(t);
  for (const t of projects) addMarker(t);
}

function addMarker(t) {
  if (t.latTrafo == null || t.lngTrafo == null) return;
  const m = L.circleMarker([t.latTrafo, t.lngTrafo], markerStyle(t));
  m.bindPopup(() => popupHTML(t), { maxWidth: 300 });
  m.addTo(state.layer);
  state.markersByCode.set(t.codTrafo, m);
}

// ---------- Filters ----------

const SATURATION_SLIDER_MAX = 200;

function getFilterState() {
  const ownerSelect = document.getElementById("filter-owner");
  const selectedOwners = Array.from(ownerSelect.selectedOptions).map(o => o.value);

  const satRaw = Number(document.getElementById("filter-saturation").value);
  const maxSaturation =
    satRaw >= SATURATION_SLIDER_MAX ? Infinity : satRaw;

  return {
    onlyProjects:   document.getElementById("filter-only-projects").checked,
    projectType:    document.getElementById("filter-project-type").value,
    maxSaturation,
    minPotencia:    Number(document.getElementById("filter-min-potencia").value),
    owners:         selectedOwners,
    substation:     document.getElementById("filter-substation").value,
    voltage:        document.getElementById("filter-voltage").value,
  };
}

function updateSaturationLabel() {
  const sat = document.getElementById("filter-saturation");
  const satVal = document.getElementById("filter-saturation-value");
  const v = Number(sat.value);
  satVal.textContent = v >= SATURATION_SLIDER_MAX ? "Sin límite" : `≤ ${v} %`;
}

function applyFilters() {
  const f = getFilterState();

  const filtered = state.allTransformers.filter(t => {
    if (f.onlyProjects && !t.hasProject) return false;

    if (f.projectType === "operational" && !t.isOperational) return false;
    if (f.projectType === "approved"    && !t.isApproved)    return false;
    if (f.projectType === "none"        && t.hasProject)     return false;

    if ((t.pctPotencia || 0) > f.maxSaturation) return false;
    if ((t.potencia || 0) < f.minPotencia) return false;

    if (f.owners.length > 0 && !f.owners.includes(t.codPropietario)) return false;
    if (f.substation && t.codSubE !== f.substation) return false;

    if (f.voltage) {
      const v = t.formTrafo || "NULL";
      if (f.voltage === "NULL" && v !== "NULL") return false;
      if (f.voltage !== "NULL" && v !== f.voltage) return false;
    }

    return true;
  });

  state.filtered = filtered;
  renderMarkers(filtered);
  updateSummary(filtered);
}

function resetFilters() {
  document.getElementById("filter-only-projects").checked = false;
  document.getElementById("filter-project-type").value = "all";
  document.getElementById("filter-saturation").value = SATURATION_SLIDER_MAX;
  updateSaturationLabel();
  document.getElementById("filter-min-potencia").value = 0;
  document.getElementById("filter-min-potencia-value").textContent = "0";
  document.getElementById("filter-substation").value = "";
  document.getElementById("filter-voltage").value = "";
  const ownerSelect = document.getElementById("filter-owner");
  for (const o of ownerSelect.options) o.selected = false;
  applyFilters();
}

// ---------- Summary + charts ----------

function updateSummary(records) {
  document.getElementById("stat-count").textContent = fmtInt.format(records.length);

  let rated = 0, allocated = 0, available = 0;
  let operational = 0, approved = 0;

  for (const t of records) {
    rated      += t.potencia || 0;
    allocated  += t.potenciaSoliAprobadas || 0;
    available  += t.potenciaDisponible || 0;
    if (t.isOperational) operational++;
    if (t.isApproved)    approved++;
  }

  document.getElementById("stat-rated").textContent     = fmtInt.format(Math.round(rated));
  document.getElementById("stat-allocated").textContent = fmtInt.format(Math.round(allocated));
  document.getElementById("stat-available").textContent = fmtInt.format(Math.round(available));
  document.getElementById("stat-operational").textContent = fmtInt.format(operational);
  document.getElementById("stat-approved").textContent    = fmtInt.format(approved);

  renderSaturationChart(records);
  renderSubstationChart(records);
}

function renderSaturationChart(records) {
  const buckets = {
    "Sin asignar (0 %)":  { count: 0, color: COLORS.satNone },
    "Disponible (≤30 %)": { count: 0, color: COLORS.satLow },
    "Moderada (30-40 %)": { count: 0, color: COLORS.satMed },
    "Alta (40-50 %)":     { count: 0, color: COLORS.satHigh },
    "Saturada (>50 %)":   { count: 0, color: COLORS.satFull },
  };
  for (const t of records) {
    const b = saturationBucket(t);
    if (b === "none")      buckets["Sin asignar (0 %)"].count++;
    else if (b === "low")  buckets["Disponible (≤30 %)"].count++;
    else if (b === "med")  buckets["Moderada (30-40 %)"].count++;
    else if (b === "high") buckets["Alta (40-50 %)"].count++;
    else                   buckets["Saturada (>50 %)"].count++;
  }
  const total = records.length || 1;
  const el = document.getElementById("saturation-bars");
  el.innerHTML = Object.entries(buckets)
    .map(([label, { count, color }]) => {
      const pct = (count / total) * 100;
      return `
        <div class="bar-row">
          <div class="bar-label">${label}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${pct.toFixed(1)}%;background:${color}"></div>
          </div>
          <div class="bar-count">${fmtInt.format(count)}</div>
        </div>
      `;
    })
    .join("");
}

function renderSubstationChart(records) {
  const counts = new Map();
  for (const t of records) {
    const sub = t.codSubE || "—";
    counts.set(sub, (counts.get(sub) || 0) + 1);
  }
  const top = Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  const max = top[0] ? top[0][1] : 1;
  const el = document.getElementById("substation-bars");
  if (top.length === 0) {
    el.innerHTML = '<p class="filter-help">Sin datos</p>';
    return;
  }
  el.innerHTML = top
    .map(([sub, count]) => {
      const pct = (count / max) * 100;
      return `
        <div class="bar-row">
          <div class="bar-label">Subestación ${sub}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${pct.toFixed(1)}%"></div>
          </div>
          <div class="bar-count">${fmtInt.format(count)}</div>
        </div>
      `;
    })
    .join("");
}

// ---------- Wire-up ----------

function populateSubstationFilter(records) {
  const subs = new Set();
  for (const t of records) {
    if (t.codSubE) subs.add(t.codSubE);
  }
  const select = document.getElementById("filter-substation");
  for (const sub of Array.from(subs).sort()) {
    const opt = document.createElement("option");
    opt.value = sub;
    opt.textContent = `Subestación ${sub}`;
    select.appendChild(opt);
  }
}

function wireInputs() {
  const ids = [
    "filter-only-projects",
    "filter-project-type",
    "filter-owner",
    "filter-substation",
    "filter-voltage",
  ];
  for (const id of ids) {
    document.getElementById(id).addEventListener("change", applyFilters);
  }

  const sat = document.getElementById("filter-saturation");
  sat.addEventListener("input", updateSaturationLabel);
  sat.addEventListener("change", applyFilters);
  updateSaturationLabel();

  const pot = document.getElementById("filter-min-potencia");
  const potVal = document.getElementById("filter-min-potencia-value");
  pot.addEventListener("input", () => { potVal.textContent = pot.value; });
  pot.addEventListener("change", applyFilters);

  document.getElementById("filter-reset").addEventListener("click", resetFilters);
}

// ---------- Bootstrap ----------

async function loadMetadata() {
  const resp = await fetch(METADATA_URL, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`metadata.json: HTTP ${resp.status}`);
  return resp.json();
}

function applyMetadata(meta) {
  const date = meta.snapshot_date || "—";
  const formattedDate = formatSnapshotDate(date);
  const count = meta.record_count != null
    ? fmtInt.format(meta.record_count)
    : "—";
  for (const el of document.querySelectorAll(".js-snapshot-date")) {
    el.textContent = formattedDate;
  }
  for (const el of document.querySelectorAll(".js-record-count")) {
    el.textContent = count;
  }
}

function loadData() {
  return new Promise((resolve, reject) => {
    Papa.parse(CSV_URL, {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.errors && results.errors.length) {
          console.warn("CSV parse errors:", results.errors.slice(0, 5));
        }
        resolve(results.data.map(parseRow));
      },
      error: reject,
    });
  });
}

async function main() {
  initMap();
  try {
    const [meta, records] = await Promise.all([loadMetadata(), loadData()]);
    applyMetadata(meta);
    state.allTransformers = records;
    populateSubstationFilter(records);
    wireInputs();
    applyFilters();
  } catch (err) {
    console.error("Failed to load data", err);
    document.getElementById("map-loading").innerHTML =
      '<p style="color:#ef4444">No se pudieron cargar los datos. Revisa la consola.</p>';
    return;
  }
  document.getElementById("map-loading").classList.add("hidden");
}

main();
