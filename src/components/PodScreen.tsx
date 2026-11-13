"use client";

import { useEffect, useRef, useState } from "react";
import type { Block, CartLine, ChatMessage, CommunityEvent, Member, Product, ToolCall } from "@/lib/types";
import { EventCard } from "./CommunityScreen";
import QrScanner from "./QrScanner";
import type { Community } from "./SavingsScreen";
import {
  Avatar, PickupPass, ProgressBar, SOLO_SHIPPING, STORE_NAMES, Sheet, api, colorFor, dayAndTime, money, primaryButton,
  SourceBadge, productEmoji, secondaryButton, shortBuilding, timeLeft, type Bag, type PodWithTotals,
} from "./shared";

export type PodDetail = { pod: PodWithTotals; members: Member[]; cart: CartLine[]; messages: ChatMessage[] };

const SUGGESTIONS = ["2 shrimp chips", "check out", "any dinners this week?", "cheddar cheese by tomorrow", "frozen dumplings"];
const CHECKOUT_PROMPT = "I'm ready to check out";
const COVER_GRADIENT = { weee: "from-[#ff7aa2] via-[#ffb36b] to-[#ffe08a]", amazon_fresh: "from-[#5fd3a5] via-[#7cc8f2] to-[#c7b8ff]" } as const;
const HOST_STEPS: Record<string, { action: string; label: string; hint: string } | undefined> = {
  open: { action: "lock", label: "Lock the cart", hint: "Stops new items so you can place the order." },
  locked: { action: "ordered", label: "I placed the order", hint: "Tell everyone it's on the way." },
  ordered: { action: "arrived", label: "It arrived", hint: "Sends everyone their bag number and pickup code." },
  arrived: { action: "close", label: "Close the pod", hint: "Once every bag is picked up." },
};
const timeOf = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

type ChatContext = {
  pods: PodWithTotals[]; pod: PodWithTotals; events: CommunityEvent[]; members: Member[]; canAdd: boolean;
  basket: CartLine[]; basketFee: number; hasPlaced: boolean; onAdd: (p: Product, qty: number) => void; onOpenPod: (id: string) => void;
  onOpenEvent: (id: string) => void; onPlaceOrder: () => void; onSend: (text: string) => void;
};

