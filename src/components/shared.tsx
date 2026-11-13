"use client";

import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import type { Marketplace, Pod } from "@/lib/types";

export type Totals = { subtotal: number; remaining: number; progress: number; freeShipping: boolean; itemCount: number; buyers: number };
export type PodWithTotals = Pod & { totals: Totals };
export type Bag = {
  bag: number; memberId: string; name: string; items: { title: string; qty: number; total: number }[];
  itemsTotal: number; amountDue: number; fee: number; venmo: string | null; zelle: string | null;
  pickupCode: string; pickupToken: string; paid: boolean; collected: boolean;
  collectedAt?: string; confirmedBy?: string; collectedBy?: string;
};

export const STORE_NAMES: Record<Marketplace, string> = { weee: "Weee!", amazon_fresh: "Amazon Fresh" };
export const SOLO_SHIPPING = 5;
const AVATAR_COLORS = ["#f47b67", "#7c6cf2", "#2f9e6e", "#f2a33a", "#e8467c", "#2bb5a8"];
const PRODUCT_EMOJI: [RegExp, string][] = [
  [/ramen|noodle|indomie|ramyun/i, "🍜"], [/chip|snack|pocky|cracker|panda|seaweed/i, "🍘"], [/cheese|cheddar/i, "🧀"],
  [/dumpling|gyoza|bao/i, "🥟"], [/rice/i, "🍚"], [/milk|yogurt/i, "🥛"], [/egg/i, "🥚"], [/tofu/i, "🧈"],
  [/banana|fruit|mango|apple/i, "🍌"], [/kimchi|chili|spicy/i, "🌶️"], [/spinach|bok choy|lettuce|veg/i, "🥬"], [/tea|drink|soda/i, "🧋"],
];

export const money = (n: number | null | undefined) => (n == null ? "?" : `$${n.toFixed(2)}`);
export const colorFor = (id: string) => AVATAR_COLORS[[...id].reduce((s, c) => s + c.charCodeAt(0), 0) % AVATAR_COLORS.length];
export const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
export const plural = (count: number, word: string, many = `${word}s`) => `${count} ${count === 1 ? word : many}`;
export const shortBuilding = (building: string) => building.split(",")[0];
export const productEmoji = (title: string) => PRODUCT_EMOJI.find(([pattern]) => pattern.test(title))?.[1] ?? "🛒";
export const dayAndTime = (iso: string) =>
  new Date(iso).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).replace(/,(?=[^,]*$)/, " ·");
export const weekdayAndHour = (iso: string) => new Date(iso).toLocaleString([], { weekday: "short", hour: "numeric" });

export function timeLeft(iso: string) {
  const minutesLeft = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  if (minutesLeft <= 0) return null;
  const days = Math.floor(minutesLeft / 1440);
  const hours = Math.floor((minutesLeft % 1440) / 60);
  return days > 0 ? `${days}d ${hours}h` : `${hours}h ${minutesLeft % 60}m`;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { "Content-Type": "application/json" } });
  return res.json();
}

export function Avatar({ id, name, size = 36, bot = false }: { id: string; name: string; size?: number; bot?: boolean }) {
  return (
    <div className="grid shrink-0 place-items-center rounded-full font-bold text-white ring-2 ring-white" style={{ width: size, height: size, background: bot ? "#195d49" : colorFor(id), fontSize: size * 0.4 }}>
      {bot ? "🛒" : initials(name)}
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-line">
      <div className="h-full rounded-full bg-forest transition-all" style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  );
}

export function StoreLogo({ marketplace }: { marketplace: Marketplace }) {
  // eslint-disable-next-line @next/next/no-img-element
  return marketplace === "weee" ? <img src="/figma/weee-logo.svg" alt="Weee!" width={84} height={24} /> : <img src="/figma/amazon-fresh-logo.png" alt="Amazon Fresh" width={108} height={24} className="object-contain" />;
}

export const primaryButton = "w-full rounded-full bg-forest py-3.5 text-center font-bold text-white transition active:scale-[0.98] disabled:opacity-40";
export const secondaryButton = "w-full rounded-full border border-line bg-white py-3 text-center font-bold text-forest transition active:scale-[0.98]";

