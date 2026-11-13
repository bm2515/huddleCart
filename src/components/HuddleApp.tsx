"use client";

import { useCallback, useEffect, useState } from "react";
import type { CommunityEvent, Member, Menus } from "@/lib/types";
import CommunityScreen from "./CommunityScreen";
import EventScreen from "./EventScreen";
import HomeScreen from "./HomeScreen";
import OrdersScreen, { type Orders } from "./OrdersScreen";
import PodScreen, { type PodDetail } from "./PodScreen";
import SavingsScreen, { type Community } from "./SavingsScreen";
import { Avatar, api, type PodWithTotals } from "./shared";
import { useMe } from "./useMe";

const TABS = [
  { id: "home", label: "Home", icon: "/figma/home.svg", path: "/", title: "HuddleCart" },
  { id: "community", label: "Community", icon: "/figma/community.svg", path: "/community", title: "Community" },
  { id: "orders", label: "Order", icon: "/figma/order.svg", path: "/orders", title: "Your order" },
  { id: "savings", label: "Savings", icon: "/figma/savings.svg", path: "/savings", title: "Your savings" },
] as const;
type TabId = (typeof TABS)[number]["id"];
const isTab = (screen: string): screen is TabId => TABS.some((t) => t.id === screen);
const CONFETTI = ["🎉", "🥟", "✨", "🍜", "💚", "🛒"];

const EVENT_PREFIX = "event:";

