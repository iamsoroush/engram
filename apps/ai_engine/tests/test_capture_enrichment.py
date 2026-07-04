import unittest
from io import BytesIO
from unittest.mock import MagicMock, patch

from ai_engine import processing
from ai_engine.processing import (
    caption_image_content,
    caption_output_metadata,
    caption_prompt,
    domain_framing,
    downscale_image_for_caption,
    enrichment_language_directive,
    image_to_data_url,
    is_fixture_capture,
    normalize_caption_pairing,
    normalize_digits_to_latin,
    parse_caption_output,
    parse_structured_transcription_output,
    patient_memory_prompt,
    raw_note_text,
    run_capture_processing_job,
    transcription_prompt,
)

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def _gateway_response(text):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    return response


def _caption_json(caption="A clinical caption.", *, confidence=0.9, ooc=None, pairing=None, uncertainties=None, display=None):
    import json

    payload = {
        "caption": caption,
        "display": display if display is not None else caption,
        "confidence": confidence,
        "outOfContext": ooc,
        "pairing": pairing or {"region": None, "laterality": None, "view": None, "phase": None, "isProductLabel": False},
        "uncertainties": uncertainties or [],
    }
    return json.dumps(payload)


class EnrichmentPromptTests(unittest.TestCase):
    def test_language_directive_auto_preserves_script(self):
        directive = enrichment_language_directive({"preferredLanguage": "auto"})
        self.assertIn("same language and script", directive)
        self.assertIn("never romanize", directive.lower())

    def test_language_directive_specific_names_native_script(self):
        directive = enrichment_language_directive({"preferredLanguage": "fa"})
        self.assertIn("Persian (Farsi)", directive)
        self.assertIn("native script", directive)

    def test_caption_prompt_is_structured_and_vertical_driven(self):
        # The vertical comes from the passed `domain` descriptor — never hardcoded in the worker.
        aesthetics = caption_prompt({"domain": {"label": "aesthetics clinic", "captionFindings": ["filler/Botox effect"]}, "preferredLanguage": "auto"})
        self.assertIn("aesthetics clinic", aesthetics.lower())
        self.assertIn("filler/Botox effect", aesthetics)
        # The structured contract is requested explicitly.
        for key in ("caption", "confidence", "outOfContext", "pairing", "isProductLabel", "uncertainties"):
            self.assertIn(key, aesthetics)
        therapy = caption_prompt({"domain": {"label": "psychotherapy practice"}, "preferredLanguage": "auto"})
        self.assertIn("psychotherapy practice", therapy.lower())
        self.assertNotIn("botox", therapy.lower())

    def test_caption_prompt_is_neutral_describer_not_diagnostician(self):
        # The caption is an objective image→text stand-in, NOT a clinical assessment: it must forbid
        # diagnosing and stating absent/normal findings ("no signs of …").
        prompt = caption_prompt({"domain": {"label": "aesthetics clinic"}, "preferredLanguage": "auto"})
        self.assertIn("not a diagnostician", prompt.lower())
        self.assertIn("do not diagnose", prompt.lower())
        self.assertIn("no signs of", prompt.lower())
        self.assertIn("visibly present", prompt.lower())

    def test_caption_prompt_product_intent_and_latin_digits(self):
        # isProductLabel must key off the PRIMARY intent (not a product merely in the background), and
        # numbers must be requested in Latin digits for cross-caption comparison.
        prompt = caption_prompt({"domain": {"label": "aesthetics clinic"}, "preferredLanguage": "fa"})
        self.assertIn("PRIMARY INTENT", prompt)
        self.assertIn("background", prompt.lower())
        self.assertIn("Latin digits", prompt)

    def test_caption_prompt_neutral_fallback_when_no_domain(self):
        prompt = caption_prompt({"clinic": {"name": "Engram Clinic"}, "preferredLanguage": "auto"})
        self.assertIn("setting is a clinic", prompt.lower())  # neutral default
        self.assertNotIn("aesthetic", prompt.lower())
        self.assertIn("Do NOT invent", prompt)
        self.assertIn("never romanize", prompt.lower())


