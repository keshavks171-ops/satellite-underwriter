"""CelesTrak catalog ingest — Phase 1 (not yet implemented).

Responsibilities (see CLAUDE.md):
- Fetch `active` + 4 debris groups from CelesTrak (JSON, no auth).
- Cache every pull to data/cache/ with a timestamp; reuse for 24h.
- Merge, dedupe by NORAD ID.
- Compute mean altitude per object -> clean DataFrame with an `altitude_km` column.

Units note: mean motion `n` in GP data is revs/day; altitude output is km.
"""
