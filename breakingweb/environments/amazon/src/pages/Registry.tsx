import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useAmazonLayout } from "../context";

const REGISTRY_TYPES = [
  {
    icon: "\uD83D\uDC8D",
    title: "Wedding Registry",
    desc: "Find everything you need for your big day",
    color: "#fce4ec",
  },
  {
    icon: "\uD83D\uDC76",
    title: "Baby Registry",
    desc: "Prepare for your new arrival",
    color: "#e3f2fd",
  },
  {
    icon: "\uD83C\uDF82",
    title: "Birthday Gift List",
    desc: "Create a list of wishes",
    color: "#fff3e0",
  },
  {
    icon: "\uD83D\uDCCB",
    title: "Custom List",
    desc: "Build a list for any occasion",
    color: "#e8f5e9",
  },
];

export function RegistryPage() {
  const location = useLocation();
  const { notify } = useAmazonLayout();
  const [searchName, setSearchName] = useState("");
  const [searched, setSearched] = useState(false);

  const handleSearch = () => {
    if (searchName.trim()) {
      setSearched(true);
    }
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div className="registry-page">
      <div className="registry-hero">
        <h1>Create your registry or list</h1>
        <p>Share what you need, get what you want</p>
      </div>

      <h2 style={{ marginBottom: 16 }}>Choose a registry type</h2>
      <div className="registry-types">
        {REGISTRY_TYPES.map((type) => (
          <div
            key={type.title}
            className="registry-type-card"
            style={{ backgroundColor: type.color }}
          >
            <div className="registry-type-card__icon">{type.icon}</div>
            <div className="registry-type-card__title">{type.title}</div>
            <div className="registry-type-card__desc">{type.desc}</div>
            <button
              className="amazon-btn amazon-btn--buy-now"
              onClick={() =>
                notify(
                  "Simulated Environment",
                  "Registry creation is simulated in this benchmark environment."
                )
              }
            >
              Create
            </button>
          </div>
        ))}
      </div>

      <div className="registry-find">
        <h2 style={{ marginBottom: 12 }}>Find a registry</h2>
        <div className="registry-find__form">
          <input
            type="text"
            className="registry-find__input"
            placeholder="Search by registrant name"
            value={searchName}
            onChange={(e) => {
              setSearchName(e.target.value);
              setSearched(false);
            }}
            onKeyDown={handleSearchKeyDown}
            aria-label="Search by registrant name"
          />
          <button
            className="amazon-btn amazon-btn--add-to-cart"
            onClick={handleSearch}
            aria-label="Search registries"
          >
            Search
          </button>
        </div>
        {searched && (
          <p style={{ marginTop: 12, color: "#565959" }}>
            No registries found for &ldquo;{searchName.trim()}&rdquo;. Try a different name.
          </p>
        )}
      </div>

      <div style={{ marginBottom: 32 }}>
        <h2 style={{ marginBottom: 12 }}>Your Lists</h2>
        <p style={{ color: "#565959", marginBottom: 8 }}>
          Manage your wishlist and saved items.
        </p>
        <Link
          to={preserveQueryParams("/wishlist", location.search)}
          className="amazon-btn amazon-btn--add-to-cart"
        >
          View Your Wishlist
        </Link>
      </div>
    </div>
  );
}
