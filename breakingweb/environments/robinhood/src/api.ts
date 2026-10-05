import type { ApiRequestOptions } from "@breakingweb/shared";

import type {
  AccountData,
  AccountSettings,
  DividendEntry,
  EarningsEvent,
  LinkedBank,
  Notification,
  OptionsContract,
  OptionsOrder,
  OptionsPosition,
  Order,
  PortfolioData,
  Position,
  PriceAlert,
  PricesResponse,
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

type RequestFn = <T>(path: string, options?: ApiRequestOptions) => Promise<T>;

export function createRobinhoodApi(request: RequestFn) {
  return {
    /* Live Prices */
    getPrices: () =>
      request<PricesResponse>("prices"),

    /* Account */
    getAccount: () =>
      request<AccountData>("account"),
    getPortfolio: () =>
      request<PortfolioData>("account/portfolio"),

    /* Positions */
    listPositions: () =>
      request<{ items: Position[] }>("positions").then((r) => r.items),
    getPosition: (symbol: string) =>
      request<{ position: Position }>(`positions/${symbol}`).then((r) => r.position),

    /* Stocks */
    getStock: (symbol: string) =>
      request<{ stock: Stock }>(`stocks/${symbol}`).then((r) => r.stock),
    getStockChart: (symbol: string, query?: Record<string, string>) =>
      request<{ prices: Array<{ date: string; close: string }> }>(`stocks/${symbol}/chart`, { query }),
    getStockEarnings: (symbol: string) =>
      request<{ items: EarningsEvent[] }>(`stocks/${symbol}/earnings`).then((r) => r.items),
    searchStocks: (q: string) =>
      request<{ items: Stock[] }>("search", { query: { q } }).then((r) => r.items),

    /* Orders */
    placeOrder: (body: {
      symbol: string;
      side: "buy" | "sell";
      order_type?: string;
      quantity: number;
      limit_price?: number;
      stop_price?: number;
      trail_amount?: number;
      trail_pct?: number;
      time_in_force?: string;
      extended_hours?: boolean;
    }) =>
      request<{ order: Order }>("orders", { method: "POST", body }).then((r) => r.order),
    listOrders: (query?: Record<string, string>) =>
      request<{ items: Order[] }>("orders", { query }).then((r) => r.items),
    cancelOrder: (orderId: string) =>
      request<{ order: Order }>(`orders/${orderId}/cancel`, { method: "POST" }).then((r) => r.order),

    /* Options */
    getOptionsChain: (symbol: string) =>
      request<{ contracts: OptionsContract[] }>(`stocks/${symbol}/options`).then((r) => r.contracts),
    placeOptionsOrder: (body: { strategy: string; legs: Array<Record<string, unknown>> }) =>
      request<{ order: OptionsOrder }>("options/orders", { method: "POST", body }).then((r) => r.order),
    listOptionsOrders: () =>
      request<{ items: OptionsOrder[] }>("options/orders").then((r) => r.items),
    getOptionsPositions: () =>
      request<{ items: OptionsPosition[] }>("options/positions").then((r) => r.items),

    /* Watchlists */
    listWatchlists: () =>
      request<{ items: Watchlist[] }>("watchlists").then((r) => r.items),
    createWatchlist: (name: string, symbols?: string[]) =>
      request<{ watchlist: Watchlist }>("watchlists", { method: "POST", body: { name, symbols } }).then((r) => r.watchlist),
    addToWatchlist: (watchlistId: string, symbol: string) =>
      request<{ watchlist: Watchlist }>(`watchlists/${watchlistId}/symbols`, { method: "POST", body: { symbol } }).then((r) => r.watchlist),
    removeFromWatchlist: (watchlistId: string, symbol: string) =>
      request<{ watchlist: Watchlist }>(`watchlists/${watchlistId}/symbols/${symbol}`, { method: "DELETE" }).then((r) => r.watchlist),
    deleteWatchlist: (watchlistId: string) =>
      request<{ watchlist: Watchlist }>(`watchlists/${watchlistId}`, { method: "DELETE" }).then((r) => r.watchlist),

    /* Transfers */
    listTransfers: () =>
      request<{ items: Transfer[] }>("transfers").then((r) => r.items),
    initiateTransfer: (body: { direction: "deposit" | "withdrawal"; amount: number; bank_account_id: string }) =>
      request<{ transfer: Transfer }>("transfers", { method: "POST", body }).then((r) => r.transfer),
    listBanks: () =>
      request<{ items: LinkedBank[] }>("banks").then((r) => r.items),

    /* Recurring */
    listRecurring: () =>
      request<{ items: RecurringInvestment[] }>("recurring").then((r) => r.items),
    createRecurring: (body: { symbol: string; amount: number; frequency: string; next_execution_date: string }) =>
      request<{ recurring: RecurringInvestment }>("recurring", { method: "POST", body }).then((r) => r.recurring),
    updateRecurring: (riId: string, body: Record<string, unknown>) =>
      request<{ recurring: RecurringInvestment }>(`recurring/${riId}`, { method: "PUT", body }).then((r) => r.recurring),
    deleteRecurring: (riId: string) =>
      request<{ recurring: RecurringInvestment }>(`recurring/${riId}`, { method: "DELETE" }).then((r) => r.recurring),

    /* Transactions */
    listTransactions: (query?: Record<string, string>) =>
      request<{ items: Transaction[] }>("transactions", { query }).then((r) => r.items),

    /* Tax */
    listTaxDocuments: (query?: Record<string, string>) =>
      request<{ items: TaxDocument[] }>("tax/documents", { query }).then((r) => r.items),
    getTaxDocument: (docId: string) =>
      request<TaxDocument>(`tax/documents/${docId}`),
    listRealizedGains: (query?: Record<string, string>) =>
      request<{ items: RealizedGainLoss[] }>("tax/gains", { query }).then((r) => r.items),

    /* Notifications */
    listNotifications: () =>
      request<{ items: Notification[] }>("notifications").then((r) => r.items),
    markNotificationRead: (notificationId: string) =>
      request<{ notification: Notification }>(`notifications/${notificationId}/read`, { method: "POST" }).then((r) => r.notification),
    markAllNotificationsRead: () =>
      request<{ count: number }>("notifications/read-all", { method: "POST" }),

    /* Alerts */
    listAlerts: () =>
      request<{ items: PriceAlert[] }>("alerts").then((r) => r.items),
    createAlert: (body: { symbol: string; condition: "above" | "below"; target_price: number }) =>
      request<{ alert: PriceAlert }>("alerts", { method: "POST", body }).then((r) => r.alert),
    deleteAlert: (alertId: string) =>
      request<{ alert: PriceAlert }>(`alerts/${alertId}`, { method: "DELETE" }).then((r) => r.alert),

    /* Dividends */
    listDividends: () =>
      request<{ items: DividendEntry[] }>("dividends").then((r) => r.items),

    /* Settings */
    getSettings: () =>
      request<AccountSettings>("settings"),
    updateSettings: (body: Partial<AccountSettings>) =>
      request<AccountSettings>("settings", { method: "PUT", body }),

    /* Security */
    getSecurityLog: () =>
      request<{ items: SecurityEntry[] }>("security/log").then((r) => r.items),
    update2FA: (method: "sms" | "authenticator" | "none") =>
      request<AccountSettings>("security/2fa", { method: "PUT", body: { method } }),

    /* Referrals */
    listReferrals: () =>
      request<{ items: Referral[] }>("referrals").then((r) => r.items),
  };
}
