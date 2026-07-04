"""Unit tests for the Q&A knowledge library retrieval + provenance (AES-410).

Pure-Python: the ranking helpers, orthography-folding, provenance selection, tag cleaning, and the
retrieval-grounded deterministic fallback are all DB-free. The SQL tenant-scoping + pgvector storage
are exercised end-to-end by the e2e-stack spec (``p0-12-qa-library-exemplar``); here we prove the math
and the language/eligibility behaviour deterministically.
"""
import unittest

from app.services.qa import _qa_draft_fallback
from app.services.qa_knowledge import library, normalize, retrieval


class NormalizeTests(unittest.TestCase):
    def test_canonicalize_folds_digits_and_persian_forms_and_zwnj(self):
        # Arabic ي/ك → Persian ی/ک, Persian digits → Latin, ZWNJ stripped, lowercased.
        self.assertEqual(normalize.canonicalize("سي‌سي ۲۰"), "سیسی 20")
        self.assertEqual(normalize.canonicalize("Botox 20U"), "botox 20u")

    def test_tokens_drops_stopwords(self):
        toks = normalize.token_set("Is the swelling normal after my filler?")
        self.assertIn("swelling", toks)
        self.assertIn("filler", toks)
        self.assertNotIn("the", toks)
        self.assertNotIn("is", toks)

    def test_detect_language(self):
        self.assertEqual(normalize.detect_language("بعد از فیلر لبم ورم داره"), "fa")
        self.assertEqual(normalize.detect_language("Is the swelling normal?"), "en")
        self.assertEqual(normalize.detect_language("20 !!"), "und")

    def test_build_search_text_combines_and_folds(self):
        text = normalize.build_search_text(question="ورم بعد از فیلر؟", answer="طبیعی است، نگران نباشید")
        self.assertIn("ورم", text)
        self.assertIn("طبیعی", text)


class LexicalScoreTests(unittest.TestCase):
    def test_identical_sets_score_one(self):
        s = {"a", "b", "c"}
        self.assertAlmostEqual(retrieval.lexical_score(s, s), 1.0)

    def test_no_overlap_is_zero(self):
        self.assertEqual(retrieval.lexical_score({"a"}, {"b"}), 0.0)

    def test_empty_is_zero(self):
        self.assertEqual(retrieval.lexical_score(set(), {"a"}), 0.0)

    def test_partial_overlap_between_zero_and_one(self):
        score = retrieval.lexical_score({"a", "b"}, {"a", "c", "d"})
        self.assertTrue(0.0 < score < 1.0)


