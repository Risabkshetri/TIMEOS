"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function submitCorrection(activityId: string, suggestedCategory: string): Promise<void> {
  const res = await fetch("/v1/feedback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": readCookie("timeos_csrf") ?? "",
    },
    body: JSON.stringify({
      target_type: "activity",
      target_id: activityId,
      correction: { suggested_category: suggestedCategory },
    }),
  });
  if (!res.ok) {
    throw new Error(`feedback submission failed: ${res.status}`);
  }
}

/** §25's "correction affordance wired to Phase 6's feedback endpoint stub". Submits durably to
 * user_feedback; nothing re-classifies until Phase 6's correction-application logic exists
 * (§15.4) — this only needs to prove the round trip works, which is why it just confirms receipt
 * rather than showing an updated category. */
export function CorrectionForm({
  activityId,
  currentLabel,
}: {
  activityId: string;
  currentLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const [suggestedCategory, setSuggestedCategory] = useState("");

  const mutation = useMutation({
    mutationFn: () => submitCorrection(activityId, suggestedCategory),
  });

  if (mutation.isSuccess) {
    return <span className="text-xs text-green-700 dark:text-green-400">Thanks, noted.</span>;
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
      className="flex items-center gap-2"
    >
      <input
        type="text"
        placeholder="What should this be?"
        value={suggestedCategory}
        onChange={(e) => setSuggestedCategory(e.target.value)}
        className="w-36 rounded border border-neutral-300 px-1.5 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
        autoFocus
      />
      <button
        type="submit"
        disabled={mutation.isPending || suggestedCategory.length === 0}
        className="text-xs font-medium text-indigo-600 disabled:opacity-50 dark:text-indigo-400"
      >
        Send
      </button>
      {mutation.isError ? <span className="text-xs text-red-600">Failed</span> : null}
    </form>
  );
}
