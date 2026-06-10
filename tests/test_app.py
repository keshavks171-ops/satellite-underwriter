"""Smoke test for the Streamlit app — Phase 4.

Uses Streamlit's AppTest harness to run the whole script in-process with default
widget values and assert it produces a quote without raising. Requires the
catalog cache to be warm (populated by an earlier real load); marked xfail-ish
by skipping if the catalog can't be loaded offline.
"""

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest

from src.ingest import catalog


def _catalog_available_offline() -> bool:
    """True if every group is cached fresh, so the app needs no network."""
    return all(catalog._read_cache(g) is not None for g in catalog.GROUPS)


@pytest.mark.skipif(
    not _catalog_available_offline(),
    reason="catalog cache cold; run load_catalog() once to populate it",
)
def test_app_renders_a_quote():
    at = AppTest.from_file("src/app/streamlit_app.py", default_timeout=60)
    at.run()

    # No uncaught exception anywhere in the script.
    assert not at.exception

    # The premium card rendered four metrics (premium, rate, prob, P99 loss).
    assert len(at.metric) == 4

    # The premium metric shows a dollar amount.
    premium_metric = at.metric[0]
    assert premium_metric.label == "Annual premium"
    assert premium_metric.value.startswith("$")


@pytest.mark.skipif(
    not _catalog_available_offline(),
    reason="catalog cache cold; run load_catalog() once to populate it",
)
def test_app_quote_changes_with_altitude():
    """Moving the altitude slider to a near-empty shell lowers the premium."""
    at = AppTest.from_file("src/app/streamlit_app.py", default_timeout=60)
    at.run()
    busy_premium = at.metric[0].value

    # 1900 km is well above the crowded shells — should be far cheaper.
    at.slider[0].set_value(1900).run()
    quiet_premium = at.metric[0].value

    to_num = lambda s: float(s.replace("$", "").replace(",", ""))
    assert to_num(quiet_premium) < to_num(busy_premium)
