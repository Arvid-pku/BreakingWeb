interface VoteButtonsProps {
  score: number;
  voteDirection: number;
  onVote: (direction: number) => void;
  vertical?: boolean;
}

export function VoteButtons({ score, voteDirection, onVote, vertical = true }: VoteButtonsProps) {
  const formatScore = (n: number) => {
    if (Math.abs(n) >= 10000) return `${(n / 1000).toFixed(1)}k`;
    if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`;
    return String(n);
  };

  return (
    <div className={`vote-buttons ${vertical ? "vote-buttons--vertical" : "vote-buttons--horizontal"}`}>
      <button
        className={`vote-btn vote-btn--up ${voteDirection === 1 ? "vote-btn--active" : ""}`}
        onClick={() => onVote(voteDirection === 1 ? 0 : 1)}
        aria-label="Upvote"
        aria-pressed={voteDirection === 1}
      >
        ▲
      </button>
      <span className={`vote-score ${voteDirection === 1 ? "vote-score--up" : voteDirection === -1 ? "vote-score--down" : ""}`}>
        {formatScore(score)}
      </span>
      <button
        className={`vote-btn vote-btn--down ${voteDirection === -1 ? "vote-btn--active" : ""}`}
        onClick={() => onVote(voteDirection === -1 ? 0 : -1)}
        aria-label="Downvote"
        aria-pressed={voteDirection === -1}
      >
        ▼
      </button>
    </div>
  );
}
