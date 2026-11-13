"use client";

import { useState } from "react";
import type { CommunityEvent, Member, Menus } from "@/lib/types";
import { Avatar, Sheet, api, dayAndTime, primaryButton, shortBuilding, timeLeft, type PodWithTotals } from "./shared";

const DAYS_AHEAD = [1, 2, 3, 4, 5];

export function EventCard({ event, members, onOpen, compact = false }: { event: CommunityEvent; members: Member[]; onOpen: () => void; compact?: boolean }) {
  const host = members.find((m) => m.id === event.hostId)?.name ?? event.hostId;
  const closesIn = event.podStatus === "open" ? timeLeft(event.closesAt) : null;
  return (
    <button onClick={onOpen} className={`flex flex-col gap-2 rounded-[14px] bg-cream p-4 text-left transition active:scale-[0.99] ${compact ? "w-[270px] shrink-0" : "w-full"}`}>
      <div className="flex w-full items-center">
        <span className="mr-2 text-2xl">{event.emoji}</span>
        <span className="flex-1 text-[17px] font-bold text-ink">{event.title}</span>
        <span className="text-[13px] font-bold text-forest">Open ›</span>
      </div>
      <div className="text-sm text-slate">{host} is hosting · {dayAndTime(event.date)}</div>
      <div className="w-full rounded-[10px] bg-mint p-3">
        <div className="flex justify-between text-[15px]"><span className="font-bold text-forest">{event.claimedCount} of {event.dishCount} dishes claimed</span><span className="text-sm text-slate">{event.comingCount} coming</span></div>
        <div className="my-2 h-1.5 w-full overflow-hidden rounded-full bg-white"><div className="h-full rounded-full bg-forest" style={{ width: `${(event.claimedCount / Math.max(1, event.dishCount)) * 100}%` }} /></div>
        <div className="truncate text-sm text-slate">{event.upForGrabs.length ? `Nobody is making: ${event.upForGrabs.join(", ").toLowerCase()}` : "Every dish is claimed 🎉"}</div>
      </div>
      <div className="flex w-full items-center gap-2 text-sm">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/figma/schedule.svg" alt="" width={18} height={18} />
        <span className="flex-1 font-bold text-ink">{closesIn ? `Closes in ${closesIn}` : "The menu is set"}</span>
        <span className="flex -space-x-2">{[event.hostId, ...event.dishes.map((d) => d.cookId).filter(Boolean)].slice(0, 4).map((id, i) => <Avatar key={`${id}-${i}`} id={id!} name={members.find((m) => m.id === id)?.name ?? id!} size={22} />)}</span>
      </div>
    </button>
  );
}

export default function CommunityScreen({ events, menus, pods, members, me, header, onOpenEvent, onHosted }: {
  events: CommunityEvent[]; menus: Menus | null; pods: PodWithTotals[]; members: Member[]; me: string; header: React.ReactNode;
  onOpenEvent: (eventId: string) => void; onHosted: (eventId: string, message: string) => void;
}) {
  const [hosting, setHosting] = useState(false);
  const building = pods[0]?.building;
  return (
    <div className="flex-1 overflow-y-auto">
      {header}
      <div className="space-y-4 px-5 pb-8">
        <div className="-mt-2 text-sm text-slate">{building && shortBuilding(building)} · {members.length} neighbors</div>
        <button onClick={() => setHosting(true)} className="flex w-full items-center gap-3 rounded-2xl bg-forest p-4 text-left text-white">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-white/15 text-2xl">+</span>
          <span><span className="block font-bold">Host an event</span><span className="text-sm text-white/80">Pick a menu, neighbors claim dishes, ingredients join the order.</span></span>
        </button>
        <div className="flex items-baseline justify-between"><h2 className="text-lg font-bold">Happening at {building && shortBuilding(building)}</h2><span className="text-sm text-slate">{events.length} open</span></div>
        {events.map((event) => <EventCard key={event.id} event={event} members={members} onOpen={() => onOpenEvent(event.id)} />)}
        <div className="rounded-2xl bg-amber-pale p-4 text-sm">
          <div className="font-bold text-amber">Not cooking?</div>
          Come anyway and bring the vibes. Every event is open to the whole building.
        </div>
      </div>
      {hosting && menus && <HostEventSheet menus={menus} pods={pods} me={me} onClose={() => setHosting(false)} onHosted={(id, message) => { setHosting(false); onHosted(id, message); }} />}
    </div>
  );
}

