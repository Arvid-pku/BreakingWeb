import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useAmazonLayout } from "../context";
import { amazonCategoryImage } from "../imageFallbacks";

export function CategoriesPage() {
  const { api } = useAmazonLayout();
  const location = useLocation();
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api.getCategories()
      .then((cats) => {
        if (!cancelled) {
          setCategories(cats);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCategories([
            "Electronics", "Books", "Clothing", "Home & Kitchen",
            "Sports", "Toys", "Automotive", "Beauty",
            "Garden", "Health", "Office", "Pet",
          ]);
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [api]);

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading categories...</p>
      </div>
    );
  }

  return (
    <div className="categories-page">
      <h1>Shop by Category</h1>
      <p className="categories-page__subtitle">Browse our full selection of departments</p>

      <div className="categories-grid">
        {categories.map((cat) => (
          <Link
            key={cat}
            to={preserveQueryParams(`/search?q=&category=${encodeURIComponent(cat)}`, location.search)}
            className="categories-grid__card"
          >
            <div className="categories-grid__icon">
              <img src={amazonCategoryImage(cat)} alt="" loading="eager" />
              <span>{cat.charAt(0).toUpperCase()}</span>
            </div>
            <span className="categories-grid__name">{cat}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
