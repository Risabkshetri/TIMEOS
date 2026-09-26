"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { CategoryOut, ClassificationCorrectionResponse } from "@/lib/types";

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function submitCorrection(
  activityId: string,
  correctedCategoryKey: string,
  applyAsRule: boolean,
  applyRetroactively: boolean,
): Promise<ClassificationCorrectionResponse> {
  const res = await fetch("/v1/feedback/classification", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": readCookie("timeos_csrf") ?? "",
    },
    body: JSON.stringify({
      activity_id: activityId,
      corrected_category_key: correctedCategoryKey,
      apply_as_rule: applyAsRule,
      apply_retroactively: applyRetroactively,
    }),
  });
  if (!res.ok) {
    throw new Error(`classification correction failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<ClassificationCorrectionResponse>;
}

/** §15.4's correction loop, applied for real (Phase 6): picks a real category from the user's
 * own taxonomy (never free text — corrected_category_key must resolve to an existing category)
 * and posts to /v1/feedback/classification, which inserts a new activities row, updates the
 * app_classifications learned prior (or sets a standing L0 rule when "always classify this app
 * this way" is checked), and optionally recomputes every other day with this app. */
export function CorrectionForm({
  activityId,
  currentLabel,
  categories,
}: {
  activityId: string;
  currentLabel: string;
  categories: CategoryOut[];
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [categoryKey, setCategoryKey] = useState(categories[0]?.key ?? "");
  const [applyAsRule, setApplyAsRule] = useState(false);
  const [applyRetroactively, setApplyRetroactively] = useState(false);

  const mutation = useMutation({
    mutationFn: () => submitCorrection(activityId, categoryKey, applyAsRule, applyRetroactively),
    onSuccess: () => {
      // The corrected day's own activities changed; other days only changed if a retroactive
      // recompute ran, but invalidating broadly here is cheap at personal scale and simpler than
      // tracking exactly which dates a query might be caching.
      queryClient.invalidateQueries({ queryKey: ["goals"] });
      queryClient.invalidateQueries({ queryKey: ["goal-alignment"] });
    },
  });

  if (mutation.isSuccess) {
    return <span className="text-xs text-green-700 dark:text-green-400">Corrected.</span>;
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-xs text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
      >
        Not {currentLabel}?
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
      className="flex flex-col gap-1.5"
    >
      <div className="flex items-center gap-2">
        <select
          value={categoryKey}
          onChange={(e) => setCategoryKey(e.target.value)}
          className="rounded border border-neutral-300 px-1.5 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
          autoFocus
        >
          {categories.map((category) => (
            <option key={category.id} value={category.key}>
              {category.label}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={mutation.isPending || categoryKey.length === 0}
          className="text-xs font-medium text-indigo-600 disabled:opacity-50 dark:text-indigo-400"
        >
          Send
        </button>
      </div>
      <label className="flex items-center gap-1 text-xs text-neutral-500">
        <input
          type="checkbox"
          checked={applyAsRule}
          onChange={(e) => setApplyAsRule(e.target.checked)}
        />
        Always classify this app this way
      </label>
      <label className="flex items-center gap-1 text-xs text-neutral-500">
        <input
          type="checkbox"
          checked={applyRetroactively}
          onChange={(e) => setApplyRetroactively(e.target.checked)}
        />
        Apply to past days with this app too
      </label>
      {mutation.isError ? <span className="text-xs text-red-600">Failed</span> : null}
    </form>
  );
}
