import type { JsonPatchOp } from "@atomc/core-ir";
import { describe, expect, it } from "vitest";
import { PatchPathError, toRelativePatch } from "../src/index.js";

describe("toRelativePatch", () => {
  it("strips the base prefix from absolute pointers emitted by patch(base)", () => {
    const ops: JsonPatchOp[] = [
      { op: "replace", path: "/electrical/assertions/0/status", value: "fail" },
      { op: "add", path: "/electrical/assertions/-", value: { id: "assert:x" } },
      { op: "remove", path: "/electrical/nets/2" },
    ];
    expect(toRelativePatch("/electrical", ops)).toEqual([
      { op: "replace", path: "/assertions/0/status", value: "fail" },
      { op: "add", path: "/assertions/-", value: { id: "assert:x" } },
      { op: "remove", path: "/nets/2" },
    ]);
  });

  it("converts the `from` pointer of move/copy ops", () => {
    const ops: JsonPatchOp[] = [
      { op: "move", from: "/electrical/components/0", path: "/electrical/components/1" },
      { op: "copy", from: "/electrical/nets/0", path: "/electrical/nets/-" },
    ];
    expect(toRelativePatch("/electrical", ops)).toEqual([
      { op: "move", from: "/components/0", path: "/components/1" },
      { op: "copy", from: "/nets/0", path: "/nets/-" },
    ]);
  });

  it("preserves escaped ~0 and ~1 tokens while stripping", () => {
    const ops: JsonPatchOp[] = [{ op: "replace", path: "/ext/my~1plugin/key~0x", value: 1 }];
    expect(toRelativePatch("/ext/my~1plugin", ops)).toEqual([
      { op: "replace", path: "/key~0x", value: 1 },
    ]);
  });

  it("treats root base as identity", () => {
    const ops: JsonPatchOp[] = [{ op: "replace", path: "/electrical/nets/0", value: 1 }];
    expect(toRelativePatch("", ops)).toEqual(ops);
    expect(toRelativePatch("/", ops)).toEqual(ops);
  });

  it("keeps already-relative pointers unchanged", () => {
    const ops: JsonPatchOp[] = [
      { op: "replace", path: "/assertions/0/status", value: "pass" },
      { op: "remove", path: "" },
      { op: "replace", path: "/", value: {} },
    ];
    expect(toRelativePatch("/electrical", ops)).toEqual(ops);
  });

  it("maps a pointer equal to the base to the subtree root", () => {
    const ops: JsonPatchOp[] = [{ op: "replace", path: "/electrical", value: {} }];
    expect(toRelativePatch("/electrical", ops)).toEqual([{ op: "replace", path: "", value: {} }]);
  });

  it("normalizes a trailing slash on the base", () => {
    const ops: JsonPatchOp[] = [{ op: "replace", path: "/electrical/nets/0", value: 1 }];
    expect(toRelativePatch("/electrical/", ops)).toEqual([
      { op: "replace", path: "/nets/0", value: 1 },
    ]);
  });

  it("rejects absolute pointers targeting a different top-level node", () => {
    const ops: JsonPatchOp[] = [{ op: "replace", path: "/keyboard/keys/0/x_u", value: 1 }];
    expect(() => toRelativePatch("/electrical", ops)).toThrow(PatchPathError);
  });

  it("rejects absolute pointers targeting a sibling under the same top-level node", () => {
    const ops: JsonPatchOp[] = [{ op: "add", path: "/electrical/nets/-", value: {} }];
    expect(() => toRelativePatch("/electrical/components", ops)).toThrow(PatchPathError);
  });

  it("rejects a non-pointer base", () => {
    expect(() => toRelativePatch("electrical", [])).toThrow(PatchPathError);
  });

  it("rejects a non-pointer op path", () => {
    const ops = [{ op: "replace", path: "assertions/0", value: 1 }] as unknown as JsonPatchOp[];
    expect(() => toRelativePatch("/electrical", ops)).toThrow(PatchPathError);
  });

  it("does not strip a base that is only a string prefix of a token", () => {
    const ops: JsonPatchOp[] = [{ op: "replace", path: "/electrical_extra", value: 1 }];
    // `/electrical_extra` is not a top-level node, so it passes through as relative.
    expect(toRelativePatch("/electrical", ops)).toEqual(ops);
  });
});
