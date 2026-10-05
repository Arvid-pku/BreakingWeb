import type { RouteMutator } from "@breakingweb/shared";

import type {
  AccountSettings,
  DividendEntry,
  LinkedBank,
  Notification,
  OptionsContract,
  OptionsOrder,
  OptionsPosition,
  Order,
  Position,
  PriceAlert,
  RealizedGainLoss,
  RecurringInvestment,
  Referral,
  SecurityEntry,
  Stock,
  TaxDocument,
  Transaction,
  Transfer,
  Watchlist,
} from "./types";

/* ------------------------------------------------------------------ */
/*  RobinhoodFixture — matches the JSON fixture shape                 */
/* ------------------------------------------------------------------ */

export interface RobinhoodFixture {
  env_id: string;
  task_id: string;
  owner_name: string;
  owner_email: string;
  account_type: string;
  cash_balance: string;
  buying_power: string;
  portfolio_value: string;
  instant_deposits_limit: string;
  margin_maintenance: string;
  gold_subscription: boolean;
  day_trade_count: number;
  account_created_at: string;
  positions: Position[];
  orders: Order[];
  options_positions: OptionsPosition[];
  options_orders: OptionsOrder[];
  stocks: Stock[];
  options_chains: Record<string, OptionsContract[]>;
  watchlists: Watchlist[];
  transactions: Transaction[];
  transfers: Transfer[];
  linked_banks: LinkedBank[];
  recurring_investments: RecurringInvestment[];
  tax_documents: TaxDocument[];
  price_alerts: PriceAlert[];
  notifications: Notification[];
  earnings_events: unknown[];
  dividend_schedule: DividendEntry[];
  settings: AccountSettings;
  security_log: SecurityEntry[];
  referral_history: Referral[];
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

let _idCounter = 0;
function genId(prefix: string): string {
  return `${prefix}_${Date.now()}_${++_idCounter}`;
}

/* ------------------------------------------------------------------ */
/*  Route matching                                                    */
/* ------------------------------------------------------------------ */

type Handler = (
  state: RobinhoodFixture,
  params: Record<string, string>,
  body: Record<string, unknown> | undefined,
  query: Record<string, unknown> | undefined,
) => { state: RobinhoodFixture; response: unknown };

interface Route {
  method: string;
  pattern: RegExp;
  paramNames: string[];
  handler: Handler;
}

const routes: Route[] = [];

function route(method: string, pattern: string, handler: Handler) {
  const paramNames: string[] = [];
  const regexStr = pattern.replace(/:(\w+)/g, (_, name) => {
    paramNames.push(name);
    return "([^/]+)";
  });
  routes.push({
    method: method.toUpperCase(),
    pattern: new RegExp(`^${regexStr}$`),
    paramNames,
    handler,
  });
}

function matchRoute(
  method: string,
  path: string,
): { handler: Handler; params: Record<string, string> } | null {
  const upper = method.toUpperCase();
  for (const r of routes) {
    if (r.method !== upper) continue;
    const m = path.match(r.pattern);
    if (m) {
      const params: Record<string, string> = {};
      r.paramNames.forEach((name, i) => { params[name] = m[i + 1]; });
      return { handler: r.handler, params };
    }
  }
  return null;
}

/* ------------------------------------------------------------------ */
/*  Account routes                                                    */
/* ------------------------------------------------------------------ */

route("GET", "account", (state) => ({
  state,
  response: {
    owner_name: state.owner_name,
    owner_email: state.owner_email,
    account_type: state.account_type,
    cash_balance: state.cash_balance,
    buying_power: state.buying_power,
    portfolio_value: state.portfolio_value,
    instant_deposits_limit: state.instant_deposits_limit,
    margin_maintenance: state.margin_maintenance,
    gold_subscription: state.gold_subscription,
    day_trade_count: state.day_trade_count,
    account_created_at: state.account_created_at,
  },
}));

route("GET", "account/portfolio", (state) => {
  let dayChange = 0;
  let totalCost = 0;
  let totalValue = 0;
  for (const p of state.positions) {
    const qty = parseFloat(p.quantity);
    const price = parseFloat(p.current_price);
    const cost = parseFloat(p.avg_cost_basis);
    dayChange += qty * price * parseFloat(p.day_change_pct) / 100;
    totalCost += qty * cost;
    totalValue += qty * price;
  }
  const portfolioVal = totalValue + parseFloat(state.cash_balance);
  const totalReturn = totalValue - totalCost;
  return {
    state,
    response: {
      portfolio_value: portfolioVal.toFixed(2),
      cash_balance: state.cash_balance,
      buying_power: state.buying_power,
      positions: state.positions,
      day_change: dayChange.toFixed(2),
      day_change_pct: portfolioVal > 0 ? ((dayChange / portfolioVal) * 100).toFixed(2) : "0.00",
      total_return: totalReturn.toFixed(2),
      total_return_pct: totalCost > 0 ? ((totalReturn / totalCost) * 100).toFixed(2) : "0.00",
    },
  };
});

/* ------------------------------------------------------------------ */
/*  Positions                                                         */
/* ------------------------------------------------------------------ */

route("GET", "positions", (state) => ({
  state,
  response: { items: state.positions },
}));

route("GET", "positions/:symbol", (state, params) => {
  const pos = state.positions.find((p) => p.symbol === params.symbol);
  if (!pos) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { position: pos } };
});

