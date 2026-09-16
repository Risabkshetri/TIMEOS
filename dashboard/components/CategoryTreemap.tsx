"use client";

import { ResponsiveContainer, Tooltip, Treemap } from "recharts";
import type { CategoryBreakdown } from "@/lib/types";
import { formatDuration } from "@/lib/format";

const COLORS = ["#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#0ea5e9", "#ef4444"];

export function CategoryTreemap({ categories }: { categories: CategoryBreakdown[] }) {
  if (categories.length === 0) {
    return <p className="text-sm text-neutral-500">No classified activity this day.</p>;
  }

  const data = categories.map((c, i) => ({
    name: c.label,
    size: c.duration_s,
    fill: COLORS[i % COLORS.length],
  }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <Treemap
          data={data}
          dataKey="size"
          stroke="#fff"
          aspectRatio={4 / 3}
          isAnimationActive={false}
        >
          <Tooltip
            formatter={(value, _name, item) => [
              formatDuration(Number(value ?? 0)),
              (item?.payload as { name?: string } | undefined)?.name ?? "",
            ]}
          />
        </Treemap>
      </ResponsiveContainer>
    </div>
  );
}
