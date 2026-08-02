# Fully agentic repositories — an operating model

> **Fold destination:** the org's engineering handbook (external); this repo's CLAUDE.md team-protocol
> section once the model is adopted here formally. Status: draft for owner review, then presentation.

This proposes an operating model for repositories developed end-to-end by AI coding agents, with
humans as owners and final decision-makers. It is not speculative: every mechanism here is running
in the Engram repository — a production clinical-memory product (live at engram.ir) built by one
person orchestrating agents across ~470 commits, including its backend, frontend, AI pipeline,
eval system, deployment, and documentation. Evidence from that repo is cited throughout (§11).

The proposal answers three problems any team hits when agents write most of the code:

1. **Statelessness** — agents forget everything between sessions; how does each one get exactly the
   context its task needs?
2. **Quality & improvement** — how do agents work like real engineers (and improve), instead of
   producing plausible code that slowly rots the system?
3. **Human primacy** — how does the developer stay the final decision-maker *with real context in
   their head* — and visibly accountable for the result — instead of degenerating into a "yes"
   button?

---

## 1. The core principle

**Human judgment is the scarce resource. The entire harness exists to spend it only where machines
can't substitute.**

The two classic failure modes are both misallocations of that resource:

- *Rubber-stamping* happens when humans are asked to do machine work — reading large diffs for
  mechanical correctness, checking link integrity, re-running regressions by hand. Attention
  exhausts, and approval becomes a reflex.
- *Detachment* happens when the work that **builds** human context — deciding what "done" means,
  owning the ground truth, touching the product — is handed to agents along with the typing.

So the design rule is: **automate verification downward, push authorship upward.**

- **Humans author ground truth**: acceptance criteria, eval golden sets, QA scripts, product
  decisions. These are never delegated. Authorship is what keeps the human's mental model current —
  approval alone does not.
- **Every mechanizable MUST becomes a check.** Instruction files are where rules go to be
  forgotten; CI is where they go to be enforced. The instruction file (CLAUDE.md) is the *residue*
  that cannot be mechanized. Evidence: in Engram, a rule "don't cite deleted docs" existed
  implicitly for weeks and was violated 12 times across the codebase; the day it became a CI check
  it caught all 12 on its first run (§11.1).
- **Agents do everything in between** — planning drafts, implementation, first-line review,
  documentation drafts — always producing artifacts a human can gate.

Two corollaries worth stating:

- **Push-based context beats pull-based context.** An agent *asked* to remember a rule sometimes
  won't; a failing check that names the rule at the moment of violation always fires. Design the
  harness so diligence is required as rarely as possible.
- **Control means authorship and execution, not approval.** The developer's control over the
  process is not a stack of sign-off buttons — extra approvals are how rubber-stamping starts. It
  is a **signature chain**: every phase transition in the delivery loop (§4) is a named decision
  the developer carries via an artifact they either authored or personally executed. Responsibility
  follows the chain — at no point can the developer say "the agent did it."

## 2. The context system — answering statelessness

