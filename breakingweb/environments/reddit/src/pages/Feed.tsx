import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useRedditLayout } from "../context";
import { PostCard } from "../components/PostCard";
import { RightSidebar } from "../components/RightSidebar";
import type { Post, Subreddit } from "../types";
import { isPostVisible, resolveFeedSort, shouldBlurNsfw } from "../utils";

export function FeedPage() {
  const { api, notify, settings } = useRedditLayout();
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const sort = resolveFeedSort(params.get("sort"), settings);
  const timeFilter = params.get("t") ?? "all";

  const [posts, setPosts] = useState<Post[]>([]);
  const [allSubreddits, setAllSubreddits] = useState<Subreddit[]>([]);
  const [loading, setLoading] = useState(true);

  const loadFeed = useCallback(async () => {
    setLoading(true);
    try {
      const [feedData, subsData] = await Promise.all([
        api.getFeed({ sort, time_filter: timeFilter }),
        api.listSubreddits(),
      ]);
      setPosts(feedData.items);
      setAllSubreddits(subsData.items);
    } catch {
      notify("Failed to load feed");
    } finally {
      setLoading(false);
    }
  }, [api, sort, timeFilter, notify]);

  useEffect(() => { void loadFeed(); }, [loadFeed]);

  const handleVote = async (postId: string, direction: number) => {
    try {
      const { post } = await api.votePost(postId, direction);
      setPosts((prev) => prev.map((p) => (p.id === postId ? post : p)));
    } catch {
      notify("Failed to vote");
    }
  };

  const handleSave = async (postId: string) => {
    const post = posts.find((p) => p.id === postId);
    if (!post) return;
    try {
      if (post.is_saved) {
        const { post: updated } = await api.unsavePost(postId);
        setPosts((prev) => prev.map((p) => (p.id === postId ? updated : p)));
        notify("Post unsaved");
      } else {
        const { post: updated } = await api.savePost(postId);
        setPosts((prev) => prev.map((p) => (p.id === postId ? updated : p)));
        notify("Post saved");
      }
    } catch {
      notify("Failed to save");
    }
  };

  const handleHide = async (postId: string) => {
    try {
      await api.hidePost(postId);
      setPosts((prev) => prev.filter((p) => p.id !== postId));
      notify("Post hidden");
    } catch {
      notify("Failed to hide post");
    }
  };

  const setSort = (newSort: string) => {
    navigate(preserveQueryParams(`/feed?sort=${newSort}`, location.search));
  };

  const visiblePosts = posts.filter((post) => isPostVisible(post, settings));
  const hasHiddenPosts = posts.length > visiblePosts.length;

  return (
    <div className="feed-page feed-page--with-sidebar">
      <div className="feed-page__main">
        <div className="feed-page__sort-bar">
          <div className="sort-tabs" role="tablist" aria-label="Sort posts">
            {["hot", "new", "top", "rising"].map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={sort === s}
                className={`sort-tab ${sort === s ? "sort-tab--active" : ""}`}
                onClick={() => setSort(s)}
              >
                {s === "hot" ? "Hot" : s === "new" ? "New" : s === "top" ? "Top" : "Rising"}
              </button>
            ))}
          </div>
          {sort === "top" && (
            <select
              className="time-filter-select"
              value={timeFilter}
              onChange={(e) => navigate(preserveQueryParams(`/feed?sort=top&t=${e.target.value}`, location.search))}
              aria-label="Time filter"
            >
              <option value="day">Today</option>
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="year">This Year</option>
              <option value="all">All Time</option>
            </select>
          )}
        </div>

        {loading ? (
          <div className="feed-page__loading">Loading posts...</div>
        ) : visiblePosts.length === 0 ? (
          <div className="feed-page__empty">
            <p>{hasHiddenPosts ? "NSFW posts are hidden by your settings." : "Nothing here yet! Subscribe to some communities to see posts."}</p>
          </div>
        ) : (
          <div className="feed-page__posts">
            {visiblePosts.map((post) => (
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
      <RightSidebar allSubreddits={allSubreddits} />
    </div>
  );
}
