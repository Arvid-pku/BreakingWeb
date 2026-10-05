import { useCallback, useEffect, useState } from "react";

import { useRedditLayout } from "../context";
import { PostCard } from "../components/PostCard";
import type { Post, Comment } from "../types";
import { isPostVisible, shouldBlurNsfw, timeAgo } from "../utils";

export function SavedPage() {
  const { api, notify, settings } = useRedditLayout();
  const [posts, setPosts] = useState<Post[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [tab, setTab] = useState<"posts" | "comments">("posts");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getSaved();
      setPosts(data.posts);
      setComments(data.comments);
    } catch {
      notify("Failed to load saved items");
    } finally {
      setLoading(false);
    }
  }, [api, notify]);

  useEffect(() => { void load(); }, [load]);

  const handleVote = async (postId: string, direction: number) => {
    try {
      const { post } = await api.votePost(postId, direction);
      setPosts((prev) => prev.map((p) => (p.id === postId ? post : p)));
    } catch { notify("Failed to vote"); }
  };

  const handleUnsave = async (postId: string) => {
    try {
      await api.unsavePost(postId);
      setPosts((prev) => prev.filter((p) => p.id !== postId));
      notify("Post unsaved");
    } catch { notify("Failed to unsave"); }
  };

  const visiblePosts = posts.filter((post) => isPostVisible(post, settings));
  const hasHiddenPosts = visiblePosts.length < posts.length;

  return (
    <div className="saved-page">
      <h1 className="saved-page__title">Saved</h1>

      <div className="saved-tabs" role="tablist">
        <button role="tab" aria-selected={tab === "posts"} className={`saved-tab ${tab === "posts" ? "saved-tab--active" : ""}`} onClick={() => setTab("posts")}>
          Posts ({posts.length})
        </button>
        <button role="tab" aria-selected={tab === "comments"} className={`saved-tab ${tab === "comments" ? "saved-tab--active" : ""}`} onClick={() => setTab("comments")}>
          Comments ({comments.length})
        </button>
      </div>

      {loading ? (
        <div className="saved-loading">Loading...</div>
      ) : tab === "posts" ? (
        visiblePosts.length === 0 ? (
          <div className="saved-empty">{hasHiddenPosts ? "Saved NSFW posts are hidden by your settings." : "No saved posts"}</div>
        ) : (
          <div className="saved-posts">
            {visiblePosts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                onVote={handleVote}
                onSave={handleUnsave}
                compact={settings?.compact_view ?? false}
                blurNsfw={shouldBlurNsfw(post, settings)}
              />
            ))}
          </div>
        )
      ) : (
        comments.length === 0 ? (
          <div className="saved-empty">No saved comments</div>
        ) : (
          <div className="saved-comments">
            {comments.map((comment) => (
              <div key={comment.id} className="saved-comment">
                <div className="saved-comment__meta">
                  <span>u/{comment.author_name}</span>
                  <span>{comment.score} points</span>
                  <span>{timeAgo(comment.created_at)}</span>
                </div>
                <p className="saved-comment__body">{comment.body}</p>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
