"""Launch a round's hyperparameter sweep and pick the winner on dev.

Veri allows four training jobs at once. Every config is scored on that round's
train sample and on its dev split. The frozen test set is scored only for the
winner. The selection score is trick F1 minus the clean-page false-block rate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from guardtrain.budget import assert_jobs_fit
from guardtrain.continuation import dpo_init
from guardtrain.data import dev_preference_rows, dpo_records, write_jsonl
from guardtrain.ledger import (
    SpendCapExceeded,
    SpendLedger,
    reserve_for_job,
    shared_veri_ledger_path,
    wall_clock_reservation_usd,
)
from guardtrain.round_eval import pending_evals, summarize_metrics
from guardtrain.round_run import (
    RoundOptions,
    _download_checkpoint,
    _learning_rate,
    _sha8,
    _write_report,
    dpo_already_used,
    merge_command,
    prepare_round,
    redact_error,
    resolve_wall_and_steps,
)
from guardtrain.schema import VERI_HARD_CAP_USD, ContractError, guard_model_name, hf_repo_name
from guardtrain.selection import pick_winner, trick_scores
from guardtrain.sweepcfg import assert_private_huggingface, expand_trials, load_sweep_config, parallel_limit
from guardtrain.tomlutil import (
    STEP_SECONDS_BUDGET,
    observed_step_seconds,
    render_train_toml,
    steps_for_wall,
    write_toml,
)
from guardtrain.veri import (
    POLL_FAILURES_BEFORE_CANCEL,
    QUEUED_STATUSES,
    TERMINAL_STATUSES,
    SubprocessVeri,
    SystemClock,
    VeriCLIError,
    _POLL_ERRORS,
    classify_checkpoint,
    fetch_metrics,
    plan_commands,
    settle_amount,
)


@dataclass
class _Job:
    trial: dict
    job_id: str
    entry_id: str
    reserved: Decimal
    checkpoint_dir: Path
    queue_started: float
    run_started: float | None = None
    failures: int = 0
    handled: bool = False
    view: dict | None = None


def trial_public_scores(metrics: dict) -> dict:
    summary = summarize_metrics(metrics)
    summary.update(trick_scores(metrics))
    return summary


def require_trial_model(report: dict, round_index: int, trial: str, model: str) -> dict:
    """One sweep-score call serves one trial. Two trials never share a model."""
    expected = guard_model_name(round_index, trial)
    if model != expected:
        raise ContractError(
            f"Trial {trial} is served as {expected}. Refusing to score it with {model}. "
            "Each sweep-score call needs --trial and --model for that one config."
        )
    found = _find_trial(report, trial)
    for other in report.get("trials") or []:
        if other.get("name") == trial:
            continue
        if other.get("served_model") == model:
            raise ContractError(
                f"{model} is already the served model for trial {other.get('name')}. "
                "Two trials cannot share a model."
            )
    found["served_model"] = model
    return found


def _find_trial(report: dict, name: str) -> dict:
    for trial in report.get("trials") or []:
        if trial.get("name") == name:
            return trial
    raise ContractError(f"Sweep has no trial named {name}.")


def refresh_winner(report: dict) -> str | None:
    """Pick from dev scores once every finished trial has one. Never reads the test set."""
    for trial in report.get("trials") or []:
        trial.pop("testset", None)
        trial.pop("slice100", None)
    waiting = [
        trial
        for trial in report.get("trials") or []
        if trial.get("selection_score") is None and trial.get("status") in {"completed", "downloaded", "scored"}
    ]
    if waiting:
        winner = None
    else:
        winner = pick_winner(report.get("trials") or [])
    report["winner"] = winner
    evals = report.get("evals")
    if isinstance(evals, dict) and evals.get("winner") != winner:
        had_test = "testset" in evals
        evals.pop("testset", None)
        evals.pop("slice100", None)
        evals["winner"] = winner
        if winner is None or had_test:
            evals["status"] = "pending"
    report["selection"] = {
        "metric": "trick_f1 - false_block_rate_clean",
        "picked_from": "dev",
        "note": (
            "Winner is the highest dev selection score. "
            "A higher trick F1 loses when it false-blocks more clean dev pages. "
            "The frozen test set is scored only for the winner."
        ),
    }
    _stamp_winner_repo(report)
    return report.get("winner")


def _stamp_winner_repo(report: dict) -> None:
    """The round log records the winner's private merged repo once dev has picked it."""
    name = report.get("winner")
    if not name:
        return
    try:
        trial = _find_trial(report, name)
    except ContractError:
        return
    if trial.get("hf_repo"):
        report["hf_repo"] = trial["hf_repo"]
    if trial.get("hf_repo_url"):
        report["hf_repo_url"] = trial["hf_repo_url"]
        report["hf_pushed"] = bool(trial.get("hf_pushed"))


