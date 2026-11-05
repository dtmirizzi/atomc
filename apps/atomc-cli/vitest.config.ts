import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      include: ["src/**/*.ts"],
      // index.ts is the process bootstrap; default-deps.ts is real fs/spawn/network glue
      // exercised by integration runs, not unit fakes.
      exclude: ["src/index.ts", "src/default-deps.ts"],
      thresholds: {
        lines: 85,
        functions: 85,
        branches: 85,
        statements: 85,
      },
    },
  },
});
