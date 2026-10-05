import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRedditLayout } from "../context";
import type { Message } from "../types";
import { timeAgo } from "../utils";

export function MessagesPage() {
  const { api, notify, refreshProfile } = useRedditLayout();
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const folder = params.get("folder") ?? "inbox";

  const [messages, setMessages] = useState<Message[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [composing, setComposing] = useState(false);
  const [replyingTo, setReplyingTo] = useState<Message | null>(null);
  const [toUser, setToUser] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  // Refs let us read live DOM values even when an agent sets input.value
  // programmatically without dispatching a React-visible input event.
  const toUserRef = useRef<HTMLInputElement>(null);
  const subjectRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const replyBodyRef = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listMessages(folder);
      setMessages(data.items);
      setUnreadCount(data.unread_count);
    } catch {
      notify("Failed to load messages");
    } finally {
      setLoading(false);
    }
  }, [api, folder, notify]);

  useEffect(() => { void load(); }, [load]);

  const handleMarkRead = async (messageId: string) => {
    try {
      const { message } = await api.markMessageRead(messageId);
      setMessages((prev) => prev.map((m) => (m.id === messageId ? message : m)));
      setUnreadCount((prev) => Math.max(0, prev - 1));
      void refreshProfile();
    } catch { notify("Failed to mark as read"); }
  };

  const handleMarkAllRead = async () => {
    try {
      const { marked } = await api.markAllMessagesRead();
      setMessages((prev) => prev.map((m) => ({ ...m, is_read: true })));
      setUnreadCount(0);
      notify(`Marked ${marked} messages as read`);
      void refreshProfile();
    } catch { notify("Failed to mark all as read"); }
  };

  const handleStartReply = (msg: Message) => {
    setReplyingTo(msg);
    setComposing(false);
    setToUser(msg.from_user);
    setSubject(msg.subject.startsWith("Re: ") ? msg.subject : `Re: ${msg.subject}`);
    setBody("");
  };

  const handleCancelReply = () => {
    setReplyingTo(null);
    setToUser("");
    setSubject("");
    setBody("");
  };

  const handleSend = async () => {
    const to = (toUserRef.current?.value ?? toUser).trim();
    const subj = (subjectRef.current?.value ?? subject).trim();
    const replyDomValue = replyingTo ? replyBodyRef.current?.value : undefined;
    const bdy = (replyDomValue ?? bodyRef.current?.value ?? body).trim();
    if (!to || !subj || !bdy) return;
    setSendError(null);
    try {
      await api.sendMessage({
        to_user: to,
        subject: subj,
        body: bdy,
        ...(replyingTo ? { parent_id: replyingTo.id } : {}),
      });
      setComposing(false);
      setReplyingTo(null);
      setToUser("");
      setSubject("");
      setBody("");
      if (toUserRef.current) toUserRef.current.value = "";
      if (subjectRef.current) subjectRef.current.value = "";
      if (bodyRef.current) bodyRef.current.value = "";
      if (replyBodyRef.current) replyBodyRef.current.value = "";
      notify("Message sent!");
      if (folder === "sent") void load();
    } catch (err) {
      const status = (err as { status?: number } | null)?.status;
      const banner = status
        ? `Failed to send message (HTTP ${status}). Your draft is still in the form — click Send again to retry.`
        : "Failed to send message. Your draft is still in the form — click Send again to retry.";
      setSendError(banner);
      notify("Failed to send message");
    }
  };

  const handleDelete = async (messageId: string) => {
    try {
      await api.deleteMessage(messageId);
      setMessages((prev) => prev.filter((m) => m.id !== messageId));
      notify("Message deleted");
    } catch { notify("Failed to delete"); }
  };

  return (
    <div className="messages-page">
      <div className="messages-header">
        <h1>Messages</h1>
        <div className="messages-header__actions">
          {unreadCount > 0 && (
            <Button variant="secondary" onClick={handleMarkAllRead} aria-label="Mark all messages as read">
              Mark all read ({unreadCount})
            </Button>
          )}
          <Button variant="primary" onClick={() => { setComposing(!composing); setReplyingTo(null); setToUser(""); setSubject(""); setBody(""); }} aria-label="Compose new message">
            {composing ? "Cancel" : "New Message"}
          </Button>
        </div>
      </div>

      <div className="messages-tabs" role="tablist">
        <button role="tab" aria-selected={folder === "inbox"} className={`messages-tab ${folder === "inbox" ? "messages-tab--active" : ""}`} onClick={() => navigate(preserveQueryParams("/messages?folder=inbox", location.search))}>
          Inbox {unreadCount > 0 && <span className="messages-tab__badge">{unreadCount}</span>}
        </button>
        <button role="tab" aria-selected={folder === "sent"} className={`messages-tab ${folder === "sent" ? "messages-tab--active" : ""}`} onClick={() => navigate(preserveQueryParams("/messages?folder=sent", location.search))}>
          Sent
        </button>
      </div>

      {composing && (
        <div className="messages-compose" aria-label="Compose message">
          {sendError && (
            <div className="messages-compose__error" role="alert" aria-live="assertive">
              {sendError}
            </div>
          )}
          <input ref={toUserRef} type="text" value={toUser} onChange={(e) => setToUser(e.target.value)} placeholder="To: u/username" className="messages-compose__input" aria-label="Recipient username" />
          <input ref={subjectRef} type="text" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject" className="messages-compose__input" aria-label="Message subject" />
          <textarea ref={bodyRef} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Message" className="messages-compose__textarea" rows={4} aria-label="Message body" />
          <Button variant="primary" onClick={handleSend} aria-label="Send message">Send</Button>
        </div>
      )}

      {loading ? (
        <div className="messages-loading">Loading...</div>
      ) : messages.length === 0 ? (
        <div className="messages-empty">No messages in {folder}</div>
      ) : (
        <div className="messages-list">
          {messages.map((msg) => (
            <div key={msg.id} className={`message-item ${!msg.is_read ? "message-item--unread" : ""}`}>
              <div className="message-item__header">
                <span className="message-item__from">
                  {folder === "sent" ? `To: u/${msg.to_user}` : `From: u/${msg.from_user}`}
                </span>
                <span className="message-item__time">{timeAgo(msg.created_at)}</span>
              </div>
              <h3 className="message-item__subject">{msg.subject}</h3>
              <p className="message-item__body">{msg.body}</p>
              <div className="message-item__actions">
                {folder === "inbox" && (
                  <button className="message-action" onClick={() => handleStartReply(msg)} aria-label="Reply to message">Reply</button>
                )}
                {!msg.is_read && folder === "inbox" && (
                  <button className="message-action" onClick={() => handleMarkRead(msg.id)} aria-label="Mark as read">Mark read</button>
                )}
                <button className="message-action message-action--delete" onClick={() => handleDelete(msg.id)} aria-label="Delete message">Delete</button>
              </div>
              {replyingTo?.id === msg.id && (
                <div className="message-reply-form" aria-label="Reply to message">
                  {sendError && (
                    <div className="messages-compose__error" role="alert" aria-live="assertive">
                      {sendError}
                    </div>
                  )}
                  <textarea ref={replyBodyRef} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write your reply..." className="messages-compose__textarea" rows={3} aria-label="Reply body" />
                  <div className="message-reply-form__actions">
                    <button className="message-action" onClick={handleCancelReply}>Cancel</button>
                    <Button variant="primary" onClick={handleSend} aria-label="Send reply">Send Reply</Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
