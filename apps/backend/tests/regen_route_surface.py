"""Regenerate the route-surface snapshot guarded by ``test_route_surface.py``.

Run from ``apps/backend`` when an endpoint is *intentionally* added, removed, or renamed::

    python -m tests.regen_route_surface

Review the resulting diff to ``tests/route_surface_snapshot.json`` before committing.
"""

import json

from tests.test_route_surface import SNAPSHOT_PATH, current_surface


def main() -> None:
    snapshot = current_surface()
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(
        f"wrote {SNAPSHOT_PATH} — "
        f"{len(snapshot['routes'])} routes, {len(snapshot['openapi_paths'])} openapi paths"
    )


if __name__ == "__main__":
    main()
