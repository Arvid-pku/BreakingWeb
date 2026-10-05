export interface Attachment {
  id: string;
  filename: string;
  content_type?: string;
  size_bytes?: number;
  kind?: string;
}

export interface Email {
  id: string;
  from_name: string;
  from_addr: string;
  to: string[];
  cc: string[];
  bcc?: string[];
  subject: string;
  body: string;
  snippet?: string;
  timestamp: string;
  is_read: boolean;
  is_starred: boolean;
  labels: string[];
  thread_id: string;
  in_reply_to?: string | null;
  attachments: Attachment[];
  thread_size?: number;
}

export interface Label {
  id: string;
  name: string;
  color: string;
  system?: boolean;
  show_in_label_list?: string;
  show_in_message_list?: string;
  show_in_imap?: boolean;
}

export interface FilterRule {
  id: string;
  name: string;
  query: string;
  from_addresses: string[];
  subject_keywords: string[];
  label_requirements: string[];
  has_attachment?: boolean | null;
  add_labels: string[];
  archive: boolean;
  mark_read: boolean;
  forward_to?: string | null;
  star: boolean;
  never_spam?: boolean;
}

export interface Contact {
  id: string;
  name: string;
  email: string;
  company?: string;
  note?: string;
  is_vip?: boolean;
  is_starred?: boolean;
  source?: string;
  last_contacted_at?: string | null;
}

export interface GmailSettings {
  id?: string;
  signature: string;
  forwarding_address?: string | null;
  display_density?: string;
  vacation_responder_enabled?: boolean;
  vacation_responder_message?: string;
  auto_advance?: string;
  language?: string;
  input_tools_enabled?: boolean;
  right_to_left?: boolean;
  max_page_size?: number;
  undo_send_seconds?: number;
  default_reply_behavior?: string;
  hover_actions_enabled?: boolean;
  send_and_archive?: boolean;
  default_text_style?: string;
}

export interface EmailListResponse {
  items: Email[];
  page: number;
  total: number;
  page_size: number;
  pages: number;
  counts?: Record<string, number>;
}

export interface ThreadResponse {
  email: Email;
  thread: Email[];
}

export interface MailboxSummary {
  labels: Label[];
  counts: Record<string, number>;
}

export interface ComposePayload {
  to: string[];
  cc: string[];
  bcc: string[];
  subject: string;
  body: string;
  reply_to?: string | null;
  thread_id?: string | null;
  attachments?: string[];
}