/* ------------------------------------------------------------------ */
/*  Stocks                                                            */
/* ------------------------------------------------------------------ */

route("GET", "stocks/:symbol", (state, params) => {
  const stock = state.stocks.find((s) => s.symbol === params.symbol);
  if (!stock) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { stock } };
});

route("GET", "stocks/:symbol/chart", (state, params) => {
  const stock = state.stocks.find((s) => s.symbol === params.symbol);
  if (!stock) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { prices: stock.historical_prices } };
});

route("GET", "stocks/:symbol/options", (state, params) => {
  const contracts = state.options_chains[params.symbol] ?? [];
  return { state, response: { contracts } };
});

route("GET", "stocks/:symbol/earnings", (state, params) => {
  const events = (state.earnings_events as Array<{ symbol: string }>).filter(
    (e) => e.symbol === params.symbol,
  );
  return { state, response: { items: events } };
});

route("GET", "stocks/:symbol/dividends", (state, params) => {
  const divs = state.dividend_schedule.filter((d) => d.symbol === params.symbol);
  return { state, response: { items: divs } };
});

/* ------------------------------------------------------------------ */
/*  Search                                                            */
/* ------------------------------------------------------------------ */

route("GET", "search", (state, _params, _body, query) => {
  const q = String(query?.q ?? "").toLowerCase();
  const items = state.stocks.filter(
    (s) => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q),
  );
  return { state, response: { items } };
});

/* ------------------------------------------------------------------ */
/*  Orders                                                            */
/* ------------------------------------------------------------------ */

