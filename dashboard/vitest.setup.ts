import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// vitest.config.ts doesn't enable `globals: true` (deliberately — explicit `import { describe,
// it, expect } from "vitest"` in every test file is clearer about what's a testing primitive vs.
// a browser/DOM global), so React Testing Library's usual auto-cleanup (which detects jest/
// vitest via a global afterEach) never registers on its own. Without this, each test's rendered
// DOM leaks into the next test, and assertions like `queryByText` or `getByTestId` start
// matching a PREVIOUS test's leftover markup instead of (or in addition to) the current one.
afterEach(() => {
  cleanup();
});
