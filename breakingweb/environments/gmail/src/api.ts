import type { ApiRequestOptions } from "@breakingweb/shared";

import type {
  ComposePayload,
  Contact,
  EmailListResponse,
  FilterRule,
  GmailSettings,
  Label,
  ThreadResponse,
} from "./types";

type RequestFn = <T>(path: string, options?: ApiRequestOptions) => Promise<T>;

export function createGmailApi(request: RequestFn) {
  return {
    listEmails: (query?: Record<string, unknown>) =>
      request<EmailListResponse>("emails", { query }),
    getThread: (emailId: string) =>
      request<ThreadResponse>(`emails/${emailId}`),
    markRead: (emailId: string) =>
      request(`emails/${emailId}/read`, { method: "POST" }),
    markAllRead: () =>
      request("emails/mark-all-read", { method: "POST" }),
    toggleStar: (emailId: string) =>
      request(`emails/${emailId}/star`, { method: "POST" }),
    setStar: (emailId: string, is_starred: boolean) =>
      request(`emails/${emailId}/star`, { method: "POST", body: { is_starred } }),
    archive: (emailId: string) =>
      request(`emails/${emailId}/archive`, { method: "POST" }),
    deleteEmail: (emailId: string) =>
      request(`emails/${emailId}/delete`, { method: "POST" }),
    restoreEmail: (emailId: string) =>
      request(`emails/${emailId}/restore`, { method: "POST" }),
    applyEmailLabel: (emailId: string, label: string, action: "add" | "remove" = "add") =>
      request(`emails/${emailId}/label`, { method: "POST", body: { label, action } }),
    forward: (emailId: string, payload: { to: string[]; cc?: string[]; bcc?: string[]; body: string }) =>
      request(`emails/${emailId}/forward`, { method: "POST", body: payload }),
    sendMessage: (payload: ComposePayload) =>
      request<{ email: unknown }>("send", {
        method: "POST",
        body: {
          to: payload.to,
          cc: payload.cc,
          bcc: payload.bcc,
          subject: payload.subject,
          body: payload.body,
          thread_id: payload.thread_id ?? null,
          in_reply_to: payload.reply_to ?? null,
          attachments: (payload.attachments ?? []).map((filename) => ({
            filename,
            content_type: "application/octet-stream",
            size_bytes: Math.max(filename.length * 64, 128),
            kind: "file",
          })),
        },
      }),
    getLabels: async () => (await request<{ items: Label[] }>("labels")).items,
    createLabel: (
      payload: {
        name: string;
        color: string;
        show_in_label_list?: string;
        show_in_message_list?: string;
        show_in_imap?: boolean;
      },
    ) =>
      request<{ label: Label }>("labels", { method: "POST", body: payload }).then((response) => response.label),
    updateLabel: (
      labelId: string,
      payload: { name?: string; show_in_label_list?: string; show_in_message_list?: string; show_in_imap?: boolean },
    ) =>
      request<{ label: Label }>(`labels/${labelId}`, { method: "PUT", body: payload }).then((response) => response.label),
    renameLabel: (labelId: string, payload: { name: string }) =>
      request<{ label: Label }>(`labels/${labelId}`, { method: "PUT", body: payload }).then((response) => response.label),
    deleteLabel: (labelId: string) =>
      request(`labels/${labelId}`, { method: "DELETE" }),
    getFilters: async () => (await request<{ items: FilterRule[] }>("filters")).items,
    createFilter: (payload: Omit<FilterRule, "id">) =>
      request<{ filter: FilterRule }>("filters", { method: "POST", body: payload }).then((response) => response.filter),
    deleteFilter: (filterId: string) =>
      request(`filters/${filterId}`, { method: "DELETE" }),
    getContacts: async () => (await request<{ items: Contact[] }>("contacts")).items,
    createContact: (payload: Omit<Contact, "id">) =>
      request<{ contact: Contact }>("contacts", { method: "POST", body: payload }).then((response) => response.contact),
    updateContact: (contactId: string, payload: Partial<Omit<Contact, "id">>) =>
      request<{ contact: Contact }>(`contacts/${contactId}`, { method: "PUT", body: payload }).then((response) => response.contact),
    setContactStar: (contactId: string, is_starred: boolean) =>
      request<{ contact: Contact }>(`contacts/${contactId}`, { method: "PUT", body: { is_starred } }).then((response) => response.contact),
    deleteContact: (contactId: string) =>
      request(`contacts/${contactId}`, { method: "DELETE" }),
    search: (q: string, query?: Record<string, unknown>) =>
      request<EmailListResponse>("search", { query: { q, ...(query ?? {}) } }),
    getSettings: () => request<{ settings: GmailSettings }>("settings").then((response) => response.settings),
    updateSettings: (payload: GmailSettings) =>
      request<{ settings: GmailSettings }>("settings", { method: "PUT", body: payload }).then((response) => response.settings),
  };
}
