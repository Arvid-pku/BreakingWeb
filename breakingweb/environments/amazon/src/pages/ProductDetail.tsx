import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams, useLocation, Link } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Product, Review, ProductQuestion } from "../types";
import { useAmazonLayout } from "../context";
import { StarRating } from "../components/StarRating";
import { useFallbackImage } from "../imageFallbacks";

function getDeliveryDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 2);
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { api, refreshCart, notify } = useAmazonLayout();
  const navigate = useNavigate();
  const location = useLocation();

  const [product, setProduct] = useState<Product | null>(null);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [questions, setQuestions] = useState<ProductQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  // Map of variant group name -> selected value. Each dimension (e.g. Color,
  // Size) has its own slot so selecting a value in one group does not wipe
  // the selection in another.
  const [selectedVariants, setSelectedVariants] = useState<Record<string, string>>({});
  const [quantity, setQuantity] = useState(1);
  const [addingToCart, setAddingToCart] = useState(false);

  const [cartAddedProduct, setCartAddedProduct] = useState<string | null>(null);

  const [showReviewForm, setShowReviewForm] = useState(false);
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewTitle, setReviewTitle] = useState("");
  const [reviewBody, setReviewBody] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);

  const [showAskForm, setShowAskForm] = useState(false);
  const [newQuestion, setNewQuestion] = useState("");
  const [askingQuestion, setAskingQuestion] = useState(false);
  const [answeringId, setAnsweringId] = useState<string | null>(null);
  const [newAnswer, setNewAnswer] = useState("");

  const dismissCartBar = useCallback(() => setCartAddedProduct(null), []);

  useEffect(() => {
    if (cartAddedProduct) {
      const timer = setTimeout(dismissCartBar, 5000);
      return () => clearTimeout(timer);
    }
  }, [cartAddedProduct, dismissCartBar]);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);

    Promise.all([
      api.getProduct(id),
      api.getReviews(id).catch(() => [] as Review[]),
      api.getQuestions(id).catch(() => [] as ProductQuestion[]),
    ]).then(([prod, revs, qs]) => {
      if (cancelled) return;
      setProduct(prod);
      setReviews(revs);
      setQuestions(qs);
      if (prod.variants && prod.variants.length > 0) {
        const initial: Record<string, string> = {};
        for (const v of prod.variants) {
          if (!(v.name in initial) && v.in_stock) {
            initial[v.name] = v.value;
          }
        }
        setSelectedVariants(initial);
      }
      setLoading(false);
    }).catch(() => {
      if (!cancelled) setLoading(false);
    });

    return () => { cancelled = true; };
  }, [api, id]);

  const selectedVariantSelections = product?.variants && Object.keys(selectedVariants).length > 0
    ? { ...selectedVariants }
    : undefined;

  const handleAddToCart = async () => {
    if (!product || addingToCart) return;
    setAddingToCart(true);
    try {
      await api.addToCart(product.id, quantity, selectedVariantSelections);
      await refreshCart();
      setCartAddedProduct(product.name);
    } catch {
      notify("Error", "Failed to add item to cart.");
    } finally {
      setAddingToCart(false);
    }
  };

  const handleBuyNow = async () => {
    if (!product || addingToCart) return;
    setAddingToCart(true);
    try {
      await api.addToCart(product.id, quantity, selectedVariantSelections);
      await refreshCart();
      navigate(preserveQueryParams("/checkout", location.search));
    } catch {
      notify("Error", "Failed to add item to cart.");
    } finally {
      setAddingToCart(false);
    }
  };

  const handleAddToWishlist = async () => {
    if (!product) return;
    try {
      await api.addToWishlist(product.id);
      notify("Added to Wishlist", `${product.name} has been saved to your wishlist.`);
    } catch {
      notify("Error", "Failed to add to wishlist.");
    }
  };

  const handleAddReview = async () => {
    if (!id || !reviewTitle.trim() || !reviewBody.trim()) return;
    setSubmittingReview(true);
    try {
      const review = await api.addReview(id, {
        rating: reviewRating,
        title: reviewTitle.trim(),
        body: reviewBody.trim(),
      });
      setReviews((prev) => [review, ...prev]);
      notify("Review Submitted", "Your review has been posted.");
    } catch {
      const simReview: Review = {
        id: `review-${Date.now()}`,
        product_id: id,
        author_name: "You",
        rating: reviewRating,
        title: reviewTitle.trim(),
        body: reviewBody.trim(),
        created_at: new Date().toISOString(),
        verified_purchase: true,
        helpful_count: 0,
      };
      setReviews((prev) => [simReview, ...prev]);
      notify("Review Submitted (simulated)", "Your review has been posted.");
    }
    setReviewTitle("");
    setReviewBody("");
    setReviewRating(5);
    setShowReviewForm(false);
    setSubmittingReview(false);
  };

  const handleAskQuestion = async () => {
    if (!id || !newQuestion.trim()) return;
    setAskingQuestion(true);
    try {
      const q = await api.askQuestion(id, newQuestion.trim());
      setQuestions((prev) => [q, ...prev]);
      notify("Question Submitted", "Your question has been posted.");
    } catch {
      const simQ: ProductQuestion = {
        id: `q-${Date.now()}`,
        product_id: id,
        question: newQuestion.trim(),
        asker_name: "You",
        answers: [],
        asked_at: new Date().toISOString(),
        vote_count: 0,
      };
      setQuestions((prev) => [simQ, ...prev]);
      notify("Question Submitted (simulated)", "Your question has been posted.");
    }
    setNewQuestion("");
    setShowAskForm(false);
    setAskingQuestion(false);
  };

  const handleAnswerQuestion = async (questionId: string) => {
    if (!id || !newAnswer.trim()) return;
    try {
      const updated = await api.answerQuestion(id, questionId, newAnswer.trim());
      setQuestions((prev) => prev.map((q) => (q.id === questionId ? updated : q)));
    } catch {
      setQuestions((prev) =>
        prev.map((q) =>
          q.id === questionId
            ? {
                ...q,
                answers: [
                  ...q.answers,
                  {
                    answer: newAnswer.trim(),
                    author_name: "You",
                    answered_at: new Date().toISOString(),
                    helpful_count: 0,
                    is_seller_response: false,
                  },
                ],
              }
            : q
        )
      );
    }
    notify("Answer Submitted", "Your answer has been posted.");
    setNewAnswer("");
    setAnsweringId(null);
  };

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading product...</p>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="amazon-error">
        <h2>Product not found</h2>
        <p>The product you are looking for does not exist or has been removed.</p>
      </div>
    );
  }

  const discount = product.list_price
    ? Math.round(((product.list_price - product.price) / product.list_price) * 100)
    : 0;
  const priceWhole = Math.floor(product.price);
  const priceFraction = (product.price % 1).toFixed(2).slice(2);

  const isBestSeller = product.rating >= 4.5;
  const boughtCount = product.review_count > 1000
    ? `${Math.floor(product.review_count / 100) * 100}+`
    : null;

  return (
    <div className="product-detail">
      {/* Cart Added Notification Bar */}
      {cartAddedProduct && (
        <div className="cart-added-bar" role="alert">
          <span className="cart-added-bar__check">&#10003;</span>
          <span className="cart-added-bar__text">
            <strong>Added to Cart</strong> &mdash; {cartAddedProduct}
          </span>
          <Link
            to={preserveQueryParams("/cart", location.search)}
            className="cart-added-bar__link"
            style={{ textDecoration: "none" }}
          >
            Go to Cart
          </Link>
          <button
            onClick={dismissCartBar}
            style={{ background: "none", border: "none", color: "white", cursor: "pointer", fontSize: 18, marginLeft: 8 }}
            aria-label="Dismiss"
          >
            &times;
          </button>
        </div>
      )}

      {/* Breadcrumb */}
      <nav className="product-detail__breadcrumb" aria-label="Breadcrumb">
        <Link to={preserveQueryParams("/home", location.search)}>Home</Link>
        <span className="product-detail__breadcrumb-sep">&rsaquo;</span>
        <Link to={preserveQueryParams(`/search?q=&category=${encodeURIComponent(product.category)}`, location.search)}>
          {product.category}
        </Link>
        {product.subcategory && (
          <>
            <span className="product-detail__breadcrumb-sep">&rsaquo;</span>
            <Link
              to={preserveQueryParams(
                `/search?q=&category=${encodeURIComponent(product.category)}&subcategory=${encodeURIComponent(product.subcategory)}`,
                location.search,
              )}
              aria-label={`Browse subcategory ${product.subcategory}`}
            >
              {product.subcategory}
            </Link>
          </>
        )}
        <span className="product-detail__breadcrumb-sep">&rsaquo;</span>
        <span className="product-detail__breadcrumb-current">{product.name.length > 60 ? product.name.slice(0, 60) + "..." : product.name}</span>
      </nav>

      <div className="product-detail__top">
        <div className="product-detail__image-col">
          <img
            src={product.image_url}
            alt={product.name}
            loading="eager"
            onError={(e) => useFallbackImage(e, product)}
          />
          <div className="product-detail__image-placeholder">
            <span>{product.category.charAt(0).toUpperCase()}</span>
            <div className="product-detail__image-label">Product Image</div>
          </div>
        </div>

        <div className="product-detail__info-col">
          <h1 className="product-detail__title">{product.name}</h1>
          <div className="product-detail__brand">
            Visit the <span className="product-detail__brand-link">{product.brand}</span> Store
          </div>
          <div className="product-detail__rating">
            <StarRating rating={product.rating} reviewCount={product.review_count} size="md" />
          </div>
          {boughtCount && (
            <div className="product-detail__bought">{boughtCount} bought in past month</div>
          )}

          {isBestSeller && (
            <div className="product-detail__best-seller">
              <span className="product-detail__best-seller-badge">#1 Best Seller</span>
              <span className="product-detail__best-seller-cat">in {product.category}</span>
            </div>
          )}

          <hr className="product-detail__divider" />

          <div className="product-detail__pricing">
            {discount > 0 && (
              <div className="product-detail__discount-row">
                <span className="product-detail__discount-badge">-{discount}%</span>
                <span className="product-detail__price-large">
                  <span className="product-detail__price-currency">$</span>
                  <span className="product-detail__price-whole">{priceWhole}</span>
                  <span className="product-detail__price-fraction">{priceFraction}</span>
                </span>
              </div>
            )}
            {!discount && (
              <div className="product-detail__price-large">
                <span className="product-detail__price-currency">$</span>
                <span className="product-detail__price-whole">{priceWhole}</span>
                <span className="product-detail__price-fraction">{priceFraction}</span>
              </div>
            )}
            {product.list_price && (
              <div className="product-detail__list-price">
                List Price: <span className="product-detail__strikethrough">${product.list_price.toFixed(2)}</span>
              </div>
            )}
          </div>

          {product.prime_eligible && (
            <div className="product-detail__prime">
              <span className="prime-badge">
                <span className="prime-badge__text">prime</span>
                <span className="prime-badge__check">&#10003;</span>
              </span>
              {" "}FREE delivery
            </div>
          )}

          <div className="product-detail__free-returns">
            <a href="#" onClick={(e) => e.preventDefault()} className="product-detail__free-returns-link">FREE Returns</a>
          </div>

          <div className="product-detail__stock">
            {product.in_stock ? (
              <span className="product-detail__in-stock">In Stock</span>
            ) : (
              <span className="product-detail__out-of-stock">Currently unavailable</span>
            )}
          </div>

          {product.variants && product.variants.length > 0 && (
            <div className="product-detail__variants">
              <h3>Options:</h3>
              <div className="product-detail__variant-list">
                {product.variants.map((variant) => (
                  <button
                    key={`${variant.name}:${variant.value}`}
                    className={`product-detail__variant-btn ${selectedVariants[variant.name] === variant.value ? "product-detail__variant-btn--selected" : ""}`}
                    onClick={() => setSelectedVariants((prev) => ({ ...prev, [variant.name]: variant.value }))}
                    disabled={!variant.in_stock}
                    aria-label={`Select variant: ${variant.name} ${variant.value}`}
                    aria-pressed={selectedVariants[variant.name] === variant.value}
                  >
                    <span className="product-detail__variant-name">{variant.name}: {variant.value}</span>
                    {variant.price_modifier !== 0 && (
                      <span className="product-detail__variant-price">
                        {variant.price_modifier > 0 ? "+" : ""}${variant.price_modifier.toFixed(2)}
                      </span>
                    )}
                    {!variant.in_stock && <span className="product-detail__variant-oos">Out of stock</span>}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="product-detail__about">
            <h3>About this item</h3>
            <p>{product.description}</p>
          </div>

          {product.features.length > 0 && (
            <div className="product-detail__features">
              <h3>Product Features</h3>
              <ul>
                {product.features.map((feature, i) => (
                  <li key={i}>{feature}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="product-detail__buy-col">
          <div className="product-detail__buy-box">
            <div className="product-detail__buy-price">
              <span className="product-detail__price-currency">$</span>
              <span className="product-detail__price-whole">{priceWhole}</span>
              <span className="product-detail__price-fraction">{priceFraction}</span>
            </div>
            {product.prime_eligible && (
              <div className="product-detail__buy-delivery">
                <span className="prime-badge">
                  <span className="prime-badge__text">prime</span>
                  <span className="prime-badge__check">&#10003;</span>
                </span>
                {" "}FREE delivery <strong>{getDeliveryDate()}</strong>
              </div>
            )}
            {!product.prime_eligible && (
              <div className="product-detail__buy-delivery">
                FREE delivery <strong>{getDeliveryDate()}</strong>
              </div>
            )}
            <div className="product-detail__buy-free-returns">
              <a href="#" onClick={(e) => e.preventDefault()}>FREE Returns</a>
            </div>
            <div className="product-detail__buy-stock">
              {product.in_stock ? (
                <span className="product-detail__in-stock">In Stock</span>
              ) : (
                <span className="product-detail__out-of-stock">Out of Stock</span>
              )}
            </div>
            <div className="product-detail__buy-shipped-by">
              Ships from and sold by <strong>Amazon.com</strong>
            </div>

            {product.in_stock && (
              <>
                <div className="product-detail__buy-qty">
                  <label htmlFor="buy-qty">Qty:</label>
                  <select
                    id="buy-qty"
                    value={quantity}
                    onChange={(e) => setQuantity(Number(e.target.value))}
                    aria-label="Select quantity"
                  >
                    {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  className="amazon-btn amazon-btn--add-to-cart"
                  onClick={handleAddToCart}
                  disabled={addingToCart || loading || !product}
                  aria-label={`Add ${product?.name ?? "item"} to Cart`}
                  data-action="add-to-cart"
                  data-product-id={product?.id}
                >
                  {addingToCart ? "Adding..." : "Add to Cart"}
                </button>
                <button
                  type="button"
                  className="amazon-btn amazon-btn--buy-now"
                  onClick={handleBuyNow}
                  disabled={addingToCart || loading || !product}
                  aria-label={`Buy ${product?.name ?? "item"} Now`}
                  data-action="buy-now"
                  data-product-id={product?.id}
                >
                  Buy Now
                </button>
                <button
                  type="button"
                  className="amazon-btn amazon-btn--wishlist"
                  onClick={handleAddToWishlist}
                  disabled={loading || !product}
                  aria-label={`Add ${product?.name ?? "item"} to Wishlist`}
                  data-action="add-to-wishlist"
                  data-product-id={product?.id}
                >
                  Add to Wishlist
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Reviews section */}
      <section className="product-detail__reviews" aria-label="Customer reviews">
        <div className="review-header">
          <h2>Customer Reviews</h2>
          <button
            className="amazon-btn amazon-btn--add-to-cart"
            onClick={() => setShowReviewForm(!showReviewForm)}
          >
            {showReviewForm ? "Cancel" : "Write a Review"}
          </button>
        </div>
        <div className="product-detail__review-summary">
          <StarRating rating={product.rating} size="lg" />
          <span className="product-detail__review-avg">{product.rating.toFixed(1)} out of 5</span>
          <span className="product-detail__review-total">{product.review_count} global ratings</span>
        </div>

        {showReviewForm && (
          <div className="review-form" aria-label="Write a review">
            <h3>Write a Customer Review</h3>
            <div className="review-form__rating">
              <label>Overall rating</label>
              <div className="review-form__stars" role="radiogroup" aria-label="Rating">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    className={`review-form__star ${star <= reviewRating ? "review-form__star--active" : ""}`}
                    onClick={() => setReviewRating(star)}
                    aria-label={`${star} star${star !== 1 ? "s" : ""}`}
                    aria-pressed={star === reviewRating}
                  >
                    &#9733;
                  </button>
                ))}
              </div>
            </div>
            <div className="review-form__field">
              <label htmlFor="review-title">Add a headline</label>
              <input
                id="review-title"
                type="text"
                value={reviewTitle}
                onChange={(e) => setReviewTitle(e.target.value)}
                placeholder="What's most important to know?"
                aria-label="Review headline"
              />
            </div>
            <div className="review-form__field">
              <label htmlFor="review-body">Add a written review</label>
              <textarea
                id="review-body"
                value={reviewBody}
                onChange={(e) => setReviewBody(e.target.value)}
                placeholder="What did you like or dislike? What did you use this product for?"
                rows={4}
                aria-label="Review body"
              />
            </div>
            <button
              className="amazon-btn amazon-btn--buy-now"
              onClick={handleAddReview}
              disabled={submittingReview || !reviewTitle.trim() || !reviewBody.trim()}
            >
              {submittingReview ? "Submitting..." : "Submit Review"}
            </button>
          </div>
        )}

        {reviews.length > 0 ? (
          <div className="product-detail__review-list">
            {reviews.map((review) => (
              <article key={review.id} className="review-card" aria-label={`Review by ${review.author_name}`}>
                <div className="review-card__header">
                  <span className="review-card__author">{review.author_name}</span>
                  {review.verified_purchase && (
                    <span className="review-card__verified">Verified Purchase</span>
                  )}
                </div>
                <div className="review-card__rating">
                  <StarRating rating={review.rating} size="sm" />
                  <strong className="review-card__title">{review.title}</strong>
                </div>
                <time className="review-card__date">{new Date(review.created_at).toLocaleDateString()}</time>
                <p className="review-card__body">{review.body}</p>
                <div className="review-card__helpful">
                  {review.helpful_count} {review.helpful_count === 1 ? "person" : "people"} found this helpful
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="product-detail__no-reviews">No reviews yet. Be the first to review this product.</p>
        )}
      </section>

      {/* Q&A Section */}
      <section className="product-detail__qa" aria-label="Questions and Answers">
        <div className="qa-header">
          <h2>Customer Questions & Answers</h2>
          <button
            className="amazon-btn amazon-btn--add-to-cart"
            onClick={() => setShowAskForm(!showAskForm)}
          >
            {showAskForm ? "Cancel" : "Ask a question"}
          </button>
        </div>

        {showAskForm && (
          <div className="qa-ask-form">
            <textarea
              className="qa-ask-form__input"
              value={newQuestion}
              onChange={(e) => setNewQuestion(e.target.value)}
              placeholder="Type your question here..."
              rows={3}
              aria-label="Your question"
            />
            <button
              className="amazon-btn amazon-btn--buy-now"
              onClick={handleAskQuestion}
              disabled={askingQuestion || !newQuestion.trim()}
            >
              {askingQuestion ? "Submitting..." : "Submit Question"}
            </button>
          </div>
        )}

        {questions.length > 0 ? (
          <div className="qa-list">
            {questions.map((q) => (
              <div key={q.id} className="qa-item">
                <div className="qa-item__question">
                  <span className="qa-item__label">Q:</span>
                  <div className="qa-item__text">
                    <p>{q.question}</p>
                    <div className="qa-item__meta">
                      Asked by {q.asker_name} on {new Date(q.asked_at).toLocaleDateString()}
                      {q.vote_count > 0 && <span> - {q.vote_count} votes</span>}
                    </div>
                  </div>
                </div>

                {q.answers.map((a, i) => (
                  <div key={i} className="qa-item__answer">
                    <span className="qa-item__label qa-item__label--answer">A:</span>
                    <div className="qa-item__text">
                      <p>{a.answer}</p>
                      <div className="qa-item__meta">
                        {a.is_seller_response && <span className="qa-item__seller-badge">Seller</span>}
                        {a.author_name} on {new Date(a.answered_at).toLocaleDateString()}
                        {a.helpful_count > 0 && <span> - {a.helpful_count} found helpful</span>}
                      </div>
                    </div>
                  </div>
                ))}

                {answeringId === q.id ? (
                  <div className="qa-answer-form">
                    <textarea
                      className="qa-answer-form__input"
                      value={newAnswer}
                      onChange={(e) => setNewAnswer(e.target.value)}
                      placeholder="Type your answer..."
                      rows={2}
                      aria-label="Your answer"
                    />
                    <div className="qa-answer-form__actions">
                      <button
                        className="amazon-btn amazon-btn--wishlist"
                        onClick={() => { setAnsweringId(null); setNewAnswer(""); }}
                      >
                        Cancel
                      </button>
                      <button
                        className="amazon-btn amazon-btn--add-to-cart"
                        onClick={() => handleAnswerQuestion(q.id)}
                        disabled={!newAnswer.trim()}
                      >
                        Submit Answer
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    className="qa-item__answer-btn"
                    onClick={() => setAnsweringId(q.id)}
                  >
                    Answer this question
                  </button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="qa-empty">No questions yet. Be the first to ask a question about this product.</p>
        )}
      </section>
    </div>
  );
}