route("POST", "orders", (state, _params, body) => {
  const symbol = String(body?.symbol ?? "");
  const side = String(body?.side ?? "buy") as "buy" | "sell";
  const orderType = String(body?.order_type ?? "market");
  const quantity = parseFloat(String(body?.quantity ?? "0"));
  const now = new Date().toISOString();

  const stock = state.stocks.find((s) => s.symbol === symbol);
  if (!stock) return { state, response: { error: `Unknown stock: ${symbol}`, status: 400 } };

  const order: Order = {
    id: genId("ord"),
    symbol,
    side,
    order_type: orderType as Order["order_type"],
    quantity: String(quantity),
    filled_quantity: "0",
    limit_price: body?.limit_price ? String(body.limit_price) : null,
    stop_price: body?.stop_price ? String(body.stop_price) : null,
    trail_amount: body?.trail_amount ? String(body.trail_amount) : null,
    trail_pct: body?.trail_pct ? String(body.trail_pct) : null,
    time_in_force: (body?.time_in_force as Order["time_in_force"]) ?? "gfd",
    status: "pending",
    extended_hours: Boolean(body?.extended_hours),
    created_at: now,
    filled_at: null,
    cancelled_at: null,
  };

  // Auto-fill market orders
  if (orderType === "market") {
    const price = parseFloat(stock.price);
    const total = price * quantity;

    if (side === "buy") {
      const cash = parseFloat(state.cash_balance);
      if (total > cash) return { state, response: { error: "Insufficient funds", status: 400 } };
      state.cash_balance = String(cash - total);
      state.buying_power = String(parseFloat(state.buying_power) - total);

      const pos = state.positions.find((p) => p.symbol === symbol);
      if (pos) {
        const newQty = parseFloat(pos.quantity) + quantity;
        pos.avg_cost_basis = String(
          (parseFloat(pos.avg_cost_basis) * parseFloat(pos.quantity) + price * quantity) / newQty,
        );
        pos.quantity = String(newQty);
        pos.current_price = stock.price;
      } else {
        state.positions.push({
          id: genId("pos"),
          symbol,
          name: stock.name,
          asset_type: stock.asset_type,
          quantity: String(quantity),
          avg_cost_basis: stock.price,
          current_price: stock.price,
          day_change_pct: stock.day_change_pct,
          total_return: "0",
          total_return_pct: "0",
          lots: [{ shares: String(quantity), cost_per_share: stock.price, acquired_date: now.slice(0, 10) }],
        });
      }
    } else {
      const pos = state.positions.find((p) => p.symbol === symbol);
      if (!pos || parseFloat(pos.quantity) < quantity) {
        return { state, response: { error: "Insufficient shares", status: 400 } };
      }
      state.cash_balance = String(parseFloat(state.cash_balance) + total);
      state.buying_power = String(parseFloat(state.buying_power) + total);
      const newQty = parseFloat(pos.quantity) - quantity;
      if (newQty <= 0) {
        state.positions = state.positions.filter((p) => p.symbol !== symbol);
      } else {
        pos.quantity = String(newQty);
      }
    }

    order.status = "filled";
    order.filled_quantity = String(quantity);
    order.filled_at = now;

    state.transactions.push({
      id: genId("txn"),
      type: side,
      symbol,
      quantity: String(quantity),
      amount: String(total),
      description: `Market ${side} ${quantity} shares of ${symbol} @ $${price}`,
      timestamp: now,
    });

    state.notifications.push({
      id: genId("notif"),
      type: "order_fill",
      title: `Order Filled: ${symbol}`,
      message: `Your market ${side} order for ${quantity} shares of ${symbol} was filled at $${price}.`,
      timestamp: now,
      is_read: false,
      action_url: null,
    });
  }

  state.orders.push(order);
  return { state, response: { order } };
});

route("GET", "orders", (state, _params, _body, query) => {
  let items = [...state.orders];
  if (query?.status) {
    items = items.filter((o) => o.status === String(query.status));
  }
  items.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return { state, response: { items } };
});

route("GET", "orders/:order_id", (state, params) => {
  const order = state.orders.find((o) => o.id === params.order_id);
  if (!order) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { order } };
});

route("POST", "orders/:order_id/cancel", (state, params) => {
  const order = state.orders.find((o) => o.id === params.order_id);
  if (!order) return { state, response: { error: "Not found", status: 404 } };
  if (order.status !== "pending" && order.status !== "partially_filled") {
    return { state, response: { error: `Cannot cancel order with status: ${order.status}`, status: 400 } };
  }
  order.status = "cancelled";
  order.cancelled_at = new Date().toISOString();
  return { state, response: { order } };
});

/* ------------------------------------------------------------------ */
/*  Options orders                                                    */
/* ------------------------------------------------------------------ */

route("POST", "options/orders", (state, _params, body) => {
  const order: OptionsOrder = {
    id: genId("oord"),
    strategy: String(body?.strategy ?? "single"),
    legs: (body?.legs as OptionsOrder["legs"]) ?? [],
    status: "pending",
    created_at: new Date().toISOString(),
    filled_at: null,
  };
  state.options_orders.push(order);
  return { state, response: { order } };
});

