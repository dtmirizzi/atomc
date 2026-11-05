import { describe, expect, it } from "vitest";
import { parsePluginManifest } from "../src/manifest.js";
import {
  normalizeWatchPath,
  watchMatches,
  watchMatchesFiles,
  watchMatchesIr,
} from "../src/watches.js";

const parsed = parsePluginManifest({
  manifest_version: "0.1.0",
  name: "demo",
  version: "0.1.0",
  description: "watch matcher demo",
  atomc: "*",
  runtime: { ts: "./dist/index.js" },
  watches: [
    {
      id: "demo:all",
      ir: ["/electrical/components", "/keyboard/*"],
      files: ["**/*.ato", "board.kicad_pcb"],
    },
  ],
  produces: [],
  gates: [],
  tools: [],
  cli: [],
  ui: [],
});
const watch = parsed.watches[0];
if (!watch) throw new Error("fixture watch missing");

describe("watchMatchesIr", () => {
  it("matches descendant IR changes", () => {
    expect(watchMatchesIr(watch, ["/electrical/components/0/value"])).toBe(true);
  });

  it("matches wildcard segments", () => {
    expect(watchMatchesIr(watch, ["/keyboard/matrix"])).toBe(true);
  });

  it("does not match unrelated pointers", () => {
    expect(watchMatchesIr(watch, ["/firmware/targets"])).toBe(false);
  });
});

describe("watchMatchesFiles", () => {
  it("matches glob patterns", () => {
    expect(watchMatchesFiles(watch, ["boards/keeb/main.ato"])).toBe(true);
    expect(watchMatchesFiles(watch, ["board.kicad_pcb"])).toBe(true);
    expect(watchMatchesFiles(watch, ["notes.md"])).toBe(false);
  });
});

describe("watchMatches", () => {
  it("matches when either IR or files changed", () => {
    expect(watchMatches(watch, { ir: ["/keyboard/keys"] })).toBe(true);
    expect(watchMatches(watch, { files: ["main.ato"] })).toBe(true);
    expect(watchMatches(watch, { ir: ["/orders"], files: ["notes.md"] })).toBe(false);
  });

  it("treats an absent change kind as no change", () => {
    expect(watchMatches(watch, {})).toBe(false);
  });

  it("re-exports path normalization", () => {
    expect(normalizeWatchPath("./a\\\\b.ato")).toBe("a/b.ato");
  });
});
