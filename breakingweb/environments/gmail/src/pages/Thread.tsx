import { useEffect, useRef, useState } from "react";
import { EmptyState, preserveQueryParams } from "@breakingweb/shared";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { IconArrowBack, IconArchive, IconDelete, IconForward, IconStar, IconLabel, IconMoveToInbox } from "../icons";
import { ComposeForm } from "../components/ComposeForm";
import { ThreadView } from "../components/ThreadView";
import { useGmailLayout } from "../context";
import type { ComposePayload, Email, Label, ThreadResponse } from "../types";

export function getThreadNextStarState(emails: Pick<Email, "is_starred">[]) {
  return !emails.every((email) => email.is_starred);
}

export function isThreadLabelApplied(
  emails: Pick<Email, "labels">[],
  labelName: string,
) {
  const labelLower = labelName.toLowerCase();
  return emails.every(
    (email) => email.labels.includes(labelName) || email.labels.includes(labelLower),
  );
}

function splitAddresses(value: string | null) {
  return (value ?? "").split(",").map((item) => item.trim()).filter(Boolean);
}

export function ThreadPage() {
  const { emailId } = useParams();
  const { api, notify, refreshMailbox, summary } = useGmailLayout();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [thread, setThread] = useState<ThreadResponse | null>(null);
  const [replyingTo, setReplyingTo] = useState<Email | null>(null);
  const [replyAllMode, setReplyAllMode] = useState(false);
  const [forwardingEmail, setForwardingEmail] = useState<Email | null>(null);
  const [labelMenuOpen, setLabelMenuOpen] = useState(false);
  const [creatingLabel, setCreatingLabel] = useState(false);
  const [newLabelName, setNewLabelName] = useState("");
  const labelMenuRef = useRef<HTMLDivElement>(null);
  const isReplayMode = searchParams.get("replay") === "1";
  const replayComposeMode = searchParams.get("replayCompose");
  const replayLabelMenuOpen = isReplayMode && searchParams.get("replayLabelMenu") === "1";
  const replayCreatingLabel = isReplayMode && searchParams.get("replayCreateLabel") === "1";
  const replayLabelName = searchParams.get("replayLabelName") ?? "";
  const displayLabelMenuOpen = isReplayMode ? replayLabelMenuOpen : labelMenuOpen;
  const displayCreatingLabel = isReplayMode ? replayCreatingLabel : creatingLabel;
  const displayNewLabelName = isReplayMode ? replayLabelName : newLabelName;

  const withErrorToast = async (fn: () => Promise<void>) => {
    try {
      await fn();
    } catch (err: unknown) {
      const detail = (err as { detail?: { error?: string } })?.detail;
      const message = detail?.error ?? "Action failed. Please retry.";
      notify("Error", message);
    }
  };

  useEffect(() => {
    if (!emailId) {
      return;
    }
    api.getThread(emailId).then(async (response) => {
      setThread(response);
      await refreshMailbox();
    });
  }, [api, emailId, refreshMailbox]);

  // Replay mode: keep reply/forward forms aligned with the replay step.
  useEffect(() => {
    if (!isReplayMode || !thread) {
      return;
    }

    const lastEmail = thread.thread[thread.thread.length - 1];
    if (!lastEmail) {
      return;
    }

    if (replayComposeMode === "reply" || replayComposeMode === "replyAll") {
      setReplyingTo(lastEmail);
      setReplyAllMode(replayComposeMode === "replyAll");
      setForwardingEmail(null);
      return;
    }

    if (replayComposeMode === "forward") {
      setReplyingTo(null);
      setReplyAllMode(false);
      setForwardingEmail(lastEmail);
      return;
    }

    setReplyingTo(null);
    setReplyAllMode(false);
    setForwardingEmail(null);
  }, [isReplayMode, replayComposeMode, thread]);

  // Close label menu on outside click
  useEffect(() => {
    if (!labelMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (labelMenuRef.current && !labelMenuRef.current.contains(e.target as Node)) {
        setLabelMenuOpen(false);
        setCreatingLabel(false);
        setNewLabelName("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [labelMenuOpen]);

  if (!emailId) {
    return (
      <EmptyState
        title="Thread not found"
        description="The selected email does not exist or the session was reset."
      />
    );
  }

  const sendReply = async (payload: ComposePayload) => {
    try {
      await api.sendMessage(payload);
      notify("Reply sent", payload.subject);
      setReplyingTo(null);
      setReplyAllMode(false);
      const response = await api.getThread(emailId);
      setThread(response);
      await refreshMailbox();
    } catch (err: unknown) {
      const detail = (err as { detail?: { error?: string } })?.detail;
      notify("Send failed", detail?.error ?? "Failed to send reply. Please retry.");
    }
  };

  const sendForward = async (payload: ComposePayload) => {
    if (!forwardingEmail) return;
    try {
      await api.forward(forwardingEmail.id, {
        to: payload.to,
        cc: payload.cc,
        bcc: payload.bcc,
        body: payload.body,
      });
      notify("Forwarded", forwardingEmail.subject);
      setForwardingEmail(null);
      const response = await api.getThread(emailId);
      setThread(response);
      await refreshMailbox();
    } catch (err: unknown) {
      const detail = (err as { detail?: { error?: string } })?.detail;
      notify("Forward failed", detail?.error ?? "Failed to forward email. Please retry.");
    }
  };

  const handleToggleStar = async () => {
    if (!thread) return;
    await withErrorToast(async () => {
      const nextStarred = getThreadNextStarState(thread.thread);
      for (const threadEmail of thread.thread) {
        await api.setStar(threadEmail.id, nextStarred);
      }
      const response = await api.getThread(emailId!);
      setThread(response);
      notify(nextStarred ? "Starred" : "Star removed");
      await refreshMailbox();
    });
  };

  const handleApplyLabel = async (label: Label) => {
    if (!thread) return;
    const action = isThreadLabelApplied(thread.thread, label.name) ? "remove" : "add";
    for (const threadEmail of thread.thread) {
      await api.applyEmailLabel(threadEmail.id, label.name, action);
    }
    const response = await api.getThread(emailId!);
    setThread(response);
    setLabelMenuOpen(false);
    notify(action === "add" ? `Label '${label.name}' added` : `Label '${label.name}' removed`);
    await refreshMailbox();
  };

  const availableLabels = (summary?.labels ?? []).filter(
    (l) => !l.system,
  );
  const returnPath =
    typeof (location.state as { from?: unknown } | null)?.from === "string"
      ? ((location.state as { from: string }).from)
      : preserveQueryParams("/inbox?label=inbox", location.search);

  return (
    <main className="gmail-page" aria-label="Thread view">
      {/* Gmail-style toolbar for thread view */}
      <div className="gmail-toolbar">
        <div className="gmail-toolbar__left">
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label="Back to inbox"
            onClick={() => navigate(returnPath)}
          >
            <IconArrowBack />
          </button>
          {thread?.email.labels.includes("trash") || (thread && !thread.email.labels.includes("inbox")) ? (
            <button
              type="button"
              className="gmail-toolbar__icon-btn"
              aria-label="Move to inbox"
              onClick={() => withErrorToast(async () => {
                if (thread) {
                  const isInTrash = thread.email.labels.includes("trash");
                  if (isInTrash) {
                    await api.restoreEmail(thread.email.id);
                  } else {
                    await api.applyEmailLabel(thread.email.id, "inbox", "add");
                  }
                  notify("Moved to inbox", thread.email.subject);
                  await refreshMailbox();
                  navigate(preserveQueryParams("/inbox?label=inbox", location.search));
                }
              })}
            >
              <IconMoveToInbox />
            </button>
          ) : (
            <button
              type="button"
              className="gmail-toolbar__icon-btn"
              aria-label="Archive this thread"
              onClick={() => withErrorToast(async () => {
                if (thread) {
                  const archivedId = thread.email.id;
                  await api.archive(archivedId);
                  notify("Conversation archived", thread.email.subject, async () => {
                    await api.applyEmailLabel(archivedId, "inbox", "add");
                    await refreshMailbox();
                  });
                  await refreshMailbox();
                  navigate(preserveQueryParams("/inbox?label=inbox", location.search));
                }
              })}
            >
              <IconArchive />
            </button>
          )}
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label={thread?.email.labels.includes("trash") ? "Delete this thread permanently" : "Delete this thread"}
            onClick={() => withErrorToast(async () => {
              if (thread) {
                const isInTrash = thread.email.labels.includes("trash");
                await api.deleteEmail(thread.email.id);
                notify(isInTrash ? "Permanently deleted" : "Moved to trash", thread.email.subject);
                await refreshMailbox();
                navigate(preserveQueryParams("/inbox?label=inbox", location.search));
              }
            })}
          >
            <IconDelete />
          </button>
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label={thread?.email.is_starred ? "Unstar this thread" : "Star this thread"}
            onClick={handleToggleStar}
          >
            <IconStar filled={thread?.email.is_starred ?? false} />
          </button>
          <div className="gmail-toolbar__label-menu-wrapper" ref={labelMenuRef}>
            <button
              type="button"
              className="gmail-toolbar__icon-btn"
              aria-label="Apply label to this thread"
              onClick={() => setLabelMenuOpen((prev) => !prev)}
            >
              <IconLabel />
            </button>
            {displayLabelMenuOpen && (
              <div className="gmail-label-menu" role="menu" aria-label="Label menu">
                {displayCreatingLabel ? (
                  <div className="gmail-label-menu__create-form">
                    <div className="gmail-label-menu__title">Create new label:</div>
                    <input
                      type="text"
                      className="gmail-label-menu__input"
                      aria-label="New label name"
                      value={displayNewLabelName}
                      onChange={(e) => setNewLabelName(e.target.value)}
                      autoFocus
                    />
                    <div className="gmail-label-menu__form-actions">
                      <button
                        type="button"
                        className="gmail-label-menu__form-btn gmail-label-menu__form-btn--create"
                        aria-label="Create label"
                        disabled={!displayNewLabelName.trim()}
                        onClick={async () => {
                          const name = displayNewLabelName.trim();
                          if (!name || !thread) return;
                          await api.createLabel({ name, color: "#1a73e8" });
                          // Apply to all emails in thread
                          for (const threadEmail of thread.thread) {
                            await api.applyEmailLabel(threadEmail.id, name, "add");
                          }
                          await refreshMailbox();
                          const response = await api.getThread(emailId!);
                          setThread(response);
                          setCreatingLabel(false);
                          setNewLabelName("");
                        }}
                      >
                        Create
                      </button>
                      <button
                        type="button"
                        className="gmail-label-menu__form-btn gmail-label-menu__form-btn--cancel"
                        aria-label="Cancel label creation"
                        onClick={() => {
                          setCreatingLabel(false);
                          setNewLabelName("");
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="gmail-label-menu__title">Label as:</div>
                    {availableLabels.map((label) => {
                      const isApplied = thread
                        ? isThreadLabelApplied(thread.thread, label.name)
                        : false;
                      return (
                        <button
                          key={label.id}
                          type="button"
                          role="menuitem"
                          className="gmail-label-menu__item"
                          aria-label={`${isApplied ? "Remove" : "Apply"} label ${label.name}`}
                          onClick={() => handleApplyLabel(label)}
                        >
                          <span className="gmail-label-menu__check">{isApplied ? "✓" : ""}</span>
                          <span className="gmail-label-menu__dot" style={{ backgroundColor: label.color }} />
                          {label.name}
                        </button>
                      );
                    })}
                    <div className="gmail-label-menu__separator" />
                    <button
                      type="button"
                      role="menuitem"
                      className="gmail-label-menu__item gmail-label-menu__item--create"
                      aria-label="Create new label"
                      onClick={() => setCreatingLabel(true)}
                    >
                      + Create new
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
          <button
            type="button"
            className="gmail-toolbar__icon-btn"
            aria-label="Forward this thread"
            onClick={() => {
              if (thread) {
                setForwardingEmail(thread.thread[thread.thread.length - 1]);
              }
            }}
          >
            <IconForward />
          </button>
        </div>
        <div className="gmail-toolbar__right" />
      </div>

      {thread ? (
        <ThreadView
          thread={thread.thread}
          onReply={setReplyingTo}
          onReplyAll={(email) => {
            setReplyingTo(email);
            setReplyAllMode(true);
          }}
        />
      ) : (
        <section className="gmail-loading">Loading thread…</section>
      )}

      {replyingTo ? (
        <ComposeForm
          title={replyAllMode ? "Reply All" : "Reply"}
          submitLabel="Send reply"
          autoScrollIntoView
          initialValue={{
            to: splitAddresses(searchParams.get("replayTo")).length > 0
              ? splitAddresses(searchParams.get("replayTo"))
              : [replyingTo.from_addr],
            cc: searchParams.has("replayCc")
              ? splitAddresses(searchParams.get("replayCc"))
              : replyAllMode
                ? [...replyingTo.to, ...replyingTo.cc].filter(
                  (addr) => addr !== "avery.quinn@thornton.com" && addr !== replyingTo.from_addr,
                )
                : [],
            bcc: splitAddresses(searchParams.get("replayBcc")),
            subject: searchParams.get("replaySubject")
              ?? (replyingTo.subject.startsWith("Re:") ? replyingTo.subject : `Re: ${replyingTo.subject}`),
            body: searchParams.has("replayBody")
              ? (searchParams.get("replayBody") ?? "")
              : `\n\nOn ${new Date(replyingTo.timestamp).toLocaleString()}, ${replyingTo.from_name} wrote:\n${replyingTo.body}`,
            attachments: splitAddresses(searchParams.get("replayAttachments")),
            reply_to: replyingTo.id,
            thread_id: replyingTo.thread_id,
          }}
          forceShowCc={searchParams.get("replayShowCc") === "1"}
          forceShowBcc={searchParams.get("replayShowBcc") === "1"}
          onCancel={() => {
            setReplyingTo(null);
            setReplyAllMode(false);
          }}
          onSubmit={sendReply}
        />
      ) : null}

      {forwardingEmail ? (
        <ComposeForm
          title="Forward"
          submitLabel="Forward"
          autoScrollIntoView
          initialValue={{
            to: splitAddresses(searchParams.get("replayTo")),
            cc: splitAddresses(searchParams.get("replayCc")),
            bcc: splitAddresses(searchParams.get("replayBcc")),
            subject: searchParams.get("replaySubject")
              ?? (forwardingEmail.subject.startsWith("Fwd:") ? forwardingEmail.subject : `Fwd: ${forwardingEmail.subject}`),
            body: searchParams.has("replayBody") ? (searchParams.get("replayBody") ?? "") : "",
            attachments: splitAddresses(searchParams.get("replayAttachments")),
          }}
          forceShowCc={searchParams.get("replayShowCc") === "1"}
          forceShowBcc={searchParams.get("replayShowBcc") === "1"}
          onCancel={() => setForwardingEmail(null)}
          onSubmit={sendForward}
        />
      ) : null}
    </main>
  );
}
