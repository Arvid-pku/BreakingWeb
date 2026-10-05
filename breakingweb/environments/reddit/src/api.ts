import type { ApiRequestOptions } from "@breakingweb/shared";

import type {
  Comment,
  Message,
  MyProfile,
  Notification,
  PaginatedResponse,
  Post,
  PostDetailResponse,
  RedditSettings,
  Subreddit,
  SubredditPageResponse,
  UserProfile,
} from "./types";

type RequestFn = <T>(path: string, options?: ApiRequestOptions) => Promise<T>;

export function createRedditApi(request: RequestFn) {
  return {
    // Feed
    getFeed: (query?: Record<string, unknown>) =>
      request<PaginatedResponse<Post> & { sort: string; time_filter: string }>("feed", { query }),

    // Subreddits
    listSubreddits: (filter?: string) =>
      request<{ items: Subreddit[] }>("subreddits", { query: { filter } }),
    getSubredditPage: (name: string, query?: Record<string, unknown>) =>
      request<SubredditPageResponse>(`r/${name}`, { query }),
    subscribe: (name: string) =>
      request<{ subreddit: Subreddit }>(`r/${name}/subscribe`, { method: "POST", body: { action: "subscribe" } }),
    unsubscribe: (name: string) =>
      request<{ subreddit: Subreddit }>(`r/${name}/subscribe`, { method: "POST", body: { action: "unsubscribe" } }),

    // Posts
    getPost: (postId: string, commentSort?: string) =>
      request<PostDetailResponse>(`posts/${postId}`, { query: { comment_sort: commentSort } }),
    createPost: (payload: {
      subreddit_name: string;
      title: string;
      body?: string;
      url?: string;
      post_type?: string;
      flair_text?: string;
      is_spoiler?: boolean;
      is_nsfw?: boolean;
    }) =>
      request<{ post: Post }>("posts", { method: "POST", body: payload }),
    editPost: (postId: string, body: string) =>
      request<{ post: Post }>(`posts/${postId}`, { method: "PUT", body: { body } }),
    deletePost: (postId: string) =>
      request<{ post: Post }>(`posts/${postId}`, { method: "DELETE" }),
    votePost: (postId: string, direction: number) =>
      request<{ post: Post }>(`posts/${postId}/vote`, { method: "POST", body: { direction } }),
    savePost: (postId: string) =>
      request<{ post: Post }>(`posts/${postId}/save`, { method: "POST" }),
    unsavePost: (postId: string) =>
      request<{ post: Post }>(`posts/${postId}/unsave`, { method: "POST" }),
    hidePost: (postId: string) =>
      request<{ post: Post }>(`posts/${postId}/hide`, { method: "POST" }),
    unhidePost: (postId: string) =>
      request<{ post: Post }>(`posts/${postId}/unhide`, { method: "POST" }),

    // Comments
    getComments: (postId: string, sort?: string) =>
      request<{ items: Comment[]; sort: string }>(`posts/${postId}/comments`, { query: { sort } }),
    createComment: (postId: string, body: string, parentId?: string) =>
      request<{ comment: Comment }>(`posts/${postId}/comments`, { method: "POST", body: { body, parent_id: parentId } }),
    editComment: (commentId: string, body: string) =>
      request<{ comment: Comment }>(`comments/${commentId}`, { method: "PUT", body: { body } }),
    deleteComment: (commentId: string) =>
      request<{ comment: Comment }>(`comments/${commentId}`, { method: "DELETE" }),
    voteComment: (commentId: string, direction: number) =>
      request<{ comment: Comment }>(`comments/${commentId}/vote`, { method: "POST", body: { direction } }),
    saveComment: (commentId: string) =>
      request<{ comment: Comment }>(`comments/${commentId}/save`, { method: "POST" }),
    unsaveComment: (commentId: string) =>
      request<{ comment: Comment }>(`comments/${commentId}/unsave`, { method: "POST" }),

    // Messages
    listMessages: (folder?: string) =>
      request<{ items: Message[]; folder: string; unread_count: number }>("messages", { query: { folder } }),
    getMessage: (messageId: string) =>
      request<{ message: Message }>(`messages/${messageId}`),
    sendMessage: (payload: { to_user: string; subject: string; body: string; parent_id?: string }) =>
      request<{ message: Message }>("messages", { method: "POST", body: payload }),
    markMessageRead: (messageId: string) =>
      request<{ message: Message }>(`messages/${messageId}/read`, { method: "POST" }),
    markAllMessagesRead: () =>
      request<{ marked: number }>("messages/mark-all-read", { method: "POST" }),
    deleteMessage: (messageId: string) =>
      request(`messages/${messageId}`, { method: "DELETE" }),

    // Notifications
    listNotifications: () =>
      request<{ items: Notification[]; unread_count: number }>("notifications"),
    markNotificationRead: (notificationId: string) =>
      request<{ notification: Notification }>(`notifications/${notificationId}/read`, { method: "POST" }),
    markAllNotificationsRead: () =>
      request<{ marked: number }>("notifications/mark-all-read", { method: "POST" }),

    // Search
    search: (q: string, query?: Record<string, unknown>) =>
      request<PaginatedResponse<Post | Subreddit> & { query: string; type: string }>("search", { query: { q, ...query } }),

    // User
    getMyProfile: () =>
      request<MyProfile>("me"),
    getUserProfile: (username: string) =>
      request<{ user: UserProfile; posts: Post[]; comments: Comment[] }>(`user/${username}`),
    getSaved: () =>
      request<{ posts: Post[]; comments: Comment[] }>("saved"),

    // Settings
    getSettings: () =>
      request<{ settings: RedditSettings }>("settings").then((r) => r.settings),
    updateSettings: (payload: Partial<RedditSettings>) =>
      request<{ settings: RedditSettings }>("settings", { method: "PUT", body: payload }).then((r) => r.settings),

    // Block
    blockUser: (username: string) =>
      request(`block/${username}`, { method: "POST" }),
    unblockUser: (username: string) =>
      request(`unblock/${username}`, { method: "POST" }),
  };
}
