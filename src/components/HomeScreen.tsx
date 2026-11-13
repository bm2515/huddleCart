"use client";

import { useState } from "react";
import type { CommunityEvent, Marketplace, Member } from "@/lib/types";
import { EventCard } from "./CommunityScreen";
import { Avatar, ProgressBar, SOLO_SHIPPING, STORE_NAMES, Sheet, StoreLogo, api, money, primaryButton, shortBuilding, timeLeft, weekdayAndHour, dayAndTime, type PodWithTotals } from "./shared";

const PACK_PHOTOS = ["/figma/pack-dumplings.png", "/figma/pack-rice.png", "/figma/pack-noodles.png"];
const STATUS_LABEL: Record<string, string> = { locked: "Host is confirming", ordered: "On the way", arrived: "Ready for pickup", closed: "Done" };

export default function HomeScreen({ pods, events, members, me, header, onOpenPod, onOpenEvent, onHost, onStartedPod }: {
  pods: PodWithTotals[]; events: CommunityEvent[]; members: Member[]; me: string; header: React.ReactNode;
  onOpenPod: (podId: string) => void; onOpenEvent: (eventId: string) => void; onHost: () => void; onStartedPod: (podId: string) => void;
}) {
  const buildings = [...new Set(pods.map((p) => p.building))];
  const [building, setBuilding] = useState<string | null>(null);
  const [sheet, setSheet] = useState<"building" | "about" | "lead" | null>(null);
  const currentBuilding = building ?? buildings[0];
  const buildingPods = pods.filter((p) => p.building === currentBuilding);
  const openPods = buildingPods.filter((p) => p.status === "open");
  const myName = members.find((m) => m.id === me)?.name;

  return (
    <div className="flex-1 overflow-y-auto">
      {header}
      <div className="space-y-4 px-5 pb-8 pt-2">
        <div className="relative overflow-hidden rounded-3xl bg-forest p-5 text-white">
          <div className="font-display text-2xl font-extrabold leading-tight">Hey {myName} 👋<br />What are we craving?</div>
          <div className="mt-1 text-sm text-white/80">Join a pod, add groceries, pick up downstairs.</div>
          <span className="absolute -right-1 top-3 rotate-12 rounded-full bg-amber-pale px-3 py-1 text-xs font-bold text-amber shadow">$2 not $5 shipping</span>
        </div>

        <button onClick={() => setSheet("building")} className="flex w-full items-center gap-2.5 rounded-xl border border-line bg-white px-3 py-2 text-left">
          <span className="text-xl">📍</span>
          <span className="flex-1">
            <span className="block text-[13px] text-slate">Delivery &amp; pickup</span>
            <span className="block text-[17px] font-bold text-ink">{currentBuilding && shortBuilding(currentBuilding)}</span>
          </span>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/figma/down.svg" alt="" width={18} height={18} />
        </button>

        <div>
          <div className="flex h-11 items-center">
            <h2 className="flex-1 text-lg font-bold text-ink">Happening at {currentBuilding && shortBuilding(currentBuilding)}</h2>
            <button onClick={onHost} className="rounded-full bg-mint px-3 py-1.5 text-sm font-bold text-forest">+ Host</button>
          </div>
          <div className="no-scrollbar -mx-5 flex gap-3 overflow-x-auto px-5">
            {events.filter((e) => e.building === currentBuilding).map((e) => <EventCard key={e.id} event={e} members={members} compact onOpen={() => onOpenEvent(e.id)} />)}
            {!events.some((e) => e.building === currentBuilding) && <button onClick={onHost} className="w-full rounded-[14px] border-2 border-dashed border-line p-4 text-sm text-slate">Nothing planned yet. Host a dinner or game night 🎉</button>}
          </div>
        </div>

        <div className="flex h-11 items-center">
          <h2 className="text-lg font-bold text-ink">Open pods</h2>
          <span className="ml-auto text-sm text-slate">{openPods.length} available</span>
          <button onClick={() => setSheet("about")} className="grid h-11 w-11 place-items-center" aria-label="About pods">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/figma/info.svg" alt="" width={20} height={20} />
          </button>
        </div>

        {buildingPods.map((pod) => <PodCard key={pod.id} pod={pod} members={members} joined={pod.memberIds.includes(me)} onOpen={() => onOpenPod(pod.id)} />)}

        <button onClick={() => setSheet("lead")} className="relative w-full overflow-hidden rounded-[14px] border-2 border-dashed border-forest/40 bg-mint p-4 text-left">
          <span className="absolute -right-1 top-2 rotate-12 rounded-full bg-amber-pale px-2.5 py-0.5 text-xs font-bold text-amber">earn 15–20%</span>
          <div className="font-display text-lg font-extrabold text-forest">👑 Become a pod lead</div>
          <div className="text-sm text-slate">Start a pod for {currentBuilding && shortBuilding(currentBuilding)}. You place one order, hand out the bags and keep part of the fees.</div>
        </button>
      </div>

      {sheet === "building" && (
        <Sheet title="Choose building" onClose={() => setSheet(null)}>
          {buildings.map((b) => (
            <button key={b} onClick={() => { setBuilding(b); setSheet(null); }}
              className={`mb-2 flex w-full items-center gap-3 rounded-xl border p-3 text-left ${b === currentBuilding ? "border-forest bg-mint" : "border-line"}`}>
              <span className="text-xl">🏢</span>
              <span className="flex-1"><span className="block font-bold">{shortBuilding(b)}</span><span className="text-sm text-slate">{b}</span></span>
              {b === currentBuilding && <span className="font-bold text-forest">✓</span>}
            </button>
          ))}
        </Sheet>
      )}
      {sheet === "lead" && currentBuilding && (
        <StartPodSheet building={currentBuilding} me={me} onClose={() => setSheet(null)} onStarted={(id) => { setSheet(null); onStartedPod(id); }} />
      )}
      {sheet === "about" && (
        <Sheet title="How pods work" onClose={() => setSheet(null)}>
          {[
            ["🛒", "Join a pod", "A neighbor hosts one grocery order for the building."],
            ["💬", "Ask HuddleCart", "Say what you want in the pod chat. Tap Add on the item you like."],
            ["📦", "Pick up downstairs", "The host orders once. You show your code and pay $2 instead of $5 shipping."],
          ].map(([emoji, title, text]) => (
            <div key={title} className="mb-3 flex gap-3 rounded-xl bg-cream p-3">
              <span className="text-2xl">{emoji}</span>
              <div><div className="font-bold">{title}</div><div className="text-sm text-slate">{text}</div></div>
            </div>
          ))}
        </Sheet>
      )}
    </div>
  );
}

