import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRedditLayout } from "../context";

export function SubmitPage() {
  const { api, notify, profile } = useRedditLayout();
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const defaultSubreddit = params.get("subreddit") ?? "";

  const [subredditName, setSubredditName] = useState(defaultSubreddit);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [url, setUrl] = useState("");
  const [postType, setPostType] = useState<"text" | "link">("text");
  const [flairText, setFlairText] = useState("");
  const [isSpoiler, setIsSpoiler] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!subredditName.trim() || !title.trim()) return;
    setIsSubmitting(true);
    try {
      const { post } = await api.createPost({
        subreddit_name: subredditName.trim(),
        title: title.trim(),
        body: postType === "text" ? body : "",
        url: postType === "link" ? url : "",
        post_type: postType,
        flair_text: flairText || undefined,
        is_spoiler: isSpoiler,
      });
      // Fallback author_name to the current user when the backend response
      // omits it — keeps the optimistic preview readable instead of "u/".
      const previewPost = post.author_name ? post : { ...post, author_name: profile?.username ?? post.author_name };
      notify("Post submitted!");
      navigate(preserveQueryParams(`/post/${post.id}`, location.search), { state: { postPreview: previewPost } });
    } catch {
      notify("Failed to submit post. Make sure the subreddit name is correct.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="submit-page">
      <h1 className="submit-page__title">Create a post</h1>

      <div className="submit-page__form">
        <div className="submit-page__field">
          <label htmlFor="subreddit-input">Community</label>
          <input
            id="subreddit-input"
            type="text"
            value={subredditName}
            onChange={(e) => setSubredditName(e.target.value)}
            placeholder="r/subreddit_name"
            className="submit-page__input"
            aria-label="Subreddit name"
          />
        </div>

        <div className="submit-page__type-tabs" role="tablist" aria-label="Post type">
          <button
            role="tab"
            aria-selected={postType === "text"}
            className={`submit-page__type-tab ${postType === "text" ? "submit-page__type-tab--active" : ""}`}
            onClick={() => setPostType("text")}
          >
            Text
          </button>
          <button
            role="tab"
            aria-selected={postType === "link"}
            className={`submit-page__type-tab ${postType === "link" ? "submit-page__type-tab--active" : ""}`}
            onClick={() => setPostType("link")}
          >
            Link
          </button>
        </div>

        <div className="submit-page__field">
          <label htmlFor="title-input">Title</label>
          <input
            id="title-input"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="An interesting title"
            className="submit-page__input"
            maxLength={300}
            aria-label="Post title"
          />
          <span className="submit-page__char-count">{title.length}/300</span>
        </div>

        {postType === "text" ? (
          <div className="submit-page__field">
            <label htmlFor="body-input">Body</label>
            <textarea
              id="body-input"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Text (optional)"
              className="submit-page__textarea"
              rows={8}
              aria-label="Post body"
            />
          </div>
        ) : (
          <div className="submit-page__field">
            <label htmlFor="url-input">URL</label>
            <input
              id="url-input"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://..."
              className="submit-page__input"
              aria-label="Link URL"
            />
          </div>
        )}

        <div className="submit-page__field">
          <label htmlFor="flair-input">Flair (optional)</label>
          <input
            id="flair-input"
            type="text"
            value={flairText}
            onChange={(e) => setFlairText(e.target.value)}
            placeholder="e.g. Discussion, OC, Question"
            className="submit-page__input"
            aria-label="Post flair"
          />
        </div>

        <div className="submit-page__options">
          <label className="submit-page__checkbox">
            <input type="checkbox" checked={isSpoiler} onChange={(e) => setIsSpoiler(e.target.checked)} />
            Mark as Spoiler
          </label>
        </div>

        <div className="submit-page__actions">
          <Button variant="secondary" onClick={() => navigate(-1)}>Cancel</Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={isSubmitting || !subredditName.trim() || !title.trim()}
            aria-label="Submit post"
          >
            {isSubmitting ? "Posting..." : "Post"}
          </Button>
        </div>
      </div>
    </div>
  );
}
