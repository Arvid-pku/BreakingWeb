import type { RouteMutator } from "@breakingweb/shared";

import type {
  Attachment,
  Contact,
  Email,
  FilterRule,
  GmailSettings,
  Label,
} from "./types";

/* ------------------------------------------------------------------ */
/*  GmailFixture — matches the JSON fixture shape                     */
/* ------------------------------------------------------------------ */

export interface GmailFixture {
  env_id: string;
  task_id: string;
  owner_name: string;
  owner_email: string;
  emails: Email[];
  sent: Email[];
  deleted: Email[];
  drafts: Email[];
  labels: Label[];
  filters: FilterRule[];
  contacts: Contact[];
  settings: GmailSettings;
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

let _idCounter = 0;
function genId(prefix: string): string {
  return `${prefix}_${Date.now()}_${++_idCounter}`;
}

function snippet(body: string): string {
  return body.split(/\s+/).join(" ").slice(0, 140);
}

function normalizeRecipient(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }

  const match = trimmed.match(/<\s*([^\s<>]+@[^\s<>]+)\s*>/);
  if (match) {
    return match[1].toLowerCase();
  }

  return trimmed.includes("@") ? trimmed.toLowerCase() : trimmed;
}

function normalizeRecipients(values: string[] | undefined): string[] {
  return (values ?? [])
    .map((value) => normalizeRecipient(String(value)))
    .filter(Boolean);
}

function threadSize(state: GmailFixture, threadId: string): number {
  return allMail(state).filter((e) => e.thread_id === threadId).length;
}

function allMail(state: GmailFixture): Email[] {
  return [...state.emails, ...state.sent, ...state.deleted].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );
}

function serializeEmail(state: GmailFixture, email: Email): Email {
  return {
    ...email,
    snippet: snippet(email.body),
    thread_size: threadSize(state, email.thread_id),
  };
}

function getThread(state: GmailFixture, threadId: string): Email[] {
  return allMail(state)
    .filter((e) => e.thread_id === threadId)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
}

function findEmail(state: GmailFixture, emailId: string): Email | null {
  for (const col of [state.emails, state.sent, state.deleted]) {
    const found = col.find((e) => e.id === emailId);
    if (found) return found;
  }
  return null;
}

function requireEmail(state: GmailFixture, emailId: string): Email {
  const email = findEmail(state, emailId);
  if (!email) throw new Error(`Unknown email id: ${emailId}`);
  return email;
}

function listEmails(
  state: GmailFixture,
  label: string,
  q?: string | null,
): Email[] {
  label = label || "inbox";
  let items: Email[];
  if (label === "sent") {
    items = [...state.sent];
  } else if (label === "trash" || label === "deleted") {
    items = [...state.deleted];
  } else {
    items = state.emails.filter((e) => !e.labels.includes("trash"));
    if (label === "archived") {
      // archived emails have had "inbox" removed
      items = items.filter(
        (e) => !e.labels.includes("inbox") && !e.labels.includes("trash"),
      );
    } else if (label !== "all") {
      items = items.filter((e) => e.labels.includes(label));
    }
  }
  if (q) {
    const lower = q.toLowerCase();
    items = items.filter((e) => emailMatchesSimple(e, lower));
  }
  return items.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );
}

function emailMatchesSimple(email: Email, lower: string): boolean {
  return (
    email.subject.toLowerCase().includes(lower) ||
    email.body.toLowerCase().includes(lower) ||
    email.from_name.toLowerCase().includes(lower) ||
    email.from_addr.toLowerCase().includes(lower) ||
    email.to.join(" ").toLowerCase().includes(lower)
  );
}

function countUnread(state: GmailFixture, label: string): number {
  return listEmails(state, label).filter((e) => !e.is_read).length;
}

