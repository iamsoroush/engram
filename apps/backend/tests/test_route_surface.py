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


def _route_dependencies(route) -> list[str]:
    """Names of the ``Depends(...)`` callables declared on a route (signature + router-level).

    Captures the auth guards (``staff_required``, ``tenant_admin_required``,
    ``require_ai_engine_token``, …) and infra deps (``get_db``, ``get_object_store``) so a route
    that is moved to a different router with a *changed* dependency — which the path/method/tag
    snapshot cannot see — fails this guard. Direct dependencies only (not the transitive graph),
    which is exactly what a route declares.
    """
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return []
    names = set()
    for dep in getattr(dependant, "dependencies", []):
        call = getattr(dep, "call", None)
        if call is not None:
            names.add(_dependency_signature(call))
    return sorted(names)


def _dependency_signature(call) -> str:
    """A stable, distinctive name for a dependency callable.

    The role guards (``staff_required``, ``tenant_admin_required``, …) are all closures named
    ``dependency`` produced by ``require_roles(*roles)`` — so the bare ``__name__`` cannot tell them
    apart. When a callable is a closure, fold its captured free-variable values into the name so
    swapping one guard for another (same shape, different roles) is caught.
    """
    name = getattr(call, "__name__", repr(call))
    closure = getattr(call, "__closure__", None) or ()
    freevars = getattr(getattr(call, "__code__", None), "co_freevars", ()) or ()
    parts = []
    for var, cell in zip(freevars, closure):
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if isinstance(value, (str, int, bool)):
            parts.append(f"{var}={value}")
        elif isinstance(value, (tuple, list, set, frozenset)) and all(isinstance(x, str) for x in value):
            parts.append(f"{var}={sorted(value)}")
    return f"{name}({','.join(parts)})" if parts else name


def current_surface() -> dict:
    """Reconstruct the route surface + OpenAPI paths from the live app object.

    Kept in lock-step with the snapshot generator so regeneration and verification agree.
    """
    routes = []
    for route in app.routes:
        methods = sorted(getattr(route, "methods", []) or [])
        include = getattr(route, "include_in_schema", True)
        routes.append(
            {
                "path": route.path,
                "methods": methods,
                "in_schema": bool(include),
                "dependencies": _route_dependencies(route),
            }
        )
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
        """The (path, methods, include_in_schema, dependencies) of all mounted routes is unchanged."""

        def key(r: dict) -> tuple:
            return (r["path"], tuple(r["methods"]), r["in_schema"], tuple(r.get("dependencies", [])))

        expected = {key(r) for r in self.snapshot["routes"]}
        actual = {key(r) for r in self.actual["routes"]}
        self.assertEqual(actual - expected, set(), "unexpected new/changed routes (incl. dependency drift)")
        self.assertEqual(expected - actual, set(), "missing routes (dropped or moved with a changed dependency)")

    def test_openapi_paths_match_snapshot(self) -> None:
        """OpenAPI paths, and per-operation tags + operationIds, are unchanged."""
        self.assertEqual(self.actual["openapi_paths"], self.snapshot["openapi_paths"])


if __name__ == "__main__":
    unittest.main()
