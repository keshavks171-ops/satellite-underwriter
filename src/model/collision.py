"""Debris flux + Poisson collision probability — Phase 2.

Two steps, kept separate so each can be unit-tested:

    Step 2 — flux:        F(h) = n(h) · v_rel · LNT_MULTIPLIER
    Step 3 — collision:   P    = 1 − exp(−F · A · T)

Units are the #1 risk in this project, so they are spelled out on every function.
"""

from __future__ import annotations

import numpy as np

# --- Constants ---------------------------------------------------------------

# Lethal non-trackable (LNT) factor. The tracked catalog only contains objects
# larger than ~10 cm, but 1–10 cm fragments can still destroy a satellite. NASA
# ODPO population estimates put the lethal population at roughly an order of
# magnitude above the tracked one; we use 8× as a configurable default.
# Source: NASA Orbital Debris Program Office — exact citation in METHODOLOGY.md.
LNT_MULTIPLIER = 8.0

# Average relative impact velocity between objects in LEO, km/s. Real values
# range ~8–12 km/s depending on geometry; 10 km/s is the standard mean.
DEFAULT_V_REL_KM_S = 10.0

# Unit conversion to watch: 1 m² = 1e-6 km². Cross-sections are entered in m²
# but the flux is per km², so we MUST convert before multiplying.
M2_TO_KM2 = 1e-6

# Seconds in a year (Julian year, 365.25 days). Mission duration is entered in
# years but the flux is per second, so we convert before multiplying.
SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0


def debris_flux(
    density_per_km3,
    v_rel_km_s: float = DEFAULT_V_REL_KM_S,
    lnt_multiplier: float = LNT_MULTIPLIER,
):
    """Lethal debris flux through a unit cross-section.

        F = n · v_rel · LNT_MULTIPLIER

    Intuition: if space has ``n`` objects per km³ and they sweep past at
    ``v_rel`` km/s, then the number crossing a 1 km² window each second is
    ``n · v_rel``. Multiplying by the LNT factor scales the tracked population up
    to include the smaller-but-still-lethal fragments we can't see.

    Units check:
        [objects/km³] · [km/s] · [dimensionless] = objects / (km² · s)   ✓

    Works on scalars or numpy arrays.

    Args:
        density_per_km3: spatial density, objects/km³ (from density.py).
        v_rel_km_s: relative impact velocity, km/s.
        lnt_multiplier: lethal non-trackable scale factor (dimensionless).

    Returns:
        Flux in impacts per km² per second.
    """
    return density_per_km3 * v_rel_km_s * lnt_multiplier


def collision_probability(
    flux_per_km2_s,
    area_m2,
    duration_years,
):
    """Probability of at least one lethal collision over the mission (Poisson).

        expected_hits = F · A · T
        P = 1 − exp(−expected_hits)

    Why Poisson: collisions are rare, independent events arriving at a steady
    average rate, which is exactly the Poisson model. ``F · A · T`` is the
    expected *number* of hits over the mission; the Poisson chance of zero hits
    is ``exp(−expected_hits)``, so the chance of *at least one* is one minus that.

    Units check:
        F [1/(km²·s)] · A [km²] · T [s] = dimensionless   ✓
    so we convert A from m²→km² (×1e-6) and T from years→seconds first.

    Implementation note: we compute ``1 − exp(−x)`` as ``-expm1(-x)``. For a tiny
    expected_hits (the usual case here) this is numerically exact and recovers
    the Taylor expansion P ≈ F·A·T, instead of losing precision to floating-point
    cancellation. Works on scalars or numpy arrays.

    Args:
        flux_per_km2_s: debris flux, impacts/(km²·s) (from debris_flux).
        area_m2: satellite cross-sectional area, m².
        duration_years: mission duration, years.

    Returns:
        Collision probability over the mission (0–1).
    """
    area_km2 = area_m2 * M2_TO_KM2
    duration_s = duration_years * SECONDS_PER_YEAR
    expected_hits = flux_per_km2_s * area_km2 * duration_s
    return -np.expm1(-expected_hits)
