import { cookies } from "next/headers";
import { redirect } from "next/navigation";

// Server components run in Node, not the browser, so they can't rely on next.config.ts's
// browser-facing rewrite (see that file's comment) — they call the backend directly and forward
// the session cookie by hand. BACKEND_INTERNAL_URL lets this resolve to the Docker service name
// ("http://api:8000") in production while defaulting to localhost for `npm run dev`.
const BACKEND_URL = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

async function cookieHeader(): Promise<string> {
  const store = await cookies();
  return store
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
}

/** GET from a server component. Redirects to /login on 401 rather than throwing, since an
 * expired/missing session is an expected, navigable state, not an error. */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    headers: { cookie: await cookieHeader() },
    cache: "no-store",
  });
  if (res.status === 401) {
    redirect("/login");
  }
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}