**Artifact-continuity, not session-continuity.** No role may depend on chat history. Every agent
must be resumable from durable artifacts: the instruction file, the docs, the epic brief, the PR.
If knowledge exists only inside one session (or one person's private assistant memory), the system
has a leak — see §11.3 for a real one.

Two first-layer contexts load into every agent automatically:

- **CLAUDE.md** (symlinked to AGENTS.md so all agent CLIs share one source) — not an encyclopedia
  but a **router**: per-task-type reading lists ("frontend task → read these four files"), plus a
  small every-task set forming the shared mental model. In Engram that set is three short files:
  the product definition, the non-negotiable design principles, and the decision index (below).
  An agent reads ~200 lines and knows what it's building, what it must not violate, and which
  decisions bind it — then pulls deeper docs only as its task requires.
- **Skills** — validated, reusable *procedures* (how to run the e2e suites correctly, how to debug
  the dev stack), loaded by relevance. Skills raise the floor: they let weaker/cheaper models
  deliver consistent quality, and they encode dead ends so no agent repeats them.

Behind the router, the documentation obeys strict layer rules:

- **Two doc classes, physically separated.** Everything under `docs/` is **system-state**: present
  tense, always matching the code. Process material (epics, plans, explorations) lives in a
  separate root-level workspace (`work-docs/`) with a lifecycle: *create → build → fold the durable
  essence into system-state → delete*. System-state docs may never link into the process workspace
  — CI enforces the isolation, which is the tripwire forcing the fold step before deletion. This
  answers "agents write TODOs into the docs": process content has a home, and the boundary is
  checked, not hoped for.
- **Every fact has exactly one home**; other docs link to it. Volatile enumerations (feature lists,
  job types, env vars) point at the code that defines them — hand-maintained copies are how docs
  rot. Docs hold *invariants and intent*; code holds *facts*.
- **A decision log, one dated file per decision** (`docs/technical-decisions/`), with a
  hooked index README on the every-task reading list: one line per decision carrying the binding
  constraint itself, so any agent can scan 30 decisions and open only the two its task touches.
  Reversals never overwrite — the new decision names what it supersedes and the old file gets a
  superseding note. Per-decision files also mean concurrent epics never merge-conflict on the log.
- **Curated indexes are allowed exactly when a check keeps them complete.** The index above is
  hand-maintained *and* CI verifies it lists every decision file. "No hand-maintained lists" was
  never the real rule; "no *unchecked* hand-maintained lists" is.
- **Doc-integrity CI** (one small script): every relative link resolves; no system-state doc links
  into the process workspace; any `docs/…` path mentioned *anywhere in the tree — code comments
  included —* must exist; the decision index is complete.

## 3. Roles and ownership

The specialty split changes shape: delivery is generalist, expertise moves into the harness.
Ownership runs on two axes:

- **The delivery axis.** Each epic or story is owned end-to-end by **one developer**, who steers
  it through the whole loop (§4) and answers for the outcome. Delivery ownership is full-stack by
  construction: the developer owns the result, not a layer.
- **The harness axis.** The capabilities every delivery passes through — the context system
  (instruction file + docs), skills, checks/CI, model policy — each with a **named human owner**
  who maintains it across all deliveries. (Readers who know Team Topologies will recognize
  stream-aligned vs. platform ownership.)

Every delivery crosses every capability. Defects observed at a crossing feed that capability
owner's backlog — the harness improves from observed failures, never from the armchair.

| Role | Who | Does |
| --- | --- | --- |
| **Developer (delivery owner)** | Human (any engineer) | Owns an epic or story end-to-end: technical product manager at epic altitude, full-stack developer at story altitude (§4). Plans with the planner, executes the human residue of verification (§5), gates the merge — signs every phase transition. A team lead of agents. |
| **Work author** | Human — team lead, PM, or another engineer; at epic altitude often the developer themselves | Defines the work *and its verification artifacts* (§5): an epic ships with its demo/QA script and epic-level acceptance; a story ships with its acceptance criteria. Whoever defines work defines what proves it. |
| **Planner agent** | Strong model, high reasoning | An assistant that drafts like a senior technical product manager — under the developer's direction, never in their place: interactive breakdowns, epic briefs + story drafts, detailed implementation plans at story altitude, plan-conformance review at merge, doc-diff curation, learnings extraction. |
| **Implementor agents** | Model tier chosen per task | Full-stack delivery in isolated worktrees. Draft code + doc updates + validation evidence. Never touch main. |
| **Adversarial reviewer agent** | Strong model, *no authorship stake* | Reviews the code by trying to **falsify** the acceptance criteria — "is it right?", not "does it match the plan?". Ideally a different model family than the implementor (shared blind spots are real). |
| **Specialist reviewers-of-record** | Humans (the former FE/BE/AI specialists) | Review or sample merges touching their specialty; own the skills for it (harness axis). Their raw material is *observed agent mistakes* — which is why they must stay in the review loop: skills maintained from the armchair rot. |
| **Harness owner** | Human, named | Owns CLAUDE.md conventions, the doc lifecycle, the checks, skill gating. The harness is now critical infrastructure; it must not have a bus factor of one *by accident*. |

Notes on the role design:

- **Implementors are full-stack, always.** Tested finding, not ideology: sub-stack agents (a
  backend agent handing off to a frontend agent) recreate the lossy interface the model is trying
  to eliminate. When an epic is too large for one agent, split it into **full-stack vertical
  slices** — never into layer agents — and let the shared epic brief carry coherence. Where slices
  meet, a contract (the OpenAPI schema) is the interface artifact.
- **Plan/review are deliberately split across two agents.** An agent reviewing work against a plan
  it wrote asks the wrong question. The planner keeps the *intent* review ("is this what we
  meant?"), the adversarial reviewer keeps the *correctness* review, and neither merges alone.
- **Skill writes are human-gated.** Agents propose skill changes with the diff and rationale;
  a human confirms. A self-modifying harness with no gate drifts.

## 4. The delivery loop — one loop, two altitudes

The lifecycle is self-similar: it runs the same way whether the developer enters at the epic or at
the story. Invariant at both altitudes: verification artifacts are authored **before
implementation**, by whoever defined the work (§5); review is evidence-based; everything lands
through the one-PR gate; the loop closes. What scales with altitude: brief size, number of agents,
planner involvement.

- **Epic altitude — the developer as technical product manager.** Input: an epic — authored by the
  developer themselves or handed over by a team lead, PM, or another engineer, carrying its
  epic-level verification artifacts (§5). The developer plans with the planner agent, signs the
  brief and the story acceptance criteria, delegates implementation to agent clusters, and
  verifies at the demo level — personally.
- **Story altitude — the developer as full-stack developer.** Input: a prepared story with
  acceptance criteria, handed off by its author (PM or team lead). The developer plans the
  implementation **in detail** with the planner agent — the implementation plan is the developer's
  authored artifact at this altitude — runs the implementor agent(s), and personally executes the
  manual acceptance checks. Ambiguity in the story goes back to the story author as a question,
  never a guess; at merge, conformance is checked against the handed-off story, and the story
  author accepts the outcome.

**1 · Plan.** At epic altitude, developer + planner agent interactively break the epic into
stories under a shared **epic brief** (the compact mental model every implementor will read).
Stories are written like a great tech lead writes them: outcome + acceptance criteria, not
step-by-step "how" — micromanagement is reserved for cases where the developer has a strong
technical opinion or is deliberately using a cheaper model. Rule of thumb: **spec detail scales
inversely with model strength and skill coverage** — and if you find yourself micromanaging
repeatedly, that's a signal a skill is missing, not that specs should grow. At story altitude, the
same phase produces the detailed implementation plan against the handed-off story. Acceptance
criteria are **machine-checkable wherever possible** (tests, evals, screenshot diffs); the
human-judgment residue is what the developer will personally execute (§5).

**2 · Implement.** Full-stack agent(s) in isolated worktrees with their own dev stacks. One agent
when the work fits in one context comfortably; vertical-slice clusters when it doesn't. Every
implementor reads the brief (or the story + implementation plan). Two hard rules: **validation
evidence is part of the deliverable** (test output, screenshots, eval results attached to the PR —
the developer reviews evidence, not claims), and **discovering a better design mid-build is a
plan-change request back to the planner, never silent improvisation** (a mid-build architecture
insight is a plan defect to fix upstream).

**3 · Developer testing.** The developer drives the product themselves — executing the demo/QA
script and every `manual` acceptance criterion from the ladder (§5) — and gives direct feedback to
the implementor in rounds. This step is load-bearing for human context — it is where the
developer's mental model of the product stays real — and it is visible in Engram's history as
repeated "owner feedback round" / "owner screenshot review" commits.

**4 · Review and merge — one PR, two approvals, one merge.** The PR carries: the code, the
implementor-drafted **state-doc diffs**, the **AC↔evidence table** (validation evidence organized
per acceptance criterion — §5), and a **deviations-and-discoveries** section (commit messages are
too narrow an upward channel for "what I learned and where I deviated"). Then:

- the **adversarial reviewer** approves the code (falsification pass against the acceptance
  criteria);
- the **planner** reviews and *edits in-branch* the doc diffs (truthfulness + curation: does this
  belong in system-state? does it contradict another doc?) and checks plan conformance — at story
  altitude, conformance to the handed-off story and the implementation plan, with the story author
  accepting the outcome;
- the **developer** merges. Path-scoped ownership (CODEOWNERS on `docs/**`) makes the human gate
  on state changes *pre-merge and mechanical*, not a post-merge audit.

Docs and code land atomically — there is never a window where main's docs lie about main's code.
The division of labor: the one who did the work **drafts** the record; the one who owns the state
**approves** it. (Prohibiting implementors from touching docs was considered and rejected: a
planner reconstructing rationale second-hand writes plausible-but-wrong docs, the most dangerous
kind. Review beats prohibition.)

**5 · Close the loop.** Decision files + index lines for anything decided; process docs folded and
deleted when the epic ships; evals updated if an AI job changed; skill proposals from anything
learned the hard way. The mechanical parts of this checklist are CI-enforced (§2), so "forgot to
update the docs" is a failing build, not a silent drift.

**Control points — the signature chain.** Control is expressed as named decisions carried by
artifacts, not as additional approval buttons (§1):

| Transition | The developer's decision | Signed artifact |
| --- | --- | --- |
| Plan → Implement | "this is what done means" | epic brief + acceptance criteria (epic altitude) / implementation plan against the handed-off story (story altitude) |
| Implement → Test | "the evidence is complete" | AC↔evidence table in the PR |
| Test → Merge | "I drove it myself and it holds" | executed demo script + manual-AC check-offs with observation notes |
| Merge → Done | "I answer for this in production" | the merge itself; incident ownership (§7) |

## 5. The verification ladder

Every level of decomposition carries its own verification artifact, defined **at the same time as
the work, by whoever defines the work** (§3). Nothing counts as specified until the thing that
will prove it is written down.

| Level | Verification artifact | Authored by | Executed by |
| --- | --- | --- | --- |
| **Epic** | demo/QA script + end-to-end smoke scenarios | the epic author | the developer — personally, by driving the product |
| **Story** | acceptance criteria with stable IDs; each maps to an integration/e2e test, an eval case, or an explicit `manual` tag | the story author (the planner may draft; the author signs) | CI runs the mapped checks on every push; the developer personally executes every `manual` criterion |
| **Task** | test scenarios derived from the criteria → integration tests; unit tests underneath | implementor agents | CI |

(A story that fans out across several implementors splits into sub-stories, each inheriting the
subset of criteria it covers — a split artifact, not a fourth permanent level.)

The developer's duty at each rung is one of three verbs:

- **Author** the top. At epic altitude the developer usually authors the epic and story artifacts;
  at story altitude they author the implementation plan and may propose additional criteria back
  to the story author.
- **Execute** the human residue — the demo script and every `manual` criterion — personally and
  non-delegably. This is §1's anti-detachment loop made concrete.
- **Gate** the machine layers. The developer does **not** re-run unit or integration suites by
  hand — that is §1's rubber-stamping failure mode, and it spends exactly the attention the manual
  checks need. CI executes them on every push; the developer's obligation is to gate that the
  mapping is complete and the evidence is green.

The strictness is mechanical, not exhortative — the same pattern that keeps the decision index
complete (§2):

- Story files carry structured acceptance-criteria blocks with stable IDs.
- **Traceability CI** fails the build on any criterion with no mapped verification.
- The PR template renders the AC↔evidence table: criterion → its check → its latest result.
- Merge is blocked until every `manual` criterion carries the developer's check-off *plus one line
  of what they observed* — a check-off without an observation is a reflex, not a verification.

## 6. Concurrency and integrity across epics

- **Worktrees isolate code, not assumptions.** Two epics planned against the same state docs a week
  apart diverge silently — Engram's own multi-agent merge train needed keep-both merges and
  renumbering fixes (§11.2). Countermeasures: the planner re-reads state docs **at merge time**,
  not plan time; merged state-doc diffs are broadcast to owners of in-flight epics.
- **Stale-but-confident docs are worse than no docs.** The link/mention checks catch dead
  references; for *lies* (doc says X, code does Y), run a periodic doc-audit agent that diffs
  claims against code. Keeping docs to invariants-and-intent (§2) shrinks the surface that can lie.
- **Negative knowledge must not die with the agent's context.** Rejected approaches and dead ends
  go into the merge review's learnings extraction (planner's job), into decision files ("X was
  evaluated and rejected because…"), and into skills' "common mistakes" sections.

## 7. Governance

- **WIP limits are the central control.** The org's throughput is capped by **human verification
  bandwidth, not agent capacity**. One developer runs 1–2 epics concurrently, full stop. A
  developer running five *will* become a "yes" button — the limit is the design, not a bottleneck
  to optimize away.
- **Human-gated surfaces** (agents propose, humans apply): dependency changes, CI configuration,
  auth/security-sensitive code, deployments, production data, skills, and the instruction file
  itself.
- **Provenance.** Agent-authored commits are attributed (co-author trailers); commits distinguish
  *owner-requested* changes from agent judgment (a `User-requested:` trailer) so later reviewers
  and merger agents know what was intentional. Third-party skills are reviewed before vendoring —
  skill files are injected instructions, i.e. a prompt-injection surface.
- **Model-tier policy is measured, central, and periodic.** Which tiers serve which work is decided
  from eval-backed comparisons, not per-delivery vibes. Engram's 74-case owner-designed comparison
  validated its incumbent cheap-tier config and rejected the mid bracket at ~3.5× cost for ~equal
  quality ([the decision record](../docs/technical-decisions/2026-07-10-model-comparison-verdict.md));
  the fixtures are kept as a reusable harness so the next comparison is cheap to run.
- **Stake and ritual.** The developer demos the shipped epic to the team and owns its production
  incidents. Social accountability does what tooling can't.

## 8. People — this is a job change, not a re-badging

Calling everyone "team lead of agents" undersells the transition. The core skills of the new role —
**acceptance-criteria authorship, verification design, epistemic hygiene about what's actually been
checked** — are not the same skills as writing code, and some excellent coders will initially be
bad at them or dislike them.

- **Train deliberately:** a new delivery owner's first epics run paired with an experienced one;
  review their *acceptance criteria*, not just their merges.
- **Hire/promote for spec-writing** the way we used to for algorithms.
- **Watch motivation, not just context.** Detachment has two causes: losing the mental model
  (countered structurally by authorship, developer testing, WIP limits, demo stake — §1, §4–§5,
  §7) and losing the joy (real for people who loved the craft of coding). Keep hands-on escape
  valves — spikes, prototypes, the harness itself — and treat "I miss coding" as a staffing
  signal, not a personal failing.
- **Customer contact stays human.** Ground truth about users cannot be delegated to agents.

## 9. The production loop — the same loop at org altitude

Mechanize one stage and the constraint moves to the next human-serial one. DevOps mechanized
release, and build became the bottleneck; agentic development mechanizes build, and the constraint
lands first on **verification** — the WIP throat of §7, by design. As the harness matures
(verification increasingly mechanized, owners trained), it migrates outward again, to the sensing
edge: real-user feedback, issue generation, prioritization — **the rate at which the org turns
real usage into validated learning**.

The answer is not a new process. The production loop is the delivery loop (§4) run at org
altitude — the org plays the developer, the market plays the product:

- **Agents draft.** A triage agent ingests every signal channel — monitoring alerts, incidents,
  support messages, in-app feedback, usage-analytics anomalies — and drafts evidence-backed
  candidate stories. Incidents also feed the decision log and skills ("what did the harness fail
  to catch, and which check do we add?").
- **Checks verify — push beats pull at the customer edge (§1).** Pull-based feedback is asking
  (surveys, "any issues?") and depends on diligence twice: yours to remember to ask, the user's to
  bother answering. Instrument the product so signal arrives on its own — telemetry, error
  reporting, in-product feedback affordances at the moment of friction, feature-flag cohorts. And
  ship smaller slices behind flags so real-user signal arrives sooner: story-altitude delivery
  (§4) serves this directly. (Interviews and demos stay — they are the human-judgment residue,
  not something instrumentation replaces.)
- **Humans decide.** Which drafted candidates become stories, and in what order, is a human
  product decision — WIP-limited like everything else, so a firehose of agent-drafted stories
  cannot bypass judgment. And the org-level anti-detachment rule: **scheduled, direct customer
  contact is the org's developer testing** (§8). Agent summaries of users are for coverage; direct
  contact is for ground truth. An org that only reads summaries loses its users exactly the way a
  developer who only reads agent reports loses the product.

One honest asymmetry: the customer edge resists mechanization differently from verification. The
scarce resource there is **access, not attention** — users respond on their schedule, not yours.
So the levers are latency-shrinking (smaller shipped slices, flags, instrumentation), not
throughput-multiplying. Hence the learning-latency metric in §10.

## 10. Adoption — pilot criteria and metrics

**Where this model fits now:** repos where verification can be mechanized (testable domains, eval-
able AI behavior, lintable conventions); greenfield or well-factored codebases; teams willing to
fund the harness before the first epic. **Where it doesn't (yet):** tangled legacy systems with no
test surface (agents flail and humans can't verify), and heavily regulated code paths without
clear machine gates — pilot elsewhere first.

**Pilot shape:** one team, one repo, 4–6 weeks. Week 1 builds the harness (instruction-file router,
doc classes + lifecycle, integrity + traceability CI, first skills); then run 2–3 epics through
the full lifecycle (§4) with the WIP limit enforced. The pilot's deliverable is not just shipped
features — it's the measured answer to "did the structure hold?"

**Metrics that matter:**

- % of acceptance criteria that are machine-checked (drive it up per epic);
- acceptance-criteria traceability coverage (no criterion without a mapped check or an explicit
  `manual` tag);
- manual criteria personally executed by the developer, with observation notes;
- verification depth: developer feedback rounds per epic, time-in-review, evidence attached per PR
  (rubber-stamping shows up here first);
- doc integrity: CI catches, drift found by audit agents;
- eval/regression catches **pre-merge** vs incidents post-merge;
- rework rate (stories reopened after merge);
- incident → prioritized-story latency; feedback signal → validated-learning latency.

## 11. Evidence appendix (Engram)

1. **Mechanized checks beat agent diligence 12–0.** The day the doc-integrity checker learned to
   verify path *mentions* (not just links), its first run found 12 code comments citing deleted
   process docs — rot that had survived weeks of disciplined agent work and CI. A follow-up rule
   (decision-index completeness) was negative-tested the same day.
2. **Semantic conflicts are real.** A five-branch parallel build produced story-numbering
   collisions and integration fallout that required keep-both merges — worktrees isolated the code
   but not the assumptions. (§6's merge-time re-reads and diff broadcasts are the response.)
3. **Private memory leaks knowledge.** The repo's hardest-won procedural knowledge (an e2e trap
   where tests silently attach to another worktree's dev server) lived for weeks in one
   assistant's private memory — invisible to other agents and teammates — until it was promoted
   into a shared, versioned skill. The rule: validated procedure belongs in skills, discoverable
   by every agent, or it doesn't exist.
4. **The doc lifecycle works when enforced.** Process docs are routinely folded and deleted on epic
   completion; the isolation tripwire (system-state may not link into the process workspace) is
   what forces the fold. The failure cases all came through the unchecked channel — prose mentions
   — which is now checked (see 1).
5. **Owner testing is visible in history** as repeated owner-feedback and screenshot-review
   commits driving UI refinement rounds — the human context loop functioning as designed.
6. **Eval-gated AI work scales.** Every AI-job change runs a golden-set eval suite (with
   majority-of-N voting to separate LLM variance from regressions); new jobs ship with their own
   suite, and golden-set scenarios are owner-designed. This is the template for "machine-checkable
   acceptance criteria" in any domain.

---

*Open questions deliberately left to the adopting team: issue-tracker integration (this repo uses
in-repo story registries), budget/billing policy per epic, and cross-repo skill sharing. None are
blocking; all follow the same pattern — agents draft, checks verify, humans decide.*
