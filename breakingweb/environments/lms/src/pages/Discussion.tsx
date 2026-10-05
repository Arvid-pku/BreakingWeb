import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { useLmsLayout } from "../context";
import type { Discussion as DiscussionType, DiscussionPost } from "../types";

export function DiscussionPage() {
  const { id: courseId, did: discussionId } = useParams<{ id: string; did: string }>();
  const { api, student, notify } = useLmsLayout();

  const [discussion, setDiscussion] = useState<DiscussionType | null>(null);
  const [posts, setPosts] = useState<DiscussionPost[]>([]);
  const [newPostBody, setNewPostBody] = useState("");
  const [replyBodies, setReplyBodies] = useState<Record<string, string>>({});
  const [showReplyForm, setShowReplyForm] = useState<Record<string, boolean>>({});
  const [editBodies, setEditBodies] = useState<Record<string, string>>({});
  const [showEditForm, setShowEditForm] = useState<Record<string, boolean>>({});
  const [posting, setPosting] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadDiscussion = async () => {
    try {
      const data = await api.getDiscussion(discussionId!);
      setDiscussion(data.discussion);
      setPosts(data.posts);
    } catch {
      // handled
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await loadDiscussion();
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [api, discussionId]);

  const handleCreatePost = async () => {
    if (!newPostBody.trim()) return;
    setPosting(true);
    try {
      await api.createPost(discussionId!, newPostBody.trim());
      setNewPostBody("");
      await loadDiscussion();
      notify("Post Created", "Your post has been added to the discussion");
    } catch {
      notify("Post Failed", "Unable to create post");
    } finally {
      setPosting(false);
    }
  };

  const handleEditOpen = (post: DiscussionPost) => {
    setEditBodies((prev) => ({ ...prev, [post.id]: post.body }));
    setShowEditForm((prev) => ({ ...prev, [post.id]: true }));
  };

  const handleEditCancel = (postId: string) => {
    setShowEditForm((prev) => ({ ...prev, [postId]: false }));
  };

  const handleEditSave = async (postId: string) => {
    const body = editBodies[postId]?.trim();
    if (!body) return;
    setPosting(true);
    try {
      const updated = await api.updatePost(discussionId!, postId, body);
      setPosts((prev) => prev.map((p) => p.id === updated.id ? updated : p));
      setShowEditForm((prev) => ({ ...prev, [postId]: false }));
      notify("Post Updated", "Your post has been updated");
    } catch {
      notify("Update Failed", "Unable to update post");
    } finally {
      setPosting(false);
    }
  };

  const handleReply = async (postId: string) => {
    const body = replyBodies[postId]?.trim();
    if (!body) return;
    setPosting(true);
    try {
      await api.replyToPost(discussionId!, postId, body);
      setReplyBodies((prev) => ({ ...prev, [postId]: "" }));
      setShowReplyForm((prev) => ({ ...prev, [postId]: false }));
      await loadDiscussion();
      notify("Reply Posted", "Your reply has been added");
    } catch {
      notify("Reply Failed", "Unable to post reply");
    } finally {
      setPosting(false);
    }
  };

  if (loading) return <div className="lms-loading">Loading...</div>;
  if (!discussion) return <div className="lms-empty">Discussion not found</div>;

  // Calculate participation
  const studentId = student?.id;
  const myPosts = posts.filter((p) => p.author_id === studentId && !p.parent_post_id).length;
  const myReplies = posts.filter((p) => p.author_id === studentId && p.parent_post_id !== null).length;

  // Build thread structure
  const topLevelPosts = posts.filter((p) => !p.parent_post_id);
  const getReplies = (postId: string) => posts.filter((p) => p.parent_post_id === postId);

  return (
    <div aria-label={`Discussion ${discussion.title}`}>
      <h1 className="lms-section-header">{discussion.title}</h1>

      {/* Discussion Info */}
      <div className="lms-card" aria-label="Discussion Details">
        <p><strong>Prompt:</strong> {discussion.prompt}</p>
        <p><strong>Due date:</strong> {new Date(discussion.due_at).toLocaleString()}</p>
        <p><strong>Points:</strong> {discussion.points_possible}</p>
        <p>
          <strong>Requirements:</strong> Minimum {discussion.min_posts} posts, {discussion.min_replies} replies
        </p>
      </div>

      {/* Participation Counter */}
      <div className="lms-card" aria-label="Participation Status">
        <h2 className="lms-card__title">Your Participation</h2>
        <p aria-label={`Your posts ${myPosts} of ${discussion.min_posts} required posts`}>
          <strong>Posts:</strong> {myPosts} of {discussion.min_posts} required
          {myPosts >= discussion.min_posts ? " \u2705" : ""}
        </p>
        <p aria-label={`Your replies ${myReplies} of ${discussion.min_replies} required replies`}>
          <strong>Replies:</strong> {myReplies} of {discussion.min_replies} required
          {myReplies >= discussion.min_replies ? " \u2705" : ""}
        </p>
      </div>

      {/* New Post Form */}
      <div className="lms-card" aria-label="New Post Form">
        <h2 className="lms-card__title">New Post</h2>
        <textarea
          className="lms-input"
          style={{ width: "100%", minHeight: "80px", resize: "vertical" }}
          value={newPostBody}
          onChange={(e) => setNewPostBody(e.target.value)}
          placeholder="Write your post..."
          aria-label="New post body"
        />
        <div style={{ marginTop: "0.5rem" }}>
          <button
            type="button"
            className="lms-btn lms-btn--primary"
            onClick={handleCreatePost}
            disabled={posting || !newPostBody.trim()}
            aria-label="Submit new post"
          >
            {posting ? "Posting..." : "Post"}
          </button>
        </div>
      </div>

      {/* Thread View */}
      <section aria-label="Discussion Posts" style={{ marginTop: "1rem" }}>
        <h2 className="lms-card__title">
          Posts ({topLevelPosts.length})
        </h2>
        {topLevelPosts.length === 0 ? (
          <p className="lms-empty">No posts yet. Be the first to post!</p>
        ) : (
          topLevelPosts.map((post) => {
            const replies = getReplies(post.id);
            return (
              <div key={post.id}>
                <div className="lms-post" aria-label={`Post by ${post.author_name}`}>
                  <div className="lms-post__meta">
                    <strong>{post.is_anonymous ? "Anonymous" : post.author_name}</strong>
                    {" -- "}
                    {new Date(post.timestamp).toLocaleString()}
                    {post.updated_at && " (edited)"}
                  </div>
                  <div className="lms-post__body">{post.body}</div>
                  <div className="lms-post__actions">
                    <button
                      type="button"
                      className="lms-btn lms-btn--secondary"
                      onClick={() =>
                        setShowReplyForm((prev) => ({
                          ...prev,
                          [post.id]: !prev[post.id],
                        }))
                      }
                      aria-label={`Reply to post by ${post.author_name}`}
                    >
                      Reply
                    </button>
                    {post.author_id === studentId && (
                      <button
                        type="button"
                        className="lms-btn lms-btn--secondary"
                        onClick={() => handleEditOpen(post)}
                        aria-label={`Edit your post`}
                        style={{ marginLeft: "0.5rem" }}
                      >
                        Edit
                      </button>
                    )}
                  </div>
                  {showEditForm[post.id] && (
                    <div style={{ marginTop: "0.5rem" }}>
                      <textarea
                        className="lms-input"
                        style={{ width: "100%", minHeight: "60px", resize: "vertical" }}
                        value={editBodies[post.id] ?? ""}
                        onChange={(e) =>
                          setEditBodies((prev) => ({
                            ...prev,
                            [post.id]: e.target.value,
                          }))
                        }
                        placeholder="Edit your post..."
                        aria-label="Edit post body"
                      />
                      <div style={{ marginTop: "0.25rem", display: "flex", gap: "0.5rem" }}>
                        <button
                          type="button"
                          className="lms-btn lms-btn--primary"
                          onClick={() => handleEditSave(post.id)}
                          disabled={posting || !editBodies[post.id]?.trim()}
                          aria-label="Save edited post"
                        >
                          {posting ? "Saving..." : "Save"}
                        </button>
                        <button
                          type="button"
                          className="lms-btn lms-btn--secondary"
                          onClick={() => handleEditCancel(post.id)}
                          aria-label="Cancel edit"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                  {showReplyForm[post.id] && (
                    <div style={{ marginTop: "0.5rem" }}>
                      <textarea
                        className="lms-input"
                        style={{ width: "100%", minHeight: "60px", resize: "vertical" }}
                        value={replyBodies[post.id] ?? ""}
                        onChange={(e) =>
                          setReplyBodies((prev) => ({
                            ...prev,
                            [post.id]: e.target.value,
                          }))
                        }
                        placeholder="Write your reply..."
                        aria-label={`Reply body for post by ${post.author_name}`}
                      />
                      <button
                        type="button"
                        className="lms-btn lms-btn--primary"
                        style={{ marginTop: "0.25rem" }}
                        onClick={() => handleReply(post.id)}
                        disabled={posting || !replyBodies[post.id]?.trim()}
                        aria-label="Submit reply"
                      >
                        {posting ? "Replying..." : "Submit Reply"}
                      </button>
                    </div>
                  )}
                </div>
                {/* Nested replies */}
                {replies.map((reply) => (
                  <div key={reply.id} className="lms-post lms-post--reply" aria-label={`Reply by ${reply.author_name}`}>
                    <div className="lms-post__meta">
                      <strong>{reply.is_anonymous ? "Anonymous" : reply.author_name}</strong>
                      {" -- "}
                      {new Date(reply.timestamp).toLocaleString()}
                      {reply.updated_at && " (edited)"}
                    </div>
                    <div className="lms-post__body">{reply.body}</div>
                  </div>
                ))}
              </div>
            );
          })
        )}
      </section>
    </div>
  );
}
