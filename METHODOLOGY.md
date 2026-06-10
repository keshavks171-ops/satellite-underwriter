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
  debris population. The tracked catalog only covers objects >10 cm, but ODPO's
  modeling (the ORDEM engineering model and the *Orbital Debris Quarterly News*)
  indicates the 1–10 cm lethal population outnumbers the tracked one by roughly
  an order of magnitude. We encode this as `LNT_MULTIPLIER = 8.0` (default,
  configurable). **TODO before submission:** pin the exact ODPO figure/page this
  8× is taken from (ORDEM 3.x documentation) rather than the order-of-magnitude
  paraphrase here.

## 3. The model

### Step 1 — Mean altitude (Phase 1)

Derived from each object's mean motion via Kepler's third law (see the
circular-orbit assumption in §4).

### Step 2 — Spatial density by altitude (Phase 2)

We bin every object into 25 km altitude shells from 200–2000 km and compute a
*density* (objects per km³), not a raw count, because higher shells enclose more
volume and would otherwise look artificially crowded:

```
shell_volume = (4/3)π [ (R + h₂)³ − (R + h₁)³ ]     # R = 6371 km, km³
density(h)   = count_in_shell / shell_volume         # objects / km³
```

**Why density and not count:** collision risk depends on how *packed* the space
around the satellite is, which is objects per unit volume — dividing out the
shell volume is what makes shells at different altitudes comparable.

### Step 3 — Debris flux (Phase 2)

```
F(h) = density(h) · v_rel · LNT_MULTIPLIER            # impacts / (km² · s)
```

`v_rel` is the average relative impact velocity in LEO (default 10 km/s,
configurable 8–12). `density · v_rel` is the number of objects sweeping through a
1 km² window per second; `LNT_MULTIPLIER` (default 8) scales the tracked
population up to include the 1–10 cm lethal-but-untrackable fragments.

### Step 4 — Collision probability, Poisson model (Phase 2)

```
expected_hits = F · A · T
P_collision   = 1 − exp(−expected_hits)
```

Collisions are rare, independent events at a steady average rate — the textbook
Poisson setup. `F · A · T` is the *expected number* of lethal hits over the
mission; the Poisson chance of zero hits is `exp(−F·A·T)`, so the chance of at
least one is one minus that. **Critical unit conversions:** the cross-section `A`
is entered in m² and converted to km² (×1e-6), and the duration `T` is entered
in years and converted to seconds (×365.25·24·3600), so that `F·A·T` is
dimensionless. The code computes `1 − exp(−x)` as `-expm1(-x)` for numerical
accuracy at small `x`.

### Steps 5–6 — Monte Carlo + pricing

_Added in Phase 3: a 10,000-trial uncertainty simulation and the premium
formula._

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
- **Uniform spread within a shell (Phase 2).** Each object is treated as if it
  spends its whole life uniformly distributed over its mean-altitude shell, so
  the shell's density applies equally everywhere inside it. Real orbits are
  inclined and eccentric, concentrating objects at certain latitudes; uniform
  spreading is the standard first-order density model.
- **Isotropic, steady flux (Phase 2).** Debris is assumed to approach from all
  directions at a single average relative velocity `v_rel` (default 10 km/s),
  and the flux is constant over the mission. This ignores directional
  ("ram vs wake") effects and the slow growth of the debris population over time.
- **Lethal non-trackable scaling (Phase 2).** We multiply the tracked-object
  flux by `LNT_MULTIPLIER = 8` to account for the 1–10 cm fragments that are too
  small to track but still mission-ending. This is a single scalar, not an
  altitude-dependent one — a deliberate simplification.
- _More added in Phase 3:_ total loss on any lethal impact; no
  collision-avoidance maneuvers; in-orbit coverage only (no launch risk);
  single-satellite policy.

## 5. Limitations

_To be written in Phase 5, including why our debris-only premium lands below
the historical ~0.5–2% of asset value per year seen in real space insurance._

## 6. Validation checks

The engine is checked against (see CLAUDE.md for detail):

1. **Density-curve shape** (peaks near ~550, ~800–1000, ~1400–1500 km).
   **PASS (2026-06-09):** the live catalog peaks at **~538 km** (Starlink),
   **~788 km** (sun-sync + the 2009 Iridium-33/Cosmos-2251 collision debris at
   ~790 km), and **~1512 km** — the curve is clearly structured, confirming the
   altitude math.
2. **Order-of-magnitude collision probability** for a reference satellite.
   **PASS:** a 1 m², 5-year mission at 800 km gives **P ≈ 2.3×10⁻⁴**, inside the
   expected 10⁻⁵–10⁻³ band — confirming the m²→km² and years→seconds conversions.
3. **Hand-computed unit tests** (shell volume, small-argument Poisson).
   **PASS:** shell volume for 400–425 km = 1.4456×10¹⁰ km³ (hand-derived), and
   `P ≈ F·A·T` for tiny `F·A·T`. Covered by the pytest suite.

_Results recorded here as the checks are implemented._