/** Where a product comes from: the store, a link to its page, and whether the price was checked live. */
export function SourceBadge({ marketplace, url, source }: { marketplace: Marketplace; url?: string; source?: "live" | "snapshot" }) {
  const isProductPage = !!url && /\/product\/|\/dp\//.test(url);
  return (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-line bg-white px-2 py-0.5 text-[11px] font-bold text-slate">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={marketplace === "weee" ? "/figma/weee-logo.svg" : "/figma/amazon-fresh-logo.png"} alt="" className="h-3 w-auto" />
      {isProductPage ? "Store listing" : `Search ${STORE_NAMES[marketplace]}`} ↗
      {source && <span className={source === "live" ? "text-forest" : "text-amber"}>· {source === "live" ? "live price" : "saved price"}</span>}
    </a>
  );
}

export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-ink/40" onClick={onClose}>
      <div className="animate-slide-up max-h-[88dvh] w-full max-w-[440px] overflow-y-auto rounded-t-3xl bg-white p-5 pb-8" onClick={(e) => e.stopPropagation()}>
        <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-line" />
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-xl font-extrabold text-ink">{title}</h2>
          <button onClick={onClose} className="grid h-9 w-9 place-items-center rounded-full bg-cream text-slate" aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export const pickupUrl = (token: string) => `${typeof window === "undefined" ? "" : window.location.origin}/pickup/${token}`;
const timeOfDay = (iso: string) => new Date(iso).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });

export function HandoffProof({ bag, hostName }: { bag: Bag; hostName: string }) {
  if (!bag.collected) return null;
  return (
    <div className="rounded-xl bg-mint p-3 text-sm text-forest">
      <div className="font-bold">✓ Picked up{bag.collectedBy && bag.collectedBy !== bag.name ? ` by ${bag.collectedBy}` : ""}</div>
      {bag.collectedAt && <div>{timeOfDay(bag.collectedAt)} · confirmed by {hostName}</div>}
    </div>
  );
}

/** The bag's QR opens a pickup link. Share it so a friend can collect; the host scans it to confirm the handoff. */
export function PickupPass({ bag, pod, hostName }: { bag: Bag; pod: Pod; hostName: string }) {
  const [shared, setShared] = useState(false);
  const url = pickupUrl(bag.pickupToken);

  async function share() {
    const text = `Pickup pass for ${bag.name}'s HuddleCart bag #${bag.bag} at ${pod.pickupSpot}`;
    if (navigator.share) await navigator.share({ title: "HuddleCart pickup pass", text, url }).catch(() => undefined);
    else await navigator.clipboard.writeText(url);
    setShared(true);
  }

  return (
    <div>
      {bag.collected ? <HandoffProof bag={bag} hostName={hostName} /> : <div className="rounded-xl bg-mint px-4 py-3 font-bold text-forest">Ready for pickup</div>}
      <div className="mt-4 font-display text-2xl font-bold text-ink">{dayAndTime(pod.deliveryEta)}</div>
      <div className="text-slate">{pod.pickupSpot}</div>
      <div className={`mt-4 rounded-2xl bg-cream p-5 text-center ${bag.collected ? "opacity-50" : ""}`}>
        <div className="font-bold text-ink">Show this code at pickup</div>
        <div className="mx-auto my-3 w-fit rounded-xl bg-white p-3"><QRCodeSVG value={url} size={148} fgColor="#182724" /></div>
        <div className="font-display text-3xl font-extrabold tracking-wide text-ink">{bag.pickupCode}</div>
        <div className="mt-1 text-sm text-slate">Bag #{bag.bag} · {money(bag.amountDue)} to {hostName}</div>
        <div className="mt-2 text-xs text-slate">{hostName} scans it to confirm the handoff. That&apos;s your proof of pickup.</div>
      </div>
      <div className="mt-4 space-y-2">
        {!bag.collected && <button onClick={share} className={primaryButton}>{shared ? "Pass shared ✓" : "Share pass with a friend"}</button>}
        {!bag.collected && <div className="text-center text-xs text-slate">Can&apos;t make it? Whoever has this pass can collect your bag.</div>}
        {bag.venmo && !bag.paid && <a href={bag.venmo} target="_blank" rel="noreferrer" className={`${secondaryButton} block`}>Pay {money(bag.amountDue)} with Venmo</a>}
        {bag.zelle && !bag.paid && <div className="text-center text-sm text-slate">or Zelle {bag.zelle}</div>}
        {bag.paid && <div className="text-center text-sm font-bold text-forest">Paid ✓</div>}
      </div>
    </div>
  );
}
