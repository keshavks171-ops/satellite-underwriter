"""Tests for src/model/density.py — Phase 2.

Covers validation check #3 (hand-computed shell volume) plus the binning and
density-lookup logic. All offline — no catalog data needed.
"""

import numpy as np
import pytest

from src.model import density


# --- Shell volume (hand-checked, validation #3) ------------------------------

def test_shell_volume_400_to_425_hand_check():
    """Shell volume for the 400–425 km shell, computed by hand.

    R = 6371 km, so the shell runs from r₁ = 6771 km to r₂ = 6796 km.
        V = (4/3)π (6796³ − 6771³)
          = (4/3)π (313,877,446,336 − 310,426,252,011)
          = (4/3)π · 3,451,194,325
          ≈ 1.4456 × 10¹⁰ km³
    """
    v = density.shell_volume_km3(400, 425)
    assert v == pytest.approx(1.4456e10, rel=1e-3)


def test_shell_volume_positive_and_grows_with_altitude():
    """Same-width shells get bigger as you go higher (more surface area)."""
    low = density.shell_volume_km3(200, 225)
    high = density.shell_volume_km3(1975, 2000)
    assert low > 0
    assert high > low


def test_shell_volume_vectorised():
    """shell_volume_km3 must work element-wise on numpy arrays."""
    inner = np.array([400.0, 800.0])
    outer = np.array([425.0, 825.0])
    out = density.shell_volume_km3(inner, outer)
    assert out.shape == (2,)
    assert out[0] == pytest.approx(1.4456e10, rel=1e-3)


# --- Density profile ---------------------------------------------------------

def test_profile_shells_span_200_to_2000():
    profile = density.build_density_profile([550.0])
    assert profile["shell_low_km"].iloc[0] == 200.0
    assert profile["shell_high_km"].iloc[-1] == 2000.0
    # (2000 - 200) / 25 = 72 shells.
    assert len(profile) == 72


def test_profile_counts_land_in_right_shell():
    """An object at 560 km belongs in the 550–575 km shell, and nowhere else."""
    profile = density.build_density_profile([560.0, 560.0, 560.0])
    shell = profile[(profile["shell_low_km"] == 550.0)]
    assert shell["count"].iloc[0] == 3
    assert profile["count"].sum() == 3  # nothing leaked into other shells


def test_profile_density_is_count_over_volume():
    profile = density.build_density_profile([560.0, 560.0])
    shell = profile[profile["shell_low_km"] == 550.0].iloc[0]
    expected = shell["count"] / shell["volume_km3"]
    assert shell["density_per_km3"] == pytest.approx(expected)


def test_profile_ignores_out_of_band_and_nan():
    """Altitudes below 200, above 2000, or NaN are dropped, not binned."""
    profile = density.build_density_profile([150.0, 5000.0, np.nan, 560.0])
    assert profile["count"].sum() == 1  # only the 560 km object counts


# --- Density lookup ----------------------------------------------------------

def test_density_at_altitude_matches_profile():
    profile = density.build_density_profile([560.0, 560.0])
    looked_up = density.density_at_altitude(profile, 560.0)
    shell = profile[profile["shell_low_km"] == 550.0].iloc[0]
    assert looked_up == pytest.approx(shell["density_per_km3"])


def test_density_at_altitude_out_of_band_is_zero():
    profile = density.build_density_profile([560.0])
    assert density.density_at_altitude(profile, 5000.0) == 0.0