route("GET", "options/orders", (state) => ({
  state,
  response: { items: state.options_orders },
}));

route("GET", "options/orders/:order_id", (state, params) => {
  const order = state.options_orders.find((o) => o.id === params.order_id);
  if (!order) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { order } };
});

route("GET", "options/positions", (state) => ({
  state,
  response: { items: state.options_positions },
}));

/* ------------------------------------------------------------------ */
/*  Watchlists                                                        */
/* ------------------------------------------------------------------ */

route("GET", "watchlists", (state) => ({
  state,
  response: { items: state.watchlists },
}));

route("POST", "watchlists", (state, _params, body) => {
  const wl: Watchlist = {
    id: genId("wl"),
    name: String(body?.name ?? ""),
    symbols: (body?.symbols as string[]) ?? [],
    created_at: new Date().toISOString(),
  };
  state.watchlists.push(wl);
  return { state, response: { watchlist: wl } };
});

route("PUT", "watchlists/:watchlist_id", (state, params, body) => {
  const wl = state.watchlists.find((w) => w.id === params.watchlist_id);
  if (!wl) return { state, response: { error: "Not found", status: 404 } };
  if (body?.name) wl.name = String(body.name);
  return { state, response: { watchlist: wl } };
});

route("DELETE", "watchlists/:watchlist_id", (state, params) => {
  const idx = state.watchlists.findIndex((w) => w.id === params.watchlist_id);
  if (idx === -1) return { state, response: { error: "Not found", status: 404 } };
  const wl = state.watchlists.splice(idx, 1)[0];
  return { state, response: { watchlist: wl } };
});

route("POST", "watchlists/:watchlist_id/symbols", (state, params, body) => {
  const wl = state.watchlists.find((w) => w.id === params.watchlist_id);
  if (!wl) return { state, response: { error: "Not found", status: 404 } };
  const symbol = String(body?.symbol ?? "");
  if (symbol && !wl.symbols.includes(symbol)) wl.symbols.push(symbol);
  return { state, response: { watchlist: wl } };
});

route("DELETE", "watchlists/:watchlist_id/symbols/:symbol", (state, params) => {
  const wl = state.watchlists.find((w) => w.id === params.watchlist_id);
  if (!wl) return { state, response: { error: "Not found", status: 404 } };
  wl.symbols = wl.symbols.filter((s) => s !== params.symbol);
  return { state, response: { watchlist: wl } };
});

/* ------------------------------------------------------------------ */
/*  Transfers & Banks                                                 */
/* ------------------------------------------------------------------ */

route("GET", "transfers", (state) => ({
  state,
  response: { items: state.transfers },
}));

route("POST", "transfers", (state, _params, body) => {
  const direction = String(body?.direction ?? "deposit") as "deposit" | "withdrawal";
  const amount = parseFloat(String(body?.amount ?? "0"));
  const bankId = String(body?.bank_account_id ?? "");
  const bank = state.linked_banks.find((b) => b.id === bankId);
  if (!bank) return { state, response: { error: "Unknown bank account", status: 400 } };

  const now = new Date().toISOString();
  if (direction === "deposit") {
    state.cash_balance = String(parseFloat(state.cash_balance) + amount);
    state.buying_power = String(parseFloat(state.buying_power) + amount);
  } else {
    if (amount > parseFloat(state.cash_balance)) {
      return { state, response: { error: "Insufficient funds for withdrawal", status: 400 } };
    }
    state.cash_balance = String(parseFloat(state.cash_balance) - amount);
    state.buying_power = String(parseFloat(state.buying_power) - amount);
  }

  const transfer: Transfer = {
    id: genId("xfer"),
    direction,
    amount: String(amount),
    status: "pending",
    bank_account_id: bankId,
    initiated_at: now,
    completed_at: null,
    expected_date: null,
  };
  state.transfers.push(transfer);

  state.transactions.push({
    id: genId("txn"),
    type: direction,
    symbol: null,
    quantity: null,
    amount: String(amount),
    description: `${direction === "deposit" ? "Deposit from" : "Withdrawal to"} ${bank.bank_name} ****${bank.last_four}`,
    timestamp: now,
  });

  return { state, response: { transfer } };
});

