import Link from "next/link";
import { shiftDate } from "@/lib/format";

export function DateNav({ basePath, date }: { basePath: string; date: string }) {
  return (
    <div className="mb-4 flex items-center gap-3 text-sm">
      <Link
        href={`${basePath}?date=${shiftDate(date, -1)}`}
        className="text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
      >
        ← Previous day
      </Link>
      <span className="font-medium">{date}</span>
      <Link
        href={`${basePath}?date=${shiftDate(date, 1)}`}
        className="text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
      >
        Next day →
      </Link>
    </div>
  );
}
