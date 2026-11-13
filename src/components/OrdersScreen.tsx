"use client";

import { useState } from "react";
import type { Member, PlacedOrder } from "@/lib/types";
import { PickupPass, Sheet, STORE_NAMES, SOLO_SHIPPING, dayAndTime, money, primaryButton, secondaryButton, shortBuilding, timeLeft, type Bag, type PodWithTotals } from "./shared";

export type CurrentOrder = Bag & { pod: PodWithTotals };
export type PastOrder = { week: number; podId: string; podName: string; items: { title: string; qty: number }[]; saved: number };
export type Orders = { current: CurrentOrder[]; past: PastOrder[]; checkouts: PlacedOrder[]; lifetimeSavings: number };

const STATUS_ORDER = ["open", "locked", "ordered", "arrived", "closed"];
const NEXT_STEPS = [
  { title: "You placed your order", text: "Done right in the pod chat.", isDone: (placed: boolean) => placed },
  { title: "The group order ships", text: "One combined order at the cutoff, so shipping is shared.", isDone: (_: boolean, status: string) => STATUS_ORDER.indexOf(status) >= 2 },
  { title: "Collect with your pickup code", text: "Show your code at pickup and pay your host by Venmo or Zelle.", isDone: (_: boolean, status: string) => STATUS_ORDER.indexOf(status) >= 3 },
];

function statusChip(order: CurrentOrder, placedNumbers: string[]) {
  const { status, cutoff } = order.pod;
  if (status === "open" && placedNumbers.length) return { label: `Placed · ${placedNumbers.join(", ")}`, className: "bg-mint text-forest" };
  if (status === "open") return { label: `Not checked out · closes in ${timeLeft(cutoff) ?? "soon"}`, className: "bg-amber-pale text-amber" };
  if (status === "locked") return { label: "Group order is going out", className: "bg-mint text-forest" };
  if (status === "ordered") return { label: "On the way", className: "bg-mint text-forest" };
  if (status === "arrived") return { label: order.collected ? "Picked up" : "Ready for pickup", className: "bg-mint text-forest" };
  return { label: "Done", className: "bg-line text-slate" };
}

export default function OrdersScreen({ orders, members, header, onOpenPod, onBrowse }: {
  orders: Orders | null; members: Member[]; header: React.ReactNode; onOpenPod: (podId: string) => void; onBrowse: () => void;
}) {
  const [passFor, setPassFor] = useState<CurrentOrder | null>(null);
  const hostNameOf = (id: string) => members.find((m) => m.id === id)?.name ?? id;
  const openPass = orders?.current.find((o) => o.pod.id === passFor?.pod.id) ?? null;

  return (
    <div className="flex-1 overflow-y-auto">
      {header}
      <div className="px-5 pb-8 pt-2">
        {orders?.current.length === 0 && (
          <div className="rounded-3xl bg-cream p-6 text-center">
            <div className="text-5xl">🧺</div>
            <div className="mt-2 font-display text-xl font-extrabold">No order yet</div>
            <div className="mb-4 text-sm text-slate">Join a pod and ask HuddleCart for what you need.</div>
            <button onClick={onBrowse} className={primaryButton}>Browse pods</button>
          </div>
        )}
        {orders?.current.map((order) => {
          const placed = (orders.checkouts ?? []).filter((c) => c.podId === order.pod.id);
          const placedItemCount = placed.reduce((sum, c) => sum + c.items.reduce((s, i) => s + i.qty, 0), 0);
          const itemCount = order.items.reduce((sum, item) => sum + item.qty, 0);
          const notCheckedOut = order.pod.status === "open" ? itemCount - placedItemCount : 0;
          const chip = statusChip(order, placed.map((c) => c.number));
          return (
            <section key={order.pod.id} className="mb-8">
              <h2 className="font-display text-[26px] font-extrabold">{placed.length || order.pod.status !== "open" ? "Order placed 🎉" : "Ready to check out?"}</h2>
              <span className={`mt-2 inline-block rounded-lg px-3 py-1.5 text-sm font-bold ${chip.className}`}>{chip.label}</span>
              <p className="mt-3 text-slate">{notCheckedOut > 0 ? `${notCheckedOut} item${notCheckedOut === 1 ? " is" : "s are"} still in your basket. Say "check out" in the pod chat to place ${notCheckedOut === 1 ? "it" : "them"}.` : "It ships with the group order. You pay your host after pickup."}</p>
              <div className="mt-3 rounded-xl bg-cream p-4">
                <div className="font-bold">{STORE_NAMES[order.pod.marketplace]} · {shortBuilding(order.pod.building)}</div>
                <div className="mt-2 font-bold">{itemCount} items · {money(order.amountDue)} estimated</div>
                <div className="text-sm text-slate">{order.items.map((i) => `${i.qty} × ${i.title}`).join(", ")}</div>
                <div className="mt-1 font-bold text-forest">Save {money(SOLO_SHIPPING - order.fee)}</div>
                <div className="mt-1 text-sm text-slate">Expected delivery: {dayAndTime(order.pod.deliveryEta)}</div>
              </div>
              <h3 className="mt-5 text-lg font-bold">What happens next</h3>
              <ol className="mt-2 space-y-3">
                {NEXT_STEPS.map((step, i) => {
                  const done = step.isDone(placed.length > 0 || order.pod.status !== "open", order.pod.status);
                  return (
                    <li key={step.title} className="flex gap-3">
                      <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-sm font-bold ${done ? "bg-forest text-white" : "bg-mint text-forest"}`}>{done ? "✓" : i + 1}</span>
                      <div><div className="font-bold">{step.title}</div><div className="text-sm text-slate">{step.text}</div></div>
                    </li>
                  );
                })}
              </ol>
              <div className="mt-5 space-y-2">
                <button onClick={() => setPassFor(order)} disabled={order.pod.status !== "arrived" && order.pod.status !== "closed"} className={primaryButton}>
                  {order.collected ? "See pickup proof" : order.pod.status === "arrived" ? "Show pickup pass" : "Pickup pass"}
                </button>
                {order.pod.status !== "arrived" && <div className="text-center text-xs text-slate">Your pickup pass unlocks when the order arrives.</div>}
                <button onClick={() => onOpenPod(order.pod.id)} className={secondaryButton}>{notCheckedOut > 0 ? "Check out in the pod chat" : "Open pod chat"}</button>
              </div>
            </section>
          );
        })}

        {!!orders?.past.length && (
          <>
            <h3 className="mb-2 text-lg font-bold">Past orders</h3>
            {orders.past.map((order) => (
              <div key={`${order.week}-${order.podId}`} className="mb-2 flex items-center gap-3 rounded-xl border border-line p-3">
                <span className="text-2xl">🧾</span>
                <div className="min-w-0 flex-1">
                  <div className="font-bold">{order.podName} <span className="text-xs font-normal text-slate">· week {order.week}</span></div>
                  <div className="truncate text-sm text-slate">{order.items.map((i) => `${i.qty} × ${i.title}`).join(", ")}</div>
                </div>
                <span className="text-sm font-bold text-forest">+{money(order.saved)}</span>
              </div>
            ))}
          </>
        )}
      </div>
      {openPass && (
        <Sheet title="Pickup pass" onClose={() => setPassFor(null)}>
          <PickupPass bag={openPass} pod={openPass.pod} hostName={hostNameOf(openPass.pod.leaderId)} />
        </Sheet>
      )}
    </div>
  );
}