class VerticalNeutralPromptTests(unittest.TestCase):
    """The worker prompts must be vertical-agnostic — driven by the passed `domain`, neutral otherwise."""

    def test_domain_framing_neutral_fallback(self):
        label, vocab, findings = domain_framing({})
        self.assertEqual(label, "clinic")
        self.assertEqual(vocab, [])
        self.assertEqual(findings, [])
        label, vocab, _ = domain_framing({"domain": {"label": "psychotherapy practice", "vocabulary": ["affect", "boundaries"]}})
        self.assertEqual(label, "psychotherapy practice")
        self.assertEqual(vocab, ["affect", "boundaries"])

    def test_transcription_prompt_is_vertical_driven(self):
        therapy = transcription_prompt({"domain": {"label": "psychotherapy practice", "vocabulary": ["affect", "boundaries", "safety plan"]}})
        self.assertIn("psychotherapy practice", therapy.lower())
        self.assertIn("boundaries", therapy.lower())
        self.assertNotIn("aesthetic", therapy.lower())
        neutral = transcription_prompt({})
        self.assertIn("clinical setting is a clinic", neutral.lower())
        self.assertNotIn("aesthetic", neutral.lower())

    def test_patient_memory_prompt_is_vertical_driven(self):
        therapy = patient_memory_prompt({"domain": {"label": "psychotherapy practice"}, "patient": {}})
        self.assertIn("psychotherapy practice", therapy.lower())
        self.assertNotIn("aesthetic", therapy.lower())
        neutral = patient_memory_prompt({"patient": {}})
        self.assertIn("clinical setting is a clinic", neutral.lower())
        self.assertNotIn("aesthetic", neutral.lower())


class DownscaleTests(unittest.TestCase):
    @unittest.skipIf(Image is None, "Pillow not installed")
    def test_downscale_bounds_longest_edge_and_returns_jpeg(self):
        source = BytesIO()
        Image.new("RGB", (4000, 2000), (123, 50, 200)).save(source, format="PNG")
        data, mime = downscale_image_for_caption(source.getvalue(), "image/png", max_edge=1280)
        self.assertEqual(mime, "image/jpeg")
        with Image.open(BytesIO(data)) as out:
            self.assertEqual(max(out.size), 1280)
            self.assertEqual(out.mode, "RGB")

    @unittest.skipIf(Image is None, "Pillow not installed")
    def test_downscale_leaves_small_image_dimensions(self):
        source = BytesIO()
        Image.new("RGB", (640, 480), (10, 20, 30)).save(source, format="JPEG")
        data, mime = downscale_image_for_caption(source.getvalue(), "image/jpeg", max_edge=1280)
        with Image.open(BytesIO(data)) as out:
            self.assertEqual(out.size, (640, 480))

    def test_downscale_falls_back_on_undecodable_bytes(self):
        data, mime = downscale_image_for_caption(b"not-an-image", "image/jpeg")
        self.assertEqual(data, b"not-an-image")
        self.assertEqual(mime, "image/jpeg")


