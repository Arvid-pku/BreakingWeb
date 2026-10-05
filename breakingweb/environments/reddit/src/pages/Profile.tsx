import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useRedditLayout } from "../context";
import { PostCard } from "../components/PostCard";
import type { Comment, Post, UserProfile } from "../types";
import { formatDate, formatNumber, isPostVisible, shouldBlurNsfw } from "../utils";

export function ProfilePage() {
  const { username } = useParams<{ username: string }>();
  const { api, notify, profile, settings } = useRedditLayout();

  const [user, setUser] = useState<UserProfile | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [tab, setTab] = useState<"posts" | "comments">("posts");
  const [loading, setLoading] = useState(true);
  const [isBlocked, setIsBlocked] = useState(false);
  const [blockBusy, setBlockBusy] = useState(false);

  const load = useCallback(async () => {
    if (!username) return;
    setLoading(true);
    try {
      const data = await api.getUserProfile(username);
      setUser(data.user);
      setPosts(data.posts);
      setComments(data.comments);
    } catch {
      notify("Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, [api, username, notify]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!username || !profile) return;
    setIsBlocked((profile.blocked_users ?? []).includes(username));
  }, [username, profile]);

  const handleVote = async (postId: string, direction: number) => {
    try {
      const { post } = await api.votePost(postId, direction);
      setPosts((prev) => prev.map((p) => (p.id === postId ? post : p)));
    } catch { notify("Failed to vote"); }
  };

  const handleSave = async (postId: string) => {
    const target = posts.find((p) => p.id === postId);
    if (!target) return;
    try {
      const { post } = target.is_saved
        ? await api.unsavePost(postId)
        : await api.savePost(postId);
      setPosts((prev) => prev.map((p) => (p.id === postId ? post : p)));
    } catch { notify("Failed to save"); }
  };

  const handleHide = async (postId: string) => {
    const target = posts.find((p) => p.id === postId);
    if (!target) return;
    try {
      const { post } = target.is_hidden
        ? await api.unhidePost(postId)
        : await api.hidePost(postId);
      setPosts((prev) => prev.map((p) => (p.id === postId ? post : p)));
    } catch { notify("Failed to hide"); }
  };

  const handleToggleBlock = async () => {
    if (!user || blockBusy) return;
    setBlockBusy(true);
    try {
      if (isBlocked) {
        await api.unblockUser(user.username as string);
        setIsBlocked(false);
        notify(`Unblocked u/${user.username}`);
      } else {
        await api.blockUser(user.username as string);
        setIsBlocked(true);
        notify(`Blocked u/${user.username}`);
      }
    } catch {
      notify(isBlocked ? "Failed to unblock user" : "Failed to block user");
    } finally {
      setBlockBusy(false);
    }
  };

  if (loading) return <div className="profile-page__loading">Loading...</div>;
  if (!user) return <div className="profile-page__error">User not found</div>;

  const visiblePosts = posts.filter((post) => isPostVisible(post, settings));
  const hasHiddenPosts = visiblePosts.length < posts.length;
  const isOwnProfile = profile?.username === user.username;
  const visibleCommunities =
    isOwnProfile && settings?.show_active_communities
      ? (profile?.subscriptions ?? []).slice(0, 5)
      : [];

  return (
    <div className="profile-page">
      <div className="profile-header">
        <div className="profile-header__avatar">
          {(user.username as string).charAt(0).toUpperCase()}
        </div>
        <div className="profile-header__info">
          <h1 className="profile-header__username">u/{user.username as string}</h1>
          {isOwnProfile && settings?.show_online_status ? (
            <div className="profile-header__status">Online now</div>
          ) : null}
          {user.display_name && <p className="profile-header__display-name">{user.display_name as string}</p>}
          {user.about && <p className="profile-header__about">{user.about as string}</p>}
          <div className="profile-header__stats">
            <div className="profile-stat">
              <span className="profile-stat__value">{formatNumber(user.post_karma as number)}</span>
              <span className="profile-stat__label">Post Karma</span>
            </div>
            <div className="profile-stat">
              <span className="profile-stat__value">{formatNumber(user.comment_karma as number)}</span>
              <span className="profile-stat__label">Comment Karma</span>
            </div>
            {user.cake_day && (
              <div className="profile-stat">
                <span className="profile-stat__value">Cake Day</span>
                <span className="profile-stat__label">{formatDate(user.cake_day as string)}</span>
              </div>
            )}
          </div>
          {visibleCommunities.length > 0 ? (
            <div className="profile-header__communities" aria-label="Active communities">
              {visibleCommunities.map((subreddit) => (
                <span key={subreddit.id} className="profile-community-chip">
                  r/{subreddit.name}
                </span>
              ))}
            </div>
          ) : null}
          {!isOwnProfile ? (
            <div className="profile-header__actions">
              <button
                type="button"
                className={`profile-header__block-btn ${isBlocked ? "profile-header__block-btn--blocked" : ""}`}
                onClick={handleToggleBlock}
                disabled={blockBusy}
                aria-pressed={isBlocked}
                aria-label={isBlocked ? `Unblock u/${user.username as string}` : `Block u/${user.username as string}`}
              >
                {blockBusy ? "Working..." : isBlocked ? "Unblock user" : "Block user"}
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="profile-tabs" role="tablist">
        <button role="tab" aria-selected={tab === "posts"} className={`profile-tab ${tab === "posts" ? "profile-tab--active" : ""}`} onClick={() => setTab("posts")}>
          Posts ({posts.length})
        </button>
        <button role="tab" aria-selected={tab === "comments"} className={`profile-tab ${tab === "comments" ? "profile-tab--active" : ""}`} onClick={() => setTab("comments")}>
          Comments ({comments.length})
        </button>
      </div>

      {tab === "posts" ? (
        <div className="profile-posts">
          {visiblePosts.length === 0 ? (
            <div className="profile-empty">{hasHiddenPosts ? "Posts are hidden by your NSFW settings." : "No posts yet"}</div>
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
      ) : (
        <div className="profile-comments">
          {comments.length === 0 ? (
            <div className="profile-empty">No comments yet</div>
          ) : (
            comments.map((comment) => (
              <div key={comment.id} className="profile-comment">
                <div className="profile-comment__meta">
                  <span className="profile-comment__context">in {comment.post_id}</span>
                  <span>{comment.score} points</span>
                </div>
                <div className="profile-comment__body">{comment.body}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
