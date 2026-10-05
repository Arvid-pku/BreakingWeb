import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";
import type { Account, GeniusInfo, Wallet } from "../types";
import { useBookingLayout } from "../context";

interface EditField {
  key: string;
  label: string;
  apiKey: string;
  type?: string;
}

const PROFILE_FIELDS: EditField[] = [
  { key: "name", label: "Full Name", apiKey: "owner_name" },
  { key: "email", label: "Email", apiKey: "owner_email", type: "email" },
  { key: "phone", label: "Phone", apiKey: "owner_phone", type: "tel" },
  { key: "nationality", label: "Nationality", apiKey: "owner_nationality" },
  { key: "date_of_birth", label: "Date of Birth", apiKey: "owner_date_of_birth", type: "date" },
  { key: "gender", label: "Gender", apiKey: "owner_gender" },
  { key: "address", label: "Address", apiKey: "owner_address" },
];

function formatDate(dateStr: string): string {
  if (!dateStr) return "Not provided";
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function AccountPage() {
  const { sessionId, api, notify } = useBookingLayout();
  const location = useLocation();

  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getAccount()
      .then((data) => {
        if (!cancelled) setAccount(data);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, sessionId]);

  const getFieldValue = (key: string): string => {
    if (!account) return "";
    const val = (account as unknown as Record<string, unknown>)[key];
    return typeof val === "string" ? val : "";
  };

  const getDisplayValue = (field: EditField): string => {
    const val = getFieldValue(field.key);
    if (!val) return "Not provided";
    if (field.type === "date") return formatDate(val);
    return val;
  };

  const startEdit = (field: EditField) => {
    setEditingField(field.key);
    setEditValue(getFieldValue(field.key));
  };

  const cancelEdit = () => {
    setEditingField(null);
    setEditValue("");
  };

  const saveEdit = async (field: EditField) => {
    setSaving(true);
    try {
      const updated = await api.updateProfile({
        [field.apiKey]: editValue,
      });
      setAccount(updated);
      notify("Profile Updated", `${field.label} has been updated.`);
    } catch {
      notify("Error", `Failed to update ${field.label.toLowerCase()}.`);
    }
    setSaving(false);
    setEditingField(null);
    setEditValue("");
  };

  if (loading) {
    return <div className="bk-loading">Loading account...</div>;
  }

  if (!account) {
    return (
      <div className="bk-empty">
        <h3>Account not found</h3>
        <p>Unable to load account information.</p>
      </div>
    );
  }

  const genius: GeniusInfo = account.genius;
  const wallet: Wallet = account.wallet;

  const geniusProgress =
    genius.bookings_needed_for_next > 0
      ? Math.round(
          (genius.total_bookings /
            (genius.total_bookings + genius.bookings_needed_for_next)) *
            100
        )
      : 100;

  return (
    <div>
      {/* Profile Header */}
      <div className="bk-genius-banner" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h3 style={{ fontSize: 22 }}>{account.name}</h3>
          <p style={{ marginTop: 4 }}>{account.email}</p>
        </div>
        <div>
          <span
            className="bk-genius-badge"
            style={{ fontSize: 14, padding: "6px 12px" }}
          >
            Genius Level {genius.level}
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 20 }}>
        {/* Left column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Personal Details */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Personal Details</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {PROFILE_FIELDS.map((field) => (
                <div
                  key={field.key}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "12px 0",
                    borderBottom: "1px solid var(--bk-border)",
                  }}
                >
                  {editingField === field.key ? (
                    <div style={{ flex: 1 }}>
                      <label
                        style={{
                          display: "block",
                          fontSize: 12,
                          color: "var(--bk-gray-600)",
                          marginBottom: 4,
                          fontWeight: 600,
                        }}
                      >
                        {field.label}
                      </label>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        {field.key === "gender" ? (
                          <select
                            className="bk-select"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            style={{ maxWidth: 300 }}
                          >
                            <option value="">Prefer not to say</option>
                            <option value="male">Male</option>
                            <option value="female">Female</option>
                            <option value="non-binary">Non-binary</option>
                            <option value="other">Other</option>
                          </select>
                        ) : (
                          <input
                            className="bk-input"
                            type={field.type || "text"}
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            style={{ maxWidth: 300 }}
                            autoFocus
                          />
                        )}
                        <button
                          className="bk-btn bk-btn--primary bk-btn--sm"
                          onClick={() => saveEdit(field)}
                          disabled={saving}
                        >
                          {saving ? "Saving..." : "Save"}
                        </button>
                        <button
                          className="bk-btn bk-btn--ghost bk-btn--sm"
                          onClick={cancelEdit}
                          disabled={saving}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div>
                        <div
                          style={{
                            fontSize: 12,
                            color: "var(--bk-gray-600)",
                            marginBottom: 2,
                          }}
                        >
                          {field.label}
                        </div>
                        <div style={{ fontSize: 14, fontWeight: 500 }}>
                          {getDisplayValue(field)}
                        </div>
                      </div>
                      <button
                        className="bk-btn bk-btn--ghost bk-btn--sm"
                        onClick={() => startEdit(field)}
                      >
                        Edit
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Genius Program */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Genius Loyalty Program</h2>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <span
                className="bk-genius-badge"
                style={{ fontSize: 16, padding: "8px 16px" }}
              >
                Level {genius.level}
              </span>
              <div style={{ fontSize: 14 }}>
                <strong>{genius.total_bookings}</strong> lifetime bookings
              </div>
            </div>

            {genius.bookings_needed_for_next > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: 13,
                    marginBottom: 6,
                  }}
                >
                  <span>Progress to Level {genius.level + 1}</span>
                  <span>
                    {genius.bookings_needed_for_next} more{" "}
                    {genius.bookings_needed_for_next === 1 ? "booking" : "bookings"} needed
                  </span>
                </div>
                <div className="bk-review-bar-track" style={{ height: 10 }}>
                  <div
                    className="bk-review-bar-fill"
                    style={{
                      width: `${geniusProgress}%`,
                      background: "var(--bk-genius-blue)",
                    }}
                  />
                </div>
              </div>
            )}

            {genius.benefits.length > 0 && (
              <div>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>
                  Your Benefits
                </h3>
                <ul style={{ listStyle: "none", padding: 0 }}>
                  {genius.benefits.map((benefit, i) => (
                    <li
                      key={i}
                      style={{
                        padding: "6px 0",
                        fontSize: 14,
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <span style={{ color: "var(--bk-green)", fontWeight: 700 }}>&#10003;</span>
                      {benefit}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Wallet */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Wallet</h2>
            <div
              style={{
                background: "var(--bk-gray-50)",
                padding: 16,
                borderRadius: "var(--bk-radius-lg)",
                textAlign: "center",
                marginBottom: 16,
              }}
            >
              <div style={{ fontSize: 12, color: "var(--bk-gray-600)", marginBottom: 4 }}>
                Available Balance
              </div>
              <div style={{ fontSize: 28, fontWeight: 800 }}>
                {wallet.currency === "USD" ? "$" : wallet.currency + " "}
                {wallet.balance.toFixed(2)}
              </div>
            </div>

            {wallet.transactions.length > 0 ? (
              <div>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>
                  Recent Transactions
                </h3>
                <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                  {wallet.transactions.slice(0, 5).map((tx, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "8px 0",
                        borderBottom: "1px solid var(--bk-border)",
                        fontSize: 13,
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 500 }}>{tx.description}</div>
                        <div style={{ color: "var(--bk-gray-600)", fontSize: 12 }}>
                          {formatDate(tx.created_at)}
                        </div>
                      </div>
                      <div
                        style={{
                          fontWeight: 600,
                          color:
                            tx.type === "credit" ? "var(--bk-green)" : "var(--bk-gray-800)",
                        }}
                      >
                        {tx.type === "credit" ? "+" : "-"}
                        {wallet.currency === "USD" ? "$" : wallet.currency + " "}
                        {Math.abs(tx.amount).toFixed(2)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p style={{ fontSize: 13, color: "var(--bk-gray-600)" }}>
                No recent transactions.
              </p>
            )}
          </div>

          {/* Quick Links */}
          <div className="bk-card" style={{ padding: 20 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>Quick Links</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {[
                { label: "Settings", path: "/settings", description: "Notifications, language, currency" },
                { label: "Payment Methods", path: "/settings", description: "Manage your saved cards" },
                { label: "Travel Preferences", path: "/settings", description: "Room, bed, and dietary preferences" },
                { label: "My Reviews", path: "/reviews", description: "View and manage your reviews" },
              ].map((link) => (
                <Link
                  key={link.label}
                  to={preserveQueryParams(link.path, location.search)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "12px 0",
                    borderBottom: "1px solid var(--bk-border)",
                    textDecoration: "none",
                    color: "inherit",
                  }}
                >
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--bk-blue-light)" }}>
                      {link.label}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--bk-gray-600)" }}>
                      {link.description}
                    </div>
                  </div>
                  <span style={{ color: "var(--bk-gray-300)", fontSize: 18 }}>&rsaquo;</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