export default function PodScreen({ detail, pods, events, me, community, onBack, onOpenPod, onOpenEvent, onJoin, onChanged, notify }: {
  detail: PodDetail | null; pods: PodWithTotals[]; events: CommunityEvent[]; me: string; community: Community | null;
  onBack: () => void; onOpenPod: (podId: string) => void; onOpenEvent: (eventId: string) => void; onJoin: (podId: string) => void;
  onChanged: () => Promise<void>; notify: (text: string, celebrate?: boolean) => void;
}) {
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<{ text: string; messagesBefore: number } | null>(null);
  const [placing, setPlacing] = useState(false);
  const [sheet, setSheet] = useState<"basket" | "host" | "pickup" | "scan" | null>(null);
  const [bags, setBags] = useState<Bag[]>([]);
  const bottom = useRef<HTMLDivElement>(null);
  const pod = detail?.pod;

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [detail?.messages.length, pending]);

  const loadBags = async () => { if (pod) setBags((await api<{ bags: Bag[] }>(`/api/delivery?podId=${pod.id}`)).bags); };
  useEffect(() => { if (sheet === "host" || sheet === "pickup") loadBags(); }, [sheet]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!detail || !pod) return <div className="grid flex-1 place-items-center text-slate">Loading pod…</div>;
  const nameOf = (id: string) => (id === "huddlecart" ? "HuddleCart" : detail.members.find((m) => m.id === id)?.name ?? id);
  const joined = pod.memberIds.includes(me);
  const isHost = pod.leaderId === me;
  const myLines = detail.cart.filter((line) => line.memberId === me);
  const basket = myLines.filter((line) => !line.orderId);
  const basketFee = myLines.some((line) => line.orderId) ? 0 : pod.feePerPerson;
  const myItemsTotal = basket.reduce((sum, l) => sum + (l.product.price ?? 0) * l.qty, 0);
  const myItemCount = basket.reduce((sum, l) => sum + l.qty, 0);
  const podEvents = events.filter((e) => e.podId === pod.id);
  // The server saves the user's message before the agent answers, so hide our local copy once it shows up.
  const pendingAlreadySaved = !!pending && detail.messages.slice(pending.messagesBefore).some((m) => m.authorId === me && m.role === "user");
  const myBag = bags.find((b) => b.memberId === me);
  const closesIn = timeLeft(pod.cutoff);
  const canShop = joined && pod.status === "open";

  async function send(text: string) {
    if (!text.trim() || pending) return;
    setDraft("");
    setPending({ text, messagesBefore: detail!.messages.length });
    await api("/api/chat", { method: "POST", body: JSON.stringify({ podId: pod!.id, memberId: me, text }) });
    await onChanged();
    setPending(null);
  }

  async function placeOrder() {
    if (placing) return;
    setPlacing(true);
    const result = await api<{ ok: boolean; reason?: string; order?: { number: string } }>("/api/checkout", { method: "POST", body: JSON.stringify({ podId: pod!.id, memberId: me }) });
    notify(result.ok ? `Order ${result.order!.number} placed! 🎉` : result.reason ?? "Couldn't place the order", result.ok);
    await onChanged();
    setPlacing(false);
  }

  const chat: ChatContext = {
    pods, pod, events, members: detail.members, canAdd: canShop, basket, basketFee, hasPlaced: myLines.some((l) => !!l.orderId),
    onAdd: addToCart, onOpenPod, onOpenEvent, onPlaceOrder: placeOrder, onSend: send,
  };

  async function addToCart(product: Product, qty: number) {
    const result = await api<{ ok: boolean; reason?: string }>("/api/cart", {
      method: "POST", body: JSON.stringify({ podId: pod!.id, memberId: me, product, qty, requestId: crypto.randomUUID() }),
    });
    notify(result.ok ? `Added ${qty} × ${product.title} · +${qty * 10} XP` : result.reason ?? "Couldn't add that", result.ok);
    onChanged();
  }

  async function removeLine(lineId: string) {
    await api("/api/cart", { method: "DELETE", body: JSON.stringify({ lineId, memberId: me }) });
    onChanged();
  }

  async function confirmHandoff(token: string) {
    const result = await api<{ ok: boolean; reason?: string }>(`/api/pickup/${token}/confirm`, { method: "POST", body: JSON.stringify({ memberId: me }) });
    notify(result.ok ? "Handoff confirmed ✓" : result.reason ?? "Couldn't confirm", result.ok);
    await onChanged();
    loadBags();
  }

  async function updateDelivery(action: string, targetId?: string) {
    const result = await api<{ ok: boolean; error?: string }>("/api/delivery", { method: "POST", body: JSON.stringify({ podId: pod!.id, memberId: me, action, targetId }) });
    if (!result.ok) notify(result.error ?? "Not allowed");
    await onChanged();
    loadBags();
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b border-line bg-white px-4 pb-3 pt-3">
        <div className="flex items-center gap-2">
          <button onClick={onBack} className="grid h-10 w-10 place-items-center rounded-full text-2xl text-forest" aria-label="Back">‹</button>
          <div className="min-w-0 flex-1">
            <div className="truncate font-bold text-ink">{STORE_NAMES[pod.marketplace]} · {shortBuilding(pod.building)}</div>
            <div className="truncate text-sm font-bold text-forest">Delivery: {dayAndTime(pod.deliveryEta)}</div>
          </div>
          <span className="text-sm font-bold text-forest">{pod.status === "open" ? (closesIn ? `${closesIn} left` : "Closed") : pod.status}</span>
        </div>
        {isHost && (
          <button onClick={() => setSheet("host")} className="mt-2 w-full rounded-full bg-amber-pale py-2 text-sm font-bold text-amber">👑 You&apos;re hosting · {HOST_STEPS[pod.status]?.label ?? "Pod closed"} ›</button>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className={`relative mb-4 overflow-hidden rounded-3xl bg-gradient-to-br ${COVER_GRADIENT[pod.marketplace]} p-5`}>
          <span className="absolute right-4 top-3 rotate-12 text-3xl">🥟</span>
          <span className="absolute bottom-3 right-10 -rotate-12 text-2xl">🍜</span>
          <div className="font-display text-3xl font-extrabold leading-tight text-ink">{pod.name}</div>
          <div className="mt-1 text-sm font-medium text-ink/80">Hosted by {nameOf(pod.leaderId)} · pickup at {pod.pickupSpot}</div>
          <div className="mt-3 flex -space-x-2">{pod.memberIds.map((id) => <Avatar key={id} id={id} name={nameOf(id)} size={30} />)}</div>
          <div className="mt-3 rounded-xl bg-white/70 p-3 backdrop-blur">
            <div className="mb-1 flex justify-between text-sm font-bold"><span>🎯 Free shipping goal</span><span>{money(pod.totals.subtotal)} / {money(pod.minimumForFreeShipping)}</span></div>
            <ProgressBar value={pod.totals.progress} />
            <div className="mt-1 text-xs text-slate">{pod.totals.freeShipping ? "Unlocked! 🎉" : `${money(pod.totals.remaining)} to go`} · everyone gets +{community?.questRewardXp ?? 50} XP when it fills</div>
          </div>
        </div>

        {podEvents.length > 0 && (
          <div className="no-scrollbar -mx-4 mb-4 flex gap-3 overflow-x-auto px-4">
            {podEvents.map((e) => <EventCard key={e.id} event={e} members={detail.members} compact onOpen={() => onOpenEvent(e.id)} />)}
          </div>
        )}
        <AgentBubble><p>Hi! Tell me what you want from {STORE_NAMES[pod.marketplace]} and I&apos;ll find it. Tap Add on the one you like, then say &quot;check out&quot; when you&apos;re done.</p></AgentBubble>
        {detail.messages.map((message) => (
          <MessageRow key={message.id} message={message} me={me} author={nameOf(message.authorId)}>
            {message.blocks.map((block, i) => <BlockView key={i} block={block} chat={chat} />)}
          </MessageRow>
        ))}
        {pending && (
          <>
            {!pendingAlreadySaved && <MessageRow message={{ id: "pending", podId: pod.id, authorId: me, role: "user", blocks: [], createdAt: new Date().toISOString() }} me={me} author={nameOf(me)}><p>{pending.text}</p></MessageRow>}
            <AgentBubble>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate">
                <span className="animate-pulse">🔧</span>
                {["get_pod_details", "understand", `search_products(${STORE_NAMES[pod.marketplace]})`].map((step, i) => (
                  <code key={step} className="animate-pulse rounded bg-white px-1.5 py-0.5" style={{ animationDelay: `${i * 0.3}s` }}>{step}</code>
                ))}
              </div>
            </AgentBubble>
          </>
        )}
        {pod.status === "arrived" && joined && myLines.length > 0 && (
          <button onClick={() => setSheet("pickup")} className="my-3 w-full rounded-2xl bg-mint p-4 text-left">
            <div className="font-bold text-forest">📦 Your bag is ready</div>
            <div className="text-sm text-slate">Tap to show your pickup code and pay your host.</div>
          </button>
        )}
        <div ref={bottom} />
      </div>

      <div className="border-t border-line bg-white px-4 pb-4 pt-3">
        {!joined ? (
          <>
            <div className="mb-2 text-center text-sm text-slate">Join to chat with HuddleCart and add to the shared order.</div>
            <button onClick={() => onJoin(pod.id)} disabled={pod.status !== "open"} className={primaryButton}>🙌 I&apos;m in · Join pod</button>
          </>
        ) : (
          <>
            {myItemCount > 0 && (
              <button onClick={() => setSheet("basket")} className="mb-3 flex w-full items-center rounded-full bg-forest px-5 py-3 font-bold text-white">
                <span className="mr-2 grid h-6 min-w-6 place-items-center rounded-full bg-white px-1.5 text-sm text-forest">{myItemCount}</span>
                <span className="flex-1 text-left">Your basket</span>
                <span>{money(myItemsTotal + basketFee)} ›</span>
              </button>
            )}
            <div className="no-scrollbar mb-2 flex gap-2 overflow-x-auto">
              {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} disabled={!!pending || !canShop} className="shrink-0 rounded-full border border-line bg-cream px-3 py-1.5 text-sm text-slate disabled:opacity-40">{s}</button>)}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); send(draft); }} className="flex items-center gap-2 rounded-full bg-cream py-1.5 pl-4 pr-1.5">
              <input value={draft} onChange={(e) => setDraft(e.target.value)} disabled={!!pending || !canShop}
                placeholder={canShop ? "Ask for groceries…" : "This cart is locked"} className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-slate/60" />
              <button disabled={!draft.trim() || !!pending} className="h-9 rounded-full bg-forest px-4 text-sm font-bold text-white disabled:opacity-30">Send</button>
            </form>
          </>
        )}
      </div>

      {sheet === "basket" && (
        <Sheet title="Your basket" onClose={() => setSheet(null)}>
          {basket.map((line) => (
            <div key={line.id} className="flex items-center gap-3 border-b border-line py-3">
              <span className="grid h-12 w-12 place-items-center rounded-xl bg-cream text-2xl">{productEmoji(line.product.title)}</span>
              <div className="min-w-0 flex-1"><div className="truncate font-bold">{line.product.title}</div><div className="my-0.5"><SourceBadge marketplace={line.product.marketplace} url={line.product.url} source={line.product.source} /></div><div className="text-sm text-slate">{line.qty} × {money(line.product.price)}{line.dishId && ` · for ${events.flatMap((e) => e.dishes).find((d) => d.id === line.dishId)?.name ?? "your dish"}`}</div></div>
              <span className="font-bold">{money((line.product.price ?? 0) * line.qty)}</span>
              {pod.status === "open" && <button onClick={() => removeLine(line.id)} className="text-slate" aria-label="Remove">✕</button>}
            </div>
          ))}
          <div className="mt-4 rounded-xl bg-cream p-4">
            <div className="font-bold">Basket summary</div>
            <div className="mt-2 flex justify-between text-sm"><span>Items</span><span>{money(myItemsTotal)}</span></div>
            <div className="flex justify-between text-sm"><span>Shared fee</span><span>{basketFee ? money(basketFee) : "paid ✓"}</span></div>
            <div className="mt-2 flex justify-between font-bold"><span>Total</span><span>{money(myItemsTotal + basketFee)}</span></div>
          </div>
          <div className="mt-3 rounded-lg bg-mint p-3 font-bold text-forest">Save {money(SOLO_SHIPPING - pod.feePerPerson)} vs. ordering alone</div>
          <button onClick={() => { setSheet(null); send(CHECKOUT_PROMPT); }} className={`${primaryButton} mt-4`}>Check out in chat</button>
          <button onClick={() => setSheet(null)} className={`${secondaryButton} mt-2`}>Keep shopping</button>
        </Sheet>
      )}

      {sheet === "pickup" && myBag && (
        <Sheet title="Pickup pass" onClose={() => setSheet(null)}>
          <PickupPass bag={myBag} pod={pod} hostName={nameOf(pod.leaderId)} />
        </Sheet>
      )}

      {sheet === "scan" && (
        <Sheet title="Scan a pickup pass" onClose={() => setSheet("host")}>
          <QrScanner onScan={(url) => { window.location.href = url; }} />
        </Sheet>
      )}

      {sheet === "host" && (
        <Sheet title="Host tools" onClose={() => setSheet(null)}>
          {HOST_STEPS[pod.status] && (
            <div className="mb-4 rounded-2xl bg-cream p-4">
              <div className="text-sm text-slate">Status: <span className="font-bold capitalize text-ink">{pod.status}</span></div>
              <div className="mb-3 text-sm text-slate">{HOST_STEPS[pod.status]!.hint}</div>
              <button onClick={() => updateDelivery(HOST_STEPS[pod.status]!.action)} className={primaryButton}>{HOST_STEPS[pod.status]!.label}</button>
            </div>
          )}
          {pod.status === "arrived" && <button onClick={() => setSheet("scan")} className={`${primaryButton} mb-4`}>📷 Scan a pickup pass</button>}
          <div className="mb-2 font-bold">Bags to pack · {bags.length}</div>
          {bags.length === 0 && <div className="text-sm text-slate">No one has added anything yet.</div>}
          {bags.map((bag) => (
            <div key={bag.bag} className="mb-2 rounded-xl border border-line p-3 text-sm">
              <div className="flex items-center gap-2">
                <span className="rounded-lg bg-forest px-2 py-0.5 font-bold text-white">#{bag.bag}</span>
                <span className="font-bold">{bag.name}</span>
                <span className="text-xs text-slate">{bag.pickupCode}</span>
                <span className="ml-auto font-bold">{money(bag.amountDue)}</span>
              </div>
              <div className="mt-1 text-slate">{bag.items.map((i) => `${i.qty} × ${i.title}`).join(", ")}</div>
              {pod.status !== "open" && (
                <div className="mt-2 flex gap-2">
                  <button onClick={() => updateDelivery("paid", bag.memberId)} className={`flex-1 rounded-full py-1.5 font-bold ${bag.paid ? "bg-mint text-forest" : "bg-cream"}`}>{bag.paid ? "Paid ✓" : "Mark paid"}</button>
                  <button onClick={() => confirmHandoff(bag.pickupToken)} disabled={bag.collected || pod.status === "locked" || pod.status === "ordered"} className={`flex-1 rounded-full py-1.5 font-bold ${bag.collected ? "bg-mint text-forest" : "bg-cream"}`}>{bag.collected ? "Handed off ✓" : "Confirm handoff"}</button>
                </div>
              )}
            </div>
          ))}
          <button onClick={() => setSheet(null)} className={`${secondaryButton} mt-3`}>Done</button>
        </Sheet>
      )}
    </div>
  );
}

function AgentBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 flex gap-2">
      <Avatar id="huddlecart" name="HuddleCart" size={32} bot />
      <div className="min-w-0 max-w-[85%] rounded-2xl rounded-tl-md bg-mint px-3.5 py-2.5 text-[15px]">{children}</div>
    </div>
  );
}

function MessageRow({ message, me, author, children }: { message: ChatMessage; me: string; author: string; children: React.ReactNode }) {
  if (message.role === "system") {
    return <div className="my-3 text-center"><span className="inline-block rounded-full bg-amber-pale px-3 py-1.5 text-sm font-medium text-amber">{children}</span></div>;
  }
  if (message.role === "agent") return <AgentBubble>{children}</AgentBubble>;
  const mine = message.authorId === me;
  return (
    <div className={`mb-3 flex gap-2 ${mine ? "flex-row-reverse" : ""}`}>
      {!mine && <Avatar id={message.authorId} name={author} size={32} />}
      <div className="max-w-[80%]">
        {!mine && <div className="mb-0.5 text-xs font-bold" style={{ color: colorFor(message.authorId) }}>{author} <span className="font-normal text-slate">{timeOf(message.createdAt)}</span></div>}
        <div className={`rounded-2xl px-3.5 py-2.5 text-[15px] ${mine ? "rounded-tr-md bg-forest text-white" : "rounded-tl-md bg-cream"}`}>{children}</div>
      </div>
    </div>
  );
}

