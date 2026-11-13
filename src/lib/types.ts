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
}

export interface ItemRequest {
  query: string;
  qty: number;
  notes?: string | null;
}

export type Block =
  | { type: "text"; text: string }
  | { type: "searching"; queries: string[] }
  | {
      type: "product_choices";
      request: ItemRequest;
      products: Product[];
      recommendedId?: string;
      reason?: string;
    }
  | { type: "out_of_stock"; request: ItemRequest; product?: Product; alternatives: Product[] }
  | { type: "cart_summary"; podId: string }
  | { type: "pod_suggestions"; podIds: string[]; reason: string };

export interface ChatMessage {
  id: string;
  podId: string;
  authorId: string;
  role: "user" | "agent" | "system";
  blocks: Block[];
  createdAt: string;
}
