import { describe, expect, it } from "vitest";
import {
  isSafeRelativePath,
  matchesAnyGlob,
  matchesGlob,
  normalizeProjectPath,
} from "../src/glob.js";

describe("normalizeProjectPath", () => {
  it("normalizes POSIX relative paths", () => {
    expect(normalizeProjectPath("./src\\a//b.ato/")).toBe("src/a/b.ato");
    expect(normalizeProjectPath("a/b")).toBe("a/b");
  });
});

describe("isSafeRelativePath", () => {
  it("accepts relative paths", () => {
    expect(isSafeRelativePath("./dist/index.js")).toBe(true);
    expect(isSafeRelativePath("dist/index.js")).toBe(true);
  });

  it("rejects absolute, drive-letter and escaping paths", () => {
    expect(isSafeRelativePath("/etc/passwd")).toBe(false);
    expect(isSafeRelativePath("../secret")).toBe(false);
    expect(isSafeRelativePath("./a/../../b")).toBe(false);
    expect(isSafeRelativePath("C:/x")).toBe(false);
    expect(isSafeRelativePath("")).toBe(false);
  });
});

describe("matchesGlob", () => {
  it("matches `*` within a segment only", () => {
    expect(matchesGlob("*.ato", "main.ato")).toBe(true);
    expect(matchesGlob("*.ato", "boards/main.ato")).toBe(false);
  });

  it("matches `**` across segments, including zero", () => {
    expect(matchesGlob("**/*.ato", "boards/keeb/main.ato")).toBe(true);
    expect(matchesGlob("**/*.ato", "main.ato")).toBe(true);
    expect(matchesGlob("boards/**", "boards/keeb/main.ato")).toBe(true);
    expect(matchesGlob("boards/**/main.ato", "boards/keeb/main.ato")).toBe(true);
    expect(matchesGlob("boards/**/main.ato", "boards/main.ato")).toBe(true);
  });

  it("supports `?` single-character matching", () => {
    expect(matchesGlob("a?c.ato", "abc.ato")).toBe(true);
    expect(matchesGlob("a?c.ato", "ac.ato")).toBe(false);
  });

  it("normalizes both pattern and path", () => {
    expect(matchesGlob("./boards/*.ato", "boards\\main.ato")).toBe(true);
  });

  it("does not match absolute paths", () => {
    expect(matchesGlob("**/*.ts", "/abs/x.ts")).toBe(false);
  });

  it("matches any of a pattern list", () => {
    expect(matchesAnyGlob(["**/*.ato", "**/*.kicad_pcb"], "board.kicad_pcb")).toBe(true);
    expect(matchesAnyGlob(["**/*.ato"], "board.kicad_pcb")).toBe(false);
  });
});
