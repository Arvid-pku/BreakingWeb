"""Composable seed builder framework for the Reddit environment.

Provides :class:`RedditSeedContext` (the mutable accumulator threaded through
every builder step) and a registry of reusable builder functions that generate
deterministic test data for Reddit benchmark tasks.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from breakingweb.backend.models.reddit import (
    Award,
    Comment,
    Flair,
    Message,
    Notification,
    Post,
    Subreddit,
    SubredditRule,
    UserProfile,
)


# ---------------------------------------------------------------------------
# RedditSeedContext
# ---------------------------------------------------------------------------

class RedditSeedContext:
    """Mutable accumulator threaded through every seed builder step."""

    def __init__(
        self,
        seed: int,
        rng: random.Random,
        fake: Any,
        now: datetime,
        base: dict[str, Any],
    ) -> None:
        self.seed = seed
        self.rng = rng
        self.fake = fake
        self.now = now
        self.base = base
        self.actors: dict[str, Any] = {}
        self.outputs: dict[str, Any] = {}
        self.counters: dict[str, int] = {}

        self.owner_username: str = base.get("owner_username", "TechNomad_42")

    def next_id(self, prefix: str) -> str:
        self.counters[prefix] = self.counters.get(prefix, 0) + 1
        return f"{prefix}_{self.counters[prefix]}"

    def resolve_actor(
        self,
        key: str,
        domain: str = "example.com",
        is_vip: bool = False,
        name: str | None = None,
    ) -> dict[str, str]:
        if key in self.actors:
            return self.actors[key]
        name = name or self.fake.name()
        username = name.replace(" ", "_").lower() + str(self.rng.randint(10, 999))
        actor = {"name": name, "username": username}
        self.actors[key] = actor
        return actor

    def random_username(self) -> str:
        """Return a random username from existing user profiles."""
        profiles = self.base.get("user_profiles", [])
        if profiles:
            return self.rng.choice(profiles).username
        return f"user_{self.rng.randint(1000, 9999)}"

    # -- Model factories ---------------------------------------------------

    def ensure_subreddit(
        self,
        name: str,
        *,
        description: str | None = None,
        is_subscribed: bool = False,
    ) -> Subreddit:
        """Return the existing subreddit by name or create+register a new one.

        Tasks that reference niche subreddits (e.g. r/datascience, r/photography,
        r/learnpython) don't always exist in the base seed pool. Creating one on
        first reference keeps the environment usable and lets agents navigate
        to /r/<name>, subscribe, and create posts without hitting 404s.
        """
        existing = next(
            (s for s in self.base["subreddits"] if s.name.lower() == name.lower()),
            None,
        )
        if existing is not None:
            return existing
        sub = Subreddit(
            id=self.next_id("sub"),
            name=name,
            display_name=name,
            description=description or f"Community discussion in r/{name}.",
            public_description=(description or f"r/{name} community discussion.")[:100],
            subscriber_count=self.rng.randint(1_000, 500_000),
            active_users=self.rng.randint(50, 5_000),
            created_at=self.now - timedelta(days=self.rng.randint(365, 365 * 10)),
            is_subscribed=is_subscribed,
            rules=[
                SubredditRule(title="Be respectful", description="Treat others with respect.", rule_type="both"),
                SubredditRule(title="No spam", description="Do not post spam.", rule_type="post"),
            ],
            flairs=[
                Flair(id=f"flair_auto_{name}_{j}", text=t, background_color=c)
                for j, (t, c) in enumerate([
                    ("Discussion", "#0079d3"),
                    ("Question", "#46d160"),
                ])
            ],
        )
        self.base["subreddits"].append(sub)
        return sub

    def post(
        self,
        *,
        subreddit_name: str,
        author_name: str | None = None,
        title: str,
        body: str = "",
        url: str = "",
        post_type: str = "text",
        score: int | None = None,
        created_at: datetime | None = None,
        flair_text: str | None = None,
        is_pinned: bool = False,
        is_locked: bool = False,
        comment_count: int = 0,
        awards: list[Award] | None = None,
    ) -> Post:
        sub = self.ensure_subreddit(subreddit_name)
        subreddit_id = sub.id
        author = author_name or self.random_username()
        post_score = score if score is not None else self.rng.randint(10, 50000)
        ts = created_at or (self.now - timedelta(hours=self.rng.randint(1, 336)))
        post = Post(
            id=self.next_id("post"),
            subreddit_id=subreddit_id,
            subreddit_name=subreddit_name,
            author_name=author,
            title=title,
            body=body,
            url=url,
            post_type=post_type,
            score=post_score,
            upvote_ratio=round(self.rng.uniform(0.6, 0.99), 2),
            comment_count=comment_count,
            created_at=ts,
            flair_text=flair_text,
            is_pinned=is_pinned,
            is_locked=is_locked,
            awards=awards or [],
            permalink=f"/r/{subreddit_name}/comments/{self.counters.get('post', 1)}",
        )
        self.base["posts"].append(post)
        return post

    def comment(
        self,
        *,
        post_id: str,
        author_name: str | None = None,
        body: str,
        parent_id: str | None = None,
        score: int | None = None,
        created_at: datetime | None = None,
        depth: int = 0,
        is_submitter: bool = False,
    ) -> Comment:
        author = author_name or self.random_username()
        c = Comment(
            id=self.next_id("comment"),
            post_id=post_id,
            parent_id=parent_id,
            author_name=author,
            body=body,
            score=score if score is not None else self.rng.randint(-5, 3000),
            created_at=created_at or (self.now - timedelta(hours=self.rng.randint(1, 168))),
            depth=depth,
            is_submitter=is_submitter,
        )
        self.base["comments"].append(c)
        # Keep the parent post's comment_count in sync so the feed card and
        # detail view agree with state.comments. Without this, target_post +
        # target_comment combos show "0 comments" even though the detail
        # page renders the thread correctly.
        parent_post = next(
            (p for p in self.base.get("posts", []) if p.id == post_id),
            None,
        )
        if parent_post is not None:
            parent_post.comment_count = getattr(parent_post, "comment_count", 0) + 1
        return c

    def message(
        self,
        *,
        from_user: str,
        to_user: str | None = None,
        subject: str,
        body: str,
        is_read: bool = False,
        created_at: datetime | None = None,
    ) -> Message:
        msg = Message(
            id=self.next_id("msg"),
            from_user=from_user,
            to_user=to_user or self.owner_username,
            subject=subject,
            body=body,
            created_at=created_at or (self.now - timedelta(hours=self.rng.randint(1, 72))),
            is_read=is_read,
        )
        self.base["messages"].append(msg)
        return msg

    def notification(
        self,
        *,
        type: str,
        title: str,
        body: str,
        is_read: bool = False,
        related_post_id: str | None = None,
        related_comment_id: str | None = None,
        subreddit_name: str | None = None,
        from_user: str | None = None,
        created_at: datetime | None = None,
    ) -> Notification:
        notif = Notification(
            id=self.next_id("notif"),
            type=type,
            title=title,
            body=body,
            created_at=created_at or (self.now - timedelta(hours=self.rng.randint(1, 48))),
            is_read=is_read,
            related_post_id=related_post_id,
            related_comment_id=related_comment_id,
            subreddit_name=subreddit_name,
            from_user=from_user,
        )
        self.base["notifications"].append(notif)
        return notif


# ---------------------------------------------------------------------------
# Builder registry
# ---------------------------------------------------------------------------

BuilderFn = Callable[[RedditSeedContext, dict[str, Any]], dict[str, Any]]

REDDIT_BUILDER_REGISTRY: dict[str, BuilderFn] = {}


def _register(name: str) -> Callable[[BuilderFn], BuilderFn]:
    def decorator(fn: BuilderFn) -> BuilderFn:
        REDDIT_BUILDER_REGISTRY[name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Core builders
# ---------------------------------------------------------------------------

@_register("target_post")
def build_target_post(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a specific post that the task targets.

    Params: subreddit, title, body, author (optional), post_type, score,
            flair_text, is_pinned, is_locked
    """
    post = ctx.post(
        subreddit_name=params["subreddit"],
        title=params["title"],
        body=params.get("body", ""),
        author_name=params.get("author"),
        post_type=params.get("post_type", "text"),
        score=params.get("score"),
        flair_text=params.get("flair_text"),
        is_pinned=params.get("is_pinned", False),
        is_locked=params.get("is_locked", False),
    )
    return {"post_id": post.id, "post_title": post.title, "subreddit_name": post.subreddit_name}


