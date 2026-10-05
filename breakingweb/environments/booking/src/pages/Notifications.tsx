import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Notification } from "../types";
import { useBookingLayout } from "../context";

const NOTIF_ICONS: Record<string, string> = {
  booking_confirmed: "\u2705",
  booking_cancelled: "\u274C",
  deal_alert: "\uD83D\uDCB0",
  price_drop: "\uD83D\uDCC9",
  genius_upgrade: "\u2B50",
  review_reminder: "\u270D\uFE0F",
  check_in_reminder: "\uD83D\uDECE\uFE0F",
  payment_received: "\uD83D\uDCB3",
  message_received: "\u2709\uFE0F",
  reward_earned: "\uD83C\uDF81",
};

const NOTIF_BADGE_CLASS: Record<string, string> = {
  booking_confirmed: "bk-badge--green",
  booking_cancelled: "bk-badge--red",
  deal_alert: "bk-badge--yellow",
  price_drop: "bk-badge--yellow",
  genius_upgrade: "bk-badge--blue",
  review_reminder: "bk-badge--blue",
  check_in_reminder: "bk-badge--green",
  payment_received: "bk-badge--green",
  message_received: "bk-badge--blue",
  reward_earned: "bk-badge--genius",
};

export default function Notifications() {
  const { sessionId, api, notify } = useBookingLayout();
  const location = useLocation();

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listNotifications();
      setNotifications(data.notifications);
      setUnreadCount(data.unread);
    } catch {
      notify("Error", "Failed to load notifications.");
    } finally {
      setLoading(false);
    }
  }, [api, sessionId, notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleMarkRead = async (notifId: string) => {
    try {
      const updated = await api.markNotificationRead(notifId);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? updated : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      notify("Error", "Failed to mark notification as read.");
    }
  };

  const formatDate = (d: string) =>
    new Date(d).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  if (loading) {
    return <div className="bk-loading">Loading notifications...</div>;
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
          Notifications
          {unreadCount > 0 && (
            <span
              className="bk-badge bk-badge--red"
              style={{ marginLeft: 10, fontSize: 12, verticalAlign: "middle" }}
            >
              {unreadCount} unread
            </span>
          )}
        </h1>
      </div>

      {notifications.length === 0 ? (
        <div className="bk-empty">
          <h3>No notifications</h3>
          <p>You're all caught up! No new notifications.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {notifications.map((notif) => {
            const icon = NOTIF_ICONS[notif.type] ?? "\uD83D\uDD14";
            const badgeClass = NOTIF_BADGE_CLASS[notif.type] ?? "bk-badge--blue";

            return (
              <div
                key={notif.id}
                className="bk-card"
                style={{
                  borderLeft: !notif.read
                    ? "3px solid var(--bk-blue-light)"
                    : "3px solid transparent",
                  cursor: !notif.read ? "pointer" : "default",
                }}
                onClick={() => {
                  if (!notif.read) void handleMarkRead(notif.id);
                }}
                role={!notif.read ? "button" : undefined}
                tabIndex={!notif.read ? 0 : undefined}
                onKeyDown={(e) => {
                  if (!notif.read && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    void handleMarkRead(notif.id);
                  }
                }}
                aria-label={
                  !notif.read
                    ? `Unread notification: ${notif.title}. Click to mark as read.`
                    : notif.title
                }
              >
                <div
                  style={{
                    padding: "14px 16px",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 14,
                  }}
                >
                  {/* Type icon */}
                  <div
                    style={{
                      fontSize: 24,
                      flexShrink: 0,
                      width: 40,
                      height: 40,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {icon}
                  </div>

                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        marginBottom: 4,
                      }}
                    >
                      <span
                        style={{
                          fontWeight: notif.read ? 400 : 700,
                          fontSize: 14,
                        }}
                      >
                        {notif.title}
                      </span>
                      <span className={`bk-badge ${badgeClass}`}>
                        {notif.type.replace(/_/g, " ")}
                      </span>
                      {!notif.read && <span className="bk-notification-dot" />}
                    </div>
                    <p
                      style={{
                        fontSize: 13,
                        color: "var(--bk-gray-600)",
                        marginBottom: 4,
                        lineHeight: 1.4,
                      }}
                    >
                      {notif.message}
                    </p>
                    <span
                      style={{ fontSize: 12, color: "var(--bk-gray-300)" }}
                    >
                      {formatDate(notif.created_at)}
                    </span>
                  </div>

                  {/* Mark read button */}
                  {!notif.read && (
                    <button
                      className="bk-btn bk-btn--ghost bk-btn--sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleMarkRead(notif.id);
                      }}
                      aria-label={`Mark "${notif.title}" as read`}
                      style={{ flexShrink: 0 }}
                    >
                      Mark read
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