def assign_trial_scores(report: dict, name: str, train_metrics: dict, dev_metrics: dict) -> None:
    """Record train-sample and dev scores. This does not write a test score."""
    trial = _find_trial(report, name)
    trial.pop("testset", None)
    trial.pop("slice100", None)
    trial["train_sample"] = trial_public_scores(train_metrics)
    dev = trial_public_scores(dev_metrics)
    trial["dev"] = dev
    trial["dev_pages"] = list(dev_metrics.get("pages") or [])
    trial["selection_score"] = dev["selection_score"]
    trial["false_block_rate_clean"] = dev["false_block_rate_clean"]
    trial["trick_f1"] = dev["trick_f1"]
    if trial.get("status") in {None, "pending", "completed", "downloaded"}:
        trial["status"] = "scored"
    refresh_winner(report)


def attach_winner_test(report: dict, test_metrics: dict, slice_metrics: dict | None = None) -> None:
    """Score the frozen test set for the dev winner and for nobody else."""
    winner = refresh_winner(report)
    if not winner:
        raise ContractError(
            "Refusing to score the test set: dev scores have not picked a winner yet."
        )
    trial = _find_trial(report, winner)
    trial["testset"] = summarize_metrics(test_metrics)
    if slice_metrics is not None:
        trial["slice100"] = summarize_metrics(slice_metrics)
    others = [item["name"] for item in report["trials"] if item["name"] != winner and "testset" in item]
    if others:
        raise ContractError(f"Test scores leaked onto non-winners: {others}")
    evals = report.setdefault("evals", {})
    evals["status"] = "scored"
    evals["winner"] = winner
    evals["testset"] = trial["testset"]
    evals["slice100"] = trial.get("slice100")
    evals["trials"] = {
        item["name"]: {
            "train_sample": item.get("train_sample"),
            "dev": item.get("dev"),
        }
        for item in report["trials"]
    }
    evals["note"] = (
        "Every config has train-sample and dev scores. "
        "testset and slice100 are the winner only."
    )


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def poll_wave(executor, jobs: list[_Job], *, opts: RoundOptions, clock) -> None:
    """Poll every job in the wave. Cancel a job that hits the queue limit, the wall, or a dead poller."""
    while any(not job.handled for job in jobs):
        for job in jobs:
            if job.handled:
                continue
            try:
                view = executor.jobs_get(job.job_id)
                job.failures = 0
                job.view = view
            except _POLL_ERRORS as exc:
                job.failures += 1
                if job.failures >= POLL_FAILURES_BEFORE_CANCEL:
                    _cancel_job(executor, job, "poll_failed", str(exc))
                continue
            status = str(view.get("status") or "")
            now = clock.time()
            if status not in QUEUED_STATUSES and status not in TERMINAL_STATUSES and job.run_started is None:
                job.run_started = now
            if status in TERMINAL_STATUSES:
                job.handled = True
                continue
            if job.run_started is None and (now - job.queue_started) >= opts.max_queue_minutes * 60:
                _cancel_job(executor, job, "queue_timeout", "")
                continue
            if job.run_started is not None and (now - job.run_started) >= opts.max_wall_minutes * 60:
                _cancel_job(executor, job, "wall_clock", "")
        if any(not job.handled for job in jobs):
            clock.sleep(opts.poll_seconds)


def _cancel_job(executor, job: _Job, reason: str, detail: str) -> None:
    try:
        executor.jobs_cancel(job.job_id)
    except Exception:
        pass
    try:
        view = executor.jobs_get(job.job_id)
    except _POLL_ERRORS:
        view = dict(job.view or {"id": job.job_id, "status": "cancelled", "cost_usd": None})
    view["cancelled_by"] = reason
    if detail:
        view["error_message"] = redact_error(VeriCLIError(detail))
    job.view = view
    job.handled = True


