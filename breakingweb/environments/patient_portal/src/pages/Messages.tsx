import { useCallback, useEffect, useState } from "react";

import { usePatientPortal } from "../context";
import type { ClinicalMessage } from "../types";

const CATEGORIES = ["clinical", "billing", "scheduling", "rx_renewal"] as const;

export function MessagesPage() {
  const { api, providers, notify, refreshUnread } = usePatientPortal();
  const [messages, setMessages] = useState<ClinicalMessage[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [selectedThread, setSelectedThread] = useState<string | null>(null);
  const [threadMessages, setThreadMessages] = useState<ClinicalMessage[]>([]);
  const [replyBody, setReplyBody] = useState("");
  const [showCompose, setShowCompose] = useState(false);

  // Compose form state
  const [composeProviderId, setComposeProviderId] = useState("");
  const [composeCategory, setComposeCategory] = useState("clinical");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeUrgent, setComposeUrgent] = useState(false);

  const providerName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;

  const loadMessages = useCallback(async () => {
    try {
      const query: { category?: string } = {};
      if (categoryFilter) query.category = categoryFilter;
      const items = await api.listMessages(query);
      setMessages(items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()));
    } catch {
      // silently continue
    }
  }, [api, categoryFilter]);

  useEffect(() => { void loadMessages(); }, [loadMessages]);

  const openThread = async (threadId: string) => {
    setSelectedThread(threadId);
    setShowCompose(false);
    try {
      const items = await api.getThread(threadId);
      setThreadMessages(items.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()));
      // Mark all unread messages in this thread as read
      for (const msg of items) {
        if (!msg.is_read) {
          await api.markMessageRead(msg.id);
        }
      }
      void refreshUnread();
      void loadMessages();
    } catch {
      // silently continue
    }
  };

  const handleReply = async () => {
    if (!replyBody.trim() || threadMessages.length === 0) return;
    const lastMsg = threadMessages[threadMessages.length - 1];
    try {
      await api.replyToMessage(lastMsg.id, { body: replyBody });
      setReplyBody("");
      notify("Reply sent");
      void openThread(selectedThread!);
    } catch {
      notify("Failed to send reply");
    }
  };

  const handleCompose = async () => {
    if (!composeProviderId || !composeSubject.trim() || !composeBody.trim()) return;
    try {
      await api.sendMessage({
        provider_id: composeProviderId,
        subject: composeSubject,
        body: composeBody,
        category: composeCategory,
        is_urgent: composeUrgent,
      });
      notify("Message sent");
      setShowCompose(false);
      setComposeProviderId("");
      setComposeSubject("");
      setComposeBody("");
      setComposeUrgent(false);
      void loadMessages();
      void refreshUnread();
    } catch {
      notify("Failed to send message");
    }
  };

  // Group messages by thread for inbox display
  const threadMap = new Map<string, ClinicalMessage>();
  for (const msg of messages) {
    const existing = threadMap.get(msg.thread_id);
    if (!existing || new Date(msg.timestamp) > new Date(existing.timestamp)) {
      threadMap.set(msg.thread_id, msg);
    }
  }
  const threads = Array.from(threadMap.values());

  return (
    <div aria-label="Messages Page">
      <h2>Messages</h2>

      <div className="pp-messages-layout">
        {/* Inbox */}
        <div className="pp-messages-inbox">
          <div className="pp-messages-toolbar">
            <fieldset aria-label="Filter by Category">
              <legend className="pp-sr-only">Category Filter</legend>
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                aria-label="Filter messages by category"
              >
                <option value="">All Categories</option>
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>{cat.replace("_", " ")}</option>
                ))}
              </select>
            </fieldset>
            <button
              className="pp-btn pp-btn--primary"
              aria-label="Compose new message"
              onClick={() => { setShowCompose(true); setSelectedThread(null); }}
            >
              Compose
            </button>
          </div>

          <nav aria-label="Message Inbox">
            {threads.length === 0 ? (
              <p>No messages.</p>
            ) : (
              <ul className="pp-message-list">
                {threads.map((msg) => {
                  const isUnread = !msg.is_read && msg.from_type !== "patient";
                  return (
                    <li key={msg.thread_id}>
                      <button
                        className={`pp-message-item${selectedThread === msg.thread_id ? " pp-message-item--selected" : ""}${isUnread ? " pp-message-item--unread" : ""}`}
                        onClick={() => openThread(msg.thread_id)}
                        aria-label={`Thread: ${msg.subject} from ${providerName(msg.provider_id)}${isUnread ? " (unread)" : ""}`}
                      >
                        <span className="pp-message-item__subject">{msg.subject}</span>
                        <span className="pp-message-item__provider">{providerName(msg.provider_id)}</span>
                        <span className={`pp-category-badge pp-category-badge--${msg.category}`}>{msg.category.replace("_", " ")}</span>
                        <span className="pp-message-item__time">{new Date(msg.timestamp).toLocaleDateString()}</span>
                        {isUnread && <span className="pp-unread-dot" aria-label="unread" />}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </nav>
        </div>

        {/* Thread View */}
        {selectedThread && !showCompose && (
          <div className="pp-messages-thread" aria-label="Message Thread">
            <h3>{threadMessages[0]?.subject ?? "Thread"}</h3>
            {threadMessages.map((msg) => (
              <article
                key={msg.id}
                className={`pp-thread-message pp-thread-message--${msg.from_type}`}
                aria-label={`Message from ${msg.from_type === "patient" ? "you" : providerName(msg.provider_id)}`}
              >
                <div className="pp-thread-message__header">
                  <strong>{msg.from_type === "patient" ? "You" : providerName(msg.provider_id)}</strong>
                  <time>{new Date(msg.timestamp).toLocaleString()}</time>
                  {msg.is_urgent && <span className="pp-urgent-badge" aria-label="Urgent">Urgent</span>}
                </div>
                <div className="pp-thread-message__body">{msg.body}</div>
                {msg.linked_entity_id && (
                  <div className="pp-text--sm pp-text--muted" aria-label={`Linked ${msg.linked_entity_type ?? "entity"}: ${msg.linked_entity_id}`}>
                    Linked {msg.linked_entity_type ?? "entity"}: {msg.linked_entity_id}
                  </div>
                )}
              </article>
            ))}

            <div className="pp-reply-form" aria-label="Reply to message">
              <label htmlFor="reply-body">Reply</label>
              <textarea
                id="reply-body"
                value={replyBody}
                onChange={(e) => setReplyBody(e.target.value)}
                aria-label="Reply message body"
                placeholder="Type your reply..."
                rows={3}
              />
              <button
                className="pp-btn pp-btn--primary"
                aria-label="Send reply"
                onClick={handleReply}
                disabled={!replyBody.trim()}
              >
                Send Reply
              </button>
            </div>
          </div>
        )}

        {/* Compose */}
        {showCompose && (
          <div className="pp-messages-compose" aria-label="Compose new message">
            <h3>New Message</h3>

            <div className="pp-form-field">
              <label htmlFor="compose-provider">To (Provider)</label>
              <select
                id="compose-provider"
                value={composeProviderId}
                onChange={(e) => setComposeProviderId(e.target.value)}
                aria-label="Select provider"
              >
                <option value="">Select a provider...</option>
                {providers
                  .slice()
                  .sort((a, b) => a.department.localeCompare(b.department) || a.name.localeCompare(b.name))
                  .map((p) => (
                    <option key={p.id} value={p.id}>{p.name} - {p.specialty} ({p.department})</option>
                  ))}
              </select>
            </div>

            <div className="pp-form-field">
              <label>Category</label>
              <div className="pp-radio-group" role="radiogroup" aria-label="Message category">
                {CATEGORIES.map((cat) => (
                  <label key={cat} className="pp-radio-label">
                    <input
                      type="radio"
                      name="compose-category"
                      value={cat}
                      checked={composeCategory === cat}
                      onChange={() => setComposeCategory(cat)}
                      aria-label={cat.replace("_", " ")}
                    />
                    {cat.replace("_", " ")}
                  </label>
                ))}
              </div>
            </div>

            <div className="pp-form-field">
              <label htmlFor="compose-subject">Subject</label>
              <input
                id="compose-subject"
                type="text"
                value={composeSubject}
                onChange={(e) => setComposeSubject(e.target.value)}
                aria-label="Message subject"
                placeholder="Enter subject"
              />
            </div>

            <div className="pp-form-field">
              <label htmlFor="compose-body">Message</label>
              <textarea
                id="compose-body"
                value={composeBody}
                onChange={(e) => setComposeBody(e.target.value)}
                aria-label="Message body"
                placeholder="Type your message..."
                rows={5}
              />
            </div>

            <div className="pp-form-field">
              <label className="pp-checkbox-label">
                <input
                  type="checkbox"
                  checked={composeUrgent}
                  onChange={(e) => setComposeUrgent(e.target.checked)}
                  aria-label="Mark as urgent"
                />
                Mark as urgent
              </label>
            </div>

            <div className="pp-form-actions">
              <button
                className="pp-btn pp-btn--primary"
                aria-label="Send message"
                onClick={handleCompose}
                disabled={!composeProviderId || !composeSubject.trim() || !composeBody.trim()}
              >
                Send
              </button>
              <button
                className="pp-btn pp-btn--secondary"
                aria-label="Cancel compose"
                onClick={() => setShowCompose(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
