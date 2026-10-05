import { gmailMutator, type GmailFixture } from "@breakingweb/gmail/mutator";

import type { TrajectoryStep, TrajectoryTarget } from "./results";

const DEFAULT_ROUTE = "/inbox?label=inbox";
const INBOX_PAGE_SIZE = 16;
const CONTACTS_PAGE_SIZE = 8;

type GmailEmail = GmailFixture["emails"][number];
type GmailLabel = GmailFixture["labels"][number];
type GmailContact = GmailFixture["contacts"][number];
type GmailSettings = GmailFixture["settings"];

interface ComposeDraft {
  mode: "compose" | "reply" | "replyAll" | "forward";
  emailId: string | null;
  replyTo: string | null;
  threadId: string | null;
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  body: string;
  attachments: string;
  showCc?: boolean;
  showBcc?: boolean;
}

interface FilterDraft {
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

interface ReplayDrafts {
  compose: ComposeDraft | null;
  searchQuery: string;
  searchActive: boolean;
  labelsPage: {
    name: string;
    color: string;
  };
  thread: {
    labelMenuOpen: boolean;
    creatingLabel: boolean;
    labelDraftName: string;
  };
  contacts: {
    name: string;
    email: string;
    company: string;
    note: string;
    isVip: boolean;
    editingId: string | null;
    page: number;
  };
  settings: {
    activeTab: string;
    values: GmailSettings;
    filterWizardOpen: boolean;
    filterWizardStep: "criteria" | "actions";
    filter: FilterDraft;
    renamingLabelId: string | null;
    renameLabelDraft: string;
  };
}

const EMPTY_FILTER_DRAFT: FilterDraft = {
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

export interface GmailReplayStepState {
  fixture: GmailFixture;
  displayRoute: string;
}

function parseRoute(route?: string) {
  const [pathname, queryString = ""] = (route || DEFAULT_ROUTE).split("?");
  return {
    pathname: pathname || "/inbox",
    searchParams: new URLSearchParams(queryString),
  };
}

function buildRoute(pathname: string, searchParams: URLSearchParams) {
  const encoded = searchParams.toString();
  return encoded ? `${pathname}?${encoded}` : pathname;
}

function normalizeLabel(value: string | null) {
  return value || "inbox";
}

function normalizeText(value: string | null | undefined) {
  return (value ?? "").replace(/\s+/g, " ").trim().toLowerCase();
}

function normalizeRecipient(value: string) {
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

function splitList(value: string) {
  return value
    .split(",")
    .map((item) => normalizeRecipient(item))
    .filter(Boolean);
}

function categoryOf(email: GmailEmail) {
  if (email.labels.includes("promotions")) return "promotions";
  if (email.labels.includes("updates")) return "updates";
  return "primary";
}

function allMail(state: GmailFixture) {
  return [...state.emails, ...state.sent, ...state.deleted].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  );
}

function findEmailById(state: GmailFixture, emailId: string | null | undefined) {
  if (!emailId) return null;
  return allMail(state).find((email) => email.id === emailId) ?? null;
}

function findLabelByName(state: GmailFixture, labelName: string) {
  const wanted = normalizeText(labelName);
  return state.labels.find((label) => normalizeText(label.name) === wanted) ?? null;
}

function findContactByName(state: GmailFixture, name: string) {
  const wanted = normalizeText(name);
  return state.contacts.find((contact) => normalizeText(contact.name) === wanted) ?? null;
}

function getCurrentThreadEmailId(route?: string) {
  const { pathname } = parseRoute(route);
  const match = pathname.match(/^\/thread\/([^/?#]+)/);
  return match?.[1] ?? null;
}

function getCurrentThreadEmail(state: GmailFixture, route?: string) {
  return findEmailById(state, getCurrentThreadEmailId(route));
}

function parseRowIndex(selector?: string) {
  if (!selector) return null;
  const articleMatch = selector.match(/article[^>]*:nth-of-type\((\d+)\)/);
  if (articleMatch) {
    return Number(articleMatch[1]);
  }
  return null;
}

function subjectFromTargetName(name: string) {
  const prefixes = [
    "Open thread ",
    "Star ",
    "Unstar ",
    "Archive ",
    "Delete ",
  ];
  for (const prefix of prefixes) {
    if (name.startsWith(prefix)) {
      return name.slice(prefix.length);
    }
  }
  return null;
}

function requestView<T>(
  state: GmailFixture,
  path: string,
  query?: Record<string, unknown>,
) {
  return gmailMutator(state, "GET", path, undefined, query).response as T;
}

function getVisibleEmails(state: GmailFixture, route?: string) {
  const { pathname, searchParams } = parseRoute(route);

  if (pathname === "/search") {
    const q = searchParams.get("q") ?? "";
    const response = requestView<{ items: GmailEmail[] }>(state, "search", {
      q,
      page: 1,
      page_size: 100,
    });
    return response.items ?? [];
  }

  if (pathname !== "/inbox") {
    return [];
  }

  const label = normalizeLabel(searchParams.get("label"));
  const category = searchParams.get("category") ?? "primary";
  const page = Number(searchParams.get("page") ?? 1);
  const response = requestView<{ items: GmailEmail[] }>(state, "emails", {
    label,
    page: 1,
    page_size: 100,
  });

  let items = response.items ?? [];
  if (category !== "all") {
    items = items.filter((email) => categoryOf(email) === category);
  }

  const start = Math.max(page - 1, 0) * INBOX_PAGE_SIZE;
  return items.slice(start, start + INBOX_PAGE_SIZE);
}

function resolveEmailFromTarget(
  state: GmailFixture,
  route: string | undefined,
  target: TrajectoryTarget | null,
) {
  if (!target) {
    return getCurrentThreadEmail(state, route);
  }

  const currentThreadEmail = getCurrentThreadEmail(state, route);
  if (currentThreadEmail) {
    return currentThreadEmail;
  }

  const visibleEmails = getVisibleEmails(state, route);
  const subject = subjectFromTargetName(target.name ?? "");
  const rowIndex = parseRowIndex(target.selector);

  if (rowIndex != null && rowIndex > 0 && rowIndex <= visibleEmails.length) {
    return visibleEmails[rowIndex - 1] ?? null;
  }

  if (subject) {
    const wanted = normalizeText(subject);
    return visibleEmails.find((email) => normalizeText(email.subject) === wanted) ?? null;
  }

  return null;
}

function buildFilterQuery(filter: FilterDraft) {
  const parts: string[] = [];
  if (filter.fromPattern.trim()) parts.push(`from:${filter.fromPattern.trim()}`);
  if (filter.subjectPhrase.trim()) parts.push(`subject:${filter.subjectPhrase.trim()}`);
  if (filter.hasAttachment) parts.push("has:attachment");
  return parts.join(" ");
}

function createReplyDraft(
  state: GmailFixture,
  email: GmailEmail,
  mode: "reply" | "replyAll",
): ComposeDraft {
  const replyAllCc =
    mode === "replyAll"
      ? [...email.to, ...email.cc].filter(
          (addr) => addr !== state.owner_email && addr !== email.from_addr,
        )
      : [];

  return {
    mode,
    emailId: email.id,
    replyTo: email.id,
    threadId: email.thread_id,
    to: email.from_addr,
    cc: replyAllCc.join(", "),
    bcc: "",
    subject: email.subject.startsWith("Re:") ? email.subject : `Re: ${email.subject}`,
    body: `\n\nOn ${new Date(email.timestamp).toLocaleString()}, ${email.from_name} wrote:\n${email.body}`,
    attachments: "",
  };
}

function createForwardDraft(email: GmailEmail): ComposeDraft {
  return {
    mode: "forward",
    emailId: email.id,
    replyTo: null,
    threadId: null,
    to: "",
    cc: "",
    bcc: "",
    subject: email.subject.startsWith("Fwd:") ? email.subject : `Fwd: ${email.subject}`,
    body: "",
    attachments: "",
  };
}

function createComposeDraft(): ComposeDraft {
  return {
    mode: "compose",
    emailId: null,
    replyTo: null,
    threadId: null,
    to: "",
    cc: "",
    bcc: "",
    subject: "",
    body: "",
    attachments: "",
  };
}

function createInitialDrafts(state: GmailFixture): ReplayDrafts {
  return {
    compose: null,
    searchQuery: "",
    searchActive: false,
    labelsPage: {
      name: "",
      color: "#1a73e8",
    },
    thread: {
      labelMenuOpen: false,
      creatingLabel: false,
      labelDraftName: "",
    },
    contacts: {
      name: "",
      email: "",
      company: "",
      note: "",
      isVip: false,
      editingId: null,
      page: 1,
    },
    settings: {
      activeTab: "General",
      values: structuredClone(state.settings),
      filterWizardOpen: false,
      filterWizardStep: "criteria",
      filter: { ...EMPTY_FILTER_DRAFT },
      renamingLabelId: null,
      renameLabelDraft: "",
    },
  };
}

function setReplayParam(searchParams: URLSearchParams, key: string, value: string | null | undefined) {
  if (value == null || value === "") {
    searchParams.delete(key);
    return;
  }

  searchParams.set(key, value);
}

function applyComposeReplayParams(
  searchParams: URLSearchParams,
  compose: ComposeDraft | null,
  includeMode: boolean,
) {
  if (includeMode && compose && compose.mode !== "compose") {
    searchParams.set("replayCompose", compose.mode);
  } else {
    searchParams.delete("replayCompose");
  }

  setReplayParam(searchParams, "replayTo", compose?.to);
  setReplayParam(searchParams, "replayCc", compose?.cc);
  setReplayParam(searchParams, "replayBcc", compose?.bcc);
  setReplayParam(searchParams, "replaySubject", compose?.subject);
  setReplayParam(searchParams, "replayBody", compose?.body);
  setReplayParam(searchParams, "replayAttachments", compose?.attachments);

  if (compose?.showCc) {
    searchParams.set("replayShowCc", "1");
  } else {
    searchParams.delete("replayShowCc");
  }

  if (compose?.showBcc) {
    searchParams.set("replayShowBcc", "1");
  } else {
    searchParams.delete("replayShowBcc");
  }
}

function withReplayParams(route: string, drafts: ReplayDrafts) {
  const { pathname, searchParams } = parseRoute(route);
  searchParams.set("replay", "1");

  // Search: show search results after "Run search" was clicked
  if (drafts.searchActive && drafts.searchQuery) {
    return buildRoute("/search", new URLSearchParams({ q: drafts.searchQuery, replay: "1" }));
  }

  if (drafts.searchQuery) {
    searchParams.set("q", drafts.searchQuery);
  } else if (pathname !== "/search") {
    searchParams.delete("q");
  }

  if (pathname === "/thread") {
    return buildRoute(pathname, searchParams);
  }

  if (pathname.startsWith("/thread/")) {
    if (drafts.compose && drafts.compose.mode !== "compose") {
      applyComposeReplayParams(searchParams, drafts.compose, true);
    } else {
      applyComposeReplayParams(searchParams, null, true);
    }

    if (drafts.thread.labelMenuOpen || drafts.thread.creatingLabel) {
      searchParams.set("replayLabelMenu", "1");
    } else {
      searchParams.delete("replayLabelMenu");
    }

    if (drafts.thread.creatingLabel) {
      searchParams.set("replayCreateLabel", "1");
      if (drafts.thread.labelDraftName) {
        searchParams.set("replayLabelName", drafts.thread.labelDraftName);
      } else {
        searchParams.delete("replayLabelName");
      }
    } else {
      searchParams.delete("replayCreateLabel");
      searchParams.delete("replayLabelName");
    }

    return buildRoute(pathname, searchParams);
  }

  // Compose page — pass draft fields so the Compose UI can display them
  if (pathname === "/compose" || drafts.compose) {
    applyComposeReplayParams(searchParams, drafts.compose, false);
    if (pathname === "/compose") {
      return buildRoute(pathname, searchParams);
    }
  }

  if (pathname === "/labels") {
    setReplayParam(searchParams, "replayNewLabelName", drafts.labelsPage.name);
    setReplayParam(searchParams, "replayContactName", drafts.contacts.name);
    setReplayParam(searchParams, "replayContactEmail", drafts.contacts.email);
    setReplayParam(searchParams, "replayContactCompany", drafts.contacts.company);
    setReplayParam(searchParams, "replayContactNote", drafts.contacts.note);

    if (drafts.contacts.isVip) {
      searchParams.set("replayContactVip", "1");
    } else {
      searchParams.delete("replayContactVip");
    }

    if (drafts.contacts.editingId) {
      searchParams.set("replayContactEditId", drafts.contacts.editingId);
    } else {
      searchParams.delete("replayContactEditId");
    }

    if (drafts.contacts.page > 1) {
      searchParams.set("replayContactPage", String(drafts.contacts.page));
    } else {
      searchParams.delete("replayContactPage");
    }

    return buildRoute(pathname, searchParams);
  }

  if (pathname === "/settings") {
    if (drafts.settings.activeTab && drafts.settings.activeTab !== "General") {
      searchParams.set("tab", drafts.settings.activeTab);
    } else {
      searchParams.delete("tab");
    }

    setReplayParam(searchParams, "replaySignature", drafts.settings.values.signature);
    setReplayParam(
      searchParams,
      "replayVacationMessage",
      drafts.settings.values.vacation_responder_message ?? "",
    );
    setReplayParam(
      searchParams,
      "replayForwardingAddress",
      drafts.settings.values.forwarding_address ?? "",
    );
    setReplayParam(
      searchParams,
      "replayUndoSendSeconds",
      drafts.settings.values.undo_send_seconds != null
        ? String(drafts.settings.values.undo_send_seconds)
        : null,
    );
    setReplayParam(
      searchParams,
      "replayMaxPageSize",
      drafts.settings.values.max_page_size != null
        ? String(drafts.settings.values.max_page_size)
        : null,
    );
    setReplayParam(searchParams, "replayLanguage", drafts.settings.values.language ?? "");
    setReplayParam(
      searchParams,
      "replayDefaultReplyBehavior",
      drafts.settings.values.default_reply_behavior ?? "",
    );
    setReplayParam(
      searchParams,
      "replayDisplayDensity",
      drafts.settings.values.display_density ?? "",
    );

    if (drafts.settings.values.vacation_responder_enabled) {
      searchParams.set("replayVacationEnabled", "1");
    } else {
      searchParams.delete("replayVacationEnabled");
    }

    if (drafts.settings.values.send_and_archive) {
      searchParams.set("replaySendAndArchive", "1");
    } else {
      searchParams.delete("replaySendAndArchive");
    }

    if (drafts.settings.renamingLabelId) {
      searchParams.set("replayRenameLabelId", drafts.settings.renamingLabelId);
      setReplayParam(searchParams, "replayRenameLabelDraft", drafts.settings.renameLabelDraft);
    } else {
      searchParams.delete("replayRenameLabelId");
      searchParams.delete("replayRenameLabelDraft");
    }

    if (drafts.settings.filterWizardOpen) {
      searchParams.set("replayFilterModal", "1");
      searchParams.set("replayFilterStep", drafts.settings.filterWizardStep);
      const filter = drafts.settings.filter;
      if (filter.fromPattern) searchParams.set("replayFilterFrom", filter.fromPattern);
      else searchParams.delete("replayFilterFrom");
      if (filter.subjectPhrase) searchParams.set("replayFilterSubject", filter.subjectPhrase);
      else searchParams.delete("replayFilterSubject");
      if (filter.addLabelsText) searchParams.set("replayFilterLabels", filter.addLabelsText);
      else searchParams.delete("replayFilterLabels");
      if (filter.forwardTo) searchParams.set("replayFilterForward", filter.forwardTo);
      else searchParams.delete("replayFilterForward");
      if (filter.name) searchParams.set("replayFilterName", filter.name);
      else searchParams.delete("replayFilterName");
      if (filter.hasAttachment) searchParams.set("replayFilterHasAttachment", "1");
      else searchParams.delete("replayFilterHasAttachment");
      if (filter.archive) searchParams.set("replayFilterArchive", "1");
      else searchParams.delete("replayFilterArchive");
      if (filter.markRead) searchParams.set("replayFilterMarkRead", "1");
      else searchParams.delete("replayFilterMarkRead");
      if (filter.star) searchParams.set("replayFilterStar", "1");
      else searchParams.delete("replayFilterStar");
      if (filter.neverSpam) searchParams.set("replayFilterNeverSpam", "1");
      else searchParams.delete("replayFilterNeverSpam");
    } else {
      [
        "replayFilterModal",
        "replayFilterStep",
        "replayFilterFrom",
        "replayFilterSubject",
        "replayFilterLabels",
        "replayFilterForward",
        "replayFilterName",
        "replayFilterHasAttachment",
        "replayFilterArchive",
        "replayFilterMarkRead",
        "replayFilterStar",
        "replayFilterNeverSpam",
      ].forEach((key) => searchParams.delete(key));
    }

    return buildRoute(pathname, searchParams);
  }

  return buildRoute(pathname, searchParams);
}

function applyRequest(
  state: GmailFixture,
  method: string,
  path: string,
  body?: Record<string, unknown>,
  query?: Record<string, unknown>,
) {
  return gmailMutator(state, method, path, body, query).response;
}

function applyFill(
  drafts: ReplayDrafts,
  state: GmailFixture,
  route: string | undefined,
  target: TrajectoryTarget | null,
  value: unknown,
) {
  const stringValue = String(value ?? "");
  const field = target?.name ?? "";
  const { pathname } = parseRoute(route);

  switch (field) {
    case "New label name":
      if (pathname === "/labels") {
        drafts.labelsPage.name = stringValue;
      } else {
        drafts.thread.labelMenuOpen = true;
        drafts.thread.creatingLabel = true;
        drafts.thread.labelDraftName = stringValue;
      }
      return;
    case "Contact name":
      drafts.contacts.name = stringValue;
      return;
    case "Contact email address":
      drafts.contacts.email = stringValue;
      return;
    case "Contact company":
      drafts.contacts.company = stringValue;
      return;
    case "Contact note":
      drafts.contacts.note = stringValue;
      return;
    case "Filter from address":
      drafts.settings.filter.fromPattern = stringValue;
      return;
    case "Filter subject phrase":
      drafts.settings.filter.subjectPhrase = stringValue;
      return;
    case "Filter labels":
      drafts.settings.filter.addLabelsText = stringValue;
      return;
    case "Filter forward address":
      drafts.settings.filter.forwardTo = stringValue;
      return;
    case "Filter name":
      drafts.settings.filter.name = stringValue;
      return;
    case "Search mail":
      drafts.searchQuery = stringValue;
      return;
    case "Mark as VIP contact":
      drafts.contacts.isVip = true;
      return;
    case "Email signature":
      drafts.settings.values.signature = stringValue;
      return;
    case "Vacation responder message":
      drafts.settings.values.vacation_responder_message = stringValue;
      return;
    case "Forwarding email address":
      drafts.settings.values.forwarding_address = stringValue;
      return;
    default:
      break;
  }

  // Rename label — store the new name, actual rename applies on click "Save"/"Rename"
  if (field.startsWith("Rename label ")) {
    const labelName = field.slice("Rename label ".length);
    const label = findLabelByName(state, labelName);
    drafts.settings.activeTab = "Labels";
    drafts.settings.renamingLabelId = label?.id ?? null;
    drafts.settings.renameLabelDraft = stringValue;
    return;
  }

  // Edit contact fields — field is "Edit contact XYZ" for inline editing
  if (field.startsWith("Edit contact ")) {
    // The edit button opens inline editing — no state mutation until save
    return;
  }

  if (
    field === "Recipients"
    || field === "Carbon copy recipients"
    || field === "Blind carbon copy recipients"
    || field === "Email subject"
    || field === "Email body"
    || field === "Attachment filenames"
  ) {
    drafts.compose ??= pathname === "/compose" ? createComposeDraft() : createComposeDraft();

    switch (field) {
      case "Recipients":
        drafts.compose.to = stringValue;
        break;
      case "Carbon copy recipients":
        drafts.compose.cc = stringValue;
        break;
      case "Blind carbon copy recipients":
        drafts.compose.bcc = stringValue;
        break;
      case "Email subject":
        drafts.compose.subject = stringValue;
        break;
      case "Email body":
        drafts.compose.body = stringValue;
        break;
      case "Attachment filenames":
        drafts.compose.attachments = stringValue;
        break;
      default:
        break;
    }
  }
}

function applyCheck(drafts: ReplayDrafts, target: TrajectoryTarget | null) {
  const field = target?.name ?? "";

  switch (field) {
    case "Skip Inbox (Archive it)":
      drafts.settings.filter.archive = true;
      break;
    case "Mark as read":
      drafts.settings.filter.markRead = true;
      break;
    case "Star it":
      drafts.settings.filter.star = true;
      break;
    case "Has attachment":
      drafts.settings.filter.hasAttachment = true;
      break;
    case "Never spam":
      drafts.settings.filter.neverSpam = true;
      break;
    case "Mark as VIP contact":
      drafts.contacts.isVip = true;
      break;
    default:
      break;
  }
}

function applySelect(
  drafts: ReplayDrafts,
  target: TrajectoryTarget | null,
  value: unknown,
) {
  const field = target?.name ?? "";

  switch (field) {
    case "Undo send seconds":
      drafts.settings.values.undo_send_seconds = Number(value);
      break;
    case "Maximum page size":
      drafts.settings.values.max_page_size = Number(value);
      break;
    case "Gmail display language":
      drafts.settings.values.language = String(value ?? "");
      break;
    default:
      break;
  }
}

function applySettingsRadio(drafts: ReplayDrafts, field: string) {
  switch (field) {
    case "Vacation responder on":
      drafts.settings.values.vacation_responder_enabled = true;
      break;
    case "Vacation responder off":
      drafts.settings.values.vacation_responder_enabled = false;
      break;
    case "Reply":
      drafts.settings.values.default_reply_behavior = "reply";
      break;
    case "Reply all":
      drafts.settings.values.default_reply_behavior = "reply_all";
      break;
    case "Show \"Send & Archive\" button in reply":
      drafts.settings.values.send_and_archive = true;
      break;
    case "Hide \"Send & Archive\" button in reply":
      drafts.settings.values.send_and_archive = false;
      break;
    case "Comfortable":
      drafts.settings.values.display_density = "comfortable";
      break;
    case "Compact":
      drafts.settings.values.display_density = "compact";
      break;
    case "Default":
      drafts.settings.values.display_density = "default";
      break;
    default:
      break;
  }
}

function applyClick(
  state: GmailFixture,
  drafts: ReplayDrafts,
  route: string | undefined,
  target: TrajectoryTarget | null,
) {
  const field = target?.name ?? "";
  const { pathname } = parseRoute(route);

  if (target?.role === "tab" && pathname === "/settings") {
    drafts.settings.activeTab = field;
    return;
  }

  applySettingsRadio(drafts, field);

  if (field.startsWith("Open thread ") || field.startsWith("Open unread thread ") || field.startsWith("Open read thread ")) {
    const email = resolveEmailFromTarget(state, route, target);
    if (email) {
      applyRequest(state, "POST", `emails/${email.id}/read`, { is_read: true });
    }
    drafts.thread.labelMenuOpen = false;
    drafts.thread.creatingLabel = false;
    drafts.thread.labelDraftName = "";
    drafts.compose = null;
    drafts.searchQuery = "";
    drafts.searchActive = false;
    return;
  }

  if (field === "Apply label to this thread") {
    drafts.thread.labelMenuOpen = true;
    drafts.thread.creatingLabel = false;
    return;
  }

  if (field === "Create new label" && pathname.startsWith("/thread/")) {
    drafts.thread.labelMenuOpen = true;
    drafts.thread.creatingLabel = true;
    return;
  }

  if (field === "Cancel label creation" && pathname.startsWith("/thread/")) {
    drafts.thread.labelMenuOpen = true;
    drafts.thread.creatingLabel = false;
    drafts.thread.labelDraftName = "";
    return;
  }

  if (field === "Create label") {
    if (pathname === "/labels") {
      if (drafts.labelsPage.name.trim()) {
        applyRequest(state, "POST", "labels", {
          name: drafts.labelsPage.name.trim(),
          color: drafts.labelsPage.color,
        });
        drafts.labelsPage.name = "";
      }
      return;
    }

    const currentThread = getCurrentThreadEmail(state, route);
    const labelName = drafts.thread.labelDraftName.trim();
    if (pathname.startsWith("/thread/") && currentThread && labelName) {
      applyRequest(state, "POST", "labels", { name: labelName, color: "#1a73e8" });
      applyRequest(state, "POST", `emails/${currentThread.id}/label`, {
        label: labelName,
        action: "add",
      });
      drafts.thread.labelMenuOpen = false;
      drafts.thread.creatingLabel = false;
      drafts.thread.labelDraftName = "";
    }
    return;
  }

  if (field.startsWith("Apply label ") || field.startsWith("Remove label ")) {
    const currentThread = getCurrentThreadEmail(state, route);
    if (!currentThread) return;
    const action = field.startsWith("Remove label ") ? "remove" : "add";
    const prefix = action === "remove" ? "Remove label " : "Apply label ";
    const labelName = field.slice(prefix.length);
    applyRequest(state, "POST", `emails/${currentThread.id}/label`, {
      label: labelName,
      action,
    });
    drafts.thread.labelMenuOpen = false;
    drafts.thread.creatingLabel = false;
    drafts.thread.labelDraftName = "";
    return;
  }

  if (field === "Star this thread" || field === "Unstar this thread") {
    const currentThread = getCurrentThreadEmail(state, route);
    if (currentThread) {
      applyRequest(state, "POST", `emails/${currentThread.id}/star`);
    }
    return;
  }

  if (field.startsWith("Star ") || field.startsWith("Unstar ")) {
    const email = resolveEmailFromTarget(state, route, target);
    if (email) {
      applyRequest(state, "POST", `emails/${email.id}/star`);
    }
    return;
  }

  if (field === "Archive this thread") {
    const currentThread = getCurrentThreadEmail(state, route);
    if (currentThread) {
      applyRequest(state, "POST", `emails/${currentThread.id}/archive`);
    }
    drafts.compose = null;
    return;
  }

  if (field === "Delete this thread") {
    const currentThread = getCurrentThreadEmail(state, route);
    if (currentThread) {
      applyRequest(state, "POST", `emails/${currentThread.id}/delete`);
    }
    drafts.compose = null;
    return;
  }

  if (field.startsWith("Archive ")) {
    const email = resolveEmailFromTarget(state, route, target);
    if (email) {
      applyRequest(state, "POST", `emails/${email.id}/archive`);
    }
    return;
  }

  if (field.startsWith("Delete filter ")) {
    const filterName = normalizeText(field.slice("Delete filter ".length));
    const filter = state.filters.find((item) => normalizeText(item.name) === filterName);
    if (filter) {
      applyRequest(state, "DELETE", `filters/${filter.id}`);
    }
    return;
  }

  if (field.startsWith("Delete contact ")) {
    const contact = findContactByName(state, field.slice("Delete contact ".length));
    if (contact) {
      applyRequest(state, "DELETE", `contacts/${contact.id}`);
    }
    return;
  }

  if (field.startsWith("Edit contact ")) {
    const contact = findContactByName(state, field.slice("Edit contact ".length));
    if (contact) {
      drafts.contacts = {
        name: contact.name,
        email: contact.email,
        company: contact.company ?? "",
        note: contact.note ?? "",
        isVip: Boolean(contact.is_vip),
        editingId: contact.id,
        page: drafts.contacts.page,
      };
    }
    return;
  }

  if (field.startsWith("Delete label ")) {
    const label = findLabelByName(state, field.slice("Delete label ".length));
    if (label) {
      applyRequest(state, "DELETE", `labels/${label.id}`);
    }
    return;
  }

  if (field.startsWith("Delete ")) {
    const email = resolveEmailFromTarget(state, route, target);
    if (email) {
      applyRequest(state, "POST", `emails/${email.id}/delete`);
    }
    return;
  }

  if (field === "Create a new filter") {
    drafts.settings.activeTab = "Filters and Blocked Addresses";
    drafts.settings.filterWizardOpen = true;
    drafts.settings.filterWizardStep = "criteria";
    drafts.settings.filter = { ...EMPTY_FILTER_DRAFT };
    return;
  }

  if (field === "Continue to filter actions") {
    drafts.settings.activeTab = "Filters and Blocked Addresses";
    drafts.settings.filterWizardOpen = true;
    drafts.settings.filterWizardStep = "actions";
    return;
  }

  if (field === "Save new filter") {
    const filter = drafts.settings.filter;
    applyRequest(state, "POST", "filters", {
      name: filter.name,
      query: buildFilterQuery(filter),
      from_addresses: filter.fromPattern.trim() ? [filter.fromPattern.trim()] : [],
      subject_keywords: filter.subjectPhrase.trim() ? [filter.subjectPhrase.trim()] : [],
      label_requirements: [],
      has_attachment: filter.hasAttachment ? true : null,
      add_labels: filter.addLabelsText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      archive: filter.archive,
      mark_read: filter.markRead,
      never_spam: filter.neverSpam,
      forward_to: filter.forwardTo.trim() || null,
      star: filter.star,
    });
    drafts.settings.filterWizardOpen = false;
    drafts.settings.filterWizardStep = "criteria";
    drafts.settings.filter = { ...EMPTY_FILTER_DRAFT };
    return;
  }

  if (field === "Save Gmail settings") {
    applyRequest(state, "PUT", "settings", drafts.settings.values as unknown as Record<string, unknown>);
    drafts.settings.values = structuredClone(state.settings);
    return;
  }

  if (field === "Add contact") {
    applyRequest(state, "POST", "contacts", {
      name: drafts.contacts.name,
      email: drafts.contacts.email,
      company: drafts.contacts.company,
      note: drafts.contacts.note,
      is_vip: drafts.contacts.isVip,
    });
    drafts.contacts = {
      name: "",
      email: "",
      company: "",
      note: "",
      isVip: false,
      editingId: null,
      page: drafts.contacts.page,
    };
    return;
  }

  if (field.startsWith("Star contact ") || field.startsWith("Unstar contact ")) {
    const contactName = field.replace(/^Un?star contact /, "");
    const contact = findContactByName(state, contactName);
    if (contact) {
      applyRequest(state, "PUT", `contacts/${contact.id}`, {
        is_starred: !Boolean(contact.is_starred),
      });
    }
    return;
  }

  if (field.startsWith("Reply all to ")) {
    const currentThread = getCurrentThreadEmail(state, route);
    if (currentThread) {
      drafts.compose = createReplyDraft(state, currentThread, "replyAll");
    }
    return;
  }

  if (field.startsWith("Reply to ")) {
    const currentThread = getCurrentThreadEmail(state, route);
    if (currentThread) {
      drafts.compose = createReplyDraft(state, currentThread, "reply");
    }
    return;
  }

  if (field === "Forward this thread") {
    const currentThread = getCurrentThreadEmail(state, route);
    if (currentThread) {
      drafts.compose = createForwardDraft(currentThread);
    }
    return;
  }

  if (field === "Run search" || field === "Search") {
    drafts.searchActive = true;
    return;
  }

  // Navigation — these change the displayed page but don't mutate state
  if (field === "Back to inbox" || field === "Inbox" || field === "Cancel compose") {
    drafts.compose = null;
    drafts.searchQuery = "";
    drafts.searchActive = false;
    return;
  }

  if (field === "Labels" || field === "Settings" || field === "Sent" ||
      field === "Starred" || field === "Promotions" || field === "Updates" ||
      field === "Primary" || field === "General") {
    drafts.searchQuery = "";
    drafts.searchActive = false;
    return;
  }

  if (field === "Filters and Blocked Addresses") {
    drafts.settings.activeTab = "Filters and Blocked Addresses";
    return;
  }

  if (field === "Show CC field") {
    if (drafts.compose) drafts.compose.showCc = true;
    return;
  }

  if (field === "Show BCC field") {
    if (drafts.compose) drafts.compose.showBcc = true;
    return;
  }

  if (field === "Cancel filter creation" || field === "Close Create a filter") {
    drafts.settings.filterWizardOpen = false;
    drafts.settings.filterWizardStep = "criteria";
    drafts.settings.filter = { ...EMPTY_FILTER_DRAFT };
    return;
  }

  if (field === "Save contact changes") {
    if (!drafts.contacts.editingId) return;
    applyRequest(state, "PUT", `contacts/${drafts.contacts.editingId}`, {
      name: drafts.contacts.name,
      email: drafts.contacts.email,
      company: drafts.contacts.company,
      note: drafts.contacts.note,
      is_vip: drafts.contacts.isVip,
    });
    drafts.contacts = {
      name: "",
      email: "",
      company: "",
      note: "",
      isVip: false,
      editingId: null,
      page: drafts.contacts.page,
    };
    return;
  }

  if (field === "Cancel contact editing") {
    drafts.contacts = {
      name: "",
      email: "",
      company: "",
      note: "",
      isVip: false,
      editingId: null,
      page: drafts.contacts.page,
    };
    return;
  }

  if (field === "Next contacts page" || field === "Previous contacts page") {
    const totalPages = Math.max(1, Math.ceil(state.contacts.length / CONTACTS_PAGE_SIZE));
    drafts.contacts.page = field === "Next contacts page"
      ? Math.min(totalPages, drafts.contacts.page + 1)
      : Math.max(1, drafts.contacts.page - 1);
    return;
  }

  if (field === "Save" && drafts.settings.activeTab === "Labels" && drafts.settings.renamingLabelId) {
    applyRequest(state, "PUT", `labels/${drafts.settings.renamingLabelId}`, {
      name: drafts.settings.renameLabelDraft.trim(),
    });
    drafts.settings.renamingLabelId = null;
    drafts.settings.renameLabelDraft = "";
    return;
  }

  if (field === "Cancel" && drafts.settings.activeTab === "Labels" && drafts.settings.renamingLabelId) {
    drafts.settings.renamingLabelId = null;
    drafts.settings.renameLabelDraft = "";
    return;
  }

  if (field === "Mark all as read") {
    for (const email of state.emails) {
      email.is_read = true;
    }
    return;
  }

  if (field === "Mark as read") {
    const currentThread = getCurrentThreadEmail(state, route);
    if (currentThread) {
      applyRequest(state, "POST", `emails/${currentThread.id}/read`, { is_read: true });
    }
    return;
  }

  if (field.startsWith("Expand ") || field === "show" || field === "hide" ||
      field === "show if unread" || field.startsWith("Show ") || field === "Rename" ||
      field === "Save" || field === "Confirm delete label" || field === "Delete") {
    // UI expand/collapse — no state mutation
    return;
  }

  if (field.startsWith("Read thread from ")) {
    // Clicking a read thread works like Open thread
    const email = resolveEmailFromTarget(state, route, target);
    if (email) {
      applyRequest(state, "POST", `emails/${email.id}/read`, { is_read: true });
    }
    drafts.searchQuery = "";
    drafts.searchActive = false;
    drafts.compose = null;
    return;
  }

  if (field.startsWith("Create label ") && !field.startsWith("Create label ")) {
    // Already handled above for the generic "Create label" button
  }

  // Tab clicks in settings
  if (target?.role === "tab") {
    drafts.settings.activeTab = field;
    return;
  }

  if (field === "Compose a new message" || (pathname === "/compose" && field === "Compose")) {
    drafts.compose = createComposeDraft();
    return;
  }

  if (field === "Send") {
    if (!drafts.compose) return;
    applyRequest(state, "POST", "send", {
      to: splitList(drafts.compose.to),
      cc: splitList(drafts.compose.cc),
      bcc: splitList(drafts.compose.bcc),
      subject: drafts.compose.subject,
      body: drafts.compose.body,
      thread_id: drafts.compose.threadId,
      in_reply_to: drafts.compose.replyTo,
      attachments: splitList(drafts.compose.attachments).map((filename) => ({
        filename,
        content_type: "application/octet-stream",
        size_bytes: Math.max(filename.length * 64, 128),
        kind: "file",
      })),
    });
    drafts.compose = null;
    return;
  }

  if (field === "Send reply") {
    if (!drafts.compose) return;
    applyRequest(state, "POST", "send", {
      to: splitList(drafts.compose.to),
      cc: splitList(drafts.compose.cc),
      bcc: splitList(drafts.compose.bcc),
      subject: drafts.compose.subject,
      body: drafts.compose.body,
      thread_id: drafts.compose.threadId,
      in_reply_to: drafts.compose.replyTo,
      attachments: splitList(drafts.compose.attachments).map((filename) => ({
        filename,
        content_type: "application/octet-stream",
        size_bytes: Math.max(filename.length * 64, 128),
        kind: "file",
      })),
    });
    drafts.compose = null;
    return;
  }

  if (field === "Forward") {
    if (!drafts.compose?.emailId) return;
    applyRequest(state, "POST", `emails/${drafts.compose.emailId}/forward`, {
      to: splitList(drafts.compose.to),
      cc: splitList(drafts.compose.cc),
      bcc: splitList(drafts.compose.bcc),
      body: drafts.compose.body,
    });
    drafts.compose = null;
    return;
  }
}

function stepTarget(step: TrajectoryStep) {
  return step.targets.ref ?? step.targets.from_ref ?? step.targets.to_ref ?? null;
}

export function buildGmailReplayStepStates(
  initialFixture: GmailFixture,
  steps: TrajectoryStep[],
): GmailReplayStepState[] {
  let state = structuredClone(initialFixture);
  const drafts = createInitialDrafts(state);
  const snapshots: GmailReplayStepState[] = [];

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const target = stepTarget(step);
    const route = step.replay_path ?? DEFAULT_ROUTE;
    const action = String(step.action?.action ?? "");
    const status = String(step.status ?? "").trim();
    const shouldApplyAction =
      status === ""
      || /^success\b/i.test(status)
      || /^finish\b/i.test(status);

    if (shouldApplyAction) {
      switch (action) {
        case "fill":
          applyFill(drafts, state, route, target, step.action?.value);
          break;
        case "check":
          applyCheck(drafts, target);
          break;
        case "select":
        case "select_option":
          applySelect(drafts, target, step.action?.value);
          break;
        case "click":
        case "dblclick":
          applyClick(state, drafts, route, target);
          break;
        case "clear":
          applyFill(drafts, state, route, target, "");
          break;
        case "scroll":
        case "hover":
        case "press":
        case "focus":
        case "noop":
        case "think":
        case "finish":
        case "report_infeasible":
          // Visual-only actions — no state mutation needed
          break;
        default:
          break;
      }
    }

    // The next step's replay_path reflects the page the agent actually saw
    // after this action. result_path is often stale in exported trajectories.
    const resultRoute =
      (i + 1 < steps.length ? steps[i + 1].replay_path : undefined) ||
      step.result_path ||
      route;
    const displayRoute = withReplayParams(resultRoute, drafts);

    snapshots.push({
      fixture: structuredClone(state),
      displayRoute,
    });
  }

  return snapshots;
}