function BlockView({ block, chat }: { block: Block; chat: ChatContext }) {
  const { pods, pod, canAdd, onAdd, onOpenPod } = chat;
  switch (block.type) {
    case "text":
      return <p className="whitespace-pre-wrap">{block.text}</p>;
    case "tool_calls":
      return <ToolCallsCard calls={block.calls} />;
    case "product_choices":
      return (
        <div className="mt-2 space-y-2">
          {block.products.map((p) => <ProductRow key={p.id} product={p} qty={block.request.qty} recommended={p.id === block.recommendedId} canAdd={canAdd && p.marketplace === pod.marketplace} onAdd={onAdd} />)}
        </div>
      );
    case "out_of_stock":
      return (
        <div className="mt-2 rounded-xl bg-amber-pale p-3">
          <div className="font-bold text-amber">😕 {block.product?.title ?? block.request.query} is out of stock</div>
          {block.alternatives.length > 0 && <div className="mt-1 text-sm text-slate">Try one of these instead</div>}
          <div className="mt-2 space-y-2">{block.alternatives.map((p) => <ProductRow key={p.id} product={p} qty={block.request.qty} canAdd={canAdd} onAdd={onAdd} />)}</div>
        </div>
      );
    case "cart_summary":
      return (
        <div className="mt-2 rounded-xl bg-white p-3 text-sm">
          <div className="font-bold">🎯 {money(pod.totals.subtotal)} of {money(pod.minimumForFreeShipping)}</div>
          <div className="my-2"><ProgressBar value={pod.totals.progress} /></div>
          <div className="text-slate">{pod.totals.itemCount} items from {pod.totals.buyers} neighbors · {pod.totals.freeShipping ? "free shipping unlocked" : `${money(pod.totals.remaining)} to go`}</div>
        </div>
      );
    case "pod_suggestions":
      return (
        <div className="mt-2 space-y-2">
          <div className="text-sm text-slate">{block.reason}</div>
          {block.podIds.map((id) => {
            const suggested = pods.find((x) => x.id === id);
            return suggested ? (
              <button key={id} onClick={() => onOpenPod(id)} className="flex w-full items-center gap-3 rounded-xl bg-white p-3 text-left">
                <span className="text-2xl">🛒</span>
                <div className="flex-1"><div className="font-bold">{suggested.name}</div><div className="text-xs text-slate">{STORE_NAMES[suggested.marketplace]} · arrives {dayAndTime(suggested.deliveryEta)}</div></div>
                <span className="rounded-full bg-forest px-3 py-1 text-xs font-bold text-white">Open</span>
              </button>
            ) : null;
          })}
        </div>
      );
    case "checkout_review":
      return <CheckoutCard chat={chat} />;
    case "order_placed":
      return (
        <div className="mt-2 rounded-xl bg-white p-3">
          <div className="flex items-center gap-2"><span className="grid h-8 w-8 place-items-center rounded-full bg-forest text-white">✓</span><div><div className="font-bold">Order placed · {block.order.number}</div><div className="text-xs text-slate">Ships with the group order</div></div></div>
          <div className="mt-2 text-sm">{block.order.items.map((i) => <div key={i.title} className="flex justify-between"><span className="truncate pr-2">{i.qty} × {i.title}</span><span>{money(i.total)}</span></div>)}</div>
          <div className="mt-1 flex justify-between border-t border-line pt-1 text-sm font-bold"><span>Total{block.order.fee ? ` incl. ${money(block.order.fee)} fee` : ""}</span><span>{money(block.order.total)}</span></div>
          <div className="mt-2 rounded-lg bg-mint p-2 text-xs text-forest">📦 Pickup {dayAndTime(block.deliveryEta)} · {block.pickupSpot}. Your pickup code shows in Order.</div>
        </div>
      );
    case "event_invite": {
      const event = chat.events.find((e) => e.id === block.eventId);
      if (!event) return null;
      return (
        <div className="mt-2 space-y-2">
          <EventCard event={event} members={chat.members} onOpen={() => chat.onOpenEvent(event.id)} />
          <div className="flex flex-wrap gap-2">
            {["See the table", "Claim a dish", "Just bringing vibes"].map((label) => (
              <button key={label} onClick={() => chat.onOpenEvent(event.id)} className="rounded-full border border-forest/30 bg-white px-3 py-1.5 text-sm font-bold text-forest">{label}</button>
            ))}
          </div>
        </div>
      );
    }
    default:
      return null;
  }
}

