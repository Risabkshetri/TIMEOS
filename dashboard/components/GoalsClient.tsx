"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { formatDuration, formatPercent } from "@/lib/format";
import type { CategoryOut, GoalAlignmentOut, GoalOut } from "@/lib/types";

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function apiRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": readCookie("timeos_csrf") ?? "",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${method} ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** §18's "Mandatory honesty": always rendered with its uncertainty band, never a bare number. */
function GoalAlignmentBadge({ goalId }: { goalId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["goal-alignment", goalId],
    queryFn: () => apiRequest<GoalAlignmentOut>(`/v1/goals/${goalId}/alignment?window=7`, "GET"),
  });

  if (isLoading) {
    return <span className="text-xs text-neutral-400">Loading alignment…</span>;
  }
  if (isError || !data) {
    return <span className="text-xs text-red-600">Alignment unavailable</span>;
  }

  const rangeHalfWidthMinutes = Math.max(data.range_high_minutes - data.aligned_minutes, 0);

  return (
    <p className="text-xs text-neutral-500">
      <span className="mr-1 font-mono uppercase tracking-wide text-amber-600 dark:text-amber-400">
        {data.label}
      </span>
      {formatDuration(data.aligned_minutes * 60)} of {formatDuration(data.target_minutes * 60)}{" "}
      this week (±{formatDuration(rangeHalfWidthMinutes * 60)}) — {formatPercent(data.attainment_ratio)}{" "}
      attainment, {formatPercent(data.coverage_ratio)} coverage
      {data.coverage_ratio < 0.6 ? " (low — treat as a lower bound)" : ""}
    </p>
  );
}

function NewGoalForm({
  categories,
  onCreated,
}: {
  categories: CategoryOut[];
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [priority, setPriority] = useState(3);
  const [targetMinutes, setTargetMinutes] = useState(300);
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? "");

  const mutation = useMutation({
    mutationFn: () =>
      apiRequest("/v1/goals", "POST", {
        name,
        priority,
        target_minutes_per_week: targetMinutes,
        active_from: new Date().toISOString().slice(0, 10),
        mappings: categoryId ? [{ category_id: categoryId, app_key: null, weight: 1.0 }] : [],
      }),
    onSuccess: () => {
      setName("");
      onCreated();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
      className="mb-8 flex flex-wrap items-end gap-3 rounded border border-neutral-200 p-4 dark:border-neutral-800"
    >
      <label className="flex flex-col text-xs text-neutral-500">
        Name
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={60}
          required
          className="w-48 rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </label>
      <label className="flex flex-col text-xs text-neutral-500">
        Priority (1 highest)
        <input
          type="number"
          min={1}
          max={5}
          value={priority}
          onChange={(e) => setPriority(Number(e.target.value))}
          className="w-20 rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </label>
      <label className="flex flex-col text-xs text-neutral-500">
        Target minutes/week
        <input
          type="number"
          min={0}
          value={targetMinutes}
          onChange={(e) => setTargetMinutes(Number(e.target.value))}
          className="w-28 rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
      </label>
      <label className="flex flex-col text-xs text-neutral-500">
        Category
        <select
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          className="w-48 rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        >
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.label}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={mutation.isPending || name.length === 0}
        className="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
      >
        Add goal
      </button>
      {mutation.isError ? <span className="text-xs text-red-600">Failed to create</span> : null}
    </form>
  );
}

export function GoalsClient({
  initialGoals,
  categories,
}: {
  initialGoals: GoalOut[];
  categories: CategoryOut[];
}) {
  const queryClient = useQueryClient();
  const { data: goals } = useQuery({
    queryKey: ["goals"],
    queryFn: () => apiRequest<GoalOut[]>("/v1/goals", "GET"),
    initialData: initialGoals,
  });

  const archiveMutation = useMutation({
    mutationFn: (goalId: string) => apiRequest(`/v1/goals/${goalId}`, "PATCH", { archived: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["goals"] }),
  });

  function categoryLabel(categoryId: string | null): string | undefined {
    return categories.find((category) => category.id === categoryId)?.label;
  }

  return (
    <div>
      <NewGoalForm
        categories={categories}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["goals"] })}
      />

      {goals.length === 0 ? (
        <p className="text-sm text-neutral-500">No goals yet.</p>
      ) : (
        <ul className="space-y-4">
          {goals.map((goal) => (
            <li key={goal.id} className="rounded border border-neutral-200 p-4 dark:border-neutral-800">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium">{goal.name}</h3>
                  <p className="text-xs text-neutral-500">
                    Priority {goal.priority} ·{" "}
                    {goal.mappings
                      .map((mapping) =>
                        mapping.category_id ? categoryLabel(mapping.category_id) : mapping.app_key,
                      )
                      .filter(Boolean)
                      .join(", ") || "no mappings"}
                  </p>
                </div>
                <button
                  onClick={() => archiveMutation.mutate(goal.id)}
                  disabled={archiveMutation.isPending}
                  className="text-xs text-neutral-400 hover:text-red-600 disabled:opacity-50"
                >
                  Archive
                </button>
              </div>
              <div className="mt-2">
                <GoalAlignmentBadge goalId={goal.id} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
