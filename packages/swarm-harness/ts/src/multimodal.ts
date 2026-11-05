/**
 * Multimodal datasheet / 3D-render inspection for swarm agents.
 *
 * The harness speaks a provider-agnostic protocol, so inspection is exposed as
 * two ordinary daemon tools (`harness:inspect_datasheet` and
 * `harness:inspect_render`) that return a {@link ModelAttachment}. Every
 * specialist is granted them in its `permittedTools` allow-list. {@link
 * HarnessInspectionDaemon} intercepts those two tools in front of the real
 * daemon so the rest of the harness, the runner and the transcripts need no
 * special cases.
 *
 * Documents must be rasterised by the producing plugin before inspection; this
 * module intentionally renders only images so behavior is identical across
 * providers.
 */
import type { HarnessDaemon, ModelAttachment, ToolDescriptor } from "./types.js";

/** Hard cap on a single inline attachment (8 MiB). */
export const MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024;

/** Media types the inspection tools accept. */
export const ALLOWED_IMAGE_MIME_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
] as const;
export type AllowedImageMimeType = (typeof ALLOWED_IMAGE_MIME_TYPES)[number];

const HARNESS_PLUGIN = "harness";

/** Tool names exposed by the inspection wrapper. */
export const INSPECTION_TOOL_NAMES = ["inspect_datasheet", "inspect_render"] as const;
export type InspectionToolName = (typeof INSPECTION_TOOL_NAMES)[number];

const ARTIFACT_INPUT_SCHEMA: Record<string, unknown> = {
  type: "object",
  properties: {
    path: {
      type: "string",
      description: "Project-relative path to a PNG/JPEG/WebP/GIF render to inspect.",
    },
    ref: { type: "string", description: "Optional IR artifact/component id for provenance." },
    name: { type: "string", description: "Optional display label for the attachment." },
  },
  required: ["path"],
  additionalProperties: false,
};

/** Descriptors for the two shared inspection tools. */
export const INSPECTION_TOOLS: readonly ToolDescriptor[] = [
  {
    plugin: HARNESS_PLUGIN,
    name: "inspect_datasheet",
    description:
      "Load a rendered datasheet page (image) into the model context. Use it to read " +
      "pinouts, package dimensions, electrical limits and connection diagrams.",
    input_schema: ARTIFACT_INPUT_SCHEMA,
    mutates: false,
  },
  {
    plugin: HARNESS_PLUGIN,
    name: "inspect_render",
    description:
      "Load a board / plate / case / jig render (image) into the model context. Use it " +
      "to check geometry, cutout alignment and component placement.",
    input_schema: ARTIFACT_INPUT_SCHEMA,
    mutates: false,
  },
];

/** `"harness:inspect_datasheet"`-style grant strings for every agent. */
export function inspectionToolGrants(): string[] {
  return INSPECTION_TOOL_NAMES.map((name) => `${HARNESS_PLUGIN}:${name}`);
}

/** Minimal file reader; injected so tests and non-Node hosts can substitute one. */
export interface ArtifactReader {
  readFile(path: string): Promise<Uint8Array>;
}

/** Where an attachment comes from. */
export interface AttachmentSource {
  /** Project-relative or absolute path to the image. */
  path: string;
  /** Optional IR ref recorded on the attachment for provenance. */
  ref?: string;
  /** Optional display name; defaults to the file basename. */
  name?: string;
  /** Optional explicit media type; sniffed from bytes/extension when omitted. */
  mimeType?: string;
}

/** Limits applied to every loaded attachment. */
export interface AttachmentLimits {
  maxBytes?: number;
  allowedMimeTypes?: readonly string[];
}

const EXTENSION_MIME: Readonly<Record<string, AllowedImageMimeType>> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  gif: "image/gif",
};

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] ?? path;
}

function extensionOf(path: string): string {
  const name = basename(path);
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot + 1).toLowerCase();
}

/** Sniff an allowed image media type from magic bytes, falling back to extension. */
export function sniffImageMimeType(
  path: string,
  bytes?: Uint8Array,
): AllowedImageMimeType | undefined {
  if (bytes !== undefined && bytes.length >= 12) {
    if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
      return "image/png";
    }
    if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
    if (bytes[0] === 0x47 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x38) {
      return "image/gif";
    }
    const ascii = Array.from(bytes.slice(0, 12), (b) => String.fromCharCode(b)).join("");
    if (ascii.startsWith("RIFF") && ascii.slice(8, 12) === "WEBP") return "image/webp";
  }
  return EXTENSION_MIME[extensionOf(path)];
}

function isAllowedMime(mimeType: string, allowed: readonly string[]): boolean {
  return allowed.includes(mimeType);
}

