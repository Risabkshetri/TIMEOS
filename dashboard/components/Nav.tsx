"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const LINKS = [
  { href: "/today", label: "Today" },
  { href: "/timeline", label: "Timeline" },
  { href: "/where-time-went", label: "Where Time Went" },
  { href: "/focus", label: "Focus" },
  { href: "/system-health", label: "System Health" },
];

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    const csrfToken = readCookie("timeos_csrf") ?? "";
    await fetch("/v1/auth/logout", {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken },
    });
    router.push("/login");
    router.refresh();
  }

  return (
    <nav className="flex items-center justify-between border-b border-neutral-200 px-6 py-3 dark:border-neutral-800">
      <div className="flex items-center gap-5">
        <span className="font-semibold">TimeOS</span>
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={
              pathname === link.href
                ? "text-sm font-medium text-indigo-600 dark:text-indigo-400"
                : "text-sm text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
            }
          >
            {link.label}
          </Link>
        ))}
      </div>
      <button
        onClick={handleLogout}
        className="text-sm text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
      >
        Sign out
      </button>
    </nav>
  );
}
