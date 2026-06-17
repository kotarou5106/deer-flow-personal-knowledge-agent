import { KnowledgeWorkspacePage } from "@/components/workspace/knowledge";

export default async function KnowledgeSourceDetailPage({
  params,
}: {
  params: Promise<{ source_id: string }>;
}) {
  const { source_id } = await params;
  return <KnowledgeWorkspacePage view="source-detail" sourceId={source_id} />;
}
