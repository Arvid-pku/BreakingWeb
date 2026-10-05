import { useCallback, useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRedditLayout } from "../context";
import type { Notification } from "../types";
import { activateOnKeyDown, timeAgo } from "../utils";

const NOTIF_LABELS: Record<string, string> = {
  comment_reply: "Reply",
  post_reply: "Post",
  mention: "@",
  upvote_milestone: "Upvote",
  award: "Award",
  message: "Message",
};

export function NotificationsPage() {
  const { api, notify, refreshProfile } = useRedditLayout();
  const navigate = useNavigate();
  const location = useLocation();

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listNotifications();
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch {
      notify("Failed to load notifications");
    } finally {
      setLoading(false);
    }
  }, [api, notify]);

  useEffect(() => { void load(); }, [load]);

  const handleMarkRead = async (notifId: string) => {
    try {
      const { notification } = await api.markNotificationRead(notifId);
      setNotifications((prev) => prev.map((n) => (n.id === notifId ? notification : n)));
      setUnreadCount((prev) => Math.max(0, prev - 1));
      void refreshProfile();
    } catch { notify("Failed to mark as read"); }
  };

  const handleMarkAllRead = async () => {
    try {
      const { marked } = await api.markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
      notify(`Marked ${marked} notifications as read`);
      void refreshProfile();
    } catch { notify("Failed"); }
  };

  const handleClick = (notif: Notification) => {
    if (!notif.is_read) void handleMarkRead(notif.id);
    if (notif.related_post_id) {
      navigate(preserveQueryParams(`/post/${notif.related_post_id}`, location.search));
    }
  };

  return (
    <div className="notifications-page">
      <div className="notifications-header">
        <h1>Notifications</h1>
        {unreadCount > 0 && (
          <Button variant="secondary" onClick={handleMarkAllRead} aria-label="Mark all notifications as read">
            Mark all read ({unreadCount})
          </Button>
        )}
      </div>

      {loading ? (
        <div className="notifications-loading">Loading...</div>
      ) : notifications.length === 0 ? (
        <div className="notifications-empty">No notifications</div>
      ) : (
        <div className="notifications-list">
          {notifications.map((notif) => (
            <div
              key={notif.id}
              className={`notification-item ${!notif.is_read ? "notification-item--unread" : ""}`}
              onClick={() => handleClick(notif)}
              onKeyDown={(event) => activateOnKeyDown(event, () => handleClick(notif))}
              role="button"
              tabIndex={0}
              aria-label={`${notif.is_read ? "" : "Unread: "}${notif.title}`}
            >
              <span className="notification-item__icon">{NOTIF_LABELS[notif.type] ?? "Alert"}</span>
              <div className="notification-item__content">
                <h3 className="notification-item__title">{notif.title}</h3>
                <p className="notification-item__body">{notif.body}</p>
                <span className="notification-item__time">{timeAgo(notif.created_at)}</span>
                {notif.subreddit_name && <span className="notification-item__sub">r/{notif.subreddit_name}</span>}
              </div>
              {!notif.is_read && <span className="notification-item__dot" />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