route("GET", "banks", (state) => ({
  state,
  response: { items: state.linked_banks },
}));

route("POST", "banks", (state, _params, body) => {
  const bank: LinkedBank = {
    id: genId("bank"),
    bank_name: String(body?.bank_name ?? ""),
    account_type: (body?.account_type as "checking" | "savings") ?? "checking",
    last_four: String(body?.last_four ?? "0000"),
    status: "verified",
    is_default: state.linked_banks.length === 0,
  };
  state.linked_banks.push(bank);
  return { state, response: { bank } };
});

route("DELETE", "banks/:bank_id", (state, params) => {
  const idx = state.linked_banks.findIndex((b) => b.id === params.bank_id);
  if (idx === -1) return { state, response: { error: "Not found", status: 404 } };
  const bank = state.linked_banks.splice(idx, 1)[0];
  return { state, response: { bank } };
});

/* ------------------------------------------------------------------ */
/*  Recurring investments                                             */
/* ------------------------------------------------------------------ */

route("GET", "recurring", (state) => ({
  state,
  response: { items: state.recurring_investments },
}));

route("POST", "recurring", (state, _params, body) => {
  const ri: RecurringInvestment = {
    id: genId("ri"),
    symbol: String(body?.symbol ?? ""),
    amount: String(body?.amount ?? "0"),
    frequency: (body?.frequency as RecurringInvestment["frequency"]) ?? "weekly",
    next_execution_date: String(body?.next_execution_date ?? new Date().toISOString().slice(0, 10)),
    status: "active",
    history: [],
  };
  state.recurring_investments.push(ri);
  return { state, response: { recurring: ri } };
});

route("PUT", "recurring/:ri_id", (state, params, body) => {
  const ri = state.recurring_investments.find((r) => r.id === params.ri_id);
  if (!ri) return { state, response: { error: "Not found", status: 404 } };
  if (body?.amount !== undefined) ri.amount = String(body.amount);
  if (body?.frequency !== undefined) ri.frequency = body.frequency as RecurringInvestment["frequency"];
  if (body?.status !== undefined) ri.status = body.status as "active" | "paused";
  return { state, response: { recurring: ri } };
});

route("DELETE", "recurring/:ri_id", (state, params) => {
  const idx = state.recurring_investments.findIndex((r) => r.id === params.ri_id);
  if (idx === -1) return { state, response: { error: "Not found", status: 404 } };
  const ri = state.recurring_investments.splice(idx, 1)[0];
  return { state, response: { recurring: ri } };
});

/* ------------------------------------------------------------------ */
/*  Transactions                                                      */
/* ------------------------------------------------------------------ */

route("GET", "transactions", (state, _params, _body, query) => {
  let items = [...state.transactions];
  if (query?.type) items = items.filter((t) => t.type === String(query.type));
  if (query?.symbol) items = items.filter((t) => t.symbol === String(query.symbol));
  items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  return { state, response: { items } };
});

/* ------------------------------------------------------------------ */
/*  Tax                                                               */
/* ------------------------------------------------------------------ */

route("GET", "tax/documents", (state, _params, _body, query) => {
  let items = [...state.tax_documents];
  if (query?.year) items = items.filter((d) => d.tax_year === Number(query.year));
  return { state, response: { items } };
});

route("GET", "tax/documents/:doc_id", (state, params) => {
  const doc = state.tax_documents.find((d) => d.id === params.doc_id);
  if (!doc) return { state, response: { error: "Not found", status: 404 } };
  return { state, response: { document: doc } };
});

route("GET", "tax/gains", (state, _params, _body, query) => {
  let items: RealizedGainLoss[] = [];
  for (const doc of state.tax_documents) {
    if (query?.year && doc.tax_year !== Number(query.year)) continue;
    items.push(...doc.realized_gains);
  }
  return { state, response: { items } };
});