class CosineTests(unittest.TestCase):
    def test_parallel_vectors(self):
        self.assertAlmostEqual(retrieval.cosine([1.0, 0.0], [2.0, 0.0]), 1.0)

    def test_orthogonal_vectors(self):
        self.assertAlmostEqual(retrieval.cosine([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_missing_or_mismatched_is_zero(self):
        self.assertEqual(retrieval.cosine(None, [1.0]), 0.0)
        self.assertEqual(retrieval.cosine([1.0, 2.0], [1.0]), 0.0)
        self.assertEqual(retrieval.cosine([0.0, 0.0], [1.0, 1.0]), 0.0)


class FuseTests(unittest.TestCase):
    def test_lexical_only_when_no_embedding(self):
        self.assertEqual(retrieval.fuse(lex=0.6, emb=None, same_language=False), 0.6)

    def test_blends_lexical_and_embedding(self):
        self.assertAlmostEqual(retrieval.fuse(lex=0.4, emb=0.8, same_language=False), 0.5 * 0.4 + 0.5 * 0.8)

    def test_same_language_bonus(self):
        base = retrieval.fuse(lex=0.4, emb=None, same_language=False)
        boosted = retrieval.fuse(lex=0.4, emb=None, same_language=True)
        self.assertGreater(boosted, base)


def _candidate(cid, *, question, answer, kind="template", title=None, language="fa", embedding=None):
    return {
        "id": cid,
        "kind": kind,
        "title": title,
        "question": question,
        "answer": answer,
        "language": language,
        "search_text": normalize.build_search_text(question=question, answer=answer),
        "embedding": embedding,
    }


class RankCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.swelling = _candidate(
            "sw", kind="template", title="Filler swelling",
            question="آیا ورم بعد از فیلر طبیعی است؟",
            answer="ورم خفیف بعد از فیلر طبیعی است و معمولاً چند روزه فروکش می‌کند.",
        )
        self.bruise = _candidate(
            "br", kind="template", title="Botox bruising",
            question="کبودی بعد از بوتاکس طبیعی است؟",
            answer="کبودی کوچک بعد از بوتاکس شایع است.",
        )
        self.sun = _candidate(
            "su", kind="sent_reply",
            question="بعد از فیلر آفتاب بروم؟",
            answer="تا یک هفته از آفتاب مستقیم پرهیز کنید.",
        )

    def test_retrieval_relevance_paraphrase_finds_the_right_template(self):
        # A PARAPHRASED question ("لبم بعد از فیلر ورم کرده") must rank the swelling template top,
        # lexical-only (gateway-less) — the backend counterpart of the eval's retrieval-relevance case.
        ranked = retrieval.rank_candidates(
            [self.bruise, self.swelling, self.sun],
            query="لبم بعد از فیلر ورم کرده، طبیعیه؟",
            query_language="fa",
            query_embedding=None,
            top_k=3,
        )
        self.assertTrue(ranked)
        self.assertEqual(ranked[0]["exemplarId"], "sw")

    def test_off_topic_query_returns_nothing_eligible(self):
        # No lexical overlap and no embeddings → return empty, not an irrelevant "based on".
        ranked = retrieval.rank_candidates(
            [self.swelling, self.bruise],
            query="پارکینگ کجاست؟",
            query_language="fa",
            query_embedding=None,
            top_k=3,
        )
        self.assertEqual(ranked, [])

    def test_top_k_caps_results(self):
        ranked = retrieval.rank_candidates(
            [self.swelling, self.bruise, self.sun],
            query="بعد از فیلر ورم و آفتاب و کبودی",
            query_language="fa",
            query_embedding=None,
            top_k=1,
        )
        self.assertEqual(len(ranked), 1)

    def test_embedding_signal_breaks_a_lexical_tie(self):
        # Two lexically-equal candidates; an embedding closer to the query wins.
        a = _candidate("a", question="سوال", answer="جواب الف", embedding=[1.0, 0.0])
        b = _candidate("b", question="سوال", answer="جواب ب", embedding=[0.0, 1.0])
        ranked = retrieval.rank_candidates(
            [a, b], query="سوال", query_language="fa", query_embedding=[0.9, 0.1], top_k=2
        )
        self.assertEqual(ranked[0]["exemplarId"], "a")

    def test_deterministic_order_is_stable(self):
        args = dict(query="بعد از فیلر ورم", query_language="fa", query_embedding=None, top_k=3)
        first = retrieval.rank_candidates([self.swelling, self.bruise, self.sun], **args)
        second = retrieval.rank_candidates([self.sun, self.bruise, self.swelling], **args)
        self.assertEqual([r["exemplarId"] for r in first], [r["exemplarId"] for r in second])


class ProvenanceTests(unittest.TestCase):
    def test_none_when_empty(self):
        self.assertIsNone(library.provenance_from_exemplars([]))

    def test_template_carries_its_title_as_label(self):
        prov = library.provenance_from_exemplars(
            [{"kind": "template", "exemplarId": "t1", "title": "Filler swelling", "answer": "…"}]
        )
        self.assertEqual(prov, {"kind": "template", "exemplarId": "t1", "label": "Filler swelling"})

    def test_sent_reply_has_no_label(self):
        prov = library.provenance_from_exemplars(
            [{"kind": "sent_reply", "exemplarId": "r1", "title": None, "answer": "…"}]
        )
        self.assertEqual(prov, {"kind": "sent_reply", "exemplarId": "r1", "label": None})


class TagCleaningTests(unittest.TestCase):
    def test_trims_dedupes_and_bounds(self):
        cleaned = library._clean_tags(["  filler ", "filler", "botox", "", "  "])
        self.assertEqual(cleaned, ["filler", "botox"])

    def test_none_is_empty(self):
        self.assertEqual(library._clean_tags(None), [])


class GroundedFallbackTests(unittest.TestCase):
    def test_fallback_uses_the_top_exemplar_guidance(self):
        # Gateway-less, the deterministic fallback must ground in the clinic's exemplar answer so the
        # draft is genuinely "based on" it (the gateway-less e2e path).
        draft = _qa_draft_fallback(
            question="ورم بعد از فیلر؟",
            doctor_name="دکتر دمو",
            prior_answers=[],
            patient_context={"displayName": "سارا"},
            top_exemplar={"answer": "ورم خفیف بعد از فیلر طبیعی است.", "kind": "template", "title": "Filler swelling"},
        )
        self.assertIn("ورم خفیف بعد از فیلر طبیعی است.", draft)
        self.assertIn("دکتر دمو", draft)

    def test_fallback_without_exemplar_is_generic_and_safe(self):
        draft = _qa_draft_fallback(
            question="Is swelling normal?",
            doctor_name="Dr. Demo",
            prior_answers=[],
            patient_context={"displayName": "Sara"},
            top_exemplar=None,
        )
        self.assertIn("Dr. Demo", draft)
        self.assertIn("call the clinic", draft.lower())


if __name__ == "__main__":
    unittest.main()
