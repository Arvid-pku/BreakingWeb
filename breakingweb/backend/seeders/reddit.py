"""Composable seed runner for Reddit environment tasks.

Instead of a monolithic per-task method, this runner reads the ``seed:``
section from a :class:`TaskDefinition` YAML, resolves actors, executes
builder steps from :data:`REDDIT_BUILDER_REGISTRY`, adds distractors, and
evaluates target templates.
"""

from __future__ import annotations

import re
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from breakingweb.backend.models.reddit import (
    Award,
    Comment,
    Flair,
    Message,
    Notification,
    Post,
    RedditSettings,
    Subreddit,
    SubredditRule,
    UserProfile,
)
from breakingweb.backend.seeder import derive_anchor_time
from breakingweb.backend.seeders._common import _assign_output
from breakingweb.tasks._schema import TaskDefinition
from breakingweb.tasks._seed_builders_reddit import (
    REDDIT_BUILDER_REGISTRY,
    RedditSeedContext,
)


# ---------------------------------------------------------------------------
# Realistic data pools
# ---------------------------------------------------------------------------

# Real subreddit data from Reddit's public API (April 2026)
SUBREDDIT_DATA = [
    {"name": "AskReddit", "display": "Ask Reddit", "desc": "r/AskReddit is the place to ask and answer thought-provoking questions.", "subs": 58_147_162},
    {"name": "funny", "display": "Funny", "desc": "Reddit's largest humor depository.", "subs": 67_182_361},
    {"name": "gaming", "display": "Gaming", "desc": "The Number One Gaming forum on the Internet.", "subs": 47_044_213},
    {"name": "worldnews", "display": "World News", "desc": "A place for major news from around the world, excluding US-internal news.", "subs": 47_244_216},
    {"name": "todayilearned", "display": "Today I Learned", "desc": "You learn something new every day; what did you learn today?", "subs": 41_326_386},
    {"name": "movies", "display": "Movies", "desc": "/r/movies is the world's largest online film community, with over 37,000,000 members.", "subs": 37_310_221},
    {"name": "pics", "display": "Pics", "desc": "A place for photographs, pictures, and other images.", "subs": 33_354_441},
    {"name": "memes", "display": "Memes", "desc": "Memes! A way of describing cultural information being shared.", "subs": 35_734_284},
    {"name": "news", "display": "News", "desc": "The place for news articles about current events in the United States and the rest of the world.", "subs": 31_318_465},
    {"name": "technology", "display": "Technology", "desc": "Subreddit dedicated to the news and discussion of technology.", "subs": 16_035_378},
    {"name": "nottheonion", "display": "Not The Onion", "desc": "For true stories that you could have sworn were from The Onion.", "subs": 25_971_007},
    {"name": "AmItheAsshole", "display": "Am I the Asshole?", "desc": "A catharsis for the frustrated moral philosopher in all of us.", "subs": 24_284_960},
    {"name": "interestingasfuck", "display": "Interesting As Fuck", "desc": "For anything truly interesting as fuck.", "subs": 16_267_456},
    {"name": "Damnthatsinteresting", "display": "Damn That's Interesting", "desc": "For the most interesting things on the internet.", "subs": 20_249_048},
    {"name": "mildlyinfuriating", "display": "Mildly Infuriating", "desc": "For things that mildly infuriate you.", "subs": 11_951_150},
    {"name": "wallstreetbets", "display": "Wall Street Bets", "desc": "Like 4chan found a Bloomberg Terminal.", "subs": 19_900_068},
    {"name": "politics", "display": "Politics", "desc": "/r/Politics is for news and discussion about U.S. politics.", "subs": 9_110_999},
    {"name": "pcmasterrace", "display": "PC Master Race", "desc": "Welcome to the official subreddit of the PC Master Race / PCMR!", "subs": 16_035_378},
    {"name": "leagueoflegends", "display": "League of Legends", "desc": "This is a subreddit devoted to the game League of Legends.", "subs": 8_361_983},
    {"name": "NoStupidQuestions", "display": "No Stupid Questions", "desc": "Ask away! Disclaimer: This is an anonymous forum so answers may not be correct.", "subs": 7_072_643},
    {"name": "Piracy", "display": "Piracy", "desc": "Dedicated to the discussion of digital piracy, including ethical problems and legal advancements.", "subs": 2_739_536},
    {"name": "personalfinance", "display": "Personal Finance", "desc": "Learn about budgeting, saving, getting out of debt, and more.", "subs": 17_000_000},
    {"name": "programming", "display": "Programming", "desc": "Computer programming news, articles, and discussion.", "subs": 5_800_000},
    {"name": "Python", "display": "Python", "desc": "News about the programming language Python.", "subs": 1_400_000},
    {"name": "MachineLearning", "display": "Machine Learning", "desc": "Discussion of machine learning and related topics.", "subs": 2_800_000},
    {"name": "dataisbeautiful", "display": "Data Is Beautiful", "desc": "A place for visual representations of data: graphs, charts, maps, etc.", "subs": 22_154_981},
    {"name": "science", "display": "Science", "desc": "A community for sharing and discussing science news, research, and discoveries.", "subs": 34_186_770},
]

