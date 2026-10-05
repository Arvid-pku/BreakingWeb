import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useRedditLayout } from "../context";
import { VoteButtons } from "../components/VoteButtons";
import { CommentThread } from "../components/CommentThread";
import type { Post as PostType, Comment } from "../types";
import { resolveCommentSort, shouldBlurNsfw, timeAgo } from "../utils";

export function PostPage() {
  const { postId } = useParams<{ postId: string }>();
  const { api, profile, notify, settings } = useRedditLayout();
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const commentSort = resolveCommentSort(params.get("comment_sort"), settings);
  const previewPost =
    (location.state as { postPreview?: PostType } | null)?.postPreview?.id === postId
      ? (location.state as { postPreview?: PostType }).postPreview ?? null
      : null;

  const [post, setPost] = useState<PostType | null>(previewPost);
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(previewPost === null);
  const [newComment, setNewComment] = useState("");
  const [activePostId, setActivePostId] = useState(postId);
  const [isEditing, setIsEditing] = useState(false);
  const [editBody, setEditBody] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  // Fallback for agents that set textarea.value programmatically without
  // dispatching an input event (React's synthetic onChange then never
  // fires, leaving `newComment` stale and the submit button disabled).
  const newCommentRef = useRef<HTMLTextAreaElement>(null);
  const editBodyRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (activePostId === postId) {
      return;
    }
    setActivePostId(postId);
    setComments([]);
    setNewComment("");
    setPost(previewPost);
    setIsEditing(false);
    setEditBody("");
  }, [activePostId, postId, previewPost]);

  const load = useCallback(async () => {
    if (!postId) return;
    setLoading(true);
    try {
      const data = await api.getPost(postId, commentSort);
      setPost(data.post);
      setComments(data.comments);
    } catch {
      notify("Failed to load post");
    } finally {
      setLoading(false);
    }
  }, [api, postId, commentSort, notify]);

  useEffect(() => { void load(); }, [load]);

  const handleVotePost = async (direction: number) => {
    if (!post) return;
    try {
      const { post: updated } = await api.votePost(post.id, direction);
      setPost(updated);
    } catch { notify("Failed to vote"); }
  };

  const handleVoteComment = async (commentId: string, direction: number) => {
    try {
      const { comment: updated } = await api.voteComment(commentId, direction);
      setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
    } catch { notify("Failed to vote"); }
  };

  const handleAddComment = async () => {
    const body = (newCommentRef.current?.value ?? newComment).trim();
    if (!postId || !body) return;
    try {
      const { comment } = await api.createComment(postId, body);
      setComments((prev) => [comment, ...prev]);
      setNewComment("");
      if (newCommentRef.current) newCommentRef.current.value = "";
      if (post) setPost({ ...post, comment_count: post.comment_count + 1 });
      notify("Comment posted");
    } catch { notify("Failed to post comment"); }
  };

  const handleReply = async (parentId: string, body: string) => {
    if (!postId) return;
    try {
      const { comment } = await api.createComment(postId, body, parentId);
      setComments((prev) => [...prev, comment]);
      if (post) setPost({ ...post, comment_count: post.comment_count + 1 });
      notify("Reply posted");
    } catch { notify("Failed to post reply"); }
  };

  const handleSaveComment = async (commentId: string) => {
    const comment = comments.find((c) => c.id === commentId);
    if (!comment) return;
    try {
      const { comment: updated } = comment.is_saved
        ? await api.unsaveComment(commentId)
        : await api.saveComment(commentId);
      setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
    } catch { notify("Failed to save"); }
  };

  const handleSavePost = async () => {
    if (!post) return;
    try {
      const { post: updated } = post.is_saved
        ? await api.unsavePost(post.id)
        : await api.savePost(post.id);
      setPost(updated);
      notify(updated.is_saved ? "Post saved" : "Post unsaved");
    } catch { notify("Failed to save"); }
  };

  const handleEditComment = async (commentId: string, body: string) => {
    try {
      const { comment: updated } = await api.editComment(commentId, body);
      setComments((prev) => prev.map((c) => (c.id === commentId ? updated : c)));
      notify("Comment edited");
    } catch { notify("Failed to edit comment"); }
  };

  const handleDeleteComment = async (commentId: string) => {
    try {
      await api.deleteComment(commentId);
      setComments((prev) => prev.map((c) => (c.id === commentId ? { ...c, is_removed: true, body: "[deleted]" } : c)));
      notify("Comment deleted");
    } catch { notify("Failed to delete comment"); }
  };

  const handleDeletePost = async () => {
    if (!post) return;
    try {
      await api.deletePost(post.id);
      notify("Post deleted");
      navigate(preserveQueryParams(`/r/${post.subreddit_name}`, location.search));
    } catch { notify("Failed to delete post"); }
  };

  const handleStartEdit = () => {
    if (!post) return;
    setEditBody(post.body ?? "");
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditBody("");
  };

  const handleSaveEdit = async () => {
    if (!post) return;
    setEditSubmitting(true);
    const body = editBodyRef.current?.value ?? editBody;
    try {
      const { post: updated } = await api.editPost(post.id, body);
      setPost(updated);
      setIsEditing(false);
      setEditBody("");
      notify("Post edited");
    } catch {
      notify("Failed to edit post");
    } finally {
      setEditSubmitting(false);
    }
  };

  if (loading && !post) return <div className="post-page__loading">Loading...</div>;
  if (!post) return <div className="post-page__error">Post not found</div>;

  const hideNsfw = post.is_nsfw && !(settings?.show_nsfw ?? false);
  const blurNsfw = shouldBlurNsfw(post, settings);
  const openLinksInNewTab = settings?.open_links_in_new_tab ?? true;

  return (
    <div className="post-page">
      <article
        className={["post-detail", blurNsfw ? "post-detail--nsfw-blur" : ""].filter(Boolean).join(" ")}
        aria-label={post.title}
      >
        <div className="post-detail__left">
          <VoteButtons score={post.score} voteDirection={post.vote_direction} onVote={handleVotePost} />
        </div>
        <div className="post-detail__content">
          <div className="post-detail__meta">
            <button
              className="post-detail__subreddit"
              onClick={() => navigate(preserveQueryParams(`/r/${post.subreddit_name}`, location.search))}
            >
              r/{post.subreddit_name}
            </button>
            <span className="post-detail__dot">·</span>
            <span>Posted by <button className="post-detail__author" onClick={() => navigate(preserveQueryParams(`/u/${post.author_name}`, location.search))}>u/{post.author_name}</button></span>
            <span className="post-detail__dot">·</span>
            <span>{timeAgo(post.created_at)}</span>
            {post.is_edited && <span className="post-detail__edited">(edited)</span>}
          </div>

          {post.flair_text && (
            <span className="post-detail__flair" style={{ backgroundColor: post.flair_color ?? "#edeff1" }}>{post.flair_text}</span>
          )}

          <h1 className="post-detail__title">{post.title}</h1>

          {hideNsfw ? (
            <div className="post-detail__nsfw-blocked">
              NSFW content is hidden by your settings. Enable “Show NSFW content” in Settings to view this post.
            </div>
          ) : isEditing ? (
            <div className="post-detail__edit-form">
              <textarea
                ref={editBodyRef}
                className="post-detail__edit-input"
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
                rows={6}
                aria-label="Edit post body"
              />
              <div className="post-detail__edit-actions">
                <button
                  type="button"
                  className="post-action post-action--primary"
                  onClick={handleSaveEdit}
                  disabled={editSubmitting}
                  aria-label="Save edited post"
                >
                  {editSubmitting ? "Saving..." : "Save edits"}
                </button>
                <button
                  type="button"
                  className="post-action"
                  onClick={handleCancelEdit}
                  disabled={editSubmitting}
                  aria-label="Cancel edit"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              {post.body && <div className="post-detail__body">{post.body}</div>}
              {post.post_type === "link" && post.url && (
                <a
                  href={post.url}
                  className="post-detail__link"
                  target={openLinksInNewTab ? "_blank" : undefined}
                  rel={openLinksInNewTab ? "noopener noreferrer" : undefined}
                >
                  {post.url}
                </a>
              )}
            </>
          )}

          {post.awards.length > 0 && (
            <div className="post-detail__awards">
              {post.awards.map((a, i) => (
                <span key={i} className="post-detail__award">
                  {a.name}{a.count > 1 ? ` x${a.count}` : ""}
                </span>
              ))}
            </div>
          )}

          <div className="post-detail__actions">
            <span>{post.comment_count} comments</span>
            <button className={`post-action ${post.is_saved ? "post-action--active" : ""}`} onClick={handleSavePost} aria-label={post.is_saved ? "Unsave" : "Save"}>
              {post.is_saved ? "★ Saved" : "☆ Save"}
            </button>
            <button className="post-action" aria-label="Share">Share</button>
            {profile && post.author_name === profile.username && !isEditing && (
              <button className="post-action" onClick={handleStartEdit} aria-label="Edit post">Edit</button>
            )}
            {profile && post.author_name === profile.username && (
              <button className="post-action post-action--danger" onClick={handleDeletePost} aria-label="Delete post">Delete</button>
            )}
            {post.is_locked && <span className="post-detail__locked">Comments locked</span>}
          </div>
        </div>
      </article>

      {!hideNsfw && !post.is_locked && (
        <div className="post-page__add-comment">
          <textarea
            ref={newCommentRef}
            className="post-page__comment-input"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="What are your thoughts?"
            rows={4}
            aria-label="Add a comment"
          />
          <button
            className="post-page__comment-submit"
            onClick={handleAddComment}
          >
            Comment
          </button>
        </div>
      )}

      {!hideNsfw ? (
        <div className="post-page__comment-sort">
        <label htmlFor="comment-sort">Sort by: </label>
        <select
          id="comment-sort"
          value={commentSort}
          onChange={(e) => navigate(preserveQueryParams(`/post/${postId}?comment_sort=${e.target.value}`, location.search))}
        >
          <option value="best">Best</option>
          <option value="top">Top</option>
          <option value="new">New</option>
          <option value="controversial">Controversial</option>
          <option value="old">Old</option>
        </select>
        </div>
      ) : null}

      {!hideNsfw && loading ? <div className="post-page__loading">Loading comments...</div> : null}

      {!hideNsfw ? (
        <CommentThread
          comments={comments}
          onVote={handleVoteComment}
          onReply={handleReply}
          onSave={handleSaveComment}
          onEdit={handleEditComment}
          onDelete={handleDeleteComment}
          ownerUsername={profile?.username ?? ""}
        />
      ) : null}
    </div>
  );
}