def _blank_trial(spec: dict, *, dry_run: bool) -> dict:
    return {
        "name": spec["name"],
        "learning_rate": spec["learning_rate"],
        "lora_rank": spec["lora_rank"],
        "lora_alpha": spec["lora_alpha"],
        "job_id": None,
        "status": "dry_run" if dry_run else "pending",
        "would_reserve_usd": None,
        "cost_usd": None,
        "checkpoint": None,
        "train_sample": None,
        "dev": None,
        "selection_score": None,
        "false_block_rate_clean": None,
        "trick_f1": None,
        "hf_repo": None,
        "hf_repo_url": None,
        "hf_pushed": False,
        "served_model": None,
        "step_seconds": None,
    }


def _row_group(row) -> str:
    extra = getattr(row, "extra", None) or {}
    gid = extra.get("group_id")
    if gid:
        return str(gid)
    return f"page:{row.page_id}"


def _pair_and_judge(dev_rows, error_rows):
    """Keep error groups as pairs. Judge on a disjoint set of dev groups.

    Groups with no errors are the judge split, so a miss stays available as a
    pair. When every group has an error, one group is held out as the judge.
    """
    error_ids = {row.page_id for row in error_rows}
    groups: dict[str, list] = {}
    for row in dev_rows:
        groups.setdefault(_row_group(row), []).append(row)
    error_groups = []
    quiet_groups = []
    for key, rows in groups.items():
        if any(row.page_id in error_ids for row in rows):
            error_groups.append(key)
        else:
            quiet_groups.append(key)
    if quiet_groups and error_groups:
        judge_keys = set(quiet_groups)
        pair_keys = set(error_groups)
    elif len(error_groups) >= 2:
        ordered = sorted(error_groups)
        judge_keys = {ordered[-1]}
        pair_keys = set(ordered[:-1])
    else:
        return None
    pairs = [row for row in error_rows if _row_group(row) in pair_keys]
    judge = [row for row in dev_rows if _row_group(row) in judge_keys]
    pair_ids = {row.page_id for row in pairs}
    judge_ids = {row.page_id for row in judge}
    if not pairs or not judge or pair_ids & judge_ids:
        return None
    return pairs, judge


def _render_trial_toml(
    opts: RoundOptions,
    trial: dict,
    *,
    dataset_id: str,
    toml_path: Path,
    max_steps: int,
    hf_repo: str,
) -> None:
    text = render_train_toml(
        output_model=guard_model_name(opts.round_index, trial["name"]),
        base_model=opts.base_model,
        dataset_id=dataset_id,
        method="sft_text",
        learning_rate=_learning_rate("sft_text", trial["learning_rate"]),
        max_steps=max_steps,
        hf_repo=hf_repo,
        num_epochs=opts.epochs,
        max_seq_length=opts.max_seq_length,
        lora_rank=trial["lora_rank"],
        lora_alpha=trial["lora_alpha"],
        grad_accum=opts.grad_accum,
    )
    write_toml(toml_path, text)


