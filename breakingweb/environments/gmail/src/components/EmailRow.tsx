import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button, classNames, formatDateTime, preserveQueryParams } from "@breakingweb/shared";

import { IconStar, IconArchive, IconDelete, IconMoveToInbox } from "../icons";
import { LabelChip } from "./LabelChip";
import type { Email, Label } from "../types";

interface EmailRowProps {
  email: Email;
  labels: Label[];
  onToggleStar: (email: Email) => void;
  onArchive: (email: Email) => void;
  onDelete: (email: Email) => void;
  onRestore?: (email: Email) => void;
  currentLabel?: string;
}

export function EmailRow({ email, labels, onToggleStar, onArchive, onDelete, onRestore, currentLabel }: EmailRowProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const normalizedEmailLabels = new Set(email.labels.map((label) => label.toLowerCase()));
  const activeLabels = labels.filter(
    (label) => normalizedEmailLabels.has(label.id.toLowerCase()) || normalizedEmailLabels.has(label.name.toLowerCase()),
  );
  const returnPath = `${location.pathname}${location.search}`;
  const threadPath = preserveQueryParams(`/thread/${email.id}`, location.search);
  const unreadState = email.is_read ? "Read" : "Unread";
  const threadLabel = `${unreadState} thread from ${email.from_name}: ${email.subject || "(no subject)"}`;

  return (
    <article
      aria-label={threadLabel}
      className={classNames("gmail-email-row", !email.is_read && "gmail-email-row--unread")}
      onClick={() => navigate(threadPath, { state: { from: returnPath } })}
      style={{ cursor: "pointer" }}
    >
      <button
        type="button"
        className="gmail-email-row__star"
        aria-label={email.is_starred ? `Unstar ${email.subject}` : `Star ${email.subject}`}
        onClick={(e) => { e.stopPropagation(); onToggleStar(email); }}
        style={{ background: "none", border: "none", cursor: "pointer", padding: "0 4px", fontSize: "1rem", color: email.is_starred ? "#f4b400" : "#c4c7c5" }}
      >
        <IconStar filled={email.is_starred} />
      </button>

      <div className="gmail-email-row__main">
        <div className="gmail-email-row__header">
          <strong>{email.from_name}</strong>
          {email.thread_size && email.thread_size > 1 ? <span className="gmail-email-row__thread-count">({email.thread_size})</span> : null}
          {!email.is_read ? <span className="gmail-email-row__status">Unread</span> : null}
        </div>
        <Link
          to={threadPath}
          state={{ from: returnPath }}
          className="gmail-email-row__subject"
          aria-label={`Open ${email.is_read ? "read" : "unread"} thread ${email.subject}`}
        >
          <span>{email.subject || "(no subject)"}</span>
          <span className="gmail-email-row__preview">{email.snippet || email.body.slice(0, 100)}</span>
        </Link>
      </div>

      <div className="gmail-email-row__meta">
        {activeLabels.map((label) => (
          <LabelChip key={label.id} label={label} />
        ))}
        {email.attachments.length > 0 ? (
          <span className="gmail-email-row__attachment-count" aria-label={`${email.attachments.length} attachments`}>
            Attachment
          </span>
        ) : null}
      </div>

      <div className="gmail-email-row__actions">
        {onRestore && (currentLabel === "trash" || currentLabel === "archived") ? (
          <Button
            variant="ghost"
            aria-label={`Move to inbox ${email.subject}`}
            onClick={(e: { stopPropagation: () => void }) => { e.stopPropagation(); onRestore(email); }}
          >
            <IconMoveToInbox />
          </Button>
        ) : (
          <Button
            variant="ghost"
            aria-label={`Archive ${email.subject}`}
            onClick={(e: { stopPropagation: () => void }) => { e.stopPropagation(); onArchive(email); }}
          >
            <IconArchive />
          </Button>
        )}
        <Button
          variant="ghost"
          aria-label={currentLabel === "trash" ? `Delete permanently ${email.subject}` : `Delete ${email.subject}`}
          onClick={(e: { stopPropagation: () => void }) => { e.stopPropagation(); onDelete(email); }}
        >
          <IconDelete />
        </Button>
      </div>

      <time className="gmail-email-row__time" dateTime={email.timestamp}>
        {formatDateTime(email.timestamp)}
      </time>
    </article>
  );
}
