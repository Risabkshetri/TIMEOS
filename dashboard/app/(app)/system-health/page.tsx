import { apiGet } from "@/lib/api";
import type { CollectorsHealthResponse } from "@/lib/types";

function timeSince(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default async function SystemHealthPage() {
  const { collectors } = await apiGet<CollectorsHealthResponse>("/v1/health/collectors");

  return (
    <div>
      <h1 className="mb-4 text-lg font-semibold">Collectors</h1>
      {collectors.length === 0 ? (
        <p className="text-sm text-neutral-500">No devices enrolled yet.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {collectors.map((collector) => {
            const isStale =
              collector.last_seen_at === null ||
              Date.now() - new Date(collector.last_seen_at).getTime() > 1000 * 60 * 60 * 6;
            return (
              <div
                key={collector.device_id}
                className="flex items-center justify-between rounded-lg border border-neutral-200 p-4 dark:border-neutral-800"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{collector.name}</span>
                    <span className="text-xs text-neutral-500">{collector.platform}</span>
                    {collector.revoked ? (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-950 dark:text-red-300">
                        Revoked
                      </span>
                    ) : isStale ? (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                        Not syncing
                      </span>
                    ) : (
                      <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-950 dark:text-green-300">
                        Healthy
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-neutral-500">
                    Last seen {timeSince(collector.last_seen_at)} · seq {collector.last_seq}
                  </p>
                </div>
                {collector.rejected_batch_count > 0 ? (
                  <span className="text-xs text-red-600 dark:text-red-400">
                    {collector.rejected_batch_count} rejected batch
                    {collector.rejected_batch_count === 1 ? "" : "es"}
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
