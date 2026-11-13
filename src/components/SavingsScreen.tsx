"use client";

import type { Orders } from "./OrdersScreen";
import { Avatar, ProgressBar, money } from "./shared";

type Badge = { id: string; label: string; emoji: string };
export type MemberStats = {
  memberId: string; name: string; items: number; orders: number; streak_weeks: number; shipping_saved: number;
  badges: Badge[]; level: { level: number; title: string; xp: number; nextLevelXp: number; progress: number };
};
export type Community = { members: Record<string, MemberStats>; leaderboard: { memberId: string; name: string; xp: number; level: number }[]; funFacts: string[]; buildingSavings: number; questRewardXp: number };

const MEDALS = ["🥇", "🥈", "🥉"];
const STICKER_TILT = ["-rotate-3", "rotate-2", "-rotate-1", "rotate-3"];

export default function SavingsScreen({ orders, community, me, header }: { orders: Orders | null; community: Community | null; me: string; header: React.ReactNode }) {
  const stats = community?.members[me];
  const past = orders?.past ?? [];
  const [latest, previous, ...earlier] = past;
  return (
    <div className="flex-1 overflow-y-auto">
      {header}
      <div className="px-5 pb-8 pt-2">
        <div className="text-xs font-bold uppercase tracking-wide text-slate">Your history</div>
        <div className="mt-2 rounded-2xl bg-mint p-5">
          <div className="font-bold text-forest">Lifetime fee savings</div>
          <div className="font-display text-4xl font-extrabold text-forest">{money(orders?.lifetimeSavings ?? 0)}</div>
          <div className="text-slate">Across {past.length} completed orders</div>
        </div>
        <div className="mt-3 divide-y divide-line border-y border-line">
          {latest && <SavingsRow label="Latest completed order" amount={latest.saved} />}
          {previous && <SavingsRow label="Previous completed order" amount={previous.saved} />}
          {earlier.length > 0 && <SavingsRow label={`${earlier.length} earlier completed orders`} amount={earlier.reduce((s, o) => s + o.saved, 0)} />}
        </div>
        <p className="mt-2 text-sm text-slate">Orders still running are not included. Your shared orders keep fees lower.</p>

        {stats && (
          <div className="mt-6 rounded-2xl bg-cream p-4">
            <div className="flex items-center gap-3">
              <div className="grid h-14 w-14 place-items-center rounded-2xl bg-forest font-display text-2xl font-extrabold text-white">{stats.level.level}</div>
              <div className="flex-1">
                <div className="font-display text-lg font-extrabold">{stats.level.title}</div>
                <div className="text-sm text-slate">{stats.level.xp} XP · 🔥 {stats.streak_weeks} week streak</div>
              </div>
            </div>
            <div className="mt-3"><ProgressBar value={stats.level.progress} /></div>
            <div className="mt-1 text-xs text-slate">{stats.level.nextLevelXp - stats.level.xp} XP to the next level. +10 XP per item, +50 per order.</div>
            {stats.badges.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {stats.badges.map((badge, i) => <span key={badge.id} className={`${STICKER_TILT[i % STICKER_TILT.length]} rounded-full bg-white px-3 py-1 text-sm font-bold shadow-sm`}>{badge.emoji} {badge.label}</span>)}
              </div>
            )}
          </div>
        )}

        {community && (
          <>
            <h3 className="mb-2 mt-6 text-lg font-bold">Building leaderboard</h3>
            {community.leaderboard.map((row, i) => (
              <div key={row.memberId} className={`mb-2 flex items-center gap-3 rounded-xl p-3 ${row.memberId === me ? "bg-mint" : "border border-line"}`}>
                <span className="w-6 text-center text-lg">{MEDALS[i] ?? i + 1}</span>
                <Avatar id={row.memberId} name={row.name} size={34} />
                <div className="flex-1"><div className="font-bold">{row.name}{row.memberId === me && " (you)"}</div><div className="text-xs text-slate">Lv {row.level} · {community.members[row.memberId]?.badges.map((b) => b.emoji).join(" ")}</div></div>
                <span className="font-bold text-forest">{row.xp} XP</span>
              </div>
            ))}
            <div className="mt-4 rounded-2xl bg-amber-pale p-4">
              <div className="font-bold text-amber">This week at the building</div>
              {community.funFacts.map((fact) => <div key={fact} className="mt-1 text-sm">🎉 {fact}</div>)}
              <div className="mt-2 text-sm font-bold">Together you&apos;ve saved {money(community.buildingSavings)} on shipping.</div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function SavingsRow({ label, amount }: { label: string; amount: number }) {
  return <div className="flex justify-between py-3"><span>{label}</span><span className="font-bold text-forest">{money(amount)}</span></div>;
}
