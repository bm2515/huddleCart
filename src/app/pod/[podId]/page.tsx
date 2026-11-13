import HuddleApp from "@/components/HuddleApp";

export default async function PodPage({ params }: { params: Promise<{ podId: string }> }) {
  const { podId } = await params;
  return <HuddleApp initialPodId={podId} />;
}
