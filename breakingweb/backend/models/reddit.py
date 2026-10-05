from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseEntity, BaseEnvState, diff_dict_of_dicts


def _reddit_query_tokens(query: str | None) -> list[str]:
    """Tokenize a reddit-style search query.

    Users commonly type the Reddit-convention prefixes ``r/<sub>`` and
    ``u/<user>`` into the search bar. Without special handling those
    prefixes get attached to the real token ("r/machinelearning") and the
    whole-token substring match fails against haystacks that only contain
    the bare name ("machinelearning"). Strip the prefixes so the search
    matches what a human would expect.
    """
    if not query:
        return []
    tokens: list[str] = []
    for raw in query.lower().split():
        tok = raw
        if tok.startswith("/r/") or tok.startswith("/u/"):
            tok = tok[3:]
        elif tok.startswith("r/") or tok.startswith("u/"):
            tok = tok[2:]
        if tok:
            tokens.append(tok)
    return tokens


# ---------------------------------------------------------------------------
# Sub-entities
# ---------------------------------------------------------------------------

class SubredditRule(BaseModel):
    title: str
    description: str
    rule_type: str = "post"  # "post", "comment", "both"

    model_config = ConfigDict(extra="forbid")


class Flair(BaseEntity):
    text: str
    background_color: str = "#edeff1"
    text_color: str = "dark"  # "dark" or "light"
    is_editable: bool = False


class Award(BaseModel):
    name: str
    count: int = 1
    icon: str = ""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Primary objects
# ---------------------------------------------------------------------------

class Subreddit(BaseEntity):
    # Subscribing to a subreddit increments subscriber_count as a side
    # effect of setting is_subscribed=True. The derived counter should
    # not trigger preserve-ALL invariants on unrelated tasks.
    DIFF_IGNORE_FIELDS: ClassVar[tuple[str, ...]] = ("subscriber_count", "active_users")
    name: str  # e.g. "AskReddit" (without r/ prefix)
    display_name: str  # e.g. "Ask Reddit"
    description: str
    public_description: str = ""
    subscriber_count: int
    active_users: int = 0
    created_at: datetime
    icon_url: str = ""
    banner_url: str = ""
    is_nsfw: bool = False
    is_subscribed: bool = False
    rules: list[SubredditRule] = Field(default_factory=list)
    flairs: list[Flair] = Field(default_factory=list)
    allow_text_posts: bool = True
    allow_link_posts: bool = True
    allow_image_posts: bool = True


class Post(BaseEntity):
    # Commenting on or voting on a post mutates these aggregate fields
    # as pure side effects of Comment creation or Vote changes (both of
    # which are already tracked in canonical_diff via their own entities
    # or the post's vote_direction field). Including them here would
    # cause preserve-ALL invariants to fire falsely whenever an agent
    # performs the intended comment/vote action on an in-scope post.
    DIFF_IGNORE_FIELDS: ClassVar[tuple[str, ...]] = ("comment_count", "score", "upvote_ratio")

    subreddit_id: str
    subreddit_name: str
    author_name: str
    author_is_op: bool = True
    title: str
    body: str = ""
    url: str = ""
    post_type: str = "text"  # "text", "link", "image"
    score: int = 0
    upvote_ratio: float = 0.5
    comment_count: int = 0
    created_at: datetime
    is_pinned: bool = False
    is_locked: bool = False
    is_removed: bool = False
    is_edited: bool = False
    is_spoiler: bool = False
    is_nsfw: bool = False
    flair_text: str | None = None
    flair_color: str | None = None
    awards: list[Award] = Field(default_factory=list)
    is_saved: bool = False
    is_hidden: bool = False
    vote_direction: int = 0  # -1, 0, 1
    permalink: str = ""


class Comment(BaseEntity):
    # Voting on a comment mutates its score as a side effect of the
    # vote_direction change. Ignored for the same reason as Post.score.
    DIFF_IGNORE_FIELDS: ClassVar[tuple[str, ...]] = ("score",)

    post_id: str
    parent_id: str | None = None  # None = top-level comment
    author_name: str
    body: str
    score: int = 0
    created_at: datetime
    is_edited: bool = False
    edited_at: datetime | None = None
    is_removed: bool = False
    is_collapsed: bool = False
    is_saved: bool = False
    is_submitter: bool = False  # whether author is the post OP
    vote_direction: int = 0
    depth: int = 0
    awards: list[Award] = Field(default_factory=list)
    flair_text: str | None = None


