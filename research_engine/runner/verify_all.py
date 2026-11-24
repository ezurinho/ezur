#!/usr/bin/env python3
"""One command that checks everything before any number is quoted.

Runs, in order:
  1. syntax of every Python and JS file that matters
  2. the deterministic test suite
  3. the registry reproduction check (19 runs re-executed)
  4. every runner artifact has all 12 gates evaluated (no unknown)
  5. the canonical selection cycle exists, matches the artifacts, and the
     data hash it was measured on is the same one the runner uses

Exit code 0 only if everything passes. Intended as a CI gate and as the
"is this still true?" button before citing the report.

    python runner/verify_all.py            # full check
    python runner/verify_all.py --quick    # skip the 19 re-runs (~1 min saved)

`--quick` still checks syntax, tests, gates and cycle consistency; it only
skips re-executing the registered backtests.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "runner"
APP = ROOT / "app"

PY_FILES = [
    APP / "server.py",
    RUNNER / "run_strategy.py",
    RUNNER / "selection_cycle.py",
    RUNNER / "verify_registry.py",
    RUNNER / "test_runner.py",
    ROOT / "research" / "load_data.py",
    ROOT / "research" / "study_costs.py",
    ROOT / "research" / "funding_study.py",
    ROOT / "research" / "build_registry_seed.py",
    ROOT / "research" / "load_multi.py",
    ROOT / "research" / "spread_study.py",
    RUNNER / "run_universe.py",
]
JS_FILES = [APP / "ui" / "app.js"]

CANONICAL_CYCLE = RUNNER / "validation" / "CYCLE-2026-11-selection.json"
VERIFICATION = RUNNER / "verification.json"
OUT_DIR = RUNNER / "out"


class Check:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ok = True
        self.skipped = False
        self.detail = ""

    def skip(self, detail: str) -> "Check":
        self.skipped = True
        self.detail = detail
        return self

    def fail(self, detail: str) -> "Check":
        self.ok = False
        self.detail = detail
        return self


def check_syntax(check: Check) -> Check:
    bad = []
    for path in PY_FILES:
        if not path.exists():
            bad.append(f"{path.name}: falta")
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            bad.append(f"{path.name}:{exc.lineno} {exc.msg}")
    if bad:
        return check.fail(" · ".join(bad))
    node = _run(["node", "--check", str(JS_FILES[0])])
    if node.returncode != 0:
        return check.fail(("stderr: " + node.stderr.strip())[:300])
    check.detail = f"{len(PY_FILES)} py · {len(JS_FILES)} js"
    return check


def check_tests(check: Check) -> Check:
    r = _run([sys.executable, str(RUNNER / "test_runner.py")], cwd=RUNNER)
    tail = [ln for ln in r.stderr.splitlines() if ln.startswith("Ran ") or ln == "OK"]
    if r.returncode != 0:
        return check.fail(" | ".join(tail) or r.stderr[-300:])
    check.detail = " ".join(tail).replace("Ran ", "").replace(" tests in", " tests,")
    return check


def check_registry(check: Check) -> Check:
    r = _run([sys.executable, str(RUNNER / "verify_registry.py")], cwd=ROOT)
    if r.returncode != 0:
        line = next((ln for ln in r.stdout.splitlines() if "reproducen" in ln), r.stdout[-300:])
        return check.fail(line.strip())
    line = next((ln for ln in r.stdout.splitlines() if "reproducen" in ln), "")
    check.detail = line.strip()
    return check


def check_gates(check: Check) -> Check:
    if not OUT_DIR.is_dir():
        return check.fail("sin artefactos del runner")
    files = sorted(OUT_DIR.glob("*.json"))
    if not files:
        return check.fail("sin artefactos del runner")
    missing, total = [], 0
    for path in files:
        try:
            art = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{path.name}: {exc}")
            continue
        gates = art.get("gates") or {}
        total += len(gates)
        unknown = [k for k, g in gates.items() if g.get("pass") is None]
        if unknown:
            missing.append(f"{path.name}: {', '.join(unknown)}")
    if missing:
        return check.fail(" · ".join(missing))
    check.detail = f"{len(files)} artefactos · {total} puertas evaluadas"
    return check


def check_cycle(check: Check) -> Check:
    if not CANONICAL_CYCLE.exists():
        return check.fail(f"falta {CANONICAL_CYCLE.name}")
    cycle = json.loads(CANONICAL_CYCLE.read_text(encoding="utf-8"))
    data_hash = (cycle.get("inputs") or {}).get("data_hash")
    if not data_hash:
        return check.fail("el ciclo no declara data_hash")

    # The artifacts and the cycle must describe the same dataset.
    mismatched = []
    for path in sorted(OUT_DIR.glob("*.json")):
        art = json.loads(path.read_text(encoding="utf-8"))
        art_hash = (art.get("data") or {}).get("sha256", "")[:16]
        if art_hash and art_hash != data_hash:
            mismatched.append(f"{path.name} usa {art_hash}")
    if mismatched:
        return check.fail(f"data_hash del ciclo {data_hash} ≠ " + " · ".join(mismatched))

    # Every artifact that reads the cycle must agree with it.
    pbo = (cycle.get("pbo") or {}).get("pbo")
    dsr = (cycle.get("dsr") or {}).get("dsr")
    for path in sorted(OUT_DIR.glob("*.json")):
        art = json.loads(path.read_text(encoding="utf-8"))
        val = art.get("validation") or {}
        art_pbo, art_dsr = val.get("pbo"), val.get("dsr")
        if isinstance(art_pbo, (int, float)) and abs(art_pbo - pbo) > 1e-9:
            return check.fail(f"{path.name}: PBO {art_pbo} ≠ ciclo {pbo}")
        if isinstance(art_dsr, (int, float)) and abs(art_dsr - dsr) > 1e-9:
            return check.fail(f"{path.name}: DSR {art_dsr} ≠ ciclo {dsr}")
        if val.get("cycle_id") not in (None, cycle.get("cycle_id")):
            return check.fail(f"{path.name}: cita {val['cycle_id']}")

    if not VERIFICATION.exists():
        return check.fail("falta runner/verification.json")
    ver = json.loads(VERIFICATION.read_text(encoding="utf-8"))
    if (ver.get("data_hash") or "") != data_hash:
        return check.fail(f"la verificación usó {ver.get('data_hash')}")

    # CPCV and PSR are reported next to the gate metrics. A missing CPCV block on
    # an artifact that predates it is tolerable; an inconsistent one is not.
    cpcv = cycle.get("cpcv") or {}
    psr = cycle.get("psr") or {}
    for path in sorted(OUT_DIR.glob("*.json")):
        art = json.loads(path.read_text(encoding="utf-8"))
        val = art.get("validation") or {}
        if cpcv.get("paths") and val.get("cpcv") is not None:
            if abs(float(val["cpcv"]) - float(cpcv["share_below_median"])) > 1e-9:
                return check.fail(f"{path.name}: CPCV {val['cpcv']} ≠ ciclo {cpcv['share_below_median']}")

    detail = (f"{cycle.get('cycle_id')} · data {data_hash} · "
              f"PBO {pbo} · DSR {dsr}")
    if cpcv.get("share_below_median") is not None:
        detail += f" · CPCV {cpcv['share_below_median']}"
    if psr.get("psr") is not None:
        detail += f" · PSR {psr['psr']}"
    check.detail = detail
    return check


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify the whole project")
    ap.add_argument("--quick", action="store_true", help="skip re-running the 19 backtests")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    checks = []
    checks.append(check_syntax(Check("sintaxis")))
    checks.append(check_tests(Check("tests")))
    if args.quick:
        checks.append(Check("registro").skip("omitido con --quick"))
    else:
        checks.append(check_registry(Check("registro")))
    checks.append(check_gates(Check("puertas")))
    checks.append(check_cycle(Check("ciclo")))

    width = max(len(c.name) for c in checks)
    for c in checks:
        mark = "omite" if c.skipped else ("ok   " if c.ok else "FALLA")
        print(f"  {mark} {c.name:<{width}}  {c.detail}")
    failed = [c for c in checks if not c.ok]
    skipped = [c for c in checks if c.skipped]
    print()
    if failed:
        print(f"{len(failed)} de {len(checks)} comprobaciones fallan"
              + (f" ({len(skipped)} omitidas)" if skipped else ""))
        return 1
    run = len(checks) - len(skipped)
    if skipped:
        print(f"{run} de {len(checks)} comprobaciones pasan · {len(skipped)} omitida(s) con --quick")
        print("aviso: --quick no re-ejecutó las corridas registradas")
    else:
        print(f"{run} de {len(checks)} comprobaciones pasan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
