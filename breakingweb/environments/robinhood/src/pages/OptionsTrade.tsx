import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { Button, preserveQueryParams } from "@breakingweb/shared";

import { useRobinhoodLayout } from "../context";
import type { OptionsContract } from "../types";

const STRATEGIES = [
  { value: "single", label: "Single" },
  { value: "vertical", label: "Vertical Spread" },
  { value: "iron_condor", label: "Iron Condor" },
  { value: "straddle", label: "Straddle" },
  { value: "strangle", label: "Strangle" },
  { value: "covered_call", label: "Covered Call" },
  { value: "protective_put", label: "Protective Put" },
] as const;

type StrategyValue = (typeof STRATEGIES)[number]["value"];

interface DraftLeg {
  contractId: string;
  side: "buy" | "sell";
  quantity: string;
}

function byStrikeAscending(a: OptionsContract, b: OptionsContract) {
  return Number.parseFloat(a.strike) - Number.parseFloat(b.strike);
}

function nearestIndex(contracts: OptionsContract[], targetStrike: number) {
  if (contracts.length === 0) return 0;
  let winner = 0;
  let bestDistance = Math.abs(Number.parseFloat(contracts[0].strike) - targetStrike);
  for (let i = 1; i < contracts.length; i += 1) {
    const nextDistance = Math.abs(Number.parseFloat(contracts[i].strike) - targetStrike);
    if (nextDistance < bestDistance) {
      winner = i;
      bestDistance = nextDistance;
    }
  }
  return winner;
}

function clampIndex(index: number, length: number) {
  if (length <= 0) return 0;
  return Math.min(Math.max(index, 0), length - 1);
}

function contractLabel(contract: OptionsContract) {
  return `${contract.option_type.toUpperCase()} $${Number.parseFloat(contract.strike).toFixed(2)} exp ${contract.expiration}`;
}

function buildStrategyLegs(
  strategy: StrategyValue,
  contracts: OptionsContract[],
  anchorContractId?: string | null,
): DraftLeg[] {
  if (contracts.length === 0) return [];

  const anchor = contracts.find((contract) => contract.contract_id === anchorContractId) ?? contracts[0];
  const expiration = anchor.expiration;
  const calls = contracts
    .filter((contract) => contract.expiration === expiration && contract.option_type === "call")
    .sort(byStrikeAscending);
  const puts = contracts
    .filter((contract) => contract.expiration === expiration && contract.option_type === "put")
    .sort(byStrikeAscending);

  const fallbackCall = calls[Math.floor(calls.length / 2)] ?? contracts[0];
  const fallbackPut = puts[Math.floor(puts.length / 2)] ?? contracts[0];
  const referenceCall = anchor.option_type === "call" ? anchor : fallbackCall;
  const referencePut = anchor.option_type === "put" ? anchor : fallbackPut;
  const callIndex = nearestIndex(calls, Number.parseFloat(referenceCall.strike));
  const putIndex = nearestIndex(puts, Number.parseFloat(referencePut.strike));

  const fromCall = (index: number, side: "buy" | "sell"): DraftLeg => ({
    contractId: (calls[clampIndex(index, calls.length)] ?? referenceCall).contract_id,
    side,
    quantity: "1",
  });
  const fromPut = (index: number, side: "buy" | "sell"): DraftLeg => ({
    contractId: (puts[clampIndex(index, puts.length)] ?? referencePut).contract_id,
    side,
    quantity: "1",
  });

  switch (strategy) {
    case "covered_call":
      return [fromCall(callIndex, "sell")];
    case "protective_put":
      return [fromPut(putIndex, "buy")];
    case "vertical":
      return [fromCall(callIndex, "buy"), fromCall(callIndex + 1, "sell")];
    case "straddle":
      return [fromCall(callIndex, "buy"), fromPut(nearestIndex(puts, Number.parseFloat(referenceCall.strike)), "buy")];
    case "strangle":
      return [fromPut(putIndex - 1, "buy"), fromCall(callIndex + 1, "buy")];
    case "iron_condor":
      return [
        fromPut(putIndex - 1, "buy"),
        fromPut(putIndex, "sell"),
        fromCall(callIndex, "sell"),
        fromCall(callIndex + 1, "buy"),
      ];
    case "single":
    default:
      return [{
        contractId: anchor.contract_id,
        side: "buy",
        quantity: "1",
      }];
  }
}

