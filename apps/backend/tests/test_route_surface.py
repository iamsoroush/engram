"""Route-surface invariance guard.

The rest of the backend test suite imports services directly and never constructs the FastAPI
app, so it cannot catch a route that failed to wire up (a mis-moved decorator, a dropped
``include_router``, a changed path/tag). This test closes that gap: it reconstructs the mounted
route surface and the OpenAPI paths from ``app.main`` and asserts they are byte-identical to a
checked-in snapshot (``tests/route_surface_snapshot.json``).

It exists to make the router-split refactor mechanical rather than scary — any accidental change to
the public route surface fails here. When an endpoint is *intentionally* added/removed/renamed,
regenerate the snapshot with::

    python -m tests.regen_route_surface   # or re-run the generator documented in that module

and review the diff.
"""

import json
import unittest
from pathlib import Path

from app.main import app

SNAPSHOT_PATH = Path(__file__).parent / "route_surface_snapshot.json"


def current_surface() -> dict:
    """Reconstruct the route surface + OpenAPI paths from the live app object.

    Kept in lock-step with the snapshot generator so regeneration and verification agree.
    """
    routes = []
    for route in app.routes:
        methods = sorted(getattr(route, "methods", []) or [])
        include = getattr(route, "include_in_schema", True)
        routes.append({"path": route.path, "methods": methods, "in_schema": bool(include)})
    routes.sort(key=lambda item: (item["path"], ",".join(item["methods"])))

    schema = app.openapi()
    paths: dict = {}
    for path, operations in schema.get("paths", {}).items():
        entry = {}
        for method, operation in operations.items():
            entry[method] = {
                "tags": operation.get("tags", []),
                "operationId": operation.get("operationId"),
            }
        paths[path] = entry

    return {"routes": routes, "openapi_paths": paths}


class RouteSurfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = json.loads(SNAPSHOT_PATH.read_text())
        self.actual = current_surface()

    def test_mounted_routes_match_snapshot(self) -> None:
        """The (path, methods, include_in_schema) set of all mounted routes is unchanged."""
        expected = {(r["path"], tuple(r["methods"]), r["in_schema"]) for r in self.snapshot["routes"]}
        actual = {(r["path"], tuple(r["methods"]), r["in_schema"]) for r in self.actual["routes"]}
        self.assertEqual(actual - expected, set(), "unexpected new/changed routes")
        self.assertEqual(expected - actual, set(), "missing routes (dropped or moved incorrectly)")

    def test_openapi_paths_match_snapshot(self) -> None:
        """OpenAPI paths, and per-operation tags + operationIds, are unchanged."""
        self.assertEqual(self.actual["openapi_paths"], self.snapshot["openapi_paths"])


if __name__ == "__main__":
    unittest.main()