# Real post titles from Reddit's public API (April 2026)
POST_TITLES = {
    "AskReddit": [
        "What's a fact that sounds made up but is actually true?",
        "What's the most underrated website on the internet?",
        "People who work in IT, what's the dumbest thing you've seen a user do?",
        "What's a small thing someone did that permanently changed your opinion of them?",
        "What is something that is considered normal today but would be horrifying 50 years ago?",
        "What are some green flags in friendships?",
        "What product or service is a complete rip-off that most people don't realize?",
        "If you could know the absolute truth to one question, what would you ask?",
    ],
    "technology": [
        "Honda President After Visiting Chinese Auto Supplier: 'We Have No Chance Against This'",
        "Sam Altman Says It'll Take Another Year Before ChatGPT Can Start a Timer",
        "Oracle Appoints Hilary Maxson As CFO With $29.7 Million Package After Firing 30,000 Employees",
        "Scientists Engineer 'Tumor-Eating' Bacteria That Devour Cancer From Within",
        "Data Centers Are Military Targets Now",
        "This New Electric Car Nearly Fills Its Battery In Under 9 Minutes",
        "Sam Altman says AI superintelligence is so big that we need a 'New Deal'",
        "Sony Pictures Entertainment to Lay Off Hundreds in Massive Reorganization",
        "Amazon, Microsoft, and Google under investor pressure to disclose data center water and power consumption",
        "Anthropic's latest AI model identifies 'thousands of zero-day vulnerabilities'",
        "Testing suggests Google's AI Overviews tell millions of lies per hour",
        "NIH Scientists Discover Powerful New Opioid That Relieves Pain Without Dangerous Side Effects",
        "Target puts customers on the hook for AI shopping assistant errors",
    ],
    "gaming": [
        "As an older gamer, seeing young kids waste their money on in-game purchases eats at my soul",
        "Quantic Dream's Star Wars Eclipse Is Reportedly Still 'Years Off'",
        "Games I Recognize as Masterpieces But Can't Finish",
        "How is there no modern version of Rockband?",
        "There needs to be more games about playing as giant monsters/Kaiju",
        "Nvidia's DLSS 5 video gets blocked after false copyright claim from Italian broadcaster",
        "Best Final Mission in Gaming? Mass Effect 2 IMO",
        "Y'all need to embrace your local libraries. Just rented this for free.",
        "What are your top 5 single player story games of all time?",
    ],
    "worldnews": [
        "Scientists confirm Arctic ice sheet has lost 30% more mass than previously estimated",
        "International coalition agrees to phase out fossil fuel subsidies by 2030",
        "New renewable energy installations exceeded fossil fuel capacity for the first time globally",
        "UN report warns of critical water shortages affecting 3 billion people by 2030",
    ],
    "movies": [
        "Christopher Nolan's new film 'Odyssey' officially greenlit with a $250M budget",
        "Denis Villeneuve confirms Dune: Part Three is in development",
        "The original Star Wars trilogy is getting a theatrical re-release in IMAX",
        "Martin Scorsese announces his next film will be a 3-hour epic about the Roman Empire",
    ],
    "mildlyinfuriating": [
        "When digital menus randomly change to a 30s advert",
        "I ordered some comic books and the packaging was shredded up comic books",
        "AITA smoking weed on my porch?",
    ],
    "pics": [
        "Younes Lalehzar, A Jewish community leader, stands next to ruins of Yousef Abad Synagogue in Tehran",
        "Princess Diana shared a heartfelt hug with a young fan during her 1995 visit to Birmingham",
    ],
    "programming": [
        "Why I switched from TypeScript back to Python for my backend and never looked back",
        "Rust just overtook C++ as the 5th most popular programming language on the TIOBE Index",
        "The most useful Git commands nobody teaches you",
        "I built a full-stack app in a weekend using only AI code assistants — here's what I learned",
        "PostgreSQL 17 released with native JSON column type and 2x faster queries",
    ],
    "personalfinance": [
        "Just paid off $87,000 in student loans in 3 years — here's exactly how I did it",
        "PSA: If you're not contributing to your employer's 401k match, you're leaving free money on the table",
        "My financial advisor recommended I invest in whole life insurance. Is this good advice?",
        "I'm 28 and just found out I have $45k in medical debt I didn't know about. What do I do?",
    ],
    "funny": [
        "Everybody Makes Mistakes",
        "Why Do Capybaras Not Get Eaten By Crocodiles?",
    ],
}

