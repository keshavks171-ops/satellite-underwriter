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

- **CelesTrak GP catalog** (primary, no auth): active satellites and the four
  major debris clouds (Cosmos-1408, Fengyun-1C, Iridium-33, Cosmos-2251).
  _To be detailed in Phase 1._
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

- _Added as the model is built._ Examples to come: each object spends its whole
  life uniformly spread over its mean-altitude shell; total loss on any lethal
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
