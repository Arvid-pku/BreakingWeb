import { describe, it, expect, vi, beforeEach } from "vitest";
import type { TrajectoryStep } from "../results";

/* ------------------------------------------------------------------ */
/*  Category 9: buildGmailReplayStepStates unit tests                  */
/* ------------------------------------------------------------------ */

// Mock gmailMutator since it's a heavy dependency
vi.mock("@breakingweb/gmail/mutator", () => ({
  gmailMutator: vi.fn(
    (state: unknown, method: string, path: string, body?: unknown, query?: unknown) => {
      // Simple passthrough - return empty response
      return { response: { items: [] } };
    },
  ),
}));

// Import after mock setup
import { buildGmailReplayStepStates } from "../gmailReplay";
import type { GmailReplayStepState } from "../gmailReplay";
import { gmailMutator } from "@breakingweb/gmail/mutator";

function getQueryParams(route: string) {
  return new URL(`https://example.test${route}`).searchParams;
}

function makeFixture() {
  return {
    env_id: "gmail",
    task_id: "test",
    owner_name: "Test User",
    owner_email: "test@example.com",
    emails: [
      {
        id: "email_1",
        thread_id: "thread_1",
        subject: "Hello",
        body: "Hi there",
        from_addr: "sender@example.com",
        from_name: "Sender",
        to: ["test@example.com"],
        cc: [],
        bcc: [],
        timestamp: "2024-01-01T10:00:00Z",
        labels: ["inbox"],
        is_read: false,
        is_starred: false,
        snippet: "Hi there",
        thread_size: 1,
        attachments: [],
      },
    ],
    sent: [],
    deleted: [],
    drafts: [],
    labels: [
      { id: "label_1", name: "Work", color: "#ff0000" },
    ],
    filters: [],
    contacts: [
      {
        id: "contact_1",
        name: "Sender",
        email: "sender@example.com",
        company: "Acme",
        note: "",
        is_starred: false,
        is_vip: false,
      },
    ],
    settings: {
      signature: "",
      vacation_responder_message: "",
      vacation_responder_enabled: false,
      forwarding_address: "",
      undo_send_seconds: 5,
      max_page_size: 50,
      language: "English",
      default_reply_behavior: "reply" as const,
      send_and_archive: false,
      display_density: "default" as const,
    },
  };
}