class Message(BaseEntity):
    from_user: str
    to_user: str
    subject: str
    body: str
    created_at: datetime
    is_read: bool = False
    parent_id: str | None = None
    context: str = ""  # permalink context for comment replies


class Notification(BaseEntity):
    type: str  # "comment_reply", "post_reply", "mention", "upvote_milestone", "award", "message"
    title: str
    body: str
    created_at: datetime
    is_read: bool = False
    related_post_id: str | None = None
    related_comment_id: str | None = None
    subreddit_name: str | None = None
    from_user: str | None = None


class UserProfile(BaseEntity):
    username: str
    display_name: str = ""
    avatar_url: str = ""
    banner_url: str = ""
    about: str = ""
    post_karma: int = 0
    comment_karma: int = 0
    cake_day: datetime | None = None
    is_premium: bool = False
    is_mod: bool = False
    trophies: list[str] = Field(default_factory=list)


class RedditSettings(BaseEntity):
    # Display preferences
    default_feed_sort: str = "hot"  # "hot", "new", "top", "rising"
    default_comment_sort: str = "best"  # "best", "top", "new", "controversial", "old"
    show_nsfw: bool = False
    blur_nsfw: bool = True
    open_links_in_new_tab: bool = True
    theme: str = "light"  # "light", "dark"
    compact_view: bool = False
    # Notification preferences
    email_comment_reply: bool = True
    email_post_reply: bool = True
    email_mentions: bool = True
    email_messages: bool = True
    email_digest: bool = False
    # Privacy
    show_online_status: bool = True
    allow_followers: bool = True
    show_active_communities: bool = True
    # Content
    country: str = "US"
    language: str = "en"
    auto_play_media: bool = True
    reduce_animations: bool = False


# ---------------------------------------------------------------------------
# Main state container
# ---------------------------------------------------------------------------

