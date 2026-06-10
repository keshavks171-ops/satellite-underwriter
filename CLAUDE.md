# CLAUDE.md — Underwrite a Satellite 🛰️

An insurance pricing engine for spacecraft. Input a satellite's orbit, size,
value, and mission length — get back a quoted insurance premium based on real
orbital debris collision risk, computed from live NASA/CelesTrak catalog data.

Built for the NASA × Hack Club Stardance Challenge (deadline: Sept 30, 2026).

## Who's building this

A high school student with solid Python basics, learning the math and tooling as
he goes. Claude Code should therefore:

- Prefer simple, readable code over clever code
- Explain every non-obvious formula in comments (he must be able to defend the
  methodology to Hack Club reviewers)
- Write tests for every model function before moving to the next phase
- Flag any assumption being made, in code comments and in METHODOLOGY.md
- Never silently change units — unit bugs are the #1 risk in this project

## Tech stack

| Layer    | Choice              | Why                              |
| -------- | ------------------- | -------------------------------- |
| Language | Python 3.11+        | Familiar, fast to build          |
| Data     | httpx, pandas, numpy| Fetch + wrangle catalog data     |
| UI       | Streamlit + Plotly  | Full app in pure Python, free host |
| Tests    | pytest              | Run after every phase            |
| Deploy   | Streamlit Community Cloud | Free, one-click from GitHub  |

No database needed — cache catalog snapshots as local JSON/parquet files.

## Repo structure

```
satellite-underwriter/
├── CLAUDE.md                  # this file
├── README.md                  # public-facing: what it is, demo link, screenshots
├── METHODOLOGY.md             # the math, assumptions, data sources (judges read this)
├── requirements.txt
├── data/
│   └── cache/                 # cached catalog pulls (gitignored)
├── src/
│   ├── ingest/
│   │   └── catalog.py         # fetch + cache CelesTrak data, compute altitudes
│   ├── model/
│   │   ├── density.py         # debris spatial density by altitude
│   │   ├── collision.py       # flux + collision probability
│   │   ├── montecarlo.py      # uncertainty simulation
│   │   └── pricing.py         # premium calculation
│   └── app/
│       └── streamlit_app.py   # the quote UI
├── tests/
│   ├── test_density.py
│   ├── test_collision.py
│   └── test_pricing.py
└── notebooks/                 # optional exploration
```

## Data sources

### 1. CelesTrak GP catalog (primary, no auth required)

- All active satellites: `https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json`
- Major debris clouds (fetch each, same URL pattern with `GROUP=`):
  cosmos-1408-debris, fengyun-1c-debris, iridium-33-debris, cosmos-2251-debris
- Optionally `GROUP=last-30-days` for recent launches

Rules: cache every pull to `data/cache/` with a timestamp and reuse for 24h.
CelesTrak rate-limits aggressive clients — never fetch in a loop.

### 2. NASA Orbital Debris Program Office (published constants)

Tracked catalog objects are only the >10 cm population. Smaller "lethal
non-trackable" debris (1–10 cm) can still destroy a satellite. ODPO publications
estimate roughly an order of magnitude more lethal objects than tracked ones. We
encode this as a configurable constant:

```python
LNT_MULTIPLIER = 8.0  # lethal non-trackable factor, default 8x tracked flux
# Source: NASA ODPO published population estimates; document exact citation in METHODOLOGY.md
```

### 3. Satellite parameters: user input

Altitude (km), cross-sectional area (m²), mission duration (years), insured
value ($).

## The model (the heart of the project)

### Step 1 — Spatial density by altitude

For each cataloged object, derive mean altitude from its mean motion `n`
(revs/day in GP data):

```
n_rad = n * 2π / 86400                 # rad/s
a = (μ / n_rad²)^(1/3)                 # semi-major axis, μ = 398600.4418 km³/s²
h = a − 6371                           # mean altitude, km
```

Bin all objects into 25 km altitude shells from 200–2000 km. Spatial density per
shell:

```
n(h) = count_in_shell / shell_volume
shell_volume = (4/3)π [ (R+h₂)³ − (R+h₁)³ ]     # R = 6371 km → density in objects/km³
```

Simplifying assumption (document it): each object spends its whole life
uniformly spread over its mean-altitude shell. Real orbits are elliptical and
inclined; this is the standard first-order approximation.

### Step 2 — Debris flux

```
F(h) = n(h) × v_rel × LNT_MULTIPLIER
```

`v_rel` = average relative impact velocity in LEO, default 10 km/s (configurable
8–12). Flux units: impacts per km² per second.