class CaptionParsingTests(unittest.TestCase):
    def test_parse_structured_caption(self):
        parsed = parse_caption_output(_caption_json("Left cheek asymmetry.", confidence=0.8, pairing={"region": "cheek", "laterality": "Left", "view": "front", "phase": "Before", "isProductLabel": False}))
        self.assertEqual(parsed["caption"], "Left cheek asymmetry.")
        self.assertEqual(parsed["confidence"], 0.8)
        self.assertEqual(parsed["pairing"]["laterality"], "left")
        self.assertEqual(parsed["pairing"]["phase"], "before")
        self.assertIsNone(parsed["outOfContext"])

    def test_parse_caption_plain_text_fallback(self):
        parsed = parse_caption_output("Just a plain caption with no JSON.")
        self.assertEqual(parsed["caption"], "Just a plain caption with no JSON.")
        self.assertIsNone(parsed["confidence"])
        self.assertFalse(parsed["pairing"]["isProductLabel"])

    def test_parse_caption_out_of_context(self):
        parsed = parse_caption_output(_caption_json("A parking receipt.", ooc={"present": True, "reason": "not clinical", "confidence": 0.9}))
        self.assertTrue(parsed["outOfContext"]["present"])
        self.assertEqual(parsed["outOfContext"]["reason"], "not clinical")

    def test_parse_caption_empty_is_none(self):
        self.assertIsNone(parse_caption_output("  "))
        self.assertIsNone(parse_caption_output('{"caption": ""}'))

    def test_normalize_pairing_drops_unknown_enums(self):
        pairing = normalize_caption_pairing({"region": "Forehead", "laterality": "sideways", "phase": "weird", "isProductLabel": True})
        self.assertEqual(pairing["region"], "Forehead")
        self.assertIsNone(pairing["laterality"])  # not a known laterality
        self.assertIsNone(pairing["phase"])
        self.assertTrue(pairing["isProductLabel"])

    def test_quantities_normalized_to_latin_digits(self):
        # Persian/Arabic-Indic digits → Western 0-9 so quantification is comparable across captures.
        self.assertEqual(normalize_digits_to_latin("لات ۰۴۰۲۹، ۲ سی‌سی"), "لات 04029، 2 سی‌سی")
        self.assertEqual(normalize_digits_to_latin("batch ٠٤٠٢٩"), "batch 04029")
        # A Persian caption keeps its words but its numbers come back Latin.
        parsed = parse_caption_output(_caption_json("جعبه ژل، شماره بچ ۰۴۰۲۹"))
        self.assertIn("04029", parsed["caption"])
        self.assertNotIn("۰", parsed["caption"])
        self.assertIn("ژل", parsed["caption"])  # prose words untouched

    def test_display_kept_only_when_same_text_as_caption(self):
        # The Markdown display variant is accepted only when it's the caption text with just **bold**
        # added (digits normalized to match); a display that changed the wording falls back to caption.
        ok = parse_caption_output(_caption_json("Decosalin spray, batch 04029", display="**Decosalin** spray, batch **۰۴۰۲۹**"))
        self.assertEqual(ok["display"], "**Decosalin** spray, batch **04029**")
        self.assertEqual(ok["caption"], "Decosalin spray, batch 04029")  # caption stays clean
        diverged = parse_caption_output(_caption_json("Decosalin spray, batch 04029", display="**A totally different sentence.**"))
        self.assertEqual(diverged["display"], diverged["caption"])  # rejected → falls back to clean caption

    def test_audio_transcript_quantities_normalized_to_latin(self):
        import json

        raw = json.dumps(
            {
                "transcript": "بیمار ۲ سی‌سی ژل دریافت کرد",
                "language": "fa",
                "patient_information": {"national_id": "۱۲۳۴۵۶۷۸۹۰", "phone": "۰۹۱۲۳۴۵۶۷۸۹", "confidence": 0.5},
            }
        )
        out = parse_structured_transcription_output(raw)
        self.assertIn("2 سی‌سی", out["transcript"])  # number Latinized, words kept
        self.assertEqual(out["patient_information"]["national_id"], "1234567890")
        self.assertEqual(out["patient_information"]["phone"], "09123456789")