def _build_dpo_report(
    opts: RoundOptions,
    report: dict,
    dev_rows,
    test_ids: set[str],
    *,
    launch: bool,
    executor,
    ledger: SpendLedger,
    clock,
    metrics_fetcher,
) -> None:
    """Pairs from the winner's dev false blocks and dev misses. Never test pages."""
    if dpo_already_used(opts.runs) and not opts.dry_run:
        report["dpo"] = {
            "status": "refused",
            "note": "DPO is limited to one live round. A previous round already used it.",
        }
        return
    winner_name = report.get("winner")
    if not winner_name:
        report["dpo"] = {
            "status": "pending_winner",
            "source": "dev false blocks and dev misses only",
            "note": (
                "Pairs are built from the winner's dev false blocks and dev misses. "
                "Test pages are not used. DPO starts from this round's private merged SFT winner."
            ),
        }
        return
    winner = _find_trial(report, winner_name)
    pages = winner.get("dev_pages") or []
    rows = [
        row
        for row in dev_preference_rows(dev_rows, {"pages": pages})
        if row.page_id not in test_ids and row.page_set not in {"testset", "slice100", "test", "frozen"}
    ]
    split = _pair_and_judge(dev_rows, rows)
    path = opts.runs / "training" / "datasets" / f"round{opts.round_index}.dpo.jsonl"
    judge_path = opts.runs / "training" / "datasets" / f"round{opts.round_index}.dpo.judge.jsonl"
    if split is None:
        report["dpo"] = {
            "status": "refused_no_judge",
            "pairs": 0,
            "source": "dev false blocks and dev misses only",
            "note": (
                "DPO needs a fresh dev split that the pairs did not train on. "
                "This round could not hold a nonempty judge group out of the error groups."
            ),
            "job_id": None,
        }
        return
    pair_rows, judge_rows = split
    records = dpo_records(
        pair_rows,
        max_page_tokens=opts.max_page_tokens,
        system_in_user=opts.system_in_user,
        hide_held_out_labels=opts.hide_held_out_labels,
    )
    write_jsonl(path, records)
    write_jsonl(judge_path, [row.as_dict() for row in judge_rows])
    base, how = dpo_init(winner, opts.round_index, winner_name)
    payload = {
        "status": "pairs_ready" if records else "no_pairs",
        "pairs": len(records),
        "path": str(path),
        "judge_path": str(judge_path),
        "judge_rows": len(judge_rows),
        "base_model": base,
        "init": how,
        "hf_repo": hf_repo_name(opts.round_index, f"{winner_name}-dpo"),
        "source": "dev false blocks and dev misses only",
        "job_id": None,
    }
    report["dpo"] = payload
    if not launch or not records or opts.dry_run:
        return
    _launch_dpo_job(
        opts,
        report,
        records,
        path,
        base,
        executor=executor,
        ledger=ledger,
        clock=clock,
        metrics_fetcher=metrics_fetcher,
    )


def launch_pending_dpo(
    opts: RoundOptions,
    report: dict,
    dev_rows,
    test_ids: set[str],
    *,
    executor=None,
    ledger: SpendLedger | None = None,
    clock=None,
    metrics_fetcher=None,
) -> dict:
    """Start the one DPO job after dev scores have named a winner.

    A sweep downloads several adapters before any of them can be served, so
    the winner is often chosen later by ``sweep-score``. This builds pairs
    from that winner's dev false blocks and dev misses and, unless
    ``opts.dry_run``, submits one DPO job.
    """
    if not report.get("winner"):
        refresh_winner(report)
    if not report.get("winner"):
        raise ContractError("Dev scores have not picked a winner yet. DPO is not launched.")
    current = report.get("dpo") or {}
    if current.get("job_id") or current.get("status") in {"launched", "completed", "running"}:
        raise ContractError("This round already launched DPO.")
    ledger = ledger or SpendLedger(
        shared_veri_ledger_path(),
        VERI_HARD_CAP_USD,
        quant="cents",
    )
    _build_dpo_report(
        opts,
        report,
        dev_rows,
        test_ids,
        launch=not opts.dry_run,
        executor=executor,
        ledger=ledger,
        clock=clock or SystemClock(),
        metrics_fetcher=metrics_fetcher or fetch_metrics,
    )
    _write_report(opts.runs, opts.round_index, report)
    return report


