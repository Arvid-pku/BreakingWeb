export interface GeoLocation {
  lat: number;
  lng: number;
}

export interface ReviewBreakdown {
  staff: number;
  facilities: number;
  cleanliness: number;
  comfort: number;
  value_for_money: number;
  location: number;
  free_wifi: number;
}

export interface HouseRules {
  check_in_from: string;
  check_in_until: string;
  check_out_from: string;
  check_out_until: string;
  children_allowed: boolean;
  pets_allowed: boolean;
  pet_fee: number;
  smoking_allowed: boolean;
  parties_allowed: boolean;
  quiet_hours_from: string;
  quiet_hours_until: string;
}

export interface CancellationPolicy {
  type: string;
  free_cancel_before_days: number;
  penalty_percentage: number;
  description: string;
}

export interface NearbyAttraction {
  name: string;
  distance_km: number;
  type: string;
}

export interface RoomType {
  id: string;
  property_id: string;
  name: string;
  description: string;
  max_occupancy: number;
  bed_type: string;
  bed_count: number;
  room_size_sqm: number;
  price_per_night: number;
  original_price: number | null;
  amenities: string[];
  meals_included: string;
  cancellation_policy: CancellationPolicy;
  is_available: boolean;
  rooms_left: number;
  images: string[];
  view_type: string;
}

export interface Property {
  id: string;
  name: string;
  property_type: string;
  star_rating: number;
  city: string;
  country: string;
  neighborhood: string;
  address: string;
  geo: GeoLocation;
  description: string;
  short_description: string;
  review_score: number;
  review_score_label: string;
  review_count: number;
  review_breakdown: ReviewBreakdown;
  amenities: string[];
  popular_facilities: string[];
  room_types: RoomType[];
  images: string[];
  house_rules: HouseRules;
  distance_from_center_km: number;
  nearby_attractions: NearbyAttraction[];
  genius_discount_pct: number;
  is_genius_property: boolean;
  languages_spoken: string[];
  chain_name: string;
  sustainability_badge: boolean;
  currency: string;
  reviews?: Review[];
  // Computed fields from API
  price_from?: number | null;
  original_price_from?: number | null;
}

export interface PropertyBrief {
  id: string;
  name: string;
  property_type: string;
  star_rating: number;
  city: string;
  country: string;
  neighborhood: string;
  review_score: number;
  review_score_label: string;
  review_count: number;
  distance_from_center_km: number;
  popular_facilities: string[];
  is_genius_property: boolean;
  genius_discount_pct: number;
  images: string[];
  price_from: number | null;
  original_price_from: number | null;
  currency: string;
  free_cancellation: boolean;
  breakfast_included: boolean;
  rooms_available: number;
}

export interface ReservationGuest {
  full_name: string;
  email: string;
  phone: string;
  country: string;
  special_requests: string;
}

export interface Reservation {
  id: string;
  property_id: string;
  property_name: string;
  room_type_id: string;
  room_type_name: string;
  check_in: string;
  check_out: string;
  nights: number;
  guests: number;
  rooms: number;
  price_per_night: number;
  total_price: number;
  taxes_and_fees: number;
  taxes: number;
  city_fee: number;
  resort_fee: number;
  cleaning_fee: number;
  currency: string;
  status: string;
  booked_at: string;
  guest_info: ReservationGuest;
  payment_method_id: string;
  cancellation_policy: CancellationPolicy;
  confirmation_number: string;
  is_genius_deal: boolean;
  genius_discount: number;
  meals_included: string;
  rating_submitted: boolean;
  property?: PropertyBrief;
}

export interface Review {
  id: string;
  property_id: string;
  reservation_id: string;
  author_name: string;
  author_country: string;
  overall_score: number;
  scores: ReviewBreakdown;
  title: string;
  positive: string;
  negative: string;
  room_type: string;
  travel_purpose: string;
  traveled_with: string;
  stay_date: string;
  created_at: string;
  helpful_count: number;
  property_response: string;
}

export interface SavedList {
  id: string;
  name: string;
  property_ids: string[];
  created_at: string;
  updated_at: string;
  property_previews?: { id: string; name: string; city: string; images: string[] }[];
}

export interface PaymentMethod {
  id: string;
  card_type: string;
  last_four: string;
  expiry: string;
  holder_name: string;
  is_default: boolean;
}

export interface Message {
  id: string;
  property_id: string;
  property_name: string;
  reservation_id: string;
  subject: string;
  body: string;
  sender: string;
  read: boolean;
  created_at: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  created_at: string;
  related_id: string | null;
}

export interface SearchHistoryEntry {
  destination: string;
  check_in: string;
  check_out: string;
  guests: number;
  rooms: number;
  searched_at: string;
}

export interface GeniusInfo {
  level: number;
  total_bookings: number;
  bookings_needed_for_next: number;
  benefits: string[];
}

export interface WalletTransaction {
  amount: number;
  type: string;
  description: string;
  created_at: string;
}

export interface Wallet {
  balance: number;
  currency: string;
  transactions: WalletTransaction[];
}

export interface TravelPreferences {
  smoking: boolean;
  preferred_bed_type: string;
  floor_preference: string;
  accessibility_needs: boolean;
  preferred_room_type: string;
  dietary_restrictions: string[];
  preferred_language: string;
  preferred_currency: string;
}

export interface BookingSettings {
  id: string;
  default_payment_id: string | null;
  email_notifications: boolean;
  deal_alerts: boolean;
  review_reminders: boolean;
  price_alerts: boolean;
  newsletter: boolean;
  sms_notifications: boolean;
  language: string;
  currency: string;
  country: string;
  two_factor_enabled: boolean;
}

export interface Account {
  name: string;
  email: string;
  phone: string;
  nationality: string;
  date_of_birth: string;
  gender: string;
  address: string;
  genius: GeniusInfo;
  wallet: Wallet;
}

export interface Destination {
  city: string;
  country: string;
  property_count: number;
  min_price: number | null;
}

export interface Deal {
  property: PropertyBrief;
  room_type: string;
  price: number;
  original_price: number;
  discount_pct: number;
  currency: string;
}

export interface SearchResults {
  results: PropertyBrief[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  available_cities: string[];
  available_property_types: string[];
}

// ---------------------------------------------------------------------------
// Rebooking assistant (Feature I)
// ---------------------------------------------------------------------------

export interface RebookingCandidate {
  property_id: string;
  property_name: string;
  city: string;
  star_rating: number;
  review_score: number;
  room_type_id: string;
  room_type_name: string;
  price_per_night: number;
  nights: number;
  base_total: number;
  taxes: number;
  city_fee: number;
  resort_fee: number;
  cleaning_fee: number;
  total_with_fees: number;
  currency: string;
}

export interface RebookingSuggestion {
  id: string;
  original_reservation_id: string;
  city: string;
  check_in: string;
  check_out: string;
  guests: number;
  candidates: RebookingCandidate[];
  created_at: string;
  consumed_at: string | null;
  consumed_property_id: string | null;
}
