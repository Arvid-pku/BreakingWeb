import { useEffect, useState } from "react";
import { EmptyState } from "@breakingweb/shared";
import { useSearchParams } from "react-router-dom";

import { EmailRow } from "../components/EmailRow";
import { useGmailLayout } from "../context";
import type { Email, EmailListResponse } from "../types";

const SEARCH_PAGE_SIZE = 100;

async function fetchSearchSnapshot(
  api: ReturnType<typeof useGmailLayout>["api"],
  query: string,
): Promise<EmailListResponse> {
  const firstPage = await api.search(query, { page: 1, page_size: SEARCH_PAGE_SIZE });
  if (firstPage.pages <= 1) {
    return firstPage;
  }

  const remainingPages = await Promise.all(
    Array.from({ length: firstPage.pages - 1 }, (_, index) =>
      api.search(query, {
        page: index + 2,
        page_size: SEARCH_PAGE_SIZE,
      }),
    ),
  );

  return {
    ...firstPage,
    items: [firstPage, ...remainingPages].flatMap((response) => response.items),
  };
}

export function SearchPage() {
  const { api, notify, refreshMailbox, summary } = useGmailLayout();
  const [searchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const searchNonce = searchParams.get("_t") ?? "";
  const [results, setResults] = useState<EmailListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const hasQuery = query.trim() !== "";

  useEffect(() => {
    if (!hasQuery) {
      setResults(null);
      return;
    }
    setIsLoading(true);
    fetchSearchSnapshot(api, query).then(setResults).finally(() => setIsLoading(false));
  }, [api, hasQuery, query, searchNonce]);

  const mutate = async (email: Email, fn: () => Promise<unknown>, toast: string) => {
    await fn();
    notify(toast, email.subject);
    if (hasQuery) {
      setResults(await fetchSearchSnapshot(api, query));
    }
    await refreshMailbox();
  };

  const hasResults = (results?.items ?? []).length > 0;

  return (
    <main className="gmail-page gmail-page--search" aria-label="Search">
      {isLoading ? (
        <section className="gmail-loading" aria-live="polite">Searching…</section>
      ) : null}

      {!isLoading && !hasQuery ? (
        <section className="wab-card gmail-search-panel">
          <div className="gmail-search-panel__tips" aria-label="Search tips">
            <span>from:finance@acme.com</span>
            <span>subject:budget</span>
            <span>has:attachment</span>
            <span>label:vip</span>
          </div>
        </section>
      ) : null}

      {!isLoading && hasQuery && !hasResults ? (
        <EmptyState
          title="No messages match this search"
          description={`No results for "${query}". Try different keywords, sender names, or filters like is:unread and label:VIP.`}
        />
      ) : null}

      <section className="gmail-email-list" aria-label="Search results" aria-live="polite">
        {(results?.items ?? []).map((email) => (
          <EmailRow
            key={email.id}
            email={email}
            labels={summary?.labels ?? []}
            onToggleStar={(entry) => mutate(entry, () => api.toggleStar(entry.id), "Updated star")}
            onArchive={(entry) => mutate(entry, () => api.archive(entry.id), "Archived thread")}
            onDelete={(entry) => mutate(entry, () => api.deleteEmail(entry.id), "Moved thread to trash")}
          />
        ))}
      </section>
    </main>
  );
}