/** One screen at a time: a tab, an event board ("event:<id>"), or a pod chat (any other id). */
export default function HuddleApp({ initialScreen = "home" }: { initialScreen?: string }) {
  const [me, setMe] = useMe();
  const [screen, setScreen] = useState(initialScreen);
  const [lastTab, setLastTab] = useState<TabId>(isTab(initialScreen) ? initialScreen : "home");
  const [pods, setPods] = useState<PodWithTotals[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [community, setCommunity] = useState<Community | null>(null);
  const [orders, setOrders] = useState<Orders | null>(null);
  const [events, setEvents] = useState<CommunityEvent[]>([]);
  const [menus, setMenus] = useState<Menus | null>(null);
  const [detail, setDetail] = useState<PodDetail | null>(null);
  const [toast, setToast] = useState<{ text: string; celebrate: boolean } | null>(null);

  const refresh = useCallback(async () => {
    const [all, game, mine, happening] = await Promise.all([
      api<{ pods: PodWithTotals[]; members: Member[] }>("/api/pods"),
      api<Community>("/api/community"),
      api<Orders>(`/api/orders?memberId=${me}`),
      api<{ events: CommunityEvent[]; menus: Menus }>("/api/events"),
    ]);
    setEvents(happening.events);
    setMenus(happening.menus);
    setPods(all.pods);
    setMembers(all.members);
    setCommunity(game);
    setOrders(mine);
    if (!isTab(screen) && !screen.startsWith(EVENT_PREFIX)) setDetail(await api<PodDetail>(`/api/pods?podId=${screen}`));
  }, [screen, me]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(timer);
  }, [toast]);

  function go(next: string) {
    setScreen(next);
    if (isTab(next)) setLastTab(next);
    else setDetail(null);
    const path = isTab(next) ? TABS.find((t) => t.id === next)!.path : next.startsWith(EVENT_PREFIX) ? `/event/${next.slice(EVENT_PREFIX.length)}` : `/pod/${next}`;
    window.history.replaceState(null, "", path);
  }

  async function joinPod(podId: string) {
    const result = await api<{ ok: boolean; reason?: string }>("/api/pods/join", { method: "POST", body: JSON.stringify({ podId, memberId: me }) });
    setToast({ text: result.ok ? "You're in! Ask HuddleCart for what you need." : result.reason ?? "Couldn't join that pod", celebrate: result.ok });
    refresh();
  }

  const tab = TABS.find((t) => t.id === screen);
  const eventId = screen.startsWith(EVENT_PREFIX) ? screen.slice(EVENT_PREFIX.length) : null;
  const openEvent = (id: string) => go(EVENT_PREFIX + id);
  const notify = (text: string, celebrate = false) => setToast({ text, celebrate });
  const header = tab && (
    <div className="flex items-center px-5 pb-2 pt-5">
      <h1 className={`flex-1 font-display font-extrabold ${tab.id === "home" ? "text-2xl text-forest" : "text-[26px] text-ink"}`}>{tab.title}</h1>
      <label className="relative flex items-center gap-1.5 rounded-full border border-line bg-white py-1 pl-1 pr-3 text-sm font-bold">
        <Avatar id={me} name={members.find((m) => m.id === me)?.name ?? me} size={26} />
        {members.find((m) => m.id === me)?.name} ▾
        <select value={me} onChange={(e) => setMe(e.target.value)} className="absolute inset-0 cursor-pointer opacity-0" aria-label="Switch neighbor">
          {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </label>
    </div>
  );

  return (
    <div className="flex h-dvh justify-center">
      <div className="flex h-full w-full max-w-[440px] flex-col overflow-hidden bg-white shadow-[0_10px_60px_rgba(24,39,36,0.15)] sm:my-0">
        {screen === "home" && <HomeScreen pods={pods} events={events} members={members} me={me} header={header} onOpenPod={go} onOpenEvent={openEvent} onHost={() => go("community")}
          onStartedPod={async (id) => { notify("Your pod is live! Share it with neighbors 👑", true); await refresh(); go(id); }} />}
        {screen === "community" && <CommunityScreen events={events} menus={menus} pods={pods} members={members} me={me} header={header} onOpenEvent={openEvent}
          onHosted={async (id, message) => { notify(message, true); await refresh(); openEvent(id); }} />}
        {eventId && <EventScreen event={events.find((e) => e.id === eventId)} members={members} me={me} onBack={() => go(lastTab)} onOpenPod={go} onChanged={refresh} notify={notify} />}
        {screen === "orders" && <OrdersScreen orders={orders} members={members} header={header} onOpenPod={go} onBrowse={() => go("home")} />}
        {screen === "savings" && <SavingsScreen orders={orders} community={community} me={me} header={header} />}
        {!tab && !eventId && (
          <PodScreen detail={detail} pods={pods} events={events} me={me} community={community} onBack={() => go(lastTab)} onOpenPod={go}
            onOpenEvent={openEvent} onJoin={joinPod} onChanged={refresh} notify={notify} />
        )}

        {tab && (
          <nav className="flex justify-center border-t border-line bg-white px-2 pb-3 pt-1.5">
            {TABS.map((t) => (
              <button key={t.id} onClick={() => go(t.id)} className={`relative flex h-[52px] flex-1 flex-col items-center justify-center gap-0.5 rounded-xl ${screen === t.id ? "bg-mint" : ""}`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={t.icon} alt="" width={24} height={24} />
                <span className={`text-xs font-bold ${screen === t.id ? "text-forest" : "text-slate"}`}>{t.label}</span>
                {t.id === "orders" && !!orders?.current.length && <span className="absolute right-[30%] top-1 h-2.5 w-2.5 rounded-full bg-berry" />}
              </button>
            ))}
          </nav>
        )}
      </div>

      {toast && (
        <div className="animate-pop-in fixed bottom-28 left-1/2 z-50 w-max max-w-[90vw] rounded-full bg-ink px-5 py-3 text-sm font-bold text-white shadow-xl">
          {toast.text}
          {toast.celebrate && CONFETTI.map((emoji, i) => (
            <span key={i} className="animate-float-up absolute -top-2 text-xl" style={{ left: `${10 + i * 16}%`, animationDelay: `${i * 0.06}s` }}>{emoji}</span>
          ))}
        </div>
      )}
    </div>
  );
}
