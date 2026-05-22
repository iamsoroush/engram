# Design Principles

## 1. Capture first

The user must be able to capture before selecting or verifying a patient.

Capture flow should feel immediate and interruption-free.

---

## 2. Sessions are continuously evolving objects

A session is not a rigid workflow step.

The same session can:
- receive captures
- process progressively
- remain reviewable
- be verified later

Users should never lose access because a workflow step is incomplete.

---

## 3. Patients are the primary long-term navigation model

The system should feel patient-centered, not queue-centered.

Use:
- patient timelines
- session history
- lightweight status indicators

Avoid:
- workflow-heavy dashboards
- large review queues
- rigid processing funnels

---

## 4. Prefer soft workflow over enforced workflow

Users should be able to:
- assign sessions anywhere
- verify anywhere
- review anywhere
- continue capturing anywhere

Warnings and confidence indicators are preferred over blocking behavior.

---

## 5. Keep the report central

The report is the primary clinical surface.

Captures, summaries, and extracted findings support the report instead of competing with it.

Even incomplete sessions should preserve a stable report layout.

---

## 6. Keep AI mostly invisible

AI should feel assistive, not dominant.

Do not expose:
- pipelines
- model states
- technical reasoning

Expose only:
- useful summaries
- extracted findings
- confidence warnings
- source traceability

---

## 7. Use progressive disclosure

High-level understanding should appear first.

Suggested hierarchy:
1. report
2. summary
3. extracted findings
4. source captures

Avoid overwhelming the user with raw information by default.

---

## 8. Preserve “capture anywhere” feeling

Persistent capture actions are encouraged.

However, capture destination must always remain clear to avoid user anxiety about where new material was saved.

---

## 9. Minimize cognitive fatigue

Do not force users into:
- mandatory verification
- mandatory organization
- sequential workflow completion

The system should support natural clinical interruptions and asynchronous review behavior.

---

## 10. The product should feel lightweight

The UX should resemble:
- fast clinical memory
- Apple Notes simplicity
- lightweight assistant behavior

Avoid HIS-like complexity and administrative density.
