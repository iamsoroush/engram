import unittest
import uuid
from types import SimpleNamespace

from app.models import CaptureType
from app.services import therapy_reporting as tr


def _note(text, cid=None):
    return SimpleNamespace(
        id=cid or uuid.uuid4(),
        capture_type=CaptureType.note,
        capture_metadata={"decorated_text": {"text": text}},
        captured_at=None,
        created_at=None,
    )


def _audio(text, cid=None):
    return SimpleNamespace(
        id=cid or uuid.uuid4(),
        capture_type=CaptureType.audio,
        capture_metadata={"transcript": {"text": text}},
        captured_at=None,
        created_at=None,
    )


def _session(metadata=None, title="Session 1", patient_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        patient_id=patient_id,
        title=title,
        report_template_key=None,
        extracted_metadata=metadata or {},
    )


class FormatTests(unittest.TestCase):
    def test_normalize_defaults_to_dap(self):
        self.assertEqual(tr.normalize_therapy_format(None), "dap")
        self.assertEqual(tr.normalize_therapy_format("nope"), "dap")
        self.assertEqual(tr.normalize_therapy_format("SOAP"), "soap")

    def test_format_from_session_reads_input_scalar(self):
        self.assertEqual(tr.therapy_format_from_session(_session({"therapy_format": "birp"})), "birp")
        self.assertEqual(tr.therapy_format_from_session(_session({})), "dap")


class SentenceRoutingTests(unittest.TestCase):
    def test_dap_sections_and_plan_routing(self):
        captures = [_note("Client reported anxiety. Plan to practice assertiveness before next session.")]
        model = tr.build_therapy_report_model(_session(), captures, fmt="dap")
        section_ids = [s["id"] for s in model["sections"]]
        self.assertEqual(section_ids, ["data", "assessment", "plan"])
        plan = next(s for s in model["sections"] if s["id"] == "plan")
        self.assertIn("assertiveness", plan["blocks"][0]["text"])
        data = next(s for s in model["sections"] if s["id"] == "data")
        self.assertIn("anxiety", data["blocks"][0]["text"])

    def test_plan_routing_survives_decoration_rewording(self):
        # Note decoration commonly rewords "plan to X" → "The plan is to X" — still route to Plan.
        captures = [_note("Client described work burnout. The plan is to set boundaries next week.")]
        model = tr.build_therapy_report_model(_session(), captures, fmt="dap")
        plan = next(s for s in model["sections"] if s["id"] == "plan")
        self.assertIn("boundaries", plan["blocks"][0]["text"])

    def test_soap_objective_routing(self):
        captures = [_note("She appeared tearful when discussing her father. Still anxious about work.")]
        model = tr.build_therapy_report_model(_session(), captures, fmt="soap")
        self.assertEqual([s["id"] for s in model["sections"]], ["subjective", "objective", "assessment", "plan"])
        objective = next(s for s in model["sections"] if s["id"] == "objective")
        self.assertIn("tearful", objective["blocks"][0]["text"])

    def test_birp_sections(self):
        captures = [_note("We explored coping strategies. Client engaged well.")]
        model = tr.build_therapy_report_model(_session(), captures, fmt="birp")
        self.assertEqual([s["id"] for s in model["sections"]], ["behavior", "intervention", "response", "plan"])

    def test_format_reprojects_same_content_no_loss(self):
        captures = [_note("Discussed boundaries with mother. Plan to journal this week.")]
        dap = tr.build_therapy_report_model(_session(), captures, fmt="dap")
        soap = tr.build_therapy_report_model(_session(), captures, fmt="soap")
        dap_text = " ".join(b["text"] for s in dap["sections"] for b in s["blocks"])
        soap_text = " ".join(b["text"] for s in soap["sections"] for b in s["blocks"])
        for marker in ("boundaries with mother", "journal this week"):
            self.assertIn(marker, dap_text)
            self.assertIn(marker, soap_text)


