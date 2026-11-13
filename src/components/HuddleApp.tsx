"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Block, CartLine, ChatMessage, Member, Pod, Product } from "@/lib/types";
import { useMe } from "./useMe";

type PodWithTotals = Pod & { totals: Totals };
type Totals = { subtotal: number; remaining: number; progress: number; freeShipping: boolean; itemCount: number; buyers: number };
type Badge = { id: string; label: string; emoji: string };
type MemberStats = {
  memberId: string; name: string; items: number; orders: number; streak_weeks: number; shipping_saved: number;
  badges: Badge[]; level: { level: number; title: string; xp: number; nextLevelXp: number; progress: number };
};
type Community = { members: Record<string, MemberStats>; leaderboard: { memberId: string; name: string; xp: number; level: number }[]; funFacts: string[]; buildingSavings: number; questRewardXp: number };
type PodDetail = { pod: PodWithTotals; members: Member[]; cart: CartLine[]; messages: ChatMessage[]; pickups: Record<string, { paid: boolean; collected: boolean }> };
type Bag = { bag: number; memberId: string; name: string; items: { title: string; qty: number; total: number }[]; amountDue: number; fee: number; venmo: string | null; zelle: string | null; paid: boolean; collected: boolean };

const STORE_NAMES = { weee: "Weee!", amazon_fresh: "Amazon Fresh" } as const;
const AVATAR_COLORS = ["#f47b67", "#5865f2", "#3ba55c", "#faa61a", "#eb459e", "#45ddc0"];
const SUGGESTIONS = ["2 shrimp chips", "cheddar cheese by tomorrow", "frozen dumplings", "how close are we?"];
const NEXT_STEP: Record<string, { action: string; label: string } | undefined> = {
  open: { action: "lock", label: "Lock cart" },
  locked: { action: "ordered", label: "Mark ordered" },
  ordered: { action: "arrived", label: "It arrived" },
  arrived: { action: "close", label: "Close pod" },
};

const money = (n: number | null | undefined) => (n == null ? "?" : `$${n.toFixed(2)}`);
const colorFor = (id: string) => AVATAR_COLORS[[...id].reduce((s, c) => s + c.charCodeAt(0), 0) % AVATAR_COLORS.length];
const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
const timeOf = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
const cutoffLabel = (iso: string) => new Date(iso).toLocaleString([], { weekday: "short", hour: "numeric" });

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { "Content-Type": "application/json" } });
  return res.json();
}

function Avatar({ id, name, size = 40, bot = false }: { id: string; name: string; size?: number; bot?: boolean }) {
  return (
    <div className="grid shrink-0 place-items-center rounded-full font-bold text-white" style={{ width: size, height: size, background: bot ? "#1f5c4a" : colorFor(id), fontSize: size * 0.38 }}>
      {bot ? "🛒" : initials(name)}
    </div>
  );
}

function Bar({ value, className = "bg-lime" }: { value: number; className?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/30">
      <div className={`h-full rounded-full transition-all ${className}`} style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  );
}