const CLOSE_OPTIONS = [["Tonight", 6], ["Tomorrow", 24], ["In 2 days", 48]] as const;

function StartPodSheet({ building, me, onClose, onStarted }: { building: string; me: string; onClose: () => void; onStarted: (podId: string) => void }) {
  const [name, setName] = useState("");
  const [marketplace, setMarketplace] = useState<Marketplace>("weee");
  const [pickupSpot, setPickupSpot] = useState(`${shortBuilding(building)} lobby`);
  const [closesInHours, setClosesInHours] = useState<number>(24);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    const result = await api<{ ok: boolean; reason?: string; pod?: { id: string } }>("/api/pods", {
      method: "POST", body: JSON.stringify({ memberId: me, name: name || `${STORE_NAMES[marketplace]} run`, marketplace, building, pickupSpot, closesInHours }),
    });
    if (result.ok && result.pod) onStarted(result.pod.id);
    else setError(result.reason ?? "Couldn't start the pod");
  }

  const pill = (active: boolean) => `flex-1 rounded-full border px-3 py-2 text-sm font-bold ${active ? "border-forest bg-forest text-white" : "border-line bg-white text-ink"}`;
  return (
    <Sheet title="Lead a pod" onClose={onClose}>
      <div className="mb-3 rounded-xl bg-cream p-3 text-sm text-slate">As lead you place the one group order, get the bags at {shortBuilding(building)}, scan each neighbor&apos;s pickup QR and collect their $2.</div>
      <label className="mb-1 block text-sm font-bold">Pod name</label>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Friday snack run" className="mb-3 w-full rounded-xl border border-line px-3 py-2.5 outline-none focus:border-forest" />
      <label className="mb-1 block text-sm font-bold">Store</label>
      <div className="mb-3 flex gap-2">{(["weee", "amazon_fresh"] as const).map((m) => <button key={m} onClick={() => setMarketplace(m)} className={pill(marketplace === m)}>{STORE_NAMES[m]}</button>)}</div>
      <label className="mb-1 block text-sm font-bold">Order closes</label>
      <div className="mb-3 flex gap-2">{CLOSE_OPTIONS.map(([label, hours]) => <button key={label} onClick={() => setClosesInHours(hours)} className={pill(closesInHours === hours)}>{label}</button>)}</div>
      <label className="mb-1 block text-sm font-bold">Pickup spot</label>
      <input value={pickupSpot} onChange={(e) => setPickupSpot(e.target.value)} className="mb-3 w-full rounded-xl border border-line px-3 py-2.5 outline-none focus:border-forest" />
      {error && <div className="mb-2 text-sm text-berry">{error}</div>}
      <button onClick={start} disabled={!pickupSpot.trim()} className={primaryButton}>👑 Start my pod</button>
    </Sheet>
  );
}

