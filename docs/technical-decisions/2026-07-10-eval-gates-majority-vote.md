# Eval gates vote majority-of-N on failure (2026-07-10)

Single-sample LLM variance was indistinguishable from prompt regressions: a ~80-call `run_all` run
almost always had one different case fail per run. The gates now support `EVAL_VOTES=N`
(`gate_votes` in `apps/ai_engine/eval/_common.py`): a case that fails is re-sampled and passes on a
majority of attempts; a first-attempt pass costs one call; the LLM-judge tier is never re-voted.
`EVAL_VOTES=3` is the standard for CLAUDE.md §4 eval-gate runs — a red case under voting is a
majority-confirmed regression worth a prompt fix, not a re-run. Prompt fixes stay on the
whack-a-mole discipline: every wording change bumps `PROMPT_VERSION` + its pinned hash
(`tests/test_prompt_versions.py`) in the same commit, then re-verifies the affected modules under
`EVAL_VOTES=3`.
