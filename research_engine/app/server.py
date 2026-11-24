"""BTC Quant Research Registry — local registry + UI (stdlib only).

Append-only research log: strategies, cycles, runs, verdicts, gates and events
in SQLite, served over a small JSON API plus a static dashboard.

    python app/server.py --port 8787

The database is created on first boot from research/cache/registry_seed.json
(real runs produced by research/build_registry_seed.py). After that, the DB is
the source of truth; runs are never overwritten, only appended with a new id.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
UI = Path(__file__).resolve().parent / "ui"
SEED = ROOT / "research" / "cache" / "registry_seed.json"
RUNNER_OUT = ROOT / "runner" / "out"
RUNNER_SPECS = ROOT / "runner" / "specs"
RUNNER_VALIDATION = ROOT / "runner" / "validation"
DB_DEFAULT = Path(__file__).resolve().parent / "registry.db"
EVENT_TYPES = {"run", "audit", "note", "cycle"}
WATCH = [
    "INFORME_AUDITORIA.md",
    "PROMPT_V4.md",
    "README.md",
    "resumen.html",
    "research/load_data.py",
    "research/study_costs.py",
    "research/funding_study.py",
    "research/export_charts.py",
    "research/build_registry_seed.py",
    "research/cache/study_results.json",
    "research/cache/funding_results.json",
    "research/cache/registry_seed.json",
    "runner/run_strategy.py",
    "runner/selection_cycle.py",
    "runner/verify_registry.py",
    "runner/verify_all.py",
    "runner/verification.json",
    "runner/strategy_spec.schema.json",
    "runner/validation/CYCLE-2026-11.json",
    "runner/validation/CYCLE-2026-11-selection.json",
    "runner/validation/sensitivity/CYCLE-2026-11-full.json",
    "app/server.py",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS strategies (
  id TEXT PRIMARY KEY, name TEXT, family TEXT, timeframe TEXT,
  hypothesis TEXT, rules TEXT, risks TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS cycles (
  id TEXT PRIMARY KEY, name TEXT, created_at TEXT, pbo REAL, dsr REAL,
  dsr_threshold REAL, sr_best REAL, sr0 REAL, minbtl_years REAL,
  coverage_years REAL, trials INTEGER, wfa_min_trades INTEGER,
  wfa_folds INTEGER, wfa_total_trades INTEGER, verdict TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, strategy_id TEXT, cycle_id TEXT, version TEXT,
  created_at TEXT, label TEXT, params TEXT, costs TEXT, metrics TEXT,
  gates TEXT, verdict TEXT, artifacts TEXT, equity TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, type TEXT,
  run_id TEXT, message TEXT);
"""

VERDICTS = ("APPROVED", "INCONCLUSIVE", "REJECTED")
REQUIRED_METRICS = ("n", "pf_net", "pf_stress", "pf_ci95", "t_stat", "mdd")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def json_field(row: sqlite3.Row, key: str, default):
    raw = row[key]
    return json.loads(raw) if raw else default


def seed_db(con: sqlite3.Connection) -> None:
    if con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]:
        return
    if not SEED.exists():
        print(f"[seed] {SEED} not found: starting empty")
        return
    data = json.loads(SEED.read_text(encoding="utf-8"))
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("project", json.dumps({**data["project"], "dataset": data["dataset"],
                                        "budget": data.get("budget", {})})))
    for s in data["strategies"]:
        con.execute("INSERT OR IGNORE INTO strategies VALUES (?,?,?,?,?,?,?,?)",
                    (s["id"], s["name"], s["family"], s["timeframe"],
                     s["hypothesis"], s["rules"], s["risks"], s["created_at"]))
    for c in data["cycles"]:
        con.execute("INSERT OR IGNORE INTO cycles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (c["id"], c["name"], c["created_at"], c["pbo"], c["dsr"],
                     c.get("dsr_threshold"), c.get("sr_best"), c.get("sr0"),
                     c.get("minbtl_years"), c.get("coverage_years"), c.get("trials"),
                     c.get("wfa_min_trades"), c.get("wfa_folds"), c.get("wfa_total_trades"),
                     c["verdict"], c.get("notes", "")))
    for r in data["runs"]:
        con.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r["id"], r["strategy_id"], r["cycle_id"], r["version"], r["created_at"],
                     r["label"], json.dumps(r["params"]), json.dumps(r["costs"]),
                     json.dumps(r["metrics"]), json.dumps(r["gates"]), r["verdict"],
                     json.dumps(r["artifacts"]), json.dumps(r["equity"]), r.get("notes", "")))
    for e in data["events"]:
        con.execute("INSERT INTO events(ts, actor, type, run_id, message) VALUES (?,?,?,?,?)",
                    (e["ts"], e["actor"], e["type"], e.get("run_id"), e["message"]))
    con.commit()
    print(f"[seed] imported {len(data['runs'])} runs / {len(data['strategies'])} strategies")


