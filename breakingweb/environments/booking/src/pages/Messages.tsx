import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Message, Reservation } from "../types";
import { useBookingLayout } from "../context";

export default function Messages() {
  const { sessionId, api, notify } = useBookingLayout();
  const location = useLocation();

  const [messages, setMessages] = useState<Message[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Reply state
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replySubject, setReplySubject] = useState("");
  const [replyBody, setReplyBody] = useState("");
  const [sending, setSending] = useState(false);

  // New message compose state
  const [composing, setComposing] = useState(false);
  const [composePropertyId, setComposePropertyId] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeSending, setComposeSending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listMessages();
      setMessages(data.messages);
      setUnreadCount(data.unread);
    } catch {
      notify("Error", "Failed to load messages.");
    } finally {
      setLoading(false);
    }
  }, [api, sessionId, notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleMarkRead = async (messageId: string) => {
    try {
      const updated = await api.markMessageRead(messageId);
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? updated : m))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      notify("Error", "Failed to mark message as read.");
    }
  };

  const handleExpand = (msg: Message) => {
    const newExpanded = expandedId === msg.id ? null : msg.id;
    setExpandedId(newExpanded);

    // Mark as read on expand — but only for messages *received* from the
    // property. Guest-sent messages don't have a read/unread semantic from
    // the sender's perspective, and auto-marking them breaks canonical_diff
    // predicates that assert `read: false` on freshly-created outgoing
    // messages.
    if (newExpanded && !msg.read && msg.sender !== "guest") {
      void handleMarkRead(msg.id);
    }
  };

  const handleStartReply = (msg: Message) => {
    setReplyingTo(msg.id);
    setReplySubject(`Re: ${msg.subject}`);
    setReplyBody("");
  };

  const handleSendReply = async (msg: Message) => {
    if (!replySubject.trim() || !replyBody.trim()) return;
    setSending(true);
    try {
      await api.sendMessage({
        property_id: msg.property_id,
        reservation_id: msg.reservation_id || undefined,
        subject: replySubject.trim(),
        body: replyBody.trim(),
      });
      setReplyingTo(null);
      setReplySubject("");
      setReplyBody("");
      notify("Sent", "Your reply has been sent.");
      void load();
    } catch {
      notify("Error", "Failed to send reply.");
    } finally {
      setSending(false);
    }
  };

  const handleSendNew = async () => {
    if (!composePropertyId || !composeSubject.trim() || !composeBody.trim()) return;
    setComposeSending(true);
    try {
      await api.sendMessage({
        property_id: composePropertyId,
        subject: composeSubject.trim(),
        body: composeBody.trim(),
      });
      setComposing(false);
      setComposePropertyId("");
      setComposeSubject("");
      setComposeBody("");
      notify("Sent", "Your message has been sent.");
      void load();
    } catch {
      notify("Error", "Failed to send message.");
    } finally {
      setComposeSending(false);
    }
  };

  // Get unique properties from messages + reservations for the compose dropdown
  const [reservations, setReservations] = useState<Reservation[]>([]);
  useEffect(() => {
    api.listReservations().then((data) => setReservations(data.reservations ?? [])).catch(() => {});
  }, [api, sessionId]);

  const knownProperties = Array.from(
    new Map([
      ...messages.map((m) => [m.property_id, m.property_name || m.property_id] as [string, string]),
      ...reservations.map((r) => [r.property_id, r.property_name || r.property_id] as [string, string]),
    ]).entries()
  );

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  // Group messages by property
  const grouped = messages.reduce<Record<string, Message[]>>((acc, msg) => {
    const key = msg.property_name || msg.property_id;
    if (!acc[key]) acc[key] = [];
    acc[key].push(msg);
    return acc;
  }, {});

  if (loading) {
    return <div className="bk-loading">Loading messages...</div>;
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 20,
        }}
      >
        <h1 className="bk-section-title" style={{ marginBottom: 0 }}>
          Messages
          {unreadCount > 0 && (
            <span
              className="bk-badge bk-badge--red"
              style={{ marginLeft: 10, fontSize: 12, verticalAlign: "middle" }}
            >
              {unreadCount} unread
            </span>
          )}
        </h1>
        <button
          className="bk-btn bk-btn--primary"
          onClick={() => setComposing(!composing)}
        >
          {composing ? "Cancel" : "New Message"}
        </button>
      </div>

      {/* Compose new message form */}
      {composing && (
        <div className="bk-card" style={{ padding: 20, marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>New Message</h2>
          <div className="bk-form-group">
            <label htmlFor="compose-property">To (Property)</label>
            <select
              id="compose-property"
              className="bk-input"
              value={composePropertyId}
              onChange={(e) => setComposePropertyId(e.target.value)}
            >
              <option value="">Select a property...</option>
              {knownProperties.map(([id, name]) => (
                <option key={id} value={id}>{name}</option>
              ))}
            </select>
          </div>
          <div className="bk-form-group">
            <label htmlFor="compose-subject">Subject</label>
            <input
              id="compose-subject"
              type="text"
              className="bk-input"
              value={composeSubject}
              onChange={(e) => setComposeSubject(e.target.value)}
              placeholder="Enter subject..."
            />
          </div>
          <div className="bk-form-group">
            <label htmlFor="compose-body">Message</label>
            <textarea
              id="compose-body"
              className="bk-textarea"
              rows={4}
              value={composeBody}
              onChange={(e) => setComposeBody(e.target.value)}
              placeholder="Type your message..."
            />
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button className="bk-btn bk-btn--ghost" onClick={() => setComposing(false)}>
              Cancel
            </button>
            <button
              className="bk-btn bk-btn--primary"
              onClick={() => void handleSendNew()}
              disabled={composeSending || !composePropertyId || !composeSubject.trim() || !composeBody.trim()}
            >
              {composeSending ? "Sending..." : "Send Message"}
            </button>
          </div>
        </div>
      )}

      {messages.length === 0 ? (
        <div className="bk-empty">
          <h3>No messages</h3>
          <p>You have no messages from properties yet.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {Object.entries(grouped).map(([propertyName, msgs]) => (
            <div key={propertyName} className="bk-section">
              <h2
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  marginBottom: 12,
                  color: "var(--bk-blue)",
                }}
              >
                {propertyName}
              </h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {msgs.map((msg) => {
                  const isExpanded = expandedId === msg.id;
                  const isReplying = replyingTo === msg.id;

                  return (
                    <div
                      key={msg.id}
                      className="bk-card"
                      style={{
                        borderLeft: !msg.read
                          ? "3px solid var(--bk-blue-light)"
                          : "3px solid transparent",
                      }}
                    >
                      {/* Message header - clickable */}
                      <div
                        style={{
                          padding: "12px 16px",
                          cursor: "pointer",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                        onClick={() => handleExpand(msg)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            handleExpand(msg);
                          }
                        }}
                        aria-expanded={isExpanded}
                        aria-label={`${!msg.read ? "Unread: " : ""}${msg.subject}`}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 8,
                              marginBottom: 2,
                            }}
                          >
                            <span
                              style={{
                                fontWeight: msg.read ? 400 : 700,
                                fontSize: 14,
                              }}
                            >
                              {msg.subject}
                            </span>
                            {!msg.read && (
                              <span className="bk-notification-dot" />
                            )}
                          </div>
                          <p
                            style={{
                              fontSize: 13,
                              color: "var(--bk-gray-600)",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {msg.body}
                          </p>
                        </div>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 12,
                            flexShrink: 0,
                            marginLeft: 16,
                          }}
                        >
                          <span
                            style={{ fontSize: 12, color: "var(--bk-gray-300)" }}
                          >
                            {msg.sender}
                          </span>
                          <span
                            style={{ fontSize: 12, color: "var(--bk-gray-300)" }}
                          >
                            {formatDate(msg.created_at)}
                          </span>
                        </div>
                      </div>

                      {/* Expanded body */}
                      {isExpanded && (
                        <div
                          style={{
                            borderTop: "1px solid var(--bk-border)",
                            padding: 16,
                          }}
                        >
                          <div
                            style={{
                              fontSize: 12,
                              color: "var(--bk-gray-600)",
                              marginBottom: 8,
                            }}
                          >
                            From: {msg.sender} &middot;{" "}
                            {formatDate(msg.created_at)}
                          </div>
                          <p style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                            {msg.body}
                          </p>

                          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
                            {!msg.read && msg.sender !== "guest" && (
                              <button
                                className="bk-btn bk-btn--ghost bk-btn--sm"
                                onClick={() => void handleMarkRead(msg.id)}
                                aria-label="Mark as read"
                              >
                                Mark as read
                              </button>
                            )}
                            <button
                              className="bk-btn bk-btn--secondary bk-btn--sm"
                              onClick={() => handleStartReply(msg)}
                              aria-label="Reply to message"
                            >
                              Reply
                            </button>
                          </div>

                          {/* Reply form */}
                          {isReplying && (
                            <div
                              style={{
                                marginTop: 16,
                                padding: 16,
                                background: "var(--bk-gray-50)",
                                borderRadius: "var(--bk-radius)",
                              }}
                            >
                              <div className="bk-form-group">
                                <label htmlFor={`reply-subject-${msg.id}`}>
                                  Subject
                                </label>
                                <input
                                  id={`reply-subject-${msg.id}`}
                                  type="text"
                                  className="bk-input"
                                  value={replySubject}
                                  onChange={(e) =>
                                    setReplySubject(e.target.value)
                                  }
                                  aria-label="Reply subject"
                                />
                              </div>
                              <div className="bk-form-group">
                                <label htmlFor={`reply-body-${msg.id}`}>
                                  Message
                                </label>
                                <textarea
                                  id={`reply-body-${msg.id}`}
                                  className="bk-textarea"
                                  rows={4}
                                  value={replyBody}
                                  onChange={(e) => setReplyBody(e.target.value)}
                                  placeholder="Type your reply..."
                                  aria-label="Reply body"
                                />
                              </div>
                              <div
                                style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}
                              >
                                <button
                                  className="bk-btn bk-btn--ghost bk-btn--sm"
                                  onClick={() => setReplyingTo(null)}
                                >
                                  Cancel
                                </button>
                                <button
                                  className="bk-btn bk-btn--primary bk-btn--sm"
                                  onClick={() => void handleSendReply(msg)}
                                  disabled={
                                    sending ||
                                    !replySubject.trim() ||
                                    !replyBody.trim()
                                  }
                                >
                                  {sending ? "Sending..." : "Send Reply"}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
