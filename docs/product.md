# Product

## Product summary

AesMem is a lightweight clinical capture tool for aesthetics clinics. It helps doctors capture session information quickly using audio, photo, and text without forcing them into a full HIS-like workflow.

## Target users

- Aesthetics doctors
- Clinic staff involved in clinical documentation

## Core problem

Doctors often capture clinical information using scattered tools such as notes, photos, and voice recordings. This creates friction during the visit and makes later organization difficult.

## Product promise

Make clinical session capture fast, low-friction, and progressively organized.

## Current product behavior

### Capture-first workflow

The user can start capturing information immediately.

Supported capture types:
- Audio
- Photo
- Text

The user should not be forced to select or create a patient before capturing.

Each capture can show an expandable generated-text area wherever captures are listed:

- Audio shows transcription.
- Photo shows a caption.
- Text shows decorated text.

For the current prototype, these fields are placeholder backend outputs. Captures simulate about five seconds of processing before the placeholder text is marked complete.

### Active session workflow

After the first capture, the system creates or uses an active session.

New captures are attached to the active session by default.

The user should be able to understand which session is currently active.
