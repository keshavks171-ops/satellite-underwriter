"""Tests for src/model/montecarlo.py — Phase 3.

The simulation is random, so we test its *structural* guarantees (shapes,
ranges, determinism under a seed, monotonic response to inputs) rather than
exact values. All offline.
"""

import numpy as np
import pytest

from src.model import montecarlo

# A realistic-ish debris density (~the 800 km shell from Phase 2 validation).
BASE_DENSITY = 1.86e-8


def test_result_array_lengths():
    res = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 10_000_000, n_trials=1000, seed=1)
    assert res.n_trials == 1000
    assert res.losses.shape == (1000,)
    assert res.probabilities.shape == (1000,)


def test_determinism_with_seed():
    """Same seed -> identical results (needed so a quote is reproducible)."""
    a = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 1e7, n_trials=500, seed=42)
    b = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 1e7, n_trials=500, seed=42)
    assert np.array_equal(a.losses, b.losses)
    assert a.expected_loss == b.expected_loss


def test_different_seeds_differ():
    a = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 1e7, n_trials=500, seed=1)
    b = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 1e7, n_trials=500, seed=2)
    assert not np.array_equal(a.losses, b.losses)


def test_probabilities_in_unit_interval():
    res = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 1e7, n_trials=2000, seed=3)
    assert np.all(res.probabilities >= 0.0)
    assert np.all(res.probabilities <= 1.0)


def test_loss_never_exceeds_insured_value():
    """Loss = P × value and P ≤ 1, so no trial can lose more than the value."""
    value = 1e7
    res = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, value, n_trials=2000, seed=4)
    assert np.all(res.losses <= value)
    assert np.all(res.losses >= 0.0)


def test_percentile_ordering():
    """P99 sits at or beyond P95, which sits at or beyond the mean."""
    res = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 1e7, n_trials=5000, seed=5)
    assert res.loss_p99 >= res.loss_p95
    assert res.loss_p95 >= res.expected_loss


def test_zero_density_gives_zero_loss():
    res = montecarlo.run_simulation(0.0, 2.0, 5.0, 1e7, n_trials=1000, seed=6)
    assert res.expected_loss == 0.0
    assert np.all(res.losses == 0.0)
    assert res.loss_std == 0.0


def test_higher_density_means_higher_expected_loss():
    """Monotonicity: more debris -> more expected loss (same seed for fairness)."""
    low = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 1e7, n_trials=4000, seed=7)
    high = montecarlo.run_simulation(BASE_DENSITY * 5, 2.0, 5.0, 1e7, n_trials=4000, seed=7)
    assert high.expected_loss > low.expected_loss


def test_default_is_ten_thousand_trials():
    res = montecarlo.run_simulation(BASE_DENSITY, 2.0, 5.0, 1e7, seed=8)
    assert res.n_trials == 10_000
    assert res.losses.shape == (10_000,)
