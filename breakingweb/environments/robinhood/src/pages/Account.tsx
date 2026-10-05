import { useEffect, useState } from "react";
import { Button } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { AccountSettings, SecurityEntry } from "../types";

export function AccountPage() {
  const { api, notify } = useRobinhoodLayout();
  const [settings, setSettings] = useState<AccountSettings | null>(null);
  const [securityLog, setSecurityLog] = useState<SecurityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getSettings(), api.getSecurityLog()])
      .then(([s, log]) => {
        if (!cancelled) {
          setSettings(s);
          setSecurityLog(log);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api]);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await api.updateSettings(settings);
      setSettings(updated);
      notify("Settings Saved");
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate2FA = async (method: "sms" | "authenticator" | "none") => {
    try {
      const updated = await api.update2FA(method);
      setSettings(updated);
      notify("2FA Updated", `Two-factor authentication set to ${method}`);
      const log = await api.getSecurityLog();
      setSecurityLog(log);
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Failed to update 2FA");
    }
  };

  if (loading) return <div className="rh-loading">Loading...</div>;
  if (!settings) return <div className="rh-empty">Unable to load settings</div>;

  return (
    <div className="rh-account" aria-label="Account settings">
      <h1>Account</h1>

      <section className="rh-account__section" aria-label="Settings">
        <h2>Settings</h2>

        <div className="rh-order-form__field">
          <label htmlFor="setting-theme">Theme</label>
          <select
            id="setting-theme"
            value={settings.display_theme}
            onChange={(e) => setSettings({ ...settings, display_theme: e.target.value as "light" | "dark" })}
          >
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>

        <div className="rh-order-form__field">
          <label htmlFor="setting-order-type">Default Order Type</label>
          <select
            id="setting-order-type"
            value={settings.default_order_type}
            onChange={(e) => setSettings({ ...settings, default_order_type: e.target.value as "market" | "limit" })}
          >
            <option value="market">Market</option>
            <option value="limit">Limit</option>
          </select>
        </div>

        <div className="rh-order-form__field rh-order-form__field--checkbox">
          <label>
            <input
              type="checkbox"
              checked={settings.reinvest_dividends}
              onChange={(e) => setSettings({ ...settings, reinvest_dividends: e.target.checked })}
            />
            Reinvest Dividends
          </label>
        </div>

        <div className="rh-order-form__field rh-order-form__field--checkbox">
          <label>
            <input
              type="checkbox"
              checked={settings.extended_hours_enabled}
              onChange={(e) => setSettings({ ...settings, extended_hours_enabled: e.target.checked })}
            />
            Extended Hours Trading
          </label>
        </div>

        <Button variant="primary" onClick={handleSave} disabled={saving} aria-label="Save settings">
          {saving ? "Saving..." : "Save Settings"}
        </Button>
      </section>

      <section className="rh-account__section" aria-label="Security">
        <h2>Security</h2>

        <div className="rh-order-form__field">
          <label htmlFor="setting-2fa">Two-Factor Authentication</label>
          <select
            id="setting-2fa"
            value={settings.two_factor_method}
            onChange={(e) => handleUpdate2FA(e.target.value as "sms" | "authenticator" | "none")}
          >
            <option value="none">None</option>
            <option value="sms">SMS</option>
            <option value="authenticator">Authenticator App</option>
          </select>
        </div>
      </section>

      <section className="rh-account__section" aria-label="Security log">
        <h2>Security Log</h2>
        {securityLog.length === 0 ? (
          <div className="rh-empty">No security events</div>
        ) : (
          <table className="rh-table" aria-label="Security log table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Device</th>
                <th>IP Address</th>
                <th>Location</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {securityLog.map((entry, i) => (
                <tr key={i}>
                  <td>{entry.event.replace(/_/g, " ")}</td>
                  <td>{entry.device}</td>
                  <td>{entry.ip_address}</td>
                  <td>{entry.location}</td>
                  <td>{new Date(entry.timestamp).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
