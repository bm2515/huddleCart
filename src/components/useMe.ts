"use client";
import { useEffect, useState } from "react";

export function useMe() {
  const [me, setMe] = useState("bisma");
  useEffect(() => {
    const saved = localStorage.getItem("huddle:me");
    if (saved) setMe(saved);
  }, []);
  const update = (v: string) => {
    localStorage.setItem("huddle:me", v);
    setMe(v);
  };
  return [me, update] as const;
}
