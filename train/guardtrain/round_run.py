"""Assemble one round and, unless --dry-run, submit it to Veri."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from guardtrain.budget import assert_jobs_fit
from guardtrain.continuation import dpo_init, plan_continuation
from guardtrain.data import (
    assemble_round,
    attach_page_text,
    discover_frozen_ids,
    dpo_records,
    load_labels,
    load_previous_miss_files,
    partition_dev,
    resolve_pages_dir,
    sft_records,
    write_jsonl,
)
from guardtrain.evaluate import read_testset_content_hash
from guardtrain.overlap import assert_no_test_overlap
from guardtrain.round_eval import dev_miss_path, pending_evals, sample_train_rows
from guardtrain.ledger import (
    SpendCapExceeded,
    SpendLedger,
    reserve_for_job,
    shared_veri_ledger_path,
    wall_clock_reservation_usd,
)
from guardtrain.paths import repo_root
from guardtrain.schema import (
    DEFAULT_EPOCHS,
    FALLBACK_BASE_MODEL,
    MIN_TRAIN_ROWS,
    PRIMARY_BASE_MODEL,
    VERI_BALANCE_FLOOR_USD,
    VERI_HARD_CAP_USD,
    ContractError,
    guard_model_name,
    gym_schema_readme,
    hf_repo_name,
)
from guardtrain.tomlutil import (
    STEP_SECONDS_BUDGET,
    observed_step_seconds,
    render_train_toml,
    steps_for_rows,
    steps_for_wall,
    wall_minutes_for_steps,
    write_toml,
)
from guardtrain.veri import (
    SubprocessVeri,
    SystemClock,
    classify_checkpoint,
    fetch_metrics,
    job_ran,
    newest_checkpoint_id,
    plan_commands,
    poll_until_done,
    settle_amount,
    storage_note,
    VeriCLIError,
)


@dataclass
class RoundOptions:
    round_index: int
    labels: Path
    runs: Path
    dry_run: bool = False
    dpo: bool = False
    base_model: str = PRIMARY_BASE_MODEL
    misses: list[Path] | None = None
    older_misses: list[Path] | None = None
    replay_fraction: float = 0.2
    dev_labels: Path | None = None
    attacker_labels: Path | None = None
    require_dev: bool = False
    require_previous_dev_eval: bool = False
    dev_fraction: float = 0.2
    train_sample_size: int = 64
    seed: int = 0
    max_wall_minutes: int | None = 60
    max_queue_minutes: int = 30
    max_steps: int = 400
    epochs: int = DEFAULT_EPOCHS
    retrain_from_base: bool = False
    distilled: Path | None = None
    spend_cap: str = VERI_HARD_CAP_USD
    poll_seconds: float = 30
    max_page_tokens: int = 2000
    system_in_user: bool = False
    hide_held_out_labels: bool = False
    lora_rank: int = 16
    lora_alpha: int = 32
    learning_rate: float | None = None
    grad_accum: int = 8
    max_seq_length: int = 4096
    pages_dir: Path | None = None
    test_id_files: list[Path] | None = None
    repo: Path | None = None
    min_rows: int = MIN_TRAIN_ROWS


def _sha8(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:8]


def dpo_already_used(runs: Path) -> bool:
    training = runs / "training"
    if not training.is_dir():
        return False
    for path in sorted(training.glob("round*.json")):
        if path.name.endswith(".refused.json"):
            continue
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if payload.get("method") == "dpo" and not payload.get("dry_run"):
            return True
        dpo = payload.get("dpo") or {}
        if (
            isinstance(dpo, dict)
            and dpo.get("status") in {"launched", "completed"}
            and not payload.get("dry_run")
        ):
            return True
    return False


def default_previous_dev_misses(runs: Path, round_index: int) -> list[Path]:
    """The immediately previous round's dev misses, and nothing from the test set."""
    if round_index < 1:
        return []
    path = dev_miss_path(runs, round_index - 1)
    return [path] if path.is_file() else []


def default_older_misses(runs: Path, round_index: int) -> list[Path]:
    """Dev misses from rounds <= N-2. Round N-1 is the full previous dev-miss file."""
    found = []
    for index in range(0, max(0, round_index - 1)):
        path = dev_miss_path(runs, index)
        if path.is_file():
            found.append(path)
    return found


