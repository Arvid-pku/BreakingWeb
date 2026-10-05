import { useEffect, useState } from "react";
import { Button } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { LinkedBank, Transfer } from "../types";

export function TransfersPage() {
  const { api, notify, refreshAccount } = useRobinhoodLayout();
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [banks, setBanks] = useState<LinkedBank[]>([]);
  const [loading, setLoading] = useState(true);
  const [direction, setDirection] = useState<"deposit" | "withdrawal">("deposit");
  const [amount, setAmount] = useState("");
  const [bankId, setBankId] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = async () => {
    try {
      const [t, b] = await Promise.all([api.listTransfers(), api.listBanks()]);
      setTransfers(t);
      setBanks(b);
      if (b.length > 0 && !bankId) {
        const defaultBank = b.find((bank) => bank.is_default) ?? b[0];
        setBankId(defaultBank.id);
      }
    } catch { /* skip */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, [api]);

  const handleSubmit = async () => {
    if (!amount || !bankId) return;
    setIsSubmitting(true);
    try {
      await api.initiateTransfer({
        direction,
        amount: parseFloat(amount),
        bank_account_id: bankId,
      });
      notify(`${direction === "deposit" ? "Deposit" : "Withdrawal"} Initiated`, `$${parseFloat(amount).toFixed(2)}`);
      setAmount("");
      await refreshAccount();
      await load();
    } catch (err) {
      notify("Error", err instanceof Error ? err.message : "Transfer failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) return <div className="rh-loading">Loading...</div>;

  return (
    <div className="rh-transfers" aria-label="Transfers">
      <h1>Transfers</h1>

      <div className="rh-transfers__form">
        <div className="rh-order-form__tabs">
          <button
            aria-label="Deposit"
            className={`rh-order-form__tab ${direction === "deposit" ? "rh-order-form__tab--active" : ""}`}
            onClick={() => setDirection("deposit")}
          >
            Deposit
          </button>
          <button
            className={`rh-order-form__tab ${direction === "withdrawal" ? "rh-order-form__tab--active" : ""}`}
            onClick={() => setDirection("withdrawal")}
          >
            Withdraw
          </button>
        </div>

        <div className="rh-order-form__field">
          <label htmlFor="xfer-bank">From</label>
          <select id="xfer-bank" value={bankId} onChange={(e) => setBankId(e.target.value)}>
            {banks.map((b) => (
              <option key={b.id} value={b.id}>
                {b.bank_name} ({b.account_type}) ****{b.last_four}
              </option>
            ))}
          </select>
        </div>

        <div className="rh-order-form__field">
          <label htmlFor="xfer-amount">Amount</label>
          <input
            id="xfer-amount"
            type="number"
            min="0"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
          />
        </div>

        <Button
          variant="primary"
          disabled={!amount || !bankId || isSubmitting}
          onClick={handleSubmit}
          aria-label={direction === "deposit" ? "Submit deposit" : "Submit withdrawal"}
        >
          {isSubmitting ? "Processing..." : direction === "deposit" ? "Submit Deposit" : "Submit Withdrawal"}
        </Button>
      </div>

      <section className="rh-transfers__history" aria-label="Transfer history">
        <h2>Transfer History</h2>
        {transfers.length === 0 ? (
          <div className="rh-empty">No transfers yet</div>
        ) : (
          <div className="rh-transfers__list">
            {transfers.map((t) => (
              <div key={t.id} className="rh-transfers__row" aria-label={`${t.direction} $${parseFloat(t.amount).toFixed(2)}`}>
                <div className="rh-transfers__info">
                  <span className={t.direction === "deposit" ? "rh-gain" : "rh-loss"}>
                    {t.direction === "deposit" ? "Deposit" : "Withdrawal"}
                  </span>
                  <span>${parseFloat(t.amount).toFixed(2)}</span>
                </div>
                <div className="rh-transfers__meta">
                  <span className="rh-transfers__status">{t.status}</span>
                  <span>{new Date(t.initiated_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