class EnrichmentHelperTests(unittest.TestCase):
    def test_image_to_data_url_uses_image_mime(self):
        url = image_to_data_url(b"\x89PNG", "image/png")
        self.assertTrue(url.startswith("data:image/png;base64,"))

    def test_image_to_data_url_defaults_non_image_mime_to_jpeg(self):
        url = image_to_data_url(b"x", "application/octet-stream")
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))

    def test_is_fixture_capture_by_filename_and_detail(self):
        self.assertTrue(is_fixture_capture({"metadata": {"original_filename": "photo_01_pre_correction_left_cheek.jpg"}}))
        self.assertTrue(
            is_fixture_capture({"metadata": {"detail": "Patient prefers subtle correction ... send a follow-up photo in 2 weeks if asymmetry persists."}})
        )
        self.assertFalse(is_fixture_capture({"metadata": {"detail": "Botox to forehead, 20 units."}}))

    def test_raw_note_text(self):
        self.assertEqual(raw_note_text({"metadata": {"detail": "  note  "}}), "note")
        self.assertIsNone(raw_note_text({"metadata": {"detail": "   "}}))
        self.assertIsNone(raw_note_text({"metadata": {}}))

    def test_caption_output_metadata_carries_attributes(self):
        job = {"id": "job-1", "jobType": "image_capture_process", "inputArtifactIds": []}
        result = {
            "caption": "Left cheek filler effect.",
            "confidence": 0.4,
            "outOfContext": None,
            "pairing": {"region": "cheek", "laterality": "left", "view": None, "phase": "after", "isProductLabel": False},
            "uncertainties": ["confirm the area"],
        }
        output = caption_output_metadata(job, result)
        self.assertEqual(output["text"], "Left cheek filler effect.")
        self.assertEqual(output["confidence"], 0.4)
        self.assertEqual(output["pairing"]["phase"], "after")
        self.assertEqual(output["uncertainties"], ["confirm the area"])
        self.assertNotIn("intents", output)

    def test_caption_output_metadata_maps_ooc_to_intents(self):
        job = {"id": "job-1", "jobType": "image_capture_process", "inputArtifactIds": []}
        result = {"caption": "Screenshot.", "confidence": 0.9, "outOfContext": {"present": True, "reason": "not clinical", "confidence": 0.9}, "pairing": {}, "uncertainties": []}
        output = caption_output_metadata(job, result)
        self.assertTrue(output["intents"]["out_of_context"]["present"])
        self.assertEqual(output["intents"]["out_of_context"]["reason"], "not clinical")


class EnrichmentGatewayTests(unittest.TestCase):
    @patch("ai_engine.jobs.capture_photo.gateway_client")
    def test_caption_returns_structured_result(self, client_factory):
        client_factory.return_value.chat.completions.create.return_value = _gateway_response(
            _caption_json("Pre-correction image of mild left cheek asymmetry.", confidence=0.85)
        )
        result = caption_image_content(b"img", "image/jpeg", {"preferredLanguage": "auto"})
        self.assertEqual(result["caption"], "Pre-correction image of mild left cheek asymmetry.")
        self.assertEqual(result["confidence"], 0.85)

    @patch("ai_engine.jobs.capture_photo.gateway_client")
    def test_caption_empty_response_is_none(self, client_factory):
        client_factory.return_value.chat.completions.create.return_value = _gateway_response("  ")
        self.assertIsNone(caption_image_content(b"img", "image/jpeg", None))

    @patch("ai_engine.jobs.capture_photo.gateway_client")
    def test_product_label_triggers_high_detail_reread(self, client_factory):
        create = client_factory.return_value.chat.completions.create
        # First (low-detail) pass flags a product label; the second (high-detail) pass reads the lot.
        create.side_effect = [
            _gateway_response(_caption_json("A medication box.", pairing={"isProductLabel": True})),
            _gateway_response(_caption_json("Juvederm Voluma, lot ABC123.", pairing={"isProductLabel": True})),
        ]
        result = caption_image_content(b"img", "image/jpeg", {"preferredLanguage": "auto"})
        self.assertEqual(create.call_count, 2)
        self.assertIn("lot ABC123", result["caption"])
        self.assertTrue(result["pairing"]["isProductLabel"])


class FakeBackendClient:
    """Minimal BackendClient stand-in capturing the completed output."""

    def __init__(self, payload):
        self._payload = payload
        self.completed = None
        self.progressed = []
        self.files = {}

    def start_job(self, job_id, *, celery_task_id, retry_count):
        return self._payload

    def progress_job(self, job_id, *, output_key, output, stage):
        self.progressed.append((output_key, stage))

    def get_file(self, path):
        return self.files.get(path, (b"img-bytes", "image/jpeg"))

    def complete_job(self, job_id, *, output_key, output):
        self.completed = (output_key, output)


