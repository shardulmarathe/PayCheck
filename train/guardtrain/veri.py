"""Veri CLI wrapper: estimate, launch, poll with a hard cancel, download.

There is no submit-time wall-clock field. The platform running-time limit is
24 hours. This module cancels the job itself when ``--max-wall-minutes`` elapses
after the job leaves ``queued``. ``veri jobs download`` returns the HF checkpoint.
For QLoRA that checkpoint is the adapter (``adapter_model.safetensors``);
merging is a separate local step.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable, Protocol

import httpx

from guardtrain.redact import redact
from guardtrain.schema import CHECKPOINT_STORAGE_USD

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "canceled", "error"})
QUEUED_STATUSES = frozenset({"queued", "pending"})

MetricsFetcher = Callable[[str], list[dict]]


class VeriCLIError(Exception):
    pass


class Clock(Protocol):
    def time(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def time(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class Completed:
    returncode: int
    stdout: str
    stderr: str


def default_runner(args: list[str], timeout: float) -> Completed:
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=timeout,
        check=False,
    )
    return Completed(proc.returncode, proc.stdout or "", proc.stderr or "")


def parse_json_value(stdout: str) -> dict | list:
    text = stdout.strip()
    if not text:
        raise VeriCLIError("veri returned empty stdout")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Some builds print a log line before the JSON document.
        obj_start = text.find("{")
        list_start = text.find("[")
        starts = [pos for pos in (obj_start, list_start) if pos >= 0]
        if not starts:
            raise VeriCLIError("veri stdout was not JSON") from None
        start = min(starts)
        end = text.rfind("}" if text[start] == "{" else "]")
        if end <= start:
            raise VeriCLIError("veri stdout was not JSON") from None
        try:
            obj = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise VeriCLIError("veri stdout was not JSON") from exc
    if not isinstance(obj, (dict, list)):
        raise VeriCLIError("veri JSON stdout was not an object or list")
    return obj


def parse_json_stdout(stdout: str) -> dict:
    obj = parse_json_value(stdout)
    if not isinstance(obj, dict):
        raise VeriCLIError("veri JSON stdout was not an object")
    return obj


def _step_from_checkpoint_id(checkpoint_id: str) -> int | None:
    if "@" not in checkpoint_id:
        return None
    tail = checkpoint_id.rsplit("@", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return None


def newest_checkpoint_id(payload: object, job_id: str) -> str | None:
    """Pick the newest checkpoint from ``veri checkpoints list``.

    The documented list is newest-step first. A numeric ``step`` wins when
    present; otherwise the first id is used.
    """
    if isinstance(payload, dict):
        items = payload.get("checkpoints") or payload.get("data") or payload.get("items")
        if items is None and (payload.get("id") or payload.get("checkpoint_id")):
            items = [payload]
        if items is None:
            items = []
    elif isinstance(payload, list):
        items = payload
    else:
        return None
    best_id: str | None = None
    best_step = -1
    first_id: str | None = None
    for item in items:
        step: int | None
        if isinstance(item, str):
            cid = item
            step = _step_from_checkpoint_id(cid)
        elif isinstance(item, dict):
            cid = str(item.get("id") or item.get("checkpoint_id") or "")
            raw_step = item.get("step")
            if isinstance(raw_step, int):
                step = raw_step
            elif isinstance(raw_step, str) and raw_step.isdigit():
                step = int(raw_step)
            else:
                step = _step_from_checkpoint_id(cid)
        else:
            continue
        if not cid:
            continue
        if first_id is None:
            first_id = cid
        if step is None:
            continue
        if step >= best_step:
            best_step = step
            best_id = cid
    if best_id:
        return best_id
    if first_id:
        return first_id
    return None


def extract_id(payload: dict, *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    nested = payload.get("dataset") or payload.get("job") or payload.get("data")
    if isinstance(nested, dict):
        for key in keys:
            value = nested.get(key)
            if value:
                return str(value)
    raise VeriCLIError("veri JSON did not include an id")


def parse_balance(payload: dict) -> Decimal:
    """Read ``balance_usd`` from ``veri billing balance``."""
    if not isinstance(payload, dict):
        raise VeriCLIError("veri billing balance did not return a JSON object")
    for key in ("balance_usd", "available_usd", "credit_balance_usd", "remaining_usd"):
        value = payload.get(key)
        if value is not None and not isinstance(value, dict):
            return Decimal(str(value))
    for key in ("billing", "data"):
        inner = payload.get(key)
        if isinstance(inner, dict) and inner is not payload:
            try:
                return parse_balance(inner)
            except VeriCLIError:
                continue
    raise VeriCLIError("veri billing balance JSON did not include balance_usd")


def extract_cost(payload: dict) -> Decimal | None:
    for key in ("cost_usd", "billed_cost_usd", "actual_cost_usd", "total_cost_usd", "cost"):
        if payload.get(key) is not None and not isinstance(payload.get(key), dict):
            return Decimal(str(payload[key]))
    for container_name in ("usage", "billing"):
        container = payload.get(container_name)
        if isinstance(container, dict):
            for key in ("cost_usd", "total_usd", "amount_usd", "cost"):
                if container.get(key) is not None:
                    return Decimal(str(container[key]))
    return None


def public_job_view(payload: dict) -> dict:
    error = payload.get("error") or {}
    if not isinstance(error, dict):
        error = {"message": str(error)}
    model = payload.get("model")
    base = payload.get("base_model")
    if not base and isinstance(model, dict):
        base = model.get("base")
    return {
        "id": str(payload.get("id") or payload.get("job_id") or ""),
        "status": str(payload.get("status") or "").lower(),
        "cost_usd": None if extract_cost(payload) is None else format(extract_cost(payload), "f"),
        "error_code": error.get("code"),
        "error_message": redact(str(error.get("message") or "")),
        "base_model": base,
    }


def loss_curve_from_metrics(payload: dict) -> list[dict]:
    points = []
    for point in payload.get("metrics") or []:
        if not isinstance(point, dict):
            continue
        values = point.get("values") if isinstance(point.get("values"), dict) else {}
        loss = None
        for key, value in values.items():
            if "loss" in str(key).lower() and isinstance(value, (int, float)):
                loss = value
                break
        recorded = {"step": point.get("step"), "loss": loss, "values": values}
        for key in ("timestamp", "created_at", "time"):
            if point.get(key) is not None:
                recorded[key] = point[key]
        points.append(recorded)
    return points


def fetch_metrics(job_id: str) -> list[dict]:
    """GET /v1/training_jobs/{id}/metrics. No ``veri jobs metrics`` command is documented."""
    key = os.environ.get("VERI_API_KEY", "")
    if not key:
        return []
    base = os.environ.get("VERI_API_URL", "https://api.veri.studio").rstrip("/")
    url = f"{base}/v1/training_jobs/{job_id}/metrics"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {key}"},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - the message is redacted before it is stored
        raise VeriCLIError(redact(f"metrics fetch failed: {exc}")) from None
    if not isinstance(payload, dict):
        return []
    return loss_curve_from_metrics(payload)


class SubprocessVeri:
    def __init__(self, runner: Callable[[list[str], float], Completed] | None = None):
        self._runner = runner or default_runner

    def _completed(self, args: list[str], timeout: float) -> Completed:
        # The API key stays in the environment. It is never placed in argv.
        completed = self._runner(["veri", *args], timeout)
        if completed.returncode != 0:
            detail = redact(completed.stderr or completed.stdout or "veri failed")
            raise VeriCLIError(detail)
        return completed

    def _run(self, args: list[str], timeout: float = 180) -> dict:
        completed = self._completed(args, timeout)
        try:
            return parse_json_stdout(completed.stdout)
        except VeriCLIError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise VeriCLIError(redact(str(exc))) from None

    def datasets_check(self, path: Path) -> None:
        # ``veri datasets check`` is a local validator. Success is the exit code.
        self._completed(["datasets", "check", str(path)], 180)

    def datasets_upload(self, path: Path, name: str) -> str:
        payload = self._run(
            ["datasets", "upload", str(path), "--name", name, "--format", "json"],
            timeout=600,
        )
        return extract_id(payload, "id", "dataset_id", "name")

    def billing_balance(self) -> Decimal:
        """Current workspace credit. Veri kills every running job when this hits $0."""
        payload = self._run(["billing", "balance", "--format", "json"], timeout=60)
        return parse_balance(payload)

    def jobs_estimate(self, toml_path: Path) -> dict:
        return self._run(["jobs", "estimate", str(toml_path), "--format", "json"])

    def jobs_create(self, toml_path: Path) -> str:
        payload = self._run(["jobs", "create", str(toml_path), "--format", "json"])
        return extract_id(payload, "id", "job_id")

    def jobs_get(self, job_id: str) -> dict:
        payload = self._run(["jobs", "get", job_id, "--format", "json"])
        view = public_job_view(payload)
        if not view["id"]:
            view["id"] = job_id
        return view

    def jobs_cancel(self, job_id: str) -> None:
        self._completed(["jobs", "cancel", job_id, "--format", "json"], 180)

    def jobs_download(self, job_id: str, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Download writes files. A non-JSON success message is still success.
        self._completed(
            ["jobs", "download", job_id, "--output-dir", str(output_dir)],
            3600,
        )

    def checkpoints_list(self, job_id: str) -> dict | list:
        completed = self._completed(["checkpoints", "list", job_id, "--format", "json"], 180)
        return parse_json_value(completed.stdout)

    def checkpoints_download(self, job_id: str, checkpoint_id: str, output_dir: Path) -> None:
        """Intermediate LoRA adapter. Final weights still use ``jobs download``."""
        output_dir.mkdir(parents=True, exist_ok=True)
        self._completed(
            [
                "checkpoints",
                "download",
                job_id,
                checkpoint_id,
                "--output",
                str(output_dir),
                "--artifact",
                "adapter",
            ],
            3600,
        )


POLL_FAILURES_BEFORE_CANCEL = 5
_POLL_ERRORS = (VeriCLIError, subprocess.TimeoutExpired, TimeoutError, OSError)


def poll_until_done(
    executor: SubprocessVeri,
    job_id: str,
    *,
    max_wall_minutes: float,
    max_queue_minutes: float,
    poll_seconds: float,
    clock: Clock,
) -> dict:
    """Poll ``veri jobs get``. Cancel on the queue limit, the wall clock, or a dead poller.

    The wall clock starts when the job first leaves ``queued``, which is when
    Veri starts billing (instance boot). Queue time is not billed if the job
    never gets a GPU. This poller does not send heartbeats.

    Transient ``jobs get`` failures retry with exponential backoff. After
    repeated failures, or any other fatal error, the job is cancelled before
    the exception propagates. A clean return does not cancel.
    """
    started = clock.time()
    run_started: float | None = None
    last: dict = {"id": job_id, "status": "unknown", "cost_usd": None}
    failures = 0
    # Set only after a clean return. The finally block is what cancels if the
    # watcher dies for any other reason, including a raised poll error.
    handled = False

    def finish_cancel(reason: str) -> dict:
        executor.jobs_cancel(job_id)
        try:
            view = executor.jobs_get(job_id)
        except _POLL_ERRORS:
            view = dict(last)
        view["cancelled_by"] = reason
        view["watcher_run_started"] = run_started
        view["watcher_finished"] = clock.time()
        return view

    try:
        while True:
            try:
                last = executor.jobs_get(job_id)
                failures = 0
            except _POLL_ERRORS as exc:
                failures += 1
                if failures >= POLL_FAILURES_BEFORE_CANCEL:
                    raise VeriCLIError(
                        redact(
                            f"veri jobs get failed {failures} times; cancel requested: {exc}"
                        )
                    ) from None
                delay = min(60.0, float(poll_seconds) * (2 ** (failures - 1)))
                clock.sleep(delay)
                continue
            status = last["status"]
            now = clock.time()
            if status not in QUEUED_STATUSES and status not in TERMINAL_STATUSES and run_started is None:
                run_started = now
            if status in TERMINAL_STATUSES:
                handled = True
                last["watcher_run_started"] = run_started
                last["watcher_finished"] = clock.time()
                return last
            queued_for = now - started
            if run_started is None and queued_for >= max_queue_minutes * 60:
                view = finish_cancel("queue_timeout")
                handled = True
                return view
            if run_started is not None and (now - run_started) >= max_wall_minutes * 60:
                view = finish_cancel("wall_clock")
                handled = True
                return view
            clock.sleep(poll_seconds)
    finally:
        if not handled:
            try:
                executor.jobs_cancel(job_id)
            except Exception:
                pass


def classify_checkpoint(path: Path) -> str:
    if not path.exists():
        return "missing"
    if any(path.rglob("adapter_config.json")):
        return "adapter"
    if any(path.rglob("model.safetensors")) or any(path.rglob("pytorch_model.bin")):
        return "full"
    return "unknown"


def plan_commands(
    *,
    dataset_path: Path,
    dataset_name: str,
    toml_path: Path,
    checkpoint_dir: Path,
    merge_command: str,
) -> list[str]:
    return [
        f"veri datasets check {dataset_path}",
        f"veri datasets upload {dataset_path} --name {dataset_name} --format json",
        f"veri jobs estimate {toml_path} --format json",
        f"veri jobs create {toml_path} --format json",
        "veri jobs get <job_id> --format json",
        "veri jobs cancel <job_id>",
        f"veri jobs download <job_id> --output-dir {checkpoint_dir}",
        "veri checkpoints list <job_id> --format json",
        f"veri checkpoints download <job_id> <ckpt> --output {checkpoint_dir} --artifact adapter",
        "GET /v1/training_jobs/<job_id>/metrics",
        merge_command,
    ]


def job_ran(view: dict) -> bool:
    if view.get("cancelled_by") == "queue_timeout":
        return False
    if view.get("status") in QUEUED_STATUSES:
        return False
    return True


def settle_amount(view: dict, reserved: Decimal) -> tuple[Decimal, str]:
    raw = view.get("cost_usd")
    if raw is not None:
        return Decimal(str(raw)), "actual"
    if not job_ran(view):
        return Decimal("0"), "unbilled_queue_cancel"
    # Unknown bill after the GPU booted. Keep the reservation so the cap stays honest.
    return reserved, "reserved_upper_bound"


def storage_note() -> str:
    return (
        f"Checkpoint storage is about ${CHECKPOINT_STORAGE_USD} on top of GPU time "
        "for every billed job. veri jobs estimate does not include it."
    )
