"""Tests for src/ingest/catalog.py — Phase 1.

Two kinds of tests:
1. Hand-checked altitude math (no network).
2. Cache behaviour with the network fetch mocked out, so a second call within
   24h provably hits the cache and never touches the network.
"""

import json
import time

import pandas as pd
import pytest

from src.ingest import catalog


# --- Altitude math (hand-checked) --------------------------------------------

def test_altitude_geostationary():
    """A GEO satellite does ~1.0027 revs/day and sits at ~35,786 km.

    1.0027 revs/day is one lap per sidereal day. Plugging it through Kepler's
    third law must give the textbook geostationary altitude. This is the
    cleanest hand-check because the answer is a famous constant.
    """
    h = catalog.compute_altitude_km(1.0027389)
    assert h == pytest.approx(35786, abs=20)  # km, within 20 km of the textbook value


def test_altitude_iss_like():
    """The ISS does ~15.5 revs/day and orbits at roughly 400–430 km."""
    h = catalog.compute_altitude_km(15.5)
    assert 400 < h < 450


def test_altitude_is_vectorised():
    """compute_altitude_km must work element-wise on a pandas Series."""
    motions = pd.Series([1.0027389, 15.5])
    out = catalog.compute_altitude_km(motions)
    assert isinstance(out, pd.Series)
    assert out.iloc[0] == pytest.approx(35786, abs=20)
    assert 400 < out.iloc[1] < 450


def test_altitude_monotonic():
    """Higher mean motion = shorter, lower orbit. Altitude must decrease as
    mean motion increases."""
    assert catalog.compute_altitude_km(16.0) < catalog.compute_altitude_km(12.0)


# --- Cache behaviour (network mocked) ----------------------------------------

def _fake_objects(group):
    """Two fake catalog objects per group, with unique NORAD ids per group."""
    base = {
        "active": 1000,
        "cosmos-1408-debris": 2000,
        "fengyun-1c-debris": 3000,
        "iridium-33-debris": 4000,
        "cosmos-2251-debris": 5000,
    }[group]
    return [
        {
            "NORAD_CAT_ID": base + i,
            "OBJECT_NAME": f"{group}-{i}",
            "MEAN_MOTION": 15.0,
            "ECCENTRICITY": 0.001,
            "INCLINATION": 53.0,
        }
        for i in range(2)
    ]


@pytest.fixture
def mocked_catalog(tmp_path, monkeypatch):
    """Point the cache at a temp dir and replace the network fetch with a fake
    that counts how many times it is called."""
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)

    calls = {"count": 0}

    def fake_fetch(group, client):
        calls["count"] += 1
        return _fake_objects(group)

    monkeypatch.setattr(catalog, "_fetch_group", fake_fetch)
    return calls


def test_first_call_fetches_every_group(mocked_catalog):
    df = catalog.load_catalog()
    # One fetch per group, exactly once.
    assert mocked_catalog["count"] == len(catalog.GROUPS)
    # 2 fake objects per group, no collisions across groups.
    assert len(df) == 2 * len(catalog.GROUPS)
    assert "altitude_km" in df.columns


def test_second_call_hits_cache_no_network(mocked_catalog):
    catalog.load_catalog()
    fetches_after_first = mocked_catalog["count"]
    # Second call within 24h: cache is fresh, so the fetch must NOT run again.
    catalog.load_catalog()
    assert mocked_catalog["count"] == fetches_after_first


def test_force_refresh_refetches(mocked_catalog):
    catalog.load_catalog()
    fetches_after_first = mocked_catalog["count"]
    catalog.load_catalog(force_refresh=True)
    # force_refresh ignores the cache, so every group is fetched again.
    assert mocked_catalog["count"] == fetches_after_first + len(catalog.GROUPS)


def test_stale_cache_is_ignored(tmp_path, monkeypatch):
    """A cache file older than 24h must be treated as a miss."""
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)
    stale = {
        "group": "active",
        # 25 hours ago — past the 24h TTL.
        "fetched_at_unix": time.time() - 25 * 3600,
        "objects": _fake_objects("active"),
    }
    (tmp_path / "active.json").write_text(json.dumps(stale))
    assert catalog._read_cache("active") is None


def test_fresh_cache_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)
    fresh = {
        "group": "active",
        "fetched_at_unix": time.time(),  # just now
        "objects": _fake_objects("active"),
    }
    (tmp_path / "active.json").write_text(json.dumps(fresh))
    cached = catalog._read_cache("active")
    assert cached is not None
    assert len(cached) == 2


# --- Snapshot fallback (network down) -----------------------------------------

def test_snapshot_fallback_when_network_fails(tmp_path, monkeypatch):
    """If the fetch raises and a snapshot exists, load_catalog uses the snapshot."""
    import httpx

    cache_dir = tmp_path / "cache"
    snap_dir = tmp_path / "snapshot"
    cache_dir.mkdir()
    snap_dir.mkdir()
    monkeypatch.setattr(catalog, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(catalog, "SNAPSHOT_DIR", snap_dir)

    # Bundle a snapshot for every group.
    for g in catalog.GROUPS:
        (snap_dir / f"{g}.json").write_text(
            json.dumps({"group": g, "fetched_at_unix": 0, "objects": _fake_objects(g)})
        )

    def dead_network(group, client):
        raise httpx.ConnectTimeout("simulated: CelesTrak unreachable")

    monkeypatch.setattr(catalog, "_fetch_group", dead_network)

    df = catalog.load_catalog()
    assert len(df) == 2 * len(catalog.GROUPS)  # all groups served from snapshot
    assert catalog.used_snapshot() is True


def test_no_snapshot_reraises_network_error(tmp_path, monkeypatch):
    """With no snapshot available, the network error must surface, not vanish."""
    import httpx

    cache_dir = tmp_path / "cache"
    snap_dir = tmp_path / "snapshot"  # left empty: no fallback
    cache_dir.mkdir()
    snap_dir.mkdir()
    monkeypatch.setattr(catalog, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(catalog, "SNAPSHOT_DIR", snap_dir)

    def dead_network(group, client):
        raise httpx.ConnectTimeout("simulated: CelesTrak unreachable")

    monkeypatch.setattr(catalog, "_fetch_group", dead_network)

    with pytest.raises(httpx.ConnectTimeout):
        catalog.load_catalog()


def test_fresh_cache_skips_snapshot(mocked_catalog):
    """When the cache/network works, used_snapshot() reports False."""
    catalog.load_catalog()
    assert catalog.used_snapshot() is False


def test_dedupe_by_norad_id(tmp_path, monkeypatch):
    """Two objects sharing a NORAD id collapse to one row."""
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)

    def fake_fetch(group, client):
        # Every group returns the SAME single object (same NORAD id).
        return [{
            "NORAD_CAT_ID": 99999,
            "OBJECT_NAME": "DUP",
            "MEAN_MOTION": 15.0,
            "ECCENTRICITY": 0.001,
            "INCLINATION": 53.0,
        }]

    monkeypatch.setattr(catalog, "_fetch_group", fake_fetch)
    df = catalog.load_catalog()
    assert len(df) == 1
    assert df.iloc[0]["norad_id"] == 99999
