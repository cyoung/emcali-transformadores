# Disponibilidad de transformadores de EMCALI

Aplicación web interactiva, estática y sin backend que muestra los **16.165
transformadores públicos** de la red de distribución de EMCALI en Cali y su
área metropolitana. Permite revisar la saturación de potencia y ubicar los
proyectos de autogeneración solar **operativos** y **aprobados** que aparecen
en el portal público de EMCALI.

> **Aviso:** Este sitio reproduce, de forma **no oficial**, el portal público
> [Consultar Disponibilidad](https://www.emcali.com.co/web/servicios/autogeneracion/consultar-disponibilidad)
> de EMCALI. La fecha exacta de descarga está en `data/metadata.json`
> (la única fuente de verdad) y también se muestra en la barra destacada del
> sitio. Para cualquier decisión operativa, usa siempre el portal oficial.

---

## Qué muestra

- **Mapa de 16.165 transformadores** renderizados sobre canvas (Leaflet),
  coloreados según su nivel de saturación de potencia, con los umbrales del
  propio portal de EMCALI (verde / amarillo / naranja / rojo).
- **99 proyectos solares** destacados con un contorno de color distinto:
  azul para los operativos (ya entregan energía a la red) y morado
  para los aprobados que siguen en trámite.
- **Filtros interactivos** por propietario, subestación, nivel de tensión,
  saturación máxima y potencia nominal mínima.
- **Panel de resumen en vivo** con totales agregados, distribución de
  saturación y las diez subestaciones con más transformadores dentro del
  filtro actual.

## Estructura

```
emcali-transformadores/
├── index.html     # Página principal
├── app.js         # Lógica cliente (carga CSV + metadata, mapa, filtros)
├── style.css      # Estilos
├── data/
│   ├── emcali_transformers.csv  # Copia de los datos (2,3 MB, ~16k filas)
│   └── metadata.json            # Fecha y conteos — fuente única de verdad
├── README.md
└── LICENSE
```

## Licencia

Código: MIT (ver `LICENSE`).

Datos: información pública publicada por EMCALI a través de su portal
_Consultar Disponibilidad_. Este proyecto no está afiliado, patrocinado ni
respaldado por EMCALI; los datos se redistribuyen únicamente con fines
informativos y de investigación.

---

## (English summary)

Static single-page web app that visualizes EMCALI's public
distribution-transformer dataset (16,165 records) for the Cali metro area
as a Leaflet canvas map. Highlights the ~99 transformers with operational
or approved solar interconnection projects. No backend, no build step —
drop the folder onto GitHub Pages and it just works.
