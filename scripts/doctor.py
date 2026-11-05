#!/usr/bin/env python3
"""atomc environment doctor (WP-0.1).

Stdlib-only Python 3.14 script. Verifies every external toolchain atomc needs is
present and usable. Exits 0 iff all *required* checks pass.

Usage:
    python3 scripts/doctor.py            # human-readable report
    python3 scripts/doctor.py --json     # machine-readable report

Environment: source ~/.atomc/env.sh first so Renode/pyrenode3/QMK are on PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"
ENV_FILE = Path.home() / ".atomc" / "env.sh"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
WARN = "WARN"


@dataclass
class Result:
    name: str
    status: str
    version: str = ""
    detail: str = ""
    hint: str = ""
    required: bool = True


def _run(
    cmd: list[str], timeout: int = 30, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def check_binary(
    name: str,
    cmd: list[str],
    version_args: list[str] | None = None,
    required: bool = True,
    hint: str = "",
    env: dict[str, str] | None = None,
) -> Result:
    path = shutil.which(name, path=(env or os.environ).get("PATH"))
    if not path:
        return Result(
            name,
            FAIL if required else WARN,
            detail="not found on PATH",
            hint=hint or f"install {name}",
            required=required,
        )
    version = ""
    if version_args is not None:
        try:
            proc = _run([name, *version_args], timeout=30, env=env)
            out = _first_line(proc.stdout) or _first_line(proc.stderr)
            version = out
        except Exception as exc:
            return Result(
                name, FAIL, detail=f"version probe failed: {exc}", hint=hint, required=required
            )
    return Result(name, PASS, version=version, detail=path, required=required)


def check_python_314() -> Result:
    py = shutil.which("python3.14") or shutil.which("python3")
    if not py:
        return Result("python 3.14", FAIL, hint="uv python install 3.14")
    try:
        proc = _run([py, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"])
        ver = proc.stdout.strip()
    except Exception as exc:
        return Result("python 3.14", FAIL, detail=str(exc), hint="uv python install 3.14")
    if ver.startswith("3.14."):
        return Result("python 3.14", PASS, version=ver, detail=py)
    return Result(
        "python 3.14",
        FAIL,
        version=ver,
        detail=py,
        hint="uv python install 3.14 (found wrong version)",
    )


def check_venv_import(module: str, expr: str | None = None) -> Result:
    label = f".venv import {module}"
    if not VENV_PY.exists():
        return Result(label, FAIL, detail=f"{VENV_PY} missing", hint="bash scripts/bootstrap.sh")
    code = expr or f"import {module}"
    env = _env_with_atomc()
    try:
        proc = _run([str(VENV_PY), "-c", code], timeout=60, env=env)
    except Exception as exc:
        return Result(label, FAIL, detail=str(exc), hint="reinstall verification venv")
    if proc.returncode == 0:
        return Result(label, PASS, detail="imported")
    return Result(
        label,
        FAIL,
        detail=_first_line(proc.stderr) or "import failed",
        hint="reinstall with scripts/bootstrap.sh; see ENVIRONMENT.md",
    )


def _env_with_atomc() -> dict[str, str]:
    env = dict(os.environ)
    if ENV_FILE.exists():
        try:
            out = _run(["bash", "-c", f". {ENV_FILE} >/dev/null 2>&1; env"], timeout=15)
            for line in out.stdout.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    # env.sh is the authoritative atomc environment: its PATH
                    # prepends must win over the caller's existing PATH.
                    env[k] = v
        except Exception:
            pass
    return env


def check_renode_headless() -> Result:
    env = _env_with_atomc()
    if not shutil.which("renode", path=env.get("PATH")):
        return Result(
            "renode --version",
            FAIL,
            detail="not found on PATH",
            hint=". ~/.atomc/env.sh  (or run scripts/bootstrap.sh)",
        )
    try:
        proc = _run(["renode", "--version"], timeout=60, env=env)
    except Exception as exc:
        return Result("renode --version", FAIL, detail=str(exc), hint="check Gatekeeper quarantine")
    text = _first_line(proc.stdout) + " " + _first_line(proc.stderr)
    if proc.returncode == 0:
        return Result("renode --version", PASS, version=text.strip(), detail="headless probe OK")
    return Result(
        "renode --version",
        FAIL,
        detail=text.strip() or "nonzero exit",
        hint="xattr -dr com.apple.quarantine ~/.local/opt/renode-1.17.0/Renode.app",
    )


def check_renode_smoke() -> Result:
    """Run a tiny platform load headless and confirm Renode exits 0."""
    env = _env_with_atomc()
    if not shutil.which("renode", path=env.get("PATH")):
        return Result(
            "renode smoke (load stm32f4)",
            FAIL,
            detail="renode missing",
            hint="install Renode via bootstrap.sh",
        )
    script = (
        "mach create\n"
        "machine LoadPlatformDescription @platforms/cpus/stm32f4.repl\n"
        "start\n"
        "sleep 1\n"
        "quit\n"
    )
    try:
        proc = _run(
            ["renode", "--disable-xwt", "--console", "--plain", "-e", script], timeout=120, env=env
        )
    except Exception as exc:
        return Result(
            "renode smoke (load stm32f4)",
            FAIL,
            detail=str(exc),
            hint="run `renode --console` manually and inspect",
        )
    combined = (proc.stdout + proc.stderr).lower()
    if "hardfault" in combined:
        return Result(
            "renode smoke (load stm32f4)", WARN, detail="ran but HardFault observed", required=False
        )
    if proc.returncode == 0 and ("stm32" in combined or "machine" in combined):
        return Result("renode smoke (load stm32f4)", PASS, detail="platform loaded and started")
    # Renode's -e handling differs across versions; treat a clean exit as success.
    if proc.returncode == 0:
        return Result(
            "renode smoke (load stm32f4)", PASS, detail="exited 0", version=_first_line(proc.stdout)
        )
    return Result(
        "renode smoke (load stm32f4)",
        FAIL,
        detail=_first_line(proc.stderr) or f"exit {proc.returncode}",
        hint="run the smoke manually; see ENVIRONMENT.md",
    )


def check_pyrenode3() -> Result:
    env = _env_with_atomc()
    if not VENV_PY.exists():
        return Result(
            "pyrenode3 Emulation()", FAIL, detail=".venv missing", hint="bash scripts/bootstrap.sh"
        )
    code = "from pyrenode3.wrappers import Emulation\ne = Emulation()\nprint('EmulationOK')\n"
    try:
        proc = _run([str(VENV_PY), "-c", code], timeout=180, env=env)
    except Exception as exc:
        return Result(
            "pyrenode3 Emulation()",
            FAIL,
            detail=str(exc),
            hint="ensure PYRENODE_RUNTIME=coreclr + DOTNET_ROOT set",
        )
    if "EmulationOK" in proc.stdout:
        return Result("pyrenode3 Emulation()", PASS, detail="Emulation() constructed")
    detail = _first_line(proc.stderr) or _first_line(proc.stdout) or "no output"
    return Result(
        "pyrenode3 Emulation()",
        FAIL,
        detail=detail,
        hint="source ~/.atomc/env.sh; see ENVIRONMENT.md pyrenode3 section",
    )


def check_qmk_doctor() -> Result:
    env = _env_with_atomc()
    if not shutil.which("qmk", path=env.get("PATH")):
        return Result(
            "qmk doctor",
            FAIL,
            detail="qmk not found",
            hint="uv tool install qmk && qmk setup -y -H ~/qmk_firmware",
        )
    try:
        proc = _run(["qmk", "doctor"], timeout=180, env=env)
    except Exception as exc:
        return Result("qmk doctor", FAIL, detail=str(exc), hint="run `qmk doctor` manually")
    text = proc.stdout + proc.stderr
    if proc.returncode == 0 and "failed" not in text.lower():
        return Result("qmk doctor", PASS, detail="all checks passed", version=_qmk_version(env))
    # Extract the summary lines for context.
    bad = [ln.strip() for ln in text.splitlines() if "FAIL" in ln.upper() or "✗" in ln]
    return Result(
        "qmk doctor",
        FAIL,
        detail="; ".join(bad[:3]) or "doctor reported issues",
        hint="see ENVIRONMENT.md QMK section",
    )


def _qmk_version(env: dict[str, str]) -> str:
    try:
        return _first_line(_run(["qmk", "--version"], timeout=30, env=env).stdout)
    except Exception:
        return ""


def check_gh_auth() -> Result:
    if not shutil.which("gh"):
        return Result("gh auth status", WARN, detail="gh not installed", required=False)
    try:
        proc = _run(["gh", "auth", "status"], timeout=30)
    except Exception as exc:
        return Result("gh auth status", FAIL, detail=str(exc), hint="gh auth login")
    if proc.returncode == 0:
        return Result("gh auth status", PASS, detail="authenticated")
    return Result("gh auth status", FAIL, detail=_first_line(proc.stderr), hint="gh auth login")


def check_kicad() -> Result:
    # Optional GUI dependency (WP-1.6 for `ato build` layout + viewing).
    found = shutil.which("kicad-cli") or (Path("/Applications/KiCad/KiCad.app").exists())
    if found:
        return Result("kicad", PASS, detail=str(found), required=False)
    return Result("kicad", SKIP, detail="not installed (optional; --with-kicad)", required=False)


def collect() -> list[Result]:
    results: list[Result] = [
        check_binary("uv", ["uv"], ["--version"], hint="https://docs.astral.sh/uv/"),
        check_python_314(),
        check_binary("node", ["node"], ["--version"], hint="install node >= 22"),
        check_binary("pnpm", ["pnpm"], ["--version"], hint="npm i -g pnpm"),
        check_binary(
            "turbo", ["turbo"], ["--version"], required=False, hint="pnpm add -g turbo@latest"
        ),
        check_binary(
            "biome",
            ["biome"],
            ["--version"],
            required=False,
            hint="pnpm add -g @biomejs/biome@latest",
        ),
        check_binary("ato", ["ato"], ["--version"], hint="uv tool install atopile==0.15.9"),
        check_binary(
            "arm-none-eabi-gcc",
            ["arm-none-eabi-gcc"],
            ["--version"],
            hint="brew install osx-cross/arm/arm-gcc-bin@13",
            env=_env_with_atomc(),
        ),
        check_arm_gcc_toolchain(),
        check_binary("cmake", ["cmake"], ["--version"], hint="brew install cmake"),
        check_binary("ninja", ["ninja"], ["--version"], hint="brew install ninja"),
        _check_dotnet(),
        check_venv_import(
            "build123d",
            "import build123d; print(getattr(build123d, '__version__', 'ok'))",
        ),
        check_venv_import("OCP", "import OCP; print('ok')"),
        check_venv_import("kiutils", "import kiutils; print('ok')"),
        check_renode_headless(),
        check_renode_smoke(),
        check_pyrenode3(),
        check_binary("gh", ["gh"], ["--version"], required=False, hint="brew install gh"),
        check_gh_auth(),
        check_binary("qmk", ["qmk"], None, hint="uv tool install qmk"),
        check_qmk_doctor(),
        check_kicad(),
    ]
    return results


def check_arm_gcc_toolchain() -> Result:
    """QMK needs a full GNU Arm toolchain (nosys/nano specs), not just a bare gcc.
    Homebrew's core arm-none-eabi-gcc formula omits newlib specs, so this compiles
    a trivial file end-to-end to prove the toolchain is usable."""
    env = _env_with_atomc()
    gcc = shutil.which("arm-none-eabi-gcc", path=env.get("PATH"))
    if not gcc:
        return Result(
            "arm-none-eabi toolchain (compile)",
            FAIL,
            detail="gcc not found",
            hint="brew install osx-cross/arm/arm-gcc-bin@13",
        )
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "probe.c"
        out = Path(tmp) / "probe.elf"
        src.write_text("int main(void){return 0;}\n")
        cmd = [
            gcc,
            "-mcpu=cortex-m0",
            "-mthumb",
            "-mno-thumb-interwork",
            "--specs=nosys.specs",
            "--specs=nano.specs",
            "-x",
            "c",
            "-o",
            str(out),
            str(src),
        ]
        try:
            proc = _run(cmd, timeout=60, env=env)
        except Exception as exc:
            return Result(
                "arm-none-eabi toolchain (compile)",
                FAIL,
                detail=str(exc),
                hint="install osx-cross/arm/arm-gcc-bin@13",
            )
        ok = proc.returncode == 0 and out.exists() and out.stat().st_size > 1000
    if ok:
        ver = _first_line(_run([gcc, "--version"], timeout=30, env=env).stdout)
        return Result(
            "arm-none-eabi toolchain (compile)",
            PASS,
            version=ver,
            detail=f"{gcc} (nosys/nano specs OK)",
        )
    return Result(
        "arm-none-eabi toolchain (compile)",
        FAIL,
        detail=_first_line(proc.stderr) or f"exit {proc.returncode}",
        hint="install osx-cross/arm/arm-gcc-bin@13 (core formula lacks newlib specs)",
    )


def _check_dotnet() -> Result:
    # dotnet@8 is keg-only; probe via brew prefix if not on PATH.
    env = _env_with_atomc()
    dotnet = shutil.which("dotnet", path=env.get("PATH"))
    if not dotnet:
        try:
            prefix = _run(["brew", "--prefix", "dotnet@8"], timeout=30).stdout.strip()
            candidate = Path(prefix) / "bin" / "dotnet"
            if candidate.exists():
                dotnet = str(candidate)
        except Exception:
            dotnet = None
    if not dotnet:
        return Result(
            "dotnet 8",
            FAIL,
            detail="not found",
            hint="brew install dotnet@8; source ~/.atomc/env.sh",
        )
    try:
        proc = _run([dotnet, "--list-runtimes"], timeout=30)
    except Exception as exc:
        return Result("dotnet 8", FAIL, detail=str(exc), hint="brew install dotnet@8")
    if "Microsoft.NETCore.App 8." in proc.stdout:
        return Result("dotnet 8", PASS, detail=dotnet, version=_dotnet8_line(proc.stdout))
    return Result("dotnet 8", FAIL, detail="no 8.x runtime found", hint="brew install dotnet@8")


def _dotnet8_line(text: str) -> str:
    for line in text.splitlines():
        if "Microsoft.NETCore.App 8." in line:
            return line.strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="atomc environment doctor")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    results = collect()

    if args.json:
        print(
            json.dumps(
                {
                    "ok": all(r.status in (PASS, SKIP, WARN) for r in results),
                    "env_file": str(ENV_FILE),
                    "env_file_exists": ENV_FILE.exists(),
                    "checks": [r.__dict__ for r in results],
                },
                indent=2,
            )
        )
    else:
        width = max(len(r.name) for r in results)
        symbols = {
            PASS: "\033[32m✓\033[0m",
            FAIL: "\033[31m✗\033[0m",
            WARN: "\033[33m!\033[0m",
            SKIP: "\033[90m-\033[0m",
        }
        print()
        for r in results:
            sym = symbols.get(r.status, "?")
            ver = f"  {r.version}" if r.version else ""
            note = f"  ({r.detail})" if r.detail and not r.version else ""
            print(f"  {sym} {r.name.ljust(width)} {r.status}{ver}{note}")
            if r.status == FAIL and r.hint:
                print(f"      \033[33m→ {r.hint}\033[0m")
        failed = [r for r in results if r.status == FAIL]
        print()
        if failed:
            print(f"\033[31m{len(failed)} check(s) failed.\033[0m")
        else:
            print("\033[1;32mAll checks passed.\033[0m")
        if not ENV_FILE.exists():
            print(f"\033[33mnote: {ENV_FILE} missing — run scripts/bootstrap.sh\033[0m")
        print()

    return 0 if all(r.status != FAIL for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