def _launch_dpo_job(
    opts: RoundOptions,
    report: dict,
    records: list[dict],
    path: Path,
    base: str,
    *,
    executor,
    ledger: SpendLedger,
    clock,
    metrics_fetcher,
) -> None:
    dpo_wall, _planned_steps = resolve_wall_and_steps(opts, max(1, len(records)))
    wall = wall_clock_reservation_usd(dpo_wall, gpu_count=1)
    try:
        balance = executor.billing_balance()
        assert_jobs_fit(
            ledger=ledger,
            spend_cap=opts.spend_cap,
            reservations=[wall],
            balance=balance,
            require_balance=True,
        )
    except Exception as exc:
        report["dpo"]["status"] = "refused_budget"
        report["dpo"]["note"] = redact_error(exc)
        return
    if not os.environ.get("VERI_API_KEY"):
        report["dpo"]["status"] = "refused"
        report["dpo"]["note"] = "VERI_API_KEY is not set."
        return
    try:
        executor.datasets_check(path)
        dataset_id = executor.datasets_upload(path, f"guard-dpo-r{opts.round_index}-{_sha8(path)}")
    except VeriCLIError as exc:
        report["dpo"]["status"] = "upload_failed"
        report["dpo"]["note"] = str(exc)
        return
    winner = _find_trial(report, report["winner"])
    rank = int(winner.get("lora_rank") or opts.lora_rank)
    alpha = int(winner.get("lora_alpha") or rank * 2)
    dpo_wall, max_steps = resolve_wall_and_steps(opts, len(records))
    toml_path = opts.runs / "training" / "configs" / f"round{opts.round_index}.dpo.toml"
    dpo_repo = str(report["dpo"].get("hf_repo") or hf_repo_name(opts.round_index, f"{report['winner']}-dpo"))
    write_toml(
        toml_path,
        render_train_toml(
            output_model=guard_model_name(opts.round_index, f"{report['winner']}-dpo"),
            base_model=base,
            dataset_id=dataset_id,
            method="dpo",
            learning_rate=_learning_rate("dpo", None),
            max_steps=max_steps,
            hf_repo=dpo_repo,
            max_seq_length=opts.max_seq_length,
            lora_rank=rank,
            lora_alpha=alpha,
            grad_accum=opts.grad_accum,
        ),
    )
    estimate = executor.jobs_estimate(toml_path)
    estimate_usd = None
    rate = None
    if estimate.get("estimated_cost_usd") is not None:
        estimate_usd = Decimal(str(estimate["estimated_cost_usd"]))
    if estimate.get("rate_usd_per_hour") is not None:
        rate = Decimal(str(estimate["rate_usd_per_hour"]))
    wall_live = wall_clock_reservation_usd(
        dpo_wall,
        gpu_count=int(estimate.get("gpu_count") or 1),
        hourly_rate=rate if rate is not None else Decimal("1.05"),
    )
    reserved = reserve_for_job(estimate_usd, wall_live)
    try:
        balance = executor.billing_balance()
        assert_jobs_fit(
            ledger=ledger,
            spend_cap=opts.spend_cap,
            reservations=[reserved],
            balance=balance,
            require_balance=True,
        )
    except Exception as exc:
        report["dpo"]["status"] = "refused_budget"
        report["dpo"]["note"] = redact_error(exc)
        return
    entry_id = ledger.authorize(reserved, note=f"round {opts.round_index} dpo", requested_cap=opts.spend_cap)
    try:
        job_id = executor.jobs_create(toml_path)
    except VeriCLIError as exc:
        ledger.release(entry_id, note="dpo create failed before a job id")
        report["dpo"]["status"] = "create_failed"
        report["dpo"]["note"] = str(exc)
        return
    ledger.attach_job(entry_id, job_id)
    job = _Job(
        trial=report["dpo"],
        job_id=job_id,
        entry_id=entry_id,
        reserved=reserved,
        checkpoint_dir=opts.runs / "training" / "checkpoints" / f"round{opts.round_index}-dpo",
        queue_started=clock.time(),
    )
    opts.max_wall_minutes = dpo_wall
    try:
        poll_wave(executor, [job], opts=opts, clock=clock)
    finally:
        if not job.handled:
            _cancel_job(executor, job, "poll_failed", "dpo watcher stopped")
    view = job.view or {"status": "unknown", "cost_usd": None}
    actual, confidence = settle_amount(view, reserved)
    ledger.settle(entry_id, actual, job_id=job_id)
    report["dpo"]["job_id"] = job_id
    report["dpo"]["status"] = view.get("status")
    report["dpo"]["cost_usd"] = format(actual, "f")
    report["dpo"]["cost_confidence"] = confidence
    try:
        saved = _download_checkpoint(executor, job_id, view, job.checkpoint_dir)
        report["dpo"]["checkpoint"] = {"dir": str(job.checkpoint_dir), "saved": saved}
        if saved != "none":
            report["dpo"]["checkpoint"]["kind"] = classify_checkpoint(job.checkpoint_dir)
    except VeriCLIError as exc:
        report["dpo"]["download_error"] = str(exc)
    try:
        report["dpo"]["loss_curve"] = metrics_fetcher(job_id)
    except VeriCLIError:
        report["dpo"]["loss_curve"] = []


