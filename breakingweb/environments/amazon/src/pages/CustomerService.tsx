import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Order } from "../types";
import { useAmazonLayout } from "../context";

const HELP_TOPICS = [
  {
    icon: "Orders",
    title: "Your Orders",
    desc: "Track, return, or cancel an order",
    path: "/orders",
  },
  {
    icon: "Returns",
    title: "Returns & Refunds",
    desc: "Return or exchange items, request refund",
    path: "/returns",
  },
  {
    icon: "Settings",
    title: "Account Settings",
    desc: "Change email, password, or account info",
    path: "/account",
  },
  {
    icon: "Payment",
    title: "Payment & Gift Cards",
    desc: "Add or edit payment methods, check gift card balance",
    path: "/gift-cards",
  },
  {
    icon: "Prime",
    title: "Prime Membership",
    desc: "Manage your Prime subscription",
    path: "/account",
  },
  {
    icon: "Digital",
    title: "Digital Services",
    desc: "Kindle, Alexa, app issues",
    path: "/account",
  },
  {
    icon: "Shipping",
    title: "Shipping & Delivery",
    desc: "Track packages, delivery issues",
    path: "/orders",
  },
  {
    icon: "Support",
    title: "Device Support",
    desc: "Echo, Fire TV, Kindle troubleshooting",
    path: "/account",
  },
];

export function CustomerServicePage() {
  const location = useLocation();
  const { api, notify } = useAmazonLayout();
  const [recentOrders, setRecentOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .getOrders()
      .then((items) => {
        if (!cancelled) {
          setRecentOrders(items.slice(0, 3));
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRecentOrders([]);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const handleSearch = () => {
    if (searchQuery.trim()) {
      notify("Search", `No results found for "${searchQuery.trim()}". Try browsing the help topics below.`);
    }
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div className="cs-page">
      <h1 className="cs-page__greeting">Hello Jordan, what can we help you with?</h1>

      <div className="cs-page__search">
        <input
          type="text"
          placeholder="Search our help library"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          aria-label="Search our help library"
        />
        <button onClick={handleSearch} aria-label="Search help">
          Search
        </button>
      </div>

      <div className="cs-topics">
        {HELP_TOPICS.map((topic) => (
          <Link
            key={topic.title}
            to={preserveQueryParams(topic.path, location.search)}
            className="cs-topic-card"
          >
            <div className="cs-topic-card__icon">{topic.icon}</div>
            <div className="cs-topic-card__title">{topic.title}</div>
            <div className="cs-topic-card__desc">{topic.desc}</div>
          </Link>
        ))}
      </div>

      <div className="cs-recent-orders">
        <h2>Your recent orders</h2>
        {loading ? (
          <div className="amazon-loading">
            <div className="amazon-spinner" />
            <p>Loading orders...</p>
          </div>
        ) : recentOrders.length === 0 ? (
          <p>No recent orders found.</p>
        ) : (
          <div className="cs-recent-orders__list">
            {recentOrders.map((order) => (
              <div key={order.id} className="cs-recent-orders__item">
                <div className="cs-recent-orders__info">
                  <strong>Order #{order.id}</strong>
                  <span> &mdash; {order.status}</span>
                  <span className="cs-recent-orders__date">
                    {" "}
                    &middot; Placed {new Date(order.placed_at).toLocaleDateString()}
                  </span>
                  <span> &middot; ${order.total.toFixed(2)}</span>
                </div>
                <div className="cs-recent-orders__actions">
                  <Link
                    to={preserveQueryParams("/orders", location.search)}
                    className="amazon-btn amazon-btn--add-to-cart"
                  >
                    Track package
                  </Link>
                  <Link
                    to={preserveQueryParams(`/returns/new/${order.id}`, location.search)}
                    className="amazon-btn amazon-btn--secondary"
                  >
                    Return items
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="cs-contact">
        <h2 className="cs-contact__title">Need more help?</h2>
        <p style={{ marginBottom: 16, color: "#565959" }}>
          We're here for you 24/7. Call us or start a chat.
        </p>
        <div className="cs-contact__buttons">
          <button
            className="amazon-btn amazon-btn--buy-now"
            onClick={() =>
              notify(
                "Simulated Environment",
                "This is a simulated environment. Live contact is not available."
              )
            }
          >
            Contact Us
          </button>
          <button
            className="amazon-btn amazon-btn--add-to-cart"
            onClick={() =>
              notify(
                "Simulated Environment",
                "This is a simulated environment. Live chat is not available."
              )
            }
          >
            Chat with us
          </button>
        </div>
        <p style={{ marginTop: 16, fontSize: 13, color: "#565959" }}>
          Or call us: <strong>1-888-280-4331</strong>
        </p>
      </div>
    </div>
  );
}
