import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppLangProvider, toLang } from "../../../shared/i18n";
import type { CaptureSession } from "../../../domain/types";
import { aiCreatedPatientNeedsVerification } from "../captureModel";
import { AiCreatedPatientPanel } from "./CaptureBadges";

// The verify-count / reachable-resolver invariant (Track B, phantom-verify-count fix): the sticky
// "N to confirm" bar counts an AI-created-patient blocker via `aiCreatedPatientNeedsVerification`, and
// the SAME predicate gates the only resolver for it (`AiCreatedPatientPanel`). This test pins the two
// together over the full action lattice so a counted blocker can never lack a reachable resolver, and
// an un-counted action can never render an orphan panel (the historical phantom count: the bar read
// "an ai_patient_action exists", the panel read "created + still unverified").

function session(overrides: Partial<CaptureSession> = {}): CaptureSession {
  return {
    id: "session-1",
    label: "Session",
    time: "10:00",
    dateLabel: "Today",
    duration: "5m",
    summary: "",
    status: "processing",
    items: [],
    ...overrides,
  };
}

function panelRenders(action: Record<string, unknown>, sess: CaptureSession): boolean {
  const markup = renderToStaticMarkup(
    <AppLangProvider lang={toLang("en")}>
      <AiCreatedPatientPanel action={action} session={sess} onComplete={async () => {}} />
    </AppLangProvider>,
  );
  return markup.trim() !== "";
}

const cases: Array<{ name: string; action: Record<string, unknown>; sess: CaptureSession; blocker: boolean }> = [
  {
    name: "AI-created patient, still unverified → counted + resolver renders",
    action: { action: "created_and_assigned", patientId: "p1", needsVerification: true },
    sess: session({ patientId: "p1", patientName: "Sara" }),
    blocker: true,
  },
  {
    name: "AI-created patient already verified → not counted, no panel",
    action: { action: "created_and_assigned", patientId: "p1", status: "verified" },
    sess: session({ patientId: "p1", patientName: "Sara" }),
    blocker: false,
  },
  {
    name: "AI-created patient, needsVerification explicitly false → not counted, no panel",
    action: { action: "created_and_assigned", patientId: "p1", needsVerification: false },
    sess: session({ patientId: "p1", patientName: "Sara" }),
    blocker: false,
  },
  {
    name: "a plain AI match (not created) → not counted, no panel (the phantom-count case)",
    action: { action: "matched", patientId: "p1" },
    sess: session({ patientId: "p1", patientName: "Sara" }),
    blocker: false,
  },
  {
    name: "created_and_assigned but no patient id anywhere → not counted, no panel",
    action: { action: "created_and_assigned", needsVerification: true },
    sess: session(),
    blocker: false,
  },
  {
    name: "empty action → not counted, no panel",
    action: {},
    sess: session(),
    blocker: false,
  },
];

describe("AI-created-patient verify blocker — count and resolver stay in lock-step", () => {
  for (const testCase of cases) {
    it(testCase.name, () => {
      const counted = aiCreatedPatientNeedsVerification(testCase.action, testCase.sess);
      expect(counted).toBe(testCase.blocker);
      // The invariant: the predicate that drives the COUNT is exactly the one that renders the RESOLVER.
      expect(panelRenders(testCase.action, testCase.sess)).toBe(counted);
    });
  }
});
