# Underwrite a Satellite 🛰️

An insurance pricing engine for spacecraft. Feed it a satellite's orbit, size,
value, and mission length — get back a quoted insurance premium based on real
orbital-debris collision risk, computed from live NASA / CelesTrak catalog data.

Built for the **NASA × Hack Club Stardance Challenge** (deadline: Sept 30, 2026).

> ⚠️ Work in progress. This README is a placeholder; the pitch, screenshots, and
> live demo link land in Phase 5.

## How it works (one-line version)

Live debris catalog → spatial density by altitude → collision flux → Poisson
collision probability → Monte Carlo loss distribution → insurance premium.

The full math, assumptions, and data sources live in
[METHODOLOGY.md](METHODOLOGY.md).

## Quick start (once built)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest                                  # run the test suite
streamlit run src/app/streamlit_app.py  # launch the quote app
```

## Data sources

- **CelesTrak** GP catalog — active satellites + major debris clouds.
- **NASA Orbital Debris Program Office (ODPO)** — lethal non-trackable debris
  population estimates.

Both are credited in full in [METHODOLOGY.md](METHODOLOGY.md).

## Project status

Phase 0 (setup) complete. See [CLAUDE.md](CLAUDE.md) for the build plan.
