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
    patient_memory: ("2026-07-10.patient_memory.v3", "2e1fa0bf18073f9d911e6b4607857e51bfbc067a9b4a9ff9168192d6d9790c36"),
    # v4 (G4): doctor sign-off name moved OUT of the static instruction block into the variable tail
    # (rules block now byte-stable across doctors), + a follow-up thread-history tail segment + an
    # aftercare reference. The exemplar branch is pinned separately in
    # ``test_qa_draft_exemplar_branch_is_pinned``.
    qa_draft: ("2026-07-10.qa_draft.v7", "2b7a46699f73dcdf872b2a5073e7eb846a5d23fe410daaec513c2c7fd0d442df"),
    # v3 (G4): drop the doctor-wide `priorAnswers` block (noise + cross-patient leak surface on a
    # voice-edit that revises a GIVEN draft) and reword the guard accordingly.
    qa_revise: ("2026-07-09.qa_revise.v3", "1b0b1a270113b2fc88c731adb0e36393d9729cbb1d31a0ac04d38139ba2b210d"),
    safety_reconcile: ("2026-07-10.safety_reconcile.v2", "7e62cc375a4747e7ae890d5328a368faac59715ab5ef5671a070686ac7c77167"),
    # v4 (G3): explicit stable-prefix context layout. v5 (G7): treatment `status` classification
    # (performed | planned | uncertain) + the planned_vs_performed uncertainty code. v18 (AES-1801): safety
    # flags gain a normalized short `label` (kind + substance) as the legible primary.
    synthesis: ("2026-07-12.synthesis.v18", "a4a37ea6169423b05cc4c9f087ada89cbb4f9b77cd882087f88c2292baab35b0"),
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
        self.assertEqual(actual, "06a875c9c3facd9c37c45c102002a1dc5b79264c9e133caba92b4f606a62e98c")


if __name__ == "__main__":
    unittest.main()
