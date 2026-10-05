import { useCallback, useEffect, useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useRedditLayout } from "../context";
import { PostCard } from "../components/PostCard";
import { CommunityInfo } from "../components/RightSidebar";
import type { Post, Subreddit as SubredditType } from "../types";
import { isPostVisible, resolveFeedSort, shouldBlurNsfw } from "../utils";

export function SubredditPage() {
  const { subredditName } = useParams<{ subredditName: string }>();
  const { api, notify, settings } = useRedditLayout();
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const sort = resolveFeedSort(params.get("sort"), settings);

  const [subreddit, setSubreddit] = useState<SubredditType | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!subredditName) return;
    setLoading(true);
    try {
      const data = await api.getSubredditPage(subredditName, { sort });
      setSubreddit(data.subreddit);
      setPosts(data.items);
    } catch {
      notify("Failed to load subreddit");
    } finally {
      setLoading(false);
    }
  }, [api, subredditName, sort, notify]);

  useEffect(() => { void load(); }, [load]);

  const handleVote = async (postId: string, direction: number) => {
    try {
      const { post } = await api.votePost(postId, direction);
      setPosts((prev) => prev.map((p) => (p.id === postId ? post : p)));
    } catch { notify("Failed to vote"); }
  };

  const handleSave = async (postId: string) => {
    const post = posts.find((p) => p.id === postId);
    if (!post) return;
    try {
      const { post: updated } = post.is_saved
        ? await api.unsavePost(postId)
        : await api.savePost(postId);
      setPosts((prev) => prev.map((p) => (p.id === postId ? updated : p)));
    } catch { notify("Failed to save"); }
  };

  const handleHide = async (postId: string) => {
    try {
      await api.hidePost(postId);
      setPosts((prev) => prev.filter((p) => p.id !== postId));
    } catch { notify("Failed to hide"); }
  };

  const handleSubscribe = async () => {
    if (!subreddit) return;
    try {
      const { subreddit: updated } = subreddit.is_subscribed
        ? await api.unsubscribe(subreddit.name)
        : await api.subscribe(subreddit.name);
      setSubreddit(updated);
      notify(updated.is_subscribed ? `Joined r/${subreddit.name}` : `Left r/${subreddit.name}`);
    } catch { notify("Failed to update subscription"); }
  };

  const visiblePosts = posts.filter((post) => isPostVisible(post, settings));
  const hasHiddenPosts = posts.length > visiblePosts.length;

  if (loading) return <div className="subreddit-page__loading">Loading...</div>;
  if (!subreddit) return <div className="subreddit-page__error">Subreddit not found</div>;

  return (
    <div className="subreddit-page">
      <div className="subreddit-header">
        <div className="subreddit-header__icon">
          {subreddit.name.charAt(0).toUpperCase()}
        </div>
        <div className="subreddit-header__info">
          <h1 className="subreddit-header__name">r/{subreddit.name}</h1>
        </div>
        <div className="subreddit-header__actions">
          <button
            type="button"
            className="subreddit-page__create-btn"
            aria-label={`Create a new post in r/${subredditName}`}
            onClick={() => navigate(preserveQueryParams(`/submit?subreddit=${subredditName}`, location.search))}
          >
            + Create Post
          </button>
          <button
            className={`subreddit-header__join-btn ${subreddit.is_subscribed ? "subreddit-header__join-btn--joined" : ""}`}
            onClick={handleSubscribe}
            aria-label={subreddit.is_subscribed ? `Leave r/${subreddit.name}` : `Join r/${subreddit.name}`}
          >
            {subreddit.is_subscribed ? "Joined" : "Join"}
          </button>
        </div>
      </div>

      <div className="subreddit-page__body feed-page--with-sidebar">
        <div className="feed-page__main">
          <div className="subreddit-page__sort-bar">
            <div className="sort-tabs" role="tablist">
              {["hot", "new", "top", "rising"].map((s) => (
                <button
                  key={s}
                  role="tab"
                  aria-selected={sort === s}
                  className={`sort-tab ${sort === s ? "sort-tab--active" : ""}`}
                  onClick={() => navigate(preserveQueryParams(`/r/${subredditName}?sort=${s}`, location.search))}
                >
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div className="subreddit-page__posts">
            {visiblePosts.length === 0 ? (
              <div className="subreddit-page__empty">
                {hasHiddenPosts ? "NSFW posts are hidden by your settings." : "No posts in this subreddit yet."}
              </div>
            ) : (
              visiblePosts.map((post) => (
                <PostCard
                  key={post.id}
                  post={post}
                  onVote={handleVote}
                  onSave={handleSave}
                  onHide={handleHide}
                  compact={settings?.compact_view ?? false}
                  blurNsfw={shouldBlurNsfw(post, settings)}
                />
              ))
            )}
          </div>
        </div>

        <aside className="right-sidebar" aria-label="Community info">
          <CommunityInfo subreddit={subreddit} onSubscribe={handleSubscribe} />
        </aside>
      </div>
    </div>
  );
}
