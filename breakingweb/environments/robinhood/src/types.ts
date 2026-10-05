/* TypeScript interfaces mirroring Pydantic models from backend/models/robinhood.py */

export interface HistoricalPrice {
  date: string;
  close: string;
}

export interface TaxLot {
  shares: string;
  cost_per_share: string;
  acquired_date: string;
}

export interface Position {
  id: string;
  symbol: string;
  name: string;
  asset_type: "stock" | "etf" | "crypto" | "option";
  quantity: string;
  avg_cost_basis: string;
  current_price: string;
  day_change_pct: string;
  total_return: string;
  total_return_pct: string;
  lots: TaxLot[];
}

export interface Order {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  order_type: "market" | "limit" | "stop" | "stop_limit" | "trailing_stop";
  quantity: string;
  filled_quantity: string;
  limit_price: string | null;
  stop_price: string | null;
  trail_amount: string | null;
  trail_pct: string | null;
  time_in_force: "gfd" | "gtc" | "ioc" | "opg";
  status: "pending" | "partially_filled" | "filled" | "cancelled" | "rejected";
  extended_hours: boolean;
  created_at: string;
  filled_at: string | null;
  cancelled_at: string | null;
}

export interface Stock {
  symbol: string;
  name: string;
  asset_type: "stock" | "etf";
  price: string;
  previous_close: string;
  day_change: string;
  day_change_pct: string;
  bid: string;
  ask: string;
  bid_size: number;
  ask_size: number;
  volume: number;
  avg_volume: number;
  market_cap: string | null;
  pe_ratio: string | null;
  eps: string | null;
  dividend_yield: string | null;
  fifty_two_week_high: string;
  fifty_two_week_low: string;
  sector: string;
  industry: string;
  about: string;
  historical_prices: HistoricalPrice[];
}

export interface Greeks {
  delta: string;
  gamma: string;
  theta: string;
  vega: string;
}

export interface OptionsContract {
  contract_id: string;
  underlying: string;
  option_type: "call" | "put";
  strike: string;
  expiration: string;
  bid: string;
  ask: string;
  last_price: string;
  volume: number;
  open_interest: number;
  implied_volatility: string;
  greeks: Greeks;
}

export interface OptionsPosition {
  id: string;
  contract_id: string;
  underlying_symbol: string;
  position_side: "long" | "short";
  option_type: "call" | "put";
  strike_price: string;
  expiration_date: string;
  quantity: number;
  avg_cost: string;
  current_premium: string;
  greeks: Greeks;
  status: "open" | "closed" | "exercised" | "expired";
}

export interface OptionsLeg {
  side: "buy" | "sell";
  option_type: "call" | "put";
  strike: string;
  expiration: string;
  quantity: number;
  premium: string;
}

export interface OptionsOrder {
  id: string;
  strategy: string;
  legs: OptionsLeg[];
  status: "pending" | "filled" | "cancelled" | "rejected";
  created_at: string;
  filled_at: string | null;
}

export interface Watchlist {
  id: string;
  name: string;
  symbols: string[];
  created_at: string;
}

export interface Transfer {
  id: string;
  direction: "deposit" | "withdrawal";
  amount: string;
  status: "pending" | "completed" | "failed" | "reversed";
  bank_account_id: string;
  initiated_at: string;
  completed_at: string | null;
  expected_date: string | null;
}

export interface LinkedBank {
  id: string;
  bank_name: string;
  account_type: "checking" | "savings";
  last_four: string;
  status: "verified" | "pending";
  is_default: boolean;
}

export interface RecurringExecution {
  date: string;
  amount: string;
  shares_bought: string;
  price: string;
}

export interface RecurringInvestment {
  id: string;
  symbol: string;
  amount: string;
  frequency: "daily" | "weekly" | "biweekly" | "monthly";
  next_execution_date: string;
  status: "active" | "paused";
  history: RecurringExecution[];
}

export interface Transaction {
  id: string;
  type: string;
  symbol: string | null;
  quantity: string | null;
  amount: string;
  description: string;
  timestamp: string;
}

export interface RealizedGainLoss {
  symbol: string;
  buy_date: string;
  sell_date: string;
  proceeds: string;
  cost_basis: string;
  gain_loss: string;
  wash_sale: boolean;
  holding_period: "short" | "long";
}

export interface TaxDocument {
  id: string;
  type: string;
  tax_year: number;
  available_date: string;
  realized_gains: RealizedGainLoss[];
}

export interface PriceAlert {
  id: string;
  symbol: string;
  condition: "above" | "below";
  target_price: string;
  status: "active" | "triggered";
  created_at: string;
  triggered_at: string | null;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  timestamp: string;
  is_read: boolean;
  action_url: string | null;
}

export interface EarningsEvent {
  symbol: string;
  date: string;
  time: "before_market" | "after_market";
  eps_estimate: string | null;
  eps_actual: string | null;
  revenue_estimate: string | null;
  revenue_actual: string | null;
}

export interface DividendEntry {
  symbol: string;
  ex_date: string;
  pay_date: string;
  amount_per_share: string;
  estimated_total: string;
  status: "upcoming" | "paid";
}

export interface AccountSettings {
  id?: string;
  display_theme: "light" | "dark";
  default_order_type: "market" | "limit";
  reinvest_dividends: boolean;
  extended_hours_enabled: boolean;
  biometric_login: boolean;
  two_factor_method: "sms" | "authenticator" | "none";
  notification_prefs: Record<string, boolean>;
}

export interface SecurityEntry {
  event: string;
  device: string;
  ip_address: string;
  location: string;
  timestamp: string;
}

export interface Referral {
  referred_name: string;
  status: "pending" | "completed";
  reward_stock: string;
  reward_value: string;
  date: string;
}

export interface AccountData {
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
}

export interface PortfolioData {
  portfolio_value: string;
  cash_balance: string;
  buying_power: string;
  positions: Position[];
  day_change: string;
  day_change_pct: string;
  total_return: string;
  total_return_pct: string;
}

export interface PriceData {
  price: string;
  day_change: string;
  day_change_pct: string;
  bid: string;
  ask: string;
}

export interface PricesResponse {
  tick: number;
  prices: Record<string, PriceData>;
  portfolio_value: string;
  cash_balance: string;
  pending_orders_filled: string[];
}
