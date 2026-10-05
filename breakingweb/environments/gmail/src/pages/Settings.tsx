import { useEffect, useMemo, useState } from "react";
import { Button, DataTable, FormField, Modal } from "@breakingweb/shared";
import { useSearchParams } from "react-router-dom";

import { IconDelete } from "../icons";
import { useGmailLayout } from "../context";
import type { FilterRule, GmailSettings, Label } from "../types";

type ExtendedLabel = Label & {
  show_in_message_list?: string;
};

type ExtendedFilterRule = FilterRule & {
  never_spam?: boolean;
};

type DraftLabel = {
  id: string;
  name: string;
} | null;

type LabelVisibility = "show" | "hide" | "show_if_unread";

const SETTINGS_TABS = [
  "General",
  "Labels",
  "Inbox",
  "Accounts and Import",
  "Filters and Blocked Addresses",
  "Forwarding and POP/IMAP",
  "Add-ons",
  "Chat and Meet",
] as const;

const SETTINGS_TABS_SECONDARY = ["Advanced", "Offline", "Themes"] as const;

const DEFAULT_SETTINGS: GmailSettings = {
  signature: "",
  forwarding_address: "",
  display_density: "comfortable",
  vacation_responder_enabled: false,
  vacation_responder_message: "",
  auto_advance: "newer",
  language: "English (US)",
  input_tools_enabled: true,
  right_to_left: false,
  max_page_size: 50,
  undo_send_seconds: 5,
  default_reply_behavior: "reply",
  hover_actions_enabled: true,
  send_and_archive: false,
  default_text_style: "Sans Serif",
};

interface DraftFilter {
  name: string;
  fromPattern: string;
  subjectPhrase: string;
  hasAttachment: boolean;
  addLabelsText: string;
  forwardTo: string;
  archive: boolean;
  star: boolean;
  markRead: boolean;
  neverSpam: boolean;
}

const EMPTY_DRAFT_FILTER: DraftFilter = {
  name: "",
  fromPattern: "",
  subjectPhrase: "",
  hasAttachment: false,
  addLabelsText: "",
  forwardTo: "",
  archive: false,
  star: false,
  markRead: false,
  neverSpam: false,
};

function buildFilterQuery(draft: DraftFilter): string {
  const parts: string[] = [];
  if (draft.fromPattern.trim()) {
    parts.push(`from:${draft.fromPattern.trim()}`);
  }
  if (draft.subjectPhrase.trim()) {
    parts.push(`subject:${draft.subjectPhrase.trim()}`);
  }
  if (draft.hasAttachment) {
    parts.push("has:attachment");
  }
  return parts.join(" ");
}

function filterCriteriaSummary(draft: DraftFilter): string {
  const labels: string[] = [];
  if (draft.fromPattern.trim()) {
    labels.push(`From ${draft.fromPattern.trim()}`);
  }
  if (draft.subjectPhrase.trim()) {
    labels.push(`Subject contains "${draft.subjectPhrase.trim()}"`);
  }
  if (draft.hasAttachment) {
    labels.push("Has attachment");
  }
  return labels.join(" · ") || "No criteria selected";
}

function hasFilterAction(draft: DraftFilter): boolean {
  return Boolean(
    draft.addLabelsText.trim() ||
      draft.forwardTo.trim() ||
      draft.archive ||
      draft.star ||
      draft.markRead ||
      draft.neverSpam,
  );
}

function getLabelVisibility(label: Label): LabelVisibility {
  const visibility = (label as ExtendedLabel).show_in_label_list;
  return visibility === "hide" || visibility === "show_if_unread" ? visibility : "show";
}

function getMessageListVisibility(label: Label): LabelVisibility {
  const extended = label as ExtendedLabel;
  if (typeof extended.show_in_message_list === "string") {
    const visibility = extended.show_in_message_list;
    return visibility === "hide" || visibility === "show_if_unread" ? visibility : "show";
  }
  return label.show_in_imap === false ? "hide" : "show";
}

function renderVisibilityButtons(
  value: LabelVisibility,
  onChange: (value: LabelVisibility) => void,
  fieldName: string,
  showIfUnread = true,
) {
  return (
    <span className="gmail-labels-table__toggles" aria-label={`${fieldName} visibility`}>
      <button
        type="button"
        className={`gmail-labels-table__toggle ${value === "show" ? "gmail-labels-table__toggle--active" : ""}`}
        onClick={() => onChange("show")}
      >
        show
      </button>
      <button
        type="button"
        className={`gmail-labels-table__toggle ${value === "hide" ? "gmail-labels-table__toggle--active" : ""}`}
        onClick={() => onChange("hide")}
      >
        hide
      </button>
      {showIfUnread && (
        <button
          type="button"
          className={`gmail-labels-table__toggle ${value === "show_if_unread" ? "gmail-labels-table__toggle--active" : ""}`}
          onClick={() => onChange("show_if_unread")}
        >
          show if unread
        </button>
      )}
    </span>
  );
}

function filterActionSummary(item: FilterRule): string {
  const rule = item as ExtendedFilterRule;
  return [
    item.add_labels.length ? `Label: ${item.add_labels.join(", ")}` : "",
    item.archive ? "Archive" : "",
    item.mark_read ? "Mark read" : "",
    item.star ? "Star" : "",
    rule.never_spam ? "Never spam" : "",
    item.forward_to ? `Fwd: ${item.forward_to}` : "",
  ]
    .filter(Boolean)
    .join(" · ") || "—";
}