def _previous_round_scored(runs: Path, round_index: int) -> bool:
    path = runs / "training" / f"round{round_index - 1}.json"
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (payload.get("evals") or {}).get("status") == "scored"


def merge_command(checkpoint_dir: Path, base_model: str) -> str:
    out = checkpoint_dir / "merged"
    return (
        "python -m guardtrain merge "
        f"--adapter {checkpoint_dir} --base {base_model} --out {out}"
    )


def _learning_rate(method: str, override: float | None) -> float:
    if override is not None:
        return override
    return 1e-4 if method == "sft_text" else 1e-5


def resolve_wall_and_steps(opts: RoundOptions, n_rows: int) -> tuple[int, int]:
    """Wall minutes and the step cap written into the job.

    Epochs are capped at 2. An explicit wall still truncates that plan, so
    60 minutes stays at 28 steps and the $1.29 reservation. When the wall is
    unset, size it to the epoch plan.
    """
    from guardtrain.early_stop import clamp_epochs

    opts.epochs = clamp_epochs(int(opts.epochs))
    if opts.max_wall_minutes is None:
        planned = steps_for_rows(n_rows, opts.grad_accum, opts.max_steps, None, opts.epochs)
        wall = wall_minutes_for_steps(planned)
        steps = steps_for_rows(n_rows, opts.grad_accum, opts.max_steps, wall, opts.epochs)
        return wall, steps
    wall = int(opts.max_wall_minutes)
    steps = steps_for_rows(n_rows, opts.grad_accum, opts.max_steps, wall, opts.epochs)
    return wall, steps


def _attach_distilled(rows, path: Path) -> int:
    """Copy teacher targets onto train rows. Missing pages keep the label target."""
    by_id: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            continue
        page_id = str(obj.get("page_id") or "")
        target = (
            obj.get("target")
            or obj.get("assistant")
            or obj.get("output")
            or obj.get("distilled_target")
        )
        if page_id and target:
            by_id[page_id] = str(target)
    attached = 0
    for row in rows:
        text = by_id.get(row.page_id)
        if not text:
            continue
        row.extra["distilled_target"] = text
        attached += 1
    return attached


def _row_group_id(row) -> str:
    gid = row.extra.get("group_id") if row.extra else None
    if gid:
        return str(gid)
    return f"page:{row.page_id}"


