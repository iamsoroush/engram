# CaptureFirst Designer Handoff

Design system: shadcn/ui + Tailwind CSS. Principle: doctor must never be forced to select a patient before capturing.

## S1. Today / Capture Home

Make capture the default action and make unassigned sessions visible without making them feel like a blocker.

### Components
- Top bar with product name and doctor identity
- Primary Start Capture CTA
- Secondary quick actions: Add photo only, Write quick note
- Unassigned sessions counter
- Recent captures list
- Design intent helper card

### States
- Empty state: no recent captures, 0 unassigned
- Normal state: recent captures and unassigned count
- Warning state: many unassigned sessions with gentle review prompt
- Saving state: disabled Start Capture only if the app cannot safely start a session

### Interactions
- Start Capture opens S2 immediately, without patient selection.
- Review queue opens S4.
- Recent capture click opens S6 if matched, S5/S4 path if unassigned.

## S2. Active Capture Session

Support low-friction capture during the visit while keeping patient assignment intentionally separate.

### Components
- Unassigned session header
- Elapsed timer and status indicator
- Save Session primary action
- Voice/photo/note capture controls
- Session feed of captured items
- Pause/discard secondary actions

### States
- Idle active session
- Recording voice
- Photo captured / upload pending
- Saving
- Network or device error
- Discard confirmation

### Interactions
- Doctor can add multiple items to one session.
- Save moves to S3.
- Discard requires confirmation because captured source material may be lost.
- No patient search appears on this screen.

## S3. Session Saved Confirmation

Reassure the doctor that unassigned capture is safe and offer the next natural action.

### Components
- Success confirmation
- Session summary label
- Start another capture primary action
- Review unassigned sessions secondary action
- Short reassurance copy

### States
- Saved successfully
- Saved but sync pending
- Save failed retry state

### Interactions
- Start another capture opens S2 with a new session.
- Review unassigned opens S4.
- Back returns to S1.

## S4. Unassigned Sessions Inbox

Let the doctor review unassigned captures when there is time, without turning the product into scheduling software.

### Components
- Queue filters
- Session search
- Unassigned session cards
- Preview panel
- Find patient to match CTA

### States
- Empty queue
- Queue with selected item
- Search/filter results
- Preview loading
- Preview unavailable

### Interactions
- Selecting a session updates preview.
- Match opens S5.
- Filters narrow the queue but do not expose full clinic scheduling.

## S5. Patient Match Workspace

Make patient assignment explicit, safe, and reversible.

### Components
- Captured session preview
- Patient search input
- Candidate patient list
- Confidence/reason hints as UX copy
- Confirm match CTA
- Keep unassigned action
- Safety cue

### States
- No search entered
- Candidate list available
- No candidate found
- Selected candidate
- Confirming match
- Possible duplicate warning

### Interactions
- Doctor reviews captured context and chooses a candidate.
- Confirm match leads to S6.
- Keep unassigned returns to S4.
- System may suggest candidates, but never silently assigns.

## S6. Patient Visit Session View

Show matched captured material organized around the visit, while preserving original sources and avoiding HIS-like scope.

### Components
- Patient summary card
- Matched session metadata
- Captured material sections
- Original source list
- Undo match link
- Scope boundary notice

### States
- Matched session loaded
- Source preview opened
- Undo match confirmation
- Missing source warning

### Interactions
- Source click opens original capture preview.
- Undo match returns the session to S4.
- No billing, invoicing, insurance, or diagnosis workflow appears here.

