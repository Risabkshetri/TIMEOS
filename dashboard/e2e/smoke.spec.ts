import { expect, test } from "@playwright/test";

// §25's "E2E smoke": proves the real login -> session cookie -> five real views -> logout loop
// works end to end against the real backend, not that any one view's content is pixel-perfect.
// Requires a real dashboard password already set via `python -m
// timeos.jobs.set_dashboard_password` against the backend this dev server is pointed at —
// there's no bootstrap-a-fresh-user step here, matching how a real deployment actually works
// (one owner, one password, set once).
const PASSWORD = process.env.E2E_DASHBOARD_PASSWORD ?? "timeos-dev-dashboard-password-2026";

test("root path redirects to /login when signed out", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "TimeOS" })).toBeVisible();
});

test("wrong password stays on the login page with an error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Dashboard password").fill("definitely-not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Incorrect password.")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("correct password signs in and every nav view loads without error", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Dashboard password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/today$/);

  const views: Array<{ label: string; heading: RegExp }> = [
    { label: "Today", heading: /Where time went/ },
    { label: "Timeline", heading: /Tracked|Idle|Unobserved|Device offline/ },
    { label: "Where Time Went", heading: /Activity log/ },
    { label: "Focus", heading: /Session list/ },
    { label: "System Health", heading: /Collectors/ },
  ];

  for (const view of views) {
    await page.getByRole("link", { name: view.label, exact: true }).click();
    await expect(page.getByText(view.heading).first()).toBeVisible();
    // A thrown server-component error renders Next's own generic digest page — this catches
    // that class of failure even when a view's happy-path assertion above would still pass.
    await expect(page.getByText(/application error/i)).toHaveCount(0);
  }
});

test("signing out ends the session", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Dashboard password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/today$/);

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/today");
  await expect(page).toHaveURL(/\/login$/);
});