class RedditState(BaseEnvState):
    DIFF_DIFFABLE_SINGLETONS: ClassVar[tuple[str, ...]] = ("settings",)

    owner_username: str
    owner_display_name: str
    owner_avatar_url: str = ""
    owner_post_karma: int = 0
    owner_comment_karma: int = 0
    owner_cake_day: datetime | None = None
    owner_about: str = ""

    subreddits: list[Subreddit] = Field(default_factory=list)
    posts: list[Post] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    sent_messages: list[Message] = Field(default_factory=list)
    notifications: list[Notification] = Field(default_factory=list)
    user_profiles: list[UserProfile] = Field(default_factory=list)

    subscriptions: list[str] = Field(default_factory=list)  # subreddit_ids
    saved_post_ids: list[str] = Field(default_factory=list)
    saved_comment_ids: list[str] = Field(default_factory=list)
    hidden_post_ids: list[str] = Field(default_factory=list)
    blocked_users: list[str] = Field(default_factory=list)

    settings: RedditSettings = Field(default_factory=lambda: RedditSettings(id="settings_reddit"))

    id_counters: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def _next_id(self, prefix: str) -> str:
        count = self.id_counters.get(prefix, 0) + 1
        self.id_counters[prefix] = count
        return f"{prefix}_{count}"

    # ------------------------------------------------------------------
    # Subreddits
    # ------------------------------------------------------------------

    def get_subreddit(self, subreddit_id: str) -> Subreddit | None:
        return next((s for s in self.subreddits if s.id == subreddit_id), None)

    def get_subreddit_by_name(self, name: str) -> Subreddit | None:
        return next(
            (s for s in self.subreddits if s.name.lower() == name.lower()),
            None,
        )

    def subscribe(self, subreddit_id: str) -> Subreddit:
        sub = self.get_subreddit(subreddit_id)
        if sub is None:
            raise KeyError(f"Unknown subreddit id: {subreddit_id}")
        if subreddit_id not in self.subscriptions:
            self.subscriptions.append(subreddit_id)
            sub.is_subscribed = True
            sub.subscriber_count += 1
        self.touch()
        return sub

    def unsubscribe(self, subreddit_id: str) -> Subreddit:
        sub = self.get_subreddit(subreddit_id)
        if sub is None:
            raise KeyError(f"Unknown subreddit id: {subreddit_id}")
        if subreddit_id in self.subscriptions:
            self.subscriptions.remove(subreddit_id)
            sub.is_subscribed = False
            sub.subscriber_count = max(0, sub.subscriber_count - 1)
        self.touch()
        return sub

    def list_subscribed_subreddits(self) -> list[Subreddit]:
        return [s for s in self.subreddits if s.id in self.subscriptions]

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    def get_post(self, post_id: str) -> Post | None:
        return next((p for p in self.posts if p.id == post_id), None)

    @staticmethod
    def _hot_score(post: Post) -> float:
        """Reddit-inspired hot ranking: log(score) + recency bias."""
        score = max(post.score, 1)
        order = math.log10(score)
        epoch = post.created_at.timestamp()
        return order + epoch / 45000

    def list_posts(
        self,
        subreddit_name: str | None = None,
        sort: str = "hot",
        time_filter: str = "all",
    ) -> list[Post]:
        items = [p for p in self.posts if not p.is_removed and not p.is_hidden]
        if subreddit_name:
            items = [p for p in items if p.subreddit_name.lower() == subreddit_name.lower()]

        if sort == "new":
            items.sort(key=lambda p: p.created_at, reverse=True)
        elif sort == "top":
            items = self._filter_by_time(items, time_filter)
            items.sort(key=lambda p: p.score, reverse=True)
        elif sort == "rising":
            items.sort(key=lambda p: (p.upvote_ratio, p.created_at), reverse=True)
        elif sort == "controversial":
            items.sort(key=lambda p: (abs(p.upvote_ratio - 0.5), p.comment_count), reverse=False)
        else:  # hot (default)
            items.sort(key=lambda p: (p.is_pinned, self._hot_score(p)), reverse=True)

        return items

    def feed_posts(self, sort: str = "hot", time_filter: str = "all") -> list[Post]:
        subscribed_names = {s.name.lower() for s in self.list_subscribed_subreddits()}
        items = [
            p for p in self.posts
            if not p.is_removed and not p.is_hidden and p.subreddit_name.lower() in subscribed_names
        ]
        if sort == "new":
            items.sort(key=lambda p: p.created_at, reverse=True)
        elif sort == "top":
            items = self._filter_by_time(items, time_filter)
            items.sort(key=lambda p: p.score, reverse=True)
        elif sort == "rising":
            items.sort(key=lambda p: (p.upvote_ratio, p.created_at), reverse=True)
        else:  # hot (default)
            items.sort(key=lambda p: self._hot_score(p), reverse=True)
        return items

    def create_post(
        self,
        *,
        subreddit_name: str,
        title: str,
        body: str = "",
        url: str = "",
        post_type: str = "text",
        flair_text: str | None = None,
        is_spoiler: bool = False,
        is_nsfw: bool = False,
    ) -> Post:
        sub = self.get_subreddit_by_name(subreddit_name)
        if sub is None:
            raise KeyError(f"Unknown subreddit: {subreddit_name}")
        post = Post(
            id=self._next_id("post"),
            subreddit_id=sub.id,
            subreddit_name=sub.name,
            author_name=self.owner_username,
            title=title,
            body=body,
            url=url,
            post_type=post_type,
            score=1,
            upvote_ratio=1.0,
            created_at=datetime.now(timezone.utc),
            flair_text=flair_text,
            is_spoiler=is_spoiler,
            is_nsfw=is_nsfw,
            vote_direction=1,
            permalink=f"/r/{sub.name}/comments/{self.id_counters.get('post', 1)}",
        )
        self.posts.append(post)
        self.owner_post_karma += 1
        self.touch()
        return post

    def vote_post(self, post_id: str, direction: int) -> Post:
        post = self._require_post(post_id)
        if direction not in (-1, 0, 1):
            raise ValueError(f"Invalid vote direction: {direction}")
        old = post.vote_direction
        post.score += direction - old
        post.vote_direction = direction
        if post.score > 0:
            post.upvote_ratio = min(1.0, 0.5 + (direction - old) * 0.01)
        self.touch()
        return post

    def save_post(self, post_id: str) -> Post:
        post = self._require_post(post_id)
        if post_id not in self.saved_post_ids:
            self.saved_post_ids.append(post_id)
        post.is_saved = True
        self.touch()
        return post

    def unsave_post(self, post_id: str) -> Post:
        post = self._require_post(post_id)
        if post_id in self.saved_post_ids:
            self.saved_post_ids.remove(post_id)
        post.is_saved = False
        self.touch()
        return post

    def hide_post(self, post_id: str) -> Post:
        post = self._require_post(post_id)
        if post_id not in self.hidden_post_ids:
            self.hidden_post_ids.append(post_id)
        post.is_hidden = True
        self.touch()
        return post

    def unhide_post(self, post_id: str) -> Post:
        post = self._require_post(post_id)
        if post_id in self.hidden_post_ids:
            self.hidden_post_ids.remove(post_id)
        post.is_hidden = False
        self.touch()
        return post

    def delete_post(self, post_id: str) -> Post:
        post = self._require_post(post_id)
        if post.author_name != self.owner_username:
            raise ValueError("Cannot delete another user's post")
        post.is_removed = True
        post.body = "[deleted]"
        self.touch()
        return post

    def edit_post(self, post_id: str, body: str) -> Post:
        post = self._require_post(post_id)
        if post.author_name != self.owner_username:
            raise ValueError("Cannot edit another user's post")
        post.body = body
        post.is_edited = True
        self.touch()
        return post

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def get_comment(self, comment_id: str) -> Comment | None:
        return next((c for c in self.comments if c.id == comment_id), None)

    def get_post_comments(
        self, post_id: str, sort: str = "best"
    ) -> list[Comment]:
        items = [c for c in self.comments if c.post_id == post_id and not c.is_removed]
        if sort == "new":
            items.sort(key=lambda c: c.created_at, reverse=True)
        elif sort == "old":
            items.sort(key=lambda c: c.created_at)
        elif sort == "controversial":
            items.sort(key=lambda c: abs(c.score))
        elif sort == "top":
            items.sort(key=lambda c: c.score, reverse=True)
        else:  # best
            items.sort(key=lambda c: (c.score, c.created_at), reverse=True)
        return items

    def add_comment(
        self,
        *,
        post_id: str,
        body: str,
        parent_id: str | None = None,
    ) -> Comment:
        post = self._require_post(post_id)
        depth = 0
        if parent_id:
            parent = self.get_comment(parent_id)
            if parent is None:
                raise KeyError(f"Unknown parent comment id: {parent_id}")
            depth = parent.depth + 1
        comment = Comment(
            id=self._next_id("comment"),
            post_id=post_id,
            parent_id=parent_id,
            author_name=self.owner_username,
            body=body,
            score=1,
            created_at=datetime.now(timezone.utc),
            is_submitter=post.author_name == self.owner_username,
            vote_direction=1,
            depth=depth,
        )
        self.comments.append(comment)
        post.comment_count += 1
        self.owner_comment_karma += 1
        self.touch()
        return comment

    def vote_comment(self, comment_id: str, direction: int) -> Comment:
        comment = self._require_comment(comment_id)
        if direction not in (-1, 0, 1):
            raise ValueError(f"Invalid vote direction: {direction}")
        old = comment.vote_direction
        comment.score += direction - old
        comment.vote_direction = direction
        self.touch()
        return comment

    def edit_comment(self, comment_id: str, body: str) -> Comment:
        comment = self._require_comment(comment_id)
        if comment.author_name != self.owner_username:
            raise ValueError("Cannot edit another user's comment")
        if comment.is_removed:
            raise ValueError("Cannot edit a deleted comment")
        comment.body = body
        comment.is_edited = True
        comment.edited_at = datetime.now(timezone.utc)
        self.touch()
        return comment

    def delete_comment(self, comment_id: str) -> Comment:
        comment = self._require_comment(comment_id)
        if comment.author_name != self.owner_username:
            raise ValueError("Cannot delete another user's comment")
        comment.is_removed = True
        comment.body = "[deleted]"
        self.touch()
        return comment

    def save_comment(self, comment_id: str) -> Comment:
        comment = self._require_comment(comment_id)
        if comment_id not in self.saved_comment_ids:
            self.saved_comment_ids.append(comment_id)
        comment.is_saved = True
        self.touch()
        return comment

    def unsave_comment(self, comment_id: str) -> Comment:
        comment = self._require_comment(comment_id)
        if comment_id in self.saved_comment_ids:
            self.saved_comment_ids.remove(comment_id)
        comment.is_saved = False
        self.touch()
        return comment

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def get_message(self, message_id: str) -> Message | None:
        for msg in self.messages + self.sent_messages:
            if msg.id == message_id:
                return msg
        return None

    def send_message(
        self,
        *,
        to_user: str,
        subject: str,
        body: str,
        parent_id: str | None = None,
    ) -> Message:
        msg = Message(
            id=self._next_id("msg"),
            from_user=self.owner_username,
            to_user=to_user,
            subject=subject,
            body=body,
            created_at=datetime.now(timezone.utc),
            is_read=True,
            parent_id=parent_id,
        )
        self.sent_messages.append(msg)
        self.touch()
        return msg

    def mark_message_read(self, message_id: str) -> Message:
        msg = self.get_message(message_id)
        if msg is None:
            raise KeyError(f"Unknown message id: {message_id}")
        msg.is_read = True
        self.touch()
        return msg

    def mark_all_messages_read(self) -> int:
        count = 0
        for msg in self.messages:
            if not msg.is_read:
                msg.is_read = True
                count += 1
        if count:
            self.touch()
        return count

    def delete_message(self, message_id: str) -> Message:
        for collection in (self.messages, self.sent_messages):
            for index, msg in enumerate(collection):
                if msg.id == message_id:
                    removed = collection.pop(index)
                    self.touch()
                    return removed
        raise KeyError(f"Unknown message id: {message_id}")

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def mark_notification_read(self, notification_id: str) -> Notification:
        notif = next((n for n in self.notifications if n.id == notification_id), None)
        if notif is None:
            raise KeyError(f"Unknown notification id: {notification_id}")
        notif.is_read = True
        self.touch()
        return notif

    def mark_all_notifications_read(self) -> int:
        count = 0
        for n in self.notifications:
            if not n.is_read:
                n.is_read = True
                count += 1
        if count:
            self.touch()
        return count

    def unread_notification_count(self) -> int:
        return sum(1 for n in self.notifications if not n.is_read)

    def unread_message_count(self) -> int:
        return sum(1 for m in self.messages if not m.is_read)

    # ------------------------------------------------------------------
    # User profiles
    # ------------------------------------------------------------------

    def get_user_profile(self, username: str) -> UserProfile | None:
        return next(
            (u for u in self.user_profiles if u.username.lower() == username.lower()),
            None,
        )

    def block_user(self, username: str) -> None:
        if username not in self.blocked_users:
            self.blocked_users.append(username)
            self.touch()

    def unblock_user(self, username: str) -> None:
        if username in self.blocked_users:
            self.blocked_users.remove(username)
            self.touch()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_posts(self, query: str, subreddit_name: str | None = None, sort: str = "relevance") -> list[Post]:
        tokens = _reddit_query_tokens(query)
        items = [p for p in self.posts if not p.is_removed and not p.is_hidden]
        if subreddit_name:
            items = [p for p in items if p.subreddit_name.lower() == subreddit_name.lower()]

        if tokens:
            results = []
            for p in items:
                haystack = f"{p.title} {p.body} {p.subreddit_name} {p.author_name}".lower()
                if all(tok in haystack for tok in tokens):
                    results.append(p)
            items = results

        if sort == "new":
            items.sort(key=lambda p: p.created_at, reverse=True)
        elif sort == "top":
            items.sort(key=lambda p: p.score, reverse=True)
        elif sort == "comments":
            items.sort(key=lambda p: p.comment_count, reverse=True)
        # relevance keeps token-match order

        return items

    def search_subreddits(self, query: str) -> list[Subreddit]:
        tokens = _reddit_query_tokens(query)
        if not tokens:
            return list(self.subreddits)
        results = []
        for s in self.subreddits:
            haystack = f"{s.name} {s.display_name} {s.description}".lower()
            if all(tok in haystack for tok in tokens):
                results.append(s)
        results.sort(key=lambda s: s.subscriber_count, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def update_settings(self, **kwargs: Any) -> RedditSettings:
        for key, value in kwargs.items():
            if not hasattr(self.settings, key):
                raise ValueError(f"Invalid settings field: {key}")
            setattr(self.settings, key, value)
        self.touch()
        return self.settings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_post(self, post_id: str) -> Post:
        post = self.get_post(post_id)
        if post is None:
            raise KeyError(f"Unknown post id: {post_id}")
        return post

    def _require_comment(self, comment_id: str) -> Comment:
        comment = self.get_comment(comment_id)
        if comment is None:
            raise KeyError(f"Unknown comment id: {comment_id}")
        return comment

    @staticmethod
    def _filter_by_time(posts: list[Post], time_filter: str) -> list[Post]:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        cutoffs = {
            "hour": timedelta(hours=1),
            "day": timedelta(days=1),
            "week": timedelta(weeks=1),
            "month": timedelta(days=30),
            "year": timedelta(days=365),
        }
        delta = cutoffs.get(time_filter)
        if delta:
            cutoff = now - delta
            return [p for p in posts if p.created_at >= cutoff]
        return posts  # "all"

    # ------------------------------------------------------------------
    # Snapshots & summaries
    # ------------------------------------------------------------------

    def state_snapshot(self) -> dict[str, Any]:
        post_snap: dict[str, dict[str, Any]] = {}
        for p in self.posts:
            post_snap[p.id] = {
                "title": p.title,
                "score": p.score,
                "vote_direction": p.vote_direction,
                "is_saved": p.is_saved,
                "is_hidden": p.is_hidden,
                "is_removed": p.is_removed,
                "comment_count": p.comment_count,
                "flair_text": p.flair_text,
            }

        comment_snap: dict[str, dict[str, Any]] = {}
        for c in self.comments:
            comment_snap[c.id] = {
                "body": c.body[:100],
                "score": c.score,
                "vote_direction": c.vote_direction,
                "is_saved": c.is_saved,
                "is_removed": c.is_removed,
            }

        subreddit_snap: dict[str, dict[str, Any]] = {}
        for s in self.subreddits:
            subreddit_snap[s.id] = {
                "name": s.name,
                "subscriber_count": s.subscriber_count,
                "is_subscribed": s.is_subscribed,
            }

        message_snap: dict[str, dict[str, Any]] = {}
        for m in self.messages:
            message_snap[m.id] = {
                "from_user": m.from_user,
                "subject": m.subject,
                "is_read": m.is_read,
            }

        notification_snap: dict[str, dict[str, Any]] = {}
        for n in self.notifications:
            notification_snap[n.id] = {
                "type": n.type,
                "is_read": n.is_read,
            }

        settings = self.settings.model_dump(mode="json")
        settings.pop("id", None)

        return {
            "post_ids": sorted(post_snap.keys()),
            "posts": post_snap,
            "comment_ids": sorted(comment_snap.keys()),
            "comments": comment_snap,
            "subreddits": subreddit_snap,
            "subscriptions": sorted(self.subscriptions),
            "saved_post_ids": sorted(self.saved_post_ids),
            "saved_comment_ids": sorted(self.saved_comment_ids),
            "hidden_post_ids": sorted(self.hidden_post_ids),
            "blocked_users": sorted(self.blocked_users),
            "messages": message_snap,
            "sent_message_count": len(self.sent_messages),
            "notifications": notification_snap,
            "owner_post_karma": self.owner_post_karma,
            "owner_comment_karma": self.owner_comment_karma,
            "settings": settings,
        }

    def compute_collateral(self, initial: dict[str, Any]) -> dict[str, Any]:
        """Diff initial snapshot against current state for collateral-damage detection."""
        current = self.state_snapshot()
        report: dict[str, Any] = {}

        # Posts modified
        added, removed, modified = diff_dict_of_dicts(
            initial.get("posts", {}), current.get("posts", {}), "post_id"
        )
        if added:
            report["posts_added"] = added
        if removed:
            report["posts_removed"] = removed
        if modified:
            report["posts_modified"] = modified

        # Comments modified
        added, removed, modified = diff_dict_of_dicts(
            initial.get("comments", {}), current.get("comments", {}), "comment_id"
        )
        if added:
            report["comments_added"] = added
        if removed:
            report["comments_removed"] = removed
        if modified:
            report["comments_modified"] = modified

        # Subreddit changes
        added, removed, modified = diff_dict_of_dicts(
            initial.get("subreddits", {}), current.get("subreddits", {}), "subreddit_id"
        )
        if modified:
            report["subreddits_modified"] = modified

        # Subscription changes
        init_subs = set(initial.get("subscriptions", []))
        curr_subs = set(current.get("subscriptions", []))
        newly_subscribed = sorted(curr_subs - init_subs)
        newly_unsubscribed = sorted(init_subs - curr_subs)
        if newly_subscribed:
            report["subscribed"] = newly_subscribed
        if newly_unsubscribed:
            report["unsubscribed"] = newly_unsubscribed

        # Saved changes
        init_saved = set(initial.get("saved_post_ids", []))
        curr_saved = set(current.get("saved_post_ids", []))
        if curr_saved - init_saved:
            report["posts_saved"] = sorted(curr_saved - init_saved)
        if init_saved - curr_saved:
            report["posts_unsaved"] = sorted(init_saved - curr_saved)

        # Messages
        sent_delta = current.get("sent_message_count", 0) - initial.get("sent_message_count", 0)
        if sent_delta > 0:
            report["messages_sent"] = sent_delta

        # Message read state
        added_msgs, removed_msgs, modified_msgs = diff_dict_of_dicts(
            initial.get("messages", {}), current.get("messages", {}), "message_id"
        )
        if modified_msgs:
            report["messages_modified"] = modified_msgs

        # Settings
        if initial.get("settings") != current.get("settings"):
            init_settings = initial.get("settings", {})
            curr_settings = current.get("settings", {})
            changes = {
                k: {"before": init_settings.get(k), "after": curr_settings.get(k)}
                for k in set(init_settings) | set(curr_settings)
                if init_settings.get(k) != curr_settings.get(k)
            }
            if changes:
                report["settings_changed"] = changes

        # Karma
        if initial.get("owner_post_karma") != current.get("owner_post_karma"):
            report["post_karma_delta"] = current.get("owner_post_karma", 0) - initial.get("owner_post_karma", 0)
        if initial.get("owner_comment_karma") != current.get("owner_comment_karma"):
            report["comment_karma_delta"] = current.get("owner_comment_karma", 0) - initial.get("owner_comment_karma", 0)

        return report

    def session_summary(self) -> dict[str, Any]:
        return {
            "env_id": self.env_id,
            "task_id": self.task_id,
            "owner_username": self.owner_username,
            "owner_display_name": self.owner_display_name,
            "counts": {
                "subreddits": len(self.subreddits),
                "subscriptions": len(self.subscriptions),
                "posts": len(self.posts),
                "comments": len(self.comments),
                "messages": len(self.messages),
                "sent_messages": len(self.sent_messages),
                "notifications": len(self.notifications),
                "saved_posts": len(self.saved_post_ids),
                "saved_comments": len(self.saved_comment_ids),
                "hidden_posts": len(self.hidden_post_ids),
                "blocked_users": len(self.blocked_users),
                "unread_messages": self.unread_message_count(),
                "unread_notifications": self.unread_notification_count(),
                "post_karma": self.owner_post_karma,
                "comment_karma": self.owner_comment_karma,
            },
        }