# Real comment bodies from Reddit's public API (April 2026) + realistic additions
COMMENT_BODIES = [
    "This is such an important point that I think gets overlooked in most discussions about this topic.",
    "I've been saying this for years. Finally someone puts it into words better than I could.",
    "Can confirm this. I work in this field and see this happen all the time.",
    "This needs to be higher up. Everyone needs to see this.",
    "As someone who's been through something similar, I completely agree with this perspective.",
    "I actually disagree with this take. Here's why:\n\nThe data shows a much more nuanced picture when you look at it from a different angle.",
    "Source? I'd love to read more about this but I want to make sure it's credible.",
    "Underrated comment right here.",
    "The real LPT is always in the comments.",
    "This is a great explanation. I wish my professors had explained it this clearly.",
    "I used to think this way too, but after researching it more, I changed my mind. The key difference is the implementation details that people tend to gloss over.",
    "Thank you for sharing this. It really made my day.",
    "I know I'll get downvoted for this, but I think the opposite is actually true in most cases.",
    "This changed my perspective entirely. Thanks for taking the time to write this out.",
    "Can someone ELI5 this? I'm having trouble understanding the implications.",
    "As a professional in this area, I want to add some context that might be helpful...",
    "Why is this not getting more attention? This is literally the most important issue of our time.",
    "I literally just spit out my coffee reading this. Well played.",
    "Username checks out.",
    "I think you're mixing up correlation and causation here. Just because A and B happen together doesn't mean one causes the other.",
    "This happened to me too! I ended up solving it by taking a completely different approach.",
    "How is this not the top comment? This is exactly what OP needs to hear.",
    "As a developer with 15 years of experience, I can confirm this is the right approach.",
    "This is why I love Reddit. Where else would you get this kind of detailed, expert answer for free?",
    "Obligatory reminder that this is not financial/legal/medical advice.",
    "This thread is a gold mine. Saving for later.",
    # Real comments from Reddit API
    "It takes a while for changes to take effect. The bean counters finally got control of the company around 99/2000 and have never given it back.",
    "I especially love the new prelude which is basically a slap in the face to all Honda fans.",
    "Japan got 10gb fiber for both download and upload in their major cities more than 10 years ago. The hardware in Japan works so well software solutions seem redundant.",
    "The EU and America also have giant subsidies for european and american car makers. The difference is that if a manufacturer creates a great design with the money, they need to share it.",
    "As an EV owner, I usually stop for an hour here and there on long road trips for food and stretch breaks anyway. Driving cross country with only ten minute stops sounds like hell.",
    "The measurement of statistics with children is always a little difficult, as there's a lot of factors to consider.",
    "The platform itself isn't really the problem, kids will just find other ways to be weird online plus there's actually some creative stuff on there.",
    "Until governments start making growing your own food illegal.",
    "Getting pregnant. Had smoked from the age of 15, never remotely tried to quit, quit cold turkey when I found out I was pregnant and never looked back.",
    "Diarrhea = Loss of body fluids which you can replenish externally. Constipation = carrying your toxic waste with you all the time.",
]

# Real usernames from Reddit's public API + realistic additions
USERNAMES = [
    "TechExplorer99", "QuantumPanda", "MidnightCoder", "PixelNomad",
    "DataWizard42", "CoffeeAndCode", "NebulaDrifter", "SilentObserver",
    "ThreadReader", "ByteRunner", "CloudChaser", "StackOverflowed",
    "DigitalSage", "CodeMonkey_X", "AlgorithmicThink", "NeuralNexus",
    "PhotonWave", "BinaryBard", "CryptoSkeptic", "DeepDiver",
    # Real Reddit usernames from API
    "MarvelsGrantMan136", "SPXQuantAlgo", "TripleShotPls", "bigbusta",
    "pathofdumbasses", "confusiondiffusion", "penseurquelconque",
    "spaceraingame", "HerrMilkmann", "drunksandman", "ryushin6",
]


_TEMPLATE_RE = re.compile(r"\{(actor|output)\.([^}]+)\}")
_EXACT_REF_RE = re.compile(r"^\{(actor|output)\.([^}]+)\}$")


