import { useRef, useState } from "react";

import type { Comment } from "../types";
import { VoteButtons } from "./VoteButtons";
import { activateOnKeyDown, timeAgo } from "../utils";

interface CommentThreadProps {
  comments: Comment[];
  onVote: (commentId: string, direction: number) => void;
  onReply: (commentId: string, body: string) => void;
  onSave?: (commentId: string) => void;
  onEdit?: (commentId: string, body: string) => void;
  onDelete?: (commentId: string) => void;
  ownerUsername: string;
}

function buildTree(comments: Comment[]): Map<string | null, Comment[]> {
  const tree = new Map<string | null, Comment[]>();
  for (const c of comments) {
    const key = c.parent_id ?? null;
    if (!tree.has(key)) tree.set(key, []);
    tree.get(key)!.push(c);
  }
  return tree;
}

function CommentNode({
  comment,
  tree,
  onVote,
  onReply,
  onSave,
  onEdit,
  onDelete,
  ownerUsername,
}: {
  comment: Comment;
  tree: Map<string | null, Comment[]>;
  onVote: (commentId: string, direction: number) => void;
  onReply: (commentId: string, body: string) => void;
  onSave?: (commentId: string) => void;
  onEdit?: (commentId: string, body: string) => void;
  onDelete?: (commentId: string) => void;
  ownerUsername: string;
}) {
  const [isReplying, setIsReplying] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(comment.body);
  const [isCollapsed, setIsCollapsed] = useState(comment.is_collapsed);
  const isOwner = comment.author_name === ownerUsername;
  const children = tree.get(comment.id) ?? [];
  const replyRef = useRef<HTMLTextAreaElement>(null);
  const editRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmitReply = () => {
    const body = (replyRef.current?.value ?? replyText).trim();
    if (!body) return;
    onReply(comment.id, body);
    setReplyText("");
    if (replyRef.current) replyRef.current.value = "";
    setIsReplying(false);
  };

  const handleSubmitEdit = () => {
    if (!onEdit) return;
    const body = (editRef.current?.value ?? editText).trim();
    if (!body) return;
    onEdit(comment.id, body);
    setIsEditing(false);
  };

  return (
    <div className="comment-node" data-comment-id={comment.id} data-author={comment.author_name} style={{ marginLeft: `${Math.min(comment.depth * 20, 100)}px` }}>
      <div
        className="comment-node__collapse-bar"
        onClick={() => setIsCollapsed(!isCollapsed)}
        onKeyDown={(event) => activateOnKeyDown(event, () => setIsCollapsed(!isCollapsed))}
        role="button"
        tabIndex={0}
        aria-label={isCollapsed ? "Expand comment" : "Collapse comment"}
      />
      <div className="comment-node__body">
        <div className="comment-node__header">
          <button className="comment-node__toggle" onClick={() => setIsCollapsed(!isCollapsed)} aria-label={isCollapsed ? "Expand" : "Collapse"}>
            {isCollapsed ? "[+]" : "[-]"}
          </button>
          <span className={`comment-node__author ${comment.is_submitter ? "comment-node__author--op" : ""}`}>
            {comment.author_name}
            {comment.is_submitter && <span className="comment-node__op-badge">OP</span>}
          </span>
          {comment.flair_text && <span className="comment-node__flair">{comment.flair_text}</span>}
          <span className="comment-node__score">{comment.score} points</span>
          <span className="comment-node__dot">·</span>
          <span className="comment-node__time">{timeAgo(comment.created_at)}</span>
          {comment.is_edited && <span className="comment-node__edited">(edited)</span>}
          {comment.awards.length > 0 && (
            <span className="comment-node__awards">
              {comment.awards.map((a, i) => (
                <span key={i} title={a.name}>[{a.name}]</span>
              ))}
            </span>
          )}
        </div>

        {!isCollapsed && (
          <>
            <div className="comment-node__text">{comment.body}</div>
            <div className="comment-node__actions">
              <VoteButtons
                score={comment.score}
                voteDirection={comment.vote_direction}
                onVote={(dir) => onVote(comment.id, dir)}
                vertical={false}
              />
              <button className="comment-action" data-comment-id={comment.id} data-action="reply" onClick={() => setIsReplying(!isReplying)} aria-label={`Reply to comment by ${comment.author_name}`}>
                Reply
              </button>
              <button
                className={`comment-action ${comment.is_saved ? "comment-action--active" : ""}`}
                data-comment-id={comment.id}
                data-action={comment.is_saved ? "unsave" : "save"}
                onClick={() => onSave?.(comment.id)}
                aria-label={comment.is_saved ? `Unsave comment by ${comment.author_name}` : `Save comment by ${comment.author_name}`}
              >
                {comment.is_saved ? "★ Saved" : "☆ Save"}
              </button>
              {isOwner && onEdit && !comment.is_removed && (
                <button className="comment-action" data-comment-id={comment.id} data-action="edit" onClick={() => { setIsEditing(!isEditing); setEditText(comment.body); }} aria-label={`Edit comment by ${comment.author_name}`}>
                  Edit
                </button>
              )}
              {isOwner && onDelete && !comment.is_removed && (
                <button className="comment-action comment-action--danger" data-comment-id={comment.id} data-action="delete" onClick={() => onDelete(comment.id)} aria-label={`Delete comment by ${comment.author_name}`}>
                  Delete
                </button>
              )}
            </div>

            {isEditing && onEdit && (
              <div className="comment-node__reply-form" data-comment-id={comment.id}>
                <textarea
                  ref={editRef}
                  data-comment-id={comment.id}
                  data-role="edit-body"
                  className="comment-reply-textarea"
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  rows={3}
                  aria-label={`Edit comment text (${comment.author_name})`}
                />
                <div className="comment-reply-actions">
                  <button className="comment-reply-cancel" data-comment-id={comment.id} onClick={() => setIsEditing(false)}>Cancel</button>
                  <button className="comment-reply-submit" data-comment-id={comment.id} data-action="edit-submit" onClick={handleSubmitEdit}>Save Edit</button>
                </div>
              </div>
            )}

            {isReplying && (
              <div className="comment-node__reply-form" data-comment-id={comment.id}>
                <textarea
                  ref={replyRef}
                  data-comment-id={comment.id}
                  data-role="reply-body"
                  className="comment-reply-textarea"
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder={`Reply to ${comment.author_name}...`}
                  rows={3}
                  aria-label={`Reply text for comment by ${comment.author_name}`}
                />
                <div className="comment-reply-actions">
                  <button className="comment-reply-cancel" data-comment-id={comment.id} onClick={() => { setIsReplying(false); setReplyText(""); }}>Cancel</button>
                  <button className="comment-reply-submit" data-comment-id={comment.id} data-action="reply-submit" onClick={handleSubmitReply}>Reply</button>
                </div>
              </div>
            )}

            {children.map((child) => (
              <CommentNode
                key={child.id}
                comment={child}
                tree={tree}
                onVote={onVote}
                onReply={onReply}
                onSave={onSave}
                onEdit={onEdit}
                onDelete={onDelete}
                ownerUsername={ownerUsername}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}

export function CommentThread({ comments, onVote, onReply, onSave, onEdit, onDelete, ownerUsername }: CommentThreadProps) {
  const tree = buildTree(comments);
  const topLevel = tree.get(null) ?? [];

  return (
    <div className="comment-thread" aria-label="Comments">
      {topLevel.length === 0 ? (
        <div className="comment-thread__empty">No comments yet. Be the first to comment!</div>
      ) : (
        topLevel.map((comment) => (
          <CommentNode
            key={comment.id}
            comment={comment}
            tree={tree}
            onVote={onVote}
            onReply={onReply}
            onSave={onSave}
            onEdit={onEdit}
            onDelete={onDelete}
            ownerUsername={ownerUsername}
          />
        ))
      )}
    </div>
  );
}
