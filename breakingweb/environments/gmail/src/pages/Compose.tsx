import { preserveQueryParams } from "@breakingweb/shared";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { ComposeForm } from "../components/ComposeForm";
import { useGmailLayout } from "../context";
import type { ComposePayload } from "../types";

function splitAddresses(value: string | null) {
  return (value ?? "").split(",").map((item) => item.trim()).filter(Boolean);
}

export function ComposePage() {
  const { api, notify, refreshMailbox } = useGmailLayout();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const isReplayMode = searchParams.get("replay") === "1";
  const hasReplayDraft =
    isReplayMode &&
    [
      "replayTo",
      "replayCc",
      "replayBcc",
      "replaySubject",
      "replayBody",
      "replayAttachments",
      "replayShowCc",
      "replayShowBcc",
    ].some((key) => searchParams.has(key));

  const initialValue: Partial<ComposePayload> = hasReplayDraft || isReplayMode
    ? {
        to: splitAddresses(searchParams.get("replayTo")),
        cc: splitAddresses(searchParams.get("replayCc")),
        bcc: splitAddresses(searchParams.get("replayBcc")),
        subject: searchParams.get("replaySubject") ?? "",
        body: searchParams.get("replayBody") ?? "",
        attachments: splitAddresses(searchParams.get("replayAttachments")),
      } satisfies Partial<ComposePayload>
    : (location.state ?? {}) as Partial<ComposePayload>;

  return (
    <main className="gmail-page" aria-label="Compose message">
      <ComposeForm
        initialValue={initialValue}
        forceShowCc={searchParams.get("replayShowCc") === "1"}
        forceShowBcc={searchParams.get("replayShowBcc") === "1"}
        onCancel={() => navigate(-1)}
        onSubmit={async (payload) => {
          try {
            await api.sendMessage(payload);
            notify("Message sent", payload.subject);
            await refreshMailbox();
            navigate(preserveQueryParams("/inbox?label=sent", location.search));
          } catch (err: unknown) {
            const detail = (err as { detail?: { error?: string } })?.detail;
            const message = detail?.error ?? "Failed to send message. Please retry.";
            notify("Send failed", message);
          }
        }}
      />
    </main>
  );
}
