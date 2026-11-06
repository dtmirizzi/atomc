import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["ts/**/*.test.ts"],
    // Every file spawns its own real daemon over `uv run`; running files in
    // parallel would race the shared uv environment and the free-port probe.
    fileParallelism: false,
    testTimeout: 300_000,
    hookTimeout: 300_000,
  },
});
