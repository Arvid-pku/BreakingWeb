import { useNavigate, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Post } from "../types";
import { activateOnKeyDown, formatNumber, safeHostname, timeAgo } from "../utils";

interface PostCardProps {
  post: Post;
  onVote: (postId: string, direction: number) => void;
  onSave?: (postId: string) => void;
  onHide?: (postId: string) => void;
  onDelete?: (postId: string) => void;
  onEdit?: (postId: string) => void;
  ownerUsername?: string;
  compact?: boolean;
  blurNsfw?: boolean;
}

export function PostCard({
  post,
  onVote,
  onSave,
  onHide,
  onDelete,
  onEdit,
  ownerUsername,
  compact,
  blurNsfw,
}: PostCardProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const postRoute = preserveQueryParams(`/post/${post.id}`, location.search);
  const postHostname = post.post_type === "link" && post.url ? safeHostname(post.url) : null;

  const openPost = () => {
    navigate(postRoute, { state: { postPreview: post } });
  };

  return (
    <article
      className={[
        "post-card",
        compact ? "post-card--compact" : "",
        blurNsfw ? "post-card--nsfw-blur" : "",
      ].filter(Boolean).join(" ")}
      aria-label={`Post: ${post.title}`}
    >
      {/* Header: subreddit + author + time + Join */}
      <div className="post-card__header">
        <span className="post-card__sub-icon">
          {post.subreddit_name.charAt(0).toUpperCase()}
        </span>
        <button
          className="post-card__subreddit"
          onClick={(e) => { e.stopPropagation(); navigate(preserveQueryParams(`/r/${post.subreddit_name}`, location.search)); }}
          aria-label={`Go to r/${post.subreddit_name}`}
        >
          r/{post.subreddit_name}
        </button>
        <span className="post-card__sep">·</span>
        <button
          className="post-card__author"
          onClick={(e) => { e.stopPropagation(); navigate(preserveQueryParams(`/u/${post.author_name}`, location.search)); }}
        >
          u/{post.author_name}
        </button>
        <span className="post-card__sep">·</span>
        <span className="post-card__time">{timeAgo(post.created_at)}</span>
        {post.is_pinned && <span className="post-card__badge post-card__badge--pinned">Pinned</span>}
        {post.is_locked && <span className="post-card__badge post-card__badge--locked">Locked</span>}
      </div>

      {/* Flair */}
      {post.flair_text && (
        <span className="post-card__flair" style={{ backgroundColor: post.flair_color ?? "#0079d3" }}>
          {post.flair_text}
        </span>
      )}

      {/* Title */}
      <h3
        className="post-card__title"
        onClick={openPost}
        onKeyDown={(event) => activateOnKeyDown(event, openPost)}
        role="link"
        tabIndex={0}
      >
        {post.is_spoiler && <span className="post-card__spoiler-tag">SPOILER</span>}
        {post.is_nsfw && <span className="post-card__nsfw-tag">NSFW</span>}
        {post.title}
        {postHostname && (
          <span className="post-card__domain">({postHostname})</span>
        )}
      </h3>

      {/* Body preview */}
      {!compact && post.body && (
        <div className="post-card__body-preview">
          {post.body.length > 300 ? `${post.body.slice(0, 300)}...` : post.body}
        </div>
      )}

      {/* Awards */}
      {post.awards.length > 0 && (
        <div className="post-card__awards">
          {post.awards.map((award, i) => (
            <span key={i} className="post-card__award" title={award.name}>
              {award.name}
              {award.count > 1 && <span>{award.count}</span>}
            </span>
          ))}
        </div>
      )}

      {/* Action bar: votes + comments + award + save + hide + share — HORIZONTAL like real Reddit */}
      <div className="post-card__actions">
        <div className="post-card__vote-group">
          <button
            className={`post-card__vote-btn ${post.vote_direction === 1 ? "post-card__vote-btn--up-active" : ""}`}
            onClick={(e) => { e.stopPropagation(); onVote(post.id, post.vote_direction === 1 ? 0 : 1); }}
            aria-label="Upvote"
            aria-pressed={post.vote_direction === 1}
          >▲</button>
          <span className={`post-card__score ${post.vote_direction === 1 ? "post-card__score--up" : post.vote_direction === -1 ? "post-card__score--down" : ""}`}>
            {formatNumber(post.score)}
          </span>
          <button
            className={`post-card__vote-btn ${post.vote_direction === -1 ? "post-card__vote-btn--down-active" : ""}`}
            onClick={(e) => { e.stopPropagation(); onVote(post.id, post.vote_direction === -1 ? 0 : -1); }}
            aria-label="Downvote"
            aria-pressed={post.vote_direction === -1}
          >▼</button>
        </div>

        <button
          className="post-card__action-btn"
          onClick={openPost}
          aria-label={`${post.comment_count} comments`}
        >
          {post.comment_count} comments
        </button>

        <button
          className="post-card__action-btn"
          onClick={(e) => { e.stopPropagation(); onSave?.(post.id); }}
          aria-label={post.is_saved ? "Unsave" : "Save"}
        >
          {post.is_saved ? "★ Saved" : "☆ Save"}
        </button>

        <button
          className="post-card__action-btn"
          onClick={(e) => { e.stopPropagation(); onHide?.(post.id); }}
          aria-label="Hide"
        >
          Hide
        </button>

        <button className="post-card__action-btn" aria-label="Share">
          Share
        </button>

        {ownerUsername && post.author_name === ownerUsername && onEdit && (
          <button className="post-card__action-btn" onClick={(e) => { e.stopPropagation(); onEdit(post.id); }} aria-label="Edit">Edit</button>
        )}
        {ownerUsername && post.author_name === ownerUsername && onDelete && (
          <button className="post-card__action-btn post-card__action-btn--danger" onClick={(e) => { e.stopPropagation(); onDelete(post.id); }} aria-label="Delete">Delete</button>
        )}
      </div>
    </article>
  );
}
