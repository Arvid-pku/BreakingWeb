import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Product } from "../types";
import { useAmazonLayout } from "../context";
import { ProductCard } from "../components/ProductCard";
import { amazonCategoryImage } from "../imageFallbacks";

const CATEGORIES = [
  { name: "Electronics", label: "Electronics" },
  { name: "Books", label: "Books" },
  { name: "Clothing", label: "Clothing" },
  { name: "Home & Kitchen", label: "Home" },
  { name: "Sports & Outdoors", label: "Sports" },
  { name: "Toys & Games", label: "Toys" },
  { name: "Health & Beauty", label: "Beauty" },
  { name: "Office Supplies", label: "Office" },
];

const HERO_CATEGORIES = [
  {
    title: "Save on tech essentials",
    linkText: "Shop electronics",
    category: "Electronics",
    items: [
      { label: "Audio", image: "/static/product-images/amazon/electronics-audio.svg" },
      { label: "Computer", image: "/static/product-images/amazon/electronics-computer.svg" },
      { label: "Storage", image: "/static/product-images/amazon/electronics-storage.svg" },
      { label: "Accessories", image: "/static/product-images/amazon/electronics-accessory.svg" },
    ],
  },
  {
    title: "Refresh your home",
    linkText: "Shop home",
    category: "Home & Kitchen",
    items: [
      { label: "Cookware", image: "/static/product-images/amazon/kitchen-cookware.svg" },
      { label: "Drinkware", image: "/static/product-images/amazon/kitchen-drinkware.svg" },
      { label: "Appliances", image: "/static/product-images/amazon/home-appliance.svg" },
      { label: "Groceries", image: "/static/product-images/amazon/grocery.svg" },
    ],
  },
  {
    title: "Fitness and wellness finds",
    linkText: "Shop fitness",
    category: "Sports & Outdoors",
    items: [
      { label: "Training", image: "/static/product-images/amazon/sports-fitness.svg" },
      { label: "Yoga", image: "/static/product-images/amazon/sports-yoga.svg" },
      { label: "Wearables", image: "/static/product-images/amazon/wearable.svg" },
      { label: "Vitamins", image: "/static/product-images/amazon/health-beauty.svg" },
    ],
  },
  {
    title: "Work and school supplies",
    linkText: "Shop office",
    category: "Office Supplies",
    items: [
      { label: "Supplies", image: "/static/product-images/amazon/office-supplies.svg" },
      { label: "Furniture", image: "/static/product-images/amazon/office-furniture.svg" },
      { label: "Books", image: "/static/product-images/amazon/book.svg" },
      { label: "Bags", image: "/static/product-images/amazon/bag.svg" },
    ],
  },
];

export function HomePage() {
  const { api } = useAmazonLayout();
  const location = useLocation();
  const [featured, setFeatured] = useState<Product[]>([]);
  const [deals, setDeals] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      api.getProducts({ page_size: 8, sort_by: "rating" }).catch(() => ({ items: [] as Product[] })),
      api.getProducts({ page_size: 8, sort_by: "price_low" }).catch(() => ({ items: [] as Product[] })),
    ]).then(([featuredResult, dealsResult]) => {
      if (cancelled) return;
      setFeatured(featuredResult.items ?? []);
      setDeals(dealsResult.items ?? []);
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, [api]);

  return (
    <div className="home-page">
      <section className="home-hero" aria-label="Featured shopping departments">
        <span className="home-hero__arrow home-hero__arrow--left" aria-hidden="true" />
        <span className="home-hero__arrow home-hero__arrow--right" aria-hidden="true" />
        <div className="home-hero__content">
          <h1>Fast delivery on everyday finds</h1>
          <p>Shop benchmark essentials across electronics, home, office, fitness, and more.</p>
          <div className="home-hero__cta">
            <Link
              to={preserveQueryParams("/deals", location.search)}
              className="amazon-btn amazon-btn--add-to-cart home-hero__btn"
            >
              Shop Today's Deals
            </Link>
          </div>
        </div>
        <div className="home-hero__visual">
          <img src="/static/product-images/amazon/electronics-audio.svg" alt="" />
          <img src="/static/product-images/amazon/kitchen-cookware.svg" alt="" />
          <img src="/static/product-images/amazon/sports-fitness.svg" alt="" />
        </div>
      </section>

      <section className="home-promo-grid" aria-label="Featured departments">
        {HERO_CATEGORIES.map((promo) => (
          <article key={promo.title} className="home-promo-card">
            <h2>{promo.title}</h2>
            <div className="home-promo-card__tiles">
              {promo.items.map((item) => (
                <Link
                  key={item.label}
                  to={preserveQueryParams(`/search?q=&category=${encodeURIComponent(promo.category)}`, location.search)}
                  className="home-promo-card__tile"
                >
                  <span className="home-promo-card__image">
                    <img src={item.image} alt="" loading="lazy" />
                  </span>
                  <span>{item.label}</span>
                </Link>
              ))}
            </div>
            <Link
              to={preserveQueryParams(`/search?q=&category=${encodeURIComponent(promo.category)}`, location.search)}
              className="home-promo-card__link"
            >
              {promo.linkText}
            </Link>
          </article>
        ))}
      </section>

      <section className="home-categories" aria-label="Shop by category">
        <h2 className="home-section__title">Shop by Category</h2>
        <div className="home-categories__grid">
          {CATEGORIES.map((cat) => (
            <Link
              key={cat.name}
              to={preserveQueryParams(`/search?q=&category=${encodeURIComponent(cat.name)}`, location.search)}
              className="home-category-card"
              aria-label={`Browse ${cat.name}`}
            >
              <div className="home-category-card__square">
                <img
                  src={amazonCategoryImage(cat.name)}
                  alt=""
                  aria-hidden="true"
                  loading="lazy"
                />
              </div>
              <span className="home-category-card__name">{cat.label}</span>
            </Link>
          ))}
        </div>
      </section>

      {/* Featured products */}
      {featured.length > 0 && (
        <section className="home-featured" aria-label="Featured products">
          <h2 className="home-section__title">Featured Products</h2>
          <div className="home-products__grid">
            {featured.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        </section>
      )}

      {/* Deals */}
      {deals.length > 0 && (
        <section className="home-deals" aria-label="Today's deals">
          <div className="home-section__header">
            <h2 className="home-section__title">Top Deals</h2>
            <Link
              to={preserveQueryParams("/deals", location.search)}
              className="home-section__see-all"
            >
              See all deals
            </Link>
          </div>
          <div className="home-products__grid">
            {deals.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        </section>
      )}

      {loading && (
        <div className="amazon-loading" aria-label="Loading products">
          <div className="amazon-spinner" />
          <p>Loading products...</p>
        </div>
      )}
    </div>
  );
}
