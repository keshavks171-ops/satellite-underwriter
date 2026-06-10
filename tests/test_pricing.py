"""Tests for src/model/pricing.py — Phase 3.

The premium formula is deterministic, so these are hand-checked exact values.
Plus an end-to-end generate_quote consistency test (seeded). All offline.
"""

import pytest

from src.model import pricing


# --- price_premium (hand-checked) --------------------------------------------

def test_premium_breakdown_hand_check():
    """Worked example, computed by hand:

        expected_loss = 1000, loss_std = 400, k = 0.25, expense = 15%,
        value = 1,000,000, T = 5 yr

        risk_load    = 0.25 · 400               = 100
        expense_load = 0.15 · (1000 + 100)      = 165
        premium      = 1000 + 100 + 165         = 1265
        annual_rate  = 1265 / 1,000,000 / 5     = 2.53e-4  (0.0253%/yr)
    """
    b = pricing.price_premium(
        expected_loss=1000.0, loss_std=400.0,
        insured_value=1_000_000.0, duration_years=5.0,
    )
    assert b.risk_load == pytest.approx(100.0)
    assert b.expense_load == pytest.approx(165.0)
    assert b.premium == pytest.approx(1265.0)
    assert b.annual_rate == pytest.approx(2.53e-4)


def test_premium_is_sum_of_components():
    b = pricing.price_premium(2000.0, 800.0, 5_000_000.0, 3.0)
    assert b.premium == pytest.approx(b.expected_loss + b.risk_load + b.expense_load)


def test_expense_is_fraction_of_risk_premium():
    b = pricing.price_premium(2000.0, 800.0, 5_000_000.0, 3.0)
    assert b.expense_load == pytest.approx(0.15 * (b.expected_loss + b.risk_load))


def test_annual_rate_formula():
    b = pricing.price_premium(2000.0, 800.0, 5_000_000.0, 3.0)
    assert b.annual_rate == pytest.approx(b.premium / 5_000_000.0 / 3.0)


def test_custom_knobs():
    """Different k and expense rate flow through correctly."""
    b = pricing.price_premium(
        1000.0, 400.0, 1_000_000.0, 5.0,
        risk_load_k=0.5, expense_rate=0.20,
    )
    # risk_load = 0.5·400 = 200; expense = 0.20·(1000+200) = 240; premium = 1440
    assert b.risk_load == pytest.approx(200.0)
    assert b.expense_load == pytest.approx(240.0)
    assert b.premium == pytest.approx(1440.0)


def test_zero_loss_zero_premium():
    b = pricing.price_premium(0.0, 0.0, 1_000_000.0, 5.0)
    assert b.premium == 0.0
    assert b.annual_rate == 0.0


def test_zero_value_does_not_divide_by_zero():
    b = pricing.price_premium(1000.0, 400.0, 0.0, 5.0)
    assert b.annual_rate == 0.0  # defensive guard, not a crash


# --- generate_quote (end-to-end consistency) ---------------------------------

def test_generate_quote_is_consistent():
    """The Quote's premium must match re-pricing its own simulation stats."""
    q = pricing.generate_quote(
        base_density_per_km3=1.86e-8,
        area_m2=2.0, duration_years=5.0, insured_value=1e7,
        n_trials=2000, seed=99,
    )
    recomputed = pricing.price_premium(
        q.simulation.expected_loss, q.simulation.loss_std,
        q.insured_value, q.duration_years,
    )
    assert q.breakdown.premium == pytest.approx(recomputed.premium)
    assert q.breakdown.premium > 0
    assert q.breakdown.annual_rate > 0
    assert q.simulation.losses.shape == (2000,)


def test_generate_quote_premium_exceeds_expected_loss():
    """A loaded premium must always exceed the bare expected loss."""
    q = pricing.generate_quote(1.86e-8, 2.0, 5.0, 1e7, n_trials=2000, seed=7)
    assert q.breakdown.premium > q.simulation.expected_loss