def compute_gates(metrics: dict, costs: dict, max_mdd: float = 0.25, extra: dict | None = None) -> dict:
    def g(value, threshold, op, ok):
        return {"value": value, "threshold": threshold, "op": op, "pass": bool(ok)}

    ci_low = float(metrics["pf_ci95"][0])
    gates = {
        "pf_net": g(metrics["pf_net"], 1.0, ">", metrics["pf_net"] > 1.0),
        "pf_ci_low": g(ci_low, 1.0, ">", ci_low > 1.0),
        "t_stat": g(metrics["t_stat"], 3.0, ">=", metrics["t_stat"] >= 3.0),
        "trades": g(int(metrics["n"]), 300, ">=", int(metrics["n"]) >= 300),
        "cost_stress_2x": g(metrics["pf_stress"], 1.0, ">", metrics["pf_stress"] > 1.0),
        "mdd_budget": g(metrics["mdd"], max_mdd, ">=", metrics["mdd"] >= -max_mdd),
        "funding": g("included" if costs.get("funding") else "n/a (intradía)",
                     "required", "=", True),
    }
    # Puertas que solo puede evaluar el runner (fuente: su result.json).
    if extra:
        if extra.get("alpha_annual") is not None:
            gates["benchmark_alpha"] = g(round(float(extra["alpha_annual"]), 4), 0.0, ">",
                                          float(extra["alpha_annual"]) > 0.0)
        if extra.get("plateau_pass") is not None:
            gates["plateau"] = g("plano" if extra["plateau_pass"] else "pico aislado",
                                 "±20%", "=", bool(extra["plateau_pass"]))
        if extra.get("pbo") is not None:
            gates["pbo"] = g(round(float(extra["pbo"]), 4), 0.20, "≤",
                             float(extra["pbo"]) <= 0.20)
        if extra.get("dsr") is not None:
            gates["dsr"] = g(round(float(extra["dsr"]), 4), 0.95, "≥",
                             float(extra["dsr"]) >= 0.95)
        if extra.get("wfa_min_trades") is not None:
            gates["wfa"] = g(int(extra["wfa_min_trades"]), 30, "≥",
                             int(extra["wfa_min_trades"]) >= 30)
    return gates


def verdict_for(metrics: dict, gates: dict) -> tuple[str, str]:
    if metrics["pf_net"] <= 1.0 or not gates["cost_stress_2x"]["pass"] or not gates["mdd_budget"]["pass"]:
        return "REJECTED", "PF neto, stress de costes o MDD fuera de presupuesto"
    if gates.get("pbo", {}).get("pass") is False:
        return "REJECTED", "PBO fuera de umbral: la selección no distingue la señal del ruido"
    if gates.get("dsr", {}).get("pass") is False:
        return "REJECTED", "DSR fuera de umbral: el Sharpe no sobrevive al ajuste por múltiples pruebas"
    if gates.get("benchmark_alpha", {}).get("pass") is False:
        return "REJECTED", "alpha nulo o negativo frente a buy & hold"
    if gates.get("plateau", {}).get("pass") is False:
        return "REJECTED", "rendimiento concentrado en un pico aislado de parámetros"
    if not (gates["trades"]["pass"] and gates["t_stat"]["pass"] and gates["pf_ci_low"]["pass"]):
        return "INCONCLUSIVE", "sin potencia estadística (trades, t-stat o IC del PF)"
    if gates.get("wfa", {}).get("pass") is False:
        return "INCONCLUSIVE", "sin potencia estadística por fold en el walk-forward"
    return "APPROVED", ""


