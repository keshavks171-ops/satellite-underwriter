"""Tests for src/model/collision.py — Phase 2.

Covers the flux formula, the Poisson collision probability, the unit
conversions (m²→km², years→seconds), and validation check #3's small-argument
behaviour (P ≈ F·A·T for tiny F·A·T). All offline.
"""

import numpy as np
import pytest

from src.model import collision


# --- Flux --------------------------------------------------------------------

def test_flux_formula():
    """F = n · v_rel · LNT. With n=1, v_rel=10, LNT=8 → 80."""
    f = collision.debris_flux(1.0, v_rel_km_s=10.0, lnt_multiplier=8.0)
    assert f == pytest.approx(80.0)


def test_flux_uses_defaults():
    """Default v_rel=10, LNT=8, so flux for n=2 is 2·10·8 = 160."""
    assert collision.debris_flux(2.0) == pytest.approx(160.0)


def test_flux_scales_linearly_with_density():
    assert collision.debris_flux(4.0) == pytest.approx(2 * collision.debris_flux(2.0))


def test_flux_vectorised():
    out = collision.debris_flux(np.array([1.0, 2.0]))
    assert out.tolist() == pytest.approx([80.0, 160.0])


# --- Collision probability ---------------------------------------------------

def test_small_argument_taylor(  ):
    """Validation #3: for tiny F·A·T, P ≈ F·A·T (1 − e^-x ≈ x).

    Pick F, A, T so that expected_hits = F·A·T is tiny, then check P matches the
    raw expected_hits to high precision.
    """
    # area 1 m² = 1e-6 km², duration 1 yr = 31,557,600 s.
    # expected_hits = F · 1e-6 · 31,557,600. Choose F = 1e-9 → ~3.16e-8 hits.
    flux = 1e-9
    expected_hits = flux * collision.M2_TO_KM2 * collision.SECONDS_PER_YEAR
    p = collision.collision_probability(flux, area_m2=1.0, duration_years=1.0)
    assert expected_hits < 1e-6          # genuinely in the tiny regime
    assert p == pytest.approx(expected_hits, rel=1e-9)


def test_unit_conversions_explicit():
    """P = 1 − exp(−F·A·T) with A in km² and T in seconds. Verify by computing
    expected_hits the long way and comparing."""
    flux = 50.0          # impacts/(km²·s)
    area_m2 = 2.0        # → 2e-6 km²
    years = 5.0          # → 5 · 31,557,600 s
    expected_hits = flux * (area_m2 * 1e-6) * (years * 365.25 * 24 * 3600)
    p = collision.collision_probability(flux, area_m2, years)
    assert p == pytest.approx(1.0 - np.exp(-expected_hits))


def test_probability_in_unit_interval():
    """A realistic flux gives a probability strictly inside [0, 1).

    (Use a flux that makes expected_hits ~0.6 — large enough to be clearly
    non-tiny, small enough not to floating-point-saturate at exactly 1.0.)
    """
    p = collision.collision_probability(1e-4, area_m2=10.0, duration_years=20.0)
    assert 0.0 <= p < 1.0


def test_probability_monotonic_in_duration():
    """Longer mission → higher collision probability (realistic flux scale)."""
    p2 = collision.collision_probability(1e-7, 2.0, 2.0)
    p5 = collision.collision_probability(1e-7, 2.0, 5.0)
    assert p5 > p2


def test_zero_flux_gives_zero_probability():
    assert collision.collision_probability(0.0, 2.0, 5.0) == 0.0


def test_collision_probability_vectorised():
    """Works element-wise on an array of fluxes (needed for Monte Carlo)."""
    out = collision.collision_probability(np.array([0.0, 50.0]), 2.0, 5.0)
    assert out[0] == 0.0
    assert out[1] > 0.0
