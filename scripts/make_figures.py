"""Generate the README chart images from the live model output.

Produces three PNGs in assets/ that mirror the app's three charts:
  - density.png         debris spatial density vs altitude
  - loss_hist.png       Monte Carlo loss distribution with P95/P99
  - premium_curve.png   premium (annual rate) vs altitude

Run:  python scripts/make_figures.py
Requires matplotlib (see requirements-dev.txt). These are committed assets, so
you only re-run this when the model or the catalog snapshot changes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")  # headless: write files, no display
import matplotlib.pyplot as plt

from src.ingest import catalog
from src.model import density
from src.model.pricing import generate_quote

ASSETS = Path(__file__).resolve().parents[1] / "assets"
ASSETS.mkdir(exist_ok=True)

# Reference satellite (matches the methodology sample quote).
ALT, AREA, YEARS, VALUE, SEED = 550.0, 2.0, 5.0, 10_000_000, 42

print("Loading catalog + building density profile…")
df = catalog.load_catalog()
profile = density.build_density_profile(df["altitude_km"])
base = density.density_at_altitude(profile, ALT)
quote = generate_quote(base, AREA, YEARS, VALUE, seed=SEED)

# --- 1. Debris density vs altitude ------------------------------------------
fig, ax = plt.subplots(figsize=(8, 4.2))
ax.semilogy(profile["shell_center_km"], profile["density_per_km3"], color="#1f77b4")
ax.axvline(ALT, color="crimson", linestyle="--", label=f"your satellite ({ALT:.0f} km)")
ax.set_xlabel("altitude (km)")
ax.set_ylabel("objects / km³ (log scale)")
ax.set_title("Debris spatial density vs altitude")
ax.legend()
ax.grid(True, which="both", alpha=0.2)
fig.tight_layout()
fig.savefig(ASSETS / "density.png", dpi=130)
plt.close(fig)

# --- 2. Loss distribution histogram -----------------------------------------
s = quote.simulation
fig, ax = plt.subplots(figsize=(8, 4.2))
ax.hist(s.losses, bins=60, color="#2ca02c", alpha=0.85)
ax.axvline(s.loss_p95, color="orange", linestyle="--", label=f"P95 = ${s.loss_p95:,.0f}")
ax.axvline(s.loss_p99, color="crimson", linestyle=":", label=f"P99 = ${s.loss_p99:,.0f}")
ax.set_xlabel("loss ($)")
ax.set_ylabel(f"trials (of {s.n_trials:,})")
ax.set_title("Monte Carlo loss distribution")
ax.legend()
ax.grid(True, alpha=0.2)
fig.tight_layout()
fig.savefig(ASSETS / "loss_hist.png", dpi=130)
plt.close(fig)

# --- 3. Premium vs altitude curve -------------------------------------------
alts, rates = [], []
for _, shell in profile.iterrows():
    q = generate_quote(shell["density_per_km3"], AREA, YEARS, VALUE, seed=SEED)
    alts.append(shell["shell_center_km"])
    rates.append(q.breakdown.annual_rate * 100)
cheapest_i = min(range(len(rates)), key=lambda i: rates[i])

fig, ax = plt.subplots(figsize=(8, 4.2))
ax.plot(alts, rates, color="#9467bd")
ax.axvline(ALT, color="crimson", linestyle="--", label=f"your altitude ({ALT:.0f} km)")
ax.scatter([alts[cheapest_i]], [rates[cheapest_i]], color="green", s=90, marker="*",
           zorder=5, label=f"cheapest (~{alts[cheapest_i]:.0f} km)")
ax.set_xlabel("altitude (km)")
ax.set_ylabel("annual rate (% of value / year)")
ax.set_title("Premium vs altitude — where is it cheapest to fly?")
ax.legend()
ax.grid(True, alpha=0.2)
fig.tight_layout()
fig.savefig(ASSETS / "premium_curve.png", dpi=130)
plt.close(fig)

print(f"Wrote 3 figures to {ASSETS}/")
print(f"  Sample quote: premium ${quote.breakdown.premium:,.0f}, "
      f"rate {quote.breakdown.annual_rate*100:.3f}%/yr")
