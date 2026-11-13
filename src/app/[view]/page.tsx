import { notFound } from "next/navigation";
import HuddleApp from "@/components/HuddleApp";

const SCREEN_FOR_PATH: Record<string, string> = { orders: "orders", savings: "savings", community: "community", leaderboard: "savings", discover: "home" };

export default async function ViewPage({ params }: { params: Promise<{ view: string }> }) {
  const { view } = await params;
  if (!SCREEN_FOR_PATH[view]) notFound();
  return <HuddleApp initialScreen={SCREEN_FOR_PATH[view]} />;
}
