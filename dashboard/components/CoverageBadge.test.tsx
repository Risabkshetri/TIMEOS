import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoverageBadge } from "@/components/CoverageBadge";

describe("CoverageBadge", () => {
  it("marks ratios below 0.6 as low coverage (§14.3's gate)", () => {
    render(<CoverageBadge ratio={0.25} />);
    const badge = screen.getByTestId("coverage-badge");
    expect(badge.dataset.coverageLevel).toBe("low");
    expect(badge.textContent).toContain("25%");
  });

  it("marks ratios at or above 0.9 as high coverage", () => {
    render(<CoverageBadge ratio={0.95} />);
    expect(screen.getByTestId("coverage-badge").dataset.coverageLevel).toBe("high");
  });

  it("marks ratios between 0.6 and 0.9 as partial coverage", () => {
    render(<CoverageBadge ratio={0.75} />);
    expect(screen.getByTestId("coverage-badge").dataset.coverageLevel).toBe("partial");
  });

  it("treats the 0.6 boundary itself as no longer low", () => {
    render(<CoverageBadge ratio={0.6} />);
    expect(screen.getByTestId("coverage-badge").dataset.coverageLevel).not.toBe("low");
  });
});
