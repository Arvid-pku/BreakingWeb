import { useEffect, useMemo, useState } from "react";
import { EmptyState, Tabs } from "@breakingweb/shared";
import { useSearchParams } from "react-router-dom";

import { EmailRow } from "../components/EmailRow";
import { useGmailLayout } from "../context";
import { IconChevronLeft, IconChevronRight } from "../icons";
import type { Email, EmailListResponse } from "../types";

const PAGE_SIZE = 16;
const API_PAGE_SIZE = 100;

/**
 * Category tabs mirror real Gmail's Primary/Promotions/Updates tabbed inbox.
 * "Primary" excludes emails labeled "promotions" or "updates".
 * "All Mail" shows everything (the old default).
 */
const CATEGORY_LABELS = new Set(["promotions", "updates"]);

function categoryOf(email: Email): string {
  for (const label of email.labels ?? []) {
    if (CATEGORY_LABELS.has(label)) return label;
  }
  return "primary";
}

async function fetchMailboxSnapshot(
  api: ReturnType<typeof useGmailLayout>["api"],
  options: { label: string; starred?: boolean },
): Promise<EmailListResponse> {
  const { label, starred } = options;
  const firstPage = await api.listEmails({
    label,
    starred,
    page: 1,
    page_size: API_PAGE_SIZE,
  });
  if (firstPage.pages <= 1) {
    return firstPage;
  }

  const remainingPages = await Promise.all(
    Array.from({ length: firstPage.pages - 1 }, (_, index) =>
      api.listEmails({
        label,
        starred,
        page: index + 2,
        page_size: API_PAGE_SIZE,
      }),
    ),
  );

  return {
    ...firstPage,
    items: [firstPage, ...remainingPages].flatMap((response) => response.items),
  };
}

export function InboxPage() {
  const { api, notify, refreshMailbox, summary } = useGmailLayout();
  const [searchParams, setSearchParams] = useSearchParams();
  const [inbox, setInbox] = useState<EmailListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const label = searchParams.get("label") ?? "inbox";
  const filter = searchParams.get("filter");
  const page = Number(searchParams.get("page") ?? 1);
  const category = searchParams.get("category") ?? "primary";
  const isStarredView = label === "starred" || filter === "starred";
  const showCategoryTabs = label === "inbox" && !isStarredView;
  const mailboxQuery = useMemo(
    () => ({
      label,
      starred: filter === "starred" ? true : undefined,
    }),
    [filter, label],
  );

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    // Category tabs filter client-side, so fetch the full mailbox view via pagination.
    fetchMailboxSnapshot(api, mailboxQuery)
      .then((response) => {
        if (!cancelled) setInbox(response);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load emails");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, [api, mailboxQuery]);

  const reload = async () => {
    const response = await fetchMailboxSnapshot(api, mailboxQuery);
    setInbox(response);
    await refreshMailbox();
  };

  const runMutation = async (email: Email, mutate: () => Promise<unknown>, title: string, onUndo?: () => void) => {
    try {
      await mutate();
      notify(title, email.subject, onUndo);
      await reload();
    } catch (err: unknown) {
      const detail = (err as { detail?: { error?: string } })?.detail;
      const message = detail?.error ?? "Action failed. Please retry.";
      notify("Error", message);
    }
  };

  // Filter by category, then paginate client-side
  const filteredEmails = useMemo(() => {
    if (!inbox) return [];
    if (!showCategoryTabs || category === "all") return inbox.items;
    return inbox.items.filter((email) => categoryOf(email) === category);
  }, [category, inbox, showCategoryTabs]);

  const totalItems = filteredEmails.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
  const rangeStart = totalItems > 0 ? (page - 1) * PAGE_SIZE + 1 : 0;
  const rangeEnd = Math.min(page * PAGE_SIZE, totalItems);
  const pageItems = filteredEmails.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const hasUnread = filteredEmails.some((email) => !email.is_read);

  const handleMarkAllRead = async () => {
    await api.markAllRead();
    await reload();
  };

  const labelTitle = isStarredView
    ? "Starred"
    : (label === "inbox" ? "Inbox" : label[0]?.toUpperCase() + label.slice(1));

  return (
    <main className="gmail-page" aria-label={labelTitle}>
      <div className="gmail-toolbar">
        <div className="gmail-toolbar__left">
          {showCategoryTabs ? (
            <Tabs
              label="Inbox categories"
              items={[
                { label: "Primary", value: "primary" },
                { label: "Promotions", value: "promotions" },
                { label: "Updates", value: "updates" },
                { label: "All Mail", value: "all" },
              ]}
              value={category}
              onChange={(next) => setSearchParams((current) => {
                current.set("category", next);
                current.set("page", "1");
                return current;
              })}
            />
          ) : null}
          {hasUnread ? (
            <button
              type="button"
              className="gmail-toolbar__action-btn"
              aria-label="Mark all as read"
              onClick={handleMarkAllRead}
            >
              Mark all read
            </button>
          ) : null}
        </div>
        <div className="gmail-toolbar__right">
          {totalItems > 0 ? (
            <>
              <span className="gmail-toolbar__page-info">
                {rangeStart}–{rangeEnd} of {totalItems}
              </span>
              <button
                type="button"
                className="gmail-toolbar__nav-btn"
                aria-label="Previous page"
                disabled={page <= 1}
                onClick={() => setSearchParams((current) => {
                  current.set("page", String(page - 1));
                  return current;
                })}
              >
                <IconChevronLeft />
              </button>
              <button
                type="button"
                className="gmail-toolbar__nav-btn"
                aria-label="Next page"
                disabled={page >= totalPages}
                onClick={() => setSearchParams((current) => {
                  current.set("page", String(page + 1));
                  return current;
                })}
              >
                <IconChevronRight />
              </button>
            </>
          ) : null}
        </div>
      </div>

      {isLoading ? <section className="gmail-loading" aria-live="polite">Loading…</section> : null}

      {!isLoading && error ? (
        <EmptyState title="Something went wrong" description={error} />
      ) : null}

      {!isLoading && inbox && pageItems.length === 0 ? (
        <EmptyState
          title="No messages match this view"
          description={
            showCategoryTabs
              ? "Try another category tab to find the emails you're looking for."
              : "Try another mailbox view to find the emails you're looking for."
          }
        />
      ) : null}

      <section className="gmail-email-list" aria-label="Email results">
        {pageItems.map((email) => (
          <EmailRow
            key={email.id}
            email={email}
            labels={summary?.labels ?? []}
            currentLabel={label}
            onToggleStar={(entry) =>
              runMutation(entry, () => api.toggleStar(entry.id), entry.is_starred ? "Removed star" : "Starred thread")
            }
            onArchive={(entry) =>
              runMutation(entry, () => api.archive(entry.id), "Conversation archived", async () => {
                await api.applyEmailLabel(entry.id, "inbox", "add");
                await reload();
              })
            }
            onDelete={(entry) => runMutation(entry, () => api.deleteEmail(entry.id), label === "trash" ? "Permanently deleted" : "Moved thread to trash")}
            onRestore={(entry) =>
              runMutation(
                entry,
                () => label === "trash"
                  ? api.restoreEmail(entry.id)
                  : api.applyEmailLabel(entry.id, "inbox", "add"),
                "Moved to inbox",
              )
            }
          />
        ))}
      </section>
    </main>
  );
}
