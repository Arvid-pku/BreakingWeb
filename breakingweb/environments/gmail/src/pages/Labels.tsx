import { useEffect, useState } from "react";
import { Button, DataTable, FormField } from "@breakingweb/shared";
import { useSearchParams } from "react-router-dom";

import { LabelChip } from "../components/LabelChip";
import { useGmailLayout } from "../context";
import { IconChevronLeft, IconChevronRight, IconDelete, IconStar } from "../icons";
import type { Contact, Label } from "../types";

const CONTACTS_PAGE_SIZE = 8;

type ContactRecord = Contact & {
  starred?: boolean;
  is_starred?: boolean;
};

type ContactMutationApi = {
  toggleContactStar?: (contactId: string) => Promise<unknown>;
  setContactStar?: (contactId: string, starred: boolean) => Promise<unknown>;
  updateContact?: (contactId: string, payload: { starred?: boolean; is_starred?: boolean }) => Promise<unknown>;
};

const EMPTY_CONTACT_DRAFT = {
  name: "",
  email: "",
  company: "",
  note: "",
  is_vip: false,
};

function formatRelativeDate(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "1 day ago";
  return `${diffDays} days ago`;
}

function isContactStarred(contact: ContactRecord): boolean {
  return Boolean(contact.starred ?? contact.is_starred ?? false);
}

function extractContactRecord(result: unknown): ContactRecord | null {
  if (!result || typeof result !== "object") {
    return null;
  }

  const payload = result as { contact?: ContactRecord; id?: string };
  if (payload.contact && typeof payload.contact === "object") {
    return payload.contact;
  }
  if (typeof payload.id === "string") {
    return result as ContactRecord;
  }

  return null;
}

function contactToDraft(contact: ContactRecord) {
  return {
    name: contact.name,
    email: contact.email,
    company: contact.company ?? "",
    note: contact.note ?? "",
    is_vip: Boolean(contact.is_vip),
  };
}

function sortContacts(items: ContactRecord[]): ContactRecord[] {
  return [...items].sort((left, right) => left.name.localeCompare(right.name));
}