function mailboxCounts(state: GmailFixture): Record<string, number> {
  const labelsByName = new Map(
    state.labels.map((label) => [label.name.toLowerCase(), label]),
  );
  const counts: Record<string, number> = {
    archived: listEmails(state, "archived").length,
    unread_inbox: countUnread(state, "inbox"),
  };

  for (const label of state.labels) {
    counts[label.name.toLowerCase()] = 0;
    counts[label.id] = 0;
  }

  for (const email of state.emails) {
    for (const labelName of email.labels) {
      const normalized = labelName.toLowerCase();
      counts[normalized] = (counts[normalized] ?? 0) + 1;
      const label = labelsByName.get(normalized);
      if (label) {
        counts[label.id] = (counts[label.id] ?? 0) + 1;
      }
    }
  }

  const sentCount = state.sent.length;
  const draftCount = state.drafts.length;
  const trashCount = state.deleted.length;
  const allMailCount = state.emails.length + sentCount;
  const specialCounts = {
    sent: sentCount,
    drafts: draftCount,
    trash: trashCount,
    "all mail": allMailCount,
  };

  for (const [name, value] of Object.entries(specialCounts)) {
    counts[name] = value;
    const label = labelsByName.get(name);
    if (label) {
      counts[label.id] = value;
    }
  }

  return counts;
}

function paginate<T>(
  items: T[],
  page: number,
  pageSize: number,
): { items: T[]; page: number; page_size: number; total: number; pages: number } {
  page = Math.max(page, 1);
  pageSize = Math.min(Math.max(pageSize, 1), 100);
  const start = (page - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    page,
    page_size: pageSize,
    total: items.length,
    pages: Math.max(1, Math.ceil(items.length / pageSize)),
  };
}

/* ------------------------------------------------------------------ */
/*  Route matching                                                    */
/* ------------------------------------------------------------------ */

type Handler = (
  state: GmailFixture,
  params: Record<string, string>,
  body: Record<string, unknown> | undefined,
  query: Record<string, unknown> | undefined,
) => { state: GmailFixture; response: unknown };

interface Route {
  method: string;
  pattern: RegExp;
  paramNames: string[];
  handler: Handler;
}

const routes: Route[] = [];

function route(method: string, pattern: string, handler: Handler) {
  const paramNames: string[] = [];
  const regexStr = pattern.replace(/:(\w+)/g, (_, name) => {
    paramNames.push(name);
    return "([^/]+)";
  });
  routes.push({
    method: method.toUpperCase(),
    pattern: new RegExp(`^${regexStr}$`),
    paramNames,
    handler,
  });
}

function matchRoute(
  method: string,
  path: string,
): { handler: Handler; params: Record<string, string> } | null {
  const upper = method.toUpperCase();
  for (const r of routes) {
    if (r.method !== upper) continue;
    const m = path.match(r.pattern);
    if (m) {
      const params: Record<string, string> = {};
      r.paramNames.forEach((name, i) => {
        params[name] = m[i + 1];
      });
      return { handler: r.handler, params };
    }
  }
  return null;
}

/* ------------------------------------------------------------------ */
/*  Email routes                                                      */
/* ------------------------------------------------------------------ */

// GET /emails — list with filtering and pagination
route("GET", "emails", (state, _params, _body, query) => {
  const label = String(query?.label ?? "inbox");
  const q = query?.q != null ? String(query.q) : null;
  const unread = query?.unread != null ? query.unread === true || query.unread === "true" : null;
  const starred = query?.starred != null ? query.starred === true || query.starred === "true" : null;
  const page = Number(query?.page ?? 1);
  const pageSize = Number(query?.page_size ?? 25);

  let emails = listEmails(state, label, q);
  if (unread !== null) {
    emails = emails.filter((e) => e.is_read === !unread);
  }
  if (starred !== null) {
    emails = emails.filter((e) => e.is_starred === starred);
  }
  const items = emails.map((e) => serializeEmail(state, e));
  const payload = paginate(items, page, pageSize);
  return {
    state,
    response: {
      ...payload,
      counts: mailboxCounts(state),
    },
  };
});