/* ── Helper: capitalize label name for display ── */
function labelDisplayName(name: string): string {
  if (name === "all mail") return "All Mail";
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/* ════════════════════════════════════════════════════════════════
   General Tab
   ════════════════════════════════════════════════════════════════ */

function getFeatureFlag(flag: string): boolean {
  const w = window as unknown as Record<string, unknown>;
  const flags = (w.__wabFeatureFlags ?? {}) as Record<string, unknown>;
  return Boolean(flags[flag]);
}

function UndoSendRow({
  settings,
  setSettings,
}: {
  settings: GmailSettings;
  setSettings: React.Dispatch<React.SetStateAction<GmailSettings>>;
}) {
  return (
    <div className="gmail-settings-row">
      <div className="gmail-settings-row__label">Undo Send:</div>
      <div className="gmail-settings-row__controls">
        <div className="gmail-settings-row__line">
          Send cancellation period:{" "}
          <select
            value={settings.undo_send_seconds ?? 5}
            onChange={(e) =>
              setSettings((s) => ({ ...s, undo_send_seconds: Number(e.target.value) }))
            }
            aria-label="Undo send seconds"
            className="gmail-settings-select gmail-settings-select--sm"
          >
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={30}>30</option>
          </select>{" "}
          seconds
        </div>
      </div>
    </div>
  );
}

function GeneralTab({
  settings,
  setSettings,
  onSave,
}: {
  settings: GmailSettings;
  setSettings: React.Dispatch<React.SetStateAction<GmailSettings>>;
  onSave: () => void;
}) {
  return (
    <div className="gmail-settings-table" role="table" aria-label="General settings">
      {/* Display density */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Display density:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__radios">
            {["default", "comfortable", "compact"].map((density) => (
              <label key={density}>
                <input
                  type="radio"
                  name="display_density"
                  checked={(settings.display_density ?? "comfortable") === density}
                  onChange={() => setSettings((s) => ({ ...s, display_density: density }))}
                />
                <span>{density.charAt(0).toUpperCase() + density.slice(1)}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Language */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Language:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__line">
            <strong>Gmail display language:</strong>
            <select
              value={settings.language ?? "English (US)"}
              onChange={(e) => setSettings((s) => ({ ...s, language: e.target.value }))}
              aria-label="Gmail display language"
              className="gmail-settings-select"
            >
              <option value="English (US)">English (US)</option>
              <option value="English (UK)">English (UK)</option>
              <option value="Spanish">Spanish</option>
              <option value="French">French</option>
              <option value="German">German</option>
              <option value="Japanese">Japanese</option>
              <option value="Chinese (Simplified)">Chinese (Simplified)</option>
            </select>
          </div>
          <label className="gmail-settings-row__checkbox">
            <input
              type="checkbox"
              checked={Boolean(settings.input_tools_enabled)}
              onChange={(e) => setSettings((s) => ({ ...s, input_tools_enabled: e.target.checked }))}
            />
            <span>
              <strong>Enable input tools</strong> - Use various text input tools to type in the
              language of your choice -{" "}
              <span className="gmail-settings-link">Edit tools</span> -{" "}
              <span className="gmail-settings-link">Learn more</span>
            </span>
          </label>
          <div className="gmail-settings-row__radios">
            <label>
              <input
                type="radio"
                name="rtl"
                checked={!settings.right_to_left}
                onChange={() => setSettings((s) => ({ ...s, right_to_left: false }))}
              />
              <span>Right-to-left editing support off</span>
            </label>
            <label>
              <input
                type="radio"
                name="rtl"
                checked={Boolean(settings.right_to_left)}
                onChange={() => setSettings((s) => ({ ...s, right_to_left: true }))}
              />
              <span>Right-to-left editing support on</span>
            </label>
          </div>
        </div>
      </div>

      {/* Maximum page size */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Maximum page size:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__line">
            Show{" "}
            <select
              value={settings.max_page_size ?? 50}
              onChange={(e) => setSettings((s) => ({ ...s, max_page_size: Number(e.target.value) }))}
              aria-label="Maximum page size"
              className="gmail-settings-select gmail-settings-select--sm"
            >
              <option value={10}>10</option>
              <option value={15}>15</option>
              <option value={20}>20</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>{" "}
            conversations per page
          </div>
        </div>
      </div>

      {/* Undo Send — hidden from General when relocated to Advanced via feature flag */}
      {!getFeatureFlag("undo_send_advanced") && (
        <UndoSendRow settings={settings} setSettings={setSettings} />
      )}

      {/* Auto-advance */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Auto-advance:</div>
        <div className="gmail-settings-row__controls">
          <p style={{ margin: "0 0 4px", fontSize: "0.8125rem", color: "var(--color-text-muted)" }}>
            After you delete, archive, or mute a conversation, advance to the:
          </p>
          <div className="gmail-settings-row__radios">
            {(["newer", "older", "back_to_list"] as const).map((value) => (
              <label key={value}>
                <input
                  type="radio"
                  name="auto_advance"
                  checked={(settings.auto_advance ?? "newer") === value}
                  onChange={() => setSettings((s) => ({ ...s, auto_advance: value }))}
                />
                <span>
                  {value === "newer" ? "Newer conversation" : value === "older" ? "Older conversation" : "Back to threadlist"}
                </span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Default reply behavior */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Default reply behavior:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__radios">
            <label>
              <input
                type="radio"
                name="reply_behavior"
                checked={settings.default_reply_behavior !== "reply_all"}
                onChange={() => setSettings((s) => ({ ...s, default_reply_behavior: "reply" }))}
              />
              <span>Reply</span>
            </label>
            <label>
              <input
                type="radio"
                name="reply_behavior"
                checked={settings.default_reply_behavior === "reply_all"}
                onChange={() => setSettings((s) => ({ ...s, default_reply_behavior: "reply_all" }))}
              />
              <span>Reply all</span>
            </label>
          </div>
        </div>
      </div>

      {/* Hover actions */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Hover actions:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__radios">
            <label>
              <input
                type="radio"
                name="hover_actions"
                checked={settings.hover_actions_enabled !== false}
                onChange={() => setSettings((s) => ({ ...s, hover_actions_enabled: true }))}
              />
              <span>
                <strong>Enable hover actions</strong> - Quickly gain access to archive, delete, mark
                as read, and snooze controls on hover.
              </span>
            </label>
            <label>
              <input
                type="radio"
                name="hover_actions"
                checked={settings.hover_actions_enabled === false}
                onChange={() => setSettings((s) => ({ ...s, hover_actions_enabled: false }))}
              />
              <span>Disable hover actions</span>
            </label>
          </div>
        </div>
      </div>

      {/* Send and Archive */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Send and Archive:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__radios">
            <label>
              <input
                type="radio"
                name="send_archive"
                checked={settings.send_and_archive === true}
                onChange={() => setSettings((s) => ({ ...s, send_and_archive: true }))}
              />
              <span>Show "Send & Archive" button in reply</span>
            </label>
            <label>
              <input
                type="radio"
                name="send_archive"
                checked={settings.send_and_archive !== true}
                onChange={() => setSettings((s) => ({ ...s, send_and_archive: false }))}
              />
              <span>Hide "Send & Archive" button in reply</span>
            </label>
          </div>
        </div>
      </div>

      {/* Default text style */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Default text style:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__line gmail-settings-textstyle">
            <select
              value={settings.default_text_style ?? "Sans Serif"}
              onChange={(e) => setSettings((s) => ({ ...s, default_text_style: e.target.value }))}
              aria-label="Default text style"
              className="gmail-settings-select"
            >
              <option value="Sans Serif">Sans Serif</option>
              <option value="Serif">Serif</option>
              <option value="Fixed Width">Fixed Width</option>
              <option value="Wide">Wide</option>
              <option value="Narrow">Narrow</option>
              <option value="Comic Sans MS">Comic Sans MS</option>
              <option value="Garamond">Garamond</option>
              <option value="Georgia">Georgia</option>
              <option value="Tahoma">Tahoma</option>
              <option value="Trebuchet MS">Trebuchet MS</option>
              <option value="Verdana">Verdana</option>
            </select>
            <span className="gmail-settings-textstyle__toolbar">
              <button type="button" className="gmail-settings-textstyle__btn" aria-label="Text size">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 4v3h5v12h3V7h5V4H9zm-6 8h3v7h3v-7h3V9H3v3z"/></svg>
              </button>
              <button type="button" className="gmail-settings-textstyle__btn" aria-label="Text color">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M11 2L5.5 16h2.25l1.12-3h6.25l1.12 3h2.25L13 2h-2zm-1.38 9L12 4.67 14.38 11H9.62z"/></svg>
              </button>
              <button type="button" className="gmail-settings-textstyle__btn" aria-label="Remove formatting">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3.27 5L2 6.27l6.97 6.97L6.5 19h3l1.57-3.66L16.73 21 18 19.73 3.55 5.27 3.27 5zM6 5v.18L8.82 8h2.4l-.72 1.68 2.1 2.1L14.21 8H20V5H6z"/></svg>
              </button>
            </span>
          </div>
        </div>
      </div>

      {/* Forwarding address */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Forwarding:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__line">
            Forward a copy of incoming mail to{" "}
            <input
              type="text"
              value={settings.forwarding_address ?? ""}
              onChange={(e) => setSettings((s) => ({ ...s, forwarding_address: e.target.value }))}
              placeholder="(no forwarding address)"
              aria-label="Forwarding email address"
              className="gmail-settings-input"
              style={{ width: "280px" }}
            />
          </div>
        </div>
      </div>

      {/* Signature */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Signature:</div>
        <div className="gmail-settings-row__controls">
          <textarea
            rows={4}
            value={settings.signature}
            onChange={(e) => setSettings((s) => ({ ...s, signature: e.target.value }))}
            aria-label="Email signature"
            className="gmail-settings-textarea"
          />
        </div>
      </div>

      {/* Vacation responder */}
      <div className="gmail-settings-row">
        <div className="gmail-settings-row__label">Vacation responder:</div>
        <div className="gmail-settings-row__controls">
          <div className="gmail-settings-row__radios">
            <label>
              <input
                type="radio"
                name="vacation"
                checked={!settings.vacation_responder_enabled}
                onChange={() => setSettings((s) => ({ ...s, vacation_responder_enabled: false }))}
              />
              <span>Vacation responder off</span>
            </label>
            <label>
              <input
                type="radio"
                name="vacation"
                checked={Boolean(settings.vacation_responder_enabled)}
                onChange={() => setSettings((s) => ({ ...s, vacation_responder_enabled: true }))}
              />
              <span>Vacation responder on</span>
            </label>
          </div>
          {settings.vacation_responder_enabled && (
            <textarea
              rows={4}
              value={settings.vacation_responder_message ?? ""}
              onChange={(e) =>
                setSettings((s) => ({ ...s, vacation_responder_message: e.target.value }))
              }
              aria-label="Vacation responder message"
              className="gmail-settings-textarea"
              placeholder="Vacation message"
            />
          )}
        </div>
      </div>

      {/* Save */}
      <div className="gmail-settings-row gmail-settings-row--actions">
        <div className="gmail-settings-row__label" />
        <div className="gmail-settings-row__controls">
          <Button variant="primary" aria-label="Save Gmail settings" onClick={onSave}>
            Save Changes
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   Labels Tab
   ════════════════════════════════════════════════════════════════ */

const SYSTEM_LABEL_ORDER = [
  "inbox",
  "starred",
  "snoozed",
  "important",
  "sent",
  "scheduled",
  "drafts",
  "all mail",
  "spam",
  "trash",
];

const CATEGORY_LABELS = ["promotions", "updates"];

function LabelsTab({
  labels,
  onUpdateLabel,
  onStartRenameLabel,
  onRenameDraftChange,
  onCommitRenameLabel,
  onCancelRenameLabel,
  onPromptDeleteLabel,
  editingLabel,
  canRenameLabel,
  canDeleteLabel,
}: {
  labels: Label[];
  onUpdateLabel: (
    labelId: string,
    field: "show_in_label_list" | "show_in_message_list" | "show_in_imap",
    value: string | boolean,
  ) => void;
  onStartRenameLabel: (label: Label) => void;
  onRenameDraftChange: (value: string) => void;
  onCommitRenameLabel: () => void;
  onCancelRenameLabel: () => void;
  onPromptDeleteLabel: (label: Label) => void;
  editingLabel: DraftLabel;
  canRenameLabel: boolean;
  canDeleteLabel: boolean;
}) {
  const systemLabels = SYSTEM_LABEL_ORDER
    .map((name) => labels.find((l) => l.name.toLowerCase() === name))
    .filter((l): l is Label => l != null);

  const categoryLabels = CATEGORY_LABELS
    .map((name) => labels.find((l) => l.name.toLowerCase() === name))
    .filter((l): l is Label => l != null);

  const userLabels = labels.filter(
    (l) =>
      !l.system &&
      !CATEGORY_LABELS.includes(l.name.toLowerCase()),
  );

  return (
    <div className="gmail-settings-labels" aria-label="Labels settings">
      {/* System labels */}
      <table className="gmail-labels-table" aria-label="System labels">
        <thead>
          <tr>
            <th className="gmail-labels-table__th gmail-labels-table__th--name">System labels</th>
            <th className="gmail-labels-table__th">Show in label list</th>
            <th className="gmail-labels-table__th">Show in message list</th>
            <th className="gmail-labels-table__th gmail-labels-table__th--imap">Show in IMAP</th>
          </tr>
        </thead>
        <tbody>
          {systemLabels.map((label) => (
            <LabelRow key={label.id} label={label} onUpdate={onUpdateLabel} />
          ))}
        </tbody>
      </table>

      {/* Categories */}
      <table className="gmail-labels-table" aria-label="Categories">
        <thead>
          <tr>
            <th className="gmail-labels-table__th gmail-labels-table__th--name">Categories</th>
            <th className="gmail-labels-table__th">Show in label list</th>
            <th className="gmail-labels-table__th">Show in message list</th>
            <th className="gmail-labels-table__th gmail-labels-table__th--imap">Show in IMAP</th>
          </tr>
        </thead>
        <tbody>
          {categoryLabels.map((label) => (
            <LabelRow key={label.id} label={label} onUpdate={onUpdateLabel} />
          ))}
        </tbody>
      </table>

      {/* User labels */}
      {userLabels.length > 0 && (
        <table className="gmail-labels-table" aria-label="Labels">
          <thead>
            <tr>
              <th className="gmail-labels-table__th gmail-labels-table__th--name">Labels</th>
              <th className="gmail-labels-table__th">Show in label list</th>
              <th className="gmail-labels-table__th">Show in message list</th>
              <th className="gmail-labels-table__th gmail-labels-table__th--imap">Show in IMAP</th>
              <th className="gmail-labels-table__th">Actions</th>
            </tr>
          </thead>
          <tbody>
            {userLabels.map((label) => (
              <LabelRow
                key={label.id}
                label={label}
                onUpdate={onUpdateLabel}
                editingLabel={editingLabel}
                onStartRenameLabel={onStartRenameLabel}
                onRenameDraftChange={onRenameDraftChange}
                onCommitRenameLabel={onCommitRenameLabel}
                onCancelRenameLabel={onCancelRenameLabel}
                onPromptDeleteLabel={onPromptDeleteLabel}
                canRenameLabel={canRenameLabel}
                canDeleteLabel={canDeleteLabel}
                showActions
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function LabelRow({
  label,
  onUpdate,
  editingLabel,
  onStartRenameLabel,
  onRenameDraftChange,
  onCommitRenameLabel,
  onCancelRenameLabel,
  onPromptDeleteLabel,
  canRenameLabel = false,
  canDeleteLabel = false,
  showActions = false,
}: {
  label: Label;
  onUpdate: (
    labelId: string,
    field: "show_in_label_list" | "show_in_message_list" | "show_in_imap",
    value: string | boolean,
  ) => void;
  editingLabel?: DraftLabel;
  onStartRenameLabel?: (label: Label) => void;
  onRenameDraftChange?: (value: string) => void;
  onCommitRenameLabel?: () => void;
  onCancelRenameLabel?: () => void;
  onPromptDeleteLabel?: (label: Label) => void;
  canRenameLabel?: boolean;
  canDeleteLabel?: boolean;
  showActions?: boolean;
}) {
  const visibility = getLabelVisibility(label);
  const messageListVisibility = getMessageListVisibility(label);
  const isEditing = editingLabel?.id === label.id;

  return (
    <tr className="gmail-labels-table__row">
      <td className="gmail-labels-table__td gmail-labels-table__td--name">
        {isEditing ? (
          <input
            type="text"
            value={editingLabel?.name ?? label.name}
            onChange={(event) => onRenameDraftChange?.(event.target.value)}
            aria-label={`Rename label ${label.name}`}
            className="gmail-settings-input"
            style={{ width: "100%" }}
          />
        ) : (
          labelDisplayName(label.name)
        )}
      </td>
      <td className="gmail-labels-table__td">
        {renderVisibilityButtons(
          visibility,
          (value) => onUpdate(label.id, "show_in_label_list", value),
          "label list",
          label.name.toLowerCase() !== "inbox",
        )}
      </td>
      <td className="gmail-labels-table__td">
        {renderVisibilityButtons(
          messageListVisibility,
          (value) => onUpdate(label.id, "show_in_message_list", value),
          "message list",
          label.name.toLowerCase() !== "inbox",
        )}
      </td>
      <td className="gmail-labels-table__td gmail-labels-table__td--imap">
        <label className="gmail-labels-table__imap-check">
          <input
            type="checkbox"
            checked={label.show_in_imap !== false}
            onChange={(e) => onUpdate(label.id, "show_in_imap", e.target.checked)}
          />
          Show in IMAP
        </label>
      </td>
      {showActions && (
        <td className="gmail-labels-table__td">
          <span className="gmail-labels-table__toggles">
            {isEditing ? (
              <>
                <button
                  type="button"
                  className="gmail-labels-table__toggle gmail-labels-table__toggle--active"
                  onClick={onCommitRenameLabel}
                  disabled={!canRenameLabel}
                >
                  Save
                </button>
                <button
                  type="button"
                  className="gmail-labels-table__toggle"
                  onClick={onCancelRenameLabel}
                >
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="gmail-labels-table__toggle"
                  onClick={() => onStartRenameLabel?.(label)}
                  disabled={!canRenameLabel}
                >
                  Rename
                </button>
                <button
                  type="button"
                  className="gmail-labels-table__toggle"
                  onClick={() => onPromptDeleteLabel?.(label)}
                  disabled={!canDeleteLabel}
                >
                  Delete
                </button>
              </>
            )}
          </span>
        </td>
      )}
    </tr>
  );
}

/* ════════════════════════════════════════════════════════════════
   Filters Tab (Filters and Blocked Addresses)
   ════════════════════════════════════════════════════════════════ */

function FiltersTab({
  filters,
  onDeleteFilter,
  onOpenCreateFilter,
}: {
  filters: FilterRule[];
  onDeleteFilter: (id: string) => void;
  onOpenCreateFilter: () => void;
}) {
  return (
    <div className="gmail-settings-filters">
      <p style={{ margin: "0 0 0.75rem", fontSize: "0.875rem", color: "var(--color-text-muted)" }}>
        The following filters are applied to incoming mail:
      </p>
      <DataTable
        label="Current filters"
        columns={[
          { key: "name", header: "Name", render: (item) => item.name },
          { key: "query", header: "Matches", render: (item) => item.query || "—" },
          {
            key: "action",
            header: "Action",
            render: (item) => filterActionSummary(item),
          },
          {
            key: "delete",
            header: "",
            render: (item) => (
              <button
                type="button"
                className="gmail-toolbar__icon-btn"
                aria-label={`Delete filter ${item.name}`}
                onClick={() => onDeleteFilter(item.id)}
              >
                <IconDelete />
              </button>
            ),
          },
        ]}
        rows={filters}
      />
      <div style={{ marginTop: "0.75rem" }}>
        <Button variant="secondary" onClick={onOpenCreateFilter} aria-label="Create a new filter">
          Create a new filter
        </Button>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   Main Settings Page
   ════════════════════════════════════════════════════════════════ */

export function SettingsPage() {
  const { api, notify } = useGmailLayout();
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState("General");
  const [settings, setSettings] = useState<GmailSettings>(DEFAULT_SETTINGS);
  const [labels, setLabels] = useState<Label[]>([]);
  const [filters, setFilters] = useState<FilterRule[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [filterWizardStep, setFilterWizardStep] = useState<"criteria" | "actions">("criteria");
  const [newFilter, setNewFilter] = useState<DraftFilter>(EMPTY_DRAFT_FILTER);
  const [editingLabel, setEditingLabel] = useState<DraftLabel>(null);
  const [deleteLabelTarget, setDeleteLabelTarget] = useState<Label | null>(null);
  const gmailApi = api as unknown as {
    getSettings: () => Promise<GmailSettings>;
    getLabels: () => Promise<Label[]>;
    getFilters: () => Promise<FilterRule[]>;
    updateSettings: (payload: GmailSettings) => Promise<GmailSettings>;
    updateLabel: (
      labelId: string,
      payload: Record<string, string | boolean>,
    ) => Promise<Label>;
    renameLabel?: (labelId: string, payload: { name: string }) => Promise<Label>;
    deleteLabel?: (labelId: string) => Promise<void>;
    createFilter: (payload: Record<string, unknown>) => Promise<FilterRule>;
    deleteFilter: (filterId: string) => Promise<void>;
  };
  const canRenameLabel = typeof gmailApi.renameLabel === "function";
  const canDeleteLabel = typeof gmailApi.deleteLabel === "function";
  const isReplayMode = searchParams.get("replay") === "1";

  useEffect(() => {
    gmailApi.getSettings().then(setSettings).catch(() => setSettings(DEFAULT_SETTINGS));
    gmailApi.getLabels().then(setLabels);
    gmailApi.getFilters().then(setFilters);
  }, [gmailApi]);

  const replayActiveTab = isReplayMode
    ? searchParams.get("tab") ?? "General"
    : activeTab;
  const replaySettings = useMemo(() => {
    if (!isReplayMode) {
      return settings;
    }

    return {
      ...settings,
      signature: searchParams.get("replaySignature") ?? settings.signature,
      vacation_responder_message:
        searchParams.get("replayVacationMessage") ?? settings.vacation_responder_message,
      forwarding_address:
        searchParams.get("replayForwardingAddress") ?? settings.forwarding_address,
      undo_send_seconds: searchParams.has("replayUndoSendSeconds")
        ? Number(searchParams.get("replayUndoSendSeconds"))
        : settings.undo_send_seconds,
      max_page_size: searchParams.has("replayMaxPageSize")
        ? Number(searchParams.get("replayMaxPageSize"))
        : settings.max_page_size,
      language: searchParams.get("replayLanguage") ?? settings.language,
      default_reply_behavior:
        searchParams.get("replayDefaultReplyBehavior") ?? settings.default_reply_behavior,
      display_density: searchParams.get("replayDisplayDensity") ?? settings.display_density,
      vacation_responder_enabled: searchParams.has("replayVacationEnabled")
        ? searchParams.get("replayVacationEnabled") === "1"
        : settings.vacation_responder_enabled,
      send_and_archive: searchParams.has("replaySendAndArchive")
        ? searchParams.get("replaySendAndArchive") === "1"
        : settings.send_and_archive,
    };
  }, [isReplayMode, searchParams, settings]);
  const replayEditingLabel = useMemo(() => {
    if (!isReplayMode) {
      return editingLabel;
    }

    const labelId = searchParams.get("replayRenameLabelId");
    if (!labelId) {
      return null;
    }

    const currentLabel = labels.find((label) => label.id === labelId);
    return {
      id: labelId,
      name: searchParams.get("replayRenameLabelDraft") ?? currentLabel?.name ?? "",
    };
  }, [editingLabel, isReplayMode, labels, searchParams]);
  const replayFilterWizardOpen = isReplayMode
    ? searchParams.get("replayFilterModal") === "1"
    : isModalOpen;
  const replayFilterWizardStep = isReplayMode
    ? (searchParams.get("replayFilterStep") === "actions" ? "actions" : "criteria")
    : filterWizardStep;
  const replayFilter = isReplayMode
    ? {
        ...EMPTY_DRAFT_FILTER,
        name: searchParams.get("replayFilterName") ?? "",
        fromPattern: searchParams.get("replayFilterFrom") ?? "",
        subjectPhrase: searchParams.get("replayFilterSubject") ?? "",
        addLabelsText: searchParams.get("replayFilterLabels") ?? "",
        forwardTo: searchParams.get("replayFilterForward") ?? "",
        hasAttachment: searchParams.get("replayFilterHasAttachment") === "1",
        archive: searchParams.get("replayFilterArchive") === "1",
        markRead: searchParams.get("replayFilterMarkRead") === "1",
        star: searchParams.get("replayFilterStar") === "1",
        neverSpam: searchParams.get("replayFilterNeverSpam") === "1",
      }
    : newFilter;

  const handleSaveSettings = async () => {
    const next = await gmailApi.updateSettings(settings);
    setSettings(next);
    notify("Settings saved");
  };

  const handleUpdateLabel = async (
    labelId: string,
    field: "show_in_label_list" | "show_in_message_list" | "show_in_imap",
    value: string | boolean,
  ) => {
    const updated = await gmailApi.updateLabel(labelId, { [field]: value });
    setLabels((current) => current.map((l) => (l.id === updated.id ? updated : l)));
  };

  const handleStartRenameLabel = (label: Label) => {
    setEditingLabel({ id: label.id, name: label.name });
  };

  const handleRenameDraftChange = (value: string) => {
    setEditingLabel((current) => (current ? { ...current, name: value } : current));
  };

  const handleCancelRenameLabel = () => {
    setEditingLabel(null);
  };

  const handleCommitRenameLabel = async () => {
    if (!editingLabel) {
      return;
    }
    const nextName = editingLabel.name.trim();
    if (!nextName) {
      notify("Label name cannot be empty");
      return;
    }
    if (typeof gmailApi.renameLabel !== "function") {
      notify("Label rename is not wired up yet", nextName);
      return;
    }
    const updated = await gmailApi.renameLabel(editingLabel.id, { name: nextName });
    setLabels((current) => current.map((l) => (l.id === updated.id ? updated : l)));
    setEditingLabel(null);
    notify("Label renamed", updated.name);
  };

  const handlePromptDeleteLabel = (label: Label) => {
    setDeleteLabelTarget(label);
  };

  const handleDeleteLabel = async () => {
    if (!deleteLabelTarget) {
      return;
    }
    if (typeof gmailApi.deleteLabel !== "function") {
      notify("Label delete is not wired up yet", deleteLabelTarget.name);
      return;
    }
    await gmailApi.deleteLabel(deleteLabelTarget.id);
    setLabels((current) => current.filter((label) => label.id !== deleteLabelTarget.id));
    notify("Label deleted", deleteLabelTarget.name);
    setDeleteLabelTarget(null);
  };

  const handleDeleteFilter = async (filterId: string) => {
    await gmailApi.deleteFilter(filterId);
    setFilters((current) => current.filter((f) => f.id !== filterId));
    notify("Filter deleted");
  };

  const resetFilterWizard = () => {
    setIsModalOpen(false);
    setFilterWizardStep("criteria");
    setNewFilter(EMPTY_DRAFT_FILTER);
  };

  const openCreateFilter = () => {
    setNewFilter(EMPTY_DRAFT_FILTER);
    setFilterWizardStep("criteria");
    setIsModalOpen(true);
  };

  const saveNewFilter = async () => {
    const query = buildFilterQuery(newFilter);
    const created = await gmailApi.createFilter({
      name: newFilter.name,
      query,
      from_addresses: newFilter.fromPattern.trim()
        ? newFilter.fromPattern.split(",").map((s) => s.trim()).filter(Boolean)
        : [],
      subject_keywords: newFilter.subjectPhrase.trim() ? [newFilter.subjectPhrase.trim()] : [],
      label_requirements: [],
      has_attachment: newFilter.hasAttachment ? true : null,
      add_labels: newFilter.addLabelsText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      archive: newFilter.archive,
      mark_read: newFilter.markRead,
      never_spam: newFilter.neverSpam,
      forward_to: newFilter.forwardTo.trim() || null,
      star: newFilter.star,
    });
    setFilters((current) => [...current, created]);
    resetFilterWizard();
    notify("Filter created", created.name);
  };

  return (
    <main className="gmail-page gmail-page--settings" aria-label="Settings">
      {/* Settings header */}
      <div className="gmail-settings-header">
        <h1 className="gmail-settings-header__title">Settings</h1>
      </div>

      {/* Tab bar */}
      <nav className="gmail-settings-tabs" aria-label="Settings tabs">
        <div className="gmail-settings-tabs__row" role="tablist">
          {SETTINGS_TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`gmail-settings-tabs__tab ${replayActiveTab === tab ? "gmail-settings-tabs__tab--active" : ""}`}
              onClick={() => setActiveTab(tab)}
              aria-selected={replayActiveTab === tab}
              role="tab"
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="gmail-settings-tabs__row" role="tablist">
          {SETTINGS_TABS_SECONDARY.map((tab) => (
            <button
              key={tab}
              type="button"
              className={`gmail-settings-tabs__tab ${replayActiveTab === tab ? "gmail-settings-tabs__tab--active" : ""}`}
              onClick={() => setActiveTab(tab)}
              aria-selected={replayActiveTab === tab}
              role="tab"
            >
              {tab}
            </button>
          ))}
        </div>
      </nav>

      {/* Tab content */}
      <div className="gmail-settings-content">
        {replayActiveTab === "General" && (
          <GeneralTab settings={replaySettings} setSettings={setSettings} onSave={handleSaveSettings} />
        )}
        {replayActiveTab === "Labels" && (
          <LabelsTab
            labels={labels}
            onUpdateLabel={handleUpdateLabel}
            onStartRenameLabel={handleStartRenameLabel}
            onRenameDraftChange={handleRenameDraftChange}
            onCommitRenameLabel={handleCommitRenameLabel}
            onCancelRenameLabel={handleCancelRenameLabel}
            onPromptDeleteLabel={handlePromptDeleteLabel}
            editingLabel={replayEditingLabel}
            canRenameLabel={canRenameLabel}
            canDeleteLabel={canDeleteLabel}
          />
        )}
        {replayActiveTab === "Filters and Blocked Addresses" && (
          <FiltersTab
            filters={filters}
            onDeleteFilter={handleDeleteFilter}
            onOpenCreateFilter={openCreateFilter}
          />
        )}
        {activeTab === "Advanced" && getFeatureFlag("undo_send_advanced") && (
          <div className="gmail-settings-table" role="table" aria-label="Advanced settings">
            <UndoSendRow settings={settings} setSettings={setSettings} />
            <div className="gmail-settings-row gmail-settings-row--actions">
              <div className="gmail-settings-row__label" />
              <div className="gmail-settings-row__controls">
                <Button variant="primary" aria-label="Save Gmail settings" onClick={handleSaveSettings}>
                  Save Changes
                </Button>
              </div>
            </div>
          </div>
        )}
        {!["General", "Labels", "Filters and Blocked Addresses"].includes(activeTab) &&
          !(activeTab === "Advanced" && getFeatureFlag("undo_send_advanced")) && (
          <div className="gmail-settings-placeholder">
            <p>
              {replayActiveTab} settings are not available in this environment.
            </p>
          </div>
        )}
      </div>

      {/* Create filter modal */}
      <Modal
        open={replayFilterWizardOpen}
        title={replayFilterWizardStep === "criteria" ? "Create a filter" : "Choose what happens next"}
        description={
          replayFilterWizardStep === "criteria"
            ? "Step 1 of 2: define which messages should match this filter."
            : "Step 2 of 2: choose what Gmail should do when a message matches."
        }
        onClose={resetFilterWizard}
        footer={
          replayFilterWizardStep === "criteria" ? (
            <>
              <Button variant="ghost" onClick={resetFilterWizard} aria-label="Cancel filter creation">
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => setFilterWizardStep("actions")}
                aria-label="Continue to filter actions"
                disabled={buildFilterQuery(replayFilter) === ""}
              >
                Continue
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                onClick={() => setFilterWizardStep("criteria")}
                aria-label="Back to filter criteria"
              >
                Back
              </Button>
              <Button
                variant="primary"
                onClick={saveNewFilter}
                aria-label="Save new filter"
                disabled={!hasFilterAction(replayFilter)}
              >
                Create filter
              </Button>
            </>
          )
        }
      >
        {replayFilterWizardStep === "criteria" ? (
          <div className="gmail-modal-grid">
            <FormField
              id="new-filter-from"
              label="From"
              hint="Use a sender address or a whole domain like @vendor.com."
              inputProps={{
                value: replayFilter.fromPattern,
                onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                  setNewFilter((current) => ({ ...current, fromPattern: event.target.value })),
                placeholder: "finance@acme.com or @vendor.com",
                "aria-label": "Filter from address",
              }}
            />
            <FormField
              id="new-filter-subject"
              label="Subject"
              hint="Use a short phrase that should appear in the subject line."
              inputProps={{
                value: replayFilter.subjectPhrase,
                onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                  setNewFilter((current) => ({ ...current, subjectPhrase: event.target.value })),
                placeholder: "Payroll Exception",
                "aria-label": "Filter subject phrase",
              }}
            />
            <label className="gmail-settings-card__checkbox">
              <input
                type="checkbox"
                checked={replayFilter.hasAttachment}
                onChange={(event) => setNewFilter((current) => ({ ...current, hasAttachment: event.target.checked }))}
              />
              <span>Has attachment</span>
            </label>
            <div className="gmail-settings-summary-card" aria-label="Filter criteria preview">
              <strong>Matches</strong>
              <p>{filterCriteriaSummary(replayFilter)}</p>
            </div>
          </div>
        ) : (
          <div className="gmail-modal-grid">
            <div className="gmail-settings-summary-card" aria-label="Current filter criteria">
              <strong>Matches</strong>
              <p>{filterCriteriaSummary(replayFilter)}</p>
            </div>
            <FormField
              id="new-filter-labels"
              label="Apply labels"
              inputProps={{
                value: replayFilter.addLabelsText,
                onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                  setNewFilter((current) => ({ ...current, addLabelsText: event.target.value })),
                placeholder: "Billing Vendors, Payroll",
                "aria-label": "Filter labels",
              }}
            />
            <FormField
              id="new-filter-forward"
              label="Forward to"
              inputProps={{
                value: replayFilter.forwardTo,
                onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                  setNewFilter((current) => ({ ...current, forwardTo: event.target.value })),
                placeholder: "chief-of-staff@example.com",
                "aria-label": "Filter forward address",
              }}
            />
            <FormField
              id="new-filter-name"
              label="Filter name"
              hint="Optional. If blank, Gmail will use the criteria summary."
              inputProps={{
                value: replayFilter.name,
                onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                  setNewFilter((current) => ({ ...current, name: event.target.value })),
                "aria-label": "Filter name",
              }}
            />
            <label className="gmail-settings-card__checkbox">
              <input
                type="checkbox"
                checked={replayFilter.archive}
                onChange={(event) => setNewFilter((current) => ({ ...current, archive: event.target.checked }))}
              />
              <span>Skip Inbox (Archive it)</span>
            </label>
            <label className="gmail-settings-card__checkbox">
              <input
                type="checkbox"
                checked={replayFilter.markRead}
                onChange={(event) => setNewFilter((current) => ({ ...current, markRead: event.target.checked }))}
              />
              <span>Mark as read</span>
            </label>
            <label className="gmail-settings-card__checkbox">
              <input
                type="checkbox"
                checked={replayFilter.star}
                onChange={(event) => setNewFilter((current) => ({ ...current, star: event.target.checked }))}
              />
              <span>Star it</span>
            </label>
            <label className="gmail-settings-card__checkbox">
              <input
                type="checkbox"
                checked={replayFilter.neverSpam}
                onChange={(event) =>
                  setNewFilter((current) => ({ ...current, neverSpam: event.target.checked }))
                }
              />
              <span>Never spam</span>
            </label>
          </div>
        )}
      </Modal>

      <Modal
        open={deleteLabelTarget != null}
        title="Delete label"
        description={
          deleteLabelTarget
            ? `Remove the label "${deleteLabelTarget.name}" from Gmail.`
            : ""
        }
        onClose={() => setDeleteLabelTarget(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteLabelTarget(null)} aria-label="Cancel delete label">
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleDeleteLabel}
              aria-label="Confirm delete label"
              disabled={typeof gmailApi.deleteLabel !== "function"}
            >
              Delete label
            </Button>
          </>
        }
      >
        <p style={{ margin: 0 }}>
          {deleteLabelTarget
            ? `Deleting "${deleteLabelTarget.name}" removes it from the current label list.`
            : ""}
        </p>
      </Modal>
    </main>
  );
}
