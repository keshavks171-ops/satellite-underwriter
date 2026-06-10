"""Debris spatial density by altitude — Phase 2.

Bins cataloged objects into 25 km altitude shells (200–2000 km) and computes a
spatial density (objects per km³) for each shell:

    n(h) = count_in_shell / shell_volume
    shell_volume = (4/3)π [ (R+h₂)³ − (R+h₁)³ ]     # R = 6371 km

Why volume matters: a raw object *count* per shell is misleading because higher
shells are physically bigger (more volume), so they can hold more objects at the
same crowding. Dividing by the shell's volume gives a true *density* — how
packed the space actually is — which is what drives collision risk.

Units: shell volume in km³, density in objects/km³.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Mean Earth radius, km. Matches src/ingest/catalog.py (single physical constant).
EARTH_RADIUS_KM = 6371.0

# Altitude binning: 25 km shells spanning the LEO band the model prices.
SHELL_WIDTH_KM = 25.0
ALTITUDE_MIN_KM = 200.0
ALTITUDE_MAX_KM = 2000.0


def shell_volume_km3(inner_alt_km, outer_alt_km):
    """Volume of a spherical shell between two altitudes (km³).

        V = (4/3)π [ (R + h_outer)³ − (R + h_inner)³ ]

    This is just the volume of the big sphere (out to the outer altitude) minus
    the volume of the smaller sphere (out to the inner altitude) — the leftover
    is the hollow shell between them.

    Works on scalars or numpy arrays (vectorised).

    Args:
        inner_alt_km: inner edge altitude above the surface, km.
        outer_alt_km: outer edge altitude above the surface, km.

    Returns:
        Shell volume in km³.
    """
    r_outer = EARTH_RADIUS_KM + outer_alt_km
    r_inner = EARTH_RADIUS_KM + inner_alt_km
    return (4.0 / 3.0) * math.pi * (r_outer**3 - r_inner**3)


def build_density_profile(
    altitudes_km,
    shell_width_km: float = SHELL_WIDTH_KM,
    alt_min_km: float = ALTITUDE_MIN_KM,
    alt_max_km: float = ALTITUDE_MAX_KM,
) -> pd.DataFrame:
    """Bin object altitudes into shells and compute spatial density per shell.

    Args:
        altitudes_km: array-like of object mean altitudes (km), e.g. the
            ``altitude_km`` column from :func:`src.ingest.catalog.load_catalog`.
            NaNs and altitudes outside [alt_min, alt_max] are ignored.
        shell_width_km: width of each altitude shell (default 25 km).
        alt_min_km, alt_max_km: altitude band to bin over (default 200–2000 km).

    Returns:
        DataFrame, one row per shell, with columns:
            shell_low_km     float — inner edge altitude
            shell_high_km    float — outer edge altitude
            shell_center_km  float — midpoint (handy for plotting)
            count            int   — number of objects in the shell
            volume_km3       float — shell volume
            density_per_km3  float — count / volume (objects per km³)
    """
    alt = np.asarray(altitudes_km, dtype=float)
    alt = alt[~np.isnan(alt)]

    # Shell edges: 200, 225, ..., 2000. np.histogram counts objects per bin.
    edges = np.arange(alt_min_km, alt_max_km + shell_width_km, shell_width_km)
    counts, _ = np.histogram(alt, bins=edges)

    low = edges[:-1]
    high = edges[1:]
    volume = shell_volume_km3(low, high)

    return pd.DataFrame(
        {
            "shell_low_km": low,
            "shell_high_km": high,
            "shell_center_km": (low + high) / 2.0,
            "count": counts.astype(int),
            "volume_km3": volume,
            "density_per_km3": counts / volume,
        }
    )


def density_at_altitude(profile: pd.DataFrame, altitude_km: float) -> float:
    """Look up the spatial density (objects/km³) of the shell containing a given
    altitude.

    This is what the collision model calls with the user's satellite altitude.

    Args:
        profile: a DataFrame from :func:`build_density_profile`.
        altitude_km: the altitude to look up.

    Returns:
        The shell's density in objects/km³, or 0.0 if the altitude falls outside
        the binned band (no cataloged debris there in our model).
    """
    match = profile[
        (profile["shell_low_km"] <= altitude_km)
        & (altitude_km < profile["shell_high_km"])
    ]
    if match.empty:
        return 0.0
    return float(match.iloc[0]["density_per_km3"])
