import PickupScreen from "@/components/PickupScreen";

export default async function PickupPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <PickupScreen token={token} />;
}