function findClosestContract(
  contracts: OptionsContract[],
  filter: { strike?: string; expiration?: string; option_type?: string },
): OptionsContract | null {
  const matchType = contracts.filter((c) =>
    !filter.option_type || c.option_type === filter.option_type,
  );
  if (matchType.length === 0) return null;

  const matchExp = filter.expiration
    ? matchType.filter((c) => c.expiration === filter.expiration)
    : matchType;
  const pool = matchExp.length > 0 ? matchExp : matchType;

  if (filter.strike !== undefined) {
    const target = Number.parseFloat(filter.strike);
    if (!Number.isNaN(target)) {
      let best = pool[0];
      let bestDist = Math.abs(Number.parseFloat(best.strike) - target);
      for (const c of pool) {
        const d = Math.abs(Number.parseFloat(c.strike) - target);
        if (d < bestDist) { best = c; bestDist = d; }
      }
      return best;
    }
  }
  return pool[0];
}

export function OptionsTradePage() {
  const { symbol } = useParams<{ symbol: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { api, notify } = useRobinhoodLayout();
  const [contracts, setContracts] = useState<OptionsContract[]>([]);
  const [loading, setLoading] = useState(true);
  const [strategy, setStrategy] = useState<StrategyValue>("single");
  const [draftLegs, setDraftLegs] = useState<DraftLeg[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [contextBanner, setContextBanner] = useState<string | null>(null);
  // Per-leg type filter ("any" | "call" | "put") to make the contract dropdown navigable.
  const [legTypeFilter, setLegTypeFilter] = useState<Record<number, "any" | "call" | "put">>({});

  // Parse incoming intent (close, roll, preselected contract) once contracts have loaded.
  const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    api.getOptionsChain(symbol)
      .then((nextContracts) => {
        if (cancelled) return;
        setContracts(nextContracts);

        // Intent params from links (Close / Roll / preselect a contract from the chain).
        const action = searchParams.get("action"); // "close" | "roll" | null
        const presetContractId = searchParams.get("contract_id");
        const presetStrike = searchParams.get("strike") ?? undefined;
        const presetExpiration = searchParams.get("expiration") ?? undefined;
        const presetOptionType = searchParams.get("option_type") ?? undefined;
        const positionSide = searchParams.get("position_side"); // "long" | "short"
        const presetSideParam = searchParams.get("side"); // optional explicit side
        const presetQuantity = searchParams.get("quantity");

        // Resolve target contract by id; if not present, pick the nearest by strike+expiration.
        const targetContract =
          (presetContractId ? nextContracts.find((c) => c.contract_id === presetContractId) : null) ??
          findClosestContract(nextContracts, {
            strike: presetStrike,
            expiration: presetExpiration,
            option_type: presetOptionType,
          });

        if (action === "close" && targetContract) {
          // Close = opposite side of the position.
          const closeSide: "buy" | "sell" = positionSide === "long" ? "sell" : "buy";
          setStrategy("single");
          setDraftLegs([{
            contractId: targetContract.contract_id,
            side: closeSide,
            quantity: presetQuantity ?? "1",
          }]);
          setContextBanner(
            `Closing ${positionSide ?? ""} ${targetContract.option_type.toUpperCase()} $${Number.parseFloat(targetContract.strike).toFixed(2)} exp ${targetContract.expiration} (${closeSide} to close).`,
          );
        } else if (action === "roll" && targetContract) {
          // Roll = leg 1 closes the existing position; leg 2 opens a new one at the same strike but next expiration.
          const closeSide: "buy" | "sell" = positionSide === "long" ? "sell" : "buy";
          const openSide: "buy" | "sell" = closeSide === "buy" ? "sell" : "buy";
          // Find a later expiration with the same option_type for the new leg.
          const sameType = nextContracts.filter((c) => c.option_type === targetContract.option_type);
          const laterExpirations = [...new Set(sameType.map((c) => c.expiration))]
            .filter((e) => e > targetContract.expiration)
            .sort();
          let openLegContract: OptionsContract | null = null;
          if (laterExpirations.length > 0) {
            openLegContract = findClosestContract(sameType, {
              strike: targetContract.strike,
              expiration: laterExpirations[0],
              option_type: targetContract.option_type,
            });
          }
          setStrategy("vertical"); // multi-leg shell so the user has 2 legs immediately
          const legs: DraftLeg[] = [
            {
              contractId: targetContract.contract_id,
              side: closeSide,
              quantity: presetQuantity ?? "1",
            },
          ];
          if (openLegContract) {
            legs.push({
              contractId: openLegContract.contract_id,
              side: openSide,
              quantity: presetQuantity ?? "1",
            });
          }
          setDraftLegs(legs);
          setContextBanner(
            `Rolling ${positionSide ?? ""} ${targetContract.option_type.toUpperCase()} $${Number.parseFloat(targetContract.strike).toFixed(2)} exp ${targetContract.expiration}: leg 1 closes (${closeSide}), leg 2 opens (${openSide}) at the next expiration. Adjust strike/expiration as needed.`,
          );
        } else if (targetContract) {
          // Plain preselect (e.g. clicked a row in the chain).
          const presetSide: "buy" | "sell" = presetSideParam === "sell" ? "sell" : "buy";
          setStrategy("single");
          setDraftLegs([{
            contractId: targetContract.contract_id,
            side: presetSide,
            quantity: presetQuantity ?? "1",
          }]);
        } else {
          setDraftLegs(buildStrategyLegs("single", nextContracts));
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, symbol, searchParams]);

  const contractsById = useMemo(
    () => Object.fromEntries(contracts.map((contract) => [contract.contract_id, contract])),
    [contracts],
  );

  const sortedContracts = useMemo(() => {
    // Group: option_type, then expiration ascending, then strike ascending.
    return [...contracts].sort((a, b) => {
      if (a.option_type !== b.option_type) return a.option_type.localeCompare(b.option_type);
      if (a.expiration !== b.expiration) return a.expiration.localeCompare(b.expiration);
      return Number.parseFloat(a.strike) - Number.parseFloat(b.strike);
    });
  }, [contracts]);

  const netPremium = draftLegs.reduce((total, leg) => {
    const contract = contractsById[leg.contractId];
    if (!contract) return total;
    const quantity = Number.parseInt(leg.quantity || "1", 10) || 1;
    const quote = Number.parseFloat(leg.side === "buy" ? contract.ask : contract.bid);
    return total + (leg.side === "buy" ? 1 : -1) * quote * quantity * 100;
  }, 0);

  const resetForStrategy = (nextStrategy: StrategyValue) => {
    const anchorContractId = draftLegs[0]?.contractId ?? contracts[0]?.contract_id;
    setStrategy(nextStrategy);
    setDraftLegs(buildStrategyLegs(nextStrategy, contracts, anchorContractId));
  };

  const handleLegChange = (index: number, updates: Partial<DraftLeg>) => {
    setDraftLegs((current) => current.map((leg, legIndex) => (
      legIndex === index ? { ...leg, ...updates } : leg
    )));
  };

  const handleAddLeg = () => {
    const fallbackContractId = draftLegs[draftLegs.length - 1]?.contractId ?? contracts[0]?.contract_id;
    if (!fallbackContractId || draftLegs.length >= 4) return;
    setDraftLegs((current) => [
      ...current,
      {
        contractId: fallbackContractId,
        side: "buy",
        quantity: "1",
      },
    ]);
  };

  const handleRemoveLeg = (index: number) => {
    setDraftLegs((current) => current.filter((_, legIndex) => legIndex !== index));
  };

  const handleSubmit = async () => {
    if (!symbol || draftLegs.length === 0) return;
    const legs = draftLegs
      .map((leg) => {
        const contract = contractsById[leg.contractId];
        if (!contract) return null;
        return {
          underlying_symbol: symbol,
          side: leg.side,
          option_type: contract.option_type,
          strike: contract.strike,
          expiration: contract.expiration,
          quantity: Number.parseInt(leg.quantity || "1", 10) || 1,
          premium: leg.side === "buy" ? contract.ask : contract.bid,
        };
      })
      .filter((leg): leg is NonNullable<typeof leg> => leg !== null);

    if (legs.length === 0) return;

    setIsSubmitting(true);
    try {
      await api.placeOptionsOrder({ strategy, legs });
      notify("Options Order Placed", `${strategy.replace(/_/g, " ")} on ${symbol}`);
      navigate(preserveQueryParams("/options/positions", location.search));
    } catch (err) {
      notify("Order Failed", err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) return <div className="rh-loading">Loading...</div>;

  return (
    <div className="rh-options-trade" aria-label={`Trade ${symbol} options`}>
      <div className="rh-options-trade__header">
        <button
          className="rh-back-btn"
          onClick={() => navigate(preserveQueryParams(`/stocks/${symbol}/options`, location.search))}
          aria-label="Back to options chain"
        >
          ← {symbol} Options
        </button>
        <h1>Trade {symbol} Options</h1>
      </div>

      {contextBanner ? (
        <div className="rh-options-trade__banner" role="status" aria-live="polite">
          {contextBanner}
        </div>
      ) : null}

      <div className="rh-order-form__field">
        <label htmlFor="opt-strategy">Strategy</label>
        <select
          id="opt-strategy"
          value={strategy}
          onChange={(e) => resetForStrategy(e.target.value as StrategyValue)}
        >
          {STRATEGIES.map((entry) => (
            <option key={entry.value} value={entry.value}>{entry.label}</option>
          ))}
        </select>
      </div>

      <div className="rh-options-trade__helper">
        Pick a strategy preset or build a custom multi-leg order. Each leg has a Type filter (Calls/Puts) so you can find the right strike quickly. Click "Add Leg" to combine up to 4 legs.
      </div>

      <div className="rh-options-trade__legs">
        {draftLegs.map((leg, index) => {
          const contract = contractsById[leg.contractId];
          const filter = legTypeFilter[index] ?? "any";
          const visibleContracts = sortedContracts.filter((c) => filter === "any" || c.option_type === filter);
          return (
            <div key={`${leg.contractId}-${index}`} className="rh-options-trade__leg-card">
              <div className="rh-options-trade__leg-header">
                <strong>Leg {index + 1}</strong>
                {draftLegs.length > 1 ? (
                  <button
                    type="button"
                    className="rh-options-trade__remove-leg"
                    onClick={() => handleRemoveLeg(index)}
                    aria-label={`Remove leg ${index + 1}`}
                  >
                    Remove
                  </button>
                ) : null}
              </div>
              <div className="rh-options-trade__leg-fields">
                <div className="rh-order-form__field">
                  <label htmlFor={`opt-leg-side-${index}`}>Side</label>
                  <select
                    id={`opt-leg-side-${index}`}
                    value={leg.side}
                    onChange={(e) => handleLegChange(index, { side: e.target.value as "buy" | "sell" })}
                  >
                    <option value="buy">Buy</option>
                    <option value="sell">Sell</option>
                  </select>
                </div>
                <div className="rh-order-form__field">
                  <label htmlFor={`opt-leg-type-${index}`}>Type</label>
                  <select
                    id={`opt-leg-type-${index}`}
                    value={filter}
                    onChange={(e) => setLegTypeFilter((prev) => ({ ...prev, [index]: e.target.value as "any" | "call" | "put" }))}
                  >
                    <option value="any">Any</option>
                    <option value="call">Calls</option>
                    <option value="put">Puts</option>
                  </select>
                </div>
                <div className="rh-order-form__field">
                  <label htmlFor={`opt-leg-contract-${index}`}>Contract</label>
                  <select
                    id={`opt-leg-contract-${index}`}
                    value={leg.contractId}
                    onChange={(e) => handleLegChange(index, { contractId: e.target.value })}
                  >
                    {visibleContracts.map((entry) => (
                      <option key={entry.contract_id} value={entry.contract_id}>
                        {contractLabel(entry)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="rh-order-form__field">
                  <label htmlFor={`opt-leg-quantity-${index}`}>Contracts</label>
                  <input
                    id={`opt-leg-quantity-${index}`}
                    type="number"
                    min="1"
                    value={leg.quantity}
                    onChange={(e) => handleLegChange(index, { quantity: e.target.value })}
                  />
                </div>
              </div>
              {contract ? (
                <div className="rh-options-trade__leg-summary">
                  <span>{contract.option_type.toUpperCase()}</span>
                  <span>${Number.parseFloat(contract.strike).toFixed(2)}</span>
                  <span>exp {contract.expiration}</span>
                  <span>Bid ${Number.parseFloat(contract.bid).toFixed(2)}</span>
                  <span>Ask ${Number.parseFloat(contract.ask).toFixed(2)}</span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="rh-options-trade__actions">
        <Button variant="secondary" disabled={draftLegs.length >= 4} onClick={handleAddLeg} aria-label="Add a new leg to this order">
          Add Leg
        </Button>
        <Button variant="secondary" onClick={() => resetForStrategy(strategy)}>
          Reset Preset
        </Button>
      </div>

      <div className="rh-order-form__summary">
        <div className="rh-order-form__row">
          <span>Leg Count</span>
          <span>{draftLegs.length}</span>
        </div>
        <div className="rh-order-form__row">
          <span>Estimated Net {netPremium >= 0 ? "Debit" : "Credit"}</span>
          <span>${Math.abs(netPremium).toFixed(2)}</span>
        </div>
      </div>

      <Button
        variant="primary"
        disabled={draftLegs.length === 0 || isSubmitting}
        onClick={handleSubmit}
        aria-label="Submit options order"
      >
        {isSubmitting ? "Submitting..." : `Submit ${strategy.replace(/_/g, " ")} Order`}
      </Button>
    </div>
  );
}