// GET /emails/:emailId — get thread
route("GET", "emails/:emailId", (state, params) => {
  const email = findEmail(state, params.emailId);
  if (!email) {
    return { state, response: { error: "Not found", status: 404 } };
  }
  return {
    state,
    response: {
      email: serializeEmail(state, email),
      thread: getThread(state, email.thread_id).map((e) =>
        serializeEmail(state, e),
      ),
    },
  };
});

// POST /emails/:emailId/read
route("POST", "emails/:emailId/read", (state, params, body) => {
  const email = requireEmail(state, params.emailId);
  email.is_read = body?.is_read !== undefined ? Boolean(body.is_read) : true;
  return { state, response: { email: serializeEmail(state, email) } };
});

// POST /emails/:emailId/star
route("POST", "emails/:emailId/star", (state, params, body) => {
  const email = requireEmail(state, params.emailId);
  const requested = body?.is_starred;
  email.is_starred =
    requested !== undefined && requested !== null
      ? Boolean(requested)
      : !email.is_starred;

  if (email.is_starred && !email.labels.includes("starred")) {
    email.labels.push("starred");
  }
  if (!email.is_starred) {
    email.labels = email.labels.filter((l) => l !== "starred");
  }
  return { state, response: { email: serializeEmail(state, email) } };
});

// POST /emails/:emailId/label
route("POST", "emails/:emailId/label", (state, params, body) => {
  const email = requireEmail(state, params.emailId);
  const labelName = String(body?.label ?? "");
  const action = String(body?.action ?? "add");

  if (action === "add") {
    // ensure label exists
    ensureLabel(state, labelName);
    if (!email.labels.includes(labelName)) {
      email.labels.push(labelName);
    }
  } else if (action === "remove") {
    email.labels = email.labels.filter((l) => l !== labelName);
  }
  return { state, response: { email: serializeEmail(state, email) } };
});

// POST /emails/:emailId/archive
route("POST", "emails/:emailId/archive", (state, params) => {
  const email = requireEmail(state, params.emailId);
  email.labels = email.labels.filter((l) => l !== "inbox");
  return { state, response: { email: serializeEmail(state, email) } };
});

// POST /emails/:emailId/delete
route("POST", "emails/:emailId/delete", (state, params) => {
  const emailId = params.emailId;

  // Try to remove from emails or sent
  for (const col of [state.emails, state.sent]) {
    const idx = col.findIndex((e) => e.id === emailId);
    if (idx !== -1) {
      const removed = col.splice(idx, 1)[0];
      removed.labels = ["trash"];
      state.deleted.push(removed);
      return { state, response: { email: removed } };
    }
  }

  // Already in deleted or other
  const email = requireEmail(state, emailId);
  if (!state.deleted.includes(email)) {
    email.labels = ["trash"];
    state.deleted.push(email);
  }
  return { state, response: { email } };
});

// POST /emails/:emailId/forward
route("POST", "emails/:emailId/forward", (state, params, body) => {
  const original = requireEmail(state, params.emailId);
  const to = normalizeRecipients(body?.to as string[] | undefined);
  const cc = normalizeRecipients(body?.cc as string[] | undefined);
  const bcc = normalizeRecipients(body?.bcc as string[] | undefined);
  const fwdBody = String(body?.body ?? "");

  const subject = original.subject.toLowerCase().startsWith("fwd:")
    ? original.subject
    : `Fwd: ${original.subject}`;

  let fullBody = fwdBody.trim();
  if (fullBody) fullBody += "\n\n";
  fullBody += `Forwarded message from ${original.from_name} <${original.from_addr}>:\n\n${original.body}`;

  const threadId = `thread_sent_${state.sent.length + 1}`;
  const email: Email = {
    id: genId("sent"),
    from_name: state.owner_name,
    from_addr: state.owner_email,
    to,
    cc,
    bcc,
    subject,
    body: fullBody,
    timestamp: new Date().toISOString(),
    is_read: true,
    is_starred: false,
    labels: ["sent"],
    thread_id: threadId,
    in_reply_to: null,
    attachments: [...original.attachments],
  };
  state.sent.push(email);
  return { state, response: { email } };
});

