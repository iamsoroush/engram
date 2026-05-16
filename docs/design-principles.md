# Design Principles

## 1. Capture first

The user must be able to capture audio, photo, or text before selecting a patient.

Patient selection or matching must not block capture.

## 2. Keep the workflow lightweight

The app should feel like a fast clinical assistant, not a hospital information system.

Avoid:
- large dashboards
- administrative-heavy flows
- billing/insurance concepts
- complex patient registry behavior

## 3. Active session should be clear

After the first capture, the user should always understand where new captures will go.

The active session should remain visible or easily understandable.

## 4. Organize progressively

The system can organize, match, or enrich information after capture.

Uncertainty should be shown clearly, but should not block the user from capturing.

## 5. Minimize primary actions

The main capture experience should stay focused on a small number of core actions:
- record audio
- capture/upload photo
- write text

## 6. Hide technical AI details

Do not expose internal AI or processing details unless they directly affect user trust, workflow, or error recovery.

## 7. Prefer warnings over blocking

When the system is uncertain, prefer visible warnings, review states, or attention markers instead of preventing the user from continuing.
