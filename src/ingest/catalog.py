"""CelesTrak catalog ingest — Phase 1.

Fetches the `active` satellite catalog plus the four major debris clouds from
CelesTrak, caches each pull to ``data/cache/`` for 24 hours, merges and dedupes
them by NORAD ID, and computes each object's mean altitude.

Public entry point: :func:`load_catalog` -> a clean pandas DataFrame with an
``altitude_km`` column.

Units note: CelesTrak's GP ("General Perturbations") JSON gives mean motion in
*revolutions per day*. We convert that to a mean altitude in *kilometres*.
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

# --- Constants ---------------------------------------------------------------

# CelesTrak GP catalog endpoint. We hit it once per group, max once per 24h.
BASE_URL = "https://celestrak.org/NORAD/elements/gp.php"

# The groups we pull. `active` is every operational satellite; the other four
# are the big debris clouds that dominate LEO collision risk. Order matters for
# dedupe: `active` is listed first, so an operational satellite wins over a
# debris-cloud duplicate (they essentially never overlap, but be deterministic).
GROUPS = [
    "active",
    "cosmos-1408-debris",  # 2021 Russian ASAT test (~550 km)
    "fengyun-1c-debris",   # 2007 Chinese ASAT test (~850 km)
    "iridium-33-debris",   # 2009 Iridium–Cosmos collision (~790 km)
    "cosmos-2251-debris",  # the other half of the 2009 collision
]

# Where cached pulls live. Resolved relative to the repo root (this file is at
# <repo>/src/ingest/catalog.py, so parents[2] is <repo>).
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"

# Bundled snapshot, committed to the repo (unlike the cache). Used as a
# fallback when CelesTrak is unreachable — e.g. Streamlit Community Cloud's
# IP ranges sometimes get rate-limited by CelesTrak.
SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "snapshot"

# Reuse a cached pull for this long before going back to the network.
CACHE_TTL_HOURS = 24

# Network retry: one extra attempt after a short pause covers transient blips
# without hammering CelesTrak (rate-limit-friendly).
FETCH_ATTEMPTS = 2
RETRY_WAIT_SECONDS = 2.0

# Standard gravitational parameter of Earth (G·M), km^3 / s^2.
# Source: WGS-84 / standard astrodynamics value.
MU = 398600.4418

# Mean Earth radius, km. We subtract this from the semi-major axis to get a
# mean altitude above the surface.
EARTH_RADIUS_KM = 6371.0

# Seconds in one day — used to convert mean motion (revs/day) to rad/s.
SECONDS_PER_DAY = 86400.0


# --- Orbital mechanics -------------------------------------------------------

def compute_altitude_km(mean_motion_rev_per_day):
    """Convert mean motion (revolutions/day) to mean altitude (km).

    The math (Kepler's third law, circular-orbit approximation):

        n_rad = n · 2π / 86400          # mean motion in radians/second
        a     = (μ / n_rad²)^(1/3)      # semi-major axis, km   (μ = G·M_earth)
        h     = a − R_earth             # mean altitude, km

    Why this works: a satellite's orbital period depends only on the size of its
    orbit (its semi-major axis ``a``). Mean motion ``n`` is just how many laps it
    does per day, so it encodes the period, and Kepler's third law lets us solve
    for ``a``. Subtracting Earth's radius turns that into a height above the
    surface.

    Simplifying assumption (documented in METHODOLOGY.md): we treat ``a`` as the
    object's altitude, i.e. we pretend every orbit is circular. Real orbits are
    elliptical, so this is the object's *mean* altitude — the standard
    first-order approximation for a debris-density model.

    Works on a single float or a pandas Series / numpy array (vectorised).

    Args:
        mean_motion_rev_per_day: mean motion in revolutions per day (>0).

    Returns:
        Mean altitude in kilometres (same shape as the input).
    """
    n_rad = mean_motion_rev_per_day * 2.0 * math.pi / SECONDS_PER_DAY
    semi_major_axis_km = (MU / n_rad**2) ** (1.0 / 3.0)
    return semi_major_axis_km - EARTH_RADIUS_KM


# --- Cache helpers -----------------------------------------------------------

def _cache_path(group: str) -> Path:
    """File path for a group's cached pull."""
    return CACHE_DIR / f"{group}.json"


def _read_cache(group: str):
    """Return cached objects for ``group`` if the cache is fresh, else None.

    Freshness is decided by the ``fetched_at_unix`` timestamp embedded in the
    file, compared against :data:`CACHE_TTL_HOURS`.
    """
    path = _cache_path(group)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None  # corrupt/unreadable cache -> treat as a miss
    age_seconds = time.time() - payload.get("fetched_at_unix", 0)
    if age_seconds >= CACHE_TTL_HOURS * 3600:
        return None  # stale
    return payload.get("objects")


def _write_cache(group: str, objects: list) -> None:
    """Persist a group's objects to the cache with a fetch timestamp."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    payload = {
        "group": group,
        "fetched_at_unix": now,
        # Human-readable timestamp so anyone can eyeball when this was pulled.
        "fetched_at_iso": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "objects": objects,
    }
    _cache_path(group).write_text(json.dumps(payload))


# --- Fetching ----------------------------------------------------------------

def _fetch_group(group: str, client: httpx.Client) -> list:
    """Fetch one group's GP catalog from CelesTrak as a list of dicts.

    Retries once after a short pause on network errors (transient blips).
    CelesTrak returns a JSON array of objects on success. On an error (bad
    group name, rate limit) it sometimes returns a short string or HTML instead,
    so we guard against that.
    """
    params = {"GROUP": group, "FORMAT": "json"}
    last_error = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            resp = client.get(BASE_URL, params=params)
            resp.raise_for_status()
            break
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < FETCH_ATTEMPTS - 1:
                time.sleep(RETRY_WAIT_SECONDS)
    else:
        raise last_error
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(
            f"Unexpected response for group {group!r} (not a JSON array): "
            f"{str(data)[:200]!r}"
        )
    return data


def _read_snapshot(group: str):
    """Read a group's objects from the bundled snapshot, or None if absent.

    Unlike the cache, the snapshot has no TTL — it's the emergency fallback
    when the network is unavailable, so old data beats no data.
    """
    path = SNAPSHOT_DIR / f"{group}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return payload.get("objects")


# Where the most recent load_catalog() got each group's data from:
# {"group": "cache" | "network" | "snapshot"}. The app reads this to tell the
# user when it's running on the bundled snapshot instead of live data.
LAST_LOAD_SOURCES: dict[str, str] = {}


def _load_all_groups(force_refresh: bool = False):
    """Return ``[(group, objects), ...]``: fresh cache -> network -> snapshot.

    Only opens a network connection if at least one group needs fetching, so a
    fully-cached second call within 24h does zero network I/O. If CelesTrak is
    unreachable (e.g. it rate-limits Streamlit Cloud's IP range), we fall back
    to the snapshot bundled in the repo rather than crash — old data beats no
    data for a demo app, and the UI flags the staleness.

    We never fetch in a tight loop: each group is requested exactly once, all
    over a single shared HTTP client, to respect CelesTrak's rate limits.
    """
    LAST_LOAD_SOURCES.clear()
    results: dict[str, list] = {}
    needs_fetch: list[str] = []

    for group in GROUPS:
        if not force_refresh:
            cached = _read_cache(group)
            if cached is not None:
                results[group] = cached
                LAST_LOAD_SOURCES[group] = "cache"
                continue
        needs_fetch.append(group)

    if needs_fetch:
        headers = {"User-Agent": "satellite-underwriter/0.1 (Hack Club Stardance)"}
        with httpx.Client(timeout=30.0, headers=headers) as client:
            for group in needs_fetch:
                try:
                    objects = _fetch_group(group, client)
                    _write_cache(group, objects)
                    results[group] = objects
                    LAST_LOAD_SOURCES[group] = "network"
                except httpx.HTTPError:
                    snapshot = _read_snapshot(group)
                    if snapshot is None:
                        raise  # no fallback available -> surface the real error
                    results[group] = snapshot
                    LAST_LOAD_SOURCES[group] = "snapshot"

    # Preserve GROUPS order (active first) for deterministic dedupe downstream.
    return [(g, results[g]) for g in GROUPS if g in results]


def used_snapshot() -> bool:
    """True if the most recent load fell back to the bundled snapshot for any
    group (i.e. the data may be stale)."""
    return "snapshot" in LAST_LOAD_SOURCES.values()


# --- Public API --------------------------------------------------------------

def load_catalog(force_refresh: bool = False) -> pd.DataFrame:
    """Load the merged satellite + debris catalog with computed altitudes.

    Fetches (or reuses the 24h cache for) the active catalog and the four debris
    clouds, concatenates them, dedupes by NORAD ID, and adds an ``altitude_km``
    column.

    Args:
        force_refresh: if True, ignore the cache and re-fetch every group.

    Returns:
        A DataFrame with one row per unique object and these columns:
            norad_id        int    — NORAD catalog number (unique key)
            object_name     str    — object name from CelesTrak
            group           str    — which group it came from (active/debris)
            mean_motion     float  — revolutions per day
            eccentricity    float  — orbit eccentricity (0 = circular)
            inclination_deg float  — orbital inclination, degrees
            altitude_km     float  — mean altitude above Earth's surface, km
    """
    loaded = _load_all_groups(force_refresh=force_refresh)

    frames = []
    for group, objects in loaded:
        if not objects:
            continue
        df = pd.DataFrame(objects)
        df["group"] = group
        frames.append(df)

    if not frames:
        raise RuntimeError("No catalog data loaded (every group was empty).")

    raw = pd.concat(frames, ignore_index=True)

    # Dedupe by NORAD ID, keeping the first occurrence (active before debris).
    raw = raw.drop_duplicates(subset="NORAD_CAT_ID", keep="first")

    # Build a clean, explicitly-typed frame. Coerce numerics so a stray bad
    # value becomes NaN rather than blowing up, then drop unusable rows.
    catalog = pd.DataFrame(
        {
            "norad_id": pd.to_numeric(raw["NORAD_CAT_ID"], errors="coerce"),
            "object_name": raw["OBJECT_NAME"].astype("string"),
            "group": raw["group"].astype("string"),
            "mean_motion": pd.to_numeric(raw["MEAN_MOTION"], errors="coerce"),
            "eccentricity": pd.to_numeric(raw["ECCENTRICITY"], errors="coerce"),
            "inclination_deg": pd.to_numeric(raw["INCLINATION"], errors="coerce"),
        }
    )

    # A non-positive or missing mean motion can't yield a real altitude.
    catalog = catalog[catalog["mean_motion"] > 0]
    catalog = catalog.dropna(subset=["norad_id", "mean_motion"])
    catalog["norad_id"] = catalog["norad_id"].astype(int)

    # The whole point of Phase 1: derive altitude from mean motion (vectorised).
    catalog["altitude_km"] = compute_altitude_km(catalog["mean_motion"])

    return catalog.reset_index(drop=True)


if __name__ == "__main__":
    # Manual smoke run: `python -m src.ingest.catalog`
    df = load_catalog()
    print(f"Loaded {len(df):,} unique objects.")
    print(f"Altitude range: {df['altitude_km'].min():.0f} – "
          f"{df['altitude_km'].max():.0f} km")
    print(df[["norad_id", "object_name", "group", "altitude_km"]].head())
