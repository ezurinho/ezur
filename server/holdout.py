"""Candado del holdout, aplicado al runner y no solo a los scripts de research.

El tramo 2026-12-01/2027-05-31 es evidencia de una sola vez. Un backtest que
lo toque sin pre-registro ni sello reproducible debe fallar antes de ejecutar
el motor, no después de mirar el resultado.

El sello usa las mismas piezas que `confirmatory.seal_holdout`: hash del CSV,
de la identidad de la estrategia y de la configuración que define el estudio.
La configuración sellada excluye `execution` a propósito: el estrés de costes
duplica comisiones y slippage, y debe poder correr sobre el mismo holdout sin
considerarse otro estudio.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .confirmatory import canonical_hash, file_hash, seal_holdout, verify_seal

HOLDOUT_START = datetime(2026, 12, 1, tzinfo=timezone.utc)
# El final documentado es inclusivo (23:59:59); para comparar ventanas
# semiaabiertas se usa el comienzo del día siguiente.
HOLDOUT_END = datetime(2027, 5, 31, 23, 59, 59, tzinfo=timezone.utc)
HOLDOUT_END_EXCLUSIVE = datetime(2027, 6, 1, tzinfo=timezone.utc)
SEAL_ENV = "EZUR_HOLDOUT_UNSEAL"

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "holdout"
PREREG_FILE = DATA_DIR / "PREREGISTRO.sha256"
LOCK_FILE = DATA_DIR / "lock.json"
# El ledger y las atestaciones son la fuente de verdad del consumo. Viven
# separados del sello: el sello dice qué estudio se autorizó; el ledger, qué
# pasó con él.
EVENTS_FILE = DATA_DIR / "events.jsonl"
ATTESTATION_DIR = DATA_DIR / "attestations"
PERMIT_TTL_SECONDS = 5 * 60

_ONE_MICROSECOND = timedelta(microseconds=1)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEDGER_LOCK = threading.RLock()


class HoldoutSealed(RuntimeError):
    """Se intentó usar el holdout sin autorización registrada.

    El mensaje sigue siendo legible para la CLI; los campos estructurados
    permiten que la API devuelva código, estado e incidente sin inventarlos a
    partir del texto.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "HO-001",
        state: str = "SEALED",
        incident_id: str | None = None,
        status_code: int = 409,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.state = state
        # Un identificador estable permite citar el intento aunque el evento
        # no se pueda persistir; el ledger añade el suyo cuando sí se escribe.
        self.incident_id = incident_id or (
            "hoi_" + hashlib.sha256(f"{code}:{message}".encode("utf-8")).hexdigest()[:20]
        )
        self.status_code = status_code

    def as_dict(self) -> dict[str, Any]:
        return {
            "detail": str(self),
            "code": self.code,
            "state": self.state,
            "incident_id": self.incident_id,
        }


@dataclass(frozen=True)
class HoldoutPermit:
    """Permiso de estudio; las sub-corridas de estrés comparten este permiso."""

    permit_id: str
    surface: str
    study_id: str
    dataset_id: str
    study_hash: str
    strategy_hash: str
    prereg_sha256: str
    seal_sha256: str
    window: tuple[str, str]
    issued_at: str
    expires_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "permit_id": self.permit_id,
            "surface": self.surface,
            "study_id": self.study_id,
            "dataset_id": self.dataset_id,
            "study_hash": self.study_hash,
            "strategy_hash": self.strategy_hash,
            "prereg_sha256": self.prereg_sha256,
            "seal_sha256": self.seal_sha256,
            "window": list(self.window),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def effective_window(
    dataset_first: datetime | None,
    dataset_last: datetime | None,
    *,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime] | None:
    """Intersección real entre el CSV y la ventana pedida (fin exclusivo)."""
    if dataset_first is None or dataset_last is None:
        return None
    first = _aware(dataset_first)
    last = _aware(dataset_last)
    if start is not None:
        first = max(first, _aware(start))
    if end is not None:
        last = min(last, _aware(end) - _ONE_MICROSECOND)
    return (first, last) if first <= last else None


