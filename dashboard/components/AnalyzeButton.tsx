"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function triggerAnalysis(date: string): Promise<void> {
  const res = await fetch(`/v1/ai/analyze/${date}`, {
    method: "POST",
    headers: { "X-CSRF-Token": readCookie("timeos_csrf") ?? "" },
  });
  if (!res.ok) {
    throw new Error(`analysis request failed: ${res.status} ${await res.text()}`);
  }
}

/** §22.9: "manual triggers capped at 5/day" — a 429 here means that cap was hit, not a bug. */
export function AnalyzeButton({ date }: { date: string }) {
  const router = useRouter();
  const mutation = useMutation({
    mutationFn: () => triggerAnalysis(date),
    onSuccess: () => router.refresh(),
  });

  return (
    <div className="rounded-lg border border-neutral-200 p-6 text-center dark:border-neutral-800">
      <p className="mb-3 text-sm text-neutral-500">No AI analysis exists for this day yet.</p>
      <button
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {mutation.isPending ? "Analyzing…" : "Analyze this day"}
      </button>
      {mutation.isError ? (
        <p className="mt-3 text-xs text-red-600">
          {mutation.error instanceof Error && mutation.error.message.includes("429")
            ? "You've reached today's limit of 5 manual analyses."
            : "Analysis failed. The AI provider may be unavailable — the rest of the dashboard is unaffected."}
        </p>
      ) : null}
    </div>
  );
}
