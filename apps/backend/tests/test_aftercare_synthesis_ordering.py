"""G1: the synthesis aftercare-template loader must issue a deterministic ORDER BY.

The templates serialize inside the synthesis context's stable clinic block, so a run-to-run row-order
flip (Postgres returns unordered rows arbitrarily) would move the prompt's byte-prefix cache boundary.
This pins the ORDER BY (created_at, id) on the query and that the function preserves the DB's order.
"""
import unittest
import uuid
from types import SimpleNamespace

from app.models import AftercareTemplate
from app.services.ai_jobs.worker import _aftercare_templates_for_synthesis


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return iter(self._rows)


class _CapturingDb:
    """Fake db that records the statement passed to execute() and returns canned rows."""

    def __init__(self, rows):
        self._rows = rows
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return _Result(self._rows)


def _template(name: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name=name, procedure_type="botox", body="body")


class AftercareSynthesisOrderingTests(unittest.TestCase):
    def test_query_orders_by_created_at_then_id(self):
        db = _CapturingDb([_template("A"), _template("B")])
        _aftercare_templates_for_synthesis(db, uuid.uuid4())
        order_by_sql = " ".join(str(clause) for clause in db.statement._order_by_clauses)
        self.assertIn("aftercare_templates.created_at", order_by_sql)
        self.assertIn("aftercare_templates.id", order_by_sql)

    def test_preserves_db_row_order(self):
        rows = [_template("first"), _template("second"), _template("third")]
        db = _CapturingDb(rows)
        result = _aftercare_templates_for_synthesis(db, uuid.uuid4())
        self.assertEqual([item["name"] for item in result], ["first", "second", "third"])


if __name__ == "__main__":
    unittest.main()