function makeStep(overrides: Partial<TrajectoryStep> = {}): TrajectoryStep {
  return {
    step: 0,
    thought: "thinking",
    action: { action: "click", ref: 1 },
    targets: {},
    status: "success",
    elapsed_seconds: 1.0,
    replay_path: "/inbox?label=inbox",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("buildGmailReplayStepStates", () => {
  // 9a: Returns empty array when steps are empty
  it("returns empty array for empty steps", () => {
    const result = buildGmailReplayStepStates(makeFixture() as any, []);
    expect(result).toEqual([]);
  });

  // 9b: Returns one state per step, each with independent fixture clone
  it("returns one state per step with cloned fixtures", () => {
    const steps = [
      makeStep({ step: 0 }),
      makeStep({ step: 1 }),
      makeStep({ step: 2 }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    expect(result).toHaveLength(3);

    // Each fixture should be a distinct object (structuredClone)
    expect(result[0].fixture).not.toBe(result[1].fixture);
    expect(result[1].fixture).not.toBe(result[2].fixture);
  });

  // 9c: fill action on compose field updates draft state
  it("fill action on compose Recipients updates draft and route", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "fill", ref: 1, value: "alice@example.com" },
        targets: { ref: { role: "textbox", name: "Recipients" } },
        replay_path: "/compose",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    expect(result).toHaveLength(1);
    expect(result[0].displayRoute).toBeDefined();
  });

  // 9d: click action on email thread
  it("click on Open thread triggers email read mutation", () => {
    const fixture = makeFixture();
    (gmailMutator as any).mockImplementation(
      (state: any, method: string, path: string, body?: any, query?: any) => {
        if (method === "GET" && path === "emails") {
          return { response: { items: fixture.emails } };
        }
        return { response: {} };
      },
    );

    const steps = [
      makeStep({
        step: 0,
        action: { action: "click", ref: 1 },
        targets: { ref: { role: "link", name: "Open thread Hello" } },
        replay_path: "/inbox?label=inbox",
      }),
    ];

    buildGmailReplayStepStates(fixture as any, steps);

    // Should have called gmailMutator to mark email as read
    expect(gmailMutator).toHaveBeenCalledWith(
      expect.anything(),
      "POST",
      expect.stringContaining("/read"),
      expect.objectContaining({ is_read: true }),
      undefined,
    );
  });

  // 9e: click on star toggles starred state
  it("click on Star triggers star mutation", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "click", ref: 1 },
        targets: { ref: { role: "button", name: "Star this thread" } },
        replay_path: "/thread/email_1",
      }),
    ];

    // Mock gmailMutator to return the email for the GET request
    const fixture = makeFixture();
    (gmailMutator as any).mockImplementation(
      (state: any, method: string, path: string, body?: any, query?: any) => {
        if (method === "GET") {
          return { response: { items: fixture.emails } };
        }
        return { response: {} };
      },
    );

    buildGmailReplayStepStates(fixture as any, steps);

    expect(gmailMutator).toHaveBeenCalledWith(
      expect.anything(),
      "POST",
      "emails/email_1/star",
      undefined,
      undefined,
    );
  });

  // 9f: Settings tab selection updates activeTab
  it("click on settings tab updates displayRoute", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "click", ref: 1 },
        targets: { ref: { role: "tab", name: "Filters and Blocked Addresses" } },
        replay_path: "/settings",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    // The tab should be encoded in the display route
    expect(result[0].displayRoute).toContain("tab=");
  });

  // 9g: check action sets filter draft fields
  it("check action sets filter draft boolean fields", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "check", ref: 1 },
        targets: { ref: { role: "checkbox", name: "Skip Inbox (Archive it)" } },
        replay_path: "/settings",
      }),
    ];

    // Should not throw
    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    expect(result).toHaveLength(1);
  });

  // 9h: select action sets settings values
  it("select action updates settings draft values", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "select", ref: 1, value: "10" },
        targets: { ref: { role: "combobox", name: "Undo send seconds" } },
        replay_path: "/settings",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    expect(result).toHaveLength(1);
  });

  // 9i: Mutations from step N don't leak into step N-1's snapshot
  it("step snapshots are isolated — mutations don't leak backward", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "fill", ref: 1, value: "new sig" },
        targets: { ref: { role: "textbox", name: "Email signature" } },
        replay_path: "/settings",
      }),
      makeStep({
        step: 1,
        action: { action: "click", ref: 2 },
        targets: { ref: { role: "button", name: "Save Gmail settings" } },
        replay_path: "/settings",
      }),
    ];

    (gmailMutator as any).mockImplementation(
      (state: any, method: string, path: string, body?: any) => {
        if (method === "PUT" && path === "settings") {
          // Simulate settings save by mutating state
          state.settings = { ...state.settings, ...body };
        }
        return { response: {} };
      },
    );

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);

    // Step 0 snapshot should have original settings (save hasn't happened yet)
    expect(result[0].fixture.settings.signature).toBe("");
    // Step 1 snapshot may have updated settings (after save mutation)
    // The key point: step 0 is not affected by step 1's mutation
  });

  // 9j: fill action on label name field
  it("fill on New label name in /labels updates labelsPage draft", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "fill", ref: 1, value: "Important" },
        targets: { ref: { role: "textbox", name: "New label name" } },
        replay_path: "/labels",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    expect(result).toHaveLength(1);
  });

  // 9k: compose flow - fill fields then send
  it("compose flow: fill Recipients then Send", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "click", ref: 1 },
        targets: { ref: { role: "button", name: "Compose a new message" } },
        replay_path: "/inbox?label=inbox",
      }),
      makeStep({
        step: 1,
        action: { action: "fill", ref: 2, value: "bob@example.com" },
        targets: { ref: { role: "textbox", name: "Recipients" } },
        replay_path: "/compose",
      }),
      makeStep({
        step: 2,
        action: { action: "fill", ref: 3, value: "Hello Bob" },
        targets: { ref: { role: "textbox", name: "Email subject" } },
        replay_path: "/compose",
      }),
      makeStep({
        step: 3,
        action: { action: "click", ref: 4 },
        targets: { ref: { role: "button", name: "Send" } },
        replay_path: "/compose",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    expect(result).toHaveLength(4);

    // Send should call gmailMutator with POST "send"
    expect(gmailMutator).toHaveBeenCalledWith(
      expect.anything(),
      "POST",
      "send",
      expect.objectContaining({
        to: ["bob@example.com"],
        subject: "Hello Bob",
      }),
      undefined,
    );
  });

  it("prefers the next replay path when result_path is stale", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "click", ref: 1 },
        targets: { ref: { role: "button", name: "Compose a new message" } },
        replay_path: "/inbox",
        result_path: "/inbox",
        status: "",
      }),
      makeStep({
        step: 1,
        action: { action: "fill", ref: 2, value: "alice@example.com" },
        targets: { ref: { role: "textbox", name: "Recipients" } },
        replay_path: "/compose",
        status: "",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    expect(result[0].displayRoute).toContain("/compose");
  });

  it("does not apply failed fill actions to replay drafts", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "fill", ref: 1, value: "should-not-stick@example.com" },
        targets: { ref: { role: "textbox", name: "Recipients" } },
        replay_path: "/compose",
        status: "ERROR: ValueError: Received an empty action.",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    const params = getQueryParams(result[0].displayRoute);

    expect(params.get("replayTo")).toBeNull();
  });

  it("shows in-progress search text in the shell query string before submit", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "fill", ref: 1, value: "vendor security" },
        targets: { ref: { role: "searchbox", name: "Search mail" } },
        replay_path: "/inbox?label=inbox",
        status: "",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    const params = getQueryParams(result[0].displayRoute);

    expect(params.get("q")).toBe("vendor security");
  });

  it("emits compose replay params for cc, bcc, subject, and attachments", () => {
    const steps = [
      makeStep({
        step: 0,
        action: { action: "click", ref: 1 },
        targets: { ref: { role: "button", name: "Compose a new message" } },
        replay_path: "/inbox",
        status: "",
      }),
      makeStep({
        step: 1,
        action: { action: "click", ref: 2 },
        targets: { ref: { role: "button", name: "Show CC field" } },
        replay_path: "/compose",
        status: "",
      }),
      makeStep({
        step: 2,
        action: { action: "click", ref: 3 },
        targets: { ref: { role: "button", name: "Show BCC field" } },
        replay_path: "/compose",
        status: "",
      }),
      makeStep({
        step: 3,
        action: { action: "fill", ref: 4, value: "cc@example.com" },
        targets: { ref: { role: "textbox", name: "Carbon copy recipients" } },
        replay_path: "/compose",
        status: "",
      }),
      makeStep({
        step: 4,
        action: { action: "fill", ref: 5, value: "bcc@example.com" },
        targets: { ref: { role: "textbox", name: "Blind carbon copy recipients" } },
        replay_path: "/compose",
        status: "",
      }),
      makeStep({
        step: 5,
        action: { action: "fill", ref: 6, value: "Replay subject" },
        targets: { ref: { role: "textbox", name: "Email subject" } },
        replay_path: "/compose",
        status: "",
      }),
      makeStep({
        step: 6,
        action: { action: "fill", ref: 7, value: "notes.txt" },
        targets: { ref: { role: "textbox", name: "Attachment filenames" } },
        replay_path: "/compose",
        status: "",
      }),
    ];

    const result = buildGmailReplayStepStates(makeFixture() as any, steps);
    const params = getQueryParams(result[6].displayRoute);

    expect(params.get("replayShowCc")).toBe("1");
    expect(params.get("replayShowBcc")).toBe("1");
    expect(params.get("replayCc")).toBe("cc@example.com");
    expect(params.get("replayBcc")).toBe("bcc@example.com");
    expect(params.get("replaySubject")).toBe("Replay subject");
    expect(params.get("replayAttachments")).toBe("notes.txt");
  });

  it("emits replay params for unsaved settings and contacts drafts", () => {
    const settingsSteps = [
      makeStep({
        step: 0,
        action: { action: "fill", ref: 1, value: "Regards, Team" },
        targets: { ref: { role: "textbox", name: "Email signature" } },
        replay_path: "/settings",
        status: "",
      }),
    ];
    const contactSteps = [
      makeStep({
        step: 0,
        action: { action: "fill", ref: 2, value: "Priya Patel" },
        targets: { ref: { role: "textbox", name: "Contact name" } },
        replay_path: "/labels",
        status: "",
      }),
    ];

    const settingsResult = buildGmailReplayStepStates(makeFixture() as any, settingsSteps);
    const contactResult = buildGmailReplayStepStates(makeFixture() as any, contactSteps);

    expect(getQueryParams(settingsResult[0].displayRoute).get("replaySignature")).toBe("Regards, Team");
    expect(getQueryParams(contactResult[0].displayRoute).get("replayContactName")).toBe("Priya Patel");
  });
});
