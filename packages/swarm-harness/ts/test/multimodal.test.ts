import { describe, expect, it } from "vitest";
import {
  ALLOWED_IMAGE_MIME_TYPES,
  createImageAttachment,
  HarnessInspectionDaemon,
  INSPECTION_TOOLS,
  inspectionToolGrants,
  loadImageAttachment,
  MAX_ATTACHMENT_BYTES,
  MultimodalInspector,
  sniffImageMimeType,
} from "../src/index.js";
import { FakeDaemon } from "./fakes.js";

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0, 0, 0, 0, 0]);
const GIF = new Uint8Array([0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0, 0, 0, 0, 0, 0]);
const WEBP = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x45, 0x42, 0x50]);

function readerFor(files: Record<string, Uint8Array>): {
  readFile: (path: string) => Promise<Uint8Array>;
} {
  return {
    readFile: async (path: string) => {
      const bytes = files[path];
      if (bytes === undefined) throw new Error(`missing fixture ${path}`);
      return bytes;
    },
  };
}

describe("sniffImageMimeType", () => {
  it("detects magic bytes", () => {
    expect(sniffImageMimeType("x.bin", PNG)).toBe("image/png");
    expect(sniffImageMimeType("x.bin", JPEG)).toBe("image/jpeg");
    expect(sniffImageMimeType("x.bin", GIF)).toBe("image/gif");
    expect(sniffImageMimeType("x.bin", WEBP)).toBe("image/webp");
  });

  it("falls back to the extension", () => {
    expect(sniffImageMimeType("render.PNG")).toBe("image/png");
    expect(sniffImageMimeType("render.jpeg")).toBe("image/jpeg");
    expect(sniffImageMimeType("render.webp")).toBe("image/webp");
    expect(sniffImageMimeType("render.gif")).toBe("image/gif");
  });

  it("returns undefined for unknown inputs", () => {
    expect(sniffImageMimeType("notes.txt")).toBeUndefined();
    expect(sniffImageMimeType("notes.txt", new Uint8Array([1, 2, 3]))).toBeUndefined();
  });
});

describe("createImageAttachment", () => {
  it("builds a valid attachment", () => {
    expect(createImageAttachment({ data: "AAAA", mimeType: "image/png" })).toEqual({
      kind: "image",
      mimeType: "image/png",
      data: "AAAA",
    });
  });

  it("carries optional name and ref", () => {
    expect(
      createImageAttachment({
        data: "AAAA",
        mimeType: "image/png",
        name: "page-1",
        ref: "art:datasheet",
      }),
    ).toEqual({
      kind: "image",
      mimeType: "image/png",
      data: "AAAA",
      name: "page-1",
      ref: "art:datasheet",
    });
  });

  it("rejects empty data and unsupported types", () => {
    expect(() => createImageAttachment({ data: "", mimeType: "image/png" })).toThrow(/empty/);
    expect(() => createImageAttachment({ data: "AAAA", mimeType: "application/pdf" })).toThrow(
      /unsupported/,
    );
  });
});

describe("loadImageAttachment", () => {
  it("reads and encodes an image with a sniffed type", async () => {
    const attachment = await loadImageAttachment(readerFor({ "renders/plate.png": PNG }), {
      path: "renders/plate.png",
    });
    expect(attachment.mimeType).toBe("image/png");
    expect(attachment.name).toBe("plate.png");
    expect(attachment.data).toBe(Buffer.from(PNG).toString("base64"));
  });

  it("honors an explicit type and display name", async () => {
    const attachment = await loadImageAttachment(
      readerFor({ "p.dat": JPEG }),
      { path: "p.dat", mimeType: "image/jpeg", name: "datasheet page" },
      {},
    );
    expect(attachment).toMatchObject({ mimeType: "image/jpeg", name: "datasheet page" });
  });

  it("rejects empty, oversized and undetectable files", async () => {
    await expect(
      loadImageAttachment(readerFor({ "e.png": new Uint8Array([]) }), { path: "e.png" }),
    ).rejects.toThrow(/empty/);
    await expect(
      loadImageAttachment(
        readerFor({ "big.png": new Uint8Array(64).fill(1) }),
        { path: "big.png" },
        { maxBytes: 8 },
      ),
    ).rejects.toThrow(/exceeding/);
    await expect(
      loadImageAttachment(
        readerFor({ "x.bin": new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]) }),
        { path: "x.bin" },
      ),
    ).rejects.toThrow(/could not determine/);
  });

  it("enforces a caller-supplied mime allow-list", async () => {
    await expect(
      loadImageAttachment(
        readerFor({ "a.png": PNG }),
        { path: "a.png" },
        {
          allowedMimeTypes: ["image/webp"],
        },
      ),
    ).rejects.toThrow(/unsupported/);
  });
});

