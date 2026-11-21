import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { clearApiCache } from "../api/client";

afterEach(() => {
  cleanup();
  clearApiCache();
  vi.unstubAllGlobals();
});
