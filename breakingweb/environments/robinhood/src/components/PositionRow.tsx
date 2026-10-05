import { Link, useLocation } from "react-router-dom";
import { preserveQueryParams } from "@breakingweb/shared";

import type { Position } from "../types";
import { Sparkline } from "./Sparkline";

interface PositionRowProps {
  position: Position;
}

export function PositionRow({ position }: PositionRowProps) {
  const location = useLocation();
  const price = parseFloat(position.current_price);
  const changePct = parseFloat(position.day_change_pct);
  const totalReturn = parseFloat(position.total_return);
  const totalReturnPct = parseFloat(position.total_return_pct);
  const qty = parseFloat(position.quantity);
  const isPositive = changePct >= 0;
  const isReturnPositive = totalReturn >= 0;

  // Fake sparkline data from the position
  const fakeData = Array.from({ length: 20 }, (_, i) =>
    price * (1 + (Math.sin(i * 0.5 + price) * 0.02 * (isPositive ? 1 : -1))),
  );

  return (
    <Link
      to={preserveQueryParams(`/stocks/${position.symbol}`, location.search)}
      className="rh-position-row"
      aria-label={`${position.symbol} position`}
    >
      <div className="rh-position-row__info">
        <span className="rh-position-row__symbol">{position.symbol}</span>
        <span className="rh-position-row__shares">{qty} {qty === 1 ? "Share" : "Shares"}</span>
      </div>
      <div className="rh-position-row__chart">
        <Sparkline data={fakeData} positive={isPositive} />
      </div>
      <div className="rh-position-row__values">
        <span className="rh-position-row__price">${price.toFixed(2)}</span>
        <span className={`rh-position-row__change ${isReturnPositive ? "rh-gain" : "rh-loss"}`}>
          {isReturnPositive ? "+" : ""}${totalReturn.toFixed(2)} ({isReturnPositive ? "+" : ""}{totalReturnPct.toFixed(2)}%)
        </span>
      </div>
    </Link>
  );
}
