"use client";

import { useState } from "react";
import type { CommunityEvent, Dish, Member } from "@/lib/types";
import { Avatar, Sheet, SourceBadge, api, dayAndTime, money, plural, primaryButton, secondaryButton, shortBuilding, timeLeft } from "./shared";

const COURSES = [
  { id: "starter", label: "Starters", one: "starter" }, { id: "main", label: "Mains", one: "main" }, { id: "side", label: "Sides", one: "side" },
  { id: "dessert", label: "Sweets", one: "sweet" }, { id: "drink", label: "Drinks", one: "drink" },
] as const;

export default function EventScreen({ event, members, me, onBack, onOpenPod, onChanged, notify }: {
  event: CommunityEvent | undefined; members: Member[]; me: string; onBack: () => void; onOpenPod: (podId: string) => void;
  onChanged: () => Promise<void>; notify: (text: string, celebrate?: boolean) => void;
}) {
  const [claiming, setClaiming] = useState<Dish | null>(null);
  const [addingDish, setAddingDish] = useState(false);
  if (!event) return <div className="grid flex-1 place-items-center text-slate">Loading event…</div>;

  const nameOf = (id: string) => (id === me ? "You" : members.find((m) => m.id === id)?.name ?? id);
  const hostName = members.find((m) => m.id === event.hostId)?.name ?? event.hostId;
  const isHost = event.hostId === me;
  const myDishes = event.dishes.filter((d) => d.cookId === me);
  const onVibes = event.vibes.includes(me);
  const upForGrabs = event.dishes.filter((d) => !d.cookId);
  const menuIsSet = event.podStatus !== "open";
  const closesIn = timeLeft(event.closesAt);

  async function post(path: string, body: object, success: string) {
    const result = await api<{ ok: boolean; reason?: string }>(path, { method: "POST", body: JSON.stringify({ eventId: event!.id, memberId: me, ...body }) });
    notify(result.ok ? success : result.reason ?? "That didn't work", result.ok);
    await onChanged();
    return result.ok;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center gap-2 px-4 pt-3">
        <button onClick={onBack} className="grid h-10 w-10 place-items-center rounded-full text-2xl text-forest" aria-label="Back">‹</button>
        <button onClick={() => onOpenPod(event.podId)} className="ml-auto rounded-full bg-cream px-3 py-1.5 text-sm font-bold text-forest">💬 Pod chat</button>
      </header>
      <div className="flex-1 overflow-y-auto px-5 pb-6">
        <div className="relative">
          <span className="absolute right-1 top-0 rotate-12 text-4xl">{event.emoji}</span>
          <h1 className="pr-12 font-display text-[28px] font-extrabold leading-tight">{event.title}</h1>
          <div className="text-sm text-slate">{isHost ? "You are hosting" : `${hostName} is hosting`} · {dayAndTime(event.date)} · {shortBuilding(event.building)}</div>
        </div>

        {menuIsSet && (
          <div className="mt-4 rounded-2xl bg-forest p-5 text-white">
            <div className="text-xs font-bold text-white/70">huddlecart.</div>
            <div className="font-display text-2xl font-extrabold">The menu is set</div>
            <div className="mb-3 text-sm text-white/80">Groceries ordered. Pickup {dayAndTime(event.pickupAt)}, {event.pickupSpot}.</div>
            {event.dishes.filter((d) => d.cookId).map((d) => <div key={d.id} className="flex justify-between border-t border-white/10 py-1.5 text-sm"><span className="font-bold">{d.name}</span><span>{nameOf(d.cookId!)}</span></div>)}
          </div>
        )}

        {myDishes.length > 0 && (
          <div className="mt-4 rounded-xl bg-forest p-3 text-white">
            <div className="font-bold">You are bringing {myDishes.map((d) => d.name.toLowerCase()).join(" and ")}</div>
            <div className="text-sm text-white/80">Ingredients ride with the group order{isHost ? "." : `. Settle up with ${hostName} after pickup.`}</div>
          </div>
        )}
        {onVibes && <div className="mt-4 rounded-xl bg-forest p-3 text-white"><div className="font-bold">You are on vibes duty ✨</div><div className="text-sm text-white/80">No cooking, no cart. Just show up hungry.</div></div>}

        <div className="mt-4 rounded-xl bg-mint p-4">
          <div className="flex justify-between"><span className="font-bold text-forest">{plural(event.claimedCount, "dish", "dishes")} · for {event.guests}</span><span className="text-sm text-slate">{menuIsSet ? "Order placed" : `Closes in ${closesIn ?? "soon"}`}</span></div>
          <div className="mt-1 text-sm text-slate">{COURSES.map((c) => plural(event.courseCounts[c.id] ?? 0, c.one)).join(" · ")}</div>
          <div className="text-sm text-slate">{event.comingCount} coming · {event.cookingCount} cooking · {event.vibesCount} on vibes duty{event.avoid ? ` · ${event.avoid}` : ""}</div>
        </div>

        {upForGrabs.length > 0 && (
          <section className="mt-5">
            <div className="mb-2 text-xs font-bold uppercase tracking-wide text-amber">{hostName} would love these · up for grabs</div>
            {upForGrabs.map((dish) => (
              <div key={dish.id} className="flex items-center gap-3 border-b border-line py-2.5">
                <div className="flex-1"><div className="font-bold">{dish.name}</div><div className="text-xs text-slate">{plural(dish.ingredients.length, "ingredient")} · {money(dish.ingredientsTotal)}</div></div>
                <button onClick={() => setClaiming(dish)} disabled={menuIsSet} className="rounded-full bg-forest px-4 py-2 text-sm font-bold text-white disabled:opacity-40">Claim</button>
              </div>
            ))}
          </section>
        )}

        {COURSES.map((course) => {
          const dishes = event.dishes.filter((d) => d.cookId && d.course === course.id);
          if (!dishes.length) return null;
          return (
            <section key={course.id} className="mt-4">
              <div className="mb-1 text-xs font-bold uppercase tracking-wide text-slate">{course.label}</div>
              {dishes.map((dish) => (
                <div key={dish.id} className={`flex items-center gap-2 border-b border-line py-2 ${dish.cookId === me ? "-mx-2 rounded-lg bg-mint px-2" : ""}`}>
                  <div className="flex-1"><div className="font-bold">{dish.name}{dish.veg && <span className="ml-1 text-xs text-forest">· veg</span>}</div>{dish.note && <div className="text-xs italic text-slate">“{dish.note}”</div>}</div>
                  <Avatar id={dish.cookId!} name={members.find((m) => m.id === dish.cookId)?.name ?? dish.cookId!} size={22} />
                  <span className="text-sm text-slate">{nameOf(dish.cookId!)}{dish.cookId === event.hostId ? ", host" : ""}</span>
                </div>
              ))}
            </section>
          );
        })}
        {event.vibes.length > 0 && <div className="mt-3 text-sm"><b>Vibes crew:</b> {event.vibes.map(nameOf).join(", ")} {event.vibes.length === 1 ? "is" : "are"} coming hungry.</div>}
      </div>

      {!menuIsSet && (
        <div className="flex gap-2 border-t border-line px-4 pb-4 pt-3">
          {isHost ? (
            <button onClick={() => post("/api/events/nudge", {}, "Nudge posted in the pod chat 📣")} className={primaryButton}>{upForGrabs.length ? `Nudge about ${upForGrabs.slice(0, 2).map((d) => d.name.toLowerCase()).join(" and ")}` : "Share the table"}</button>
          ) : myDishes.length || onVibes ? (
            <>
              <button onClick={() => post("/api/events/unclaim", {}, "Your pick is cleared")} className={secondaryButton}>Change my pick</button>
              <button onClick={() => onOpenPod(event.podId)} className={secondaryButton}>Share the table</button>
            </>
          ) : (
            <>
              <button onClick={() => setAddingDish(true)} className="flex-1 rounded-full border-2 border-dashed border-forest/40 py-3 text-sm font-bold text-forest">Add your own dish</button>
              <button onClick={() => post("/api/events/vibes", {}, "You're on vibes duty ✨")} className="flex-1 rounded-full border-2 border-dashed border-forest/40 py-3 text-sm font-bold text-forest">Just bringing vibes</button>
            </>
          )}
        </div>
      )}

      {claiming && <ClaimSheet dish={claiming} hostName={hostName} onClose={() => setClaiming(null)}
        onClaim={async (addIngredients) => { if (await post("/api/events/claim", { dishId: claiming.id, addIngredients }, addIngredients ? `You're bringing ${claiming.name}! Ingredients are in your basket.` : `You're bringing ${claiming.name}!`)) setClaiming(null); }} />}
      {addingDish && <AddDishSheet onClose={() => setAddingDish(false)}
        onAdd={async (name, course, note) => { if (await post("/api/events/dish", { name, course, note }, `${name} is on the table!`)) setAddingDish(false); }} />}
    </div>
  );
}

