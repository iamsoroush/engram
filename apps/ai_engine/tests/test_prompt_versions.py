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
    # v4 (G4): doctor sign-off name moved OUT of the static instruction block into the variable tail
    # (rules block now byte-stable across doctors), + a follow-up thread-history tail segment + an
    # aftercare reference. The exemplar branch is pinned separately in
    # ``test_qa_draft_exemplar_branch_is_pinned``.
    qa_draft: ("2026-07-09.qa_draft.v4", "95e47ab7cb58df0e51cb2b07f8a370c24fdad735659e1a8a45ffdb6866b270d3"),
    # v3 (G4): drop the doctor-wide `priorAnswers` block (noise + cross-patient leak surface on a
    # voice-edit that revises a GIVEN draft) and reword the guard accordingly.
    qa_revise: ("2026-07-09.qa_revise.v3", "1b0b1a270113b2fc88c731adb0e36393d9729cbb1d31a0ac04d38139ba2b210d"),
    safety_reconcile: ("2026-07-04.safety_reconcile.v1", "0d2383985d8fb5d814175f4dc246d5ce9c6a9686904d275b0808154f7820e974"),
    # v4 (G3): explicit stable-prefix context layout — stable clinic/patient blocks, then captures as
    # one flat list, then the per-run volatile blocks LAST (sort_keys=False) — so run N+1 byte-extends
    # run N for the gateway prefix cache. Serialization order changed → hash changed.
    synthesis: ("2026-07-09.synthesis.v4", "dc01ced184e3465de7a215dede0dbef39d15d63469368e866d13a2476138e30b"),
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
        self.assertEqual(actual, "11e2f88528af6ed3570c312e40493981badd113c48b7c1651aa06708362b8daa")


if __name__ == "__main__":
    unittest.main()