export default function HuddleApp({ initialPodId = "the-house" }: { initialPodId?: string }) {
  const [me, setMe] = useMe();
  const [pods, setPods] = useState<PodWithTotals[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [community, setCommunity] = useState<Community | null>(null);
  const [channel, setChannel] = useState<string>(initialPodId);
  const [detail, setDetail] = useState<PodDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [panel, setPanel] = useState<"none" | "cart" | "bags" | "nav" | "members">("none");
  const [bags, setBags] = useState<Bag[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const onLeaderboard = channel === "leaderboard";
  const pod = detail?.pod;
  const iLead = pod?.leaderId === me;
  const nameOf = (id: string) => (id === "huddlecart" ? "HuddleCart" : members.find((m) => m.id === id)?.name ?? id);

  const refresh = useCallback(async () => {
    const [all, game] = await Promise.all([api<{ pods: PodWithTotals[]; members: Member[] }>("/api/pods"), api<Community>("/api/community")]);
    setPods(all.pods);
    setMembers(all.members);
    setCommunity(game);
    if (channel !== "leaderboard") setDetail(await api<PodDetail>(`/api/pods?podId=${channel}`));
  }, [channel]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail?.messages.length, thinking]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(timer);
  }, [toast]);

  function openChannel(id: string) {
    setChannel(id);
    setDetail(null);
    setPanel("none");
    window.history.replaceState(null, "", id === "leaderboard" ? "/" : `/pod/${id}`);
  }

  async function send(text: string) {
    if (!text.trim() || !pod) return;
    setDraft("");
    setThinking(true);
    const optimistic: ChatMessage = { id: "pending", podId: pod.id, authorId: me, role: "user", blocks: [{ type: "text", text }], createdAt: new Date().toISOString() };
    setDetail((d) => (d ? { ...d, messages: [...d.messages, optimistic] } : d));
    await api("/api/chat", { method: "POST", body: JSON.stringify({ podId: pod.id, memberId: me, text }) });
    setThinking(false);
    refresh();
  }

  async function addToCart(product: Product, qty: number) {
    if (!pod) return;
    const result = await api<{ ok: boolean; reason?: string }>("/api/cart", {
      method: "POST",
      body: JSON.stringify({ podId: pod.id, memberId: me, product, qty, requestId: crypto.randomUUID() }),
    });
    setToast(result.ok ? `+${qty * 10} XP · Added ${qty} × ${product.title}` : result.reason ?? "Couldn't add that");
    refresh();
  }

  async function removeLine(lineId: string) {
    await api("/api/cart", { method: "DELETE", body: JSON.stringify({ lineId, memberId: me }) });
    refresh();
  }

  async function delivery(action: string, targetId?: string) {
    if (!pod) return;
    const result = await api<{ ok: boolean; error?: string }>("/api/delivery", { method: "POST", body: JSON.stringify({ podId: pod.id, memberId: me, action, targetId }) });
    if (!result.ok) setToast(result.error ?? "Not allowed");
    await refresh();
    if (panel === "bags" || action === "arrived") loadBags();
  }

  async function loadBags() {
    if (!pod) return;
    const result = await api<{ bags: Bag[] }>(`/api/delivery?podId=${pod.id}`);
    setBags(result.bags);
    setPanel("bags");
  }

  const myStats = community?.members[me];
  const buildings = [...new Set(pods.map((p) => p.building))];

  const sidebar = (
    <div className="flex h-full">
      <nav className="flex w-[72px] flex-col items-center gap-2 bg-[#1e1f22] py-3">
        <Link href="/" className="grid h-12 w-12 place-items-center rounded-2xl bg-forest text-2xl">🛒</Link>
        <div className="h-0.5 w-8 rounded bg-white/10" />
        {buildings.map((b) => (
          <button key={b} title={b} onClick={() => openChannel(pods.find((p) => p.building === b)!.id)}
            className={`grid h-12 w-12 place-items-center rounded-[24px] text-sm font-bold text-white transition-all hover:rounded-2xl ${pod?.building === b ? "rounded-2xl bg-forest" : "bg-[#313338]"}`}>
            {initials(b.split(",")[0])}
          </button>
        ))}
        <button title="Start a pod (coming soon)" className="grid h-12 w-12 place-items-center rounded-[24px] bg-[#313338] text-2xl text-[#3ba55c]">+</button>
      </nav>
      <aside className="flex w-60 flex-col bg-[#2b2d31]">
        <div className="border-b border-black/30 px-4 py-3 font-bold text-white shadow">{pod?.building.split(",")[0] ?? "HuddleCart"}</div>
        <div className="flex-1 overflow-y-auto px-2 py-3 text-[15px]">
          <div className="px-2 pb-1 text-xs font-bold uppercase tracking-wide text-[#949ba4]">Order pods</div>
          {pods.map((p) => (
            <button key={p.id} onClick={() => openChannel(p.id)}
              className={`mb-0.5 w-full rounded px-2 py-1.5 text-left ${channel === p.id ? "bg-[#404249] text-white" : "text-[#949ba4] hover:bg-[#35373c] hover:text-[#dbdee1]"}`}>
              <div className="flex items-center gap-1.5">
                <span className="text-lg leading-none text-[#80848e]">#</span>
                <span className="flex-1 truncate">{p.name.toLowerCase().replace(/\s+/g, "-")}</span>
                {p.status === "open" ? <span className="h-2 w-2 rounded-full bg-[#3ba55c]" /> : <span className="text-[10px] uppercase">{p.status}</span>}
              </div>
              <div className="ml-5 mt-1"><Bar value={p.totals.progress} /></div>
            </button>
          ))}
          <div className="px-2 pb-1 pt-4 text-xs font-bold uppercase tracking-wide text-[#949ba4]">Community</div>
          <button onClick={() => openChannel("leaderboard")}
            className={`w-full rounded px-2 py-1.5 text-left ${onLeaderboard ? "bg-[#404249] text-white" : "text-[#949ba4] hover:bg-[#35373c]"}`}>
            🏆 leaderboard
          </button>
        </div>
        <div className="flex items-center gap-2 bg-[#232428] px-2 py-2">
          <Avatar id={me} name={nameOf(me)} size={34} />
          <div className="min-w-0 flex-1">
            <select value={me} onChange={(e) => setMe(e.target.value)} className="w-full bg-transparent text-sm font-semibold text-white outline-none">
              {members.map((m) => <option key={m.id} value={m.id} className="bg-[#2b2d31]">{m.name}</option>)}
            </select>
            {myStats && (
              <>
                <div className="text-[11px] text-[#b5bac1]">Lv {myStats.level.level} {myStats.level.title} · 🔥{myStats.streak_weeks}w</div>
                <Bar value={myStats.level.progress} className="bg-[#5865f2]" />
              </>
            )}
          </div>
        </div>
      </aside>
    </div>
  );

  const memberList = pod && community && (
    <aside className="w-60 overflow-y-auto bg-[#2b2d31] px-3 py-4 text-sm">
      <div className="mb-4 rounded-lg bg-[#1e1f22] p-3">
        <div className="text-xs font-bold uppercase text-lime">Pod quest</div>
        <div className="mt-1 text-[#dbdee1]">{pod.totals.freeShipping ? "Free shipping unlocked!" : `${money(pod.totals.remaining)} to free shipping`}</div>
        <div className="my-2"><Bar value={pod.totals.progress} /></div>
        <div className="text-xs text-[#949ba4]">Everyone gets +{community.questRewardXp} XP when it fills</div>
      </div>
      {[{ title: "Leader", ids: [pod.leaderId] }, { title: "Neighbors", ids: pod.memberIds.filter((id) => id !== pod.leaderId) }].map((group) => (
        <div key={group.title} className="mb-4">
          <div className="mb-1 text-xs font-bold uppercase text-[#949ba4]">{group.title} — {group.ids.length}</div>
          {group.ids.map((id) => {
            const stats = community.members[id];
            return (
              <div key={id} className="flex items-center gap-2 rounded px-1 py-1.5 hover:bg-[#35373c]">
                <Avatar id={id} name={nameOf(id)} size={32} />
                <div className="min-w-0">
                  <div className="truncate font-medium" style={{ color: colorFor(id) }}>{nameOf(id)} {group.title === "Leader" && "👑"}</div>
                  <div className="truncate text-xs text-[#949ba4]">Lv {stats?.level.level} · {stats?.badges.map((b) => b.emoji).join(" ")}</div>
                </div>
              </div>
            );
          })}
        </div>
      ))}
      <div className="mb-1 text-xs font-bold uppercase text-[#949ba4]">This week</div>
      {community.funFacts.map((fact) => <div key={fact} className="mb-1.5 rounded bg-[#1e1f22] px-2 py-1.5 text-xs text-[#dbdee1]">🎉 {fact}</div>)}
    </aside>
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-[#313338] text-[#dbdee1]">
      <div className="hidden md:flex">{sidebar}</div>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 border-b border-black/30 px-3 py-2.5 shadow-sm">
          <button className="text-xl md:hidden" onClick={() => setPanel("nav")}>☰</button>
          {onLeaderboard ? <div className="font-bold text-white">🏆 leaderboard</div> : pod && (
            <>
              <span className="text-2xl leading-none text-[#80848e]">#</span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-bold text-white">{pod.name}</div>
                <div className="truncate text-xs text-[#949ba4]">{STORE_NAMES[pod.marketplace]} · cutoff {cutoffLabel(pod.cutoff)} · pickup {pod.pickupSpot}</div>
              </div>
              <button onClick={() => setPanel("cart")} className="rounded-full bg-forest px-3 py-1 text-sm font-semibold text-lime">🛒 {pod.totals.itemCount}</button>
              <button className="text-lg lg:hidden" onClick={() => setPanel("members")}>👥</button>
            </>
          )}
        </header>

        {pod && !onLeaderboard && iLead && (
          <div className="flex items-center gap-2 bg-forest/40 px-3 py-1.5 text-sm">
            <span className="flex-1">👑 You lead this pod · {pod.status}</span>
            {pod.status !== "open" && <button onClick={loadBags} className="rounded bg-white/10 px-2.5 py-1">Bags</button>}
            {NEXT_STEP[pod.status] && <button onClick={() => delivery(NEXT_STEP[pod.status]!.action)} className="rounded bg-lime px-2.5 py-1 font-semibold text-forest-deep">{NEXT_STEP[pod.status]!.label}</button>}
          </div>
        )}

        {onLeaderboard ? <Leaderboard community={community} /> : (
          <>
            <div className="flex-1 overflow-y-auto py-3">
              <Welcome pod={pod} />
              {detail?.messages.map((message) => (
                <Message key={message.id} message={message} author={nameOf(message.authorId)} pods={pods} onAdd={addToCart} onOpenPod={openChannel} pod={pod} canAdd={pod?.status === "open"} />
              ))}
              {thinking && <div className="px-4 py-2 text-sm text-[#949ba4]">🛒 HuddleCart is checking Weee and Amazon…</div>}
              {pod && pod.status === "arrived" && !iLead && <PickupCard podId={pod.id} me={me} onDone={() => delivery("collected")} />}
              <div ref={bottom} />
            </div>
            <div className="px-3 pb-3">
              <div className="no-scrollbar mb-2 flex gap-2 overflow-x-auto">
                {SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} disabled={thinking || pod?.status !== "open"} className="shrink-0 rounded-full border border-white/10 px-3 py-1 text-xs text-[#b5bac1] hover:bg-white/5 disabled:opacity-40">{s}</button>)}
              </div>
              <form onSubmit={(e) => { e.preventDefault(); send(draft); }} className="flex items-center gap-2 rounded-lg bg-[#383a40] px-3 py-2.5">
                <input value={draft} onChange={(e) => setDraft(e.target.value)} disabled={thinking || pod?.status !== "open"}
                  placeholder={pod?.status === "open" ? `Message #${pod?.name.toLowerCase().replace(/\s+/g, "-")} or ask HuddleCart` : "Cart is locked"}
                  className="flex-1 bg-transparent text-[15px] text-white placeholder-[#6d6f78] outline-none" />
                <button disabled={!draft.trim() || thinking} className="font-semibold text-lime disabled:opacity-30">Send</button>
              </form>
            </div>
          </>
        )}
      </main>

      <div className="hidden lg:flex">{!onLeaderboard && memberList}</div>

      {panel === "nav" && <Drawer side="left" onClose={() => setPanel("none")}>{sidebar}</Drawer>}
      {panel === "members" && <Drawer side="right" onClose={() => setPanel("none")}>{memberList}</Drawer>}
      {panel === "cart" && detail && <Drawer side="right" onClose={() => setPanel("none")}><CartPanel detail={detail} me={me} nameOf={nameOf} onRemove={removeLine} /></Drawer>}
      {panel === "bags" && pod && <Drawer side="right" onClose={() => setPanel("none")}><BagsPanel bags={bags} onMark={async (action, id) => { await delivery(action, id); loadBags(); }} /></Drawer>}
      {toast && <div className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-full bg-[#111214] px-4 py-2 text-sm font-medium text-lime shadow-xl">{toast}</div>}
    </div>
  );
}

function Drawer({ side, onClose, children }: { side: "left" | "right"; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex bg-black/60" onClick={onClose}>
      <div className={`flex h-full max-w-[90vw] ${side === "right" ? "ml-auto" : ""}`} onClick={(e) => e.stopPropagation()}>{children}</div>
    </div>
  );
}

function Welcome({ pod }: { pod?: PodWithTotals }) {
  if (!pod) return <div className="px-4 py-6 text-[#949ba4]">Loading…</div>;
  return (
    <div className="mx-4 mb-4 border-b border-white/5 pb-4">
      <div className="mb-2 grid h-16 w-16 place-items-center rounded-full bg-[#41434a] text-3xl">#</div>
      <div className="text-2xl font-bold text-white">Welcome to #{pod.name}</div>
      <div className="text-sm text-[#949ba4]">One {STORE_NAMES[pod.marketplace]} order for {pod.building}. Tell HuddleCart what you want, tap Add, pay {money(pod.feePerPerson)} instead of $5 shipping.</div>
    </div>
  );
}

function Message({ message, author, pods, pod, canAdd, onAdd, onOpenPod }: {
  message: ChatMessage; author: string; pods: PodWithTotals[]; pod?: PodWithTotals; canAdd: boolean;
  onAdd: (p: Product, qty: number) => void; onOpenPod: (id: string) => void;
}) {
  if (message.role === "system") {
    return <div className="mx-4 my-2 flex items-center gap-2 text-sm text-[#949ba4]"><span className="text-[#3ba55c]">➜</span>{message.blocks.map((b) => (b.type === "text" ? b.text : "")).join(" ")}<span className="text-xs">{timeOf(message.createdAt)}</span></div>;
  }
  const isBot = message.role === "agent";
  return (
    <div className="flex gap-3 px-4 py-1.5 hover:bg-[#2e3035]">
      <Avatar id={message.authorId} name={author} bot={isBot} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="font-semibold" style={{ color: isBot ? "#d9f07a" : colorFor(message.authorId) }}>{author}</span>
          {isBot && <span className="rounded bg-[#5865f2] px-1 text-[10px] font-bold text-white">AGENT</span>}
          <span className="text-xs text-[#949ba4]">{timeOf(message.createdAt)}</span>
        </div>
        {message.blocks.map((block, i) => <BlockView key={i} block={block} pods={pods} pod={pod} canAdd={canAdd} onAdd={onAdd} onOpenPod={onOpenPod} />)}
      </div>
    </div>
  );
}

function BlockView({ block, pods, pod, canAdd, onAdd, onOpenPod }: {
  block: Block; pods: PodWithTotals[]; pod?: PodWithTotals; canAdd: boolean; onAdd: (p: Product, qty: number) => void; onOpenPod: (id: string) => void;
}) {
  switch (block.type) {
    case "text":
      return <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{block.text}</p>;
    case "product_choices":
      return (
        <div className="mt-2">
          <div className="mb-1.5 text-xs text-[#949ba4]">For “{block.request.query}” × {block.request.qty}{block.reason ? ` · ${block.reason}` : ""}</div>
          <div className="no-scrollbar flex gap-2 overflow-x-auto pb-1">
            {block.products.map((p) => <ProductCard key={p.id} product={p} qty={block.request.qty} recommended={p.id === block.recommendedId} canAdd={canAdd && p.marketplace === pod?.marketplace} onAdd={onAdd} />)}
          </div>
        </div>
      );
    case "out_of_stock":
      return (
        <div className="mt-2 rounded-lg border-l-4 border-clay bg-[#2b2d31] p-3">
          <div className="text-sm font-semibold text-[#f0a58b]">⚠️ {block.product?.title ?? block.request.query} is out of stock</div>
          {block.alternatives.length > 0 && <div className="mb-1.5 mt-1 text-xs text-[#949ba4]">Try one of these instead</div>}
          <div className="no-scrollbar flex gap-2 overflow-x-auto">
            {block.alternatives.map((p) => <ProductCard key={p.id} product={p} qty={block.request.qty} canAdd={canAdd} onAdd={onAdd} />)}
          </div>
        </div>
      );
    case "cart_summary":
      return pod ? (
        <div className="mt-2 max-w-sm rounded-lg bg-[#2b2d31] p-3 text-sm">
          <div className="font-semibold text-white">🎯 Pod quest: {money(pod.totals.subtotal)} of {money(pod.minimumForFreeShipping)}</div>
          <div className="my-2"><Bar value={pod.totals.progress} /></div>
          <div className="text-[#949ba4]">{pod.totals.itemCount} items from {pod.totals.buyers} neighbors · {pod.totals.freeShipping ? "free shipping unlocked" : `${money(pod.totals.remaining)} to go`}</div>
        </div>
      ) : null;
    case "pod_suggestions":
      return (
        <div className="mt-2 space-y-1.5">
          <div className="text-xs text-[#949ba4]">{block.reason}</div>
          {block.podIds.map((id) => {
            const p = pods.find((x) => x.id === id);
            return p ? (
              <button key={id} onClick={() => onOpenPod(id)} className="flex w-full max-w-sm items-center gap-3 rounded-lg bg-[#2b2d31] p-3 text-left hover:bg-[#35373c]">
                <span className="text-2xl text-[#80848e]">#</span>
                <div className="flex-1">
                  <div className="font-semibold text-white">{p.name}</div>
                  <div className="text-xs text-[#949ba4]">{STORE_NAMES[p.marketplace]} · arrives {cutoffLabel(p.deliveryEta)} · {p.totals.buyers} buying</div>
                </div>
                <span className="rounded bg-[#3ba55c] px-2 py-1 text-xs font-semibold text-white">Join</span>
              </button>
            ) : null;
          })}
        </div>
      );
    default:
      return null;
  }
}

function ProductCard({ product, qty: initialQty, recommended, canAdd, onAdd }: { product: Product; qty: number; recommended?: boolean; canAdd: boolean; onAdd: (p: Product, qty: number) => void }) {
  const [qty, setQty] = useState(initialQty);
  const blocked = product.inStock === false || product.price == null || !canAdd;
  return (
    <div className={`w-44 shrink-0 rounded-lg bg-[#2b2d31] p-2.5 ${recommended ? "ring-2 ring-lime" : ""}`}>
      {recommended && <div className="mb-1 text-[10px] font-bold uppercase text-lime">★ Best match</div>}
      <div className="line-clamp-2 h-10 text-sm font-medium text-white">{product.title}</div>
      <div className="mt-1 flex items-center justify-between text-xs">
        <span className="text-base font-bold text-white">{money(product.price)}</span>
        <span className={product.inStock === false ? "text-clay" : product.inStock ? "text-[#3ba55c]" : "text-[#faa61a]"}>
          {product.inStock === false ? "Out of stock" : product.inStock ? "In stock" : "Check stock"}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-1.5">
        <button onClick={() => setQty(Math.max(1, qty - 1))} className="h-7 w-7 rounded bg-[#1e1f22]">−</button>
        <span className="w-5 text-center text-sm">{qty}</span>
        <button onClick={() => setQty(Math.min(20, qty + 1))} className="h-7 w-7 rounded bg-[#1e1f22]">+</button>
        <button disabled={blocked} onClick={() => onAdd(product, qty)} className="ml-auto h-7 rounded bg-lime px-3 text-sm font-semibold text-forest-deep disabled:bg-[#41434a] disabled:text-[#80848e]">Add</button>
      </div>
      <a href={product.url} target="_blank" rel="noreferrer" className="mt-1.5 block truncate text-[10px] text-[#949ba4] hover:underline">
        {STORE_NAMES[product.marketplace]} · {product.source === "live" ? "live search" : "catalog"}
      </a>
    </div>
  );
}

function CartPanel({ detail, me, nameOf, onRemove }: { detail: PodDetail; me: string; nameOf: (id: string) => string; onRemove: (id: string) => void }) {
  const byMember = detail.cart.reduce<Record<string, CartLine[]>>((acc, line) => ({ ...acc, [line.memberId]: [...(acc[line.memberId] ?? []), line] }), {});
  const { pod } = detail;
  return (
    <div className="w-80 overflow-y-auto bg-[#2b2d31] p-4">
      <div className="text-lg font-bold text-white">Shared cart</div>
      <div className="my-2"><Bar value={pod.totals.progress} /></div>
      <div className="mb-4 text-sm text-[#949ba4]">{money(pod.totals.subtotal)} of {money(pod.minimumForFreeShipping)} · {pod.totals.freeShipping ? "free shipping 🎉" : `${money(pod.totals.remaining)} to go`}</div>
      {Object.keys(byMember).length === 0 && <div className="text-sm text-[#949ba4]">Empty so far. Ask HuddleCart for something!</div>}
      {Object.entries(byMember).map(([memberId, lines]) => {
        const items = lines.reduce((s, l) => s + (l.product.price ?? 0) * l.qty, 0);
        return (
          <div key={memberId} className="mb-3 rounded-lg bg-[#1e1f22] p-3">
            <div className="mb-1 flex items-center gap-2"><Avatar id={memberId} name={nameOf(memberId)} size={22} /><span className="font-semibold text-white">{nameOf(memberId)}</span><span className="ml-auto text-sm">{money(items + pod.feePerPerson)}</span></div>
            {lines.map((l) => (
              <div key={l.id} className="flex items-center gap-2 py-0.5 text-sm">
                <span className="flex-1 truncate">{l.qty} × {l.product.title}</span>
                <span>{money((l.product.price ?? 0) * l.qty)}</span>
                {(memberId === me || pod.leaderId === me) && pod.status === "open" && <button onClick={() => onRemove(l.id)} className="text-[#949ba4] hover:text-clay">✕</button>}
              </div>
            ))}
            <div className="text-xs text-[#949ba4]">incl. {money(pod.feePerPerson)} pod fee</div>
          </div>
        );
      })}
    </div>
  );
}

function BagsPanel({ bags, onMark }: { bags: Bag[]; onMark: (action: string, memberId: string) => void }) {
  return (
    <div className="w-80 overflow-y-auto bg-[#2b2d31] p-4">
      <div className="mb-3 text-lg font-bold text-white">Bags to pack</div>
      {bags.map((b) => (
        <div key={b.bag} className="mb-3 rounded-lg bg-[#1e1f22] p-3 text-sm">
          <div className="flex items-center"><span className="mr-2 rounded bg-lime px-2 font-bold text-forest-deep">#{b.bag}</span><span className="font-semibold text-white">{b.name}</span><span className="ml-auto font-bold">{money(b.amountDue)}</span></div>
          {b.items.map((i) => <div key={i.title} className="mt-1 text-[#b5bac1]">{i.qty} × {i.title}</div>)}
          <div className="mt-2 flex gap-2">
            <button onClick={() => onMark("paid", b.memberId)} className={`flex-1 rounded py-1 ${b.paid ? "bg-[#3ba55c] text-white" : "bg-white/10"}`}>{b.paid ? "Paid ✓" : "Mark paid"}</button>
            <button onClick={() => onMark("collected", b.memberId)} className={`flex-1 rounded py-1 ${b.collected ? "bg-[#3ba55c] text-white" : "bg-white/10"}`}>{b.collected ? "Picked up ✓" : "Picked up"}</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function PickupCard({ podId, me, onDone }: { podId: string; me: string; onDone: () => Promise<void> }) {
  const [bag, setBag] = useState<Bag | null>(null);
  const loadBag = useCallback(() => api<{ bags: Bag[] }>(`/api/delivery?podId=${podId}`).then((r) => setBag(r.bags.find((b) => b.memberId === me) ?? null)), [podId, me]);
  useEffect(() => { loadBag(); }, [loadBag]);
  if (!bag) return null;
  return (
    <div className="mx-4 my-3 max-w-sm rounded-lg border border-lime/40 bg-[#2b2d31] p-4">
      <div className="text-xs font-bold uppercase text-lime">Your bag is ready</div>
      <div className="mt-1 text-2xl font-bold text-white">Bag #{bag.bag} · {money(bag.amountDue)}</div>
      <div className="mt-3 flex gap-2 text-sm">
        {bag.venmo && <a href={bag.venmo} target="_blank" rel="noreferrer" className="flex-1 rounded bg-[#008cff] py-1.5 text-center font-semibold text-white">Pay with Venmo</a>}
        <button onClick={async () => { await onDone(); loadBag(); }} disabled={bag.collected} className="flex-1 rounded bg-lime py-1.5 font-semibold text-forest-deep disabled:opacity-50">{bag.collected ? "Picked up ✓" : "I picked it up"}</button>
      </div>
      {bag.zelle && <div className="mt-2 text-xs text-[#949ba4]">or Zelle {bag.zelle}</div>}
    </div>
  );
}

function Leaderboard({ community }: { community: Community | null }) {
  if (!community) return null;
  const medals = ["🥇", "🥈", "🥉"];
  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mb-4 rounded-xl bg-forest p-4">
        <div className="text-sm text-lime">Building savings so far</div>
        <div className="text-3xl font-bold text-white">${community.buildingSavings} saved on shipping</div>
        <div className="text-sm text-white/70">Every pod order saves each neighbor $3 versus ordering alone.</div>
      </div>
      <div className="mb-2 text-xs font-bold uppercase text-[#949ba4]">Top neighbors</div>
      {community.leaderboard.map((row, i) => {
        const stats = community.members[row.memberId];
        return (
          <div key={row.memberId} className="mb-2 flex items-center gap-3 rounded-lg bg-[#2b2d31] p-3">
            <span className="w-6 text-center text-lg">{medals[i] ?? i + 1}</span>
            <Avatar id={row.memberId} name={row.name} size={36} />
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-white">{row.name} <span className="text-xs text-[#949ba4]">Lv {row.level} {stats.level.title}</span></div>
              <div className="flex flex-wrap gap-1 pt-1">{stats.badges.map((b) => <span key={b.id} className="rounded-full bg-[#1e1f22] px-2 py-0.5 text-xs">{b.emoji} {b.label}</span>)}</div>
            </div>
            <div className="text-right"><div className="font-bold text-lime">{row.xp} XP</div><div className="text-xs text-[#949ba4]">🔥 {stats.streak_weeks}w streak</div></div>
          </div>
        );
      })}
      <div className="mb-2 mt-4 text-xs font-bold uppercase text-[#949ba4]">This week in the building</div>
      {community.funFacts.map((f) => <div key={f} className="mb-1.5 rounded bg-[#2b2d31] px-3 py-2 text-sm">🎉 {f}</div>)}
    </div>
  );
}
