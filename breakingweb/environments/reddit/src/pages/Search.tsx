import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useRedditLayout } from "../context";
import { PostCard } from "../components/PostCard";
import type { Post, Subreddit } from "../types";
import { activateOnKeyDown, formatNumber, isPostVisible, shouldBlurNsfw } from "../utils";

export function SearchPage() {
  const { api, notify, setSearchValue, settings } = useRedditLayout();
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const query = params.get("q") ?? "";
  const type = params.get("type") ?? "posts";
  const sort = params.get("sort") ?? "relevance";

  const [results, setResults] = useState<(Post | Subreddit)[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setSearchValue(query);
  }, [query, setSearchValue]);

  const doSearch = useCallback(async () => {
    if (!query.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await api.search(query, { type, sort });
      setResults(data.items);
    } catch {
      notify("Search failed");
    } finally {
      setLoading(false);
    }
  }, [api, query, type, sort, notify]);

  useEffect(() => { void doSearch(); }, [doSearch]);

  const handleVote = async (postId: string, direction: number) => {
    try {
      const { post } = await api.votePost(postId, direction);
      setResults((prev) => prev.map((r) => ("score" in r && r.id === postId ? post : r)));
    } catch { notify("Failed to vote"); }
  };

  const handleSave = async (postId: string) => {
    const target = results.find((r) => "score" in r && r.id === postId) as Post | undefined;
    if (!target) return;
    try {
      const { post } = target.is_saved
        ? await api.unsavePost(postId)
        : await api.savePost(postId);
      setResults((prev) => prev.map((r) => ("score" in r && r.id === postId ? post : r)));
    } catch { notify("Failed to save"); }
  };

  const handleHide = async (postId: string) => {
    const target = results.find((r) => "score" in r && r.id === postId) as Post | undefined;
    if (!target) return;
    try {
      const { post } = target.is_hidden
        ? await api.unhidePost(postId)
        : await api.hidePost(postId);
      setResults((prev) => prev.map((r) => ("score" in r && r.id === postId ? post : r)));
    } catch { notify("Failed to hide"); }
  };

  const visiblePostResults =
    type === "posts" ? (results as Post[]).filter((post) => isPostVisible(post, settings)) : [];
  const hasHiddenPostResults = type === "posts" && visiblePostResults.length < results.length;

  return (
    <div className="search-page">
      <h2 className="search-page__heading">
        {query ? `Search results for "${query}"` : "Search Reddit"}
      </h2>

      <div className="search-page__tabs" role="tablist">
        <button role="tab" aria-selected={type === "posts"} className={`search-tab ${type === "posts" ? "search-tab--active" : ""}`} onClick={() => navigate(preserveQueryParams(`/search?q=${encodeURIComponent(query)}&type=posts`, location.search))}>
          Posts
        </button>
        <button role="tab" aria-selected={type === "subreddits"} className={`search-tab ${type === "subreddits" ? "search-tab--active" : ""}`} onClick={() => navigate(preserveQueryParams(`/search?q=${encodeURIComponent(query)}&type=subreddits`, location.search))}>
          Communities
        </button>
      </div>

      {type === "posts" && (
        <div className="search-page__sort">
          <select value={sort} onChange={(e) => navigate(preserveQueryParams(`/search?q=${encodeURIComponent(query)}&type=posts&sort=${e.target.value}`, location.search))} aria-label="Sort results">
            <option value="relevance">Relevance</option>
            <option value="top">Top</option>
            <option value="new">New</option>
            <option value="comments">Most Comments</option>
          </select>
        </div>
      )}

      {loading ? (
        <div className="search-page__loading">Searching...</div>
      ) : (type === "posts" ? visiblePostResults.length === 0 : results.length === 0) ? (
        <div className="search-page__empty">
          {query ? (hasHiddenPostResults ? "Search results are hidden by your NSFW settings." : "No results found") : "Enter a search query above"}
        </div>
      ) : type === "subreddits" ? (
        <div className="search-page__subreddits">
          {(results as Subreddit[]).map((sub) => (
            <div
              key={sub.id}
              className="search-subreddit-card"
              onClick={() => navigate(preserveQueryParams(`/r/${sub.name}`, location.search))}
              onKeyDown={(event) =>
                activateOnKeyDown(event, () => navigate(preserveQueryParams(`/r/${sub.name}`, location.search)))
              }
              role="link"
              tabIndex={0}
            >
              <h3 className="search-subreddit-card__name">r/{sub.name}</h3>
              <p className="search-subreddit-card__desc">{sub.description}</p>
              <span className="search-subreddit-card__members">{formatNumber(sub.subscriber_count)} members</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="search-page__posts">
          {visiblePostResults.map((post) => (
            <PostCard
              key={post.id}
              post={post}
              onVote={handleVote}
              onSave={handleSave}
              onHide={handleHide}
              compact={settings?.compact_view ?? false}
              blurNsfw={shouldBlurNsfw(post, settings)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