// POST /send
route("POST", "send", (state, _params, body) => {
  const to = normalizeRecipients(body?.to as string[] | undefined);
  const cc = normalizeRecipients(body?.cc as string[] | undefined);
  const bcc = normalizeRecipients(body?.bcc as string[] | undefined);
  const subject = String(body?.subject ?? "");
  const emailBody = String(body?.body ?? "");
  const inReplyTo = (body?.in_reply_to as string | null) ?? null;
  let threadId = (body?.thread_id as string | null) ?? null;
  const rawAttachments = (body?.attachments ?? []) as Array<{
    filename: string;
    content_type?: string;
    size_bytes?: number;
    kind?: string;
  }>;

  if (inReplyTo && !threadId) {
    const original = findEmail(state, inReplyTo);
    if (original) threadId = original.thread_id;
  }
  threadId = threadId ?? `thread_sent_${state.sent.length + 1}`;

  const attachments: Attachment[] = rawAttachments.map((a) => ({
    id: `client_attachment_${a.filename}`,
    filename: a.filename,
    content_type: a.content_type,
    size_bytes: a.size_bytes,
    kind: a.kind,
  }));

  const email: Email = {
    id: genId("sent"),
    from_name: state.owner_name,
    from_addr: state.owner_email,
    to,
    cc,
    bcc,
    subject,
    body: emailBody,
    timestamp: new Date().toISOString(),
    is_read: true,
    is_starred: false,
    labels: ["sent"],
    thread_id: threadId,
    in_reply_to: inReplyTo,
    attachments,
  };
  state.sent.push(email);
  return { state, response: { email } };
});

/* ------------------------------------------------------------------ */
/*  Label routes                                                      */
/* ------------------------------------------------------------------ */

function ensureLabel(
  state: GmailFixture,
  name: string,
  color = "#1a73e8",
  opts?: {
    show_in_label_list?: string;
    show_in_message_list?: string;
    show_in_imap?: boolean;
  },
): Label {
  const existing = state.labels.find(
    (l) => l.name.toLowerCase() === name.toLowerCase(),
  );
  if (existing) return existing;
  const label: Label = {
    id: `label_${state.labels.length + 1}`,
    name,
    color,
    system: false,
    show_in_label_list: opts?.show_in_label_list ?? "show",
    show_in_message_list: opts?.show_in_message_list ?? "show",
    show_in_imap: opts?.show_in_imap ?? true,
  };
  state.labels.push(label);
  return label;
}

// GET /labels
route("GET", "labels", (state) => {
  return { state, response: { items: state.labels } };
});

// POST /labels
route("POST", "labels", (state, _params, body) => {
  const name = String(body?.name ?? "");
  const color = String(body?.color ?? "#1a73e8");
  const label = ensureLabel(state, name, color, {
    show_in_label_list: body?.show_in_label_list as string | undefined,
    show_in_message_list: body?.show_in_message_list as string | undefined,
    show_in_imap: body?.show_in_imap as boolean | undefined,
  });
  return { state, response: { label } };
});

