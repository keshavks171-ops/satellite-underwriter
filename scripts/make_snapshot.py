"""Build the bundled catalog snapshot from the local cache.

Streamlit Community Cloud sometimes can't reach CelesTrak (cloud IP ranges get
rate-limited), so the repo ships a slim snapshot of the catalog as a fallback.
This script regenerates it from a fresh local cache:

    python -c "from src.ingest.catalog import load_catalog; load_catalog()"
    python scripts/make_snapshot.py

The snapshot keeps only the five GP fields the model uses, which shrinks the
active catalog from ~7 MB to under 2 MB.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingest.catalog import CACHE_DIR, GROUPS, SNAPSHOT_DIR

# The only GP fields load_catalog() reads — everything else is dead weight.
KEEP_FIELDS = ["NORAD_CAT_ID", "OBJECT_NAME", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION"]


def main() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for group in GROUPS:
        cache_file = CACHE_DIR / f"{group}.json"
        if not cache_file.exists():
            sys.exit(f"Missing cache for {group!r} — run load_catalog() first.")
        payload = json.loads(cache_file.read_text())
        slim = [{k: obj.get(k) for k in KEEP_FIELDS} for obj in payload["objects"]]
        out = {
            "group": group,
            "fetched_at_unix": payload["fetched_at_unix"],
            "fetched_at_iso": payload.get("fetched_at_iso", ""),
            "objects": slim,
        }
        out_file = SNAPSHOT_DIR / f"{group}.json"
        out_file.write_text(json.dumps(out))
        print(f"{group:24s} {len(slim):>7,} objects  -> {out_file}")


if __name__ == "__main__":
    main()
