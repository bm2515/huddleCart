export type Marketplace = "weee" | "amazon_fresh";

export type PodStatus = "open" | "locked" | "ordered" | "arrived" | "closed";

export interface Member {
  id: string;
  name: string;
  venmo?: string;
  zelle?: string;
}

export interface Pod {
  id: string;
  name: string;
  building: string;
  interest?: string;
  leaderId: string;
  memberIds: string[];
  marketplace: Marketplace;
  minimumForFreeShipping: number;
  feePerPerson: number;
  cutoff: string;
  deliveryEta: string;
  pickupSpot: string;
  status: PodStatus;
}

export interface Product {
  id: string;
  marketplace: Marketplace;
  title: string;
  price: number | null;
  unit?: string;
  url: string;
  image?: string;
  inStock: boolean | null;
  checkedAt: string;
  source: "live" | "snapshot";
}

export interface CartLine {
  id: string;
  podId: string;
  memberId: string;
  product: Product;
  qty: number;
  addedAt: string;
  orderId?: string;
  dishId?: string;
}

export interface ItemRequest {
  query: string;
  qty: number;
  notes?: string | null;
}

export type Block =
  | { type: "text"; text: string }
  | { type: "searching"; queries: string[] }
  | { type: "tool_calls"; calls: ToolCall[] }
  | {
      type: "product_choices";
      request: ItemRequest;
      products: Product[];
      recommendedId?: string;
      reason?: string;
    }
  | { type: "out_of_stock"; request: ItemRequest; product?: Product; alternatives: Product[] }
  | { type: "cart_summary"; podId: string }
  | { type: "pod_suggestions"; podIds: string[]; reason: string }
  | { type: "checkout_review"; podId: string }
  | { type: "order_placed"; order: PlacedOrder; pickupSpot: string; deliveryEta: string }
  | { type: "event_invite"; eventId: string };

export interface ToolCall {
  tool: "get_pod_details" | "search_products" | "find_open_pods";
  args: Record<string, string | number | null>;
  summary: string;
  source?: "live" | "snapshot";
  sources?: { title: string; url: string; marketplace: Marketplace }[];
}

export interface PlacedOrder {
  id: string;
  number: string;
  podId: string;
  memberId: string;
  items: { title: string; qty: number; total: number }[];
  itemsTotal: number;
  fee: number;
  total: number;
  placedAt: string;
}

export interface Dish {
  id: string;
  name: string;
  course: "starter" | "main" | "side" | "dessert" | "drink";
  veg: boolean;
  recipe: string | null;
  note: string | null;
  cookId: string | null;
  wished: boolean;
  ingredients: Product[];
  ingredientsTotal: number;
}

export interface CommunityEvent {
  id: string;
  podId: string;
  hostId: string;
  occasion: string;
  emoji: string;
  title: string;
  date: string;
  guests: number;
  avoid: string | null;
  dishes: Dish[];
  vibes: string[];
  podName: string;
  podStatus: PodStatus;
  closesAt: string;
  pickupAt: string;
  pickupSpot: string;
  building: string;
  marketplace: Marketplace;
  claimedCount: number;
  dishCount: number;
  comingCount: number;
  cookingCount: number;
  vibesCount: number;
  courseCounts: Record<string, number>;
  upForGrabs: string[];
}

export type Menus = Record<string, { label: string; hint: string; title: string; emoji: string; dishes: { name: string; course: string; veg: boolean }[] }>;

export interface ChatMessage {
  id: string;
  podId: string;
  authorId: string;
  role: "user" | "agent" | "system";
  blocks: Block[];
  createdAt: string;
}