// PUT /labels/:labelId
route("PUT", "labels/:labelId", (state, params, body) => {
  const label = state.labels.find((l) => l.id === params.labelId);
  if (!label) {
    return { state, response: { error: "Not found", status: 404 } };
  }

  const newName = body?.name as string | undefined;
  if (newName !== undefined && newName !== null && newName !== label.name) {
    if (label.system) {
      return {
        state,
        response: { error: `System labels cannot be renamed: ${label.name}`, status: 400 },
      };
    }
    // Check for conflicts
    const conflict = state.labels.find(
      (l) => l.id !== params.labelId && l.name.toLowerCase() === newName.toLowerCase(),
    );
    if (conflict) {
      return {
        state,
        response: { error: `Label already exists: ${newName}`, status: 400 },
      };
    }
    const oldName = label.name;
    label.name = newName;
    // Update references in emails and filters
    for (const col of [state.emails, state.sent, state.deleted]) {
      for (const email of col) {
        email.labels = email.labels.map((l) => (l === oldName ? newName : l));
      }
    }
    for (const rule of state.filters) {
      rule.add_labels = rule.add_labels.map((l) => (l === oldName ? newName : l));
      rule.label_requirements = rule.label_requirements.map((l) =>
        l === oldName ? newName : l,
      );
    }
  }
  if (body?.show_in_label_list !== undefined) {
    label.show_in_label_list = String(body.show_in_label_list);
  }
  if (body?.show_in_message_list !== undefined) {
    label.show_in_message_list = String(body.show_in_message_list);
  }
  if (body?.show_in_imap !== undefined) {
    label.show_in_imap = Boolean(body.show_in_imap);
  }
  return { state, response: { label } };
});

// DELETE /labels/:labelId
route("DELETE", "labels/:labelId", (state, params) => {
  const idx = state.labels.findIndex((l) => l.id === params.labelId);
  if (idx === -1) {
    return { state, response: { error: "Not found", status: 404 } };
  }
  const label = state.labels[idx];
  if (label.system) {
    return {
      state,
      response: { error: `System labels cannot be deleted: ${label.name}`, status: 400 },
    };
  }
  state.labels.splice(idx, 1);
  // Remove label from emails and filters
  for (const col of [state.emails, state.sent, state.deleted]) {
    for (const email of col) {
      email.labels = email.labels.filter((l) => l !== label.name);
    }
  }
  for (const rule of state.filters) {
    rule.add_labels = rule.add_labels.filter((l) => l !== label.name);
    rule.label_requirements = rule.label_requirements.filter(
      (l) => l !== label.name,
    );
  }
  return { state, response: { label } };
});

/* ------------------------------------------------------------------ */
/*  Filter routes                                                     */
/* ------------------------------------------------------------------ */

// GET /filters
route("GET", "filters", (state) => {
  return { state, response: { items: state.filters } };
});

// POST /filters
route("POST", "filters", (state, _params, body) => {
  const name = String(body?.name ?? body?.query ?? "Untitled filter");
  const query = String(body?.query ?? "");
  const parsed = parseFilterQuery(query);

  const fromAddresses =
    normalizeFilterFromAddresses(body?.from_addresses as string[] | undefined) ||
    parsed.from_addresses;
  const subjectKeywords =
    (body?.subject_keywords as string[])?.length
      ? (body!.subject_keywords as string[])
      : parsed.subject_keywords;
  const labelRequirements =
    (body?.label_requirements as string[])?.length
      ? (body!.label_requirements as string[])
      : parsed.label_requirements;
  const hasAttachment =
    body?.has_attachment !== undefined && body?.has_attachment !== null
      ? Boolean(body.has_attachment)
      : parsed.has_attachment;

  const filter: FilterRule = {
    id: `filter_${state.filters.length + 1}`,
    name,
    query,
    from_addresses: fromAddresses,
    subject_keywords: subjectKeywords,
    label_requirements: labelRequirements,
    has_attachment: hasAttachment,
    add_labels: (body?.add_labels as string[]) ?? [],
    archive: Boolean(body?.archive),
    mark_read: Boolean(body?.mark_read),
    forward_to: (body?.forward_to as string | null) ?? null,
    star: Boolean(body?.star),
    never_spam: Boolean(body?.never_spam),
  };
  state.filters.push(filter);
  return { state, response: { filter } };
});

// DELETE /filters/:filterId
route("DELETE", "filters/:filterId", (state, params) => {
  const idx = state.filters.findIndex((f) => f.id === params.filterId);
  if (idx === -1) {
    return { state, response: { error: "Not found", status: 404 } };
  }
  const filter = state.filters.splice(idx, 1)[0];
  return { state, response: { filter } };
});

