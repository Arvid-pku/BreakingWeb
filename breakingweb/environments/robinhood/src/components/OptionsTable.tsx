import type { OptionsContract } from "../types";

interface OptionsTableProps {
  contracts: OptionsContract[];
  optionType: "call" | "put";
  onSelect?: (contract: OptionsContract) => void;
}

export function OptionsTable({ contracts, optionType, onSelect }: OptionsTableProps) {
  const filtered = contracts.filter((c) => c.option_type === optionType);

  if (filtered.length === 0) {
    return <div className="rh-options-table__empty">No {optionType} options available</div>;
  }

  return (
    <table className="rh-options-table" aria-label={`${optionType} options`}>
      <thead>
        <tr>
          <th>Strike</th>
          <th>Bid</th>
          <th>Ask</th>
          <th>Last</th>
          <th>Vol</th>
          <th>OI</th>
          <th>IV</th>
          <th>Delta</th>
        </tr>
      </thead>
      <tbody>
        {filtered.map((c) => (
          <tr
            key={c.contract_id}
            className="rh-options-table__row"
            onClick={() => onSelect?.(c)}
            role={onSelect ? "button" : undefined}
            tabIndex={onSelect ? 0 : undefined}
            aria-label={`${optionType} strike ${c.strike}`}
          >
            <td className="rh-options-table__strike">${parseFloat(c.strike).toFixed(2)}</td>
            <td>${parseFloat(c.bid).toFixed(2)}</td>
            <td>${parseFloat(c.ask).toFixed(2)}</td>
            <td>${parseFloat(c.last_price).toFixed(2)}</td>
            <td>{c.volume.toLocaleString()}</td>
            <td>{c.open_interest.toLocaleString()}</td>
            <td>{(parseFloat(c.implied_volatility) * 100).toFixed(1)}%</td>
            <td>{parseFloat(c.greeks.delta).toFixed(3)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
