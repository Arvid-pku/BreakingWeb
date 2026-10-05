export interface SubredditRule {
  title: string;
  description: string;
  rule_type: string;
}

export interface Flair {
  id: string;
  text: string;
  background_color: string;
  text_color: string;
  is_editable: boolean;
}

export interface Award {
  name: string;
  count: number;
  icon: string;
}

export interface Subreddit {
  id: string;
  name: string;
  display_name: string;
  description: string;
  public_description: string;
  subscriber_count: number;
  active_users: number;
  created_at: string;
  icon_url: string;
  banner_url: string;
  is_nsfw: boolean;
  is_subscribed: boolean;
  rules: SubredditRule[];
  flairs: Flair[];
}

export interface Post {
  id: string;
  subreddit_id: string;
  subreddit_name: string;
  author_name: string;
  title: string;
  body: string;
  url: string;
  post_type: string;
  score: number;
  upvote_ratio: number;
  comment_count: number;
  created_at: string;
  is_pinned: boolean;
  is_locked: boolean;
  is_removed: boolean;
  is_edited: boolean;
  is_spoiler: boolean;
  is_nsfw: boolean;
  flair_text: string | null;
  flair_color: string | null;
  awards: Award[];
  is_saved: boolean;
  is_hidden: boolean;
  vote_direction: number;
  permalink: string;
}

export interface Comment {
  id: string;
  post_id: string;
  parent_id: string | null;
  author_name: string;
  body: string;
  score: number;
  created_at: string;
  is_edited: boolean;
  edited_at: string | null;
  is_removed: boolean;
  is_collapsed: boolean;
  is_saved: boolean;
  is_submitter: boolean;
  vote_direction: number;
  depth: number;
  awards: Award[];
  flair_text: string | null;
}

export interface Message {
  id: string;
  from_user: string;
  to_user: string;
  subject: string;
  body: string;
  created_at: string;
  is_read: boolean;
  parent_id: string | null;
  context: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  created_at: string;
  is_read: boolean;
  related_post_id: string | null;
  related_comment_id: string | null;
  subreddit_name: string | null;
  from_user: string | null;
}

export interface UserProfile {
  username: string;
  display_name: string;
  avatar_url: string;
  about: string;
  post_karma: number;
  comment_karma: number;
  cake_day: string | null;
  is_premium: boolean;
}

export interface RedditSettings {
  id?: string;
  default_feed_sort: string;
  default_comment_sort: string;
  show_nsfw: boolean;
  blur_nsfw: boolean;
  open_links_in_new_tab: boolean;
  theme: string;
  compact_view: boolean;
  email_comment_reply: boolean;
  email_post_reply: boolean;
  email_mentions: boolean;
  email_messages: boolean;
  email_digest: boolean;
  show_online_status: boolean;
  allow_followers: boolean;
  show_active_communities: boolean;
  country: string;
  language: string;
  auto_play_media: boolean;
  reduce_animations: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  page: number;
  total: number;
  page_size: number;
  pages: number;
}

export interface PostDetailResponse {
  post: Post;
  comments: Comment[];
  comment_sort: string;
}

export interface SubredditPageResponse extends PaginatedResponse<Post> {
  subreddit: Subreddit;
  sort: string;
}

export interface MyProfile {
  username: string;
  display_name: string;
  avatar_url: string;
  about: string;
  post_karma: number;
  comment_karma: number;
  cake_day: string | null;
  subscriptions: Subreddit[];
  unread_messages: number;
  unread_notifications: number;
  blocked_users: string[];
}