def _load_spec_map(labels: Path | None) -> dict[str, dict]:
    if labels is None:
        return {}
    specs_dir = Path(labels).parent / "specs"
    found: dict[str, dict] = {}
    if not specs_dir.is_dir():
        return found
    for path in sorted(specs_dir.glob("*.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(spec, dict):
            found[str(spec.get("page_id") or path.stem)] = spec
    return found


def _attach_groups(rows, spec_map: dict[str, dict]) -> None:
    if not spec_map or not rows:
        return
    root = str(repo_root())
    import sys

    if root not in sys.path:
        sys.path.insert(0, root)
    from gym.groups import group_id_of

    for row in rows:
        if row.extra.get("group_id"):
            continue
        spec = spec_map.get(row.page_id)
        if not spec:
            continue
        row.extra["group_id"] = group_id_of(spec)


def _structure_for(rows, spec_maps: list[dict[str, dict]]) -> dict:
    root = str(repo_root())
    import sys

    if root not in sys.path:
        sys.path.insert(0, root)
    from gym.structure import STRUCTURE_NOTE, features_from_page_text, features_of_spec, structure_block

    def features_of(row):
        for mapping in spec_maps:
            spec = mapping.get(row.page_id)
            if spec:
                return features_of_spec(spec)
        return features_from_page_text(row.page_text)

    block = structure_block(
        rows,
        verdict_of=lambda row: row.verdict or "unknown",
        attack_of=lambda row: row.attack_type or "unknown",
        features_of=features_of,
    )
    block["note"] = STRUCTURE_NOTE
    return block


def _drop_dev_groups(rows, dev_groups: set[str], dev_ids: set[str]):
    kept = []
    for row in rows:
        if row.page_id in dev_ids or _row_group_id(row) in dev_groups:
            continue
        kept.append(row)
    return kept


def _load_cumulative(runs: Path, rounds: list[int]):
    rows = []
    for index in rounds:
        path = runs / "training" / "datasets" / f"round{index}.train.jsonl"
        if path.is_file():
            rows.extend(load_labels(path))
    return rows


def _group_summary(train_rows, dev_rows) -> dict:
    def counts(rows) -> dict[str, int]:
        found: dict[str, int] = {}
        for row in rows:
            gid = _row_group_id(row)
            found[gid] = found.get(gid, 0) + 1
        return found

    train_counts = counts(train_rows)
    dev_counts = counts(dev_rows)
    return {
        "policy": (
            "Each group_id is entirely train or entirely dev. "
            "Gym pages are grouped by template and seed family. "
            "Attacker specs use the group_id they carry."
        ),
        "train_groups": len(train_counts),
        "dev_groups": len(dev_counts),
        "shared_groups": sorted(set(train_counts) & set(dev_counts)),
    }


def _refuse_shared_groups(train_rows, dev_rows) -> None:
    train_groups = {_row_group_id(row) for row in train_rows}
    dev_groups = {_row_group_id(row) for row in dev_rows}
    shared = sorted(train_groups & dev_groups)
    if not shared:
        return
    shown = ", ".join(shared[:8])
    extra = f" (+{len(shared) - 8} more)" if len(shared) > 8 else ""
    raise ContractError(
        "Refusing round: group_id appears in both train and dev "
        f"({shown}{extra}). Near-copies must stay on one side."
    )


def prepare_round(opts: RoundOptions) -> dict:
    """Build this round's mix, hold dev groups out, and write the dataset files.

    Does not talk to Veri and does not write ``roundN.json``.
    """
    root = opts.repo or repo_root()
    pages = resolve_pages_dir(opts.labels, opts.pages_dir)
    loaded = load_labels(opts.labels)
    attach_page_text(loaded, pages, required=True)
    spec_map = _load_spec_map(opts.labels)
    _attach_groups(loaded, spec_map)
    fresh, dev_in_file = partition_dev(loaded)
    dev_rows = list(dev_in_file)
    dev_spec_map = dict(spec_map)
    if opts.dev_labels is not None:
        if not opts.dev_labels.is_file():
            if opts.require_dev:
                raise ContractError(
                    f"Dev split not found: {opts.dev_labels}. "
                    "Generate it with python -m gym.train --round "
                    f"{opts.round_index} --n <count>."
                )
        else:
            extra = load_labels(opts.dev_labels)
            attach_page_text(extra, resolve_pages_dir(opts.dev_labels, None), required=True)
            dev_specs = _load_spec_map(opts.dev_labels)
            _attach_groups(extra, dev_specs)
            dev_spec_map.update(dev_specs)
            dev_rows.extend(partition_dev(extra)[1] or extra)
    elif opts.require_dev:
        raise ContractError(
            "A live round needs --dev (data/trainset/roundN/dev/labels.jsonl). "
            "The dev split is scored and held out of this round's training mix."
        )
    attacker_rows: list = []
    attacker_spec_map: dict = {}
    if opts.attacker_labels is not None:
        if not opts.attacker_labels.is_file():
            raise ContractError(f"Attacker labels not found: {opts.attacker_labels}")
        attacker_rows = load_labels(opts.attacker_labels)
        attach_page_text(attacker_rows, resolve_pages_dir(opts.attacker_labels, None), required=True)
        attacker_spec_map = _load_spec_map(opts.attacker_labels)
        _attach_groups(attacker_rows, attacker_spec_map)
    held_out_attacker = 0
    if attacker_rows:
        import sys

        gym_root = str(repo_root())
        if gym_root not in sys.path:
            sys.path.insert(0, gym_root)
        from gym.groups import split_by_group

        attacker_train, attacker_dev = split_by_group(
            attacker_rows,
            group_of=_row_group_id,
            attack_of=lambda row: row.attack_type or "unknown",
            dev_fraction=opts.dev_fraction,
            seed=opts.seed + opts.round_index + 3,
            pinned_train={_row_group_id(row) for row in fresh},
            pinned_dev={_row_group_id(row) for row in dev_rows},
        )
        for row in attacker_dev:
            row.split = "dev"
            row.page_set = "dev"
        held_out_attacker = len(attacker_dev)
        dev_rows.extend(attacker_dev)
        attacker_rows = attacker_train
    _refuse_shared_groups(fresh, dev_rows)

    test_ids = discover_frozen_ids(root, opts.test_id_files or [])
    if opts.round_index >= 1 and opts.require_previous_dev_eval and not _previous_round_scored(opts.runs, opts.round_index):
        raise ContractError(
            f"Refusing round {opts.round_index}: round {opts.round_index - 1} has no scored dev eval. "
            "Run python -m guardtrain round-eval on that round first. "
            "Misses are taken from that dev eval, never from the test set."
        )

    previous = []
    miss_paths = list(opts.misses or [])
    if not miss_paths:
        miss_paths = default_previous_dev_misses(opts.runs, opts.round_index)
    if opts.round_index >= 1 and opts.require_previous_dev_eval and not miss_paths:
        raise ContractError(
            f"Refusing round {opts.round_index}: no dev misses from round {opts.round_index - 1}. "
            "round-eval writes runs/training/datasets/round<N-1>.dev.misses.jsonl."
        )
    if miss_paths:
        previous = load_previous_miss_files(miss_paths, test_ids)
        attach_page_text(previous, pages, required=True)
    older_paths = list(opts.older_misses or [])
    if opts.round_index >= 2 and not older_paths:
        older_paths = default_older_misses(opts.runs, opts.round_index)
    older = load_previous_miss_files(older_paths, test_ids) if older_paths else []
    if older:
        attach_page_text(older, pages, required=True)

    dev_leaks = [row.page_id for row in dev_rows if row.page_id in test_ids]
    if dev_leaks:
        shown = ", ".join(dev_leaks[:8])
        raise ContractError(
            "Refusing round: the dev split contains frozen test page ids "
            f"({shown}). Dev is not a copy of the test set."
        )

    continuation = plan_continuation(
        opts.runs,
        opts.round_index,
        opts.base_model,
        retrain_from_base=opts.retrain_from_base,
        trial="sft",
    )
    opts.base_model = continuation.base_model
    if continuation.mode == "retrain_cumulative":
        cumulative = _load_cumulative(opts.runs, continuation.cumulative_rounds)
        seen = {row.page_id for row in fresh}
        for row in cumulative:
            if row.page_id not in seen:
                fresh.append(row)
                seen.add(row.page_id)
    dev_groups = {_row_group_id(row) for row in dev_rows}
    dev_ids = {row.page_id for row in dev_rows}
    fresh = _drop_dev_groups(fresh, dev_groups, dev_ids)
    attacker_rows = _drop_dev_groups(attacker_rows, dev_groups, dev_ids)
    previous = _drop_dev_groups(previous, dev_groups, dev_ids)
    older = _drop_dev_groups(older, dev_groups, dev_ids)

    mixed, stats = assemble_round(
        round_index=opts.round_index,
        round0_rows=fresh,
        previous_misses=previous,
        older_misses=older,
        attacker_rows=attacker_rows,
        test_ids=test_ids,
        replay_fraction=opts.replay_fraction,
        seed=opts.seed,
        max_page_tokens=opts.max_page_tokens,
    )
    _refuse_shared_groups(mixed, dev_rows)
    assert_no_test_overlap(mixed, what="train data")
    if dev_rows:
        assert_no_test_overlap(dev_rows, what="the dev split")
    fresh_for_sample = [row for row in mixed if row.mix_source == "train"]
    train_sample = sample_train_rows(fresh_for_sample, opts.train_sample_size, opts.seed + opts.round_index)
    testset_labels = root / "data" / "testset" / "labels.jsonl"
    slice_file = root / "gym" / "testset" / "slice100.txt"
    testset_hash = read_testset_content_hash(root).get("content_hash")
    distilled_rows = 0
    if not opts.dpo:
        distilled_path = opts.distilled
        if distilled_path is None:
            candidate = Path(opts.labels).parent / "distilled.jsonl"
            if candidate.is_file():
                distilled_path = candidate
        if distilled_path is not None and Path(distilled_path).is_file():
            distilled_rows = _attach_distilled(mixed, Path(distilled_path))
    method = "dpo" if opts.dpo else "sft_text"
    if method == "dpo":
        records = dpo_records(
            mixed,
            max_page_tokens=opts.max_page_tokens,
            system_in_user=opts.system_in_user,
            hide_held_out_labels=opts.hide_held_out_labels,
        )
        if not records:
            raise ContractError(
                "DPO needs miss rows with a model_output that differs from the gold JSON. "
                "Score a dev split first and pass that misses file."
            )
    else:
        records = sft_records(
            mixed,
            max_page_tokens=opts.max_page_tokens,
            system_in_user=opts.system_in_user,
            hide_held_out_labels=opts.hide_held_out_labels,
        )

    datasets = opts.runs / "training" / "datasets"
    payload_path = datasets / f"round{opts.round_index}.{method}.jsonl"
    meta_path = datasets / f"round{opts.round_index}.meta.jsonl"
    write_jsonl(payload_path, records)
    write_jsonl(meta_path, [row.as_dict() for row in mixed])
    write_jsonl(datasets / f"round{opts.round_index}.train.jsonl", [row.as_dict() for row in fresh_for_sample])
    write_jsonl(datasets / f"round{opts.round_index}.dev.jsonl", [row.as_dict() for row in dev_rows])
    structure = {
        "features": ["checkbox", "popup", "fee_line", "strike_through"],
        "train": _structure_for(mixed, [spec_map, attacker_spec_map]),
        "dev": _structure_for(dev_rows, [dev_spec_map, attacker_spec_map]),
    }
    return {
        "root": root,
        "records": records,
        "method": method,
        "payload_path": payload_path,
        "meta_path": meta_path,
        "datasets": datasets,
        "stats": stats,
        "dev_rows": dev_rows,
        "attacker_rows": attacker_rows,
        "held_out_attacker": held_out_attacker,
        "test_ids": test_ids,
        "fresh_for_sample": fresh_for_sample,
        "train_sample": train_sample,
        "testset_labels": testset_labels,
        "slice_file": slice_file,
        "testset_hash": testset_hash,
        "continuation": {
            "mode": continuation.mode,
            "base_model": continuation.base_model,
            "reason": continuation.reason,
            "cumulative_rounds": continuation.cumulative_rounds,
            "hf_repo": continuation.hf_repo,
        },
        "distilled_rows": distilled_rows,
        "structure": structure,
        "groups": _group_summary(mixed, dev_rows),
        "base_model": opts.base_model,
    }


def launch_round(
    opts: RoundOptions,
    *,
    executor: SubprocessVeri | None = None,
    ledger: SpendLedger | None = None,
    clock: SystemClock | None = None,
    metrics_fetcher=None,
) -> dict:
    if Decimal(opts.spend_cap) > Decimal(VERI_HARD_CAP_USD):
        raise SpendCapExceeded(
            f"Refusing spend cap ${opts.spend_cap} above the ${VERI_HARD_CAP_USD} Veri hard cap.",
            spent=Decimal("0"),
            attempted=Decimal(opts.spend_cap),
            cap=Decimal(VERI_HARD_CAP_USD),
        )
    if opts.dpo and dpo_already_used(opts.runs):
        raise ContractError(
            "DPO is limited to one round. A previous live round already used method=dpo."
        )

    prepared = prepare_round(opts)
    root = prepared["root"]
    records = prepared["records"]
    method = prepared["method"]
    payload_path = prepared["payload_path"]
    meta_path = prepared["meta_path"]
    datasets = prepared["datasets"]
    stats = prepared["stats"]
    dev_rows = prepared["dev_rows"]
    attacker_rows = prepared["attacker_rows"]
    test_ids = prepared["test_ids"]
    fresh_for_sample = prepared["fresh_for_sample"]
    train_sample = prepared["train_sample"]
    testset_labels = prepared["testset_labels"]
    slice_file = prepared["slice_file"]
    testset_hash = prepared["testset_hash"]

    wall, max_steps = resolve_wall_and_steps(opts, len(records))
    hf_repo = prepared["continuation"]["hf_repo"] or hf_repo_name(opts.round_index, "sft")
    output_model = guard_model_name(opts.round_index, "sft")
    train_base = opts.base_model
    if method == "dpo":
        train_base, _how = dpo_init({"name": "sft"}, opts.round_index, "sft")
        hf_repo = hf_repo_name(opts.round_index, "sft-dpo")
        output_model = guard_model_name(opts.round_index, "sft-dpo")
    dataset_name = f"guard-{method}-r{opts.round_index}-{_sha8(payload_path)}"
    toml_path = opts.runs / "training" / "configs" / f"round{opts.round_index}.toml"
    # Dataset id is filled after upload. Dry-run and the pre-upload toml use the name.
    dataset_id = dataset_name
    toml_text = render_train_toml(
        output_model=output_model,
        base_model=train_base,
        dataset_id=dataset_id,
        method=method,
        learning_rate=_learning_rate(method, opts.learning_rate),
        max_steps=max_steps,
        hf_repo=hf_repo,
        num_epochs=opts.epochs,
        max_seq_length=opts.max_seq_length,
        lora_rank=opts.lora_rank,
        lora_alpha=opts.lora_alpha,
        grad_accum=opts.grad_accum,
    )
    write_toml(toml_path, toml_text)

    checkpoint_dir = opts.runs / "training" / "checkpoints" / f"round{opts.round_index}"
    commands = plan_commands(
        dataset_path=payload_path,
        dataset_name=dataset_name,
        toml_path=toml_path,
        checkpoint_dir=checkpoint_dir,
        merge_command=merge_command(checkpoint_dir, train_base),
    )
    wall_usd = wall_clock_reservation_usd(wall, gpu_count=1)
    ledger = ledger or SpendLedger(
        shared_veri_ledger_path(),
        VERI_HARD_CAP_USD,
        quant="cents",
    )
    if ledger.would_exceed(wall_usd, opts.spend_cap):
        totals = ledger.totals(opts.spend_cap)
        raise SpendCapExceeded(
            (
                f"Refusing round {opts.round_index}: reserving ${wall_usd} would put "
                f"${totals.committed + wall_usd} against a ${totals.cap} cap."
            ),
            spent=totals.committed,
            attempted=wall_usd,
            cap=totals.cap,
        )

    report = {
        "schema_version": 1,
        "round": opts.round_index,
        "method": method,
        "dry_run": opts.dry_run,
        "base_model": train_base,
        "fallback_base_model": FALLBACK_BASE_MODEL,
        "output_model": output_model,
        "hf_repo": hf_repo,
        "hf_pushed": False,
        "distilled_rows": prepared.get("distilled_rows", 0),
        "step_seconds": None,
        "job_id": None,
        "status": "dry_run" if opts.dry_run else "launching",
        "cost_usd": None,
        "cost_confidence": None,
        "would_reserve_usd": format(wall_usd, "f"),
        "reserved_usd": None,
        "estimated_gpu_usd": None,
        "loss_curve": [],
        "commands": commands,
        "dataset": {
            "payload": str(payload_path),
            "meta": str(meta_path),
            "uploaded_rows": len(records),
            "mix": stats.as_dict(),
            "held_out_attacks": ["copycat_domain", "listing_injection"],
            "frozen_test_ids": len(test_ids),
            "dev_rows": len(dev_rows),
            "attacker_rows": len(attacker_rows),
            "policy": (
                "Fresh gym.train pages for this round, plus this round's attacker pages, "
                "plus the previous round's dev misses, plus a small replay of older dev misses. "
                "Dev is a whole-group holdout and is not trained on."
            ),
        },
        "groups": prepared["groups"],
        "structure": prepared["structure"],
        "continuation": prepared["continuation"],
        "splits": {
            "train": str(datasets / f"round{opts.round_index}.train.jsonl"),
            "dev": str(datasets / f"round{opts.round_index}.dev.jsonl"),
            "testset": str(testset_labels),
            "slice": str(slice_file),
        },
        "evals": pending_evals(
            train_rows=fresh_for_sample,
            dev_rows=dev_rows,
            sample_ids=[row.page_id for row in train_sample],
            testset_labels=str(testset_labels) if testset_labels.is_file() else None,
            slice_file=str(slice_file) if slice_file.is_file() else None,
            content_hash=testset_hash,
        ),
        "limits": {
            "max_wall_minutes": wall,
            "max_queue_minutes": opts.max_queue_minutes,
            "max_steps": max_steps,
            "epochs": opts.epochs,
            "early_stopping": {
                "metric": "trick_f1 - false_block_rate_clean",
                "max_epochs": 2,
                "patience": 1,
            },
            "max_steps_ceiling": opts.max_steps,
            "step_seconds_budget": STEP_SECONDS_BUDGET,
            "steps_allowed_by_wall": steps_for_wall(wall),
            "min_rows": opts.min_rows,
            "spend_cap_usd": opts.spend_cap,
            "hard_cap_usd": VERI_HARD_CAP_USD,
            "balance_floor_usd": VERI_BALANCE_FLOOR_USD,
            "gpu_type": "L4-24GB",
            "gpu_count": 1,
            "load_in_4bit": True,
            "lora_rank": opts.lora_rank,
        },
        "checkpoint": {
            "dir": str(checkpoint_dir),
            "kind": None,
            "merge_command": merge_command(checkpoint_dir, train_base),
        },
        "gym_schema_readme": gym_schema_readme(root),
        "notes": [
            storage_note(),
            "QLoRA is single-GPU. On OOM, rerun with --base-model " + FALLBACK_BASE_MODEL + ".",
            "No deployment is created. Do not host this model on Veri.",
            "veri jobs download returns the HF checkpoint. QLoRA checkpoints are adapters; merge locally.",
            (
                f"max_steps is {max_steps}: {opts.epochs} epoch(s), capped at 2, "
                "stopped on dev trick_f1 minus the false-block rate when per-epoch scores exist. "
                f"The --max-steps ceiling and a {STEP_SECONDS_BUDGET}s/step budget sit inside the {wall}-minute wall. "
                "use_unsloth is on. Veri does not expose completion-only loss, so the system prompt stays short."
            ),
            (
                f"The job pushes private merged weights to {hf_repo}. "
                "A failed Hugging Face push does not fail the Veri job, and the next round "
                "will not continue from a repo that was not recorded."
            ),
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if len(records) < opts.min_rows:
        report["notes"].append(
            f"{len(records)} trainable rows is below the launch minimum of {opts.min_rows}. "
            "A live round refuses this mix. Pass --min-rows only for a deliberate tiny run."
        )
    if opts.dry_run:
        report["status"] = "dry_run"
        _write_report(opts.runs, opts.round_index, report)
        return report

    import os

    if len(records) < opts.min_rows:
        raise ContractError(
            f"Refusing to launch round {opts.round_index}: {len(records)} trainable rows "
            f"is below the minimum of {opts.min_rows}."
        )

    if not os.environ.get("VERI_API_KEY"):
        raise VeriCLIError(
            "VERI_API_KEY is not set. Export it in the shell that launches the job. "
            "Dry-run does not need it."
        )

    executor = executor or SubprocessVeri()
    clock = clock or SystemClock()
    metrics_fetcher = metrics_fetcher or fetch_metrics

    executor.datasets_check(payload_path)
    dataset_id = executor.datasets_upload(payload_path, dataset_name)
    toml_text = render_train_toml(
        output_model=output_model,
        base_model=train_base,
        dataset_id=dataset_id,
        method=method,
        learning_rate=_learning_rate(method, opts.learning_rate),
        max_steps=max_steps,
        hf_repo=hf_repo,
        num_epochs=opts.epochs,
        max_seq_length=opts.max_seq_length,
        lora_rank=opts.lora_rank,
        lora_alpha=opts.lora_alpha,
        grad_accum=opts.grad_accum,
    )
    write_toml(toml_path, toml_text)
    estimate = executor.jobs_estimate(toml_path)
    estimate_usd = None
    rate = None
    if estimate.get("estimated_cost_usd") is not None:
        estimate_usd = Decimal(str(estimate["estimated_cost_usd"]))
        report["estimated_gpu_usd"] = format(estimate_usd, "f")
    if estimate.get("rate_usd_per_hour") is not None:
        rate = Decimal(str(estimate["rate_usd_per_hour"]))
    wall_live = wall_clock_reservation_usd(
        wall,
        gpu_count=int(estimate.get("gpu_count") or 1),
        hourly_rate=rate if rate is not None else Decimal("1.05"),
    )
    reserved = reserve_for_job(estimate_usd, wall_live)
    report["would_reserve_usd"] = format(reserved, "f")
    balance = executor.billing_balance()
    budget = assert_jobs_fit(
        ledger=ledger,
        spend_cap=opts.spend_cap,
        reservations=[reserved],
        balance=balance,
        require_balance=True,
    )
    report["budget"] = budget

    entry_id = ledger.authorize(
        reserved,
        note=f"round {opts.round_index} {method}",
        requested_cap=opts.spend_cap,
    )
    report["ledger_entry"] = entry_id
    report["reserved_usd"] = format(reserved, "f")
    try:
        job_id = executor.jobs_create(toml_path)
    except VeriCLIError:
        ledger.release(entry_id, note="create failed before a job id; validation failures are not billed")
        raise
    ledger.attach_job(entry_id, job_id)
    report["job_id"] = job_id

    def settle_and_write(view: dict | None) -> None:
        source = view or {"status": report.get("status"), "cost_usd": None}
        actual, confidence = settle_amount(source, reserved)
        ledger.settle(entry_id, actual, job_id=job_id)
        report["cost_usd"] = format(actual, "f")
        report["cost_confidence"] = confidence
        if view is not None and not job_ran(view):
            report["notes"].append("Cancelled before a GPU was allocated. Settled at $0.")
        _write_report(opts.runs, opts.round_index, report)

    try:
        view = poll_until_done(
            executor,
            job_id,
            max_wall_minutes=wall,
            max_queue_minutes=opts.max_queue_minutes,
            poll_seconds=opts.poll_seconds,
            clock=clock,
        )
    except BaseException as exc:
        # The poller already tried to cancel. Settle before returning so a
        # download is never the thing that leaves the reservation open.
        report["status"] = "poll_failed" if not isinstance(exc, KeyboardInterrupt) else "interrupt_cancel_requested"
        report["error_message"] = redact_error(exc)
        report["notes"].append(
            "Polling stopped. Settled at the reserved upper bound until veri billing transactions say otherwise."
        )
        settle_and_write(None)
        raise
    report["status"] = view.get("status")
    report["cancelled_by"] = view.get("cancelled_by")
    report["error_code"] = view.get("error_code")
    report["error_message"] = view.get("error_message")
    try:
        report["loss_curve"] = metrics_fetcher(job_id)
    except VeriCLIError as exc:
        report["loss_curve"] = []
        report["notes"].append(str(exc))
    pushed_url = str(view.get("hf_repo_url") or "")
    if view.get("status") == "completed" and pushed_url:
        report["hf_repo_url"] = pushed_url
        report["hf_pushed"] = True
    report["step_seconds"] = observed_step_seconds(
        report.get("loss_curve"),
        run_started=view.get("watcher_run_started"),
        finished=view.get("watcher_finished"),
        steps=max_steps,
    )
    # Ledger and round report are durable before any download. A failed
    # download must not leave the reservation open or the job id only in memory.
    settle_and_write(view)
    try:
        saved = _download_checkpoint(executor, job_id, view, checkpoint_dir)
    except VeriCLIError as exc:
        report["download_error"] = str(exc)
        report["notes"].append(
            "Download failed after the ledger was settled. Re-run the download command; do not launch another job for this reservation."
        )
        _write_report(opts.runs, opts.round_index, report)
        return report
    report["checkpoint"]["saved"] = saved
    if saved != "none":
        report["checkpoint"]["kind"] = classify_checkpoint(checkpoint_dir)
    _write_report(opts.runs, opts.round_index, report)
    return report


def redact_error(exc: BaseException) -> str:
    from guardtrain.redact import redact

    return redact(str(exc))


def _download_checkpoint(executor: SubprocessVeri, job_id: str, view: dict, checkpoint_dir: Path) -> str:
    """Final weights when the job completed; newest adapter checkpoint after a cancel."""
    if view.get("status") == "completed":
        executor.jobs_download(job_id, checkpoint_dir)
        return "final"
    if not job_ran(view):
        return "none"
    payload = executor.checkpoints_list(job_id)
    checkpoint_id = newest_checkpoint_id(payload, job_id)
    if not checkpoint_id:
        raise VeriCLIError(
            "No intermediate checkpoint was listed. "
            "veri checkpoints list may be unavailable for this workspace."
        )
    executor.checkpoints_download(job_id, checkpoint_id, checkpoint_dir)
    return checkpoint_id


def _write_report(runs: Path, round_index: int, report: dict) -> Path:
    path = runs / "training" / f"round{round_index}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path
