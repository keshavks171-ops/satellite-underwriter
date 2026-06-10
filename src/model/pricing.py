"""Premium pricing — Phase 3.

Turns the Monte Carlo loss distribution into an actual insurance premium using
the standard-deviation pricing principle:

    expected_loss = mean(loss_distribution)            # the "pure premium"
    risk_load     = k · std(loss_distribution)         # k = 0.25 default
    expense_load  = 15% · (expected_loss + risk_load)
    premium       = expected_loss + risk_load + expense_load
    annual_rate   = premium / value / T_years          # % of asset value per year

Why each piece (so you can defend it):
- **expected_loss** is what we expect to pay out on average — the bare cost of
  the risk. Charging only this would bankrupt the insurer half the time.
- **risk_load** charges extra for *uncertainty*. A risk with a wide loss
  distribution is more dangerous than a predictable one with the same mean, so
  we add `k` standard deviations. This is the textbook "standard-deviation
  principle."
- **expense_load** covers the insurer's running costs (admin, capital, profit),
  taken as a flat 15% of the risk-based premium.
- **annual_rate** re-expresses the premium as a yearly percentage of the
  satellite's value, which is how space insurance is actually quoted.

Units: all dollar amounts in dollars; annual_rate is a fraction per year
(multiply by 100 for a percentage).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.model.montecarlo import SimulationResult, run_simulation

# Default pricing knobs (documented in METHODOLOGY.md).
DEFAULT_RISK_LOAD_K = 0.25       # standard-deviation loading factor
DEFAULT_EXPENSE_RATE = 0.15      # expense load as a fraction of risk premium


@dataclass
class PremiumBreakdown:
    """The premium and its components, all in dollars except annual_rate."""

    expected_loss: float
    risk_load: float
    expense_load: float
    premium: float
    annual_rate: float           # fraction of insured value per year


def price_premium(
    expected_loss: float,
    loss_std: float,
    insured_value: float,
    duration_years: float,
    *,
    risk_load_k: float = DEFAULT_RISK_LOAD_K,
    expense_rate: float = DEFAULT_EXPENSE_RATE,
) -> PremiumBreakdown:
    """Compute the premium breakdown from loss-distribution statistics.

    Args:
        expected_loss: mean of the loss distribution, dollars.
        loss_std: standard deviation of the loss distribution, dollars.
        insured_value: insured value, dollars (used for the annual rate).
        duration_years: mission duration, years (used for the annual rate).
        risk_load_k: standard-deviation loading factor.
        expense_rate: expense load as a fraction of (expected_loss + risk_load).

    Returns:
        A :class:`PremiumBreakdown`.
    """
    risk_load = risk_load_k * loss_std
    expense_load = expense_rate * (expected_loss + risk_load)
    premium = expected_loss + risk_load + expense_load
    # Guard against a zero-value/zero-duration divide; a real quote always has
    # positive value and duration, but keep it defensive.
    if insured_value > 0 and duration_years > 0:
        annual_rate = premium / insured_value / duration_years
    else:
        annual_rate = 0.0
    return PremiumBreakdown(
        expected_loss=expected_loss,
        risk_load=risk_load,
        expense_load=expense_load,
        premium=premium,
        annual_rate=annual_rate,
    )


@dataclass
class Quote:
    """A complete quote: the satellite inputs, the risk distribution, and the
    priced premium. This is the object the Streamlit app (Phase 4) renders."""

    # Echoed inputs
    area_m2: float
    duration_years: float
    insured_value: float
    # Risk (from the Monte Carlo)
    simulation: SimulationResult
    # Pricing
    breakdown: PremiumBreakdown


def generate_quote(
    base_density_per_km3: float,
    area_m2: float,
    duration_years: float,
    insured_value: float,
    *,
    risk_load_k: float = DEFAULT_RISK_LOAD_K,
    expense_rate: float = DEFAULT_EXPENSE_RATE,
    n_trials: int = None,
    seed: int | None = None,
    **sim_kwargs,
) -> Quote:
    """End-to-end: run the Monte Carlo, then price the premium.

    This is the single call the app makes once it has looked up the debris
    density at the user's altitude.

    Args:
        base_density_per_km3: debris density at the satellite's altitude.
        area_m2, duration_years, insured_value: satellite/policy inputs.
        risk_load_k, expense_rate: pricing knobs.
        n_trials, seed, **sim_kwargs: passed through to
            :func:`src.model.montecarlo.run_simulation`.

    Returns:
        A :class:`Quote`.
    """
    # Only forward n_trials if the caller set it, so run_simulation's own
    # default (10,000) stays the single source of truth.
    if n_trials is not None:
        sim_kwargs["n_trials"] = n_trials
    sim = run_simulation(
        base_density_per_km3,
        area_m2,
        duration_years,
        insured_value,
        seed=seed,
        **sim_kwargs,
    )
    breakdown = price_premium(
        sim.expected_loss,
        sim.loss_std,
        insured_value,
        duration_years,
        risk_load_k=risk_load_k,
        expense_rate=expense_rate,
    )
    return Quote(
        area_m2=area_m2,
        duration_years=duration_years,
        insured_value=insured_value,
        simulation=sim,
        breakdown=breakdown,
    )
