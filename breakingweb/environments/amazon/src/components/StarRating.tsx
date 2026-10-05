interface StarRatingProps {
  rating: number;
  reviewCount?: number;
  size?: "sm" | "md" | "lg";
}

export function StarRating({ rating, reviewCount, size = "md" }: StarRatingProps) {
  const fullStars = Math.floor(rating);
  const hasHalf = rating - fullStars >= 0.25 && rating - fullStars < 0.75;
  const adjustedFull = rating - fullStars >= 0.75 ? fullStars + 1 : fullStars;
  const emptyStars = 5 - adjustedFull - (hasHalf ? 1 : 0);

  return (
    <span className={`star-rating star-rating--${size}`} aria-label={`${rating} out of 5 stars`}>
      {Array.from({ length: adjustedFull }, (_, i) => (
        <span key={`full-${i}`} className="star star--full" aria-hidden="true">&#9733;</span>
      ))}
      {hasHalf && <span className="star star--half" aria-hidden="true">&#9733;</span>}
      {Array.from({ length: Math.max(0, emptyStars) }, (_, i) => (
        <span key={`empty-${i}`} className="star star--empty" aria-hidden="true">&#9734;</span>
      ))}
      {reviewCount !== undefined && (
        <span className="star-rating__count">{reviewCount.toLocaleString()}</span>
      )}
    </span>
  );
}
