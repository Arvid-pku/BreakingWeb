import type { ApiRequestOptions } from "@breakingweb/shared";

import type {
  AmazonAccount,
  Address,
  AmazonSettings,
  CartItem,
  CartSummary,
  GiftCard,
  Notification,
  Order,
  PaymentMethod,
  Product,
  ProductQuestion,
  PromoCode,
  ReturnRequest,
  Review,
  SearchResult,
} from "./types";

type RequestFn = <T>(path: string, options?: ApiRequestOptions) => Promise<T>;

export function createAmazonApi(request: RequestFn) {
  return {
    /* ── Auth ── */
    login: (email: string, password: string) =>
      request<{ success: boolean; user: { name: string; email: string } }>("login", {
        method: "POST",
        body: { email, password },
      }),
    logout: () =>
      request<{ success: boolean }>("logout", { method: "POST" }),

    /* ── Products ── */
    getProducts: (query?: Record<string, unknown>) =>
      request<SearchResult>("products", { query }),
    searchProducts: (q: string, query?: Record<string, unknown>) =>
      request<SearchResult>("search", { query: { q, ...(query ?? {}) } }),
    getProduct: (productId: string) =>
      request<{ product: Product }>(`products/${productId}`).then((r) => r.product),
    getFeaturedProducts: () =>
      request<{ items: Product[] }>("products/featured").then((r) => r.items ?? []),
    getCategories: () =>
      request<{ items: { category: string }[] }>("categories").then((r) => (r.items ?? []).map((c) => c.category)),
    getDeals: (query?: Record<string, unknown>) =>
      request<SearchResult>("deals", { query }),
    getBrowsingHistory: () =>
      request<{ items: Product[] }>("browsing-history").then((r) => r.items ?? []),

    /* ── Cart ── */
    getCart: () =>
      request<Omit<CartSummary, "item_count">>("cart").then((r) => ({
        ...r,
        items: r.items ?? [],
        totals: r.totals ?? { subtotal: 0, shipping: 0, tax: 0, discount: 0, gift_card_applied: 0, total: 0 },
        item_count: (r.items ?? []).reduce((sum, item) => sum + (item.quantity ?? 1), 0),
      })),
    addToCart: (productId: string, quantity: number, variantSelections?: Record<string, string>) =>
      request<{ cart_item: CartItem }>("cart/add", {
        method: "POST",
        body: { product_id: productId, quantity, variant_selections: variantSelections ?? {} },
      }).then((r) => r.cart_item),
    updateCartItem: (itemId: string, quantity: number) =>
      request<{ cart_item: CartItem }>(`cart/${itemId}`, {
        method: "PUT",
        body: { quantity },
      }).then((r) => r.cart_item),
    removeFromCart: (itemId: string) =>
      request<{ cart_item: CartItem }>(`cart/${itemId}`, { method: "DELETE" }).then((r) => r.cart_item),

    /* ── Orders ── */
    placeOrder: (addressId: string, paymentMethodId: string, promoCode?: string | null) =>
      request<{ order: Order }>("checkout", {
        method: "POST",
        body: { shipping_address_id: addressId, payment_method_id: paymentMethodId, promo_code: promoCode ?? null },
      }).then((r) => r.order),
    getOrders: () =>
      request<{ items: Order[] }>("orders").then((r) => r.items ?? []),
    getOrder: (orderId: string) =>
      request<{ order: Order }>(`orders/${orderId}`).then((r) => r.order),
    updateOrderStatus: (orderId: string, status: string) =>
      request<{ order: Order }>(`orders/${orderId}/status`, {
        method: "PUT",
        body: { status },
      }).then((r) => r.order),
    cancelOrder: (orderId: string) =>
      request<{ order: Order }>(`orders/${orderId}/cancel`, {
        method: "POST",
      }).then((r) => r.order),

    /* ── Returns ── */
    getReturns: () =>
      request<{ items: ReturnRequest[] }>("returns").then((r) => r.items ?? []),
    createReturn: (orderId: string, itemIndex: number, reason: string) =>
      request<{ return: ReturnRequest }>("returns", {
        method: "POST",
        body: { order_id: orderId, order_item_index: itemIndex, reason },
      }).then((r) => r.return),
    getReturn: (id: string) =>
      request<{ return: ReturnRequest }>(`returns/${id}`).then((r) => r.return),
    updateReturn: (id: string, status: string) =>
      request<{ return: ReturnRequest }>(`returns/${id}`, {
        method: "PUT",
        body: { status },
      }).then((r) => r.return),

    /* ── Promo Codes ── */
    applyPromo: (code: string) =>
      request<{ promo: PromoCode }>("promo/apply", {
        method: "POST",
        body: { code },
      }).then((r) => r.promo),
    clearPromo: () =>
      request<{ ok: boolean }>("promo/clear", { method: "POST" }).then(() => undefined),
    validatePromo: (code: string) =>
      request<{ valid: boolean; promo?: PromoCode }>(`promo/validate/${code}`),

    /* ── Questions & Answers ── */
    getQuestions: (productId: string) =>
      request<{ items: ProductQuestion[] }>(`products/${productId}/questions`).then((r) => r.items ?? []),
    askQuestion: (productId: string, question: string) =>
      request<{ question: ProductQuestion }>(`products/${productId}/questions`, {
        method: "POST",
        body: { question },
      }).then((r) => r.question),
    answerQuestion: (productId: string, questionId: string, answer: string) =>
      request<{ question: ProductQuestion }>(`products/${productId}/questions/${questionId}/answer`, {
        method: "POST",
        body: { answer },
      }).then((r) => r.question),

    /* ── Gift Cards ── */
    getGiftCards: () =>
      request<{ items: GiftCard[] }>("gift-cards").then((r) => r.items ?? []),
    addGiftCard: (code: string, amount: number) =>
      request<{ gift_card: GiftCard }>("gift-cards/add", {
        method: "POST",
        body: { code, amount },
      }).then((r) => r.gift_card),
    redeemGiftCard: (id: string) =>
      request<{ gift_card: GiftCard }>(`gift-cards/${id}/redeem`, {
        method: "POST",
      }).then((r) => r.gift_card),

    /* ── Notifications ── */
    getNotifications: (unreadOnly?: boolean) =>
      request<{ items: Notification[] }>("notifications", {
        query: unreadOnly ? { unread_only: "true" } : undefined,
      }).then((r) => r.items ?? []),
    markNotificationRead: (id: string) =>
      request<{ notification: Notification }>(`notifications/${id}/read`, {
        method: "POST",
      }).then((r) => r.notification),

    /* ── Addresses ── */
    getAddresses: () =>
      request<{ items: Address[] }>("addresses").then((r) => r.items ?? []),
    addAddress: (payload: Omit<Address, "id">) =>
      request<{ address: Address }>("addresses", {
        method: "POST",
        body: payload,
      }).then((r) => r.address),
    updateAddress: (addressId: string, payload: Partial<Omit<Address, "id">>) =>
      request<{ address: Address }>(`addresses/${addressId}`, {
        method: "PUT",
        body: payload,
      }).then((r) => r.address),
    deleteAddress: (addressId: string) =>
      request(`addresses/${addressId}`, { method: "DELETE" }),

    /* ── Payment Methods ── */
    getPaymentMethods: () =>
      request<{ items: PaymentMethod[] }>("payment-methods").then((r) => r.items ?? []),
    addPaymentMethod: (payload: Omit<PaymentMethod, "id">) =>
      request<{ payment_method: PaymentMethod }>("payment-methods", {
        method: "POST",
        body: payload,
      }).then((r) => r.payment_method),
    deletePaymentMethod: (paymentMethodId: string) =>
      request(`payment-methods/${paymentMethodId}`, { method: "DELETE" }),

    /* ── Wishlist ── */
    getWishlist: () =>
      request<{ items: Product[] }>("wishlist").then((r) => r.items ?? []),
    addToWishlist: (productId: string) =>
      request<{ ok: boolean; product_id: string }>("wishlist/add", {
        method: "POST",
        body: { product_id: productId },
      }).then(() => undefined),
    removeFromWishlist: (productId: string) =>
      request("wishlist/remove", {
        method: "POST",
        body: { product_id: productId },
      }),

    /* ── Reviews ── */
    getReviews: (productId: string) =>
      request<{ items: Review[] }>(`products/${productId}/reviews`).then((r) => r.items ?? []),
    addReview: (productId: string, payload: { rating: number; title: string; body: string }) =>
      request<{ review: Review }>(`products/${productId}/reviews`, {
        method: "POST",
        body: { product_id: productId, ...payload },
      }).then((r) => r.review),

    /* ── Settings / Account ── */
    getSettings: () =>
      request<{ settings: AmazonSettings }>("settings").then((r) => r.settings),
    updateSettings: (payload: Partial<AmazonSettings>) =>
      request<{ settings: AmazonSettings }>("settings", {
        method: "PUT",
        body: payload,
      }).then((r) => r.settings),
    getAccount: () =>
      request<AmazonAccount>("account"),
    changePassword: (currentPassword: string, newPassword: string) =>
      request<{ success: boolean }>("account/password", {
        method: "PUT",
        body: { current_password: currentPassword, new_password: newPassword },
      }),
  };
}