class RunCaptureEnrichmentTests(unittest.TestCase):
    def _payload(self, capture_type, *, enrichment=True, metadata=None):
        return {
            "job": {"id": "job-1", "jobType": f"{capture_type}_capture_process", "inputArtifactIds": ["a-1"]},
            "capture": {
                "id": "cap-1",
                "type": capture_type,
                "status": "processing",
                "metadata": metadata or {},
                "sourceArtifactId": "art-1",
            },
            "transcriptionContext": None,
            "enrichmentContext": {"preferredLanguage": "auto"} if enrichment else None,
        }

    @patch("ai_engine.jobs.capture.transcription_is_configured", return_value=True)
    @patch("ai_engine.jobs.capture.caption_image_content", return_value={"caption": "A clinical caption.", "confidence": 0.9, "outOfContext": None, "pairing": {"region": "cheek", "laterality": "left", "view": None, "phase": "before", "isProductLabel": False}, "uncertainties": []})
    def test_pro_photo_is_captioned(self, _caption, _configured):
        fake = FakeBackendClient(self._payload("photo"))
        with patch("ai_engine.jobs.capture.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        self.assertEqual(fake.completed[0], "caption")
        self.assertEqual(fake.completed[1]["text"], "A clinical caption.")
        self.assertEqual(fake.completed[1]["pairing"]["region"], "cheek")

    @patch("ai_engine.jobs.capture.transcription_is_configured", return_value=True)
    def test_note_is_raw_passthrough_no_gateway(self, _configured):
        # Notes never call the gateway: the job completes with the RAW text under `note_text`.
        with patch("ai_engine.jobs.capture.caption_image_content") as caption:
            fake = FakeBackendClient(self._payload("note", metadata={"detail": "raw note text"}))
            with patch("ai_engine.jobs.capture.BackendClient", return_value=fake):
                run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
            caption.assert_not_called()
        self.assertEqual(fake.completed[0], "note_text")
        self.assertEqual(fake.completed[1]["text"], "raw note text")

    @patch("ai_engine.jobs.capture.transcription_is_configured", return_value=True)
    @patch("ai_engine.jobs.capture.caption_image_content", return_value={"caption": "ignored"})
    def test_basic_photo_has_no_caption(self, caption, _configured):
        # No enrichmentContext (Basic tenant) → never calls the gateway and writes NO caption
        # (blank), so the UI offers a manual "Add caption" instead of a placeholder.
        fake = FakeBackendClient(self._payload("photo", enrichment=False))
        with patch("ai_engine.jobs.capture.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        caption.assert_not_called()
        self.assertEqual(fake.completed[0], "caption")
        self.assertEqual(fake.completed[1]["text"], "")

    @patch("ai_engine.jobs.capture.transcription_is_configured", return_value=True)
    @patch("ai_engine.jobs.capture.caption_image_content", return_value=None)
    def test_empty_caption_yields_no_caption(self, _caption, _configured):
        # An empty gateway response leaves the photo without a caption (manual add), not a placeholder.
        fake = FakeBackendClient(self._payload("photo"))
        with patch("ai_engine.jobs.capture.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        self.assertEqual(fake.completed[0], "caption")
        self.assertEqual(fake.completed[1]["text"], "")

    @patch("ai_engine.jobs.capture.transcription_is_configured", return_value=True)
    @patch("ai_engine.jobs.capture.caption_image_content", return_value={"caption": "ignored"})
    def test_fixture_photo_skips_enrichment(self, caption, _configured):
        payload = self._payload("photo", metadata={"original_filename": "photo_01_pre_correction_left_cheek.jpg"})
        fake = FakeBackendClient(payload)
        with patch("ai_engine.jobs.capture.BackendClient", return_value=fake):
            run_capture_processing_job("job-1", celery_task_id=None, retry_count=0)
        caption.assert_not_called()
        self.assertEqual(
            fake.completed[1]["text"],
            processing.TEST_CAPTURE_TEXT_BY_FILENAME["photo_01_pre_correction_left_cheek.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
