import { PrivacyPreview } from "@/components/PrivacyPreview";
import { apiGet } from "@/lib/api";
import { formatTime } from "@/lib/format";
import type { PrivacyAuditEventOut } from "@/lib/types";

export default async function PrivacyPage() {
  const auditEvents = await apiGet<PrivacyAuditEventOut[]>("/v1/privacy/audit");

  return (
    <div>
      <h1 className="mb-6 text-lg font-semibold">Privacy</h1>

      <PrivacyPreview />

      <h2 className="mt-10 mb-3 text-lg font-semibold">Audit log</h2>
      {auditEvents.length === 0 ? (
        <p className="text-sm text-neutral-500">
          No privacy gate calls yet — nothing has been prepared for an AI analysis.
        </p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-neutral-500 dark:border-neutral-800">
              <th className="py-2 font-normal">When</th>
              <th className="py-2 font-normal">Actor</th>
              <th className="py-2 font-normal">Outcome</th>
              <th className="py-2 font-normal">Fields</th>
              <th className="py-2 font-normal">Shares app names</th>
              <th className="py-2 font-normal">Digest</th>
            </tr>
          </thead>
          <tbody>
            {auditEvents.map((event) => (
              <tr key={event.id} className="border-b border-neutral-100 dark:border-neutral-900">
                <td className="py-2 tabular-nums text-neutral-500">
                  {formatTime(event.occurred_at)}
                </td>
                <td className="py-2">{event.actor}</td>
                <td className="py-2">
                  {event.outcome === "allowed" ? (
                    <span className="text-green-700 dark:text-green-400">Allowed</span>
                  ) : (
                    <span className="text-red-600 dark:text-red-400">
                      Rejected ({event.rejected_fields.length})
                    </span>
                  )}
                </td>
                <td className="py-2 tabular-nums">{event.field_count}</td>
                <td className="py-2">{event.ai_share_app_names ? "Yes" : "No"}</td>
                <td className="py-2 font-mono text-xs text-neutral-500">
                  {event.payload_sha256.slice(0, 12)}…
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
