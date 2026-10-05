import { useState, useEffect, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useAmazonLayout } from "../context";
import type { AmazonAccount, Notification } from "../types";

interface NavbarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  onSearchSubmit: () => void;
  cartCount: number;
}

const DEPARTMENTS = [
  "All",
  "Electronics",
  "Books",
  "Home & Kitchen",
  "Clothing",
  "Sports & Outdoors",
  "Health & Beauty",
  "Toys & Games",
  "Office Supplies",
];

export function Navbar({ searchValue, onSearchChange, onSearchSubmit, cartCount }: NavbarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { api, notify } = useAmazonLayout();
  const [unreadCount, setUnreadCount] = useState(0);
  const [showAccountDropdown, setShowAccountDropdown] = useState(false);
  const [searchDepartment, setSearchDepartment] = useState("All");
  const [ownerName, setOwnerName] = useState("Sign in");
  const [isLoggedIn, setIsLoggedIn] = useState(true);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getNotifications(true)
      .then((items: Notification[]) => setUnreadCount(items.length))
      .catch(() => setUnreadCount(0));

    api.getAccount()
      .then((acct: AmazonAccount | null) => {
        if (acct?.owner_name) {
          const first = acct.owner_name.split(" ")[0];
          setOwnerName(first);
        }
        if (acct) {
          setIsLoggedIn(acct.is_logged_in);
        }
      })
      .catch(() => {});
  }, [api, location.pathname]);

  const handleSignOut = async () => {
    setShowAccountDropdown(false);
    try {
      await api.logout();
    } catch {
      // logout is best-effort
    }
    setIsLoggedIn(false);
    setOwnerName("Sign in");
    notify("Signed Out", "You have been signed out.");
    navigate(preserveQueryParams("/login", location.search));
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowAccountDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onSearchSubmit();
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearchSubmit();
  };

  return (
    <header className="amazon-navbar" role="banner">
      <div className="amazon-navbar__inner">
        {/* Logo */}
        <Link
          to={preserveQueryParams("/home", location.search)}
          className="amazon-navbar__logo"
          aria-label="Amazon Home"
        >
          <span className="amazon-navbar__logo-text">amazon</span>
          <span className="amazon-navbar__logo-smile"></span>
        </Link>

        {/* Delivery location */}
        <div className="amazon-navbar__deliver">
          <span className="amazon-navbar__deliver-label">
            <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ marginRight: 2, verticalAlign: "middle" }}>
              <path d="M8 1C5.24 1 3 3.24 3 6c0 4.5 5 9 5 9s5-4.5 5-9c0-2.76-2.24-5-5-5z" />
              <circle cx="8" cy="6" r="1.5" />
            </svg>
            Deliver to
          </span>
          <span className="amazon-navbar__deliver-location">Benchmark User</span>
        </div>

        {/* Search bar */}
        <form
          className="amazon-navbar__search"
          role="search"
          onSubmit={handleFormSubmit}
          action="#"
        >
          <select
            className="amazon-navbar__search-dropdown"
            value={searchDepartment}
            onChange={(e) => setSearchDepartment(e.target.value)}
            aria-label="Search in department"
          >
            {DEPARTMENTS.map((dept) => (
              <option key={dept} value={dept}>{dept}</option>
            ))}
          </select>
          <input
            type="text"
            className="amazon-navbar__search-input"
            placeholder="Search Amazon"
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="Search Amazon"
          />
          <button
            type="submit"
            className="amazon-navbar__search-btn"
            aria-label="Submit search"
          >
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="11" cy="11" r="7" />
              <line x1="16.5" y1="16.5" x2="21" y2="21" />
            </svg>
          </button>
        </form>

        {/* Nav links */}
        <nav className="amazon-navbar__links" aria-label="Main navigation">
          {/* Notification bell */}
          <Link
            to={preserveQueryParams("/notifications", location.search)}
            className="amazon-navbar__notification-bell"
            aria-label={`Notifications, ${unreadCount} unread`}
          >
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 01-3.46 0" />
            </svg>
            {unreadCount > 0 && (
              <span className="amazon-navbar__notification-count">{unreadCount}</span>
            )}
          </Link>

          {/* Account dropdown */}
          <div className="amazon-navbar__account-wrapper" ref={dropdownRef}>
            <button
              className="amazon-navbar__link amazon-navbar__account-trigger"
              onClick={() => setShowAccountDropdown(!showAccountDropdown)}
              aria-expanded={showAccountDropdown}
              aria-haspopup="true"
            >
              <span className="amazon-navbar__link-small">Hello, {ownerName}</span>
              <span className="amazon-navbar__link-bold">Account & Lists &#9662;</span>
            </button>
            {showAccountDropdown && (
              <div className="amazon-navbar__account-dropdown">
                <Link
                  to={preserveQueryParams("/account", location.search)}
                  className="amazon-navbar__dropdown-item"
                  onClick={() => setShowAccountDropdown(false)}
                >
                  Your Account
                </Link>
                <Link
                  to={preserveQueryParams("/orders", location.search)}
                  className="amazon-navbar__dropdown-item"
                  onClick={() => setShowAccountDropdown(false)}
                >
                  Your Orders
                </Link>
                <Link
                  to={preserveQueryParams("/returns", location.search)}
                  className="amazon-navbar__dropdown-item"
                  onClick={() => setShowAccountDropdown(false)}
                >
                  Returns & Refunds
                </Link>
                <Link
                  to={preserveQueryParams("/gift-cards", location.search)}
                  className="amazon-navbar__dropdown-item"
                  onClick={() => setShowAccountDropdown(false)}
                >
                  Gift Cards
                </Link>
                <Link
                  to={preserveQueryParams("/wishlist", location.search)}
                  className="amazon-navbar__dropdown-item"
                  onClick={() => setShowAccountDropdown(false)}
                >
                  Your Wishlist
                </Link>
                <Link
                  to={preserveQueryParams("/settings", location.search)}
                  className="amazon-navbar__dropdown-item"
                  onClick={() => setShowAccountDropdown(false)}
                >
                  Settings
                </Link>
                <hr className="amazon-navbar__dropdown-divider" />
                {isLoggedIn ? (
                  <button
                    className="amazon-navbar__dropdown-item amazon-navbar__dropdown-btn"
                    onClick={handleSignOut}
                  >
                    Sign Out
                  </button>
                ) : (
                  <Link
                    to={preserveQueryParams("/login", location.search)}
                    className="amazon-navbar__dropdown-item"
                    onClick={() => setShowAccountDropdown(false)}
                  >
                    Sign In
                  </Link>
                )}
              </div>
            )}
          </div>

          <Link
            to={preserveQueryParams("/orders", location.search)}
            className="amazon-navbar__link"
          >
            <span className="amazon-navbar__link-small">Returns</span>
            <span className="amazon-navbar__link-bold">& Orders</span>
          </Link>

          <Link
            to={preserveQueryParams("/orders", location.search)}
            className="amazon-navbar__link amazon-navbar__link--orders"
          >
            <span className="amazon-navbar__link-bold">Orders</span>
          </Link>

          <Link
            to={preserveQueryParams("/cart", location.search)}
            className="amazon-navbar__cart"
            aria-label={`Shopping cart, ${cartCount} items`}
          >
            <div className="amazon-navbar__cart-icon">
              <span className="amazon-navbar__cart-count amazon-navbar__cart-count--orange">{cartCount}</span>
              <svg viewBox="0 0 40 36" width="40" height="36" aria-hidden="true">
                <path
                  d="M2 2h6l3 18h22l3-14H13"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                <circle cx="14" cy="30" r="3" fill="currentColor" />
                <circle cx="30" cy="30" r="3" fill="currentColor" />
              </svg>
            </div>
            <span className="amazon-navbar__cart-label">Cart</span>
          </Link>
        </nav>
      </div>

      {/* Sub-nav bar */}
      <div className="amazon-subnav">
        <div className="amazon-subnav__inner">
          <Link to={preserveQueryParams("/home", location.search)} className="amazon-subnav__link">All</Link>
          <Link to={preserveQueryParams("/deals", location.search)} className="amazon-subnav__link">Today's Deals</Link>
          <Link to={preserveQueryParams("/customer-service", location.search)} className="amazon-subnav__link">Customer Service</Link>
          <Link to={preserveQueryParams("/registry", location.search)} className="amazon-subnav__link">Registry</Link>
          <Link to={preserveQueryParams("/gift-cards", location.search)} className="amazon-subnav__link">Gift Cards</Link>
          <Link to={preserveQueryParams("/home", location.search)} className="amazon-subnav__link">Sell</Link>
          <Link to={preserveQueryParams("/search?q=&category=Electronics", location.search)} className="amazon-subnav__link">Electronics</Link>
          <Link to={preserveQueryParams("/search?q=&category=Books", location.search)} className="amazon-subnav__link">Books</Link>
          <Link to={preserveQueryParams("/search?q=&category=Clothing", location.search)} className="amazon-subnav__link">Clothing</Link>
          <Link to={preserveQueryParams(`/search?q=&category=${encodeURIComponent("Home & Kitchen")}`, location.search)} className="amazon-subnav__link">Home & Kitchen</Link>
          <Link to={preserveQueryParams(`/search?q=&category=${encodeURIComponent("Sports & Outdoors")}`, location.search)} className="amazon-subnav__link">Sports</Link>
        </div>
      </div>
    </header>
  );
}