const TOOL_ICONS: Record<ToolCall["tool"], string> = { get_pod_details: "📋", search_products: "🔎", find_open_pods: "🗓️" };

/** Shows which tools the agent called and the store pages it found, so neighbors can check the sources. */
function ToolCallsCard({ calls }: { calls: ToolCall[] }) {
  const [open, setOpen] = useState(false);
  if (!calls.length) return null;
  const sources = calls.flatMap((c) => c.sources ?? []);
  return (
    <div className="mb-2 rounded-xl border border-forest/15 bg-white/70 text-xs">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left font-bold text-forest">
        🔧 Used {calls.length} {calls.length === 1 ? "tool" : "tools"}
        <span className="truncate font-normal text-slate">· {calls.map((c) => c.tool).join(", ")}</span>
        <span className="ml-auto">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-forest/10 px-2.5 py-2">
          {calls.map((call, i) => (
            <div key={i}>
              <code className="break-all font-bold text-ink">{TOOL_ICONS[call.tool]} {call.tool}({Object.entries(call.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})</code>
              <div className="text-slate">→ {call.summary}{call.source && ` · ${call.source === "live" ? "live web search" : "saved catalog"}`}</div>
            </div>
          ))}
        </div>
      )}
      {sources.length > 0 && (
        <div className="flex flex-wrap gap-1 border-t border-forest/10 px-2.5 py-1.5">
          <span className="text-slate">Sources:</span>
          {sources.map((s, i) => <a key={i} href={s.url} target="_blank" rel="noreferrer" className="max-w-[160px] truncate rounded-full bg-cream px-2 py-0.5 text-forest underline">{STORE_NAMES[s.marketplace]}: {s.title}</a>)}
        </div>
      )}
    </div>
  );
}

