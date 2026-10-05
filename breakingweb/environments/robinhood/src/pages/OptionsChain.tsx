import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { OptionsContract } from "../types";
import { OptionsTable } from "../components/OptionsTable";

export function OptionsChainPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { api } = useRobinhoodLayout();
  const [contracts, setContracts] = useState<OptionsContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"call" | "put">("call");

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    api.getOptionsChain(symbol)
      .then((c) => { if (!cancelled) setContracts(c); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, symbol]);

  if (loading) return <div className="rh-loading">Loading...</div>;

  const expirations = [...new Set(contracts.map((c) => c.expiration))].sort();

  return (
    <div className="rh-options-chain" aria-label={`${symbol} options chain`}>
      <div className="rh-options-chain__header">
        <h1>{symbol} Options</h1>
        <div className="rh-options-chain__actions">
          <Link to={preserveQueryParams("/options/positions", location.search)}>
            <Button variant="secondary" aria-label="View options positions">Positions</Button>
          </Link>
          <Link to={preserveQueryParams(`/stocks/${symbol}/options/trade`, location.search)}>
            <Button variant="primary" aria-label="Trade options">Trade Options</Button>
          </Link>
        </div>
      </div>

      {expirations.length > 0 && (
        <div className="rh-options-chain__expirations">
          <span className="rh-options-chain__label">Expirations:</span>
          {expirations.map((exp) => (
            <span key={exp} className="rh-options-chain__exp-chip">{exp}</span>
          ))}
        </div>
      )}

      <div className="rh-options-chain__tabs">
        <button
          className={`rh-tab ${activeTab === "call" ? "rh-tab--active" : ""}`}
          onClick={() => setActiveTab("call")}
        >
          Calls
        </button>
        <button
          className={`rh-tab ${activeTab === "put" ? "rh-tab--active" : ""}`}
          onClick={() => setActiveTab("put")}
        >
          Puts
        </button>
      </div>

      {contracts.length === 0 ? (
        <div className="rh-empty">No options contracts available for {symbol}</div>
      ) : (
        <OptionsTable
          contracts={contracts}
          optionType={activeTab}
          onSelect={(contract) => {
            const params = new URLSearchParams();
            params.set("contract_id", contract.contract_id);
            params.set("option_type", contract.option_type);
            params.set("strike", contract.strike);
            params.set("expiration", contract.expiration);
            navigate(
              preserveQueryParams(
                `/stocks/${symbol}/options/trade?${params.toString()}`,
                location.search,
              ),
            );
          }}
        />
      )}
    </div>
  );
}