function HostEventSheet({ menus, pods, me, onClose, onHosted }: { menus: Menus; pods: PodWithTotals[]; me: string; onClose: () => void; onHosted: (eventId: string, message: string) => void }) {
  const openPods = pods.filter((p) => p.status === "open");
  const [step, setStep] = useState<"details" | "menu">("details");
  const [occasion, setOccasion] = useState("holiday");
  const [title, setTitle] = useState("");
  const [guests, setGuests] = useState(8);
  const [daysAhead, setDaysAhead] = useState(3);
  const [podId, setPodId] = useState(openPods[0]?.id ?? "");
  const [avoid, setAvoid] = useState("");
  const [cooking, setCooking] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const menu = menus[occasion];
  const eventDate = (() => { const d = new Date(); d.setDate(d.getDate() + daysAhead); d.setHours(19, 0, 0, 0); return d; })();

  function toggleCooking(name: string, cook: boolean) {
    const next = new Set(cooking);
    if (cook) next.add(name); else next.delete(name);
    setCooking(next);
  }

  async function sendInvite() {
    const result = await api<{ ok: boolean; reason?: string; event?: { id: string } }>("/api/events", {
      method: "POST",
      body: JSON.stringify({ hostId: me, podId, occasion, title: title || menu.title, date: eventDate.toISOString(), guests, avoid: avoid || null, cooking: [...cooking] }),
    });
    if (!result.ok || !result.event) return setError(result.reason ?? "Couldn't create the event");
    onHosted(result.event.id, cooking.size ? `Invite sent! Ingredients for your ${cooking.size} dishes are in your basket.` : "Invite sent to the pod chat!");
  }

  if (step === "menu") {
    return (
      <Sheet title="Pick your menu" onClose={onClose}>
        <div className="mb-3 rounded-xl bg-mint p-3 text-sm">Ideas for <b>{title || menu.title}</b> for {guests}{avoid ? `, ${avoid.toLowerCase()}` : ""}. Say which you will cook and which you hope a guest brings.</div>
        {menu.dishes.map((dish) => {
          const mine = cooking.has(dish.name);
          return (
            <div key={dish.name} className={`mb-2 flex items-center gap-2 rounded-xl border p-3 ${mine ? "border-forest bg-mint" : "border-line"}`}>
              <div className="flex-1"><div className="font-bold">{dish.name}</div><div className="text-xs capitalize text-slate">{dish.course}{dish.veg ? " · veg" : ""}</div></div>
              <button onClick={() => toggleCooking(dish.name, true)} className={`rounded-lg border px-2.5 py-2 text-xs font-bold ${mine ? "border-forest bg-forest text-white" : "border-line bg-white"}`}>I&apos;ll make it</button>
              <button onClick={() => toggleCooking(dish.name, false)} className={`rounded-lg border px-2.5 py-2 text-xs font-bold ${!mine ? "border-forest text-forest" : "border-line bg-white"}`}>Would love</button>
            </div>
          );
        })}
        <div className="my-3 flex justify-between text-sm"><span>{cooking.size} you are making · {menu.dishes.length - cooking.size} wished for</span><span className="font-bold text-forest">{menu.dishes.filter((d) => d.veg).length} vegetarian</span></div>
        {error && <div className="mb-2 text-sm text-berry">{error}</div>}
        <button onClick={sendInvite} className={primaryButton}>Send the invite 💌</button>
        <button onClick={() => setStep("details")} className="mt-2 w-full py-2 text-sm font-bold text-slate">Back</button>
      </Sheet>
    );
  }

  return (
    <Sheet title="Host an event" onClose={onClose}>
      <div className="mb-2 font-bold">What is the occasion?</div>
      <div className="mb-4 grid grid-cols-2 gap-2">
        {Object.entries(menus).map(([id, m]) => (
          <button key={id} onClick={() => setOccasion(id)} className={`rounded-xl border p-3 text-left ${occasion === id ? "border-forest bg-mint" : "border-line"}`}>
            <div className="font-bold">{m.emoji} {m.label}</div><div className="text-xs text-slate">{m.hint}</div>
          </button>
        ))}
      </div>
      <label className="mb-2 block rounded-xl border border-line p-3"><span className="text-xs text-slate">Name it</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={menu.title} className="block w-full font-bold outline-none" />
      </label>
      <div className="mb-2 grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-line p-3"><div className="text-xs text-slate">How many people</div>
          <div className="flex items-center gap-2 font-bold"><button onClick={() => setGuests(Math.max(2, guests - 1))} className="h-7 w-7 rounded-lg bg-cream">−</button>{guests}<button onClick={() => setGuests(Math.min(50, guests + 1))} className="h-7 w-7 rounded-lg bg-cream">+</button></div>
        </div>
        <label className="rounded-xl border border-line p-3"><span className="text-xs text-slate">Anything to avoid</span>
          <input value={avoid} onChange={(e) => setAvoid(e.target.value)} placeholder="No pork" className="block w-full font-bold outline-none" />
        </label>
      </div>
      <div className="mb-2 rounded-xl border border-line p-3"><div className="mb-1 text-xs text-slate">When is it</div>
        <div className="no-scrollbar flex gap-2 overflow-x-auto">
          {DAYS_AHEAD.map((n) => { const d = new Date(); d.setDate(d.getDate() + n); return (
            <button key={n} onClick={() => setDaysAhead(n)} className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-bold ${daysAhead === n ? "bg-forest text-white" : "bg-cream"}`}>{d.toLocaleDateString([], { weekday: "short", day: "numeric" })} · 7 PM</button>
          ); })}
        </div>
      </div>
      <div className="mb-4 rounded-xl border border-line p-3"><div className="mb-1 text-xs text-slate">Ingredients ride with this grocery pod</div>
        {openPods.map((p) => (
          <button key={p.id} onClick={() => setPodId(p.id)} className={`mb-1 flex w-full justify-between rounded-lg px-2 py-1.5 text-left text-sm ${podId === p.id ? "bg-mint font-bold text-forest" : ""}`}>
            <span>{p.name}</span><span>closes {timeLeft(p.cutoff) ? `in ${timeLeft(p.cutoff)}` : "soon"}</span>
          </button>
        ))}
      </div>
      <button onClick={() => setStep("menu")} disabled={!podId} className={primaryButton}>Suggest a menu ✨</button>
    </Sheet>
  );
}
