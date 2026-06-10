# Methodology

This document is written for the Hack Club Stardance judges. It records the
math, the assumptions, and the data sources behind every number the engine
quotes. It is filled in as each phase is built — right now it is a skeleton.

## 1. Overview

The engine estimates the probability that a satellite is destroyed by an
orbital-debris collision over its mission, converts that into an expected
financial loss, and prices an insurance premium on top of it.

Pipeline: catalog → spatial density → debris flux → collision probability →
Monte Carlo loss distribution → premium.

## 2. Data sources

- **CelesTrak GP catalog** (primary, no auth): we pull five groups from
  `https://celestrak.org/NORAD/elements/gp.php?GROUP=<group>&FORMAT=json` —
  `active` (all operational satellites) plus the four major debris clouds
  `cosmos-1408-debris`, `fengyun-1c-debris`, `iridium-33-debris`,
  `cosmos-2251-debris`. Each pull is cached to `data/cache/<group>.json` with a
  fetch timestamp and reused for 24 hours, so we hit CelesTrak at most once per
  group per day (it rate-limits aggressive clients). We merge the five groups
  and dedupe by NORAD catalog number.

  **Live catalog size (snapshot 2026-06-09):** 18,242 unique objects —
  active 15,626, fengyun-1c-debris 1,914, cosmos-2251-debris 589,
  iridium-33-debris 110, cosmos-1408-debris 3. The Cosmos-1408 cloud (a 2021
  low-altitude ~480 km ASAT test) has almost entirely re-entered, and the older
  2007/2009 clouds have thinned, so the live count sits below the ~20k seen in
  earlier snapshots. This is real orbital decay, not a data error: zero rows are
  dropped by the dedupe/clean step.
- **NASA Orbital Debris Program Office (ODPO)**: lethal non-trackable (1–10 cm)
  debris population. Encoded as `LNT_MULTIPLIER = 8.0` (default). _Exact
  citation to be added in Phase 2._

## 3. The model

_Filled in across Phases 2–3. Will cover: mean-altitude derivation, 25 km
shells and shell volumes, spatial density, debris flux, the Poisson collision
model, the Monte Carlo uncertainty simulation, and the premium formula._

## 4. Assumptions (running list)

These are the simplifying assumptions the model makes. Each is restated next to
the code that relies on it.

- **Circular-orbit / mean-altitude approximation (Phase 1).** We derive each
  object's altitude from its mean motion via Kepler's third law,
  `a = (μ / n_rad²)^(1/3)` with `μ = 398600.4418 km³/s²` and
  `R_earth = 6371 km`, then take altitude `h = a − R_earth`. This treats every
  orbit as circular, so `h` is the object's *mean* altitude. Real orbits are
  elliptical and inclined; using the semi-major axis is the standard first-order
  approximation for a debris-density model. A handful of highly eccentric or
  deep-space objects get large/odd altitudes and simply fall outside the
  200–2000 km LEO shells the model bins (Phase 2), so they don't distort it.
- _More added as the model is built:_ each object spends its whole life
  uniformly spread over its mean-altitude shell; total loss on any lethal
  impact; no collision-avoidance maneuvers; in-orbit coverage only (no launch
  risk); single-satellite policy.

## 5. Limitations

_To be written in Phase 5, including why our debris-only premium lands below
the historical ~0.5–2% of asset value per year seen in real space insurance._

## 6. Validation checks

The engine is checked against (see CLAUDE.md for detail):

1. Density-curve shape (peaks near ~550, ~800–1000, ~1400–1500 km).
2. Order-of-magnitude collision probability for a reference satellite.
3. Hand-computed unit tests (shell volume, small-argument Poisson).

_Results recorded here as the checks are implemented._
