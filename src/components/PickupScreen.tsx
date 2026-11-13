"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { Pod } from "@/lib/types";
import { HandoffProof, PickupPass, api, money, primaryButton, type Bag } from "./shared";
import { useMe } from "./useMe";

type PickupInfo = { pod: Pod; bag: Bag; hostName: string };

/** What a scanned or shared pickup QR opens. The host confirms the handoff; anyone else sees the pass. */
export default function PickupScreen({ token }: { token: string }) {
  const [me] = useMe();
  const [info, setInfo] = useState<PickupInfo | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [collectedBy, setCollectedBy] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await api<PickupInfo & { ok?: boolean }>(`/api/pickup/${token}`);
    if (result.ok === false) return setNotFound(true);
    setInfo(result);
  }, [token]);
  useEffect(() => { load(); }, [load]);

  async function confirm() {
    const result = await api<{ ok: boolean; reason?: string }>(`/api/pickup/${token}/confirm`, { method: "POST", body: JSON.stringify({ memberId: me, collectedBy }) });
    if (!result.ok) setError(result.reason ?? "Couldn't confirm");
    load();
  }

  const isHost = info && info.pod.leaderId === me;
  return (
    <div className="flex min-h-dvh justify-center">
      <div className="w-full max-w-[440px] bg-white p-5 shadow-[0_10px_60px_rgba(24,39,36,0.15)]">
        <Link href="/" className="font-display text-xl font-extrabold text-forest">HuddleCart</Link>
        {notFound && <div className="mt-6 rounded-xl bg-amber-pale p-4 text-amber">This pickup pass isn&apos;t valid.</div>}
        {info && (
          <>
            <h1 className="mt-4 font-display text-[26px] font-extrabold">{isHost ? "Confirm handoff" : "Pickup pass"}</h1>
            <div className="mb-4 text-slate">{info.pod.name} · bag #{info.bag.bag} for {info.bag.name}</div>
            {isHost ? (
              <div className="space-y-3">
                <div className="rounded-xl bg-cream p-4">
                  {info.bag.items.map((i) => <div key={i.title} className="flex justify-between text-sm"><span className="truncate pr-2">{i.qty} × {i.title}</span><span>{money(i.total)}</span></div>)}
                  <div className="mt-1 flex justify-between border-t border-line pt-1 font-bold"><span>Owed to you</span><span>{money(info.bag.amountDue)} {info.bag.paid ? "· paid ✓" : ""}</span></div>
                </div>
                {info.bag.collected ? <HandoffProof bag={info.bag} hostName={info.hostName} /> : (
                  <>
                    <label className="block rounded-xl border border-line p-3"><span className="text-xs text-slate">Who is picking it up?</span>
                      <input value={collectedBy} onChange={(e) => setCollectedBy(e.target.value)} placeholder={info.bag.name} className="block w-full font-bold outline-none" />
                    </label>
                    {error && <div className="text-sm text-berry">{error}</div>}
                    <button onClick={confirm} className={primaryButton}>Hand over bag #{info.bag.bag}</button>
                  </>
                )}
              </div>
            ) : <PickupPass bag={info.bag} pod={info.pod} hostName={info.hostName} />}
          </>
        )}
      </div>
    </div>
  );
}
