"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { yesterdayIsoDate } from "@/lib/format";
import type { PrivacyPreviewResponse } from "@/lib/types";

async function fetchPreview(date: string): Promise<PrivacyPreviewResponse> {
  const res = await fetch(`/v1/privacy/preview/${date}`);
  if (!res.ok) {
    throw new Error(`preview failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<PrivacyPreviewResponse>;
}

/** §38 Phase 7 Definition of Done: "the preview endpoint shows a payload the owner is comfortable
 * sending to a third party" — this renders the REAL response from /v1/privacy/preview/{date},
 * exactly as returned, so there's nothing between what's shown here and what would actually cross
 * the boundary to an LLM. */
export function PrivacyPreview() {
  const [date, setDate] = useState(yesterdayIsoDate());

  const mutation = useMutation({
    mutationFn: () => fetchPreview(date),
  });

  return (
    <div>
      <h2 className="mb-3 text-lg font-semibold">Preview what would be sent</h2>
      <div className="mb-4 flex items-center gap-3">
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="rounded border border-neutral-300 px-2 py-1 text-sm dark:border-neutral-700 dark:bg-neutral-900"
        />
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Preview
        </button>
      </div>

      {mutation.isError ? (
        <p className="text-sm text-red-600">Failed to build a preview for this date.</p>
      ) : null}

      {mutation.data ? (
        <div>
          <p className="mb-2 text-xs text-neutral-500">
            SHA-256 of this exact payload: <code>{mutation.data.payload_sha256}</code>
          </p>
          <pre className="max-h-[32rem] overflow-auto rounded-lg border border-neutral-200 bg-neutral-50 p-4 text-xs dark:border-neutral-800 dark:bg-neutral-900">
            {JSON.stringify(mutation.data.context, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
