import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Address, PaymentMethod, PromoCode, GiftCard } from "../types";
import { useAmazonLayout } from "../context";
import { useFallbackImage } from "../imageFallbacks";

export function CheckoutPage() {
  const { api, cartSummary, refreshCart, notify } = useAmazonLayout();
  const navigate = useNavigate();
  const location = useLocation();

  const [addresses, setAddresses] = useState<Address[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [selectedAddressId, setSelectedAddressId] = useState("");
  const [selectedPaymentId, setSelectedPaymentId] = useState("");
  const [loading, setLoading] = useState(true);
  const [placing, setPlacing] = useState(false);

  const [showNewAddress, setShowNewAddress] = useState(false);
  const [newAddress, setNewAddress] = useState({
    full_name: "",
    street_address: "",
    city: "",
    state: "",
    zip_code: "",
    country: "United States",
    phone: "",
    is_default: false,
  });

  const [promoCode, setPromoCode] = useState("");
  const [appliedPromo, setAppliedPromo] = useState<PromoCode | null>(null);
  const [promoError, setPromoError] = useState("");
  const [applyingPromo, setApplyingPromo] = useState(false);

  const [giftCards, setGiftCards] = useState<GiftCard[]>([]);
  const [useGiftCardBalance, setUseGiftCardBalance] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      api.getAddresses().catch(() => [] as Address[]),
      api.getPaymentMethods().catch(() => [] as PaymentMethod[]),
      api.getGiftCards().catch(() => [] as GiftCard[]),
      cartSummary ? Promise.resolve() : refreshCart(),
    ]).then(([addrs, pms, gcs]) => {
      if (cancelled) return;
      setAddresses(addrs);
      setPaymentMethods(pms);
      setGiftCards(gcs);
      const defaultAddr = addrs.find((a) => a.is_default);
      if (defaultAddr) setSelectedAddressId(defaultAddr.id);
      else if (addrs.length > 0) setSelectedAddressId(addrs[0].id);
      const defaultPm = pms.find((p) => p.is_default);
      if (defaultPm) setSelectedPaymentId(defaultPm.id);
      else if (pms.length > 0) setSelectedPaymentId(pms[0].id);
      setLoading(false);
    });

    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, refreshCart]);

  const handleAddAddress = async () => {
    if (!newAddress.full_name || !newAddress.street_address || !newAddress.city || !newAddress.state || !newAddress.zip_code) {
      notify("Error", "Please fill in all required address fields.");
      return;
    }
    try {
      const addr = await api.addAddress(newAddress);
      setAddresses((prev) => [...prev, addr]);
      setSelectedAddressId(addr.id);
      setShowNewAddress(false);
      setNewAddress({ full_name: "", street_address: "", city: "", state: "", zip_code: "", country: "United States", phone: "", is_default: false });
      notify("Address added", "New shipping address has been saved.");
    } catch {
      notify("Error", "Failed to add address.");
    }
  };

  const handleApplyPromo = async () => {
    if (!promoCode.trim()) return;
    setApplyingPromo(true);
    setPromoError("");
    try {
      const promo = await api.applyPromo(promoCode.trim());
      setAppliedPromo(promo);
      setPromoError("");
      notify("Promo Applied", `Discount code "${promo.code}" has been applied.`);
    } catch {
      setAppliedPromo(null);
      setPromoError("Unable to apply this promo code.");
      notify("Error", "Failed to apply promo code.");
    }
    setApplyingPromo(false);
  };

  const handleRemovePromo = async () => {
    try {
      await api.clearPromo();
    } catch {
      notify("Error", "Failed to remove promo code.");
      return;
    }
    setAppliedPromo(null);
    setPromoCode("");
    setPromoError("");
    notify("Promo Removed", "Discount code has been removed.");
  };

  const handlePlaceOrder = async () => {
    if (!selectedAddressId || !selectedPaymentId) {
      notify("Error", "Please select a shipping address and payment method.");
      return;
    }
    if (!cartSummary || cartSummary.items.length === 0) {
      notify("Error", "Your cart is empty.");
      return;
    }
    setPlacing(true);
    try {
      const order = await api.placeOrder(selectedAddressId, selectedPaymentId, appliedPromo?.code ?? null);
      await refreshCart();
      navigate(preserveQueryParams(`/order-confirmation/${order.id}`, location.search));
    } catch {
      notify("Error", "Failed to place order. Please try again.");
    } finally {
      setPlacing(false);
    }
  };

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading checkout...</p>
      </div>
    );
  }

  const items = cartSummary?.items ?? [];
  const subtotal = cartSummary?.totals?.subtotal ?? 0;
  const shipping = cartSummary?.totals?.shipping ?? (subtotal >= 25 ? 0 : 5.99);
  const tax = cartSummary?.totals?.tax ?? subtotal * 0.08;

  let promoDiscount = 0;
  if (appliedPromo) {
    if (appliedPromo.discount_type === "percentage") {
      promoDiscount = subtotal * (appliedPromo.discount_value / 100);
    } else {
      promoDiscount = Math.min(appliedPromo.discount_value, subtotal);
    }
  }

  const giftCardBalance = giftCards.reduce((sum, gc) => sum + gc.balance, 0);
  const giftCardApplied = useGiftCardBalance ? Math.min(giftCardBalance, subtotal + shipping + tax - promoDiscount) : 0;

  const total = subtotal + shipping + tax - promoDiscount - giftCardApplied;

  if (items.length === 0) {
    return (
      <div className="checkout-empty">
        <h1>Checkout</h1>
        <p>Your cart is empty. Add items before checking out.</p>
      </div>
    );
  }

  return (
    <div className="checkout-page">
      <h1 className="checkout-page__title">Checkout</h1>

      <div className="checkout-page__simulation-banner" role="alert">
        SIMULATION MODE - No real purchases will be made. This is a benchmark environment.
      </div>

      <div className="checkout-page__body">
        <div className="checkout-page__main">
          {/* Shipping address */}
          <section className="checkout-section" aria-label="Shipping address">
            <h2 className="checkout-section__title">
              <span className="checkout-section__number">1</span>
              Shipping address
            </h2>
            <div className="checkout-section__content">
              {addresses.length > 0 ? (
                <div className="checkout-addresses">
                  {addresses.map((addr) => (
                    <label
                      key={addr.id}
                      className={`checkout-address-card ${selectedAddressId === addr.id ? "checkout-address-card--selected" : ""}`}
                    >
                      <input
                        type="radio"
                        name="address"
                        value={addr.id}
                        checked={selectedAddressId === addr.id}
                        onChange={() => setSelectedAddressId(addr.id)}
                        aria-label={`Ship to ${addr.full_name}, ${addr.street_address}`}
                      />
                      <div className="checkout-address-card__info">
                        <strong>{addr.full_name}</strong>
                        <span>{addr.street_address}</span>
                        <span>{addr.city}, {addr.state} {addr.zip_code}</span>
                        <span>{addr.country}</span>
                        {addr.phone && <span>Phone: {addr.phone}</span>}
                      </div>
                    </label>
                  ))}
                </div>
              ) : (
                <p>No saved addresses. Add one below.</p>
              )}

              <button
                className="checkout-section__add-btn"
                onClick={() => setShowNewAddress(!showNewAddress)}
              >
                {showNewAddress ? "Cancel" : "+ Add a new address"}
              </button>

              {showNewAddress && (
                <div className="checkout-new-address">
                  <div className="checkout-form-row">
                    <label>
                      Full name *
                      <input
                        type="text"
                        value={newAddress.full_name}
                        onChange={(e) => setNewAddress({ ...newAddress, full_name: e.target.value })}
                        aria-label="Full name"
                      />
                    </label>
                  </div>
                  <div className="checkout-form-row">
                    <label>
                      Street address *
                      <input
                        type="text"
                        value={newAddress.street_address}
                        onChange={(e) => setNewAddress({ ...newAddress, street_address: e.target.value })}
                        aria-label="Street address"
                      />
                    </label>
                  </div>
                  <div className="checkout-form-row checkout-form-row--split">
                    <label>
                      City *
                      <input
                        type="text"
                        value={newAddress.city}
                        onChange={(e) => setNewAddress({ ...newAddress, city: e.target.value })}
                        aria-label="City"
                      />
                    </label>
                    <label>
                      State *
                      <input
                        type="text"
                        value={newAddress.state}
                        onChange={(e) => setNewAddress({ ...newAddress, state: e.target.value })}
                        aria-label="State"
                      />
                    </label>
                    <label>
                      ZIP *
                      <input
                        type="text"
                        value={newAddress.zip_code}
                        onChange={(e) => setNewAddress({ ...newAddress, zip_code: e.target.value })}
                        aria-label="ZIP code"
                      />
                    </label>
                  </div>
                  <div className="checkout-form-row">
                    <label>
                      Phone
                      <input
                        type="text"
                        value={newAddress.phone}
                        onChange={(e) => setNewAddress({ ...newAddress, phone: e.target.value })}
                        aria-label="Phone number"
                      />
                    </label>
                  </div>
                  <button className="amazon-btn amazon-btn--add-to-cart" onClick={handleAddAddress}>
                    Save address
                  </button>
                </div>
              )}
            </div>
          </section>

          {/* Payment method */}
          <section className="checkout-section" aria-label="Payment method">
            <h2 className="checkout-section__title">
              <span className="checkout-section__number">2</span>
              Payment method
            </h2>
            <div className="checkout-section__content">
              {paymentMethods.length > 0 ? (
                <div className="checkout-payments">
                  {paymentMethods.map((pm) => (
                    <label
                      key={pm.id}
                      className={`checkout-payment-card ${selectedPaymentId === pm.id ? "checkout-payment-card--selected" : ""}`}
                    >
                      <input
                        type="radio"
                        name="payment"
                        value={pm.id}
                        checked={selectedPaymentId === pm.id}
                        onChange={() => setSelectedPaymentId(pm.id)}
                        aria-label={`Pay with ${pm.card_type} ending in ${pm.last_four}`}
                      />
                      <div className="checkout-payment-card__info">
                        <strong>{pm.holder_name}</strong>
                        <span>{pm.card_type} ending in {pm.last_four}</span>
                        <span>Expires {pm.expiry}</span>
                      </div>
                    </label>
                  ))}
                </div>
              ) : (
                <p>No saved payment methods. Please add one in Account Settings.</p>
              )}
            </div>
          </section>

          {/* Promo code */}
          <section className="checkout-section" aria-label="Promo code">
            <h2 className="checkout-section__title">
              <span className="checkout-section__number">3</span>
              Promo code & Gift Cards
            </h2>
            <div className="checkout-section__content">
              <div className="checkout-promo">
                {appliedPromo ? (
                  <div className="checkout-promo__applied">
                    <div className="checkout-promo__applied-info">
                      <span className="checkout-promo__applied-code">{appliedPromo.code}</span>
                      <span className="checkout-promo__applied-discount">
                        {appliedPromo.discount_type === "percentage"
                          ? `-${appliedPromo.discount_value}%`
                          : `-$${appliedPromo.discount_value.toFixed(2)}`
                        }
                      </span>
                      <span className="checkout-promo__applied-savings">
                        You save: ${promoDiscount.toFixed(2)}
                      </span>
                    </div>
                    <button
                      className="checkout-promo__remove-btn"
                      onClick={handleRemovePromo}
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <div className="checkout-promo__input-row">
                    <input
                      type="text"
                      className="checkout-promo__input"
                      value={promoCode}
                      onChange={(e) => { setPromoCode(e.target.value); setPromoError(""); }}
                      placeholder="Enter promo code"
                      aria-label="Promo code"
                    />
                    <button
                      className="amazon-btn amazon-btn--add-to-cart"
                      onClick={handleApplyPromo}
                      disabled={applyingPromo || !promoCode.trim()}
                    >
                      {applyingPromo ? "Applying..." : "Apply"}
                    </button>
                  </div>
                )}
                {promoError && <div className="checkout-promo__error">{promoError}</div>}
              </div>

              {giftCardBalance > 0 && (
                <div className="checkout-giftcard">
                  <label className="checkout-giftcard__toggle">
                    <input
                      type="checkbox"
                      checked={useGiftCardBalance}
                      onChange={(e) => setUseGiftCardBalance(e.target.checked)}
                    />
                    <span>Use Gift Card balance (${giftCardBalance.toFixed(2)} available)</span>
                  </label>
                  {useGiftCardBalance && giftCardApplied > 0 && (
                    <div className="checkout-giftcard__applied">
                      Gift card applied: -${giftCardApplied.toFixed(2)}
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* Review items */}
          <section className="checkout-section" aria-label="Review items">
            <h2 className="checkout-section__title">
              <span className="checkout-section__number">4</span>
              Review items and shipping
            </h2>
            <div className="checkout-section__content">
              <div className="checkout-items">
                {items.map((item) => (
                  <div key={item.id} className="checkout-item">
                    <div className="checkout-item__image">
                      {item.image_url ? (
                        <img
                          src={item.image_url}
                          alt={item.product_name}
                          style={{ width: "100%", height: "100%", objectFit: "contain" }}
                          onError={(e) => useFallbackImage(e, {
                            name: item.product_name,
                            category: item.category,
                            subcategory: item.subcategory,
                          })}
                        />
                      ) : (
                        <div className="cart-item__image-placeholder visible"><span>{(item.product_name ?? "P")[0]}</span></div>
                      )}
                    </div>
                    <div className="checkout-item__info">
                      <div className="checkout-item__name">{item.product_name}</div>
                      {item.variant_name && <div className="checkout-item__variant">Variant: {item.variant_name}</div>}
                      <div className="checkout-item__price">${(item.unit_price ?? 0).toFixed(2)}</div>
                      <div className="checkout-item__qty">Qty: {item.quantity}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>

        {/* Order summary sidebar */}
        <aside className="checkout-page__sidebar" aria-label="Order summary">
          <div className="checkout-summary-box">
            <button
              className="amazon-btn amazon-btn--buy-now checkout-summary-box__place-order"
              onClick={handlePlaceOrder}
              disabled={placing || !selectedAddressId || !selectedPaymentId}
              aria-label="Place your simulated order"
            >
              {placing ? "Placing order..." : "Place Simulated Order"}
            </button>
            <p className="checkout-summary-box__disclaimer">
              By placing your order, you agree that this is a <strong>simulated order</strong> in a benchmark environment. No real purchase will be made.
            </p>
            <hr />
            <h3>Order Summary</h3>
            <div className="checkout-summary-box__row">
              <span>Items ({cartSummary?.item_count ?? 0}):</span>
              <span>${subtotal.toFixed(2)}</span>
            </div>
            <div className="checkout-summary-box__row">
              <span>Shipping & handling:</span>
              <span>${shipping.toFixed(2)}</span>
            </div>
            <div className="checkout-summary-box__row">
              <span>Estimated tax:</span>
              <span>${tax.toFixed(2)}</span>
            </div>
            {promoDiscount > 0 && (
              <div className="checkout-summary-box__row checkout-summary-box__row--discount">
                <span>Promo discount:</span>
                <span>-${promoDiscount.toFixed(2)}</span>
              </div>
            )}
            {giftCardApplied > 0 && (
              <div className="checkout-summary-box__row checkout-summary-box__row--discount">
                <span>Gift card:</span>
                <span>-${giftCardApplied.toFixed(2)}</span>
              </div>
            )}
            <hr />
            <div className="checkout-summary-box__row checkout-summary-box__row--total">
              <strong>Order total:</strong>
              <strong>${Math.max(0, total).toFixed(2)}</strong>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