/* ------------------------------------------------------------------ */
/*  Notifications                                                     */
/* ------------------------------------------------------------------ */

route("GET", "notifications", (state) => ({
  state,
  response: { items: state.notifications },
}));

route("POST", "notifications/:notification_id/read", (state, params) => {
  const notif = state.notifications.find((n) => n.id === params.notification_id);
  if (!notif) return { state, response: { error: "Not found", status: 404 } };
  notif.is_read = true;
  return { state, response: { notification: notif } };
});

route("POST", "notifications/read-all", (state) => {
  let count = 0;
  for (const n of state.notifications) {
    if (!n.is_read) { n.is_read = true; count++; }
  }
  return { state, response: { count } };
});

/* ------------------------------------------------------------------ */
/*  Alerts                                                            */
/* ------------------------------------------------------------------ */

route("GET", "alerts", (state) => ({
  state,
  response: { items: state.price_alerts },
}));

route("POST", "alerts", (state, _params, body) => {
  const alert: PriceAlert = {
    id: genId("alert"),
    symbol: String(body?.symbol ?? ""),
    condition: (body?.condition as "above" | "below") ?? "above",
    target_price: String(body?.target_price ?? "0"),
    status: "active",
    created_at: new Date().toISOString(),
    triggered_at: null,
  };
  state.price_alerts.push(alert);
  return { state, response: { alert } };
});

route("DELETE", "alerts/:alert_id", (state, params) => {
  const idx = state.price_alerts.findIndex((a) => a.id === params.alert_id);
  if (idx === -1) return { state, response: { error: "Not found", status: 404 } };
  const alert = state.price_alerts.splice(idx, 1)[0];
  return { state, response: { alert } };
});

/* ------------------------------------------------------------------ */
/*  Dividends                                                         */
/* ------------------------------------------------------------------ */

route("GET", "dividends", (state) => ({
  state,
  response: { items: state.dividend_schedule },
}));

/* ------------------------------------------------------------------ */
/*  Settings                                                          */
/* ------------------------------------------------------------------ */

route("GET", "settings", (state) => ({
  state,
  response: { settings: state.settings },
}));

route("PUT", "settings", (state, _params, body) => {
  if (body) {
    const keys: (keyof AccountSettings)[] = [
      "display_theme", "default_order_type", "reinvest_dividends",
      "extended_hours_enabled", "biometric_login", "two_factor_method",
      "notification_prefs",
    ];
    for (const key of keys) {
      if (body[key] !== undefined && body[key] !== null) {
        (state.settings as unknown as Record<string, unknown>)[key] = body[key];
      }
    }
  }
  return { state, response: { settings: state.settings } };
});

/* ------------------------------------------------------------------ */
/*  Security                                                          */
/* ------------------------------------------------------------------ */

route("GET", "security/log", (state) => ({
  state,
  response: { items: state.security_log },
}));

route("PUT", "security/2fa", (state, _params, body) => {
  const method = String(body?.method ?? "none") as "sms" | "authenticator" | "none";
  state.settings.two_factor_method = method;
  state.security_log.push({
    event: "2fa_change",
    device: "web",
    ip_address: "0.0.0.0",
    location: "Unknown",
    timestamp: new Date().toISOString(),
  });
  return { state, response: { settings: state.settings } };
});

/* ------------------------------------------------------------------ */
/*  Referrals                                                         */
/* ------------------------------------------------------------------ */

route("GET", "referrals", (state) => ({
  state,
  response: { items: state.referral_history },
}));

/* ------------------------------------------------------------------ */
/*  Exported mutator                                                  */
/* ------------------------------------------------------------------ */

export const robinhoodMutator: RouteMutator<RobinhoodFixture> = (
  state,
  method,
  path,
  body,
  query,
) => {
  const cleanPath = path.replace(/^\//, "");
  const match = matchRoute(method, cleanPath);
  if (!match) {
    return { state, response: { error: `No route: ${method} /${cleanPath}`, status: 404 } };
  }
  return match.handler(
    state,
    match.params,
    body as Record<string, unknown> | undefined,
    query,
  );
};
