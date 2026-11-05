import { describe, expect, it } from "vitest";
import {
  escapePointerToken,
  getAt,
  joinPointer,
  parsePointer,
  unescapePointerToken,
} from "../src/lib/pointer.js";

describe("pointer tokens", () => {
  it("escapes ~ and /", () => {
    expect(escapePointerToken("a/b~c")).toBe("a~1b~0c");
  });

  it("unescapes in the correct order", () => {
    expect(unescapePointerToken("a~1b~0c")).toBe("a/b~c");
  });

  it("round-trips arbitrary tokens", () => {
    for (const token of ["", "plain", "a/b", "~x", "~1", "a~1b", "üñí"]) {
      expect(unescapePointerToken(escapePointerToken(token))).toBe(token);
    }
  });
});

describe("parsePointer", () => {
  it("returns [] for the root", () => {
    expect(parsePointer("")).toEqual([]);
  });

  it("splits and unescapes tokens", () => {
    expect(parsePointer("/a/b~1c/d~0e")).toEqual(["a", "b/c", "d~e"]);
  });

  it("throws on a pointer not starting with slash", () => {
    expect(() => parsePointer("a/b")).toThrow(/Invalid JSON Pointer/);
  });
});

describe("joinPointer", () => {
  it("appends escaped tokens", () => {
    expect(joinPointer("/a", "b/c", "d~e")).toBe("/a/b~1c/d~0e");
  });

  it("supports an empty base", () => {
    expect(joinPointer("", "x")).toBe("/x");
  });
});

describe("getAt", () => {
  const doc = {
    a: { "b/c": 1, list: [{ v: "zero" }, { v: "one" }] },
    empty: {},
    nil: null,
  };

  it("returns the root for an empty pointer", () => {
    expect(getAt(doc, "")).toBe(doc);
  });

  it("navigates objects and arrays", () => {
    expect(getAt<number>(doc, "/a/b~1c")).toBe(1);
    expect(getAt<string>(doc, "/a/list/1/v")).toBe("one");
  });

  it("returns undefined for missing paths", () => {
    expect(getAt(doc, "/nope")).toBeUndefined();
    expect(getAt(doc, "/a/list/9")).toBeUndefined();
    expect(getAt(doc, "/a/list/-1")).toBeUndefined();
    expect(getAt(doc, "/a/list/x")).toBeUndefined();
    expect(getAt(doc, "/nil/deep")).toBeUndefined();
    expect(getAt(doc, "/empty/x/y")).toBeUndefined();
  });

  it("supports the '-' append token as the array length (undefined when absent)", () => {
    expect(getAt(doc, "/a/list/-")).toBeUndefined();
  });
});
