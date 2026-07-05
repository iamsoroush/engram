"""PROMPT_VERSION hash-pin gate (§3.3).

Each prompt's ``PROMPT_VERSION`` is pinned to a sha256 of its canonically-built text. Editing wording
WITHOUT bumping ``PROMPT_VERSION`` fails here — which is the point: an eval regression must be
attributable to a specific prompt diff, so a silent wording change (same version, different text) is a
bug. When you intentionally change a prompt: bump its ``PROMPT_VERSION`` and update its pinned hash in
the same commit (regenerate with the snippet in the test docstring). Byte-identical to the pre-§3.3
inline builders at introduction (proven separately at the increment).
"""
import hashlib
import unittest

from ai_engine.prompts import (
    caption,
    patient_memory,
    qa_draft,
    qa_revise,
    safety_reconcile,
    synthesis,
    transcription,
)

# A single canonical context exercising every prompt's branches (fa + vertical framing + payloads).
CANONICAL_CONTEXT = {
    "domain": {"label": "aesthetics clinic", "vocabulary": ["filler", "botox"], "captionFindings": ["filler/Botox effect"]},
    "reportLanguage": "fa",
    "preferredLanguage": "fa",
    "patient": {"displayName": "X"},
    "language": "fa",
    "qaDraft": {"patientQuestion": "Q", "doctorName": "Dr", "patientContext": {"a": 1}, "priorAnswers": [{"q": "x"}]},
    "qaRevise": {"patientQuestion": "Q", "currentDraft": "D", "patientContext": {}, "priorAnswers": []},
    "existingFlags": [{"key": "allergy|x", "kind": "allergy", "text": "x"}],
    "newFlags": [{"key": "consent|y", "kind": "consent", "text": "y"}],
}

# module -> (expected PROMPT_VERSION, expected sha256 of build(CANONICAL_CONTEXT))
PINNED = {
    transcription: ("2026-07-05.transcription.v2", "413299ab0b3c6e9388938e1251ad730b9166d1483df27641a899aca2adbce5f5"),
    caption: ("2026-07-04.caption.v1", "b066644f987c727fac3f4d1e430b6856acaa79bbd7db406b763136ef79f1d634"),
    patient_memory: ("2026-07-05.patient_memory.v2", "f425a3fe2c1bb363f5df840866af784e0b40e05ceb253b1a2c8e8237ccb5330a"),
    # v3 adds an UNCONDITIONAL cross-patient never-copy rule (Q-3) that renders on every path — so the
    # no-exemplar hash changed from v2. The exemplar branch is pinned separately in
    # ``test_qa_draft_exemplar_branch_is_pinned``.
    qa_draft: ("2026-07-05.qa_draft.v3", "a698f8009ef0e8e97bcc7b6848a07a79b149c7a0a25073a11e28cc38f248ef0d"),
    # v2 adds the same cross-patient never-copy rule to the voice-edit prompt (Q-3).
    qa_revise: ("2026-07-05.qa_revise.v2", "02a8097f1e7b1384e336c78692790e9ca23b59966cd6bcd1849bbb5c788bb43a"),
    safety_reconcile: ("2026-07-04.safety_reconcile.v1", "0d2383985d8fb5d814175f4dc246d5ce9c6a9686904d275b0808154f7820e974"),
    synthesis: ("2026-07-05.synthesis.v3", "c7fbf63b19deaee4a7fd9d7ab473d74753b5627ece4b2058baffee40e8effaf7"),
}


class PromptVersionPinTests(unittest.TestCase):
    def test_versions_and_hashes_are_pinned(self):
        for module, (expected_version, expected_hash) in PINNED.items():
            with self.subTest(prompt=module.__name__):
                self.assertEqual(module.PROMPT_VERSION, expected_version)
                actual = hashlib.sha256(module.build(CANONICAL_CONTEXT).encode("utf-8")).hexdigest()
                self.assertEqual(
                    actual,
                    expected_hash,
                    f"{module.__name__} prompt text changed without a matching hash update. If the change is "
                    "intentional, bump PROMPT_VERSION and update the pinned hash in the same commit.",
                )

    def test_every_prompt_version_is_distinct(self):
        versions = [module.PROMPT_VERSION for module in PINNED]
        self.assertEqual(len(versions), len(set(versions)))

    def test_qa_draft_exemplar_branch_is_pinned(self):
        # The retrieval-grounding branch (AES-410) isn't reachable through the shared CANONICAL_CONTEXT
        # (adding a qaDraft key would perturb the prompts that serialize the whole context), so pin it
        # directly here. Editing the exemplar wording without bumping PROMPT_VERSION fails here.
        context = {
            "qaDraft": {
                "patientQuestion": "Q", "doctorName": "Dr", "patientContext": {"a": 1}, "priorAnswers": [{"q": "x"}],
                "retrievedExemplars": [{"question": "eq", "answer": "ea", "source": "template", "score": 0.9}],
            }
        }
        actual = hashlib.sha256(qa_draft.build(context).encode("utf-8")).hexdigest()
        self.assertEqual(actual, "4418230045126ee813c5b6a2a61556b995724d04ac652dc3b1e74038d703f3f9")


if __name__ == "__main__":
    unittest.main()
