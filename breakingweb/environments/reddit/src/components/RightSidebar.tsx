import { useNavigate, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Subreddit } from "../types";
import { formatNumber, formatDate } from "../utils";

interface CommunityInfoProps {
  subreddit: Subreddit;
  onSubscribe: () => void;
}

export function CommunityInfo({ subreddit, onSubscribe }: CommunityInfoProps) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="right-sidebar__widget" aria-label={`About r/${subreddit.name}`}>
      <div className="widget-header widget-header--blue">
        <h3>r/{subreddit.name}</h3>
      </div>
      <div className="widget-body">
        <p className="widget-description">{subreddit.description}</p>
        <div className="widget-stats">
          <div className="widget-stat">
            <span className="widget-stat__value">{formatNumber(subreddit.subscriber_count)}</span>
            <span className="widget-stat__label">Members</span>
          </div>
          <div className="widget-stat">
            <span className="widget-stat__value widget-stat__value--online">{formatNumber(subreddit.active_users)}</span>
            <span className="widget-stat__label">Online</span>
          </div>
        </div>
        <div className="widget-meta">
          <span>Created {formatDate(subreddit.created_at)}</span>
        </div>
        <button
          className={`widget-join-btn ${subreddit.is_subscribed ? "widget-join-btn--joined" : ""}`}
          onClick={onSubscribe}
          aria-label={subreddit.is_subscribed ? `Leave r/${subreddit.name}` : `Join r/${subreddit.name}`}
        >
          {subreddit.is_subscribed ? "Joined" : "Join"}
        </button>
        <button
          className="widget-create-post-btn"
          onClick={() => navigate(preserveQueryParams(`/submit?subreddit=${subreddit.name}`, location.search))}
        >
          Create Post
        </button>
      </div>

      {subreddit.rules.length > 0 && (
        <div className="widget-rules">
          <h4 className="widget-rules__title">r/{subreddit.name} Rules</h4>
          <ol className="widget-rules__list">
            {subreddit.rules.map((rule, i) => (
              <li key={i} className="widget-rules__item">
                <span className="widget-rules__number">{i + 1}</span>
                <span className="widget-rules__text">{rule.title}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

interface PopularCommunitiesProps {
  subreddits: Subreddit[];
}

export function PopularCommunities({ subreddits }: PopularCommunitiesProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const top = subreddits
    .slice()
    .sort((a, b) => b.subscriber_count - a.subscriber_count)
    .slice(0, 5);

  return (
    <div className="right-sidebar__widget" aria-label="Popular Communities">
      <div className="widget-header">
        <h3>Popular Communities</h3>
      </div>
      <div className="widget-body widget-body--tight">
        {top.map((sub) => (
          <button
            key={sub.id}
            className="popular-community"
            onClick={() => navigate(preserveQueryParams(`/r/${sub.name}`, location.search))}
            aria-label={`Go to r/${sub.name}`}
          >
            <span className="popular-community__icon">
              {sub.name.charAt(0).toUpperCase()}
            </span>
            <div className="popular-community__info">
              <span className="popular-community__name">r/{sub.name}</span>
              <span className="popular-community__members">{formatNumber(sub.subscriber_count)} members</span>
            </div>
          </button>
        ))}
        <button
          className="popular-community__see-more"
          onClick={() => navigate(preserveQueryParams("/search?type=subreddits&q=", location.search))}
        >
          See more
        </button>
      </div>
    </div>
  );
}

export function RedditPremiumWidget() {
  return (
    <div className="right-sidebar__widget" aria-label="Reddit Premium">
      <div className="widget-body widget-body--centered">
        <div className="premium-icon">Premium</div>
        <h4 className="premium-title">Reddit Premium</h4>
        <p className="premium-text">The best Reddit experience, with monthly Coins</p>
        <button className="premium-btn">Try Now</button>
      </div>
    </div>
  );
}

interface RightSidebarProps {
  subreddit?: Subreddit;
  onSubscribe?: () => void;
  allSubreddits?: Subreddit[];
}

export function RightSidebar({ subreddit, onSubscribe, allSubreddits }: RightSidebarProps) {
  return (
    <aside className="right-sidebar" aria-label="Sidebar">
      {subreddit && onSubscribe && (
        <CommunityInfo subreddit={subreddit} onSubscribe={onSubscribe} />
      )}
      {allSubreddits && allSubreddits.length > 0 && (
        <PopularCommunities subreddits={allSubreddits} />
      )}
      <RedditPremiumWidget />
      <div className="right-sidebar__footer">
        <div className="sidebar-footer__links">
          <span>User Agreement</span>
          <span>Privacy Policy</span>
          <span>Content Policy</span>
        </div>
        <p className="sidebar-footer__copy">Reddit, Inc. &copy; 2026. All rights reserved.</p>
      </div>
    </aside>
  );
}
