import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { Notification } from "../types";
import { NotificationItem } from "../components/NotificationItem";

export function NotificationsPage() {
  const { api, notify } = useRobinhoodLayout();
  const location = useLocation();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const items = await api.listNotifications();
      setNotifications(items);
    } catch { /* skip */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, [api]);

  const handleMarkRead = async (id: string) => {
    try {
      await api.markNotificationRead(id);
      await load();
    } catch { /* skip */ }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.markAllNotificationsRead();
      notify("All notifications marked as read");
      await load();
    } catch { /* skip */ }
  };

  if (loading) return <div className="rh-loading">Loading...</div>;

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div className="rh-notifications" aria-label="Notifications">
      <div className="rh-page-header">
        <h1>Notifications</h1>
        <div className="rh-notifications__header-actions">
          <Link to={preserveQueryParams("/alerts", location.search)}>
            <Button variant="secondary" aria-label="Manage price alerts">Manage Alerts</Button>
          </Link>
          {unreadCount > 0 && (
            <Button variant="secondary" onClick={handleMarkAllRead} aria-label="Mark all notifications as read">
              Mark All Read ({unreadCount})
            </Button>
          )}
        </div>
      </div>

      {notifications.length === 0 ? (
        <div className="rh-empty">No notifications</div>
      ) : (
        <div className="rh-notifications__list">
          {notifications.map((n) => (
            <NotificationItem key={n.id} notification={n} onMarkRead={handleMarkRead} />
          ))}
        </div>
      )}
    </div>
  );
}
