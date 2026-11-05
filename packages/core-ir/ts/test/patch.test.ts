import { describe, expect, it } from "vitest";
import { PatchBuilder, patch } from "../src/lib/patch.js";

describe("patch builder", () => {
  it("builds every op with escaped relative paths", () => {
    const ops = patch("/sourcing")
      .add("/bom/-", { id: "bom:1" })
      .replace("/build_qty", 5)
      .remove("/budget")
      .move("/a", "/b")
      .copy("/c", "/d")
      .test("/currency", "USD")
      .build();

    expect(ops).toEqual([
      { op: "add", path: "/sourcing/bom/-", value: { id: "bom:1" } },
      { op: "replace", path: "/sourcing/build_qty", value: 5 },
      { op: "remove", path: "/sourcing/budget" },
      { op: "move", from: "/sourcing/a", path: "/sourcing/b" },
      { op: "copy", from: "/sourcing/c", path: "/sourcing/d" },
      { op: "test", path: "/sourcing/currency", value: "USD" },
    ]);
  });

  it("accepts paths with or without a leading slash", () => {
    expect(patch("/electrical").add("nets/-", {}).build()).toEqual([
      { op: "add", path: "/electrical/nets/-", value: {} },
    ]);
  });

  it("preserves pre-escaped pointer tokens", () => {
    expect(patch("/a").replace("b~1c~0d", 1).build()).toEqual([
      { op: "replace", path: "/a/b~1c~0d", value: 1 },
    ]);
  });

  it("works with an empty base", () => {
    expect(patch().add("/top", true).build()).toEqual([{ op: "add", path: "/top", value: true }]);
    expect(patch().replace("", 0).build()).toEqual([{ op: "replace", path: "", value: 0 }]);
  });

  it("returns a copy from build()", () => {
    const builder = patch("/x");
    const first = builder.build();
    builder.add("/y", 1);
    const second = builder.build();
    expect(first).toEqual([]);
    expect(second).toEqual([{ op: "add", path: "/x/y", value: 1 }]);
    expect(second).not.toBe(builder.build());
  });

  it("is chainable and constructible directly", () => {
    const builder = new PatchBuilder("/n");
    expect(builder.add("/a", 1)).toBe(builder);
    expect(builder.build()).toHaveLength(1);
  });
});
