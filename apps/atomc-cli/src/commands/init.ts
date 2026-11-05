/** `atomc init <dir>` — scaffold a project from an example template. */
import { basename, join, resolve } from "node:path";
import { parseSystemIR } from "@atomc/core-ir";
import type { CliDeps, FsLike } from "../deps.js";
import { CliError } from "../errors.js";
import { emit } from "../output.js";

export interface InitOptions {
  force?: boolean;
  name?: string;
  template?: string;
  json?: boolean;
}

const IGNORED_DIRS = new Set([
  "build",
  "node_modules",
  ".venv",
  ".git",
  ".ato",
  "__pycache__",
  ".pytest_cache",
  "coverage",
  "dist",
  ".turbo",
]);

const IGNORED_EXTENSIONS = [".elf", ".bin", ".hex", ".uf2", ".o", ".map", ".a", ".pyc"];

/** Derive a lowercase slug for a fresh project id/name. */
export function slugify(value: string): string {
  const slug = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug === "" ? "project" : slug;
}

async function pathExists(fs: FsLike, path: string): Promise<boolean> {
  try {
    await fs.stat(path);
    return true;
  } catch {
    return false;
  }
}

async function directoryIsEmpty(fs: FsLike, path: string): Promise<boolean> {
  const entries = await fs.readdir(path);
  return entries.length === 0;
}

function shouldSkip(name: string): boolean {
  if (IGNORED_DIRS.has(name)) return true;
  const lower = name.toLowerCase();
  return IGNORED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

async function copyTree(fs: FsLike, source: string, dest: string): Promise<string[]> {
  const copied: string[] = [];
  await fs.mkdir(dest, { recursive: true });
  for (const entry of await fs.readdir(source)) {
    if (shouldSkip(entry.name)) continue;
    const src = join(source, entry.name);
    const out = join(dest, entry.name);
    if (entry.isDirectory()) {
      copied.push(...(await copyTree(fs, src, out)));
    } else {
      await fs.copyFile(src, out);
      copied.push(out);
    }
  }
  return copied;
}

/** Run `atomc init`; returns the process exit code. */
export async function initCommand(
  deps: CliDeps,
  dir: string,
  options: InitOptions = {},
): Promise<number> {
  if (!dir || dir.trim() === "") {
    throw new CliError("init requires a target directory", 1);
  }
  const target = resolve(deps.cwd, dir);
  const name = options.name ?? basename(target);
  const slug = slugify(options.name ?? basename(target));
  const template = options.template ?? "atomc-pad";

  if (await pathExists(deps.fs, target)) {
    if (!options.force && !(await directoryIsEmpty(deps.fs, target))) {
      throw new CliError(`refusing to overwrite non-empty directory ${target} (use --force)`, 1, {
        target,
        force: "required",
      });
    }
    if (options.force) await deps.fs.rm(target, { recursive: true, force: true });
  }

  const repoRoot = await deps.findRepoRoot();
  const templateDir = join(repoRoot, "examples", template);
  if (!(await pathExists(deps.fs, templateDir))) {
    throw new CliError(
      `template "${template}" not found at ${templateDir} (try --template atomc-keeb)`,
      1,
      { template, templateDir },
    );
  }

  const copied = await copyTree(deps.fs, templateDir, target);

  const irPath = join(target, "system_ir.json");
  if (await pathExists(deps.fs, irPath)) {
    const raw = await deps.fs.readFile(irPath, "utf8");
    const ir = parseSystemIR(JSON.parse(raw));
    const now = deps.now().toISOString();
    ir.meta = { ...ir.meta, name, project_id: `proj:${slug}`, modified_at: now };
    await deps.fs.writeFile(irPath, `${JSON.stringify(ir, null, 2)}\n`);
  }

  const configPath = join(target, "atomc.config.ts");
  if (await pathExists(deps.fs, configPath)) {
    const config = await deps.fs.readFile(configPath, "utf8");
    await deps.fs.writeFile(configPath, config.replace(/project:\s*"[^"]*"/, `project: "${name}"`));
  }

  const payload = { created: true, target, name, template, files: copied.length };
  emit(deps, options.json === true, payload, [
    `created ${name} in ${target} from template "${template}" (${copied.length} files)`,
    "next steps:",
    `  cd ${dir}`,
    "  atomc doctor",
    "  atomc daemon start",
  ]);
  return 0;
}