/** Build and validate an attachment from already-encoded base64 data. */
export function createImageAttachment(input: {
  data: string;
  mimeType: string;
  name?: string;
  ref?: string;
  allowedMimeTypes?: readonly string[];
}): ModelAttachment {
  const allowed = input.allowedMimeTypes ?? ALLOWED_IMAGE_MIME_TYPES;
  if (input.data.length === 0) {
    throw new Error("attachment data must not be empty");
  }
  if (!isAllowedMime(input.mimeType, allowed)) {
    throw new Error(`unsupported attachment mime type "${input.mimeType}"`);
  }
  const attachment: ModelAttachment = { kind: "image", mimeType: input.mimeType, data: input.data };
  if (input.name !== undefined) attachment.name = input.name;
  if (input.ref !== undefined) attachment.ref = input.ref;
  return attachment;
}

function toBase64(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64");
}

/** Read one image from an {@link ArtifactReader} and turn it into an attachment. */
export async function loadImageAttachment(
  reader: ArtifactReader,
  source: AttachmentSource,
  limits: AttachmentLimits = {},
): Promise<ModelAttachment> {
  const maxBytes = limits.maxBytes ?? MAX_ATTACHMENT_BYTES;
  const allowed = limits.allowedMimeTypes ?? ALLOWED_IMAGE_MIME_TYPES;
  const bytes = await reader.readFile(source.path);
  if (bytes.length === 0) {
    throw new Error(`attachment ${source.path} is empty`);
  }
  if (bytes.length > maxBytes) {
    throw new Error(
      `attachment ${source.path} is ${bytes.length} bytes, exceeding the ${maxBytes} byte limit`,
    );
  }
  const sniffed = source.mimeType ?? sniffImageMimeType(source.path, bytes);
  if (sniffed === undefined) {
    throw new Error(`could not determine an image media type for ${source.path}`);
  }
  return createImageAttachment({
    data: toBase64(bytes),
    mimeType: sniffed,
    name: source.name ?? basename(source.path),
    ...(source.ref !== undefined ? { ref: source.ref } : {}),
    allowedMimeTypes: allowed,
  });
}

/** Convenience inspector bound to a reader and default limits. */
export class MultimodalInspector {
  constructor(
    private readonly reader: ArtifactReader,
    private readonly limits: AttachmentLimits = {},
  ) {}

  inspect(source: AttachmentSource): Promise<ModelAttachment> {
    return loadImageAttachment(this.reader, source, this.limits);
  }
}

/** The inspection wrapper's parsed tool arguments. */
interface InspectionArgs {
  path: string;
  ref?: string;
  name?: string;
}

function parseInspectionArgs(args: unknown): InspectionArgs {
  if (typeof args !== "object" || args === null) {
    throw new Error("inspection tool args must be an object");
  }
  const record = args as Record<string, unknown>;
  if (typeof record.path !== "string" || record.path.length === 0) {
    throw new Error("inspection tool requires a non-empty `path`");
  }
  if (record.ref !== undefined && typeof record.ref !== "string") {
    throw new Error("inspection tool `ref` must be a string");
  }
  if (record.name !== undefined && typeof record.name !== "string") {
    throw new Error("inspection tool `name` must be a string");
  }
  const parsed: InspectionArgs = { path: record.path };
  if (record.ref !== undefined) parsed.ref = record.ref;
  if (record.name !== undefined) parsed.name = record.name;
  return parsed;
}

function isInspectionTool(tool: string): tool is InspectionToolName {
  return (INSPECTION_TOOL_NAMES as readonly string[]).includes(tool);
}

/**
 * {@link HarnessDaemon} decorator that serves the two inspection tools locally
 * and forwards everything else to the wrapped daemon. Place it between {@link
 * DaemonClientAdapter} and `runAgent`.
 */
export class HarnessInspectionDaemon implements HarnessDaemon {
  constructor(
    private readonly base: HarnessDaemon,
    private readonly inspector: MultimodalInspector,
  ) {}

  getIR(path: string) {
    return this.base.getIR(path);
  }

  transact(params: Parameters<HarnessDaemon["transact"]>[0]) {
    return this.base.transact(params);
  }

  lock(node: string, holder: string, ttlS: number, reason?: string) {
    return this.base.lock(node, holder, ttlS, reason);
  }

  unlock(node: string, holder: string) {
    return this.base.unlock(node, holder);
  }

  runDAG(params: { targets?: string[]; force?: boolean } = {}) {
    return this.base.runDAG(params);
  }

  runGates(ids?: readonly string[]) {
    return this.base.runGates(ids);
  }

  async listTools(agent?: Parameters<NonNullable<HarnessDaemon["listTools"]>>[0]) {
    const baseTools = this.base.listTools ? await this.base.listTools(agent) : [];
    return [...baseTools, ...INSPECTION_TOOLS];
  }

  async callTool(plugin: string, tool: string, args: unknown, holder?: string) {
    if (plugin === HARNESS_PLUGIN && isInspectionTool(tool)) {
      const parsed = parseInspectionArgs(args);
      const attachment = await this.inspector.inspect({
        path: parsed.path,
        ...(parsed.ref !== undefined ? { ref: parsed.ref } : {}),
        ...(parsed.name !== undefined ? { name: parsed.name } : {}),
      });
      return { result: attachment };
    }
    return this.base.callTool(plugin, tool, args, holder);
  }
}