function CheckoutCard({ chat }: { chat: ChatContext }) {
  const { basket, basketFee, pod } = chat;
  if (!basket.length && chat.hasPlaced) return <div className="mt-2 rounded-xl bg-white p-3 text-sm font-bold text-forest">✓ Placed. Your order and pickup pass live in the Order tab.</div>;
  if (!basket.length) return <div className="mt-2 rounded-xl bg-white p-3 text-sm text-slate">Your basket is empty right now. Ask me for something and tap Add.</div>;
  const itemsTotal = basket.reduce((sum, l) => sum + (l.product.price ?? 0) * l.qty, 0);
  return (
    <div className="mt-2 rounded-xl bg-white p-3">
      <div className="mb-1 font-bold">🧺 Your basket</div>
      <div className="mb-1 text-xs text-slate">From {STORE_NAMES[pod.marketplace]}</div>
      {basket.map((l) => <div key={l.id} className="flex justify-between text-sm"><span className="truncate pr-2">{l.qty} × <a href={l.product.url} target="_blank" rel="noreferrer" className="underline decoration-line">{l.product.title}</a></span><span>{money((l.product.price ?? 0) * l.qty)}</span></div>)}
      <div className="mt-1 flex justify-between text-sm text-slate"><span>Shared fee</span><span>{basketFee ? money(basketFee) : "paid ✓"}</span></div>
      <div className="flex justify-between border-t border-line pt-1 font-bold"><span>Total</span><span>{money(itemsTotal + basketFee)}</span></div>
      <button onClick={chat.onPlaceOrder} disabled={pod.status !== "open"} className="mt-2 w-full rounded-full bg-forest py-2.5 font-bold text-white disabled:opacity-40">Place order · {money(itemsTotal + basketFee)}</button>
      <div className="mt-1 text-center text-xs text-slate">Pay {money(itemsTotal + basketFee)} by Venmo or Zelle after pickup.</div>
    </div>
  );
}

