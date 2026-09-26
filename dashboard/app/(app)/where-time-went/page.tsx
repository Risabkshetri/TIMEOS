import { CategoryTreemap } from "@/components/CategoryTreemap";
import { CorrectionForm } from "@/components/CorrectionForm";
import { DateNav } from "@/components/DateNav";
import { apiGet } from "@/lib/api";
import { formatDuration, formatTime, yesterdayIsoDate } from "@/lib/format";
import type { ActivitiesResponse, CategoryOut, DayResponse } from "@/lib/types";

// §25's named failure case: ">200 sessions in a day (virtualise)". A day with real personal-scale
// usage rarely approaches this, so full list virtualization (react-window et al.) would be
// disproportionate machinery for a case that's never been observed against real data — a simple
// render cap keeps the DOM bounded without that dependency, revisited if a real day ever needs it.
const MAX_RENDERED_ROWS = 200;

export default async function WhereTimeWentPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  const targetDate = date ?? yesterdayIsoDate();

  const [{ categories }, { activities }, allCategories] = await Promise.all([
    apiGet<DayResponse>(`/v1/days/${targetDate}`),
    apiGet<ActivitiesResponse>(`/v1/days/${targetDate}/activities`),
    apiGet<CategoryOut[]>("/v1/categories"),
  ]);
  const correctableCategories = allCategories.filter((c) => !c.is_system);

  return (
    <div>
      <DateNav basePath="/where-time-went" date={targetDate} />

      <CategoryTreemap categories={categories} />

      <h2 className="mt-8 mb-3 text-lg font-semibold">Activity log</h2>
      {activities.length === 0 ? (
        <p className="text-sm text-neutral-500">No classified activity this day.</p>
      ) : (
        <>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-neutral-500 dark:border-neutral-800">
                <th className="py-2 font-normal">Time</th>
                <th className="py-2 font-normal">App</th>
                <th className="py-2 font-normal">Category</th>
                <th className="py-2 font-normal">Duration</th>
                <th className="py-2 font-normal" />
              </tr>
            </thead>
            <tbody>
              {activities.slice(0, MAX_RENDERED_ROWS).map((activity) => (
                <tr key={activity.id} className="border-b border-neutral-100 dark:border-neutral-900">
                  <td className="py-2 tabular-nums text-neutral-500">
                    {formatTime(activity.start_ts)}
                  </td>
                  <td className="py-2">{activity.app_keys.join(", ") || "—"}</td>
                  <td className="py-2">{activity.category_label}</td>
                  <td className="py-2 tabular-nums">{formatDuration(activity.duration_s)}</td>
                  <td className="py-2">
                    <CorrectionForm
                      activityId={activity.id}
                      currentLabel={activity.category_label}
                      categories={correctableCategories}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {activities.length > MAX_RENDERED_ROWS ? (
            <p className="mt-3 text-xs text-neutral-500">
              Showing the first {MAX_RENDERED_ROWS} of {activities.length} activities.
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