class RedditSeedRunner:
    """Execute the declarative ``seed:`` config from a Reddit task YAML."""

    def run(
        self, task: TaskDefinition, seed: int, fake: Any, rng: random.Random
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return ``(base_state, targets)`` for one Reddit task seed."""
        now = derive_anchor_time(seed)
        base = self._base_skeleton(task.task_id, now, rng)

        ctx = RedditSeedContext(
            seed=seed,
            rng=rng,
            fake=fake,
            now=now,
            base=base,
        )
        # Sync counters with base skeleton so IDs don't collide
        ctx.counters["post"] = base.get("id_counters", {}).get("post", 0)
        ctx.counters["comment"] = base.get("id_counters", {}).get("comment", 0)
        ctx.counters["msg"] = base.get("id_counters", {}).get("msg", 0)
        ctx.counters["sub"] = base.get("id_counters", {}).get("sub", 0)
        ctx.counters["notif"] = base.get("id_counters", {}).get("notif", 0)

        seed_cfg = task.seed
        if seed_cfg is None:
            raise ValueError(
                f"Task {task.task_id} has no seed config — cannot run builder pipeline"
            )

        # 1. Resolve actors (order matches YAML dict order → deterministic)
        for key, actor_spec in seed_cfg.actors.items():
            ctx.resolve_actor(
                key,
                domain=actor_spec.domain,
                is_vip=actor_spec.is_vip,
                name=actor_spec.name,
            )

        # 2. Execute builder steps in order
        for step in seed_cfg.steps:
            builder = REDDIT_BUILDER_REGISTRY.get(step.use)
            if builder is None:
                raise KeyError(
                    f"No builder registered for '{step.use}' "
                    f"(task {task.task_id})"
                )
            resolved_params = self._resolve_params(step.params, ctx)
            result = builder(ctx, resolved_params)
            # Store named outputs with alias resolution
            self._store_step_outputs(
                task_id=task.task_id,
                builder_name=step.use,
                declared_outputs=step.outputs,
                result=result,
                ctx=ctx,
            )

        # 3. Add generic distractors
        self._add_generic_distractors(ctx, count=seed_cfg.distractors)

        # 3b. Resolve task targets first so username-valued targets
        # (message recipients like target.msg_to / target.new_to that never
        # appear as a post/comment/message author) feed into profile sync.
        targets = self._resolve_targets(seed_cfg.targets, ctx)

        # 3c. Guarantee every authored entity has a user profile so that
        # /u/<author> renders instead of 404ing. Tasks sometimes seed posts,
        # comments, or messages for named characters (e.g. CryptoSkeptic)
        # that were never added to the baseline user_profiles sample, which
        # leaves the block-user flow and profile navigation broken for any
        # task that asks the agent to act on that user. Also scan resolved
        # targets for message-recipient / user-reference fields.
        self._sync_user_profiles(
            ctx,
            targets=targets,
            instruction=getattr(task, "instruction_template", None),
        )

        # 4. Sort posts by time
        base["posts"] = sorted(
            base["posts"], key=lambda p: p.created_at, reverse=True
        )

        # 5. Sync counters back
        base["id_counters"] = dict(ctx.counters)

        return base, targets

    # ------------------------------------------------------------------
    # Output storage with alias resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _store_step_outputs(
        *,
        task_id: str,
        builder_name: str,
        declared_outputs: list[str],
        result: dict[str, Any],
        ctx: RedditSeedContext,
    ) -> None:
        """Persist builder outputs, resolving aliases when declared names
        differ from canonical builder keys (e.g. search_post_id -> post_id)."""
        result_keys = list(result.keys())

        for index, out_key in enumerate(declared_outputs):
            # Direct match
            if out_key in result:
                value = result[out_key]
            # Single-value builder: any alias maps to it
            elif len(result_keys) == 1:
                value = result[result_keys[0]]
            # Positional match when declared count == result count
            elif len(declared_outputs) == len(result_keys):
                value = result[result_keys[index]]
            else:
                # Prefix match: search_post_id -> post_id
                candidates = [k for k in result_keys if out_key.startswith(f"{k}_")]
                if len(candidates) == 1:
                    value = result[candidates[0]]
                else:
                    available = ", ".join(result_keys) if result_keys else "<none>"
                    raise KeyError(
                        f"Builder '{builder_name}' for task {task_id} did not produce "
                        f"requested output '{out_key}'. Available: {available}"
                    )
            _assign_output(ctx.outputs, out_key, value, task_id=task_id, builder_name=builder_name)

    # ------------------------------------------------------------------
    # Param / target template resolution (same pattern as Gmail/Amazon)
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_params(
        cls, params: dict[str, Any], ctx: RedditSeedContext
    ) -> dict[str, Any]:
        return {k: cls._resolve_value(v, ctx) for k, v in params.items()}

    @classmethod
    def _resolve_value(cls, value: Any, ctx: RedditSeedContext) -> Any:
        if isinstance(value, str):
            exact = _EXACT_REF_RE.match(value)
            if exact:
                return cls._raw_lookup(exact.group(1), exact.group(2), ctx)
            return _TEMPLATE_RE.sub(
                lambda m: str(cls._raw_lookup(m.group(1), m.group(2), ctx)),
                value,
            )
        if isinstance(value, list):
            return [cls._resolve_value(v, ctx) for v in value]
        if isinstance(value, dict):
            return {k: cls._resolve_value(v, ctx) for k, v in value.items()}
        return value

    @staticmethod
    def _raw_lookup(kind: str, path: str, ctx: RedditSeedContext) -> Any:
        if kind == "actor":
            parts = path.split(".", 1)
            actor = ctx.actors[parts[0]]
            if len(parts) == 1:
                return actor["name"]
            return actor.get(parts[1], "")
        return ctx.outputs[path]

    @classmethod
    def _resolve_targets(
        cls, templates: dict[str, str], ctx: RedditSeedContext
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, tmpl in templates.items():
            resolved[key] = cls._resolve_value(tmpl, ctx)
        return resolved

    # ------------------------------------------------------------------
    # Generic distractors
    # ------------------------------------------------------------------

    @staticmethod
    def _sync_user_profiles(
        ctx: RedditSeedContext,
        targets: dict[str, Any] | None = None,
        instruction: str | None = None,
    ) -> None:
        """Ensure every authored entity has a matching UserProfile.

        Collects authors from posts/comments, senders/recipients from
        messages, and notification from_user fields; any name missing from
        ``user_profiles`` (and not the owner) gets a minimal auto-generated
        profile so ``/u/<name>`` renders and the Block-User button shows up.
        When resolved ``targets`` are provided, also pulls usernames from
        target keys that identify message recipients or user references
        (e.g. ``msg_to``, ``new_to``, ``reply_from``, ``block_user``,
        ``target_user``) so an agent that navigates to the recipient's
        profile before messaging still finds the user.
        """
        base = ctx.base
        owner = str(base.get("owner_username", "")).lower()
        known = {u.username.lower() for u in base.get("user_profiles", [])}
        seen: list[str] = []
        seen_lower: set[str] = set()

        def collect(name: str | None) -> None:
            if not name:
                return
            low = name.lower()
            if low == owner or low in known or low in seen_lower:
                return
            seen.append(name)
            seen_lower.add(low)

        for post in base.get("posts", []):
            collect(getattr(post, "author_name", None))
        for c in base.get("comments", []):
            collect(getattr(c, "author_name", None))
        for m in base.get("messages", []):
            collect(getattr(m, "from_user", None))
            collect(getattr(m, "to_user", None))
        for m in base.get("sent_messages", []):
            collect(getattr(m, "to_user", None))
        for n in base.get("notifications", []):
            collect(getattr(n, "from_user", None))

        # Target keys whose *values* identify a Reddit user the agent is
        # told to act on. Messaging tasks pass recipient usernames through
        # these fields; a fallback below catches any ``*_user`` / ``*_to``
        # key name too.
        if targets:
            user_slots = {
                "msg_to", "new_to", "m_to", "mt",
                "reply_from", "reply_to", "reply_author",
                "block_user", "target_user",
                "save_author", "comment_author",
                "from_user", "to_user",
            }
            for key, val in targets.items():
                if not isinstance(val, str):
                    continue
                if key in user_slots or key.endswith("_user") or key.endswith("_to"):
                    collect(val)

        # Last-resort fallback: scan the instruction template for literal
        # ``u/<name>`` references. Some tasks (e.g. reddit_compose_message)
        # hard-code the recipient username in the instruction and keep
        # ``targets`` empty, which would otherwise leave no signal for the
        # recipient to appear as a navigable profile.
        if instruction:
            import re as _re
            for raw in _re.findall(r"u/([A-Za-z][A-Za-z0-9_]+)", instruction):
                collect(raw)

        next_idx = len(base.get("user_profiles", [])) + 1
        interests = ["technology", "science", "gaming", "photography", "music"]
        for name in seen:
            profile = UserProfile(
                id=f"user_{next_idx}",
                username=name,
                display_name=name.replace("_", " "),
                about=(
                    f"Reddit user since {ctx.rng.randint(2015, 2024)}. "
                    f"Interested in {ctx.rng.choice(interests)}."
                ),
                post_karma=ctx.rng.randint(100, 500000),
                comment_karma=ctx.rng.randint(500, 1000000),
                cake_day=ctx.now - timedelta(days=ctx.rng.randint(30, 365 * 10)),
                is_premium=ctx.rng.random() < 0.1,
                trophies=ctx.rng.sample(
                    ["Verified Email", "One-Year Club", "Five-Year Club", "Gilding I", "Best Comment"],
                    k=ctx.rng.randint(1, 3),
                ),
            )
            base["user_profiles"].append(profile)
            next_idx += 1

    @staticmethod
    def _add_generic_distractors(ctx: RedditSeedContext, count: int) -> None:
        """Add filler posts as distractors."""
        distractor_subs = [s.name for s in ctx.base["subreddits"][:10]]
        distractor_titles = [
            "Just found this interesting article",
            "Can someone help me understand this?",
            "My take on the recent changes",
            "Weekly roundup thread",
            "Unpopular opinion: hear me out",
            "PSA for newcomers to this sub",
            "TIL something fascinating about this topic",
            "Does anyone else experience this?",
        ]
        for _ in range(count):
            sub_name = ctx.rng.choice(distractor_subs)
            title = ctx.rng.choice(distractor_titles)
            ctx.post(
                subreddit_name=sub_name,
                title=title,
                body="Generic discussion content for distractor.",
                score=ctx.rng.randint(1, 3000),
                created_at=ctx.now - timedelta(
                    days=ctx.rng.randint(1, 14),
                    hours=ctx.rng.randint(0, 22),
                ),
            )

    @staticmethod
    def _base_skeleton(task_id: str, now: datetime, rng: random.Random) -> dict[str, Any]:
        """Build a rich, realistic Reddit state."""

        # Create subreddits from real data
        subreddits = []
        for i, data in enumerate(SUBREDDIT_DATA):
            sub = Subreddit(
                id=f"sub_{i + 1}",
                name=data["name"],
                display_name=data["display"],
                description=data["desc"],
                public_description=data["desc"][:100],
                subscriber_count=data["subs"],
                active_users=rng.randint(1000, 50000),
                created_at=now - timedelta(days=rng.randint(365 * 3, 365 * 15)),
                is_subscribed=i < 12,  # subscribed to first 12
                rules=[
                    SubredditRule(title="Be respectful", description="Treat others with respect. No personal attacks.", rule_type="both"),
                    SubredditRule(title="No spam", description="Do not post spam or self-promotional content.", rule_type="post"),
                ],
                flairs=[
                    Flair(id=f"flair_{i}_{j}", text=t, background_color=c)
                    for j, (t, c) in enumerate([
                        ("Discussion", "#0079d3"),
                        ("News", "#ff4500"),
                        ("Question", "#46d160"),
                        ("OC", "#ff8717"),
                    ])
                ],
            )
            subreddits.append(sub)

        subscriptions = [s.id for s in subreddits if s.is_subscribed]

        # Create user profiles
        user_profiles = []
        usernames_used = list(USERNAMES)
        rng.shuffle(usernames_used)
        for i, uname in enumerate(usernames_used[:20]):
            profile = UserProfile(
                id=f"user_{i + 1}",
                username=uname,
                display_name=uname.replace("_", " "),
                about=f"Reddit user since {rng.randint(2015, 2024)}. Interested in {rng.choice(['technology', 'science', 'gaming', 'photography', 'music'])}.",
                post_karma=rng.randint(100, 500000),
                comment_karma=rng.randint(500, 1000000),
                cake_day=now - timedelta(days=rng.randint(30, 365 * 10)),
                is_premium=rng.random() < 0.1,
                trophies=rng.sample(["Verified Email", "One-Year Club", "Five-Year Club", "Gilding I", "Best Comment"], k=rng.randint(1, 3)),
            )
            user_profiles.append(profile)

        # Create realistic posts
        posts: list[Post] = []
        post_counter = 0
        for sub in subreddits:
            titles_pool = POST_TITLES.get(sub.name, [
                f"Interesting discussion about {sub.display_name}",
                f"What do you think about the latest developments in {sub.display_name}?",
                f"My experience with {sub.display_name}",
                f"PSA for {sub.display_name} community members",
            ])

            num_posts = rng.randint(3, 6)
            for j in range(num_posts):
                post_counter += 1
                author = rng.choice(usernames_used[:20])
                title = titles_pool[j % len(titles_pool)]
                is_text = rng.random() < 0.7
                score = rng.randint(-5, 85000)
                age_hours = rng.randint(1, 24 * 14)

                body = ""
                if is_text:
                    num_paragraphs = rng.randint(1, 4)
                    paragraphs = []
                    for _ in range(num_paragraphs):
                        sentences = rng.sample(COMMENT_BODIES, k=min(2, len(COMMENT_BODIES)))
                        paragraphs.append(" ".join(sentences))
                    body = "\n\n".join(paragraphs)

                post = Post(
                    id=f"post_{post_counter}",
                    subreddit_id=sub.id,
                    subreddit_name=sub.name,
                    author_name=author,
                    title=title,
                    body=body,
                    url="" if is_text else f"https://example.com/article-{post_counter}",
                    post_type="text" if is_text else "link",
                    score=score,
                    upvote_ratio=round(rng.uniform(0.5, 0.99), 2),
                    comment_count=0,  # will be updated below
                    created_at=now - timedelta(hours=age_hours),
                    is_pinned=j == 0 and rng.random() < 0.2,
                    flair_text=rng.choice([None, "Discussion", "News", "Question", "OC"]),
                    flair_color=rng.choice([None, "#0079d3", "#ff4500", "#46d160"]),
                    awards=[
                        Award(name=rng.choice(["Gold", "Silver", "Wholesome", "Helpful"]), count=rng.randint(1, 5))
                    ] if score > 5000 and rng.random() < 0.4 else [],
                    permalink=f"/r/{sub.name}/comments/{post_counter}",
                )
                posts.append(post)

        # Owner's own posts (for profile completeness)
        owner_username = "TechNomad_42"
        owner_posts_data = [
            {"sub": "technology", "title": "Just switched to Linux full-time for development — here's my honest review after 6 months", "body": "After years of macOS, I decided to make the switch to Linux (Pop!_OS specifically) for my daily development work. Here are my thoughts after 6 months of full-time use.\n\n**The Good:**\n- Package management is incredible. apt + flatpak covers everything.\n- Docker runs natively without the VM overhead.\n- Terminal experience is unmatched.\n- Customization is limitless.\n\n**The Bad:**\n- Some video conferencing apps still have issues.\n- Had to spend a weekend configuring my multi-monitor setup.\n\nOverall, I'm not going back. The productivity gains are real.", "score": 4521},
            {"sub": "Python", "title": "I built a CLI tool that generates test data for any database schema", "body": "Been working on this for a few months. It reads your DB schema and generates realistic test data with proper foreign key relationships. Supports PostgreSQL, MySQL, and SQLite.\n\nLink to the GitHub repo in comments. Would love feedback!", "score": 892},
            {"sub": "personalfinance", "title": "Finally debt-free at 32 after 5 years of aggressive payoff", "body": "Started with $94k in debt (student loans + car loan). Today I made my last payment. Here's the breakdown of my strategy...", "score": 12400},
        ]
        owner_posts: list[Post] = []
        for i, pdata in enumerate(owner_posts_data):
            post_counter += 1
            sub = next((s for s in subreddits if s.name == pdata["sub"]), subreddits[0])
            post = Post(
                id=f"post_{post_counter}",
                subreddit_id=sub.id,
                subreddit_name=sub.name,
                author_name=owner_username,
                author_is_op=True,
                title=pdata["title"],
                body=pdata["body"],
                post_type="text",
                score=pdata["score"],
                upvote_ratio=round(rng.uniform(0.88, 0.98), 2),
                comment_count=0,
                created_at=now - timedelta(days=rng.randint(2, 60), hours=rng.randint(0, 12)),
                flair_text=rng.choice(["Discussion", "OC", None]),
                awards=[Award(name="Gold", count=1)] if pdata["score"] > 5000 else [],
                permalink=f"/r/{sub.name}/comments/{post_counter}",
            )
            posts.append(post)
            owner_posts.append(post)

        # Create threaded comments
        comments: list[Comment] = []
        comment_counter = 0
        for post in posts:
            num_top_level = rng.randint(2, 8)
            for _ in range(num_top_level):
                comment_counter += 1
                author = rng.choice(usernames_used[:20])
                comment = Comment(
                    id=f"comment_{comment_counter}",
                    post_id=post.id,
                    parent_id=None,
                    author_name=author,
                    body=rng.choice(COMMENT_BODIES),
                    score=rng.randint(-10, 5000),
                    created_at=post.created_at + timedelta(minutes=rng.randint(5, 60 * 24)),
                    is_submitter=author == post.author_name,
                    depth=0,
                    awards=[Award(name="Helpful", count=1)] if rng.random() < 0.05 else [],
                )
                comments.append(comment)

                # Add replies (depth 1)
                num_replies = rng.randint(0, 3)
                for _ in range(num_replies):
                    comment_counter += 1
                    reply_author = rng.choice(usernames_used[:20])
                    reply = Comment(
                        id=f"comment_{comment_counter}",
                        post_id=post.id,
                        parent_id=comment.id,
                        author_name=reply_author,
                        body=rng.choice(COMMENT_BODIES),
                        score=rng.randint(-5, 2000),
                        created_at=comment.created_at + timedelta(minutes=rng.randint(5, 60 * 12)),
                        is_submitter=reply_author == post.author_name,
                        depth=1,
                    )
                    comments.append(reply)

                    # Occasional depth-2 replies
                    if rng.random() < 0.3:
                        comment_counter += 1
                        deep_author = rng.choice(usernames_used[:20])
                        deep_reply = Comment(
                            id=f"comment_{comment_counter}",
                            post_id=post.id,
                            parent_id=reply.id,
                            author_name=deep_author,
                            body=rng.choice(COMMENT_BODIES),
                            score=rng.randint(0, 500),
                            created_at=reply.created_at + timedelta(minutes=rng.randint(10, 60 * 6)),
                            is_submitter=deep_author == post.author_name,
                            depth=2,
                        )
                        comments.append(deep_reply)

            post.comment_count = sum(1 for c in comments if c.post_id == post.id)

        # Owner's comments
        owner_comment_posts = rng.sample(posts[:20], k=min(8, len(posts)))
        for post in owner_comment_posts:
            comment_counter += 1
            comment = Comment(
                id=f"comment_{comment_counter}",
                post_id=post.id,
                parent_id=None,
                author_name=owner_username,
                body=rng.choice([
                    "Great point! I've been thinking about this for a while and I agree with your assessment.",
                    "This is exactly what I needed to hear. Thanks for sharing your experience.",
                    "I have a slightly different take on this. In my experience, the key factor is...",
                    "Bookmarking this for later. Incredibly useful information.",
                    "As someone who works in this area, I can add some additional context...",
                ]),
                score=rng.randint(5, 500),
                created_at=post.created_at + timedelta(minutes=rng.randint(30, 60 * 48)),
                is_submitter=post.author_name == owner_username,
                depth=0,
            )
            comments.append(comment)
            post.comment_count += 1

        # Messages
        messages = []
        message_senders = rng.sample(usernames_used[:20], k=5)
        message_subjects = [
            ("Hey, loved your Linux post!", "Just wanted to say your post about switching to Linux was really helpful. I'm considering making the switch myself. Any tips for a beginner?"),
            ("Collaboration opportunity", "Hi there! I'm working on a similar project and was wondering if you'd be interested in collaborating. Let me know if you're open to chat about it."),
            ("Question about your CLI tool", "I saw your post about the test data generator. Does it support custom data types? I have a use case with JSONB columns in Postgres."),
            ("Mod invitation for r/devtools", "Hey! I'm a mod at r/devtools and we'd love to have you join our mod team. Your contributions have been really valuable to the community."),
            ("Re: Weekend meetup", "Sounds great! I'll be there at 2pm. Should I bring anything?"),
        ]
        for i, (sender, (subj, body)) in enumerate(zip(message_senders, message_subjects)):
            messages.append(Message(
                id=f"msg_{i + 1}",
                from_user=sender,
                to_user=owner_username,
                subject=subj,
                body=body,
                created_at=now - timedelta(hours=rng.randint(1, 72)),
                is_read=i > 1,  # first two unread
            ))

        sent_messages = [
            Message(
                id="msg_sent_1",
                from_user=owner_username,
                to_user="DataWizard42",
                subject="Thanks for the feedback!",
                body="Really appreciate you taking the time to review my project. I'll implement those suggestions.",
                created_at=now - timedelta(hours=rng.randint(5, 48)),
                is_read=True,
            ),
            Message(
                id="msg_sent_2",
                from_user=owner_username,
                to_user="CoffeeAndCode",
                subject="Question about your benchmarks",
                body="Hi! I saw your benchmark results and was wondering what hardware you used. Could you share your testing methodology?",
                created_at=now - timedelta(hours=rng.randint(12, 96)),
                is_read=True,
            ),
        ]

        # Notifications — link each to a relevant post so clicking navigates
        # owner_posts: [0]=technology, [1]=Python, [2]=personalfinance
        _prog_post = next((p for p in posts if p.subreddit_name == "programming"), posts[0] if posts else None)
        notifications = [
            Notification(
                id="notif_1",
                type="comment_reply",
                title="Reply to your comment",
                body=f"{rng.choice(usernames_used[:10])} replied to your comment in r/technology",
                created_at=now - timedelta(hours=rng.randint(1, 6)),
                is_read=False,
                related_post_id=owner_posts[0].id if owner_posts else None,
                subreddit_name="technology",
                from_user=rng.choice(usernames_used[:10]),
            ),
            Notification(
                id="notif_2",
                type="post_reply",
                title="New comment on your post",
                body=f"{rng.choice(usernames_used[:10])} commented on your post 'Just switched to Linux full-time'",
                created_at=now - timedelta(hours=rng.randint(2, 12)),
                is_read=False,
                related_post_id=owner_posts[0].id if owner_posts else None,
                subreddit_name="technology",
                from_user=rng.choice(usernames_used[:10]),
            ),
            Notification(
                id="notif_3",
                type="upvote_milestone",
                title="Your post hit 1000 upvotes!",
                body="Your post in r/personalfinance has reached 1000 upvotes. Congratulations!",
                created_at=now - timedelta(hours=rng.randint(6, 24)),
                is_read=False,
                related_post_id=owner_posts[2].id if len(owner_posts) > 2 else None,
                subreddit_name="personalfinance",
            ),
            Notification(
                id="notif_4",
                type="mention",
                title="You were mentioned",
                body=f"u/{rng.choice(usernames_used[:10])} mentioned you in a comment in r/programming",
                created_at=now - timedelta(hours=rng.randint(12, 48)),
                is_read=True,
                related_post_id=_prog_post.id if _prog_post else None,
                subreddit_name="programming",
                from_user=rng.choice(usernames_used[:10]),
            ),
            Notification(
                id="notif_5",
                type="award",
                title="You received a Gold award!",
                body="A kind redditor has given your post a Gold award.",
                created_at=now - timedelta(hours=rng.randint(24, 72)),
                is_read=True,
                related_post_id=owner_posts[2].id if len(owner_posts) > 2 else None,
                subreddit_name="personalfinance",
            ),
        ]

        # Some saved posts
        saved_post_ids = [posts[i].id for i in rng.sample(range(min(15, len(posts))), k=min(4, len(posts)))]
        for pid in saved_post_ids:
            post = next(p for p in posts if p.id == pid)
            post.is_saved = True

        settings = RedditSettings(
            id="settings_reddit",
            default_feed_sort="hot",
            default_comment_sort="best",
            show_nsfw=False,
            blur_nsfw=True,
            open_links_in_new_tab=True,
            theme="light",
            compact_view=False,
            email_comment_reply=True,
            email_post_reply=True,
            email_mentions=True,
            email_messages=True,
            email_digest=False,
            show_online_status=True,
            allow_followers=True,
            show_active_communities=True,
        )

        return {
            "env_id": "reddit",
            "task_id": task_id,
            "owner_username": owner_username,
            "owner_display_name": "Alex Chen",
            "owner_avatar_url": "",
            "owner_post_karma": 15243,
            "owner_comment_karma": 28891,
            "owner_cake_day": now - timedelta(days=365 * 3 + 42),
            "owner_about": "Software engineer & open-source enthusiast. Building tools that make developers' lives easier. Python | Rust | Linux",
            "subreddits": subreddits,
            "posts": sorted(posts, key=lambda p: p.created_at, reverse=True),
            "comments": comments,
            "messages": messages,
            "sent_messages": sent_messages,
            "notifications": notifications,
            "user_profiles": user_profiles,
            "subscriptions": subscriptions,
            "saved_post_ids": saved_post_ids,
            "saved_comment_ids": [],
            "hidden_post_ids": [],
            "blocked_users": [],
            "settings": settings,
            "id_counters": {
                "post": post_counter,
                "comment": comment_counter,
                "msg": 7,
                "sub": len(subreddits),
                "notif": len(notifications),
            },
        }
