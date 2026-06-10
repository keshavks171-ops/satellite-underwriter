"""Monte Carlo uncertainty simulation — Phase 3.

We never know the debris density, impact velocity, or even the satellite's
exact cross-section precisely. Instead of pretending we do, we run the collision
model 10,000 times, each time drawing those uncertain inputs from a plausible
range. The result is a *distribution* of possible losses, not a single number —
which is what lets us quote a risk-loaded premium (Phase 3 pricing) and report
VaR-style tail metrics (P95/P99).

Per trial we sample:
    density scale  ~ lognormal(median 1, σ ≈ 0.30)   # ±~30% on debris density
    v_rel          ~ uniform(8, 12) km/s             # impact velocity
    area           ~ uniform(±10%) of the nominal area

Each trial -> a collision probability -> a loss (P × insured value).

Units: losses in dollars, probabilities dimensionless.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.model.collision import (
    LNT_MULTIPLIER,
    collision_probability,
    debris_flux,
)

# Default uncertainty knobs (documented in METHODOLOGY.md).
DEFAULT_N_TRIALS = 10_000
DENSITY_LOG_SIGMA = 0.30        # σ of the lognormal density scale factor
V_REL_LOW_KM_S = 8.0
V_REL_HIGH_KM_S = 12.0
AREA_REL_UNCERTAINTY = 0.10     # ±10% on cross-section


@dataclass
class SimulationResult:
    """Outcome of a Monte Carlo run.

    Arrays are length ``n_trials`` (kept for plotting the loss histogram in
    Phase 4); the scalars are the summary statistics the pricing step needs.
    """

    losses: np.ndarray          # per-trial loss, dollars
    probabilities: np.ndarray   # per-trial collision probability
    expected_loss: float        # mean loss (the actuarial "pure premium")
    loss_std: float             # std of loss (drives the risk load)
    loss_p95: float             # 95th-percentile loss — VaR-style tail metric
    loss_p99: float             # 99th-percentile loss — deeper tail metric
    mean_probability: float     # mean collision probability over the mission
    n_trials: int


def run_simulation(
    base_density_per_km3: float,
    area_m2: float,
    duration_years: float,
    insured_value: float,
    *,
    v_rel_low: float = V_REL_LOW_KM_S,
    v_rel_high: float = V_REL_HIGH_KM_S,
    density_log_sigma: float = DENSITY_LOG_SIGMA,
    area_rel_uncertainty: float = AREA_REL_UNCERTAINTY,
    lnt_multiplier: float = LNT_MULTIPLIER,
    n_trials: int = DEFAULT_N_TRIALS,
    seed: int | None = None,
) -> SimulationResult:
    """Run the Monte Carlo collision/loss simulation.

    Args:
        base_density_per_km3: nominal debris density at the satellite's altitude
            (objects/km³), e.g. from
            :func:`src.model.density.density_at_altitude`.
        area_m2: nominal cross-sectional area, m².
        duration_years: mission duration, years.
        insured_value: insured value of the satellite, dollars.
        v_rel_low, v_rel_high: bounds of the uniform impact-velocity draw, km/s.
        density_log_sigma: σ of the lognormal density scale factor (median 1).
        area_rel_uncertainty: fractional ± range on the area draw (0.10 = ±10%).
        lnt_multiplier: lethal non-trackable scale factor.
        n_trials: number of Monte Carlo trials.
        seed: optional RNG seed for reproducibility (tests pass one).

    Returns:
        A :class:`SimulationResult`.
    """
    rng = np.random.default_rng(seed)

    # --- Sample the uncertain inputs (one draw per trial) --------------------
    # Lognormal with the underlying normal having mean 0 -> median scale = 1, so
    # the density is scaled up or down symmetrically in log-space by ~σ.
    density_scale = rng.lognormal(mean=0.0, sigma=density_log_sigma, size=n_trials)
    v_rel = rng.uniform(v_rel_low, v_rel_high, size=n_trials)
    area = rng.uniform(
        area_m2 * (1.0 - area_rel_uncertainty),
        area_m2 * (1.0 + area_rel_uncertainty),
        size=n_trials,
    )

    # --- Push each trial through the collision model (vectorised) -----------
    density_trial = base_density_per_km3 * density_scale
    flux = debris_flux(density_trial, v_rel_km_s=v_rel, lnt_multiplier=lnt_multiplier)
    probabilities = collision_probability(flux, area, duration_years)

    # Total-loss assumption: any lethal impact destroys the satellite, so the
    # loss in a trial is the collision probability times the full insured value.
    losses = probabilities * insured_value

    return SimulationResult(
        losses=losses,
        probabilities=probabilities,
        expected_loss=float(np.mean(losses)),
        loss_std=float(np.std(losses)),
        loss_p95=float(np.percentile(losses, 95)),
        loss_p99=float(np.percentile(losses, 99)),
        mean_probability=float(np.mean(probabilities)),
        n_trials=n_trials,
    )