function optionalContactValue(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

export function LabelsPage() {
  const { api, notify, summary, refreshMailbox } = useGmailLayout();
  const [searchParams] = useSearchParams();
  const [labels, setLabels] = useState<Label[]>([]);
  const [contacts, setContacts] = useState<ContactRecord[]>([]);
  const [draftLabel, setDraftLabel] = useState({ name: "", color: "#1a73e8" });
  const [draftContact, setDraftContact] = useState(EMPTY_CONTACT_DRAFT);
  const [editingContactId, setEditingContactId] = useState<string | null>(null);
  const [contactPage, setContactPage] = useState(1);
  const isReplayMode = searchParams.get("replay") === "1";

  useEffect(() => {
    api.getLabels().then(setLabels);
    api.getContacts().then((items) => setContacts(sortContacts(items)));
  }, [api]);

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(contacts.length / CONTACTS_PAGE_SIZE));
    if (contactPage > totalPages) {
      setContactPage(totalPages);
    }
  }, [contactPage, contacts.length]);

  const resetContactForm = () => {
    setDraftContact({ ...EMPTY_CONTACT_DRAFT });
    setEditingContactId(null);
  };

  const handleCreateLabel = async (event?: React.FormEvent<HTMLFormElement>) => {
    event?.preventDefault();

    const labelName = draftLabel.name.trim();
    if (labelName === "") {
      return;
    }

    const created = await api.createLabel({ ...draftLabel, name: labelName });
    setLabels((current) => [...current, created]);
    setDraftLabel({ name: "", color: "#1a73e8" });
    notify("Label created", created.name);
    await refreshMailbox();
  };

  const handleStartEditContact = (contact: ContactRecord) => {
    setEditingContactId(contact.id);
    setDraftContact(contactToDraft(contact));
  };

  const handleSaveContact = async () => {
    const payload = {
      name: draftContact.name.trim(),
      email: draftContact.email.trim(),
      company: optionalContactValue(draftContact.company),
      note: optionalContactValue(draftContact.note),
      is_vip: draftContact.is_vip,
    };

    if (editingContactId) {
      const updated = await api.updateContact(editingContactId, payload) as ContactRecord;
      setContacts((current) =>
        sortContacts(current.map((item) => (item.id === editingContactId ? { ...item, ...updated } : item))),
      );
      notify("Contact updated", updated.name);
      resetContactForm();
      return;
    }

    const created = await api.createContact(payload as Omit<Contact, "id">);
    setContacts((current) => sortContacts([...current, created as ContactRecord]));
    notify("Contact added", created.name);
    resetContactForm();
  };

  const handleToggleContactStar = async (contact: ContactRecord) => {
    const contactApi = api as ContactMutationApi;
    const nextStarred = !isContactStarred(contact);

    let result: unknown;
    if (contactApi.toggleContactStar) {
      result = await contactApi.toggleContactStar(contact.id);
    } else if (contactApi.setContactStar) {
      result = await contactApi.setContactStar(contact.id, nextStarred);
    } else if (contactApi.updateContact) {
      result = await contactApi.updateContact(contact.id, {
        starred: nextStarred,
        is_starred: nextStarred,
      });
    } else {
      throw new Error("Contact star toggle is not available");
    }

    const updatedContact = extractContactRecord(result) ?? {
      ...contact,
      starred: nextStarred,
      is_starred: nextStarred,
    };

    setContacts((current) => current.map((item) => (item.id === contact.id ? { ...item, ...updatedContact } : item)));
    notify(nextStarred ? "Contact starred" : "Contact unstarred", contact.name);
  };

  const editingContact = editingContactId
    ? contacts.find((contact) => contact.id === editingContactId) ?? null
    : null;
  const replayEditingContact = isReplayMode
    ? (
      searchParams.get("replayContactEditId")
        ? contacts.find((contact) => contact.id === searchParams.get("replayContactEditId")) ?? null
        : null
    )
    : editingContact;
  const displayDraftLabel = isReplayMode
    ? {
        name: searchParams.get("replayNewLabelName") ?? "",
        color: "#1a73e8",
      }
    : draftLabel;
  const displayDraftContact = isReplayMode
    ? {
        ...EMPTY_CONTACT_DRAFT,
        name: searchParams.get("replayContactName") ?? "",
        email: searchParams.get("replayContactEmail") ?? "",
        company: searchParams.get("replayContactCompany") ?? "",
        note: searchParams.get("replayContactNote") ?? "",
        is_vip: searchParams.get("replayContactVip") === "1",
      }
    : draftContact;
  const displayContactPage = isReplayMode
    ? Math.max(
        1,
        Math.min(
          Math.max(1, Math.ceil(contacts.length / CONTACTS_PAGE_SIZE)),
          Number(searchParams.get("replayContactPage") ?? 1),
        ),
      )
    : contactPage;
  const isEditingContact = replayEditingContact !== null;
  const visibleContacts = contacts.slice(
    (displayContactPage - 1) * CONTACTS_PAGE_SIZE,
    displayContactPage * CONTACTS_PAGE_SIZE,
  );

  return (
    <main className="gmail-page gmail-page--labels" aria-label="Labels and contacts">
      <header className="gmail-page__header">
        <div>
          <h1>Labels & contacts</h1>
        </div>
      </header>

      <section className="gmail-settings-grid">
        <section className="wab-card gmail-settings-card" aria-label="Labels">
          <h2>Labels</h2>
          <form
            className="gmail-label-form"
            aria-label="Create a new label"
            onSubmit={(event) => {
              void handleCreateLabel(event);
            }}
          >
            <div className="gmail-label-form__header">
              <h3>Create a label</h3>
              <p className="gmail-label-form__helper">
                Enter a label name and press Enter, or use the create button below.
              </p>
            </div>
            <div className="gmail-modal-grid">
              <FormField
                id="new-label-name"
                label="New label"
                inputProps={{
                  value: displayDraftLabel.name,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftLabel((current) => ({ ...current, name: event.target.value })),
                  placeholder: "Important Projects",
                  "aria-label": "New label name",
                  autoFocus: true,
                }}
              />
              <FormField
                id="new-label-color"
                label="Color"
                inputProps={{
                  type: "color",
                  value: displayDraftLabel.color,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftLabel((current) => ({ ...current, color: event.target.value })),
                  "aria-label": "New label color",
                }}
              />
            </div>
            <div className="gmail-label-form__actions">
              <Button
                variant="primary"
                type="submit"
                aria-label={displayDraftLabel.name.trim() ? `Create label ${displayDraftLabel.name.trim()}` : "Create label"}
                disabled={displayDraftLabel.name.trim() === ""}
              >
                {displayDraftLabel.name.trim() ? `Create label "${displayDraftLabel.name.trim()}"` : "Create label"}
              </Button>
            </div>
          </form>

          <div className="gmail-label-list__header">
            <h3>Existing labels</h3>
            <p>Review the current label counts below.</p>
          </div>
          <div className="gmail-label-list">
            {labels.map((label) => (
              <div key={label.id} className="gmail-label-list__item">
                <LabelChip label={label} />
                <span style={{ color: "var(--color-text-muted)" }}>
                  {summary?.counts[label.id] ?? summary?.counts[label.name.toLowerCase()] ?? 0} threads
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="gmail-settings-card" aria-label="Contacts">
          <h2>Contacts</h2>
          <DataTable
            label="Recent contacts"
            columns={[
              { key: "name", header: "Name", render: (item) => item.name },
              { key: "email", header: "Email", render: (item) => item.email },
              { key: "company", header: "Company", render: (item) => item.company ?? "—" },
              { key: "note", header: "Note", render: (item) => item.note ?? "—" },
              {
                key: "edit",
                header: "",
                render: (item) => (
                  <button
                    type="button"
                    className="gmail-labels-table__toggle"
                    aria-label={`Edit contact ${item.name}`}
                    onClick={() => handleStartEditContact(item)}
                  >
                    Edit
                  </button>
                ),
              },
              {
                key: "star",
                header: "Star",
                render: (item) => (
                  <button
                    type="button"
                    className="gmail-toolbar__icon-btn"
                    aria-label={isContactStarred(item) ? `Unstar contact ${item.name}` : `Star contact ${item.name}`}
                    onClick={async (event) => {
                      event.stopPropagation();
                      await handleToggleContactStar(item);
                    }}
                  >
                    <IconStar filled={isContactStarred(item)} />
                  </button>
                ),
              },
              {
                key: "last_contact",
                header: "Last Contact",
                render: (item) => formatRelativeDate(item.last_contacted_at),
              },
              { key: "vip", header: "VIP", render: (item) => (item.is_vip ? "Yes" : "No") },
              {
                key: "delete",
                header: "",
                render: (item) => (
                  <button
                    type="button"
                    className="gmail-toolbar__icon-btn"
                    aria-label={`Delete contact ${item.name}`}
                    onClick={async () => {
                      await api.deleteContact(item.id);
                      setContacts((current) => current.filter((c) => c.id !== item.id));
                      notify("Contact deleted", item.name);
                    }}
                  >
                    <IconDelete />
                  </button>
                ),
              },
            ]}
            rows={visibleContacts}
          />
          {contacts.length > CONTACTS_PAGE_SIZE && (
            <div className="gmail-toolbar__right" style={{ marginTop: 8 }}>
              <span className="gmail-toolbar__page-info">
                {(displayContactPage - 1) * CONTACTS_PAGE_SIZE + 1}–
                {Math.min(displayContactPage * CONTACTS_PAGE_SIZE, contacts.length)} of {contacts.length}
              </span>
              <button
                type="button"
                className="gmail-toolbar__nav-btn"
                aria-label="Previous contacts page"
                disabled={displayContactPage <= 1}
                onClick={() => setContactPage((p) => p - 1)}
              >
                <IconChevronLeft />
              </button>
              <button
                type="button"
                className="gmail-toolbar__nav-btn"
                aria-label="Next contacts page"
                disabled={displayContactPage >= Math.ceil(contacts.length / CONTACTS_PAGE_SIZE)}
                onClick={() => setContactPage((p) => p + 1)}
              >
                <IconChevronRight />
              </button>
            </div>
          )}
          <div
            className="gmail-add-contact-form"
            aria-label={isEditingContact ? "Edit selected contact" : "Add a new contact"}
          >
            <h3>{isEditingContact ? "Edit contact" : "Add contact"}</h3>
            <p className="gmail-contact-form__helper">
              {isEditingContact
                ? `Updating ${replayEditingContact?.name}.`
                : "Use Edit in the table to update an existing contact, or fill out this form to add a new one."}
            </p>
            <div className="gmail-modal-grid">
              <FormField
                id="new-contact-name"
                label="Name"
                inputProps={{
                  value: displayDraftContact.name,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftContact((c) => ({ ...c, name: event.target.value })),
                  "aria-label": "Contact name",
                }}
              />
              <FormField
                id="new-contact-email"
                label="Email"
                inputProps={{
                  value: displayDraftContact.email,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftContact((c) => ({ ...c, email: event.target.value })),
                  "aria-label": "Contact email address",
                }}
              />
              <FormField
                id="new-contact-company"
                label="Company"
                inputProps={{
                  value: displayDraftContact.company,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftContact((c) => ({ ...c, company: event.target.value })),
                  "aria-label": "Contact company",
                }}
              />
              <FormField
                id="new-contact-note"
                label="Note"
                inputProps={{
                  value: displayDraftContact.note,
                  onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
                    setDraftContact((c) => ({ ...c, note: event.target.value })),
                  placeholder: "Optional note",
                  "aria-label": "Contact note",
                }}
              />
            </div>
            <label className="gmail-checkbox-label" style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
              <input
                type="checkbox"
                checked={displayDraftContact.is_vip}
                onChange={(event) =>
                  setDraftContact((c) => ({ ...c, is_vip: event.target.checked }))
                }
                aria-label="Mark as VIP contact"
              />
              VIP contact
            </label>
            <div className="gmail-contact-form__actions">
              <Button
                variant="primary"
                aria-label={isEditingContact ? "Save contact changes" : "Add contact"}
                disabled={displayDraftContact.name.trim() === "" || displayDraftContact.email.trim() === ""}
                onClick={handleSaveContact}
              >
                {isEditingContact ? "Save contact" : "Add contact"}
              </Button>
              {isEditingContact ? (
                <Button
                  variant="secondary"
                  aria-label="Cancel contact editing"
                  onClick={resetContactForm}
                >
                  Cancel
                </Button>
              ) : null}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
