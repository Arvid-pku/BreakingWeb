import type { KeyboardEvent } from "react";
import type { Post, RedditSettings } from "./types";

export function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const seconds = Math.max(0, Math.floor((now - then) / 1000));

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  const years = Math.floor(months / 12);
  return `${years}y ago`;
}

export function formatNumber(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function activateOnKeyDown(event: KeyboardEvent<HTMLElement>, action: () => void): void {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  event.preventDefault();
  action();
}

export function safeHostname(url: string): string | null {
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

export function resolveFeedSort(sort: string | null, settings: RedditSettings | null): string {
  return sort ?? settings?.default_feed_sort ?? "hot";
}

export function resolveCommentSort(sort: string | null, settings: RedditSettings | null): string {
  return sort ?? settings?.default_comment_sort ?? "best";
}

export function isPostVisible(post: Pick<Post, "is_nsfw">, settings: RedditSettings | null): boolean {
  if (!post.is_nsfw) {
    return true;
  }
  return settings?.show_nsfw ?? false;
}

export function shouldBlurNsfw(post: Pick<Post, "is_nsfw">, settings: RedditSettings | null): boolean {
  return Boolean(post.is_nsfw && (settings?.show_nsfw ?? false) && (settings?.blur_nsfw ?? false));
}
