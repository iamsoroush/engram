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


class OwnerReproGroundingTests(unittest.TestCase):
    """AES-1802 acceptance: a topic-label title must ground a paraphrased question (the owner's repro).

    A template saved with title «ورزش بعد از بوتاکس» + answer «تا ۲۴ ساعت» and an EMPTY question must
    ground «کی میتونم ورزش کنم؟» — the draft contains «۲۴» with a template provenance. Pre-AES-1802 the
    title was dropped from ``search_text`` so «ورزش» never matched and the draft was ungrounded.
    """

    def _exemplar(self):
        # As the row is stored: search_text now folds the title, so the topic word «ورزش» is indexed.
        search_text = normalize.build_search_text(title="ورزش بعد از بوتاکس", question=None, answer="تا ۲۴ ساعت")
        return {
            "id": "ex-1",
            "kind": "template",
            "title": "ورزش بعد از بوتاکس",
            "question": None,
            "answer": "تا ۲۴ ساعت",
            "language": "fa",
            "search_text": search_text,
            "embedding": None,
        }

    def test_topic_title_grounds_paraphrased_question(self):
        ranked = retrieval.rank_candidates(
            [self._exemplar()],
            query="کی میتونم ورزش کنم؟",
            query_language="fa",
            query_embedding=None,
            top_k=3,
        )
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["kind"], "template")

    def test_grounded_draft_contains_the_answer_and_a_template_provenance(self):
        ranked = retrieval.rank_candidates(
            [self._exemplar()], query="کی میتونم ورزش کنم؟", query_language="fa", query_embedding=None, top_k=3
        )
        draft = _qa_draft_fallback(
            question="کی میتونم ورزش کنم؟",
            doctor_name="دکتر دمو",
            prior_answers=[],
            patient_context={"displayName": "سارا"},
            top_exemplar=ranked[0],
        )
        self.assertIn("۲۴", draft)  # grounded in the clinic's own answer «تا ۲۴ ساعت»
        prov = library.build_draft_provenance(exemplars=ranked, patient_context={}, thread_history=[])
        self.assertTrue(prov["grounded"])
        self.assertEqual(prov["kind"], "template")
        self.assertEqual(prov["sources"][0]["type"], "template")

    def test_title_dropped_would_not_ground_regression_guard(self):
        # Prove the fix is the title: with the OLD answer-only search_text, «ورزش» has no match.
        old = {**self._exemplar(), "search_text": normalize.canonicalize("تا ۲۴ ساعت")}
        ranked = retrieval.rank_candidates(
            [old], query="کی میتونم ورزش کنم؟", query_language="fa", query_embedding=None, top_k=3
        )
        self.assertEqual(ranked, [])


class BuildDraftProvenanceTests(unittest.TestCase):
    """AES-1803: the structured «بر اساس» provenance object built from what the payload carried."""

    def test_ungrounded_is_the_general_knowledge_state(self):
        prov = library.build_draft_provenance(exemplars=[], patient_context={}, thread_history=[])
        self.assertFalse(prov["grounded"])
        self.assertEqual(prov["sources"], [])
        self.assertNotIn("kind", prov)  # no strong "based on" attribution

    def test_all_source_kinds_are_captured(self):
        exemplars = [{"exemplarId": "ex-1", "kind": "template", "title": "Botox aftercare"}]
        prov = library.build_draft_provenance(
            exemplars=exemplars,
            patient_context={"recentAftercare": "avoid heat 24h", "recentVisitSummaries": ["botox visit"]},
            thread_history=[{"question": "q", "answer": "a"}],
        )
        types = [s["type"] for s in prov["sources"]]
        self.assertEqual(types, ["template", "patient_aftercare", "patient_summary", "conversation"])
        self.assertTrue(prov["grounded"])
        self.assertEqual(prov["kind"], "template")
        self.assertEqual(prov["exemplarId"], "ex-1")
        self.assertEqual(prov["label"], "Botox aftercare")

    def test_sent_reply_top_has_no_label_and_patient_only_still_grounds(self):
        prov = library.build_draft_provenance(
            exemplars=[{"exemplarId": "ex-2", "kind": "sent_reply", "title": None}],
            patient_context={"recentAftercare": "  "},  # blank → not a source
            thread_history=[],
        )
        self.assertEqual(prov["sources"], [{"type": "sent_reply", "exemplarId": "ex-2"}])
        self.assertEqual(prov["kind"], "sent_reply")
        self.assertIsNone(prov["label"])

    def test_patient_context_alone_grounds_without_an_exemplar(self):
        prov = library.build_draft_provenance(
            exemplars=[], patient_context={"memorySummary": "long-term memory"}, thread_history=[]
        )
        self.assertTrue(prov["grounded"])
        self.assertEqual([s["type"] for s in prov["sources"]], ["patient_summary"])
        self.assertNotIn("kind", prov)


class LooksLikeQuestionTests(unittest.TestCase):
    """AES-1802: the migration/guard heuristic that repairs a question-shaped title with an empty question."""

    def test_question_shaped_titles(self):
        self.assertTrue(normalize.looks_like_question("کی میتونم ورزش کنم؟"))
        self.assertTrue(normalize.looks_like_question("Is filler safe?"))
        self.assertTrue(normalize.looks_like_question("چطور از محل تزریق مراقبت کنم"))

    def test_topic_labels_are_not_questions(self):
        # The owner's real title is a topic label, NOT a question — it must NOT be migrated into question.
        self.assertFalse(normalize.looks_like_question("ورزش بعد از بوتاکس"))
        self.assertFalse(normalize.looks_like_question("botox aftercare"))
        self.assertFalse(normalize.looks_like_question(""))
        self.assertFalse(normalize.looks_like_question(None))


if __name__ == "__main__":
    unittest.main()
