import HuddleApp from "@/components/HuddleApp";

export default async function EventPage({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  return <HuddleApp initialScreen={`event:${eventId}`} />;
}
