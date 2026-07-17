# Converter tools

Cross-platform, dependency-free Python 3 tools replacing the historical
compiled Windows converters (`objToVertData.exe` / `vertDataToObj.exe`),
and serving every application that speaks OBJ but has no scripting API.

## `od_obj.py` — OBJ ↔ ODVertexData

```
python3 tools/od_obj.py --from-obj model.obj      # OBJ -> exchange file
python3 tools/od_obj.py --to-obj                  # exchange file -> OD_CPE.obj
python3 tools/od_obj.py --to-obj out.obj --in custom/ODVertexData.txt
```

Defaults read/write the shared exchange location (`$OD_CPE_PATH` or the
system temp directory), so the CLI composes directly with every other
implementation. Vertices, polygons (n-gons), material/surface names and UV
maps convert losslessly in both directions; weight and morph maps have no
OBJ equivalent and are dropped with a notice when writing OBJ.

## `od_watch.py` — live OBJ mirror

```
python3 tools/od_watch.py
```

Watches the exchange file and rewrites `OD_CPE.obj` next to it after every
copy from any application. One-way live feed for OBJ-only consumers.

## Application workflows

* **Plasticity** — *copy from Plasticity*: File ▸ Export ▸ OBJ, then
  `--from-obj`. *Paste into Plasticity*: `--to-obj`, then File ▸ Import.
  (A live WebSocket bridge for the copy direction is planned — see the
  roadmap.)
* **Light Tracer Render** — run `od_watch.py`, import `OD_CPE.obj` once,
  then re-import/refresh after each copy from any application. Light Tracer
  has no scripting API; this is a one-way render-target feed.
* **ZBrush / Substance Painter / 3D-Coat / C4D (legacy)** — their upstream
  integrations shell out to the old Windows `.exe` converters; `od_obj.py`
  performs the same conversions on any platform. Export/import OBJ in the
  application and convert manually (or with `od_watch.py`) until each
  integration's rewrite lands.