function ProductRow({ product, qty: initialQty, recommended, canAdd, onAdd }: { product: Product; qty: number; recommended?: boolean; canAdd: boolean; onAdd: (p: Product, qty: number) => void }) {
  const [qty, setQty] = useState(initialQty);
  const blocked = product.inStock === false || product.price == null || !canAdd;
  return (
    <div className={`relative flex gap-3 rounded-xl bg-white p-2.5 ${recommended ? "ring-2 ring-forest" : ""}`}>
      {recommended && <span className="absolute -top-2.5 right-2 rotate-3 rounded-full bg-berry px-2 py-0.5 text-[11px] font-bold text-white">⭐ Best match</span>}
      <span className="grid h-16 w-16 shrink-0 place-items-center rounded-lg bg-cream text-3xl">{productEmoji(product.title)}</span>
      <div className="min-w-0 flex-1">
        <a href={product.url} target="_blank" rel="noreferrer" className="line-clamp-2 text-sm font-bold leading-snug text-ink">{product.title}</a>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate">
          <SourceBadge marketplace={product.marketplace} url={product.url} source={product.source} />
          <span className={product.inStock === false ? "text-berry" : product.inStock ? "text-forest" : "text-amber"}>{product.inStock === false ? "Out of stock" : product.inStock ? "In stock" : "Check stock"}</span>
        </div>
        <div className="mt-1.5 flex items-center gap-1.5">
          <span className="mr-auto font-bold">{money(product.price)}</span>
          <button onClick={() => setQty(Math.max(1, qty - 1))} className="h-8 w-8 rounded-lg border border-forest/40 text-forest">−</button>
          <span className="w-5 text-center text-sm font-bold">{qty}</span>
          <button onClick={() => setQty(Math.min(20, qty + 1))} className="h-8 w-8 rounded-lg border border-forest/40 text-forest">+</button>
          <button disabled={blocked} onClick={() => onAdd(product, qty)} className="h-8 rounded-full bg-forest px-3.5 text-sm font-bold text-white disabled:bg-line disabled:text-slate">Add</button>
        </div>
      </div>
    </div>
  );
}
