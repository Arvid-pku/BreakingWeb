import { describe, expect, it, vi } from "vitest";

import { inferVisibleThreads, loadMailboxSummary } from "../src/mailboxSummary";

describe("loadMailboxSummary", () => {
  it("loads labels and authoritative mailbox counts", async () => {
    const api = {
      getLabels: vi.fn().mockResolvedValue([{ id: "label_starred", name: "starred" }]),
      listEmails: vi.fn().mockResolvedValue({
        items: [],
        page: 1,
        page_size: 1,
        total: 0,
        pages: 1,
        counts: { inbox: 12, starred: 3 },
      }),
    };

    const summary = await loadMailboxSummary(api as never);

    expect(api.getLabels).toHaveBeenCalledTimes(1);
    expect(api.listEmails).toHaveBeenCalledWith({ page: 1, page_size: 1 });
    expect(summary).toEqual({
      labels: [{ id: "label_starred", name: "starred" }],
      counts: { inbox: 12, starred: 3 },
    });
  });
});

describe("inferVisibleThreads", () => {
  it("uses label counts for inbox routes", () => {
    expect(
      inferVisibleThreads("/inbox", "?label=inbox", { inbox: 18, starred: 4 }),
    ).toBe(18);
  });

  it("uses starred counts for starred filter routes", () => {
    expect(
      inferVisibleThreads("/inbox", "?label=inbox&filter=starred", { inbox: 18, starred: 4 }),
    ).toBe(4);
  });

  it("returns zero outside inbox pages", () => {
    expect(
      inferVisibleThreads("/thread/email_1", "", { inbox: 18, starred: 4 }),
    ).toBe(0);
  });
});