function ClaimSheet({ dish, hostName, onClose, onClaim }: { dish: Dish; hostName: string; onClose: () => void; onClaim: (addIngredients: boolean) => void }) {
  const [skipOrder, setSkipOrder] = useState(false);
  return (
    <Sheet title={dish.name} onClose={onClose}>
      <div className="-mt-3 mb-3 text-sm text-slate">{hostName} would love someone to bring this</div>
      {dish.recipe && <a href={`https://www.google.com/search?q=${encodeURIComponent(dish.recipe + " recipe")}`} target="_blank" rel="noreferrer" className="mb-3 flex justify-between rounded-xl bg-mint p-3 font-bold text-forest"><span>Recipe: {dish.recipe}</span><span>›</span></a>}
      <div className="mb-1 flex items-center justify-between"><span className="rounded-full bg-mint px-2 py-0.5 text-xs font-bold text-forest">Drafted by HuddleCart</span><span className="text-xs text-slate">{plural(dish.ingredients.length, "ingredient")}</span></div>
      {dish.ingredients.map((item) => <div key={item.id} className="flex items-center justify-between gap-2 border-b border-line py-2.5"><span className="min-w-0"><span className="block font-bold">{item.title}</span><SourceBadge marketplace={item.marketplace} url={item.url} source={item.source} /></span><span className="font-bold">{money(item.price)}</span></div>)}
      <label className="mt-3 flex gap-3 rounded-xl bg-cream p-3">
        <input type="checkbox" checked={skipOrder} onChange={(e) => setSkipOrder(e.target.checked)} className="mt-1 h-5 w-5 accent-[#195d49]" />
        <span><span className="block font-bold">I&apos;ve got this</span><span className="text-sm text-slate">Skip the group order. Nothing is added to your basket.</span></span>
      </label>
      <div className="my-3 flex justify-between"><span className="text-slate">{skipOrder ? "Nothing to order" : `${plural(dish.ingredients.length, "item")} · owed to ${hostName}`}</span><span className="font-display text-2xl font-extrabold">{money(skipOrder ? 0 : dish.ingredientsTotal)}</span></div>
      <button onClick={() => onClaim(!skipOrder)} className={primaryButton}>{skipOrder ? "Claim this dish" : "Claim and add to the order"}</button>
    </Sheet>
  );
}

