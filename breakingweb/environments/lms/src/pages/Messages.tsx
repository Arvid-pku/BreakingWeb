import { useCallback, useEffect, useState } from "react";
import { useLmsLayout } from "../context";
import type { SentMessage } from "../types";

interface Recipient {
  label: string;
  value: string;
}

export function MessagesPage() {
  const { api, student, notify } = useLmsLayout();
  const [messages, setMessages] = useState<SentMessage[]>([]);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [selectedMsg, setSelectedMsg] = useState<SentMessage | null>(null);

  // Compose state
  const [showCompose, setShowCompose] = useState(false);
  const [composeTo, setComposeTo] = useState("");
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");

  const loadMessages = useCallback(async () => {
    try {
      const data = await api.listMessages();
      setMessages(data);
    } catch {
      // silently continue
    }
  }, [api]);

  const loadRecipients = useCallback(async () => {
    try {
      const courses = await api.listCourses();
      const seen = new Set<string>();
      const recips: Recipient[] = [];

      // Add advisor
      if (student?.advisor_name) {
        recips.push({ label: `${student.advisor_name} (Advisor)`, value: student.advisor_name });
        seen.add(student.advisor_name);
      }

      // Add instructors from enrolled courses
      for (const c of courses) {
        if (!seen.has(c.instructor_name)) {
          recips.push({
            label: `${c.instructor_name} (${c.course_code} Instructor)`,
            value: c.instructor_name,
          });
          seen.add(c.instructor_name);
        }
      }
      setRecipients(recips);
    } catch {
      // silently continue
    }
  }, [api, student]);

  useEffect(() => {
    void loadMessages();
    void loadRecipients();
  }, [loadMessages, loadRecipients]);

  const handleSend = async () => {
    if (!composeTo || !composeSubject.trim() || !composeBody.trim()) return;
    try {
      await api.sendMessage(composeTo, composeSubject, composeBody);
      notify("Message sent");
      setShowCompose(false);
      setComposeTo("");
      setComposeSubject("");
      setComposeBody("");
      void loadMessages();
    } catch {
      notify("Failed to send message");
    }
  };

  return (
    <div aria-label="Messages Page">
      <h2>Messages</h2>

      <div className="lms-messages-layout">
        {/* Sidebar: sent messages list */}
        <div className="lms-messages-sidebar">
          <div className="lms-messages-toolbar">
            <button
              className="lms-btn lms-btn--primary"
              aria-label="Compose new message"
              onClick={() => {
                setShowCompose(true);
                setSelectedMsg(null);
              }}
            >
              Compose
            </button>
          </div>

          <nav aria-label="Sent Messages">
            {messages.length === 0 ? (
              <p className="lms-messages-empty">No messages sent yet.</p>
            ) : (
              <ul className="lms-message-list">
                {messages.map((msg, idx) => (
                  <li key={`${msg.sent_at}-${idx}`}>
                    <button
                      className={`lms-message-item${selectedMsg === msg ? " lms-message-item--selected" : ""}`}
                      onClick={() => {
                        setSelectedMsg(msg);
                        setShowCompose(false);
                      }}
                      aria-label={`Message to ${msg.to}: ${msg.subject}`}
                    >
                      <span className="lms-message-item__to">To: {msg.to}</span>
                      <span className="lms-message-item__subject">{msg.subject}</span>
                      <span className="lms-message-item__time">
                        {new Date(msg.sent_at).toLocaleDateString()}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </nav>
        </div>

        {/* Main content: view message or compose */}
        <div className="lms-messages-content">
          {selectedMsg && !showCompose && (
            <article className="lms-message-detail" aria-label="Message detail">
              <h3>{selectedMsg.subject}</h3>
              <div className="lms-message-detail__meta">
                <span>To: {selectedMsg.to}</span>
                <time>{new Date(selectedMsg.sent_at).toLocaleString()}</time>
              </div>
              <div className="lms-message-detail__body">{selectedMsg.body}</div>
            </article>
          )}

          {showCompose && (
            <div className="lms-compose" aria-label="Compose new message">
              <h3>New Message</h3>

              <div className="lms-form-field">
                <label htmlFor="compose-to">To</label>
                <select
                  id="compose-to"
                  value={composeTo}
                  onChange={(e) => setComposeTo(e.target.value)}
                  aria-label="Select recipient"
                >
                  <option value="">Select a recipient...</option>
                  {recipients.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="lms-form-field">
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

              <div className="lms-form-field">
                <label htmlFor="compose-body">Message</label>
                <textarea
                  id="compose-body"
                  value={composeBody}
                  onChange={(e) => setComposeBody(e.target.value)}
                  aria-label="Message body"
                  placeholder="Type your message..."
                  rows={6}
                />
              </div>

              <div className="lms-form-actions">
                <button
                  className="lms-btn lms-btn--primary"
                  aria-label="Send message"
                  onClick={handleSend}
                  disabled={!composeTo || !composeSubject.trim() || !composeBody.trim()}
                >
                  Send
                </button>
                <button
                  className="lms-btn lms-btn--secondary"
                  aria-label="Cancel compose"
                  onClick={() => setShowCompose(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {!selectedMsg && !showCompose && (
            <div className="lms-messages-placeholder">
              <p>Select a message or compose a new one.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
