import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

export function Footer() {
  const location = useLocation();

  return (
    <footer className="amazon-footer" role="contentinfo">
      <div className="amazon-footer__top">
        <button
          className="amazon-footer__back-to-top"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        >
          Back to top
        </button>
      </div>
      <div className="amazon-footer__mid">
        <div className="amazon-footer__col">
          <h4>Get to Know Us</h4>
          <Link to={preserveQueryParams("/home", location.search)}>About Amazon</Link>
        </div>
        <div className="amazon-footer__col">
          <h4>Your Account</h4>
          <Link to={preserveQueryParams("/orders", location.search)}>Your Orders</Link>
          <Link to={preserveQueryParams("/wishlist", location.search)}>Your Wishlist</Link>
          <Link to={preserveQueryParams("/settings", location.search)}>Account Settings</Link>
        </div>
        <div className="amazon-footer__col">
          <h4>Shop With Us</h4>
          <Link to={preserveQueryParams("/cart", location.search)}>Your Cart</Link>
          <Link to={preserveQueryParams("/home", location.search)}>Today's Deals</Link>
        </div>
      </div>
      <div className="amazon-footer__bottom">
        <span className="amazon-footer__logo">amazon</span>
        <span className="amazon-footer__note">BreakingWeb Simulated Environment</span>
      </div>
    </footer>
  );
}
