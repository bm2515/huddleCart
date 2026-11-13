"use client";

import { useEffect, useRef, useState } from "react";

type Detector = { detect: (source: HTMLVideoElement) => Promise<{ rawValue: string }[]> };
type DetectorConstructor = new (options: { formats: string[] }) => Detector;

/** Uses the browser's BarcodeDetector when it exists. Otherwise the phone camera app works too: the QR is a link. */
export default function QrScanner({ onScan }: { onScan: (url: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const BarcodeDetector = (window as unknown as { BarcodeDetector?: DetectorConstructor }).BarcodeDetector;
    if (!BarcodeDetector || !navigator.mediaDevices) {
      setProblem("This browser can't scan in the app. Open your phone camera and point it at the pass instead.");
      return;
    }
    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    let stream: MediaStream | null = null;
    let timer: ReturnType<typeof setInterval>;
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then((s) => {
      stream = s;
      if (!video.current) return;
      video.current.srcObject = s;
      video.current.play();
      timer = setInterval(async () => {
        const [code] = await detector.detect(video.current!).catch(() => []);
        if (code?.rawValue.includes("/pickup/")) onScan(code.rawValue);
      }, 400);
    }).catch(() => setProblem("Camera access was blocked. Allow the camera, or use your phone camera app."));
    return () => { clearInterval(timer); stream?.getTracks().forEach((t) => t.stop()); };
  }, [onScan]);

  return problem ? (
    <div className="rounded-xl bg-amber-pale p-4 text-sm text-amber">{problem}</div>
  ) : (
    <div>
      <video ref={video} className="aspect-square w-full rounded-2xl bg-ink object-cover" muted playsInline />
      <div className="mt-2 text-center text-sm text-slate">Point at a neighbor&apos;s pickup pass</div>
    </div>
  );
}
