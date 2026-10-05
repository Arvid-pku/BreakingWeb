import { useCallback, useEffect, useRef } from "react";

import { useRedditLayout } from "../context";
import type { RedditSettings } from "../types";

type SelectKey =
  | "default_feed_sort"
  | "default_comment_sort"
  | "theme"
  | "language"
  | "country";

type CheckboxKey =
  | "compact_view"
  | "open_links_in_new_tab"
  | "auto_play_media"
  | "reduce_animations"
  | "show_nsfw"
  | "blur_nsfw"
  | "email_comment_reply"
  | "email_post_reply"
  | "email_mentions"
  | "email_messages"
  | "email_digest"
  | "show_online_status"
  | "allow_followers"
  | "show_active_communities";

export function SettingsPage() {
  const { settings, notify, refreshSettings, updateSettings } = useRedditLayout();

  const selectRefs = useRef<Partial<Record<SelectKey, HTMLSelectElement | null>>>({});
  const checkboxRefs = useRef<Partial<Record<CheckboxKey, HTMLInputElement | null>>>({});

  useEffect(() => {
    if (settings) {
      return;
    }
    void refreshSettings().catch(() => {
      notify("Failed to load settings");
    });
  }, [notify, refreshSettings, settings]);

  const handleUpdate = useCallback(
    async (updates: Partial<RedditSettings>) => {
      try {
        await updateSettings(updates);
        notify("Settings updated");
      } catch {
        notify("Failed to update settings");
      }
    },
    [notify, updateSettings],
  );

  // Re-read every control's live DOM value and POST the full settings payload.
  // Agents that drive the page programmatically (``select.value = 'new'`` with no
  // synthetic React event) bypass onChange; the explicit Save pass picks up the
  // current DOM state regardless.
  const saveAll = useCallback(async () => {
    if (!settings) return;
    const current = settings as unknown as Record<string, unknown>;
    const payload: Partial<RedditSettings> = {};
    const out = payload as unknown as Record<string, unknown>;
    for (const [key, el] of Object.entries(selectRefs.current) as [SelectKey, HTMLSelectElement | null][]) {
      if (el && el.value !== current[key]) {
        out[key] = el.value;
      }
    }
    for (const [key, el] of Object.entries(checkboxRefs.current) as [CheckboxKey, HTMLInputElement | null][]) {
      if (el && el.checked !== current[key]) {
        out[key] = el.checked;
      }
    }
    if (Object.keys(payload).length === 0) {
      notify("No changes to save");
      return;
    }
    await handleUpdate(payload);
  }, [handleUpdate, notify, settings]);

  if (!settings) return <div className="settings-page__loading">Loading settings...</div>;

  const regSelect = (key: SelectKey) => (el: HTMLSelectElement | null) => {
    selectRefs.current[key] = el;
  };
  const regCheck = (key: CheckboxKey) => (el: HTMLInputElement | null) => {
    checkboxRefs.current[key] = el;
  };

  return (
    <div className="settings-page">
      <h1 className="settings-page__title">User Settings</h1>

      <section className="settings-section" aria-label="Feed settings">
        <h2 className="settings-section__title">Feed</h2>
        <div className="settings-field">
          <label htmlFor="feed-sort">Default feed sort</label>
          <select id="feed-sort" ref={regSelect("default_feed_sort")} value={settings.default_feed_sort} onChange={(e) => handleUpdate({ default_feed_sort: e.target.value })}>
            <option value="hot">Hot</option>
            <option value="new">New</option>
            <option value="top">Top</option>
            <option value="rising">Rising</option>
          </select>
        </div>
        <div className="settings-field">
          <label htmlFor="comment-sort">Default comment sort</label>
          <select id="comment-sort" ref={regSelect("default_comment_sort")} value={settings.default_comment_sort} onChange={(e) => handleUpdate({ default_comment_sort: e.target.value })}>
            <option value="best">Best</option>
            <option value="top">Top</option>
            <option value="new">New</option>
            <option value="controversial">Controversial</option>
            <option value="old">Old</option>
          </select>
        </div>
      </section>

      <section className="settings-section" aria-label="Display settings">
        <h2 className="settings-section__title">Display</h2>
        <div className="settings-field settings-field--toggle">
          <label htmlFor="theme-select">Theme</label>
          <select id="theme-select" ref={regSelect("theme")} value={settings.theme} onChange={(e) => handleUpdate({ theme: e.target.value })}>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Compact view" ref={regCheck("compact_view")} checked={settings.compact_view} onChange={(e) => handleUpdate({ compact_view: e.target.checked })} />
            Compact view
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Open links in new tab" ref={regCheck("open_links_in_new_tab")} checked={settings.open_links_in_new_tab} onChange={(e) => handleUpdate({ open_links_in_new_tab: e.target.checked })} />
            Open links in new tab
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Auto-play media" ref={regCheck("auto_play_media")} checked={settings.auto_play_media} onChange={(e) => handleUpdate({ auto_play_media: e.target.checked })} />
            Auto-play media
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Reduce animations" ref={regCheck("reduce_animations")} checked={settings.reduce_animations} onChange={(e) => handleUpdate({ reduce_animations: e.target.checked })} />
            Reduce animations
          </label>
        </div>
      </section>

      <section className="settings-section" aria-label="Content settings">
        <h2 className="settings-section__title">Content</h2>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Show NSFW content" ref={regCheck("show_nsfw")} checked={settings.show_nsfw} onChange={(e) => handleUpdate({ show_nsfw: e.target.checked })} />
            Show NSFW content
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Blur NSFW images" ref={regCheck("blur_nsfw")} checked={settings.blur_nsfw} onChange={(e) => handleUpdate({ blur_nsfw: e.target.checked })} />
            Blur NSFW images
          </label>
        </div>
        <div className="settings-field">
          <label htmlFor="language-select">Language</label>
          <select id="language-select" ref={regSelect("language")} value={settings.language} onChange={(e) => handleUpdate({ language: e.target.value })}>
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
            <option value="ja">Japanese</option>
            <option value="zh">Chinese</option>
          </select>
        </div>
        <div className="settings-field">
          <label htmlFor="country-select">Country</label>
          <select id="country-select" ref={regSelect("country")} value={settings.country} onChange={(e) => handleUpdate({ country: e.target.value })}>
            <option value="US">United States</option>
            <option value="GB">United Kingdom</option>
            <option value="CA">Canada</option>
            <option value="AU">Australia</option>
            <option value="DE">Germany</option>
            <option value="FR">France</option>
            <option value="JP">Japan</option>
          </select>
        </div>
      </section>

      <section className="settings-section" aria-label="Notification settings">
        <h2 className="settings-section__title">Notifications</h2>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Email on comment replies" ref={regCheck("email_comment_reply")} checked={settings.email_comment_reply} onChange={(e) => handleUpdate({ email_comment_reply: e.target.checked })} />
            Email on comment replies
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Email on post replies" ref={regCheck("email_post_reply")} checked={settings.email_post_reply} onChange={(e) => handleUpdate({ email_post_reply: e.target.checked })} />
            Email on post replies
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Email on mentions" ref={regCheck("email_mentions")} checked={settings.email_mentions} onChange={(e) => handleUpdate({ email_mentions: e.target.checked })} />
            Email on mentions
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Email on private messages" ref={regCheck("email_messages")} checked={settings.email_messages} onChange={(e) => handleUpdate({ email_messages: e.target.checked })} />
            Email on private messages
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Email digest" ref={regCheck("email_digest")} checked={settings.email_digest} onChange={(e) => handleUpdate({ email_digest: e.target.checked })} />
            Email digest
          </label>
        </div>
      </section>

      <section className="settings-section" aria-label="Privacy settings">
        <h2 className="settings-section__title">Privacy</h2>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Show online status" ref={regCheck("show_online_status")} checked={settings.show_online_status} onChange={(e) => handleUpdate({ show_online_status: e.target.checked })} />
            Show online status
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Allow followers" ref={regCheck("allow_followers")} checked={settings.allow_followers} onChange={(e) => handleUpdate({ allow_followers: e.target.checked })} />
            Allow followers
          </label>
        </div>
        <div className="settings-field settings-field--toggle">
          <label>
            <input type="checkbox" aria-label="Show active communities" ref={regCheck("show_active_communities")} checked={settings.show_active_communities} onChange={(e) => handleUpdate({ show_active_communities: e.target.checked })} />
            Show active communities in profile
          </label>
        </div>
      </section>

      <section className="settings-section" aria-label="Save settings">
        <button type="button" className="settings-save-button" aria-label="Save all settings" onClick={() => void saveAll()}>
          Save all settings
        </button>
        <p className="settings-save-hint">
          Settings auto-save when you change a control. Use this button to re-sync
          any programmatic changes to the form that did not fire a change event.
        </p>
      </section>
    </div>
  );
}
