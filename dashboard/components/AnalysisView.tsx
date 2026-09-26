import { formatPercent } from "@/lib/format";
import type { AnalysisOut, InsightOut } from "@/lib/types";

const SECTION_LABELS: Record<string, string> = {
  wins: "Wins",
  problems: "Problems",
  patterns: "Patterns",
  distractions: "Distractions",
  goal_alignment: "Goal alignment",
};

const EPISTEMIC_STYLES: Record<string, string> = {
  FACT: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  INFERENCE: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  HYPOTHESIS: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
};

function EpistemicBadge({ status }: { status: string | null }) {
  if (!status) return null;
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${EPISTEMIC_STYLES[status] ?? "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"}`}
    >
      {status}
    </span>
  );
}

function InsightCard({ insight }: { insight: InsightOut }) {
  return (
    <li className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
      <div className="mb-1 flex items-center gap-2">
        <EpistemicBadge status={insight.epistemic_status} />
        <span className="text-xs text-neutral-500">{formatPercent(insight.confidence)} confident</span>
      </div>
      <p className="text-sm">{insight.claim}</p>
      {insight.evidence.narrative ? (
        <p className="mt-1 text-xs text-neutral-500">{insight.evidence.narrative}</p>
      ) : null}
    </li>
  );
}

function RecommendationCard({ insight }: { insight: InsightOut }) {
  return (
    <li className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
      <div className="mb-1 flex items-center gap-2">
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
          {String(insight.evidence.effort ?? "?")} effort
        </span>
        <span className="text-xs text-neutral-500">{formatPercent(insight.confidence)} confident</span>
      </div>
      <p className="text-sm font-medium">{insight.claim}</p>
      {insight.evidence.rationale ? (
        <p className="mt-1 text-xs text-neutral-500">{String(insight.evidence.rationale)}</p>
      ) : null}
      {insight.evidence.measurable_check ? (
        <p className="mt-1 text-xs text-neutral-400">
          Check: {String(insight.evidence.measurable_check)}
        </p>
      ) : null}
    </li>
  );
}

/** §22.3/§23.3: this renders EXACTLY what survived timeos.ai.validate — a dropped day_score
 * shows as "not available" rather than a fabricated fallback number, and every insight still
 * carries its epistemic_status and confidence, never presented as bare fact. */
export function AnalysisView({ analysis }: { analysis: AnalysisOut }) {
  const recommendations = analysis.insights.filter((i) => i.kind === "recommendation");

  return (
    <div>
      {analysis.validation_status !== "ok" ? (
        <p className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
          {analysis.validation_status === "failed"
            ? "The AI's response couldn't be validated — no narrative is available for this day."
            : "Some of the AI's output couldn't be verified against this day's data and was left out."}
        </p>
      ) : null}

      <div className="mb-6 flex items-baseline gap-4">
        <span className="text-3xl font-semibold">
          {analysis.day_score !== null ? analysis.day_score : "—"}
        </span>
        <span className="text-sm text-neutral-500">
          {analysis.day_score !== null ? "/ 100" : "day score not available"}
        </span>
        {analysis.overall_confidence !== null ? (
          <span className="text-xs text-neutral-400">
            {formatPercent(analysis.overall_confidence)} overall confidence
          </span>
        ) : null}
      </div>

      {analysis.score_rationale ? (
        <p className="mb-2 text-sm text-neutral-600 dark:text-neutral-400">
          {analysis.score_rationale}
        </p>
      ) : null}
      {analysis.summary ? <p className="mb-6 text-sm">{analysis.summary}</p> : null}

      {analysis.data_caveats.length > 0 ? (
        <ul className="mb-6 list-inside list-disc text-xs text-neutral-500">
          {analysis.data_caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      ) : null}

      {Object.entries(SECTION_LABELS).map(([kind, label]) => {
        const items = analysis.insights.filter((i) => i.kind === kind);
        if (items.length === 0) return null;
        return (
          <div key={kind} className="mb-6">
            <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
              {label}
            </h3>
            <ul className="space-y-2">
              {items.map((insight) => (
                <InsightCard key={insight.id} insight={insight} />
              ))}
            </ul>
          </div>
        );
      })}

      {recommendations.length > 0 ? (
        <div className="mb-6">
          <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
            Recommendations
          </h3>
          <ul className="space-y-2">
            {recommendations.map((insight) => (
              <RecommendationCard key={insight.id} insight={insight} />
            ))}
          </ul>
        </div>
      ) : null}

      {analysis.tomorrow_priorities.length > 0 ? (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
            Tomorrow
          </h3>
          <ul className="list-inside list-disc text-sm">
            {analysis.tomorrow_priorities.map((priority) => (
              <li key={priority}>{priority}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
