# New York, November 2026

A family travel site about our trip to New York (Nov 3–11, 2026), in Russian and English.

This repository holds the **built static site** (served by GitHub Pages from `main`, repo root).
The source (content, templates, build script) lives in `_src/`:

- `_src/content.yaml` — all texts, days and "moments" (the single source of truth)
- `_src/templates/`, `_src/static/` — page templates, CSS and JS
- `_src/build.py` — `python3 _src/build.py .` rebuilds every page (needs PyYAML + Jinja2 and the processed media folder)

Photos and videos are resized and stripped of EXIF/GPS metadata before publishing.