describe("MultimodalInspector", () => {
  it("inspects through the bound reader", async () => {
    const inspector = new MultimodalInspector(readerFor({ "r.png": PNG }));
    const attachment = await inspector.inspect({ path: "r.png", ref: "art:x" });
    expect(attachment.ref).toBe("art:x");
  });
});

describe("inspection tool contracts", () => {
  it("exposes exactly two read-only tools", () => {
    expect(INSPECTION_TOOLS.map((t) => t.name)).toEqual(["inspect_datasheet", "inspect_render"]);
    for (const tool of INSPECTION_TOOLS) {
      expect(tool.plugin).toBe("harness");
      expect(tool.mutates).toBe(false);
    }
    expect(inspectionToolGrants()).toEqual(["harness:inspect_datasheet", "harness:inspect_render"]);
    expect(ALLOWED_IMAGE_MIME_TYPES).toHaveLength(4);
    expect(MAX_ATTACHMENT_BYTES).toBe(8 * 1024 * 1024);
  });
});

describe("HarnessInspectionDaemon", () => {
  function build(): { base: FakeDaemon; daemon: HarnessInspectionDaemon } {
    const base = new FakeDaemon();
    base.tools = [
      {
        plugin: "atopile",
        name: "compile",
        description: "compile",
        input_schema: { type: "object" },
        mutates: true,
      },
    ];
    const inspector = new MultimodalInspector(readerFor({ "render.png": PNG }));
    return { base, daemon: new HarnessInspectionDaemon(base, inspector) };
  }

  it("merges the inspection tools after the daemon tools", async () => {
    const { daemon } = build();
    const tools = await daemon.listTools("ee-agent");
    expect(tools.map((t) => t.name)).toEqual(["compile", "inspect_datasheet", "inspect_render"]);
  });

  it("serves the inspection tools locally", async () => {
    const { base, daemon } = build();
    const result = (await daemon.callTool("harness", "inspect_render", {
      path: "render.png",
      ref: "art:render",
    })) as { result: { mimeType: string; ref?: string } };
    expect(result.result.mimeType).toBe("image/png");
    expect(result.result.ref).toBe("art:render");
    expect(base.toolCalls).toBe(0);
  });

  it("delegates every other tool to the wrapped daemon", async () => {
    const { base, daemon } = build();
    await daemon.callTool("atopile", "compile", {});
    expect(base.toolCalls).toBe(1);
  });

  it("rejects malformed inspection arguments", async () => {
    const { daemon } = build();
    await expect(daemon.callTool("harness", "inspect_render", {})).rejects.toThrow(/path/);
    await expect(daemon.callTool("harness", "inspect_render", null)).rejects.toThrow(
      /must be an object/,
    );
    await expect(
      daemon.callTool("harness", "inspect_render", { path: "x.png", ref: 3 }),
    ).rejects.toThrow(/ref/);
  });

  it("delegates the remaining daemon surface transparently", async () => {
    const { base, daemon } = build();
    await daemon.getIR("/electrical");
    await daemon.transact({ path: "/electrical", base_rev: 1, ops: [] });
    await daemon.lock("/electrical", "h", 10);
    await daemon.unlock("/electrical", "h");
    await daemon.runDAG({ targets: ["x"] });
    await daemon.runGates(["erc.no_unconnected"]);
    expect(base.events).toContain("getIR:/electrical");
    expect(base.transactCalls).toBe(1);
    expect(base.lockCalls).toBe(1);
    expect(base.unlockCalls).toBe(1);
    expect(base.runDagCalls).toBe(1);
    expect(base.runGateCalls).toBe(1);
  });
});
