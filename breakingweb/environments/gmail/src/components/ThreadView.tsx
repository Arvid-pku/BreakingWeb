import { useEffect, useState } from "react";
import { Avatar, Badge, Button } from "@breakingweb/shared";
import { formatDateTime } from "@breakingweb/shared";

import { IconReply, IconReplyAll, IconCollapse } from "../icons";
import { AttachmentPreview } from "./AttachmentPreview";
import type { Email } from "../types";

interface ThreadViewProps {
  thread: Email[];
  onReply: (email: Email) => void;
  onReplyAll: (email: Email) => void;
}

function ExpandableBulletList({ items }: { items: string[] }) {
  const previewCount = 2;
  const [expanded, setExpanded] = useState(true);
  const visibleItems = expanded ? items : items.slice(0, previewCount);
  const remainingCount = items.length - previewCount;

  return (
    <>
      <ul className="gmail-thread__body-list">
        {visibleItems.map((line, lineIndex) => (
          <li key={`body-list-item-${lineIndex}`}>{line.slice(2)}</li>
        ))}
      </ul>
      {items.length > previewCount ? (
        <button
          type="button"
          className="gmail-thread__inline-toggle"
          aria-label={expanded ? "Collapse list details" : `Show ${remainingCount} more list item${remainingCount === 1 ? "" : "s"}`}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "Show less" : `Show ${remainingCount} more`}
        </button>
      ) : null}
    </>
  );
}

function EmailBody({ body }: { body: string }) {
  const sections = body
    .split(/\n{2,}/)
    .map((section) => section.trim())
    .filter(Boolean);

  return sections.map((section, index) => {
    const lines = section
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

    if (lines.length > 0 && lines.every((line) => line.startsWith("- "))) {
      return <ExpandableBulletList key={`body-list-${index}`} items={lines} />;
    }

    if (lines.length === 1) {
      return <p key={`body-paragraph-${index}`}>{lines[0]}</p>;
    }

    return (
      <p key={`body-paragraph-${index}`}>
        {lines.map((line, lineIndex) => (
          <span key={`body-line-${index}-${lineIndex}`}>
            {line}
            {lineIndex < lines.length - 1 ? <br /> : null}
          </span>
        ))}
      </p>
    );
  });
}

function CollapsedMessage({ email, onClick }: { email: Email; onClick: () => void }) {
  return (
    <div
      className="gmail-thread__message gmail-thread__message--collapsed"
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Expand message from ${email.from_name}`}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onClick(); }}
    >
      <div className="gmail-thread__collapsed-line">
        <Avatar name={email.from_name} size={32} color="#5f6368" />
        <strong>{email.from_name}</strong>
        <span className="gmail-thread__collapsed-snippet">{email.body.slice(0, 40)}</span>
        <time dateTime={email.timestamp} style={{ marginLeft: "auto", flexShrink: 0, fontSize: "0.75rem" }}>
          {formatDateTime(email.timestamp)}
        </time>
      </div>
    </div>
  );
}

function ExpandedMessage({ email, onReply, onReplyAll, onCollapse }: { email: Email; onReply: (email: Email) => void; onReplyAll: (email: Email) => void; onCollapse?: () => void }) {
  return (
    <article className="gmail-thread__message">
      <header className="gmail-thread__header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Avatar name={email.from_name} size={40} color={email.is_starred ? "#f4b400" : "#5f6368"} />
          <div>
            <div className="gmail-thread__sender-line">
              <strong>{email.from_name}</strong>
              <span style={{ color: "var(--color-text-muted)", fontSize: "0.8125rem" }}>&lt;{email.from_addr}&gt;</span>
            </div>
            <div className="gmail-thread__recipient-line">
              to {email.to.join(", ")}
              {email.cc.length > 0 ? `, cc: ${email.cc.join(", ")}` : ""}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {email.is_starred ? <Badge tone="primary">Starred</Badge> : null}
          <time dateTime={email.timestamp} style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
            {formatDateTime(email.timestamp)}
          </time>
          <Button variant="ghost" aria-label={`Reply to ${email.subject}`} onClick={() => onReply(email)}>
            <IconReply /> Reply
          </Button>
          <Button variant="ghost" aria-label={`Reply all to ${email.subject}`} onClick={() => onReplyAll(email)}>
            <IconReplyAll /> Reply All
          </Button>
          {onCollapse ? (
            <Button variant="ghost" aria-label="Collapse message" onClick={onCollapse}>
              <IconCollapse />
            </Button>
          ) : null}
        </div>
      </header>
      <div className="gmail-thread__body"><EmailBody body={email.body} /></div>
      {email.attachments.length > 0 ? (
        <div className="gmail-thread__attachments">
          {email.attachments.map((attachment) => (
            <AttachmentPreview key={attachment.id} attachment={attachment} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function ThreadView({ thread, onReply, onReplyAll }: ThreadViewProps) {
  // By default, only the last message is expanded; earlier ones are collapsed
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
    if (thread.length === 0) return new Set<string>();
    return new Set([thread[thread.length - 1].id]);
  });

  useEffect(() => {
    if (thread.length === 0) {
      setExpandedIds(new Set<string>());
    } else {
      setExpandedIds(new Set([thread[thread.length - 1].id]));
    }
  }, [thread]);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <section className="gmail-thread" aria-label="Email thread">
      {thread.length > 0 && (
        <h2 className="gmail-thread__subject">{thread[0].subject || "(no subject)"}</h2>
      )}
      {thread.length > 1 && (
        <button
          type="button"
          className="gmail-thread__message gmail-thread__message--collapsed"
          style={{ textAlign: "center", color: "var(--color-text-muted)", fontSize: "0.8125rem" }}
          onClick={() => {
            const allIds = new Set(thread.map((e) => e.id));
            setExpandedIds(allIds);
          }}
          aria-label={`Expand all ${thread.length} messages`}
        >
          {thread.length} messages in thread
        </button>
      )}
      {thread.map((email, index) => {
        const isLast = index === thread.length - 1;
        const isExpanded = expandedIds.has(email.id);

        if (!isExpanded && !isLast) {
          return (
            <CollapsedMessage
              key={email.id}
              email={email}
              onClick={() => toggleExpand(email.id)}
            />
          );
        }

        return (
          <ExpandedMessage
            key={email.id}
            email={email}
            onReply={onReply}
            onReplyAll={onReplyAll}
            onCollapse={!isLast ? () => toggleExpand(email.id) : undefined}
          />
        );
      })}
    </section>
  );
}
