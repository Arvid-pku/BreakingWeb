import { useEffect, useState } from "react";

import type { Notification } from "../types";
import { useAmazonLayout } from "../context";

export function NotificationsPage() {
  const { api, notify } = useAmazonLayout();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unread">("all");

  useEffect(() => {
    let cancelled = false;
    api.getNotifications(filter === "unread")
      .then((items) => {
        if (!cancelled) {
          setNotifications(items);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNotifications([
            {
              id: "notif-1",
              type: "order",
              title: "Order Shipped",
              message: "Your recent order has been shipped and is on its way.",
              read: false,
              created_at: new Date().toISOString(),
              related_id: "",
            },
            {
              id: "notif-2",
              type: "deal",
              title: "Deal of the Day",
              message: "Check out today's deals with up to 50% off select items.",
              read: true,
              created_at: new Date(Date.now() - 86400000).toISOString(),
              related_id: "",
            },
            {
              id: "notif-3",
              type: "return",
              title: "Return Approved",
              message: "Your return request has been approved. A refund will be issued shortly.",
              read: false,
              created_at: new Date(Date.now() - 172800000).toISOString(),
              related_id: "",
            },
          ]);
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [api, filter]);

  const handleMarkRead = async (id: string) => {
    try {
      await api.markNotificationRead(id);
    } catch {
      // simulated
    }
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
    notify("Notification marked as read", "");
  };

  const unreadCount = notifications.filter((n) => !n.read).length;

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading notifications...</p>
      </div>
    );
  }

  return (
    <div className="notifications-page">
      <div className="notifications-page__header">
        <h1>Notifications</h1>
        {unreadCount > 0 && (
          <span className="notifications-page__badge">{unreadCount} unread</span>
        )}
      </div>

      <div className="notifications-page__filters">
        <button
          className={`notifications-filter-btn ${filter === "all" ? "notifications-filter-btn--active" : ""}`}
          onClick={() => setFilter("all")}
        >
          All
        </button>
        <button
          className={`notifications-filter-btn ${filter === "unread" ? "notifications-filter-btn--active" : ""}`}
          onClick={() => setFilter("unread")}
        >
          Unread
        </button>
      </div>

      {notifications.length === 0 ? (
        <div className="notifications-empty">
          <h2>No notifications</h2>
          <p>You're all caught up!</p>
        </div>
      ) : (
        <div className="notifications-list">
          {notifications.map((notif) => (
            <article
              key={notif.id}
              className={`notification-card ${notif.read ? "notification-card--read" : "notification-card--unread"}`}
              onClick={() => !notif.read && handleMarkRead(notif.id)}
              role="button"
              tabIndex={0}
              aria-label={`${notif.read ? "Read" : "Unread"} notification: ${notif.title}`}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !notif.read) handleMarkRead(notif.id);
              }}
            >
              <div className="notification-card__icon">
                {notif.type === "order" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <path d="M3 9h18" />
                  </svg>
                )}
                {notif.type === "deal" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" />
                    <line x1="7" y1="7" x2="7.01" y2="7" />
                  </svg>
                )}
                {notif.type === "return" && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="1 4 1 10 7 10" />
                    <path d="M3.51 15a9 9 0 102.13-9.36L1 10" />
                  </svg>
                )}
                {!["order", "deal", "return"].includes(notif.type) && (
                  <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 01-3.46 0" />
                  </svg>
                )}
              </div>
              <div className="notification-card__content">
                <div className="notification-card__title">{notif.title}</div>
                <div className="notification-card__message">{notif.message}</div>
                <div className="notification-card__time">
                  {new Date(notif.created_at).toLocaleDateString()} at {new Date(notif.created_at).toLocaleTimeString()}
                </div>
              </div>
              {!notif.read && <div className="notification-card__dot" />}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
