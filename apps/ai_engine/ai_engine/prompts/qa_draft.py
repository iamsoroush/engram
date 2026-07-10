"""Q&A reply-draft prompt (AES-402/410): a grounded, clinically-cautious reply the doctor approves.

v2 adds retrieval grounding: the backend attaches ``retrievedExemplars`` — the clinic's own approved
answers to similar questions (curated templates + auto-indexed sent replies). The exemplars set tone
and the GENERIC guidance; the patient's own context always wins on any patient-specific fact, and the
safety guardrails (escalation, never-contradict-the-aftercare) keep precedence over any exemplar.
"""
from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "2026-07-10.qa_draft.v7"


def build(payload: dict[str, Any]) -> str:
    """Build the prompt for a post-session patient Q&A reply draft (AES-402/410)."""
    qa = payload.get("qaDraft") if isinstance(payload.get("qaDraft"), dict) else {}
    exemplars = qa.get("retrievedExemplars") if isinstance(qa.get("retrievedExemplars"), list) else []
    thread_history = qa.get("threadHistory") if isinstance(qa.get("threadHistory"), list) else []
    sections = [
        "You are Engram, drafting a reply on behalf of an aesthetics clinic doctor to a patient's "
        "between-visits question. The doctor will review and edit before sending.",
        # (G4) This instruction block is STATIC across doctors + patients — the doctor's sign-off name is
        # in the variable tail (see the final "Sign off as:" line), NOT interpolated here, so the rules
        # block stays byte-identical and can share a prompt prefix across drafts.
        (
            "Write a warm, concise reply (2-4 sentences) in the patient's voice-appropriate register. "
            "Ground it in the doctor's PRIOR ANSWERS and THIS PATIENT'S CONTEXT below; match the "
            "doctor's tone. Do NOT invent clinical facts, doses, products, or diagnoses not present "
            "in the context. Reassure when appropriate, and reference — never contradict — the aftercare "
            "THIS patient was given (it is in this patient's context under `recentAftercare` when "
            "available). If the question is a follow-up, use this thread's earlier exchange for context. "
            "Tell the patient to contact the clinic if symptoms worsen or they are worried. Sign off with "
            "the doctor's name given at the END of this prompt. Return ONLY the plain-text reply."
        ),
        # Unconditional cross-patient guard (Q-3): the doctor's PRIOR ANSWERS come from OTHER patients
        # (they teach the doctor's VOICE, not facts), as do retrieved exemplars. This rule must render
        # for EVERY draft — including a new clinic with zero exemplars — not only inside the exemplars
        # block, or a dose/name from another patient's reply leaks into THIS one.
        (
            "CRITICAL cross-patient rule: the doctor's PRIOR ANSWERS and any retrieved exemplars are "
            "OTHER patients' conversations. NEVER copy a specific dose, product, brand, lot/batch "
            "number, appointment date, or a person's NAME from them into this reply — those facts "
            "belong to someone else. Address only THIS patient; use only THIS PATIENT'S CONTEXT for any "
            "patient-specific fact. If a specific number or product is not in this patient's own context "
            "or question, give generic guidance and tell them to contact the clinic to confirm specifics. "
            "Generic guidance means QUALITATIVE phrasing: do NOT state numeric durations, ranges, or "
            "doses from general knowledge either (no \"24-48 hours\", no \"18-24 months\", no «۲۴ تا "
            "۴۸ ساعت») — a patient reads any number in a clinic message as THEIR clinical instruction. "
            "Say «طی چند روز آینده» / \"over the next few days\" instead. The numbers allowed in a reply "
            "are ones present in: this patient's context, their question, this thread, or a retrieved "
            "clinic TEMPLATE exemplar (source='template' — curated clinic guidance you SHOULD adopt, "
            "numbers included). Numbers from another patient's sent reply or from general knowledge stay "
            "out. When the patient names a product or brand in their question (e.g. Voluma), refer to it "
            "VERBATIM in the reply — naming what they asked about is grounding, not invention."
        ),
    ]
    if exemplars:
        sections.append(
            "How THIS CLINIC answers similar questions (retrieved exemplars — approved templates and "
            "the clinic's own prior replies). Use them for TONE and for the GENERIC guidance, so the "
            "draft sounds like this clinic. Grounding rules, in strict priority:\n"
            "1. THIS PATIENT'S CONTEXT always wins — if it contradicts an exemplar (e.g. a different "
            "aftercare instruction, a different product), follow the patient's context, not the exemplar.\n"
            "2. Exemplar sources differ. source='template' is the clinic's CURATED guidance for exactly "
            "this kind of question: ADOPT its substance — including its numbers and durations (e.g. a "
            "template's «تا ۲۴ ساعت» stays «۲۴ ساعت», do NOT vague it to «چند روز») — unless rule 1 "
            "overrides it. source='sent_reply' is ANOTHER patient's conversation: take the shape and "
            "tone of the answer, NEVER its doses, products, brands, lots, or patient-specific numbers.\n"
            "3. Safety keeps precedence over any exemplar: on a red-flag / emergency question, escalate "
            "the patient to the clinic immediately and do NOT reassure, even if an exemplar reassures; "
            "and never contradict the aftercare THIS patient was given."
        )
        sections.append(
            "Retrieved exemplars:\n"
            + json.dumps(
                [
                    {"question": item.get("question"), "answer": item.get("answer"), "source": item.get("source")}
                    for item in exemplars
                    if isinstance(item, dict)
                ],
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    sections.extend(
        (
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
            f"The doctor's prior answers:\n{json.dumps(qa.get('priorAnswers', []), ensure_ascii=False, sort_keys=True)}",
        )
    )
    if thread_history:
        sections.append(
            "Earlier in THIS conversation with this patient (for follow-up context — this patient's own "
            "prior questions and the clinic's sent replies):\n"
            + json.dumps(
                [
                    {"question": turn.get("question"), "answer": turn.get("answer")}
                    for turn in thread_history
                    if isinstance(turn, dict)
                ],
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    # Identity LAST (the variable tail) so the instruction block above stays byte-stable across doctors.
    sections.append(f"Sign off as: {qa.get('doctorName') or 'the clinic'}")
    return "\n\n".join(sections)