def run_sweep(
    opts: RoundOptions,
    config_path: Path,
    *,
    executor: SubprocessVeri | None = None,
    ledger: SpendLedger | None = None,
    clock: SystemClock | None = None,
    metrics_fetcher=None,
    score_fn=None,
    score_test_fn=None,
    test_rows=None,
    slice_rows=None,
) -> dict:
    """Prepare one grouped round, then launch the sweep.

    ``score_fn(trial_name, rows)`` scores the train sample and the dev split.
    ``score_test_fn(trial_name, rows)`` is called only with the winner's name.
    """
    if Decimal(opts.spend_cap) > Decimal(VERI_HARD_CAP_USD):
        raise SpendCapExceeded(
            f"Refusing spend cap ${opts.spend_cap} above the ${VERI_HARD_CAP_USD} Veri hard cap.",
            spent=Decimal("0"),
            attempted=Decimal(opts.spend_cap),
            cap=Decimal(VERI_HARD_CAP_USD),
        )
    config = load_sweep_config(config_path)
    assert_private_huggingface(config)
    if config.get("spend_cap") is not None:
        opts.spend_cap = str(config["spend_cap"])
        if Decimal(opts.spend_cap) > Decimal(VERI_HARD_CAP_USD):
            raise SpendCapExceeded(
                f"Sweep spend_cap ${opts.spend_cap} is above the ${VERI_HARD_CAP_USD} hard cap.",
                spent=Decimal("0"),
                attempted=Decimal(opts.spend_cap),
                cap=Decimal(VERI_HARD_CAP_USD),
            )
    specs = expand_trials(config)
    limit = parallel_limit(config)
    if opts.dpo:
        raise ContractError("Pass dpo: true in the sweep config. The SFT sweep itself is not a DPO job.")
    prepared = prepare_round(opts)
    records = prepared["records"]
    wall_minutes, max_steps = resolve_wall_and_steps(opts, len(records))
    opts.max_wall_minutes = wall_minutes
    trials = [_blank_trial(spec, dry_run=opts.dry_run) for spec in specs]
    dataset_name = f"guard-sft_text-r{opts.round_index}-{_sha8(prepared['payload_path'])}"
    configs = opts.runs / "training" / "configs"
    for trial in trials:
        trial["hf_repo"] = hf_repo_name(opts.round_index, trial["name"])
        trial["served_model"] = guard_model_name(opts.round_index, trial["name"])
        _render_trial_toml(
            opts,
            trial,
            dataset_id=dataset_name,
            toml_path=configs / f"round{opts.round_index}.{trial['name']}.toml",
            max_steps=max_steps,
            hf_repo=trial["hf_repo"],
        )
    wall = wall_clock_reservation_usd(wall_minutes, gpu_count=1)
    ledger = ledger or SpendLedger(
        shared_veri_ledger_path(),
        VERI_HARD_CAP_USD,
        quant="cents",
    )
    # Ledger only. A dry-run has no live balance to read.
    assert_jobs_fit(
        ledger=ledger,
        spend_cap=opts.spend_cap,
        reservations=[wall for _ in trials],
        balance=None,
        require_balance=False,
    )
    first_toml = configs / f"round{opts.round_index}.{trials[0]['name']}.toml"
    first_dir = opts.runs / "training" / "checkpoints" / f"round{opts.round_index}" / trials[0]["name"]
    report = {
        "schema_version": 1,
        "round": opts.round_index,
        "method": "sft_text",
        "sweep": True,
        "dry_run": opts.dry_run,
        "winner": None,
        "base_model": prepared["base_model"],
        "max_parallel": limit,
        "parallel_cap": 4,
        "trials": trials,
        "groups": prepared["groups"],
        "structure": prepared["structure"],
        "continuation": prepared["continuation"],
        "dataset": {
            "payload": str(prepared["payload_path"]),
            "uploaded_rows": len(records),
            "mix": prepared["stats"].as_dict(),
            "dev_rows": len(prepared["dev_rows"]),
            "attacker_rows_in_train": len(prepared["attacker_rows"]),
            "attacker_groups_held_out": prepared["held_out_attacker"],
            "policy": (
                "One fresh grouped train/dev split for the round. "
                "Every sweep config trains on that train mix. Dev groups are held out."
            ),
        },
        "splits": {
            "train": str(prepared["datasets"] / f"round{opts.round_index}.train.jsonl"),
            "dev": str(prepared["datasets"] / f"round{opts.round_index}.dev.jsonl"),
            "testset": str(prepared["testset_labels"]),
            "slice": str(prepared["slice_file"]),
        },
        "evals": pending_evals(
            train_rows=prepared["fresh_for_sample"],
            dev_rows=prepared["dev_rows"],
            sample_ids=[row.page_id for row in prepared["train_sample"]],
            testset_labels=str(prepared["testset_labels"]) if prepared["testset_labels"].is_file() else None,
            slice_file=str(prepared["slice_file"]) if prepared["slice_file"].is_file() else None,
            content_hash=prepared["testset_hash"],
        ),
        "limits": {
            "max_wall_minutes": wall_minutes,
            "max_steps": max_steps,
            "epochs": opts.epochs,
            "steps_allowed_by_wall": steps_for_wall(wall_minutes),
            "step_seconds_budget": STEP_SECONDS_BUDGET,
            "spend_cap_usd": opts.spend_cap,
            "hard_cap_usd": VERI_HARD_CAP_USD,
            "max_parallel": limit,
            "jobs": len(trials),
        },
        "commands": plan_commands(
            dataset_path=prepared["payload_path"],
            dataset_name=dataset_name,
            toml_path=first_toml,
            checkpoint_dir=first_dir,
            merge_command=merge_command(first_dir, opts.base_model),
        ),
        "budget": {
            "projected_jobs": len(trials),
            "projected_each_usd": format(wall, "f"),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    report["commands"] = ["veri billing balance --format json", *report["commands"]]
    if opts.dry_run:
        if config.get("dpo"):
            _build_dpo_report(
                opts,
                report,
                prepared["dev_rows"],
                prepared["test_ids"],
                launch=False,
                executor=executor,
                ledger=ledger,
                clock=clock or SystemClock(),
                metrics_fetcher=metrics_fetcher or fetch_metrics,
            )
        else:
            report["dpo"] = {"status": "off"}
        refresh_winner(report)
        _write_report(opts.runs, opts.round_index, report)
        return report

    if len(records) < opts.min_rows:
        raise ContractError(
            f"Refusing to launch round {opts.round_index}: {len(records)} trainable rows "
            f"is below the minimum of {opts.min_rows}."
        )
    if not os.environ.get("VERI_API_KEY"):
        raise VeriCLIError("VERI_API_KEY is not set. Export it in the shell that launches the job.")

    executor = executor or SubprocessVeri()
    clock = clock or SystemClock()
    metrics_fetcher = metrics_fetcher or fetch_metrics
    executor.datasets_check(prepared["payload_path"])
    dataset_id = executor.datasets_upload(prepared["payload_path"], dataset_name)
    reservations: list[Decimal] = []
    for trial in trials:
        toml_path = configs / f"round{opts.round_index}.{trial['name']}.toml"
        _render_trial_toml(
            opts,
            trial,
            dataset_id=dataset_id,
            toml_path=toml_path,
            max_steps=max_steps,
            hf_repo=trial["hf_repo"],
        )
        estimate = executor.jobs_estimate(toml_path)
        estimate_usd = None
        rate = None
        if estimate.get("estimated_cost_usd") is not None:
            estimate_usd = Decimal(str(estimate["estimated_cost_usd"]))
        if estimate.get("rate_usd_per_hour") is not None:
            rate = Decimal(str(estimate["rate_usd_per_hour"]))
        wall_live = wall_clock_reservation_usd(
            wall_minutes,
            gpu_count=int(estimate.get("gpu_count") or 1),
            hourly_rate=rate if rate is not None else Decimal("1.05"),
        )
        reserved = reserve_for_job(estimate_usd, wall_live)
        trial["would_reserve_usd"] = format(reserved, "f")
        reservations.append(reserved)
    balance = executor.billing_balance()
    report["budget"] = assert_jobs_fit(
        ledger=ledger,
        spend_cap=opts.spend_cap,
        reservations=reservations,
        balance=balance,
        require_balance=True,
    )
    # The check above is the whole sweep. Jobs are created only after it passes.
    created: list[tuple[dict, Decimal, Path]] = []
    for trial, reserved in zip(trials, reservations):
        toml_path = configs / f"round{opts.round_index}.{trial['name']}.toml"
        checkpoint_dir = opts.runs / "training" / "checkpoints" / f"round{opts.round_index}" / trial["name"]
        created.append((trial, reserved, checkpoint_dir))

    for wave_index, wave in enumerate(_chunks(created, limit)):
        if wave_index:
            balance = executor.billing_balance()
            assert_jobs_fit(
                ledger=ledger,
                spend_cap=opts.spend_cap,
                reservations=[amount for _trial, amount, _path in wave],
                balance=balance,
                require_balance=True,
            )
        jobs: list[_Job] = []
        for trial, reserved, checkpoint_dir in wave:
            toml_path = configs / f"round{opts.round_index}.{trial['name']}.toml"
            balance = executor.billing_balance()
            assert_jobs_fit(
                ledger=ledger,
                spend_cap=opts.spend_cap,
                reservations=[reserved],
                balance=balance,
                require_balance=True,
            )
            entry_id = ledger.authorize(
                reserved,
                note=f"round {opts.round_index} sweep {trial['name']}",
                requested_cap=opts.spend_cap,
            )
            try:
                job_id = executor.jobs_create(toml_path)
            except VeriCLIError as exc:
                ledger.release(entry_id, note="create failed before a job id")
                trial["status"] = "create_failed"
                trial["error_message"] = str(exc)
                continue
            ledger.attach_job(entry_id, job_id)
            trial["job_id"] = job_id
            trial["status"] = "running"
            jobs.append(
                _Job(
                    trial=trial,
                    job_id=job_id,
                    entry_id=entry_id,
                    reserved=reserved,
                    checkpoint_dir=checkpoint_dir,
                    queue_started=clock.time(),
                )
            )
        if not jobs:
            continue
        try:
            poll_wave(executor, jobs, opts=opts, clock=clock)
        finally:
            for job in jobs:
                if not job.handled:
                    _cancel_job(executor, job, "poll_failed", "sweep watcher stopped")
        for job in jobs:
            view = job.view or {"status": "unknown", "cost_usd": None}
            actual, confidence = settle_amount(view, job.reserved)
            ledger.settle(job.entry_id, actual, job_id=job.job_id)
            job.trial["status"] = view.get("status")
            job.trial["cancelled_by"] = view.get("cancelled_by")
            job.trial["cost_usd"] = format(actual, "f")
            job.trial["cost_confidence"] = confidence
            try:
                job.trial["loss_curve"] = metrics_fetcher(job.job_id)
            except VeriCLIError as exc:
                job.trial["loss_curve"] = []
                job.trial["metrics_error"] = str(exc)
            pushed_url = str(view.get("hf_repo_url") or "")
            if view.get("status") == "completed" and pushed_url:
                job.trial["hf_repo_url"] = pushed_url
                job.trial["hf_pushed"] = True
            job.trial["step_seconds"] = observed_step_seconds(
                job.trial.get("loss_curve"),
                run_started=job.run_started,
                finished=clock.time(),
                steps=max_steps,
            )
            try:
                saved = _download_checkpoint(executor, job.job_id, view, job.checkpoint_dir)
            except VeriCLIError as exc:
                job.trial["download_error"] = str(exc)
                saved = "none"
            job.trial["checkpoint"] = {
                "dir": str(job.checkpoint_dir),
                "saved": saved,
                "kind": None if saved == "none" else classify_checkpoint(job.checkpoint_dir),
            }
            if saved != "none" and job.trial["status"] == "completed":
                job.trial["status"] = "downloaded"
        _write_report(opts.runs, opts.round_index, report)

    if score_fn is not None:
        for trial in trials:
            if trial.get("status") not in {"downloaded", "completed", "scored"}:
                continue
            train_metrics = score_fn(trial["name"], prepared["train_sample"])
            dev_metrics = score_fn(trial["name"], prepared["dev_rows"])
            assign_trial_scores(report, trial["name"], train_metrics, dev_metrics)
        winner = report.get("winner")
        if winner and score_test_fn is not None:
            test_metrics = score_test_fn(winner, list(test_rows or []))
            slice_metrics = None
            if slice_rows:
                slice_metrics = score_test_fn(winner, list(slice_rows))
            attach_winner_test(report, test_metrics, slice_metrics)
        _write_report(opts.runs, opts.round_index, report)

    if config.get("dpo"):
        _build_dpo_report(
            opts,
            report,
            prepared["dev_rows"],
            prepared["test_ids"],
            launch=True,
            executor=executor,
            ledger=ledger,
            clock=clock,
            metrics_fetcher=metrics_fetcher,
        )
        _write_report(opts.runs, opts.round_index, report)
    else:
        report["dpo"] = {"status": "off"}
        _write_report(opts.runs, opts.round_index, report)
    return report
