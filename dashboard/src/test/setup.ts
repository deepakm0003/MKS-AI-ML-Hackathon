import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { clearApiCache } from "../api/client";

// jsdom doesn't implement IntersectionObserver — stub it so the LandingPage
// (which uses useInView) doesn't crash the shell tests.
if (typeof IntersectionObserver === "undefined") {
  const mockIO = vi.fn(() => ({
    observe:    vi.fn(),
    unobserve:  vi.fn(),
    disconnect: vi.fn(),
  }));
  vi.stubGlobal("IntersectionObserver", mockIO);
}

afterEach(() => {
  cleanup();
  clearApiCache();
  vi.unstubAllGlobals();
});
