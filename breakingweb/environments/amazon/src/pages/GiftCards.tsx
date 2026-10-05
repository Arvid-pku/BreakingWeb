import { useEffect, useState } from "react";

import type { GiftCard } from "../types";
import { useAmazonLayout } from "../context";

export function GiftCardsPage() {
  const { api, notify } = useAmazonLayout();
  const [giftCards, setGiftCards] = useState<GiftCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newAmount, setNewAmount] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.getGiftCards()
      .then((items) => {
        if (!cancelled) {
          setGiftCards(items);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGiftCards([]);
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [api]);

  const totalBalance = giftCards.reduce((sum, gc) => sum + gc.balance, 0);

  const handleAddGiftCard = async () => {
    const code = newCode.trim().toUpperCase();
    if (!code) {
      notify("Error", "Please enter a gift card code.");
      return;
    }
    if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code)) {
      notify("Error", "Invalid code format. Must be XXXX-XXXX-XXXX (letters and digits).");
      return;
    }
    const amount = parseFloat(newAmount);
    if (isNaN(amount) || amount <= 0) {
      notify("Error", "Please enter a valid amount.");
      return;
    }
    try {
      const gc = await api.addGiftCard(code, amount);
      setGiftCards((prev) => [...prev, gc]);
      notify("Gift Card Added", `$${amount.toFixed(2)} gift card has been added to your account.`);
      setNewCode("");
      setNewAmount("");
      setShowAddForm(false);
    } catch {
      notify("Error", "Invalid gift card code. Please check and try again.");
    }
  };

  const handleRedeem = async (id: string) => {
    try {
      const updated = await api.redeemGiftCard(id);
      setGiftCards((prev) => prev.map((gc) => (gc.id === id ? updated : gc)));
      notify("Gift Card Redeemed", "Gift card balance has been applied to your account.");
    } catch {
      setGiftCards((prev) =>
        prev.map((gc) => (gc.id === id ? { ...gc, redeemed: true, balance: 0 } : gc))
      );
      notify("Gift Card Redeemed (simulated)", "Gift card balance has been applied.");
    }
  };

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading gift cards...</p>
      </div>
    );
  }

  return (
    <div className="giftcards-page">
      <h1>Gift Cards</h1>

      <div className="giftcards-balance-box">
        <div className="giftcards-balance-box__label">Your Gift Card Balance</div>
        <div className="giftcards-balance-box__amount">${totalBalance.toFixed(2)}</div>
      </div>

      <div className="giftcards-actions">
        <button
          className="amazon-btn amazon-btn--add-to-cart"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          {showAddForm ? "Cancel" : "Add a Gift Card"}
        </button>
      </div>

      {showAddForm && (
        <div className="giftcards-add-form">
          <h2>Add a Gift Card</h2>
          <div className="giftcards-add-form__field">
            <label htmlFor="gc-code">Gift Card Code</label>
            <input
              id="gc-code"
              type="text"
              value={newCode}
              onChange={(e) => setNewCode(e.target.value)}
              placeholder="Enter claim code (e.g., ABCD-1234-EFGH)"
              aria-label="Gift card code"
            />
          </div>
          <div className="giftcards-add-form__field">
            <label htmlFor="gc-amount">Amount ($)</label>
            <input
              id="gc-amount"
              type="number"
              min="0.01"
              step="0.01"
              value={newAmount}
              onChange={(e) => setNewAmount(e.target.value)}
              placeholder="25.00"
              aria-label="Gift card amount"
            />
          </div>
          <button
            className="amazon-btn amazon-btn--buy-now"
            onClick={handleAddGiftCard}
          >
            Apply to Account
          </button>
        </div>
      )}

      {giftCards.length === 0 ? (
        <div className="giftcards-empty">
          <h2>No gift cards</h2>
          <p>Add a gift card to get started.</p>
        </div>
      ) : (
        <div className="giftcards-list">
          {giftCards.map((gc) => (
            <article key={gc.id} className="giftcard-card">
              <div className="giftcard-card__design">
                <div className="giftcard-card__logo">amazon</div>
                <div className="giftcard-card__amount">${gc.initial_amount.toFixed(2)}</div>
              </div>
              <div className="giftcard-card__info">
                <div className="giftcard-card__code">Code: {gc.code}</div>
                <div className="giftcard-card__balance">
                  Balance: <strong>${gc.balance.toFixed(2)}</strong>
                </div>
                <div className="giftcard-card__added">
                  Added: {new Date(gc.added_at).toLocaleDateString()}
                </div>
                {gc.redeemed ? (
                  <span className="giftcard-card__redeemed">Redeemed</span>
                ) : (
                  <button
                    className="amazon-btn amazon-btn--add-to-cart giftcard-card__redeem-btn"
                    onClick={() => handleRedeem(gc.id)}
                  >
                    Redeem
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