### Step 3 — Collision probability (Poisson model)

```
P_collision = 1 − exp(−F × A × T)
```

`A` = satellite cross-section, converted m² → km² (× 1e-6) — watch this
conversion. `T` = mission duration in seconds.

### Step 4 — Monte Carlo uncertainty

10,000 trials, sampling:

- density scale factor ~ lognormal, σ ≈ 30%
- v_rel ~ uniform(8, 12) km/s
- area ±10%

Each trial → a collision probability → a loss (P × value). Output the loss
distribution: mean, std, P95, P99. (Frame P95/P99 as VaR-style tail metrics.)

### Step 5 — Premium pricing

```
expected_loss   = mean(loss_distribution)
risk_load       = k × std(loss_distribution)        # k = 0.25 default (std-deviation principle)
expense_load    = 15% of (expected_loss + risk_load)
premium         = expected_loss + risk_load + expense_load
annual_rate     = premium / value / T_years          # display as % of asset value per year
```

Assumptions to document: total loss on any lethal impact, no collision-avoidance
maneuvers, no launch risk (in-orbit coverage only), single-satellite policy.

## Validation checks (run before trusting any output)

- **Density curve shape:** peaks should appear near ~550 km (Starlink shell),
  ~800–1000 km (debris clouds + sun-sync), and ~1400–1500 km. If the curve is
  flat or random, the altitude math is wrong.
- **Order of magnitude:** a 1 m² satellite, 5-year mission at 800 km should land
  roughly in the 10⁻⁵ to 10⁻³ collision-probability range. Outside that → unit
  bug, almost certainly the m²→km² or years→seconds conversion.
- **Hand-checked unit tests:** shell volume for 400–425 km computed by hand;
  P_collision for tiny F·A·T should ≈ F·A·T (Taylor expansion).
- **Premium sanity band:** real in-orbit space insurance has historically run
  very roughly ~0.5–2% of asset value per year. Our tracked+LNT model will land
  lower for small sats — that's fine, explain the gap in METHODOLOGY.md.

## Build phases — one Claude Code session each

Start each session with: "Read CLAUDE.md, then implement Phase N. Write tests and
run pytest before finishing." Commit after every phase.

- **Phase 0 — Setup:** init repo, venv, requirements.txt, folder structure,
  .gitignore (include data/cache/). Done when: pytest runs (zero tests, zero
  errors) and repo is on GitHub.
- **Phase 1 — Ingest** (`src/ingest/catalog.py`): fetch active + 4 debris
  groups, merge, dedupe by NORAD ID, 24h file cache, compute mean altitude.
  Done when: one call returns a DataFrame of 20,000+ objects with an
  `altitude_km` column and a second call within 24h hits cache.
- **Phase 2 — Density + collision** (`density.py`, `collision.py`): binning,
  shell volumes, density curve, flux and Poisson probability, unit-tested. Done
  when: validation checks #1–#3 pass.
- **Phase 3 — Monte Carlo + pricing** (`montecarlo.py`, `pricing.py`):
  10k-trial sim returning a loss distribution; pricing function returning the
  premium breakdown. Done when: tests pass and a sample quote for
  (550 km, 2 m², 5 yr, $10M) prints a full breakdown.
- **Phase 4 — Streamlit app** (`streamlit_app.py`): quote form + premium card +
  three charts. Done when: `streamlit run` gives a working quote in under 3s.
- **Phase 5 — Polish + ship:** write METHODOLOGY.md and README.md, deploy to
  Streamlit Community Cloud, record a 60–90s demo. Done when: public URL works
  from a phone.

## Stretch goals (only after Phase 5)

- Inclination-dependent v_rel
- Constellation mode: price N satellites as a portfolio, show diversification
- PDF quote export
- Historical mode: re-run pricing before/after the 2021 Cosmos-1408 ASAT event

## Working agreements with Claude Code

- One phase per session; don't skip ahead.
- Every model function gets a docstring stating its units for inputs and outputs.
- After writing code, run the tests and the validation checks — don't just claim
  they pass.
- When the student asks "why," explain the math like he's smart but new to it.
- Keep METHODOLOGY.md updated as assumptions get added — it's written for
  challenge judges.

## Submission checklist (Hack Club Stardance)

- Public GitHub repo with README + METHODOLOGY
- Live demo URL
- Short demo video/GIF
- Data sources credited (CelesTrak, NASA ODPO)
- Submitted before Sept 30, 2026.