def overlaps_holdout(first: datetime, last: datetime) -> bool:
    return first < HOLDOUT_END_EXCLUSIVE and last >= HOLDOUT_START


def holdout_config(settings) -> dict[str, Any]:
    """Parte del perfil que no puede cambiar entre el sello y la corrida.

    `execution` queda fuera porque el test de costes duplicados es una
    sensibilidad del mismo estudio, no un estudio nuevo. `risk` sí entra: un
    cambio de riesgo cambia qué operaciones sobreviven al holdout.
    """
    payload = settings.model_dump(mode="json")
    return {
        "strategy": payload["strategy"],
        "instruments": payload["instruments"],
        "risk": payload["risk"],
    }


def strategy_payload(strategy) -> dict[str, Any]:
    params = getattr(strategy, "params", None)
    if hasattr(params, "model_dump"):
        params = params.model_dump(mode="json")
    return {
        "id": getattr(strategy, "id", ""),
        "version": getattr(strategy, "version", ""),
        "params": params,
    }


def _prereg_digest() -> str | None:
    """SHA-256 declarado en el pre-registro, si es verificable."""
    if not PREREG_FILE.is_file():
        return None
    try:
        digest = PREREG_FILE.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return digest if _SHA256.fullmatch(digest) else None


def _seal_time_error(sealed_ts: Any) -> str | None:
    """Un sello posterior al inicio del holdout firma después de ver los datos.

    El corte es estricto: el sello tiene que existir antes de
    ``2026-12-01T00:00:00Z``. Un sello exactamente en el inicio ya no puede
    demostrar que el pre-registro se congeló antes de que el tramo existiera.
    """
    sealed_at = _instant(sealed_ts)
    if sealed_at is None:
        return "el sello no tiene una fecha de creación válida"
    if sealed_at >= HOLDOUT_START:
        return (
            f"el sello se creó el {sealed_at.isoformat()}, después de que empezara "
            f"el holdout ({HOLDOUT_START.isoformat()}); el pre-registro debe ser "
            "anterior a los datos"
        )
    return None


def _check_pre_registration() -> str:
    if os.environ.get(SEAL_ENV) != "1":
        raise HoldoutSealed(
            f"el holdout {HOLDOUT_START.date()}/{HOLDOUT_END.date()} está sellado; "
            f"define {SEAL_ENV}=1 y un pre-registro firmado para abrirlo",
            code="HO-001",
            state="SEALED",
        )
    if not PREREG_FILE.is_file():
        raise HoldoutSealed(
            f"{SEAL_ENV}=1 pero falta {PREREG_FILE}: sin pre-registro firmado no se abre",
            code="HO-002",
            state="SEALED",
        )
    digest = _prereg_digest()
    if digest is None:
        raise HoldoutSealed(
            f"{PREREG_FILE} no contiene un SHA-256 válido; el pre-registro no es verificable",
            code="HO-002",
            state="SEALED",
        )
    return digest