function PodCard({ pod, members, joined, onOpen }: { pod: PodWithTotals; members: Member[]; joined: boolean; onOpen: () => void }) {
  const host = members.find((m) => m.id === pod.leaderId)?.name;
  const closesIn = pod.status === "open" ? timeLeft(pod.cutoff) : null;
  return (
    <button onClick={onOpen} className="flex w-full flex-col gap-2.5 rounded-[14px] bg-cream p-4 text-left transition active:scale-[0.99]">
      <div className="flex w-full items-center justify-between">
        <StoreLogo marketplace={pod.marketplace} />
        <span className="text-[13px] font-bold text-forest">{joined ? "You're in ✓" : "Open ›"}</span>
      </div>
      <div className="text-[15px] font-bold text-ink">{pod.name}</div>
      <div className="-mt-2 flex items-center gap-2 text-sm text-slate">
        <span className="flex -space-x-2">{pod.memberIds.slice(0, 4).map((id) => <Avatar key={id} id={id} name={members.find((m) => m.id === id)?.name ?? id} size={22} />)}</span>
        Hosted by {host} · {pod.memberIds.length} neighbors joined
      </div>
      <div className="w-full rounded-[10px] bg-mint p-3">
        <div className="text-[13px] font-bold text-forest">EXPECTED DELIVERY</div>
        <div className="font-display text-xl font-bold text-forest">{dayAndTime(pod.deliveryEta)}</div>
        <div className="text-sm text-slate">{pod.pickupSpot}</div>
      </div>
      <div className="flex w-full gap-[9px]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {PACK_PHOTOS.map((src) => <img key={src} src={src} alt="" className="h-[72px] min-w-0 flex-1 rounded-lg bg-white object-contain" />)}
      </div>
      <div className="flex w-full items-center gap-2">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/figma/schedule.svg" alt="" width={20} height={20} />
        <span className="text-[15px] font-bold text-ink">{closesIn ? `Closes in ${closesIn}` : STATUS_LABEL[pod.status] ?? "Closed"}</span>
        <span className="text-[13px] text-slate">{weekdayAndHour(pod.cutoff)}</span>
      </div>
      <div className="w-full">
        <div className="mb-1 flex justify-between text-xs text-slate"><span>🎯 Free shipping goal</span><span>{money(pod.totals.subtotal)} of {money(pod.minimumForFreeShipping)}</span></div>
        <ProgressBar value={pod.totals.progress} />
      </div>
      <div className="w-full rounded-lg bg-mint p-2.5 text-base font-bold text-forest">Save {money(SOLO_SHIPPING - pod.feePerPerson)}</div>
    </button>
  );
}
