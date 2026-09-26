import { AnalysisView } from "@/components/AnalysisView";
import { AnalyzeButton } from "@/components/AnalyzeButton";
import { DateNav } from "@/components/DateNav";
import { apiGetOrNull } from "@/lib/api";
import { yesterdayIsoDate } from "@/lib/format";
import type { AnalysisOut } from "@/lib/types";

export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  const targetDate = date ?? yesterdayIsoDate();

  const analysis = await apiGetOrNull<AnalysisOut>(`/v1/insights/${targetDate}`);

  return (
    <div>
      <DateNav basePath="/insights" date={targetDate} />
      <h1 className="mb-6 text-lg font-semibold">Diagnosis</h1>
      {analysis ? <AnalysisView analysis={analysis} /> : <AnalyzeButton date={targetDate} />}
    </div>
  );
}
