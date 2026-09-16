import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// §25/§28: "strict CSP", implemented as Next.js's own documented nonce pattern
// (https://nextjs.org/docs/app/guides/content-security-policy) rather than a static policy: a
// first attempt with a plain `script-src 'self'` in next.config.ts's headers() looked stricter
// but was actually broken — verified with Playwright capturing real browser console errors —
// because Next injects its own inline hydration/RSC-payload scripts on every page, which a
// nonce-less 'self' unconditionally blocks. The nonce here is generated fresh per request,
// forwarded to the app via the x-nonce request header (root layout reads it back out to apply to
// its own script tags if it ever needs to), and echoed into the CSP response header — Next
// recognizes a nonce present in its own CSP header and stamps its inline scripts with it
// automatically, which is what makes the app actually still hydrate under this policy (verified
// with the same Playwright console-error capture, clean on the second pass).
export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV === "development";

  const csp = [
    "default-src 'self'",
    // 'unsafe-eval' is required in dev only, for webpack's HMR/React Refresh runtime — never
    // shipped in a production build.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'", // Tailwind's compiled utility classes, recharts' inline SVG styling
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    // Skip static assets and image optimization — no need to pay the nonce-generation cost or
    // set a CSP header meant for HTML documents on a .js/.css/.png response.
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
