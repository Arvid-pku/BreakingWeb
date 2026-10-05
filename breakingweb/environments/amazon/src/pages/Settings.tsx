import { useEffect, useState } from "react";

import type { AmazonSettings } from "../types";
import { useAmazonLayout } from "../context";

export function SettingsPage() {
  const { api, notify } = useAmazonLayout();
  const [settings, setSettings] = useState<AmazonSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getSettings()
      .then((s) => { if (!cancelled) setSettings(s); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api]);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await api.updateSettings({
        default_address_id: settings.default_address_id,
        default_payment_id: settings.default_payment_id,
        prime_member: settings.prime_member,
        one_click_enabled: settings.one_click_enabled,
        email_notifications: settings.email_notifications,
        order_updates_email: settings.order_updates_email,
        deal_alerts_email: settings.deal_alerts_email,
        two_factor_enabled: settings.two_factor_enabled,
        language: settings.language,
      });
      setSettings((current) => (current ? { ...current, ...updated } : updated));
      notify("Settings saved", "Your account settings have been updated.");
    } catch {
      notify("Error", "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading settings...</p>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="amazon-error">
        <h2>Unable to load settings</h2>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <h1>Account Settings</h1>

      <div className="settings-card">
        <h2>Shopping Preferences</h2>
        <div className="settings-form">
          <div className="settings-form__row">
            <label htmlFor="settings-language">Language</label>
            <select
              id="settings-language"
              value={settings.language}
              onChange={(e) => setSettings({ ...settings, language: e.target.value })}
            >
              <option value="English">English</option>
              <option value="Spanish">Spanish</option>
              <option value="French">French</option>
              <option value="German">German</option>
              <option value="Japanese">Japanese</option>
              <option value="Chinese">Chinese</option>
            </select>
          </div>
          <div className="settings-form__row">
            <label htmlFor="settings-currency">Currency</label>
            <input id="settings-currency" type="text" value={settings.currency} readOnly />
          </div>
          <div className="settings-form__row settings-form__row--checkbox">
            <label>
              <input
                type="checkbox"
                checked={settings.prime_member}
                onChange={(e) => setSettings({ ...settings, prime_member: e.target.checked })}
              />
              Prime membership
            </label>
          </div>
          <div className="settings-form__row settings-form__row--checkbox">
            <label>
              <input
                type="checkbox"
                checked={settings.one_click_enabled}
                onChange={(e) => setSettings({ ...settings, one_click_enabled: e.target.checked })}
              />
              Enable 1-Click ordering
            </label>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <h2>Login &amp; Security</h2>
        <div className="settings-form">
          <div className="settings-form__row settings-form__row--checkbox">
            <label>
              <input
                type="checkbox"
                checked={settings.two_factor_enabled}
                onChange={(e) => setSettings({ ...settings, two_factor_enabled: e.target.checked })}
                aria-label="Two-factor authentication"
              />
              Two-factor authentication (2FA)
            </label>
            <p className="settings-form__hint">
              Require a one-time code at sign-in in addition to your password.
            </p>
          </div>
        </div>
      </div>

      <div className="settings-card">
        <h2>Notifications</h2>
        <div className="settings-form">
          <div className="settings-form__row settings-form__row--checkbox">
            <label>
              <input
                type="checkbox"
                checked={settings.email_notifications}
                onChange={(e) => setSettings({ ...settings, email_notifications: e.target.checked })}
              />
              Email notifications
            </label>
          </div>
          <div className="settings-form__row settings-form__row--checkbox">
            <label>
              <input
                id="settings-order-updates"
                type="checkbox"
                checked={settings.order_updates_email}
                onChange={(e) => setSettings({ ...settings, order_updates_email: e.target.checked })}
                aria-label="Order update emails"
              />
              Order update emails
            </label>
          </div>
          <div className="settings-form__row settings-form__row--checkbox">
            <label>
              <input
                id="settings-deal-alerts"
                type="checkbox"
                checked={settings.deal_alerts_email}
                onChange={(e) => setSettings({ ...settings, deal_alerts_email: e.target.checked })}
                aria-label="Deal alert emails"
              />
              Deal alert emails
            </label>
          </div>
        </div>
      </div>

      <div className="settings-actions">
        <button
          className="amazon-btn amazon-btn--add-to-cart"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </div>
  );
}