/* ------------------------------------------------------------------ */
/*  Filter query parsing (mirrors Python _parse_filter_query)         */
/* ------------------------------------------------------------------ */

function parseFilterQuery(query: string): {
  from_addresses: string[];
  subject_keywords: string[];
  label_requirements: string[];
  has_attachment: null | boolean;
} {
  const result = {
    from_addresses: [] as string[],
    subject_keywords: [] as string[],
    label_requirements: [] as string[],
    has_attachment: null as null | boolean,
  };
  if (!query) return result;

  const tokens = query.split(/\s+/);
  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i];
    if (token.toUpperCase() === "OR") {
      i++;
      continue;
    }
    const lowered = token.toLowerCase();
    if (!lowered.includes(":")) {
      i++;
      continue;
    }
    const [key, value] = lowered.split(":", 2);
    if (key === "from") {
      const rawValue = token.split(":", 2)[1];
      if (rawValue.startsWith("@")) {
        result.from_addresses.push(`*${rawValue}`);
      } else {
        result.from_addresses.push(
          rawValue.includes("@") ? rawValue : `*${rawValue}`,
        );
      }
    } else if (key === "subject") {
      const subjectParts = [token.split(":", 2)[1]];
      let lookahead = i + 1;
      while (lookahead < tokens.length) {
        const next = tokens[lookahead];
        if (next.toUpperCase() === "OR" || next.includes(":")) break;
        subjectParts.push(next);
        lookahead++;
      }
      result.subject_keywords.push(subjectParts.join(" "));
      i = lookahead;
      continue;
    } else if (key === "label") {
      result.label_requirements.push(token.split(":", 2)[1]);
    } else if (key === "has" && value === "attachment") {
      result.has_attachment = true;
    }
    i++;
  }
  return result;
}

function normalizeFilterFromAddresses(
  values?: string[],
): string[] {
  if (!values || !values.length) return [];
  return values
    .map((v) => v.trim())
    .filter(Boolean)
    .map((v) => {
      if (v.startsWith("@")) return `*${v}`;
      if (!v.includes("@") && !v.includes("*")) return `*${v}`;
      return v;
    });
}

/* ------------------------------------------------------------------ */
/*  Contact routes                                                    */
/* ------------------------------------------------------------------ */

// GET /contacts
route("GET", "contacts", (state, _params, _body, query) => {
  let contacts = state.contacts;
  const q = query?.q ? String(query.q).toLowerCase() : null;
  if (q) {
    contacts = contacts.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.email.toLowerCase().includes(q),
    );
  }
  return { state, response: { items: contacts } };
});

// POST /contacts
route("POST", "contacts", (state, _params, body) => {
  const email = String(body?.email ?? "");
  const name = String(body?.name ?? "");

  // Check for existing contact with same email
  const existing = state.contacts.find(
    (c) => c.email.toLowerCase() === email.toLowerCase(),
  );
  if (existing) {
    existing.name = name;
    if (body?.company !== undefined) existing.company = body.company as string;
    if (body?.note !== undefined) existing.note = body.note as string;
    if (body?.is_vip !== undefined) existing.is_vip = Boolean(body.is_vip);
    if (body?.is_starred !== undefined) existing.is_starred = Boolean(body.is_starred);
    if (body?.last_contacted_at !== undefined)
      existing.last_contacted_at = body.last_contacted_at as string | null;
    return { state, response: { contact: existing } };
  }

  const contact: Contact = {
    id: `contact_manual_${state.contacts.length + 1}`,
    name,
    email,
    company: (body?.company as string) ?? undefined,
    note: (body?.note as string) ?? undefined,
    is_vip: Boolean(body?.is_vip),
    is_starred: Boolean(body?.is_starred),
    source: "manual",
    last_contacted_at: (body?.last_contacted_at as string | null) ?? null,
  };
  state.contacts.push(contact);
  return { state, response: { contact } };
});

