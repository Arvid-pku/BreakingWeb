import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import { useAmazonLayout } from "../context";

export function LoginPage() {
  const { api, notify } = useAmazonLayout();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      notify("Error", "Please enter both email and password.");
      return;
    }
    setLoading(true);
    try {
      await api.login(email, password);
      notify("Welcome!", "You have been signed in successfully.");
      navigate(preserveQueryParams("/home", location.search));
    } catch {
      notify("Signed in (simulated)", "Login is simulated - you are now signed in.");
      navigate(preserveQueryParams("/home", location.search));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-page__container">
        <div className="login-page__logo">
          <span className="amazon-logo-text">amazon</span>
        </div>

        <form className="login-page__form" onSubmit={handleSubmit}>
          <h1 className="login-page__title">Sign in</h1>

          <div className="login-page__field">
            <label htmlFor="login-email">Email or mobile phone number</label>
            <input
              id="login-email"
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              aria-label="Email address"
              autoComplete="email"
            />
          </div>

          <div className="login-page__field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              aria-label="Password"
              autoComplete="current-password"
            />
          </div>

          <button
            type="submit"
            className="amazon-btn amazon-btn--add-to-cart login-page__submit"
            disabled={loading}
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>

          <p className="login-page__disclaimer">
            By continuing, you agree to Amazon's Conditions of Use and Privacy Notice.
          </p>

          <div className="login-page__simulation-note" role="alert">
            This is a simulated login - any credentials work. No real authentication is performed.
          </div>
        </form>

        <div className="login-page__divider">
          <span>New to Amazon?</span>
        </div>

        <button
          className="amazon-btn amazon-btn--wishlist login-page__create"
          onClick={() => navigate(preserveQueryParams("/home", location.search))}
        >
          Create your Amazon account
        </button>
      </div>
    </div>
  );
}
