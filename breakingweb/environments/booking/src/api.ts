/**
 * Booking API client.
 *
 * The request function comes from `useApi("booking", sessionId)` in the shared
 * library, which automatically adds `session_id` as a query parameter on GET
 * requests and merges it into POST/PUT/DELETE bodies.  So we never pass
 * session_id ourselves.
 */

import type { ApiRequestOptions } from "@breakingweb/shared";

import type {
  Property,
  PropertyBrief,
  Reservation,
  Review,
  SavedList,
  PaymentMethod,
  Message,
  Notification,
  Account,
  BookingSettings,
  TravelPreferences,
  GeniusInfo,
  Wallet,
  SearchHistoryEntry,
  RebookingSuggestion,
  SearchResults,
  Destination,
  Deal,
} from "./types";

type RequestFn = <T>(path: string, options?: ApiRequestOptions) => Promise<T>;

export function createBookingApi(request: RequestFn) {
  return {
    // --- Properties ---
    searchProperties(params: {
      destination?: string;
      name?: string;
      check_in?: string;
      check_out?: string;
      guests?: number;
      rooms?: number;
      min_price?: number;
      max_price?: number;
      min_rating?: number;
      star_rating?: number;
      star_ratings?: number[];
      property_type?: string;
      amenities?: string[];
      free_cancellation?: boolean;
      meals_included?: string;
      sort_by?: string;
      page?: number;
      page_size?: number;
    }) {
      return request<SearchResults>("properties/search", {
        method: "POST",
        body: params,
      });
    },

    getProperty(propertyId: string) {
      return request<Property>(`properties/${propertyId}`);
    },

    listProperties(city?: string) {
      return request<{ properties: PropertyBrief[]; total: number }>("properties", {
        query: city ? { city } : undefined,
      });
    },

    getDestinations() {
      return request<{ destinations: Destination[] }>("destinations");
    },

    getDeals() {
      return request<{ deals: Deal[] }>("deals");
    },

    getRecentlyViewed() {
      return request<{ properties: PropertyBrief[] }>("recently-viewed");
    },

    // --- Reservations ---
    createReservation(params: {
      property_id: string;
      room_type_id: string;
      check_in: string;
      check_out: string;
      guests: number;
      rooms: number;
      payment_method_id: string;
      full_name: string;
      email: string;
      phone?: string;
      country?: string;
      special_requests?: string;
      meals_included?: string;
    }) {
      return request<Reservation>("reservations", { method: "POST", body: params });
    },

    listReservations(status?: string) {
      return request<{ reservations: Reservation[]; total: number }>("reservations", {
        query: status ? { status } : undefined,
      });
    },

    getReservation(reservationId: string) {
      return request<Reservation>(`reservations/${reservationId}`);
    },

    previewCancelReservation(reservationId: string) {
      return request<{
        reservation_id: string;
        fee_amount: number;
        total_price: number;
        days_until_checkin: number;
        policy_type: string;
        policy_description: string;
        refundable: boolean;
        currency: string;
      }>(`reservations/${reservationId}/cancel-preview`, {
        method: "POST",
      });
    },

    cancelReservation(reservationId: string, feeAccepted: number | null = null) {
      return request<Reservation>(`reservations/${reservationId}/cancel`, {
        method: "POST",
        body: { fee_accepted: feeAccepted },
      });
    },

    pricePreview(params: {
      property_id: string;
      room_type_id: string;
      nights: number;
      rooms?: number;
    }) {
      const q = new URLSearchParams({
        property_id: params.property_id,
        room_type_id: params.room_type_id,
        nights: String(params.nights),
        rooms: String(params.rooms ?? 1),
      });
      return request<{
        property_id: string;
        room_type_id: string;
        nights: number;
        rooms: number;
        price_per_night: number;
        base_total: number;
        taxes: number;
        city_fee: number;
        resort_fee: number;
        cleaning_fee: number;
        total_fees: number;
        total_with_fees: number;
        currency: string;
      }>(`price-preview?${q.toString()}`);
    },

    listRebookings() {
      return request<{ rebookings: RebookingSuggestion[] }>("rebookings");
    },

    getRebookingByReservation(reservationId: string) {
      return request<RebookingSuggestion>(`rebookings/by-reservation/${reservationId}`);
    },

    modifyReservation(reservationId: string, params: {
      check_in?: string;
      check_out?: string;
      guests?: number;
      special_requests?: string;
    }) {
      return request<Reservation>(`reservations/${reservationId}`, {
        method: "PUT",
        body: params,
      });
    },

    // --- Reviews ---
    addReview(params: {
      property_id: string;
      reservation_id?: string;
      overall_score: number;
      staff?: number;
      facilities?: number;
      cleanliness?: number;
      comfort?: number;
      value_for_money?: number;
      location?: number;
      free_wifi?: number;
      title?: string;
      positive?: string;
      negative?: string;
      travel_purpose?: string;
      traveled_with?: string;
    }) {
      return request<Review>("reviews", { method: "POST", body: params });
    },

    listReviews(propertyId?: string) {
      return request<{ reviews: Review[]; total: number }>("reviews", {
        query: propertyId ? { property_id: propertyId } : undefined,
      });
    },

    // --- Saved Lists ---
    createSavedList(name: string) {
      return request<SavedList>("saved-lists", {
        method: "POST",
        body: { name },
      });
    },

    listSavedLists() {
      return request<{ lists: SavedList[] }>("saved-lists");
    },

    addToSavedList(listId: string, propertyId: string) {
      return request<SavedList>(`saved-lists/${listId}/properties`, {
        method: "POST",
        body: { property_id: propertyId },
      });
    },

    removeFromSavedList(listId: string, propertyId: string) {
      return request<SavedList>(`saved-lists/${listId}/properties/${propertyId}`, {
        method: "DELETE",
      });
    },

    deleteSavedList(listId: string) {
      return request<{ ok: boolean }>(`saved-lists/${listId}`, {
        method: "DELETE",
      });
    },

    // --- Payment Methods ---
    listPaymentMethods() {
      return request<{ payment_methods: PaymentMethod[] }>("payment-methods");
    },

    addPaymentMethod(params: {
      card_type: string;
      last_four: string;
      expiry: string;
      holder_name: string;
      is_default?: boolean;
    }) {
      return request<PaymentMethod>("payment-methods", { method: "POST", body: params });
    },

    removePaymentMethod(pmId: string) {
      return request<{ ok: boolean }>(`payment-methods/${pmId}`, {
        method: "DELETE",
      });
    },

    setDefaultPayment(pmId: string) {
      return request<Record<string, unknown>>(`payment-methods/${pmId}/set-default`, {
        method: "POST",
      });
    },

    // --- Messages ---
    listMessages() {
      return request<{ messages: Message[]; unread: number }>("messages");
    },

    sendMessage(params: {
      property_id: string;
      reservation_id?: string;
      subject: string;
      body: string;
    }) {
      return request<Message>("messages", { method: "POST", body: params });
    },

    markMessageRead(messageId: string) {
      return request<Message>(`messages/${messageId}/read`, { method: "POST" });
    },

    // --- Notifications ---
    listNotifications() {
      return request<{ notifications: Notification[]; unread: number }>("notifications");
    },

    markNotificationRead(notificationId: string) {
      return request<Notification>(`notifications/${notificationId}/read`, { method: "POST" });
    },

    markAllNotificationsRead() {
      return request<{ ok: boolean; marked_read: number }>("notifications/read-all", { method: "POST" });
    },

    // --- Account ---
    getAccount() {
      return request<Account>("account");
    },

    updateProfile(params: {
      owner_name?: string;
      owner_email?: string;
      owner_phone?: string;
      owner_nationality?: string;
      owner_date_of_birth?: string;
      owner_gender?: string;
      owner_address?: string;
    }) {
      return request<Account>("account", { method: "PUT", body: params });
    },

    getSettings() {
      return request<BookingSettings>("settings");
    },

    updateSettings(params: Record<string, unknown>) {
      return request<BookingSettings>("settings", { method: "PUT", body: params });
    },

    getPreferences() {
      return request<TravelPreferences>("preferences");
    },

    updatePreferences(params: Record<string, unknown>) {
      return request<TravelPreferences>("preferences", { method: "PUT", body: params });
    },

    getGenius() {
      return request<GeniusInfo>("genius");
    },

    getWallet() {
      return request<Wallet>("wallet");
    },

    applyWallet(params: { reservation_id?: string; amount?: number }) {
      return request<{ balance: number; currency: string; applied: number; message: string }>(
        "wallet/apply",
        { method: "POST", body: params },
      );
    },

    getSearchHistory() {
      return request<{ history: SearchHistoryEntry[] }>("search-history");
    },

    clearSearchHistory() {
      return request<{ ok: boolean }>("search-history", { method: "DELETE" });
    },

    // --- Auth ---
    login(email: string) {
      return request<{ ok: boolean; name: string }>("login", {
        method: "POST",
        body: { email, password: "simulated" },
      });
    },

    logout() {
      return request<{ ok: boolean }>("logout", { method: "POST" });
    },

    changePassword() {
      return request<{ ok: boolean }>("change-password", { method: "POST" });
    },

    // --- Evaluate ---
    evaluate(params: {
      benchmark_state?: Record<string, unknown>;
      trajectory?: Record<string, unknown>[];
    }) {
      return request<Record<string, unknown>>("evaluate", { method: "POST", body: params });
    },
  };
}

export type BookingApi = ReturnType<typeof createBookingApi>;