// PUT /contacts/:contactId
route("PUT", "contacts/:contactId", (state, params, body) => {
  const contact = state.contacts.find((c) => c.id === params.contactId);
  if (!contact) {
    return { state, response: { error: "Not found", status: 404 } };
  }

  if (body?.email !== undefined && body.email !== null) {
    const newEmail = String(body.email);
    if (newEmail.toLowerCase() !== contact.email.toLowerCase()) {
      const conflict = state.contacts.find(
        (c) =>
          c.id !== params.contactId &&
          c.email.toLowerCase() === newEmail.toLowerCase(),
      );
      if (conflict) {
        return {
          state,
          response: { error: `Contact already exists: ${newEmail}`, status: 400 },
        };
      }
      contact.email = newEmail;
    }
  }
  if (body?.name !== undefined) contact.name = String(body.name);
  if (body?.company !== undefined) contact.company = body.company as string;
  if (body?.note !== undefined) contact.note = body.note as string;
  if (body?.is_vip !== undefined) contact.is_vip = Boolean(body.is_vip);
  if (body?.is_starred !== undefined)
    contact.is_starred = Boolean(body.is_starred);
  if (body?.last_contacted_at !== undefined)
    contact.last_contacted_at = body.last_contacted_at as string | null;

  return { state, response: { contact } };
});

// DELETE /contacts/:contactId
route("DELETE", "contacts/:contactId", (state, params) => {
  const idx = state.contacts.findIndex((c) => c.id === params.contactId);
  if (idx === -1) {
    return { state, response: { error: "Not found", status: 404 } };
  }
  const contact = state.contacts.splice(idx, 1)[0];
  return { state, response: { contact } };
});

/* ------------------------------------------------------------------ */
/*  Settings routes                                                   */
/* ------------------------------------------------------------------ */

// GET /settings
route("GET", "settings", (state) => {
  return { state, response: { settings: state.settings } };
});

// PUT /settings
route("PUT", "settings", (state, _params, body) => {
  if (body) {
    const keys: (keyof GmailSettings)[] = [
      "signature",
      "forwarding_address",
      "display_density",
      "vacation_responder_enabled",
      "vacation_responder_message",
      "auto_advance",
      "language",
      "input_tools_enabled",
      "right_to_left",
      "max_page_size",
      "undo_send_seconds",
      "default_reply_behavior",
      "hover_actions_enabled",
      "send_and_archive",
      "default_text_style",
    ];
    for (const key of keys) {
      if (body[key] !== undefined && body[key] !== null) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (state.settings as any)[key] = body[key];
      }
    }
  }
  return { state, response: { settings: state.settings } };
});

/* ------------------------------------------------------------------ */
/*  Search route                                                      */
/* ------------------------------------------------------------------ */

// GET /search
route("GET", "search", (state, _params, _body, query) => {
  const q = String(query?.q ?? "").toLowerCase();
  const page = Number(query?.page ?? 1);
  const pageSize = Number(query?.page_size ?? 25);

  const candidates = [...state.emails, ...state.sent].filter(
    (e) => !e.labels.includes("trash"),
  );
  const matched = candidates
    .filter((e) => emailMatchesSimple(e, q))
    .sort(
      (a, b) =>
        new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    );

  const items = matched.map((e) => serializeEmail(state, e));
  const payload = paginate(items, page, pageSize);
  return {
    state,
    response: { ...payload, query: query?.q ?? "" },
  };
});

/* ------------------------------------------------------------------ */
/*  Exported mutator                                                  */
/* ------------------------------------------------------------------ */

export const gmailMutator: RouteMutator<GmailFixture> = (
  state,
  method,
  path,
  body,
  query,
) => {
  // Strip any leading slash or prefix
  const cleanPath = path.replace(/^\//, "");

  const match = matchRoute(method, cleanPath);
  if (!match) {
    return { state, response: { error: `No route: ${method} /${cleanPath}`, status: 404 } };
  }

  return match.handler(
    state,
    match.params,
    body as Record<string, unknown> | undefined,
    query,
  );
};
