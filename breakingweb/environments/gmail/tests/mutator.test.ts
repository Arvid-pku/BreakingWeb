import { describe, expect, it } from "vitest";

import { gmailMutator, type GmailFixture } from "../src/mutator";

function makeFixture(): GmailFixture {
  return {
    env_id: "gmail",
    task_id: "test_task",
    owner_name: "Avery Quinn",
    owner_email: "avery@example.com",
    emails: [
      {
        id: "email_1",
        from_name: "Alice",
        from_addr: "alice@example.com",
        to: ["avery@example.com"],
        cc: [],
        bcc: [],
        subject: "Flagged thread",
        body: "Please review",
        timestamp: "2026-03-19T09:00:00Z",
        is_read: false,
        is_starred: true,
        labels: ["inbox", "starred", "Projects"],
        thread_id: "thread_1",
        attachments: [],
      },
      {
        id: "email_2",
        from_name: "Bob",
        from_addr: "bob@example.com",
        to: ["avery@example.com"],
        cc: [],
        bcc: [],
        subject: "Archived thread",
        body: "For reference",
        timestamp: "2026-03-18T09:00:00Z",
        is_read: true,
        is_starred: false,
        labels: ["Projects"],
        thread_id: "thread_2",
        attachments: [],
      },
    ],
    sent: [
      {
        id: "sent_1",
        from_name: "Avery Quinn",
        from_addr: "avery@example.com",
        to: ["team@example.com"],
        cc: [],
        bcc: [],
        subject: "Sent note",
        body: "FYI",
        timestamp: "2026-03-17T09:00:00Z",
        is_read: true,
        is_starred: false,
        labels: ["sent"],
        thread_id: "thread_3",
        attachments: [],
      },
    ],
    deleted: [],
    drafts: [
      {
        id: "draft_1",
        from_name: "Avery Quinn",
        from_addr: "avery@example.com",
        to: [],
        cc: [],
        bcc: [],
        subject: "Draft note",
        body: "",
        timestamp: "2026-03-16T09:00:00Z",
        is_read: true,
        is_starred: false,
        labels: ["drafts"],
        thread_id: "draft_thread_1",
        attachments: [],
      },
    ],
    labels: [
      { id: "label_inbox", name: "inbox", color: "#202124", system: true },
      { id: "label_starred", name: "starred", color: "#fbbc04", system: true },
      { id: "label_drafts", name: "drafts", color: "#5f6368", system: true },
      { id: "label_allmail", name: "all mail", color: "#5f6368", system: true },
      { id: "label_projects", name: "Projects", color: "#1a73e8" },
    ],
    filters: [],
    contacts: [],
    settings: {
      signature: "",
      forwarding_address: "",
      display_density: "comfortable",
      vacation_responder_enabled: false,
      vacation_responder_message: "",
      auto_advance: "newer",
      language: "English (US)",
      input_tools_enabled: true,
      right_to_left: false,
      max_page_size: 50,
      undo_send_seconds: 5,
      default_reply_behavior: "reply",
      hover_actions_enabled: true,
      send_and_archive: false,
      default_text_style: "Sans Serif",
    },
  };
}

describe("gmailMutator mailbox counts", () => {
  it("returns authoritative counts for system labels and custom labels", () => {
    const { response } = gmailMutator(
      makeFixture(),
      "GET",
      "emails",
      undefined,
      { label: "inbox" },
    ) as { response: { counts: Record<string, number> } };

    expect(response.counts.inbox).toBe(1);
    expect(response.counts.starred).toBe(1);
    expect(response.counts.drafts).toBe(1);
    expect(response.counts["all mail"]).toBe(3);
    expect(response.counts.projects).toBe(2);
    expect(response.counts.label_projects).toBe(2);
    expect(response.counts.label_starred).toBe(1);
  });

  it("supports the starred mailbox view directly", () => {
    const { response } = gmailMutator(
      makeFixture(),
      "GET",
      "emails",
      undefined,
      { label: "starred" },
    ) as { response: { items: Array<{ id: string }> } };

    expect(response.items.map((item) => item.id)).toEqual(["email_1"]);
  });

  it("normalizes display-name recipients before sending", () => {
    const fixture = makeFixture();
    const { response } = gmailMutator(
      fixture,
      "POST",
      "send",
      {
        to: ["Ravi Menon <SOFIA.BROOKS@ATLAS.DEV>"],
        cc: ["Priya Sharma <PRIYA@ATLAS.DEV>"],
        bcc: ["LEGAL@ATLAS.DEV"],
        subject: "Atlas decision",
        body: "Forwarding the final decision on Project Atlas.",
      },
    ) as { response: { email: { to: string[]; cc: string[]; bcc?: string[] } } };

    expect(response.email.to).toEqual(["sofia.brooks@atlas.dev"]);
    expect(response.email.cc).toEqual(["priya@atlas.dev"]);
    expect(response.email.bcc).toEqual(["legal@atlas.dev"]);
  });
});
