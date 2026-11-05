import { describe, expect, it } from "vitest";
import {
  escapePointerToken,
  isPointerDescendant,
  isValidPointer,
  JsonPointerError,
  joinPointer,
  parsePointer,
  pointerMatchesPattern,
  pointersEqual,
  unescapePointerToken,
} from "../src/pointer.js";

describe("pointer parsing", () => {
  it("parses the empty pointer as the whole document", () => {
    expect(parsePointer("")).toEqual([]);
  });

  it("decodes escaped tokens", () => {
    expect(parsePointer("/a~1b/c~0d")).toEqual(["a/b", "c~d"]);
  });

  it("round-trips escape/unescape", () => {
    expect(unescapePointerToken(escapePointerToken("a/b~c"))).toBe("a/b~c");
  });

  it("joins tokens with escaping", () => {
    expect(joinPointer("electrical", "components", 0)).toBe("/electrical/components/0");
    expect(joinPointer()).toBe("");
  });

  it("rejects invalid pointers", () => {
    for (const pointer of ["a", "/a~2b", "/a~"]) {
      expect(isValidPointer(pointer)).toBe(false);
      expect(() => parsePointer(pointer)).toThrow(JsonPointerError);
    }
    expect(isValidPointer("")).toBe(true);
    expect(isValidPointer("/a/b")).toBe(true);
  });

  it("compares concrete pointers after unescaping", () => {
    expect(pointersEqual("/a~1b", "/a~1b")).toBe(true);
    expect(pointersEqual("/a~1b", "/a/b")).toBe(false);
  });

  it("detects descendants", () => {
    expect(isPointerDescendant("/a/b/c", "/a")).toBe(true);
    expect(isPointerDescendant("/a", "/a/b/c")).toBe(false);
    expect(isPointerDescendant("/a", "/a")).toBe(false);
  });
});

describe("pointer pattern matching", () => {
  it("matches exact pointers", () => {
    expect(pointerMatchesPattern("/electrical", "/electrical")).toBe(true);
  });

  it("matches descendants in both directions", () => {
    expect(pointerMatchesPattern("/electrical", "/electrical/components/0/value")).toBe(true);
    expect(pointerMatchesPattern("/electrical/components", "/electrical")).toBe(true);
  });

  it("does not match sibling prefixes without a token boundary", () => {
    expect(pointerMatchesPattern("/foo", "/foobar")).toBe(false);
    expect(pointerMatchesPattern("/foo/bar", "/foo/baz")).toBe(false);
  });

  it("supports a single-segment wildcard", () => {
    expect(pointerMatchesPattern("/a/*/c", "/a/b/c")).toBe(true);
    expect(pointerMatchesPattern("/a/*", "/a/b")).toBe(true);
    expect(pointerMatchesPattern("/a/*", "/a/b/c")).toBe(true);
    expect(pointerMatchesPattern("/a/*/c", "/a/b/d")).toBe(false);
  });

  it("handles escaped tokens", () => {
    expect(pointerMatchesPattern("/a~1b/c", "/a~1b/c/d")).toBe(true);
  });

  it("matches the whole-document pointer against anything", () => {
    expect(pointerMatchesPattern("", "/electrical")).toBe(true);
  });
});