def guard_window(
    dataset_first: datetime | None,
    dataset_last: datetime | None,
    *,
    start: datetime | None,
    end: datetime | None,
    dataset_path: str | Path,
    config: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    """Autoriza o aborta el tramo solicitado. Devuelve la traza para el informe."""
    window = effective_window(dataset_first, dataset_last, start=start, end=end)
    if window is None:
        return {"overlaps": False, "authorized": False, "window": None}
    first, last = window
    trace = {
        "overlaps": True,
        "authorized": False,
        "window": [first.isoformat(), last.isoformat()],
    }
    if not overlaps_holdout(first, last):
        trace["overlaps"] = False
        return trace

    # El estado terminal manda sobre el entorno: si ya se consumió, no se
    # vuelve a abrir aunque alguien deje el flag puesto o lo quite.
    current = status()
    if current["state"] == "CONSUMED":
        raise HoldoutSealed(
            "el holdout ya fue consumido; no hay una segunda lectura",
            code="HO-005",
            state="CONSUMED",
        )
    if current["state"] == "FAILED":
        raise HoldoutSealed(
            "el estudio de holdout falló y no se reintenta",
            code="HO-006",
            state="FAILED",
        )
    if current["state"] == "QUARANTINED":
        raise HoldoutSealed(
            "el ledger del holdout está en cuarentena",
            code="HO-011",
            state="QUARANTINED",
            status_code=500,
        )
    _check_pre_registration()
    verdict = verify_seal(
        LOCK_FILE,
        dataset_path=dataset_path,
        config=config,
        strategy=strategy,
    )
    if not verdict["ok"]:
        reasons = "; ".join(verdict["reasons"]) or "sello ausente o inválido"
        raise HoldoutSealed(
            f"el tramo {HOLDOUT_START.date()}/{HOLDOUT_END.date()} no tiene un sello "
            f"válido en {LOCK_FILE}: {reasons}",
            code="HO-003",
            state="SEALED",
        )
    time_error = _seal_time_error(verdict.get("sealed_ts"))
    if time_error:
        raise HoldoutSealed(time_error, code="HO-003", state="SEALED")
    trace["authorized"] = True
    trace["sealed_ts"] = verdict.get("sealed_ts")
    return trace


def seal_run(
    dataset_path: str | Path,
    settings,
    strategy,
    *,
    protocol: str = "holdout 2026-12-01/2027-05-31",
) -> dict[str, Any]:
    """Crea el sello único para este dataset, perfil y estrategia."""
    return seal_holdout(
        LOCK_FILE,
        dataset_path=dataset_path,
        config=holdout_config(settings),
        strategy=strategy_payload(strategy),
        protocol=protocol,
    )


# ---------------------------------------------------------------------------
# Estado persistido, permiso de estudio y atestación
# ---------------------------------------------------------------------------

TERMINAL_STATES = {"CONSUMED", "FAILED", "QUARANTINED"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _chain_hash(previous: str, body: dict[str, Any]) -> str:
    return hashlib.sha256(
        (previous + canonical_hash(body)).encode("utf-8")
    ).hexdigest()


def _read_events() -> list[dict[str, Any]]:
    """Ledger verificado; una línea rota no se ignora nunca."""
    target = Path(EVENTS_FILE)
    if not target.is_file():
        return []
    events: list[dict[str, Any]] = []
    previous = ""
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise HoldoutSealed(
            f"no se puede leer el ledger del holdout: {error}",
            code="HO-011",
            state="QUARANTINED",
            status_code=500,
        ) from error
    for index, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise HoldoutSealed(
                f"ledger del holdout corrupto en la línea {index}: {error}",
                code="HO-011",
                state="QUARANTINED",
                status_code=500,
            ) from error
        if not isinstance(event, dict):
            raise HoldoutSealed(
                f"ledger del holdout corrupto en la línea {index}: no es un objeto",
                code="HO-011",
                state="QUARANTINED",
                status_code=500,
            )
        if event.get("prev_hash", "") != previous:
            raise HoldoutSealed(
                f"ledger del holdout roto en la línea {index}: prev_hash no coincide",
                code="HO-011",
                state="QUARANTINED",
                status_code=500,
            )
        body = {key: value for key, value in event.items() if key != "chain_hash"}
        if event.get("chain_hash") != _chain_hash(previous, body):
            raise HoldoutSealed(
                f"ledger del holdout roto en la línea {index}: chain_hash no corresponde",
                code="HO-011",
                state="QUARANTINED",
                status_code=500,
            )
        previous = str(event["chain_hash"])
        events.append(event)
    return events


def _append_event(
    event: str,
    *,
    state_before: str,
    state_after: str,
    severity: str = "info",
    code: str = "",
    **fields: Any,
) -> dict[str, Any]:
    """Append con fsync. Si no se puede escribir, la operación no continúa."""
    with _LEDGER_LOCK:
        events = _read_events()
        previous = str(events[-1]["chain_hash"]) if events else ""
        ts = _now().isoformat()
        body: dict[str, Any] = {
            "seq": len(events) + 1,
            "ts": ts,
            "event": event,
            "severity": severity,
            "code": code,
            "state_before": state_before,
            "state_after": state_after,
            "prev_hash": previous,
            **{key: value for key, value in fields.items() if value is not None},
        }
        body["incident_id"] = "hoi_" + canonical_hash(body)[:20]
        body["chain_hash"] = _chain_hash(previous, body)
        target = Path(EVENTS_FILE)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(body, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as error:
            raise HoldoutSealed(
                f"no se puede escribir el ledger del holdout: {error}",
                code="HO-011",
                state="QUARANTINED",
                status_code=500,
            ) from error
        return body


def _active_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("event") in {"consumed", "failed", "claimed", "authorized"}:
            return event
    return None


def _state_from_events(
    events: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None, str]:
    if any(event.get("event") == "quarantined" for event in events):
        return "QUARANTINED", _active_event(events), "ledger en cuarentena"
    active = _active_event(events)
    if active is None:
        return ("READY" if _prereg_digest() and LOCK_FILE.is_file() else "SEALED"), None, ""
    name = active.get("event")
    if name == "consumed":
        return "CONSUMED", active, ""
    if name == "failed":
        return "FAILED", active, str(active.get("message") or "estudio fallido")
    expires = _instant(active.get("expires_at"))
    if expires is not None and _now() > expires:
        return "READY", active, "permiso expirado"
    if name == "authorized":
        return "AUTHORIZED", active, ""
    if name == "claimed":
        return "RUNNING", active, ""
    return "SEALED", None, ""


def _instant(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def status() -> dict[str, Any]:
    """Estado derivado del ledger; nunca desbloquea ni lee el dataset."""
    prereg = _prereg_digest()
    sealed = LOCK_FILE.is_file()
    try:
        events = _read_events()
    except HoldoutSealed as error:
        return {
            "state": "QUARANTINED",
            "window": [HOLDOUT_START.date().isoformat(), HOLDOUT_END.date().isoformat()],
            "prereg_present": bool(prereg),
            "seal_present": sealed,
            "permit": None,
            "consumed_at": None,
            "last_incident": {
                "id": None,
                "code": error.code,
                "ts": _now().isoformat(),
                "message": str(error),
            },
            "promotion_blocked": True,
            "incidents_open": 1,
            "ledger_ok": False,
        }
    state, active, reason = _state_from_events(events)
    consumed = next(
        (event for event in reversed(events) if event.get("event") == "consumed"),
        None,
    )
    incidents = [
        event
        for event in events
        if event.get("severity") in {"warn", "critical"}
    ]
    active_incidents = [
        event for event in incidents if event.get("event") not in {"consumed"}
    ]
    last_incident = incidents[-1] if incidents else None
    permit = None
    if active is not None and state in {"AUTHORIZED", "RUNNING"}:
        permit = {
            key: active.get(key)
            for key in (
                "permit_id",
                "surface",
                "study_id",
                "dataset_id",
                "study_hash",
                "strategy_hash",
                "window",
                "issued_at",
                "expires_at",
            )
        }
    return {
        "state": state,
        "window": [HOLDOUT_START.date().isoformat(), HOLDOUT_END.date().isoformat()],
        "prereg_present": bool(prereg),
        "seal_present": sealed,
        "permit": permit,
        "consumed_at": consumed.get("consumed_at") if consumed else None,
        "last_incident": (
            {
                "id": last_incident.get("incident_id"),
                "code": last_incident.get("code"),
                "ts": last_incident.get("ts"),
                "message": last_incident.get("message"),
            }
            if last_incident
            else None
        ),
        "promotion_blocked": state != "CONSUMED",
        "incidents_open": len(active_incidents),
        "ledger_ok": True,
        "reason": reason,
    }


def begin_study(
    *,
    surface: str,
    dataset_path: str | Path,
    dataset_id: str,
    settings,
    strategy,
    window: tuple[datetime, datetime],
    request_id: str | None = None,
) -> HoldoutPermit:
    """Autoriza y reclama un estudio. Solo hay un estudio vivo a la vez."""
    if surface not in {"runner", "api", "cli"}:
        raise ValueError(f"superficie de holdout inválida: {surface}")
    with _LEDGER_LOCK:
        prereg = _check_pre_registration()
        seal = verify_seal(
            LOCK_FILE,
            dataset_path=dataset_path,
            config=holdout_config(settings),
            strategy=strategy_payload(strategy),
        )
        if not seal["ok"]:
            reasons = "; ".join(seal["reasons"]) or "sello ausente o inválido"
            raise HoldoutSealed(
                f"el tramo {HOLDOUT_START.date()}/{HOLDOUT_END.date()} no tiene un sello "
                f"válido en {LOCK_FILE}: {reasons}",
                code="HO-003",
                state="SEALED",
            )
        time_error = _seal_time_error(seal.get("sealed_ts"))
        if time_error:
            raise HoldoutSealed(time_error, code="HO-003", state="SEALED")
        events = _read_events()
        state, active, _reason = _state_from_events(events)
        if state == "CONSUMED":
            raise HoldoutSealed(
                "el holdout ya fue consumido; no hay una segunda lectura",
                code="HO-005",
                state=state,
            )
        if state == "FAILED":
            raise HoldoutSealed(
                "el estudio de holdout falló y no se reintenta",
                code="HO-006",
                state=state,
            )
        if state == "QUARANTINED":
            raise HoldoutSealed(
                "el ledger del holdout está en cuarentena",
                code="HO-011",
                state=state,
                status_code=500,
            )
        if state in {"AUTHORIZED", "RUNNING"}:
            raise HoldoutSealed(
                "ya hay un permiso de holdout vivo; no se puede abrir otro",
                code="HO-008",
                state=state,
            )
        if state == "SEALED":
            raise HoldoutSealed(
                f"el holdout {HOLDOUT_START.date()}/{HOLDOUT_END.date()} está sellado",
                code="HO-001",
                state=state,
            )
        if active is not None and active.get("event") in {"authorized", "claimed"}:
            # El estado ya es READY por TTL; se deja constancia sin reutilizar el permiso.
            _append_event(
                "expired",
                state_before="AUTHORIZED" if active.get("event") == "authorized" else "RUNNING",
                state_after="READY",
                severity="warn",
                code="HO-007",
                permit_id=active.get("permit_id"),
                message="permiso expirado antes de reclamar",
            )
        study_payload = {
            "dataset_id": dataset_id,
            "study_hash": canonical_hash(holdout_config(settings)),
            "strategy_hash": canonical_hash(strategy_payload(strategy)),
            "window": [window[0].isoformat(), window[1].isoformat()],
            "prereg_sha256": prereg,
            "seal_sha256": file_hash(LOCK_FILE),
        }
        study_id = canonical_hash(study_payload)
        permit_id = "hp_" + uuid.uuid4().hex[:20]
        issued = _now()
        expires = issued + timedelta(seconds=PERMIT_TTL_SECONDS)
        fields = {
            **study_payload,
            "study_id": study_id,
            "permit_id": permit_id,
            "surface": surface,
            "request_id": request_id,
            "issued_at": issued.isoformat(),
            "expires_at": expires.isoformat(),
        }
        _append_event(
            "authorized",
            state_before="READY",
            state_after="AUTHORIZED",
            **fields,
        )
        _append_event(
            "claimed",
            state_before="AUTHORIZED",
            state_after="RUNNING",
            **fields,
        )
        return HoldoutPermit(
            permit_id=permit_id,
            surface=surface,
            study_id=study_id,
            dataset_id=dataset_id,
            study_hash=study_payload["study_hash"],
            strategy_hash=study_payload["strategy_hash"],
            prereg_sha256=prereg,
            seal_sha256=study_payload["seal_sha256"],
            window=(window[0].isoformat(), window[1].isoformat()),
            issued_at=issued.isoformat(),
            expires_at=expires.isoformat(),
        )


def _permit_from_event(event: dict[str, Any]) -> HoldoutPermit:
    return HoldoutPermit(
        permit_id=str(event["permit_id"]),
        surface=str(event.get("surface") or ""),
        study_id=str(event["study_id"]),
        dataset_id=str(event["dataset_id"]),
        study_hash=str(event["study_hash"]),
        strategy_hash=str(event["strategy_hash"]),
        prereg_sha256=str(event.get("prereg_sha256") or ""),
        seal_sha256=str(event.get("seal_sha256") or ""),
        window=(str(event["window"][0]), str(event["window"][1])),
        issued_at=str(event["issued_at"]),
        expires_at=str(event["expires_at"]),
    )


def permit_from_id(permit_id: str) -> HoldoutPermit:
    """Carga un permiso vivo. Un permiso consumido/fallido no se reabre."""
    events = _read_events()
    matching = [event for event in events if event.get("permit_id") == permit_id]
    if not matching:
        raise HoldoutSealed(
            f"permiso de holdout desconocido: {permit_id}",
            code="HO-007",
            state=status()["state"],
        )
    last = matching[-1]
    if last.get("event") == "consumed":
        raise HoldoutSealed(
            "el permiso ya fue consumido",
            code="HO-005",
            state="CONSUMED",
        )
    if last.get("event") == "failed":
        raise HoldoutSealed(
            "el permiso ya falló",
            code="HO-006",
            state="FAILED",
        )
    state, active, _reason = _state_from_events(events)
    if (
        state == "READY"
        and active is not None
        and active.get("permit_id") == permit_id
        and active.get("event") in {"authorized", "claimed"}
    ):
        _append_event(
            "expired",
            state_before="AUTHORIZED" if active.get("event") == "authorized" else "RUNNING",
            state_after="READY",
            severity="warn",
            code="HO-007",
            permit_id=permit_id,
            message="permiso expirado antes de terminar el estudio",
        )
        raise HoldoutSealed(
            "el permiso de holdout expirado",
            code="HO-007",
            state="READY",
        )
    if state != "RUNNING" or active is None or active.get("permit_id") != permit_id:
        raise HoldoutSealed(
            "el permiso de holdout no está vivo",
            code="HO-007",
            state=state,
        )
    expires = _instant(active.get("expires_at"))
    if expires is not None and _now() > expires:
        _append_event(
            "expired",
            state_before="RUNNING",
            state_after="READY",
            severity="warn",
            code="HO-007",
            permit_id=permit_id,
            message="permiso expirado antes de terminar el estudio",
        )
        raise HoldoutSealed(
            "el permiso de holdout expirado",
            code="HO-007",
            state="READY",
        )
    return _permit_from_event(active)


def verify_permit(
    permit: HoldoutPermit | str,
    *,
    dataset_id: str,
    study_hash: str,
    strategy_hash: str,
) -> HoldoutPermit:
    """La identidad de cada sub-corrida debe ser la del permiso."""
    resolved = permit_from_id(permit) if isinstance(permit, str) else permit
    mismatches = []
    if resolved.dataset_id != dataset_id:
        mismatches.append("dataset")
    if resolved.study_hash != study_hash:
        mismatches.append("configuración")
    if resolved.strategy_hash != strategy_hash:
        mismatches.append("estrategia")
    if mismatches:
        raise HoldoutSealed(
            "el estudio no coincide con el permiso sellado: " + ", ".join(mismatches),
            code="HO-004",
            state="RUNNING",
            status_code=403,
        )
    return resolved


def _write_attestation(permit_id: str, payload: dict[str, Any]) -> Path:
    target = Path(ATTESTATION_DIR) / f"{permit_id}.json"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, target)
    except OSError as error:
        raise HoldoutSealed(
            f"no se puede escribir la atestación del holdout: {error}",
            code="HO-012",
            state="FAILED",
        ) from error
    return target


def _evidence_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    """Copia canónica sin los bloques que la propia atestación modifica."""
    payload = {key: value for key, value in evidence.items() if key != "holdout"}
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, dict):
        payload["diagnostics"] = {
            key: value for key, value in diagnostics.items() if key != "holdout"
        }
    return payload


def consume_study(
    permit_id: str,
    evidence: dict[str, Any],
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Cierra el estudio con una atestación ligada al contenido de la evidencia."""
    permit = permit_from_id(permit_id)
    payload = _evidence_payload(evidence)
    evidence_sha256 = canonical_hash(payload)
    consumed_at = _now().isoformat()
    attestation = {
        "state": "CONSUMED",
        "permit_id": permit.permit_id,
        "surface": permit.surface,
        "study_id": permit.study_id,
        "dataset_id": permit.dataset_id,
        "study_hash": permit.study_hash,
        "strategy_hash": permit.strategy_hash,
        "prereg_sha256": permit.prereg_sha256,
        "seal_sha256": permit.seal_sha256,
        "window": list(permit.window),
        "evidence_sha256": evidence_sha256,
        "consumed_at": consumed_at,
        "request_id": request_id,
    }
    attestation_sha256 = canonical_hash(attestation)
    attestation["attestation_sha256"] = attestation_sha256
    target = _write_attestation(permit.permit_id, attestation)
    try:
        _append_event(
            "consumed",
            state_before="RUNNING",
            state_after="CONSUMED",
            permit_id=permit.permit_id,
            study_id=permit.study_id,
            dataset_id=permit.dataset_id,
            study_hash=permit.study_hash,
            strategy_hash=permit.strategy_hash,
            prereg_sha256=permit.prereg_sha256,
            seal_sha256=permit.seal_sha256,
            window=list(permit.window),
            evidence_sha256=evidence_sha256,
            attestation_sha256=attestation_sha256,
            consumed_at=consumed_at,
            request_id=request_id,
        )
    except HoldoutSealed:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return attestation


def fail_study(
    permit_id: str,
    message: str,
    *,
    code: str = "HO-012",
    request_id: str | None = None,
) -> dict[str, Any] | None:
    """Cierra un estudio fallido; es terminal y no se reintenta."""
    try:
        events = _read_events()
    except HoldoutSealed:
        return None
    matching = [event for event in events if event.get("permit_id") == permit_id]
    if not matching:
        return None
    last = matching[-1]
    if last.get("event") in {"consumed", "failed"}:
        return last
    return _append_event(
        "failed",
        state_before="RUNNING",
        state_after="FAILED",
        severity="critical",
        code=code,
        permit_id=permit_id,
        message=message,
        request_id=request_id,
    )


def verify_consumed(
    evidence: dict[str, Any],
    *,
    dataset_id: str | None = None,
    study_hash: str | None = None,
    strategy_hash: str | None = None,
    window: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Verifica la atestación contra el ledger, no solo contra el JSON."""
    block = evidence.get("holdout")
    checks: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []

    def check(name: str, ok: bool, reason: str) -> None:
        checks[name] = {"pass": bool(ok), "reason": "" if ok else reason}
        if not ok:
            reasons.append(reason)

    if not isinstance(block, dict):
        reason = "no hay holdout consumido"
        for name in (
            "holdout_consumido",
            "holdout_atestacion",
            "holdout_identidad",
            "holdout_ventana",
            "holdout_unico",
            "holdout_sin_incidentes",
        ):
            check(name, False, reason)
        return {"ok": False, "reasons": reasons, "checks": checks, "block": None}

    events = _read_events()
    state, _active, _reason = _state_from_events(events)
    permit_id = str(block.get("permit_id") or "")
    consumed = next(
        (
            event
            for event in reversed(events)
            if event.get("event") == "consumed" and event.get("permit_id") == permit_id
        ),
        None,
    )
    check("holdout_consumido", block.get("state") == "CONSUMED" and consumed is not None, "no hay holdout consumido")
    check("holdout_unico", state == "CONSUMED", "el ledger no está en CONSUMED")

    payload = _evidence_payload(evidence)
    digest = canonical_hash(payload)
    stored = attestation_for(permit_id) if permit_id else None
    stored_body = (
        {key: value for key, value in stored.items() if key != "attestation_sha256"}
        if isinstance(stored, dict)
        else {}
    )
    stored_ok = bool(stored) and canonical_hash(stored_body) == stored.get(
        "attestation_sha256"
    )
    try:
        seal_payload = json.loads(Path(LOCK_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seal_payload = None
    seal_time_error = (
        _seal_time_error(seal_payload.get("sealed_ts"))
        if isinstance(seal_payload, dict)
        else "no se puede leer la fecha del sello"
    )
    check(
        "holdout_atestacion",
        bool(consumed)
        and consumed.get("evidence_sha256") == digest
        and block.get("evidence_sha256") == digest
        and consumed.get("attestation_sha256") == block.get("attestation_sha256")
        and stored_ok
        and seal_time_error is None,
        seal_time_error or "la evidencia no coincide con la atestación",
    )
    expected_dataset = (
        dataset_id
        or str(evidence.get("dataset_id") or "")
        or str(block.get("dataset_id") or "")
    )
    expected_study = study_hash or str(block.get("study_hash") or "")
    expected_strategy = strategy_hash or str(block.get("strategy_hash") or "")
    identity_ok = bool(expected_dataset) and bool(expected_study) and bool(expected_strategy)
    if consumed:
        identity_ok = identity_ok and all(
            [
                consumed.get("dataset_id") == expected_dataset,
                consumed.get("study_hash") == expected_study,
                consumed.get("strategy_hash") == expected_strategy,
                block.get("dataset_id") == expected_dataset,
                block.get("study_hash") == expected_study,
                block.get("strategy_hash") == expected_strategy,
            ]
        )
    else:
        identity_ok = False
    check("holdout_identidad", identity_ok, "la identidad del holdout no coincide")
    expected_window = list(window) if window else block.get("window")
    check(
        "holdout_ventana",
        bool(expected_window)
        and list(block.get("window") or []) == list(expected_window)
        and bool(consumed)
        and list(consumed.get("window") or []) == list(expected_window),
        "la ventana de la evidencia no es la del holdout",
    )
    critical = [
        event
        for event in events
        if event.get("severity") == "critical"
        and event.get("event") not in {"consumed", "failed"}
    ]
    check("holdout_sin_incidentes", not critical, "hay incidentes críticos abiertos")
    return {
        "ok": not reasons,
        "reasons": reasons,
        "checks": checks,
        "block": block,
    }


def attestation_for(permit_id: str) -> dict[str, Any] | None:
    target = Path(ATTESTATION_DIR) / f"{permit_id}.json"
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def assert_no_compare(dataset_path: str | Path, symbols: list[str]) -> None:
    """Comparar estrategias sobre holdout es selección: se rechaza siempre."""
    from .market.csv_data import validate_dataset

    report = validate_dataset(dataset_path, symbols)
    if not report.ok or report.first_ts is None or report.last_ts is None:
        return
    if overlaps_holdout(report.first_ts, report.last_ts):
        raise HoldoutSealed(
            "comparar estrategias sobre el holdout es selección sobre la muestra final",
            code="HO-009",
            state=status()["state"],
        )
