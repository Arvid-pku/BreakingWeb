import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { AmazonAccount, Address, PaymentMethod } from "../types";
import { useAmazonLayout } from "../context";

interface AddressFormData {
  full_name: string;
  street_address: string;
  city: string;
  state: string;
  zip_code: string;
  country: string;
  phone: string;
  is_default: boolean;
}

interface PaymentFormData {
  card_type: string;
  last_four: string;
  holder_name: string;
  expiry_month: number;
  expiry_year: number;
  is_default: boolean;
}

const EMPTY_ADDRESS: AddressFormData = {
  full_name: "",
  street_address: "",
  city: "",
  state: "",
  zip_code: "",
  country: "United States",
  phone: "",
  is_default: false,
};

const EMPTY_PAYMENT: PaymentFormData = {
  card_type: "Visa",
  last_four: "",
  holder_name: "",
  expiry_month: 1,
  expiry_year: new Date().getFullYear() + 2,
  is_default: false,
};

export function AccountPage() {
  const { api, notify } = useAmazonLayout();
  const location = useLocation();

  const [account, setAccount] = useState<AmazonAccount | null>(null);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);

  // Address form state
  const [showAddressForm, setShowAddressForm] = useState(false);
  const [editingAddressId, setEditingAddressId] = useState<string | null>(null);
  const [addressForm, setAddressForm] = useState<AddressFormData>(EMPTY_ADDRESS);

  // Payment form state
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [paymentForm, setPaymentForm] = useState<PaymentFormData>(EMPTY_PAYMENT);
  const [paymentExpiry, setPaymentExpiry] = useState("");

  // Password form state
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // Delete confirmation
  const [confirmDeleteAddr, setConfirmDeleteAddr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.getAccount().catch(() => null),
      api.getAddresses().catch(() => [] as Address[]),
      api.getPaymentMethods().catch(() => [] as PaymentMethod[]),
    ]).then(([acct, addrs, pms]) => {
      if (cancelled) return;
      setAccount(acct);
      setAddresses(addrs);
      setPaymentMethods(pms);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [api]);

  /* ── Address handlers ── */

  const openAddAddress = () => {
    setEditingAddressId(null);
    setAddressForm(EMPTY_ADDRESS);
    setShowAddressForm(true);
  };

  const openEditAddress = (addr: Address) => {
    setEditingAddressId(addr.id);
    setAddressForm({
      full_name: addr.full_name,
      street_address: addr.street_address,
      city: addr.city,
      state: addr.state,
      zip_code: addr.zip_code,
      country: addr.country || "US",
      phone: addr.phone || "",
      is_default: addr.is_default,
    });
    setShowAddressForm(true);
  };

  const handleSaveAddress = async () => {
    try {
      if (editingAddressId) {
        const updated = await api.updateAddress(editingAddressId, addressForm);
        setAddresses((prev) =>
          prev.map((a) => ({ ...a, is_default: updated.is_default ? a.id === updated.id : a.is_default }))
            .map((a) => (a.id === editingAddressId ? updated : a))
        );
        notify("Address Updated", "Your address has been updated.");
      } else {
        const created = await api.addAddress(addressForm as Omit<Address, "id">);
        setAddresses((prev) => {
          const next = created.is_default ? prev.map((a) => ({ ...a, is_default: false })) : prev;
          return [...next, created];
        });
        notify("Address Added", "Your new address has been saved.");
      }
    } catch {
      notify("Error", editingAddressId ? "Failed to update address." : "Failed to add address.");
      return;
    }
    setShowAddressForm(false);
    setEditingAddressId(null);
    setAddressForm(EMPTY_ADDRESS);
  };

  const handleDeleteAddress = async (id: string) => {
    try {
      await api.deleteAddress(id);
    } catch {
      notify("Error", "Failed to delete address.");
      return;
    }
    setAddresses((prev) => prev.filter((a) => a.id !== id));
    setConfirmDeleteAddr(null);
    notify("Address Removed", "The address has been deleted.");
  };

  const handleSetDefaultAddress = async (id: string) => {
    try {
      await api.updateAddress(id, { is_default: true });
    } catch {
      notify("Error", "Failed to update default address.");
      return;
    }
    setAddresses((prev) =>
      prev.map((a) => ({ ...a, is_default: a.id === id }))
    );
    notify("Default Address", "Default address has been updated.");
  };

  /* ── Payment handlers ── */

  const openAddPayment = () => {
    setPaymentForm(EMPTY_PAYMENT);
    setPaymentExpiry("");
    setShowPaymentForm(true);
  };

  const handlePaymentExpiryChange = (val: string) => {
    // Format as MM/YY
    const cleaned = val.replace(/[^\d]/g, "");
    let formatted = cleaned;
    if (cleaned.length >= 2) {
      formatted = cleaned.slice(0, 2) + "/" + cleaned.slice(2, 4);
    }
    setPaymentExpiry(formatted);
    if (cleaned.length >= 4) {
      const month = parseInt(cleaned.slice(0, 2), 10);
      const year = 2000 + parseInt(cleaned.slice(2, 4), 10);
      setPaymentForm((prev) => ({ ...prev, expiry_month: month, expiry_year: year }));
    }
  };

  const handleSavePayment = async () => {
    const payload: Omit<PaymentMethod, "id"> = {
      card_type: paymentForm.card_type,
      last_four: paymentForm.last_four,
      expiry: `${String(paymentForm.expiry_month).padStart(2, "0")}/${String(paymentForm.expiry_year).slice(-2)}`,
      holder_name: paymentForm.holder_name,
      is_default: paymentForm.is_default,
    };
    try {
      const created = await api.addPaymentMethod(payload);
      setPaymentMethods((prev) => {
        const next = created.is_default ? prev.map((pm) => ({ ...pm, is_default: false })) : prev;
        return [...next, created];
      });
      notify("Payment Method Added", "Your new payment method has been saved.");
    } catch {
      notify("Error", "Failed to add payment method.");
      return;
    }
    setShowPaymentForm(false);
    setPaymentForm(EMPTY_PAYMENT);
    setPaymentExpiry("");
  };

  const handleDeletePayment = async (id: string) => {
    try {
      await api.deletePaymentMethod(id);
    } catch {
      notify("Error", "Failed to delete payment method.");
      return;
    }
    setPaymentMethods((prev) => prev.filter((p) => p.id !== id));
    notify("Payment Method Removed", "The payment method has been deleted.");
  };

  const handleSetDefaultPayment = async (id: string) => {
    try {
      await api.updateSettings({ default_payment_id: id });
    } catch {
      notify("Error", "Failed to update default payment method.");
      return;
    }
    setPaymentMethods((prev) =>
      prev.map((p) => ({ ...p, is_default: p.id === id }))
    );
    notify("Default Payment", "Default payment method has been updated.");
  };

  /* ── Password ── */

  const handleChangePassword = async () => {
    if (!newPassword || !confirmPassword) {
      notify("Error", "Please fill in all password fields.");
      return;
    }
    if (newPassword !== confirmPassword) {
      notify("Error", "New passwords do not match.");
      return;
    }
    try {
      await api.changePassword(currentPassword, newPassword);
      notify("Password Changed", "Your password has been updated successfully.");
    } catch {
      notify("Error", "Failed to update password.");
      return;
    }
    setShowPasswordForm(false);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
  };

  if (loading) {
    return (
      <div className="amazon-loading">
        <div className="amazon-spinner" />
        <p>Loading account...</p>
      </div>
    );
  }

  return (
    <div className="account-page">
      <h1>Your Account</h1>

      {/* ── Account Info ── */}
      <section className="account-section">
        <h2>Login & Security</h2>
        <div className="account-card">
          <div className="account-card__details">
            <div className="account-card__row">
              <span className="account-card__label">Name:</span>
              <span>{account?.owner_name || "Benchmark User"}</span>
            </div>
            <div className="account-card__row">
              <span className="account-card__label">Email:</span>
              <span>{account?.email || "user@benchmark.local"}</span>
            </div>
            <div className="account-card__row">
              <span className="account-card__label">Prime Membership:</span>
              <span>
                {account?.settings.prime_member ? (
                  <>
                    <span className="product-card__prime" style={{ marginRight: 6 }}>prime</span>
                    Member
                  </>
                ) : (
                  "Standard"
                )}
              </span>
            </div>
          </div>
          <div className="account-card__actions">
            <button onClick={() => setShowPasswordForm(!showPasswordForm)}>
              {showPasswordForm ? "Cancel" : "Change Password"}
            </button>
            <Link to={preserveQueryParams("/settings", location.search)} style={{ fontSize: 13, color: "#007185" }}>
              Account Settings
            </Link>
          </div>
          {showPasswordForm && (
            <div className="account-form" style={{ marginTop: 12 }}>
              <div className="account-form__row">
                <label className="account-form__label" htmlFor="current-pw">Current Password</label>
                <input
                  className="account-form__input"
                  id="current-pw"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="Enter current password"
                />
              </div>
              <div className="account-form__row">
                <label className="account-form__label" htmlFor="new-pw">New Password</label>
                <input
                  className="account-form__input"
                  id="new-pw"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                />
              </div>
              <div className="account-form__row">
                <label className="account-form__label" htmlFor="confirm-pw">Confirm New Password</label>
                <input
                  className="account-form__input"
                  id="confirm-pw"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm new password"
                />
              </div>
              <button className="amazon-btn amazon-btn--add-to-cart" onClick={handleChangePassword}>
                Save Password
              </button>
            </div>
          )}
        </div>
      </section>

      {/* ── Addresses ── */}
      <section className="account-section">
        <div className="account-section__header">
          <h2>Your Addresses</h2>
          <button className="amazon-btn amazon-btn--add-to-cart" onClick={openAddAddress}>
            + Add new address
          </button>
        </div>

        {showAddressForm && (
          <div className="account-form">
            <h3>{editingAddressId ? "Edit Address" : "Add New Address"}</h3>
            <div className="account-form__row">
              <label className="account-form__label" htmlFor="addr-name">Full Name</label>
              <input
                className="account-form__input"
                id="addr-name"
                value={addressForm.full_name}
                onChange={(e) => setAddressForm((f) => ({ ...f, full_name: e.target.value }))}
                placeholder="Full name"
              />
            </div>
            <div className="account-form__row">
              <label className="account-form__label" htmlFor="addr-street">Street Address</label>
              <input
                className="account-form__input"
                id="addr-street"
                value={addressForm.street_address}
                onChange={(e) => setAddressForm((f) => ({ ...f, street_address: e.target.value }))}
                placeholder="Street address"
              />
            </div>
            <div className="account-form__row" style={{ display: "flex", gap: 12 }}>
              <div style={{ flex: 2 }}>
                <label className="account-form__label" htmlFor="addr-city">City</label>
                <input
                  className="account-form__input"
                  id="addr-city"
                  value={addressForm.city}
                  onChange={(e) => setAddressForm((f) => ({ ...f, city: e.target.value }))}
                  placeholder="City"
                />
              </div>
              <div style={{ flex: 1 }}>
                <label className="account-form__label" htmlFor="addr-state">State</label>
                <input
                  className="account-form__input"
                  id="addr-state"
                  value={addressForm.state}
                  onChange={(e) => setAddressForm((f) => ({ ...f, state: e.target.value }))}
                  placeholder="State"
                />
              </div>
              <div style={{ flex: 1 }}>
                <label className="account-form__label" htmlFor="addr-zip">ZIP Code</label>
                <input
                  className="account-form__input"
                  id="addr-zip"
                  value={addressForm.zip_code}
                  onChange={(e) => setAddressForm((f) => ({ ...f, zip_code: e.target.value }))}
                  placeholder="ZIP"
                />
              </div>
            </div>
            <div className="account-form__row">
              <label className="account-form__label" htmlFor="addr-phone">Phone</label>
              <input
                className="account-form__input"
                id="addr-phone"
                value={addressForm.phone}
                onChange={(e) => setAddressForm((f) => ({ ...f, phone: e.target.value }))}
                placeholder="Phone number"
              />
            </div>
            <div className="account-form__row">
              <label style={{ fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={addressForm.is_default}
                  onChange={(e) => setAddressForm((f) => ({ ...f, is_default: e.target.checked }))}
                  style={{ marginRight: 6 }}
                />
                Set as default address
              </label>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button className="amazon-btn amazon-btn--add-to-cart" onClick={handleSaveAddress}>
                {editingAddressId ? "Update Address" : "Save Address"}
              </button>
              <button
                className="amazon-btn amazon-btn--wishlist"
                onClick={() => { setShowAddressForm(false); setEditingAddressId(null); setAddressForm(EMPTY_ADDRESS); }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {addresses.length === 0 && !showAddressForm ? (
          <p style={{ color: "#565959" }}>No saved addresses. Add one above.</p>
        ) : (
          <div className="account-cards-grid">
            {addresses.map((addr) => (
              <div key={addr.id} className={`account-card ${addr.is_default ? "account-card--default" : ""}`}>
                {addr.is_default && <span className="account-card__badge">Default</span>}
                <div className="account-card__details">
                  <strong>{addr.full_name}</strong>
                  <span>{addr.street_address}</span>
                  <span>{addr.city}, {addr.state} {addr.zip_code}</span>
                  {addr.phone && <span>{addr.phone}</span>}
                </div>
                <div className="account-card__actions" role="group" aria-label={`Actions for address at ${addr.street_address}`}>
                  <button type="button" onClick={() => openEditAddress(addr)}>Edit</button>
                  {!addr.is_default && (
                    <button
                      type="button"
                      aria-label={`Set ${addr.street_address} as default shipping address`}
                      onClick={() => handleSetDefaultAddress(addr.id)}
                    >
                      Set as default
                    </button>
                  )}
                  {confirmDeleteAddr === addr.id ? (
                    <>
                      <span role="alert" style={{ fontSize: 12, color: "#B12704" }}>Delete this address?</span>
                      <button
                        type="button"
                        style={{ color: "#B12704" }}
                        onClick={() => handleDeleteAddress(addr.id)}
                        aria-label={`Confirm delete address at ${addr.street_address}`}
                      >
                        Yes, delete
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteAddr(null)}
                        aria-label="Cancel delete"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmDeleteAddr(addr.id)}
                      aria-label={`Delete address at ${addr.street_address}`}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Payment Methods ── */}
      <section className="account-section">
        <div className="account-section__header">
          <h2>Payment Methods</h2>
          <button className="amazon-btn amazon-btn--add-to-cart" onClick={openAddPayment}>
            + Add new payment method
          </button>
        </div>

        {showPaymentForm && (
          <div className="account-form">
            <h3>Add New Payment Method</h3>
            <div className="account-form__row">
              <label className="account-form__label" htmlFor="pm-type">Card Type</label>
              <select
                className="account-form__input"
                id="pm-type"
                value={paymentForm.card_type}
                onChange={(e) => setPaymentForm((f) => ({ ...f, card_type: e.target.value }))}
              >
                <option value="Visa">Visa</option>
                <option value="Mastercard">Mastercard</option>
                <option value="American Express">American Express</option>
                <option value="Discover">Discover</option>
              </select>
            </div>
            <div className="account-form__row">
              <label className="account-form__label" htmlFor="pm-last4">Last 4 Digits</label>
              <input
                className="account-form__input"
                id="pm-last4"
                value={paymentForm.last_four}
                onChange={(e) => {
                  const v = e.target.value.replace(/\D/g, "").slice(0, 4);
                  setPaymentForm((f) => ({ ...f, last_four: v }));
                }}
                placeholder="1234"
                maxLength={4}
              />
            </div>
            <div className="account-form__row">
              <label className="account-form__label" htmlFor="pm-expiry">Expiration (MM/YY)</label>
              <input
                className="account-form__input"
                id="pm-expiry"
                value={paymentExpiry}
                onChange={(e) => handlePaymentExpiryChange(e.target.value)}
                placeholder="MM/YY"
                maxLength={5}
              />
            </div>
            <div className="account-form__row">
              <label className="account-form__label" htmlFor="pm-holder">Cardholder Name</label>
              <input
                className="account-form__input"
                id="pm-holder"
                value={paymentForm.holder_name}
                onChange={(e) => setPaymentForm((f) => ({ ...f, holder_name: e.target.value }))}
                placeholder="Name on card"
              />
            </div>
            <div className="account-form__row">
              <label style={{ fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={paymentForm.is_default}
                  onChange={(e) => setPaymentForm((f) => ({ ...f, is_default: e.target.checked }))}
                  style={{ marginRight: 6 }}
                />
                Set as default payment method
              </label>
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button className="amazon-btn amazon-btn--add-to-cart" onClick={handleSavePayment}>
                Save Payment Method
              </button>
              <button
                className="amazon-btn amazon-btn--wishlist"
                onClick={() => { setShowPaymentForm(false); setPaymentForm(EMPTY_PAYMENT); setPaymentExpiry(""); }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {paymentMethods.length === 0 && !showPaymentForm ? (
          <p style={{ color: "#565959" }}>No saved payment methods. Add one above.</p>
        ) : (
          <div className="account-cards-grid">
            {paymentMethods.map((pm) => (
              <div key={pm.id} className={`account-card ${pm.is_default ? "account-card--default" : ""}`}>
                {pm.is_default && <span className="account-card__badge">Default</span>}
                <div className="account-card__details">
                  <strong>{pm.card_type}</strong>
                  <span>ending in {pm.last_four}</span>
                  <span>Expires {pm.expiry}</span>
                  <span>{pm.holder_name}</span>
                </div>
                <div
                  className="account-card__actions"
                  role="group"
                  aria-label={`Actions for ${pm.card_type} ending in ${pm.last_four}`}
                >
                  {!pm.is_default && (
                    <button
                      type="button"
                      aria-label={`Set ${pm.card_type} ending in ${pm.last_four} as default payment method`}
                      onClick={() => handleSetDefaultPayment(pm.id)}
                    >
                      Set as default
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label={`Delete ${pm.card_type} ending in ${pm.last_four}`}
                    onClick={() => handleDeletePayment(pm.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Quick Links ── */}
      <section className="account-section">
        <h2>Quick Links</h2>
        <div className="account-grid">
          <Link
            to={preserveQueryParams("/orders", location.search)}
            className="account-card account-card--link"
          >
            <div className="account-card__icon">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M3 9h18" />
                <path d="M9 21V9" />
              </svg>
            </div>
            <h3>Your Orders</h3>
            <p>Track, return, or buy things again</p>
          </Link>

          <Link
            to={preserveQueryParams("/returns", location.search)}
            className="account-card account-card--link"
          >
            <div className="account-card__icon">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.5">
                <polyline points="1 4 1 10 7 10" />
                <path d="M3.51 15a9 9 0 102.13-9.36L1 10" />
              </svg>
            </div>
            <h3>Returns & Refunds</h3>
            <p>View return status and request new returns</p>
          </Link>

          <Link
            to={preserveQueryParams("/gift-cards", location.search)}
            className="account-card account-card--link"
          >
            <div className="account-card__icon">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="8" width="18" height="13" rx="2" />
                <path d="M12 8V21" />
                <path d="M3 12h18" />
                <path d="M7.5 8C5 8 5 5 7.5 5S12 8 12 8" />
                <path d="M16.5 8C19 8 19 5 16.5 5S12 8 12 8" />
              </svg>
            </div>
            <h3>Gift Cards</h3>
            <p>View balance and redeem gift cards</p>
          </Link>

          <Link
            to={preserveQueryParams("/settings", location.search)}
            className="account-card account-card--link"
          >
            <div className="account-card__icon">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
              </svg>
            </div>
            <h3>Account Settings</h3>
            <p>Manage preferences, language, and more</p>
          </Link>
        </div>
      </section>
    </div>
  );
}
