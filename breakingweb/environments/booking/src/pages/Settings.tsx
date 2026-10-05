import { useCallback, useEffect, useState } from "react";

import type { BookingSettings, TravelPreferences, PaymentMethod } from "../types";
import { useBookingLayout } from "../context";

export default function Settings() {
  const { sessionId, api, notify } = useBookingLayout();

  const [settings, setSettings] = useState<BookingSettings | null>(null);
  const [preferences, setPreferences] = useState<TravelPreferences | null>(null);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [savingPrefs, setSavingPrefs] = useState(false);

  // New payment method form state
  const [showAddPayment, setShowAddPayment] = useState(false);
  const [newCardType, setNewCardType] = useState("Visa");
  const [newLastFour, setNewLastFour] = useState("");
  const [newExpiry, setNewExpiry] = useState("");
  const [newHolderName, setNewHolderName] = useState("");
  const [addingPayment, setAddingPayment] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, p, pm] = await Promise.all([
        api.getSettings(),
        api.getPreferences(),
        api.listPaymentMethods(),
      ]);
      setSettings(s);
      setPreferences(p);
      setPaymentMethods(pm.payment_methods);
    } catch {
      notify("Error", "Failed to load settings.");
    } finally {
      setLoading(false);
    }
  }, [api, sessionId, notify]);

  useEffect(() => {
    void load();
  }, [load]);

  // --- Save notification/security settings ---
  const handleSaveSettings = async () => {
    if (!settings) return;
    setSavingSettings(true);
    try {
      const updated = await api.updateSettings({
        email_notifications: settings.email_notifications,
        deal_alerts: settings.deal_alerts,
        review_reminders: settings.review_reminders,
        price_alerts: settings.price_alerts,
        newsletter: settings.newsletter,
        sms_notifications: settings.sms_notifications,
        two_factor_enabled: settings.two_factor_enabled,
        language: settings.language,
        currency: settings.currency,
      });
      setSettings(updated);
      notify("Saved", "Settings have been updated.");
    } catch {
      notify("Error", "Failed to save settings.");
    } finally {
      setSavingSettings(false);
    }
  };

  // --- Save travel preferences ---
  const handleSavePreferences = async () => {
    if (!preferences) return;
    setSavingPrefs(true);
    try {
      const updated = await api.updatePreferences({
        smoking: preferences.smoking,
        preferred_bed_type: preferences.preferred_bed_type,
        floor_preference: preferences.floor_preference,
        preferred_room_type: preferences.preferred_room_type,
        preferred_currency: preferences.preferred_currency,
        accessibility_needs: preferences.accessibility_needs,
        dietary_restrictions: preferences.dietary_restrictions,
      });
      setPreferences(updated);
      notify("Saved", "Travel preferences have been updated.");
    } catch {
      notify("Error", "Failed to save preferences.");
    } finally {
      setSavingPrefs(false);
    }
  };

  // --- Payment methods ---
  const handleAddPayment = async () => {
    if (!newLastFour.trim() || !newExpiry.trim() || !newHolderName.trim()) return;
    setAddingPayment(true);
    try {
      const pm = await api.addPaymentMethod({
        card_type: newCardType,
        last_four: newLastFour.trim(),
        expiry: newExpiry.trim(),
        holder_name: newHolderName.trim(),
        is_default: paymentMethods.length === 0,
      });
      setPaymentMethods((prev) => [...prev, pm]);
      setShowAddPayment(false);
      setNewCardType("Visa");
      setNewLastFour("");
      setNewExpiry("");
      setNewHolderName("");
      notify("Added", "Payment method has been added.");
    } catch {
      notify("Error", "Failed to add payment method.");
    } finally {
      setAddingPayment(false);
    }
  };

  const handleRemovePayment = async (pmId: string) => {
    try {
      await api.removePaymentMethod(pmId);
      setPaymentMethods((prev) => prev.filter((p) => p.id !== pmId));
      notify("Removed", "Payment method has been removed.");
    } catch {
      notify("Error", "Failed to remove payment method.");
    }
  };

  const handleSetDefault = async (pmId: string) => {
    try {
      await api.updateSettings({
        default_payment_id: pmId,
      });
      setPaymentMethods((prev) =>
        prev.map((p) => ({ ...p, is_default: p.id === pmId }))
      );
      notify("Updated", "Default payment method updated.");
    } catch {
      notify("Error", "Failed to update default payment method.");
    }
  };

  // Toggle helper for settings booleans
  const toggleSetting = (key: keyof BookingSettings) => {
    if (!settings) return;
    setSettings({ ...settings, [key]: !settings[key] } as BookingSettings);
  };

  // Dietary restrictions helper
  const handleDietaryChange = (value: string) => {
    if (!preferences) return;
    const current = preferences.dietary_restrictions ?? [];
    const updated = current.includes(value)
      ? current.filter((d) => d !== value)
      : [...current, value];
    setPreferences({ ...preferences, dietary_restrictions: updated });
  };

  if (loading) {
    return <div className="bk-loading">Loading settings...</div>;
  }

  if (!settings || !preferences) {
    return (
      <div className="bk-empty">
        <h3>Unable to load settings</h3>
        <p>Please try refreshing the page.</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="bk-section-title" style={{ marginBottom: 24 }}>
        Settings
      </h1>

      {/* Notification Preferences */}
      <div className="bk-section">
        <div className="bk-card" style={{ padding: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
            Notification Preferences
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {([
              ["email_notifications", "Email Notifications"],
              ["deal_alerts", "Deal Alerts"],
              ["review_reminders", "Review Reminders"],
              ["price_alerts", "Price Alerts"],
              ["newsletter", "Newsletter"],
              ["sms_notifications", "SMS Notifications"],
            ] as [keyof BookingSettings, string][]).map(([key, label]) => (
              <label
                key={key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  fontSize: 14,
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={!!settings[key]}
                  onChange={() => toggleSetting(key)}
                  style={{ width: 18, height: 18, accentColor: "var(--bk-blue-light)" }}
                />
                {label}
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Security */}
      <div className="bk-section">
        <div className="bk-card" style={{ padding: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
            Security
          </h2>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={settings.two_factor_enabled}
              onChange={() => toggleSetting("two_factor_enabled")}
              style={{ width: 18, height: 18, accentColor: "var(--bk-blue-light)" }}
            />
            Two-Factor Authentication
          </label>
        </div>
      </div>

      {/* Language & Currency */}
      <div className="bk-section">
        <div className="bk-card" style={{ padding: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
            Language &amp; Currency
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="bk-form-group">
              <label htmlFor="settings-language">Language</label>
              <select
                id="settings-language"
                className="bk-select"
                value={settings.language}
                onChange={(e) =>
                  setSettings({ ...settings, language: e.target.value })
                }
              >
                <option value="English">English</option>
                <option value="Spanish">Spanish</option>
                <option value="French">French</option>
                <option value="German">German</option>
                <option value="Italian">Italian</option>
                <option value="Portuguese">Portuguese</option>
                <option value="Dutch">Dutch</option>
                <option value="Japanese">Japanese</option>
                <option value="Chinese">Chinese</option>
                <option value="Korean">Korean</option>
                <option value="Arabic">Arabic</option>
              </select>
            </div>
            <div className="bk-form-group">
              <label htmlFor="settings-currency">Currency</label>
              <select
                id="settings-currency"
                className="bk-select"
                value={settings.currency}
                onChange={(e) =>
                  setSettings({ ...settings, currency: e.target.value })
                }
              >
                <option value="USD">USD - US Dollar</option>
                <option value="EUR">EUR - Euro</option>
                <option value="GBP">GBP - British Pound</option>
                <option value="JPY">JPY - Japanese Yen</option>
                <option value="AUD">AUD - Australian Dollar</option>
                <option value="CAD">CAD - Canadian Dollar</option>
                <option value="CHF">CHF - Swiss Franc</option>
                <option value="CNY">CNY - Chinese Yuan</option>
                <option value="KRW">KRW - South Korean Won</option>
                <option value="INR">INR - Indian Rupee</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Save Settings Button */}
      <div style={{ marginBottom: 28 }}>
        <button
          className="bk-btn bk-btn--primary"
          onClick={handleSaveSettings}
          disabled={savingSettings}
        >
          {savingSettings ? "Saving..." : "Save Settings"}
        </button>
      </div>

      {/* Payment Methods */}
      <div className="bk-section">
        <div className="bk-card" style={{ padding: 24 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 16,
            }}
          >
            <h2 style={{ fontSize: 18, fontWeight: 700 }}>Payment Methods</h2>
            <button
              className="bk-btn bk-btn--secondary bk-btn--sm"
              onClick={() => setShowAddPayment(!showAddPayment)}
            >
              {showAddPayment ? "Cancel" : "Add New"}
            </button>
          </div>

          {/* Add payment form */}
          {showAddPayment && (
            <div
              style={{
                padding: 16,
                background: "var(--bk-gray-50)",
                borderRadius: "var(--bk-radius)",
                marginBottom: 16,
              }}
            >
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div className="bk-form-group">
                  <label htmlFor="pm-card-type">Card Type</label>
                  <select
                    id="pm-card-type"
                    className="bk-select"
                    value={newCardType}
                    onChange={(e) => setNewCardType(e.target.value)}
                  >
                    <option value="Visa">Visa</option>
                    <option value="Mastercard">Mastercard</option>
                    <option value="Amex">American Express</option>
                    <option value="Discover">Discover</option>
                  </select>
                </div>
                <div className="bk-form-group">
                  <label htmlFor="pm-last-four">Last Four Digits</label>
                  <input
                    id="pm-last-four"
                    type="text"
                    className="bk-input"
                    value={newLastFour}
                    onChange={(e) => setNewLastFour(e.target.value.replace(/\D/g, "").slice(0, 4))}
                    placeholder="1234"
                    maxLength={4}
                  />
                </div>
                <div className="bk-form-group">
                  <label htmlFor="pm-expiry">Expiry (MM/YY)</label>
                  <input
                    id="pm-expiry"
                    type="text"
                    className="bk-input"
                    value={newExpiry}
                    onChange={(e) => setNewExpiry(e.target.value)}
                    placeholder="12/25"
                  />
                </div>
                <div className="bk-form-group">
                  <label htmlFor="pm-holder">Holder Name</label>
                  <input
                    id="pm-holder"
                    type="text"
                    className="bk-input"
                    value={newHolderName}
                    onChange={(e) => setNewHolderName(e.target.value)}
                    placeholder="John Smith"
                  />
                </div>
              </div>
              <button
                className="bk-btn bk-btn--primary bk-btn--sm"
                style={{ marginTop: 8 }}
                onClick={handleAddPayment}
                disabled={addingPayment || !newLastFour.trim() || !newExpiry.trim() || !newHolderName.trim()}
              >
                {addingPayment ? "Adding..." : "Add Payment Method"}
              </button>
            </div>
          )}

          {/* Payment methods list */}
          {paymentMethods.length === 0 ? (
            <p style={{ color: "var(--bk-gray-600)", fontSize: 13 }}>
              No payment methods added yet.
            </p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {paymentMethods.map((pm) => (
                <div
                  key={pm.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 14px",
                    border: "1px solid var(--bk-border)",
                    borderRadius: "var(--bk-radius)",
                    background: pm.is_default ? "#e3f2fd" : "var(--bk-white)",
                  }}
                >
                  <div>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>
                      {pm.card_type} **** {pm.last_four}
                    </span>
                    <span
                      style={{
                        fontSize: 12,
                        color: "var(--bk-gray-600)",
                        marginLeft: 10,
                      }}
                    >
                      Exp: {pm.expiry} &middot; {pm.holder_name}
                    </span>
                    {pm.is_default && (
                      <span
                        className="bk-badge bk-badge--blue"
                        style={{ marginLeft: 10 }}
                      >
                        Default
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    {!pm.is_default && (
                      <button
                        className="bk-btn bk-btn--ghost bk-btn--sm"
                        onClick={() => void handleSetDefault(pm.id)}
                        aria-label={`Set ${pm.card_type} ending in ${pm.last_four} as default`}
                      >
                        Set Default
                      </button>
                    )}
                    <button
                      className="bk-btn bk-btn--ghost bk-btn--sm"
                      style={{ color: "var(--bk-red)" }}
                      onClick={() => void handleRemovePayment(pm.id)}
                      aria-label={`Remove ${pm.card_type} ending in ${pm.last_four}`}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Travel Preferences */}
      <div className="bk-section">
        <div className="bk-card" style={{ padding: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
            Travel Preferences
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Smoking */}
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={preferences.smoking}
                onChange={() =>
                  setPreferences({ ...preferences, smoking: !preferences.smoking })
                }
                style={{ width: 18, height: 18, accentColor: "var(--bk-blue-light)" }}
              />
              Smoking Room
            </label>

            {/* Preferred bed type */}
            <div className="bk-form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="pref-bed-type">Preferred Bed Type</label>
              <select
                id="pref-bed-type"
                className="bk-select"
                value={preferences.preferred_bed_type}
                onChange={(e) =>
                  setPreferences({ ...preferences, preferred_bed_type: e.target.value })
                }
              >
                <option value="">No preference</option>
                <option value="single">Single</option>
                <option value="double">Double</option>
                <option value="queen">Queen</option>
                <option value="king">King</option>
                <option value="twin">Twin</option>
              </select>
            </div>

            {/* Floor preference */}
            <div className="bk-form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="pref-floor">Floor Preference</label>
              <select
                id="pref-floor"
                className="bk-select"
                value={preferences.floor_preference}
                onChange={(e) =>
                  setPreferences({ ...preferences, floor_preference: e.target.value })
                }
              >
                <option value="">No preference</option>
                <option value="low">Low floor</option>
                <option value="mid">Mid floor</option>
                <option value="high">High floor</option>
              </select>
            </div>

            {/* Preferred room type */}
            <div className="bk-form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="pref-room-type">Preferred Room Type</label>
              <select
                id="pref-room-type"
                className="bk-select"
                value={preferences.preferred_room_type ?? ""}
                onChange={(e) =>
                  setPreferences({ ...preferences, preferred_room_type: e.target.value })
                }
              >
                <option value="">No preference</option>
                <option value="standard">Standard</option>
                <option value="deluxe">Deluxe</option>
                <option value="suite">Suite</option>
                <option value="family">Family</option>
              </select>
            </div>

            {/* Preferred currency */}
            <div className="bk-form-group" style={{ marginBottom: 0 }}>
              <label htmlFor="pref-currency">Preferred Currency</label>
              <select
                id="pref-currency"
                className="bk-select"
                value={preferences.preferred_currency ?? ""}
                onChange={(e) =>
                  setPreferences({ ...preferences, preferred_currency: e.target.value })
                }
              >
                <option value="">No preference</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="JPY">JPY</option>
              </select>
            </div>

            {/* Accessibility needs */}
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 14,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={preferences.accessibility_needs}
                onChange={() =>
                  setPreferences({
                    ...preferences,
                    accessibility_needs: !preferences.accessibility_needs,
                  })
                }
                style={{ width: 18, height: 18, accentColor: "var(--bk-blue-light)" }}
              />
              Accessibility Needs
            </label>

            {/* Dietary restrictions */}
            <div>
              <label style={{ display: "block", fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
                Dietary Restrictions
              </label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {[
                  { label: "Vegetarian", value: "vegetarian" },
                  { label: "Vegan", value: "vegan" },
                  { label: "Gluten-free", value: "gluten-free" },
                  { label: "Halal", value: "halal" },
                  { label: "Kosher", value: "kosher" },
                  { label: "Lactose-free", value: "lactose-free" },
                  { label: "Nut-free", value: "nut-free" },
                ].map(({ label, value }) => {
                  const isSelected = (preferences.dietary_restrictions ?? []).includes(value);
                  return (
                    <label
                      key={value}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        fontSize: 13,
                        padding: "4px 10px",
                        borderRadius: "var(--bk-radius)",
                        background: isSelected ? "#e3f2fd" : "var(--bk-gray-50)",
                        cursor: "pointer",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => handleDietaryChange(value)}
                        style={{ width: 14, height: 14, accentColor: "var(--bk-blue-light)" }}
                      />
                      {label}
                    </label>
                  );
                })}
              </div>
            </div>
          </div>

          <button
            className="bk-btn bk-btn--primary"
            style={{ marginTop: 20 }}
            onClick={handleSavePreferences}
            disabled={savingPrefs}
          >
            {savingPrefs ? "Saving..." : "Save Preferences"}
          </button>
        </div>
      </div>
    </div>
  );
}
