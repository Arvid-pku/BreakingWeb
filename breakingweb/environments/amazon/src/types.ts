export interface Product {
  id: string;
  name: string;
  brand: string;
  category: string;
  subcategory?: string;
  price: number;
  list_price?: number | null;
  currency: string;
  description: string;
  features: string[];
  image_url?: string;
  rating: number;
  review_count: number;
  in_stock: boolean;
  stock_quantity?: number;
  prime_eligible: boolean;
  seller?: string;
  delivery_estimate?: string;
  variants?: ProductVariant[];
}

export interface ProductVariant {
  name: string;
  value: string;
  price_modifier: number;
  in_stock: boolean;
}

export interface CartItem {
  id: string;
  product_id: string;
  product_name: string;
  variant_selections?: Record<string, string>;
  variant_id?: string;
  variant_name?: string;
  quantity: number;
  unit_price: number;
  image_url?: string;
  category?: string;
  subcategory?: string;
  prime_eligible?: boolean;
  in_stock?: boolean;
}

export interface Address {
  id: string;
  full_name: string;
  street_address: string;
  city: string;
  state: string;
  zip_code: string;
  country: string;
  is_default: boolean;
  phone?: string;
}

export interface PaymentMethod {
  id: string;
  card_type: string;
  last_four: string;
  expiry: string;
  holder_name: string;
  is_default: boolean;
}

export interface Order {
  id: string;
  status: string;
  items: OrderItem[];
  subtotal: number;
  shipping_cost: number;
  tax: number;
  total: number;
  shipping_address_id: string;
  payment_method_id: string;
  placed_at: string;
  estimated_delivery?: string;
  promo_code?: string | null;
  discount?: number;
  is_simulated?: boolean;
}

export interface OrderItem {
  product_id: string;
  product_name: string;
  variant_name?: string;
  variant_selections?: Record<string, string>;
  quantity: number;
  unit_price: number;
  image_url?: string;
  category?: string;
  subcategory?: string;
}

export interface Review {
  id: string;
  product_id: string;
  author_name: string;
  rating: number;
  title: string;
  body: string;
  created_at: string;
  verified_purchase: boolean;
  helpful_count: number;
}

export interface AmazonSettings {
  id?: string;
  default_address_id?: string | null;
  default_payment_id?: string | null;
  prime_member: boolean;
  one_click_enabled: boolean;
  email_notifications: boolean;
  language: string;
  currency: string;
  two_factor_enabled: boolean;
  order_updates_email: boolean;
  deal_alerts_email: boolean;
  gift_card_balance: number;
}

export interface AmazonAccount {
  owner_name: string;
  email: string;
  is_logged_in: boolean;
  settings: AmazonSettings;
}

export interface SearchResult {
  items: Product[];
  page: number;
  total: number;
  page_size: number;
  pages: number;
  categories?: string[];
}

export type WishlistItem = Product;

export interface CartSummary {
  items: CartItem[];
  totals: {
    subtotal: number;
    shipping: number;
    tax: number;
    discount: number;
    gift_card_applied: number;
    total: number;
  };
  item_count: number;
}

export interface ReturnRequest {
  id: string;
  order_id: string;
  order_item_index: number;
  product_id: string;
  product_name: string;
  image_url?: string;
  category?: string;
  subcategory?: string;
  reason: string;
  status: string;
  refund_amount: number;
  created_at: string;
  resolution_note: string;
}

export interface PromoCode {
  id: string;
  code: string;
  discount_type: string;
  discount_value: number;
  min_order_amount: number;
  valid_until: string;
  active: boolean;
}

export interface ProductAnswer {
  answer: string;
  author_name: string;
  answered_at: string;
  helpful_count: number;
  is_seller_response: boolean;
}

export interface ProductQuestion {
  id: string;
  product_id: string;
  question: string;
  asker_name: string;
  answers: ProductAnswer[];
  asked_at: string;
  vote_count: number;
}

export interface GiftCard {
  id: string;
  code: string;
  balance: number;
  initial_amount: number;
  redeemed: boolean;
  added_at: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  created_at: string;
  related_id: string;
}