function AddDishSheet({ onClose, onAdd }: { onClose: () => void; onAdd: (name: string, course: string, note: string) => void }) {
  const [name, setName] = useState("");
  const [course, setCourse] = useState("side");
  const [note, setNote] = useState("");
  return (
    <Sheet title="Add your dish" onClose={onClose}>
      <label className="mb-2 block rounded-xl border border-line p-3"><span className="text-xs text-slate">What are you making?</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Chicken chaat" className="block w-full font-bold outline-none" />
      </label>
      <div className="no-scrollbar mb-2 flex gap-2 overflow-x-auto">
        {COURSES.map((c) => <button key={c.id} onClick={() => setCourse(c.id)} className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-bold ${course === c.id ? "bg-forest text-white" : "bg-cream"}`}>{c.label}</button>)}
      </div>
      <label className="mb-3 block rounded-xl border border-line p-3"><span className="text-xs text-slate">Say something about it (optional)</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Family recipe, a little spicy" className="block w-full italic outline-none" />
      </label>
      <div className="mb-3 rounded-xl bg-mint p-3 text-sm">Need ingredients? Ask HuddleCart in the pod chat and tap Add.</div>
      <button onClick={() => onAdd(name, course, note)} disabled={!name.trim()} className={primaryButton}>Add to the table</button>
    </Sheet>
  );
}
