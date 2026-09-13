// Phase 0 stub. Real views (Today, Timeline, Focus, ...) land starting Phase 5
// per docs/TIMEOS_ENGINEERING_SPEC.md §25.
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-2 p-8">
      <h1 className="text-2xl font-semibold">TimeOS</h1>
      <p className="text-neutral-500">Dashboard scaffold — Phase 0. No product views yet.</p>
    </main>
  );
}