@_register("target_comment")
def build_target_comment(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a specific comment on a post.

    Params: post_id, body, author (optional), parent_id, score
    """
    comment = ctx.comment(
        post_id=params["post_id"],
        body=params["body"],
        author_name=params.get("author"),
        parent_id=params.get("parent_id"),
        score=params.get("score"),
    )
    return {"comment_id": comment.id, "comment_body": comment.body}


@_register("decoy_posts")
def build_decoy_posts(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create decoy posts with similar attributes to confuse shallow heuristics.

    Params: subreddit, count, title_pattern (optional), score_range
    """
    subreddit = params["subreddit"]
    count = params.get("count", 3)
    title_pattern = params.get("title_pattern", "Discussion about {topic}")
    topics = ["updates", "changes", "new features", "community feedback", "policy review"]
    score_lo, score_hi = params.get("score_range", [50, 5000])

    post_ids = []
    for i in range(count):
        title = title_pattern.replace("{topic}", ctx.rng.choice(topics))
        post = ctx.post(
            subreddit_name=subreddit,
            title=f"{title} #{i + 1}",
            body=f"This is a discussion thread about {ctx.rng.choice(topics)}.",
            score=ctx.rng.randint(score_lo, score_hi),
        )
        post_ids.append(post.id)
    return {"decoy_post_ids": post_ids}


@_register("target_message")
def build_target_message(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a specific inbox message.

    Params: from_user, subject, body, is_read
    """
    msg = ctx.message(
        from_user=params["from_user"],
        subject=params["subject"],
        body=params["body"],
        is_read=params.get("is_read", False),
    )
    return {"message_id": msg.id, "message_subject": msg.subject, "from_user": msg.from_user}


@_register("decoy_messages")
def build_decoy_messages(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create decoy messages with similar subjects.

    Params: count, subject_pattern, from_users (optional)
    """
    count = params.get("count", 3)
    subject_pattern = params.get("subject_pattern", "Re: {topic}")
    topics = ["project update", "meeting notes", "feedback", "question", "invitation"]

    msg_ids = []
    for _ in range(count):
        subject = subject_pattern.replace("{topic}", ctx.rng.choice(topics))
        msg = ctx.message(
            from_user=ctx.random_username(),
            subject=subject,
            body=f"Message body about {ctx.rng.choice(topics)}.",
            is_read=ctx.rng.random() < 0.5,
        )
        msg_ids.append(msg.id)
    return {"decoy_message_ids": msg_ids}


@_register("comment_thread")
def build_comment_thread(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a thread of comments on a post.

    Params: post_id, depth, comments_per_level, bodies (optional list)
    """
    post_id = params["post_id"]
    depth = params.get("depth", 3)
    per_level = params.get("comments_per_level", 2)
    bodies = params.get("bodies", [])

    all_ids = []
    parent_ids: list[str | None] = [None]

    for d in range(depth):
        next_parents = []
        for parent_id in parent_ids:
            for j in range(per_level):
                body_idx = d * per_level + j
                body = bodies[body_idx] if body_idx < len(bodies) else f"Comment at depth {d}"
                c = ctx.comment(
                    post_id=post_id,
                    body=body,
                    parent_id=parent_id,
                    depth=d,
                )
                all_ids.append(c.id)
                next_parents.append(c.id)
        parent_ids = next_parents[:per_level]  # limit branching

    return {"comment_ids": all_ids, "thread_depth": depth}


@_register("target_notification")
def build_target_notification(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a specific notification.

    Params: type, title, body, is_read, related_post_id, subreddit_name, from_user
    """
    notif = ctx.notification(
        type=params["type"],
        title=params["title"],
        body=params["body"],
        is_read=params.get("is_read", False),
        related_post_id=params.get("related_post_id"),
        subreddit_name=params.get("subreddit_name"),
        from_user=params.get("from_user"),
    )
    return {"notification_id": notif.id}


@_register("owner_post")
def build_owner_post(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a post authored by the session owner.

    Params: subreddit, title, body, score, flair_text
    """
    post = ctx.post(
        subreddit_name=params["subreddit"],
        author_name=ctx.owner_username,
        title=params["title"],
        body=params.get("body", ""),
        score=params.get("score", ctx.rng.randint(100, 10000)),
        flair_text=params.get("flair_text"),
    )
    return {"post_id": post.id, "post_title": post.title}


@_register("owner_comment")
def build_owner_comment(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a comment authored by the session owner.

    Params: post_id, body, parent_id, score
    """
    comment = ctx.comment(
        post_id=params["post_id"],
        author_name=ctx.owner_username,
        body=params["body"],
        parent_id=params.get("parent_id"),
        score=params.get("score", ctx.rng.randint(1, 500)),
    )
    return {"comment_id": comment.id}


@_register("subscription_state")
def build_subscription_state(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Ensure specific subreddits are subscribed/unsubscribed.

    Params: subscribe (list of subreddit names), unsubscribe (list)
    """
    for name in params.get("subscribe", []):
        sub = next((s for s in ctx.base["subreddits"] if s.name.lower() == name.lower()), None)
        if sub and sub.id not in ctx.base["subscriptions"]:
            ctx.base["subscriptions"].append(sub.id)
            sub.is_subscribed = True
    for name in params.get("unsubscribe", []):
        sub = next((s for s in ctx.base["subreddits"] if s.name.lower() == name.lower()), None)
        if sub and sub.id in ctx.base["subscriptions"]:
            ctx.base["subscriptions"].remove(sub.id)
            sub.is_subscribed = False
    return {"subscriptions": list(ctx.base["subscriptions"])}


@_register("saved_posts")
def build_saved_posts(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Mark specific posts as saved.

    Params: post_ids (list of post IDs)
    """
    for pid in params.get("post_ids", []):
        if pid not in ctx.base["saved_post_ids"]:
            ctx.base["saved_post_ids"].append(pid)
        post = next((p for p in ctx.base["posts"] if p.id == pid), None)
        if post:
            post.is_saved = True
    return {"saved_post_ids": list(ctx.base["saved_post_ids"])}


@_register("capture_notification_ids")
def build_capture_notification_ids(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Capture current notification IDs (typically used AFTER other seed steps).

    Returns ids of all currently-present notifications, plus the subset that
    are currently unread. Optional ``exclude`` param removes specific ids
    from the returned lists.

    Params: exclude (list[str], optional)
    """
    exclude = set(params.get("exclude", []))
    ids = [n.id for n in ctx.base["notifications"] if n.id not in exclude]
    unread_ids = [n.id for n in ctx.base["notifications"]
                  if not n.is_read and n.id not in exclude]
    return {"notification_ids": ids, "unread_notification_ids": unread_ids}


@_register("capture_message_ids")
def build_capture_message_ids(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Capture current inbox message IDs (typically used AFTER seed mutations).

    Returns ids of all currently-present inbox messages, plus the subset that
    are currently unread. Optional ``exclude`` param removes specific ids
    from the returned lists (useful when a subsequent task step will delete
    one of the captured messages).

    Params: exclude (list[str], optional)
    """
    exclude = set(params.get("exclude", []))
    ids = [m.id for m in ctx.base["messages"] if m.id not in exclude]
    unread_ids = [m.id for m in ctx.base["messages"]
                  if not m.is_read and m.id not in exclude]
    return {"message_ids": ids, "unread_message_ids": unread_ids}


@_register("filler_posts")
def build_filler_posts(ctx: RedditSeedContext, params: dict[str, Any]) -> dict[str, Any]:
    """Generate N filler posts in a subreddit.

    Params: subreddit, count, score_range, age_range_hours
    """
    subreddit = params["subreddit"]
    count = params.get("count", 5)
    score_lo, score_hi = params.get("score_range", [10, 5000])
    age_lo, age_hi = params.get("age_range_hours", [1, 336])

    filler_titles = [
        "What do you all think about this?",
        "Interesting perspective on the topic",
        "My experience with the community",
        "A question for the experts here",
        "Does anyone else feel this way?",
        "Sharing something I found interesting",
        "Weekly discussion thread",
        "PSA: Important information for everyone",
    ]

    post_ids = []
    for _ in range(count):
        post = ctx.post(
            subreddit_name=subreddit,
            title=ctx.rng.choice(filler_titles),
            body="Lorem ipsum discussion content.",
            score=ctx.rng.randint(score_lo, score_hi),
            created_at=ctx.now - timedelta(hours=ctx.rng.randint(age_lo, age_hi)),
        )
        post_ids.append(post.id)
    return {"filler_post_ids": post_ids}