class SynthesisTests(unittest.TestCase):
    def test_themes_and_session_so_far(self):
        captures = [_note("Anxiety about work persists. Boundaries with mother improved. Mother called again.")]
        synth = tr.build_therapy_synthesis(_session(), captures, generated_at="t")
        theme_labels = [t["label"] for t in synth["themes"]]
        self.assertIn("anxiety", theme_labels)
        self.assertIn("family", theme_labels)
        self.assertIn("1 note", synth["sessionSoFar"]["line"])
        self.assertTrue(synth["sessionSoFar"]["narrative"])
        self.assertTrue(all(thread["covered"] for thread in synth["sessionSoFar"]["threadCoverage"]))

    def test_note_and_audio_counts(self):
        synth = tr.build_therapy_synthesis(_session(), [_note("a"), _note("b"), _audio("c")], generated_at="t")
        self.assertEqual(synth["noteCount"], 2)
        self.assertEqual(synth["audioCount"], 1)

    def test_risk_suggested_then_clinician_confirmed(self):
        captures = [_note("Client mentioned feeling hopeless about the future at times.")]
        suggested = tr.build_therapy_synthesis(_session(), captures, generated_at="t")
        self.assertTrue(suggested["risk"]["suggested"])
        self.assertFalse(suggested["risk"]["active"])
        self.assertIn("hopeless", suggested["risk"]["cue"].lower())
        # Once the clinician confirms, the suggestion resolves to an active, dated flag.
        confirmed_session = _session({"therapy_risk": {"active": True, "level": "moderate", "confirmedBy": "Dr. Demo", "confirmedAt": "2026-06-13T00:00:00Z"}})
        confirmed = tr.build_therapy_synthesis(confirmed_session, captures, generated_at="t")
        self.assertTrue(confirmed["risk"]["active"])
        self.assertFalse(confirmed["risk"]["suggested"])
        self.assertEqual(confirmed["risk"]["confirmedBy"], "Dr. Demo")

    def test_no_risk_when_no_cue(self):
        synth = tr.build_therapy_synthesis(_session(), [_note("Productive session about work goals.")], generated_at="t")
        self.assertFalse(synth["risk"]["suggested"])
        self.assertFalse(synth["risk"]["active"])


class PrivacyTests(unittest.TestCase):
    def test_report_model_carries_only_shareable_plane(self):
        # The report model (which exports/payloads render) must never carry the private plane.
        session = _session({"therapy_reflections": "Private hypothesis: perfectionism."})
        captures = [_note("Client discussed work stress.")]
        model = tr.build_therapy_report_model(session, captures)
        blob = str(model)
        self.assertNotIn("perfectionism", blob)
        self.assertNotIn("reflections", blob)

    def test_audio_transcript_is_private_only(self):
        captures = [_audio("Sensitive recap the client should never see verbatim.")]
        synth = tr.build_therapy_synthesis(_session(), captures, generated_at="t")
        self.assertEqual(len(synth["planes"]["private"]["audioTranscripts"]), 1)
        shareable_blob = str(synth["planes"]["shareable"])
        self.assertNotIn("never see verbatim", shareable_blob)

    def test_apply_writes_shareable_report_excluding_reflections(self):
        session = _session({"therapy_reflections": "Private: countertransference noted."})
        session.report_template_key = None
        captures = [_note("Client described boundary win with mother. Plan to continue.")]
        tr.apply_therapy_synthesis(session, captures, db=None, generated_at="2026-06-13T00:00:00Z")
        self.assertIn("therapy", session.extracted_metadata)
        self.assertFalse(session.extracted_metadata["generated_output_stale"])
        self.assertIsInstance(session.report_model, dict)
        # The rendered, releasable report excludes the private reflections.
        self.assertNotIn("countertransference", session.generated_report)
        self.assertIn("boundary win", session.generated_report)
        self.assertTrue(session.generated_summary)


class MetadataMutationTests(unittest.TestCase):
    def test_set_format_release_risk_reflections(self):
        session = _session({})
        tr.set_therapy_format(session, "soap")
        self.assertEqual(session.extracted_metadata["therapy_format"], "soap")
        tr.set_therapy_release(session, released=True, released_at="2026-06-13T00:00:00Z")
        self.assertTrue(session.extracted_metadata["therapy_release"]["released"])
        tr.set_therapy_release(session, released=False, released_at=None)
        self.assertFalse(session.extracted_metadata["therapy_release"]["released"])
        self.assertIsNone(session.extracted_metadata["therapy_release"]["releasedAt"])
        tr.set_therapy_risk(session, active=True, level="high", note="n", confirmed_by="Dr. X", confirmed_at="2026-06-13T00:00:00Z")
        self.assertTrue(session.extracted_metadata["therapy_risk"]["active"])
        self.assertEqual(session.extracted_metadata["therapy_risk"]["level"], "high")
        tr.therapy_reflections_set(session, "  some reflection  ")
        self.assertEqual(session.extracted_metadata["therapy_reflections"], "some reflection")
        tr.therapy_reflections_set(session, "   ")
        self.assertIsNone(session.extracted_metadata["therapy_reflections"])


if __name__ == "__main__":
    unittest.main()
