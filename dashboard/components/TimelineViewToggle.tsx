import Link from "next/link";

// §38 Phase 10: a plain Link-based toggle (matching DateNav's own URL-driven pattern, no client
// state) between the per-device bands and the unified cross-device band.
export function TimelineViewToggle({
  date,
  view,
}: {
  date: string;
  view: "per_device" | "unified";
}) {
  const tabClass = (active: boolean) =>
    `rounded px-3 py-1 ${
      active
        ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
        : "text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
    }`;

  return (
    <div className="mb-4 flex gap-2 text-sm">
      <Link href={`/timeline?date=${date}&view=per_device`} className={tabClass(view === "per_device")}>
        Per device
      </Link>
      <Link href={`/timeline?date=${date}&view=unified`} className={tabClass(view === "unified")}>
        Unified
      </Link>
    </div>
  );
}
