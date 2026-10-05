import type { createGmailApi } from "./api";
import type { MailboxSummary } from "./types";

type GmailApi = ReturnType<typeof createGmailApi>;

export async function loadMailboxSummary(api: GmailApi): Promise<MailboxSummary> {
  const [labels, mailbox] = await Promise.all([
    api.getLabels(),
    api.listEmails({ page: 1, page_size: 1 }),
  ]);

  return {
    labels,
    counts: { ...(mailbox.counts ?? {}) },
  };
}

export function inferVisibleThreads(pathname: string, search: string, counts: Record<string, number>): number {
  if (!pathname.endsWith("/inbox")) {
    return 0;
  }

  const params = new URLSearchParams(search);
  const filter = params.get("filter");
  if (filter === "starred") {
    return counts.starred ?? 0;
  }

  const label = (params.get("label") ?? "inbox").toLowerCase();
  return counts[label] ?? 0;
}