def project_files() -> list[dict]:
    rows = []
    for rel in WATCH:
        p = ROOT / rel
        if not p.exists():
            rows.append({"path": rel, "exists": False})
            continue
        raw = p.read_bytes()
        rows.append({
            "path": rel, "exists": True, "bytes": len(raw),
            "mtime": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
            "sha256": hashlib.sha256(raw).hexdigest()[:16],
        })
    return rows


class Handler(BaseHTTPRequestHandler):
    server_version = "BTCRegistry/1.0"
    db: Path = DB_DEFAULT

    def log_message(self, fmt: str, *args) -> None:
        sys.stdout.write(f"{now()} {self.address_string()} {fmt % args}\n")

    # ---------------------------------------------------------------- plumbing
    def send_json(self, payload, status=HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, ctype: str) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            raise ValueError("empty body")
        if length > 1_048_576:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # -------------------------------------------------------------------- API
    def state(self) -> dict:
        con = connect(self.db)
        try:
            meta = con.execute("SELECT value FROM meta WHERE key='project'").fetchone()
            project = json.loads(meta["value"]) if meta else {}
            strategies = [dict(r) for r in con.execute("SELECT * FROM strategies ORDER BY family, timeframe, id")]
            cycles = []
            for r in con.execute("SELECT * FROM cycles ORDER BY created_at DESC"):
                d = dict(r)
                d["gates"] = {
                    "pbo": {"value": d["pbo"], "threshold": 0.20, "pass": d["pbo"] is not None and d["pbo"] <= 0.20},
                    "dsr": {"value": d["dsr"], "threshold": 0.95, "pass": d["dsr"] is not None and d["dsr"] >= 0.95},
                    "minbtl": {"value": d["minbtl_years"], "threshold": d["coverage_years"],
                               "pass": d["minbtl_years"] is not None and d["minbtl_years"] <= (d["coverage_years"] or 0)},
                    "wfa": {"value": d["wfa_min_trades"], "threshold": 30,
                            "pass": d["wfa_min_trades"] is not None and d["wfa_min_trades"] >= 30},
                }
                cycles.append(d)
            runs = []
            for r in con.execute("SELECT * FROM runs ORDER BY created_at DESC, id"):
                runs.append({
                    "id": r["id"], "strategy_id": r["strategy_id"], "cycle_id": r["cycle_id"],
                    "version": r["version"], "created_at": r["created_at"], "label": r["label"],
                    "params": json_field(r, "params", {}), "costs": json_field(r, "costs", {}),
                    "metrics": json_field(r, "metrics", {}), "gates": json_field(r, "gates", {}),
                    "verdict": r["verdict"], "artifacts": json_field(r, "artifacts", {}),
                    "equity": json_field(r, "equity", []), "notes": r["notes"],
                })
            events = [dict(r) for r in con.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT 500")]
            return {"project": project, "strategies": strategies, "cycles": cycles,
                    "runs": runs, "events": events, "files": project_files(),
                    "generated_at": now()}
        finally:
            con.close()

    def health(self) -> dict:
        """Liveness plus the integrity facts a caller actually wants.

        `ok` stays a plain liveness flag; `integrity` carries whether the stored
        metrics still reproduce and whether the artifacts agree with the cycle.
        Nothing here runs a backtest: it reads artifacts, so it is cheap enough
        to poll.
        """
        out = {"ok": True, "ts": now(), "db": str(self.db), "runs": None,
               "integrity": {"verified": None, "failures": None,
                             "data_hash": None, "artifacts_unknown_gates": None,
                             "cycle_matches_artifacts": None}}
        try:
            out["runs"] = self.count_runs()
        except Exception as exc:  # noqa: BLE001
            out["ok"] = False
            out["error"] = f"db: {exc}"
            return out

        integ = out["integrity"]
        vpath = ROOT / "runner" / "verification.json"
        if vpath.exists():
            try:
                ver = json.loads(vpath.read_text(encoding="utf-8"))
                integ["verified"] = ver.get("checked")
                integ["failures"] = ver.get("failures")
                integ["data_hash"] = ver.get("data_hash")
            except Exception:  # noqa: BLE001
                pass

        unknown = 0
        artifact_cycles = set()
        for path in sorted(RUNNER_OUT.glob("*.json")):
            try:
                art = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            unknown += sum(1 for g in (art.get("gates") or {}).values()
                           if g.get("pass") is None)
            if art.get("cycle_id"):
                artifact_cycles.add(art["cycle_id"])
        integ["artifacts_unknown_gates"] = unknown

        cands = sorted(RUNNER_VALIDATION.glob("*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if cands:
            try:
                newest = json.loads(cands[0].read_text(encoding="utf-8"))
                integ["cycle"] = newest.get("cycle_id")
                integ["cycle_matches_artifacts"] = (not artifact_cycles
                                                    or artifact_cycles == {newest.get("cycle_id")})
            except Exception:  # noqa: BLE001
                pass
        return out

    def runner_results(self) -> dict:
        """Deterministic runner artefacts (runner/out/*.json), newest first."""
        results, specs = [], []
        for path in sorted(RUNNER_OUT.glob("*.json")):
            try:
                r = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                results.append({"error": f"{path.name}: {exc}"})
                continue
            r["_file"] = path.name
            r["_bytes"] = path.stat().st_size
            results.append(r)
        for path in sorted(RUNNER_SPECS.glob("*.json")):
            try:
                s = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            specs.append({"file": path.name, "id": s.get("id"), "label": s.get("label"),
                          "version": s.get("version"), "family": s.get("family"),
                          "timeframe": s.get("timeframe_signal"),
                          "rule": (s.get("entry") or {}).get("rule"),
                          "params": s.get("params", {}),
                          "trials_declared": (s.get("validation") or {}).get("trials_declared")})
        validation = None
        if RUNNER_VALIDATION.is_dir():
            cands = sorted(RUNNER_VALIDATION.glob("*.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
            if cands:
                path = cands[0]
                try:
                    validation = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    validation = {"error": f"{path.name}: {exc}"}
                validation["_file"] = str(path.relative_to(ROOT)).replace("\\", "/")
                validation["_bytes"] = path.stat().st_size
        verification = None
        vpath = ROOT / "runner" / "verification.json"
        if vpath.exists():
            try:
                verification = json.loads(vpath.read_text(encoding="utf-8"))
                verification["_file"] = "runner/verification.json"
                verification["_mtime"] = datetime.fromtimestamp(
                    vpath.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M")
            except Exception as exc:  # noqa: BLE001
                verification = {"error": f"{vpath.name}: {exc}"}
        sensitivity = None
        spath = RUNNER_VALIDATION / "sensitivity" / "CYCLE-2026-11-full.json"
        if spath.exists():
            try:
                sensitivity = json.loads(spath.read_text(encoding="utf-8"))
                sensitivity["_file"] = str(spath.relative_to(ROOT)).replace("\\", "/")
            except Exception as exc:  # noqa: BLE001
                sensitivity = {"error": f"{spath.name}: {exc}"}
        universe = []
        udir = ROOT / "runner" / "out-universe"
        if udir.is_dir():
            for upath in sorted(udir.glob("*.json")):
                try:
                    art = json.loads(upath.read_text(encoding="utf-8"))
                    art["_file"] = str(upath.relative_to(ROOT)).replace("\\", "/")
                    universe.append(art)
                except Exception:  # noqa: BLE001  (un artefacto roto no rompe la vista)
                    continue
        return {"results": sorted(results, key=lambda r: (r.get("spec_id") or "").lower()),
                "specs": specs,
                "validation": validation,
                "verification": verification,
                "sensitivity": sensitivity,
                "universe": universe,
                "db_runs": self.count_runs()}

    def count_runs(self) -> int:
        con = connect(self.db)
        try:
            return int(con.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
        finally:
            con.close()

    def create_run(self) -> tuple[dict, int]:
        try:
            body = self.read_body()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"JSON inválido: {exc}"}, HTTPStatus.BAD_REQUEST
        missing = [k for k in ("strategy_id", "label", "metrics", "costs") if k not in body]
        if missing:
            return {"error": f"faltan campos: {missing}"}, HTTPStatus.BAD_REQUEST
        metrics = body["metrics"]
        bad = [k for k in REQUIRED_METRICS if k not in metrics]
        if bad:
            return {"error": f"faltan métricas: {bad}"}, HTTPStatus.BAD_REQUEST
        if not (isinstance(metrics["pf_ci95"], list) and len(metrics["pf_ci95"]) == 2):
            return {"error": "metrics.pf_ci95 debe ser [low, high]"}, HTTPStatus.BAD_REQUEST

        con = connect(self.db)
        try:
            if not con.execute("SELECT 1 FROM strategies WHERE id=?", (body["strategy_id"],)).fetchone():
                return {"error": "strategy_id desconocido"}, HTTPStatus.BAD_REQUEST
            cycle_id = body.get("cycle_id", "CYCLE-2026-11")
            cyc = con.execute("SELECT * FROM cycles WHERE id=?", (cycle_id,)).fetchone()
            if not cyc:
                return {"error": "cycle_id desconocido"}, HTTPStatus.BAD_REQUEST
            run_id = f"{body['strategy_id']}-v{body.get('version', '1.0.1')}-{body['label']}"
            if con.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone():
                return {"error": f"run ya registrada: {run_id} (append-only)"}, HTTPStatus.CONFLICT

            gates = compute_gates(metrics, body["costs"], extra=body)
            verdict, reason = verdict_for(metrics, gates)
            cycle_ok = (cyc["pbo"] or 0) <= 0.20 and (cyc["dsr"] or 0) >= 0.95
            if verdict == "APPROVED" and not cycle_ok:
                verdict, reason = "INCONCLUSIVE", "el ciclo no supera PBO/DSR; aprobación bloqueada"

            runner_verdict = body.get("runner_verdict")
            conflict = None
            if runner_verdict and runner_verdict != verdict:
                conflict = (f"discrepancia de veredicto en {run_id}: runner {runner_verdict} vs "
                            f"registro {verdict} (el runner evalúa 12 puertas, el registro "
                            f"{len(gates)})")

            con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (run_id, body["strategy_id"], cycle_id, body.get("version", "1.0.1"), now(),
                         body["label"], json.dumps(body.get("params", {})), json.dumps(body["costs"]),
                         json.dumps(metrics), json.dumps(gates), verdict,
                         json.dumps(body.get("artifacts", {})),
                         json.dumps(body.get("equity", [])), body.get("notes", "")))
            con.execute("INSERT INTO events(ts, actor, type, run_id, message) VALUES (?,?,?,?,?)",
                        (now(), body.get("actor", "runner"), "run", run_id,
                         f"run registrada: PF neto {metrics['pf_net']} · veredicto {verdict}"
                         + (f" ({reason})" if reason else "")))
            if conflict:
                con.execute("INSERT INTO events(ts, actor, type, run_id, message) VALUES (?,?,?,?,?)",
                            (now(), "system", "audit", run_id, conflict))
            con.commit()
            return {"id": run_id, "verdict": verdict, "gates": gates, "reason": reason,
                    "runner_verdict": runner_verdict, "conflict": conflict}, HTTPStatus.CREATED
        finally:
            con.close()

    def create_cycle(self) -> tuple[dict, int]:
        """Register a measured selection cycle (PBO/DSR/MinBTL/WFA).

        The server does not trust the numbers blindly: it requires the validation
        artifact the client claims to quote, and refuses the insert when the
        artifact's own figures disagree with the payload.
        """
        try:
            body = self.read_body()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"JSON inválido: {exc}"}, HTTPStatus.BAD_REQUEST
        missing = [k for k in ("id", "name", "pbo", "dsr", "minbtl_years",
                               "coverage_years", "wfa_min_trades", "validation_ref")
                   if k not in body]
        if missing:
            return {"error": f"faltan campos: {missing}"}, HTTPStatus.BAD_REQUEST

        ref = body["validation_ref"]
        artifact = None
        path = (ROOT / ref).resolve()
        if not path.is_relative_to(ROOT) or not path.exists():
            return {"error": f"validation_ref no encontrado: {ref}"}, HTTPStatus.BAD_REQUEST
        artifact = json.loads(path.read_text(encoding="utf-8"))
        checks = {
            "pbo": (artifact.get("pbo") or {}).get("pbo"),
            "dsr": (artifact.get("dsr") or {}).get("dsr"),
            "minbtl_years": (artifact.get("minbtl") or {}).get("minbtl_years"),
            "wfa_min_trades": (artifact.get("wfa") or {}).get("min_trades_per_fold"),
        }
        drift = [k for k, v in checks.items()
                 if v is not None and abs(float(v) - float(body[k])) > 1e-6]
        if drift:
            return {"error": f"cifras no coinciden con el artefacto: {drift}"}, HTTPStatus.CONFLICT

        pbo, dsr = float(body["pbo"]), float(body["dsr"])
        minbtl, cover = float(body["minbtl_years"]), float(body["coverage_years"])
        wfa = int(body["wfa_min_trades"])
        ok = pbo <= 0.20 and dsr >= 0.95 and minbtl <= cover and wfa >= 30
        verdict = "APPROVED" if ok else "REJECTED"

        con = connect(self.db)
        try:
            if con.execute("SELECT 1 FROM cycles WHERE id=?", (body["id"],)).fetchone():
                return {"error": f"ciclo ya registrado: {body['id']} (append-only)"}, HTTPStatus.CONFLICT
            con.execute("INSERT INTO cycles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (body["id"], body["name"], now(), pbo, dsr, 0.95,
                         body.get("sr_best"), body.get("sr0"), minbtl, cover,
                         int(body.get("trials") or 0), wfa,
                         int(body.get("wfa_folds") or 0), int(body.get("wfa_total_trades") or 0),
                         verdict, body.get("notes", "")))
            con.execute("INSERT INTO events(ts, actor, type, run_id, message) VALUES (?,?,?,?,?)",
                        (now(), body.get("actor", "runner"), "cycle", None,
                         f"ciclo {body['id']} registrado: PBO {pbo:.3f} · DSR {dsr:.3f} · "
                         f"MinBTL {minbtl:.1f}a · WFA {wfa} trades/fold → {verdict}"))
            con.commit()
            return {"id": body["id"], "verdict": verdict,
                    "validation_ref": ref}, HTTPStatus.CREATED
        finally:
            con.close()

    def create_event(self) -> tuple[dict, int]:
        try:
            body = self.read_body()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"JSON inválido: {exc}"}, HTTPStatus.BAD_REQUEST
        if not body.get("message"):
            return {"error": "message requerido"}, HTTPStatus.BAD_REQUEST
        # A misspelled kind must not be silently downgraded to `note`: an audit
        # that arrives as a note loses its meaning in the log.
        unknown = [k for k in body if k not in ("type", "actor", "run_id", "message")]
        if unknown:
            return {"error": f"campos desconocidos: {unknown}; se espera 'type', no 'kind'"}, \
                HTTPStatus.BAD_REQUEST
        kind = body.get("type", "note")
        if kind not in EVENT_TYPES:
            return {"error": f"type inválido: {kind!r}; válidos: {sorted(EVENT_TYPES)}"}, \
                HTTPStatus.BAD_REQUEST
        if kind == "run" and not body.get("run_id"):
            return {"error": "un evento de tipo 'run' necesita run_id"}, HTTPStatus.BAD_REQUEST
        con = connect(self.db)
        try:
            cur = con.execute("INSERT INTO events(ts, actor, type, run_id, message) VALUES (?,?,?,?,?)",
                              (now(), body.get("actor", "human"), kind,
                               body.get("run_id"), body["message"]))
            con.commit()
            return {"id": cur.lastrowid, "ts": now(), "type": kind}, HTTPStatus.CREATED
        finally:
            con.close()

    # ------------------------------------------------------------- HTTP verbs
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self.send_file(UI / "index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self.send_file(UI / "app.js", "text/javascript; charset=utf-8")
        if path == "/style.css":
            return self.send_file(UI / "style.css", "text/css; charset=utf-8")
        if path == "/api/state":
            return self.send_json(self.state())
        if path == "/api/health":
            return self.send_json(self.health())
        if path == "/api/results":
            return self.send_json(self.runner_results())
        if path == "/api/export":
            payload = self.state()
            body = json.dumps(payload, indent=1, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="registry_export.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/runs":
            payload, status = self.create_run()
            return self.send_json(payload, status)
        if path == "/api/events":
            payload, status = self.create_event()
            return self.send_json(payload, status)
        if path == "/api/cycles":
            payload, status = self.create_cycle()
            return self.send_json(payload, status)
        return self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    con = connect(args.db)
    seed_db(con)
    con.close()
    Handler.db = args.db
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"registry: http://{args.host}:{args.port}  db={args.db}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
