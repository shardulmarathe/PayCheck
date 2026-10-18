"""Command line for format, Veri rounds, GGUF serving, eval, and baselines."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from guardtrain.clients import (
    ApiCallError,
    MissingKeyError,
    check_anthropic,
    check_gemini,
    check_http_endpoint,
    check_mock,
    check_ollama,
    check_openai_compat,
    default_anthropic_create,
    default_gemini_create,
)
from guardtrain.convert import (
    merge_adapter,
    plan_conversion,
    run_convert,
    safe_deploy_hint,
    write_modelfile,
)
from guardtrain.data import load_labels, resolve_pages_dir, sft_records, write_jsonl
from guardtrain.evaluate import (
    build_report,
    load_eval_rows,
    prepare_page_set,
    prompt_token_estimate,
    read_testset_content_hash,
    rows_by_id_map,
    run_checks,
    slice_ids_from,
    update_leaderboard,
    write_report,
)
from guardtrain.ledger import SpendCapExceeded, SpendLedger, shared_veri_ledger_path
from guardtrain.paths import repo_root, runs_dir
from guardtrain.round_eval import dev_miss_path, load_saved_split, score_into_report, score_rows
from guardtrain.prices import gemini_max_tokens, lookup_price
from guardtrain.redact import redact
from guardtrain.round_run import RoundOptions, launch_round
from guardtrain.sweep import (
    assign_trial_scores,
    attach_winner_test,
    launch_pending_dpo,
    refresh_winner,
    require_trial_model,
    run_sweep,
)
from guardtrain.schema import (
    ANTHROPIC_DEFAULT_CAP_USD,
    ANTHROPIC_HARD_CAP_USD,
    GEMINI_HARD_CAP_USD,
    LOCAL_GGUF,
    LOCAL_OLLAMA_MODELS,
    DEFAULT_EPOCHS,
    MIN_TRAIN_ROWS,
    PRIMARY_BASE_MODEL,
    QWEN3GUARD_HF,
    VERI_HARD_CAP_USD,
    ContractError,
)
from guardtrain.serve_app import create_app, mock_complete, serve
from guardtrain.veri import VeriCLIError


def _runs(args: argparse.Namespace) -> Path:
    return Path(args.runs_dir) if args.runs_dir else runs_dir()


def _print_json(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")


def cmd_format(args: argparse.Namespace) -> int:
    rows = load_labels(Path(args.labels))
    from guardtrain.data import attach_page_text, discover_frozen_ids, filter_trainable
    from guardtrain.paths import repo_root

    attach_page_text(rows, resolve_pages_dir(Path(args.labels), Path(args.pages_dir) if args.pages_dir else None))
    test_ids = discover_frozen_ids(repo_root(), [Path(p) for p in args.test_id_file])
    kept, stats = filter_trainable(
        rows, test_ids, max_page_tokens=args.max_page_tokens, mix_source="round0"
    )
    records = sft_records(
        kept,
        max_page_tokens=args.max_page_tokens,
        system_in_user=args.system_in_user,
        hide_held_out_labels=args.hide_held_out_labels,
    )
    out = Path(args.out)
    write_jsonl(out, records)
    if args.meta_out:
        write_jsonl(Path(args.meta_out), [row.as_dict() for row in kept])
    _print_json({"out": str(out), "rows": len(records), "stats": stats.as_dict()})
    return 0


def _round_labels(args: argparse.Namespace) -> Path:
    if args.labels:
        return Path(args.labels)
    return repo_root() / "data" / "trainset" / f"round{args.round}" / "labels.jsonl"


def _optional_split(explicit: str | None, default: Path) -> Path | None:
    if explicit:
        return Path(explicit)
    return default if default.is_file() else None


def _round_options(args: argparse.Namespace, *, labels: Path | None = None) -> RoundOptions:
    labels = labels or _round_labels(args)
    dev = _optional_split(args.dev, labels.parent / "dev" / "labels.jsonl")
    attacker = _optional_split(
        args.attacker,
        repo_root() / "data" / "attacker" / f"round{args.round}" / "labels.jsonl",
    )
    return RoundOptions(
        round_index=args.round,
        labels=labels,
        runs=_runs(args),
        dry_run=args.dry_run,
        dpo=args.dpo,
        base_model=args.base_model,
        misses=[Path(p) for p in args.misses],
        older_misses=[Path(p) for p in args.older_misses],
        replay_fraction=args.replay_fraction,
        seed=args.seed,
        max_wall_minutes=args.max_wall_minutes,
        max_queue_minutes=args.max_queue_minutes,
        max_steps=args.max_steps,
        epochs=getattr(args, "epochs", DEFAULT_EPOCHS),
        retrain_from_base=getattr(args, "retrain_from_base", False),
        distilled=Path(args.distilled) if getattr(args, "distilled", None) else None,
        spend_cap=str(args.spend_cap),
        poll_seconds=args.poll_seconds,
        max_page_tokens=args.max_page_tokens,
        system_in_user=args.system_in_user,
        hide_held_out_labels=args.hide_held_out_labels,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
        learning_rate=args.learning_rate,
        grad_accum=args.grad_accum,
        pages_dir=resolve_pages_dir(labels, Path(args.pages_dir) if args.pages_dir else None),
        min_rows=args.min_rows,
        test_id_files=[Path(p) for p in args.test_id_file],
        dev_labels=dev,
        attacker_labels=attacker,
        require_dev=not args.dry_run,
        require_previous_dev_eval=not args.dry_run,
        train_sample_size=args.train_sample,
    )


def cmd_round(args: argparse.Namespace) -> int:
    opts = _round_options(args)
    report = launch_round(opts)
    _print_json(
        {
            "round": report["round"],
            "dry_run": report["dry_run"],
            "method": report["method"],
            "job_id": report["job_id"],
            "status": report["status"],
            "would_reserve_usd": report["would_reserve_usd"],
            "cost_usd": report["cost_usd"],
            "commands": report["commands"],
            "dataset": report["dataset"]["mix"],
            "evals": (report.get("evals") or {}).get("status"),
            "train_dev_gap": (report.get("evals") or {}).get("train_dev_gap"),
        }
    )
    if report.get("download_error"):
        return 1
    if not report["dry_run"] and report["status"] not in {"completed", "dry_run", "cancelled", "canceled"}:
        return 1
    return 0


def _predict_row(args: argparse.Namespace):
    def predict(row):
        if args.backend == "mock":
            return check_mock(row, max_page_tokens=args.max_page_tokens).as_pred()
        if args.backend == "ollama":
            return check_ollama(
                row,
                model=args.ollama_model,
                base_url=args.ollama_url,
                max_page_tokens=args.max_page_tokens,
                adapter=args.adapter,
            ).as_pred()
        if args.backend == "llama-cpp":
            return check_openai_compat(
                row,
                model=args.llama_model,
                base_url=args.llama_url,
                max_page_tokens=args.max_page_tokens,
                adapter=args.adapter,
            ).as_pred()
        if args.backend == "http":
            return check_http_endpoint(row, url=args.url).as_pred()
        raise ContractError(f"Unknown backend {args.backend}")

    return predict


def _rows_for_score(report: dict, runs: Path, kind: str):
    splits = report.get("splits") or {}
    if kind == "dev":
        return load_saved_split(Path(splits["dev"]))
    train_rows = load_saved_split(Path(splits["train"]))
    sample_ids = list((report.get("evals") or {}).get("train_sample", {}).get("page_ids") or [])
    if not sample_ids:
        return train_rows
    by_id = {row.page_id: row for row in train_rows}
    return [by_id[page_id] for page_id in sample_ids if page_id in by_id]


def cmd_sweep(args: argparse.Namespace) -> int:
    """Launch up to four Veri jobs. The dev split picks the winner.

    Paid jobs are not submitted unless ``--submit`` is passed. Scoring every
    trial through one ``--backend`` is refused: each trial is served under its
    own name and scored with ``sweep-score``.
    """
    if args.submit and args.dry_run:
        raise ContractError(
            "--submit and --dry-run together is an error. A sweep is a dry run unless --submit is passed alone."
        )
    if args.backend:
        raise ContractError(
            "A sweep does not score every trial against one server. "
            "Serve each trial as guard-rN-<trial> and run "
            "sweep-score --trial NAME --model guard-rN-NAME."
        )
    opts = _round_options(args)
    opts.dpo = False
    if not args.submit:
        opts.dry_run = True
    report = run_sweep(opts, Path(args.sweep))
    winner = report.get("winner")
    _print_json(
        {
            "round": report["round"],
            "dry_run": report["dry_run"],
            "winner": winner,
            "trials": [
                {
                    "name": trial["name"],
                    "status": trial.get("status"),
                    "selection_score": trial.get("selection_score"),
                    "trick_f1": trial.get("trick_f1"),
                    "false_block_rate_clean": trial.get("false_block_rate_clean"),
                    "has_testset": "testset" in trial,
                }
                for trial in report["trials"]
            ],
            "structure": {
                "train": (report.get("structure") or {}).get("train", {}).get("by_verdict"),
                "dev": (report.get("structure") or {}).get("dev", {}).get("by_verdict"),
            },
            "groups": report.get("groups"),
            "dpo": (report.get("dpo") or {}).get("status"),
            "continuation": (report.get("continuation") or {}).get("mode"),
        }
    )
    return 0


def cmd_sweep_score(args: argparse.Namespace) -> int:
    """Score downloaded sweep trials. Test scores are written only for the dev winner."""
    runs = _runs(args)
    path = runs / "training" / f"round{args.round}.json"
    if not path.is_file():
        raise ContractError(f"No round report at {path}. Launch the sweep first.")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not report.get("sweep"):
        raise ContractError(f"Round {args.round} is not a sweep report.")
    if not args.trial or not args.model:
        raise ContractError(
            "sweep-score requires --trial and --model. "
            "Serve that trial as guard-rN-<trial> and pass that name as --model."
        )
    require_trial_model(report, args.round, args.trial, args.model)
    args.ollama_model = args.model
    args.llama_model = args.model
    predict = _predict_row(args)
    if args.testset:
        if not report.get("winner"):
            refresh_winner(report)
        if not report.get("winner"):
            raise ContractError("Dev scores have not picked a winner yet. Score every trial before the test set.")
        if report.get("winner") != args.trial:
            raise ContractError(
                f"The frozen test set is scored only for the dev winner ({report.get('winner')})."
            )
        test_labels = Path(args.labels) if args.labels else repo_root() / "data" / "testset" / "labels.jsonl"
        test_rows = load_eval_rows(test_labels, Path(args.pages_dir) if args.pages_dir else None)
        if not test_rows:
            raise ContractError("The frozen test set is empty.")
        slice_path = Path(args.slice) if args.slice else repo_root() / "gym" / "testset" / "slice100.txt"
        wanted = set(slice_ids_from(slice_path)) if slice_path.is_file() else set()
        slice_rows = [row for row in test_rows if row.page_id in wanted] if wanted else []
        test_metrics = score_rows(test_rows, predict)
        slice_metrics = score_rows(slice_rows, predict) if slice_rows else None
        attach_winner_test(report, test_metrics, slice_metrics)
    else:
        train_rows = _rows_for_score(report, runs, "train")
        dev_rows = _rows_for_score(report, runs, "dev")
        if not dev_rows:
            raise ContractError("The saved dev split is empty, so a winner cannot be chosen.")
        assign_trial_scores(
            report,
            args.trial,
            score_rows(train_rows, predict),
            score_rows(dev_rows, predict),
        )
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    dpo_status = (report.get("dpo") or {}).get("status")
    if args.launch_dpo:
        if report.get("winner") and report.get("winner") != args.trial:
            raise ContractError("DPO launches from the dev winner. Pass that trial's name and model.")
        dev_path = (report.get("splits") or {}).get("dev")
        if not dev_path:
            raise ContractError("Round report has no saved dev split, so DPO pairs cannot be built.")
        from guardtrain.data import discover_frozen_ids

        limits = report.get("limits") or {}
        opts = RoundOptions(
            round_index=args.round,
            labels=Path((report.get("splits") or {}).get("train") or dev_path),
            runs=runs,
            dry_run=bool(args.dry_run),
            base_model=report.get("base_model") or PRIMARY_BASE_MODEL,
            max_wall_minutes=int(limits.get("max_wall_minutes") or 60),
            max_queue_minutes=int(limits.get("max_queue_minutes") or 30),
            max_steps=int(limits.get("max_steps") or 400),
            spend_cap=str(limits.get("spend_cap_usd") or VERI_HARD_CAP_USD),
        )
        launch_pending_dpo(
            opts,
            report,
            load_saved_split(Path(dev_path)),
            discover_frozen_ids(repo_root(), []),
        )
        dpo_status = (report.get("dpo") or {}).get("status")
    _print_json(
        {
            "round": args.round,
            "winner": report.get("winner"),
            "testset_scored": bool((report.get("evals") or {}).get("testset")),
            "trials": [trial["name"] for trial in report.get("trials") or [] if "testset" in trial],
            "dpo": dpo_status,
        }
    )
    return 0


def _load_mix_rows(report: dict):
    meta = (report.get("dataset") or {}).get("meta")
    if not meta:
        return None
    path = Path(meta)
    if not path.is_file():
        return None
    return load_saved_split(path)


def cmd_round_eval(args: argparse.Namespace) -> int:
    """Score train, dev, and the frozen test set.

    Writes ``runs/r{N}/replay.jsonl`` and ``runs/r{N}/summary.json``.
    ``--round 0 --train-labels`` scores the base model before any training
    and does not overwrite a dry-run ``round0.json``.
    The dev miss file is the only miss file the next round may train on.
    ``heldout_template`` is the headline slice. ``heldout_attack`` is recall only.
    """
    runs = _runs(args)
    report_path = runs / "training" / f"round{args.round}.json"
    base_eval = args.round == 0 and bool(args.train_labels)
    spec_dirs: list[Path] = []
    if base_eval:
        train_path = Path(args.train_labels)
        dev_path = Path(args.dev) if args.dev else train_path.parent / "dev" / "labels.jsonl"
        train_rows = load_saved_split(train_path)
        dev_rows = load_saved_split(dev_path)
        report = {
            "round": 0,
            "base_eval": True,
            "winner": None,
            "evals": {},
            "splits": {"train": str(train_path), "dev": str(dev_path)},
        }
        mix_rows = None
        spec_dirs = [train_path.parent / "specs", dev_path.parent / "specs"]
    else:
        if not report_path.is_file():
            raise ContractError(f"No round report at {report_path}. Launch the round first.")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        splits = report.get("splits") or {}
        if not splits.get("train") or not splits.get("dev"):
            raise ContractError("Round report has no saved train/dev splits.")
        train_rows = load_saved_split(Path(splits["train"]))
        dev_rows = load_saved_split(Path(splits["dev"]))
        mix_rows = _load_mix_rows(report)
        for key in ("train", "dev"):
            spec_dirs.append(Path(splits[key]).parent / "specs")
    test_labels = Path(args.labels) if args.labels else repo_root() / "data" / "testset" / "labels.jsonl"
    pages = Path(args.pages_dir) if args.pages_dir else None
    test_rows = load_eval_rows(test_labels, pages)
    slice_path = Path(args.slice) if args.slice else repo_root() / "gym" / "testset" / "slice100.txt"
    wanted = set(slice_ids_from(slice_path)) if slice_path.is_file() else set()
    slice_rows = [row for row in test_rows if row.page_id in wanted] if wanted else []
    if slice_path.is_file() and not slice_rows:
        raise ContractError(f"None of the test labels are in the slice file {slice_path}.")
    content_hash = read_testset_content_hash(repo_root()).get("content_hash")
    score_into_report(
        report,
        train_rows=train_rows,
        dev_rows=dev_rows,
        test_rows=test_rows,
        slice_rows=slice_rows,
        predict=_predict_row(args),
        dev_miss_path=dev_miss_path(runs, args.round),
        content_hash=content_hash,
        mix_rows=mix_rows,
        spec_dirs=spec_dirs,
        runs=runs,
    )
    if not base_eval:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    evals = report["evals"]
    by_slice = evals.get("by_slice") or {}
    headline = by_slice.get("heldout_template") or {}
    attack = by_slice.get("heldout_attack") or {}
    _print_json(
        {
            "round": args.round,
            "status": evals["status"],
            "headline_slice": "heldout_template",
            "heldout_template": {
                "f1": headline.get("f1"),
                "catch_rate": headline.get("catch_rate"),
                "false_block_rate": headline.get("false_block_rate"),
                "n": headline.get("n"),
            },
            "heldout_attack_recall": attack.get("recall"),
            "winner_trial": evals.get("winner_trial"),
            "train_dev_gap": evals["train_dev_gap"],
            "dev_misses": evals["dev_misses"],
            "testset_content_hash": evals["testset_content_hash"],
            "replay": evals.get("replay"),
            "summary": evals.get("summary"),
            "in_dist_vs_heldout_template_gap": None
            if not evals.get("summary")
            else json.loads(Path(evals["summary"]).read_text(encoding="utf-8")).get(
                "in_dist_vs_heldout_template_gap"
            ),
        }
    )
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    hf_dir = Path(args.hf_dir) if args.hf_dir else None
    outfile = Path(args.outfile)
    commands = plan_conversion(
        hf_dir=hf_dir,
        base_model=args.base_model,
        outfile=outfile,
        outtype=args.outtype,
        llama_cpp_dir=args.llama_cpp_dir,
        quantize=args.quantize,
        hf_repo=args.hf_repo,
    )
    modelfile = outfile.with_suffix(".Modelfile")
    payload = {"dry_run": args.dry_run, "commands": commands, "modelfile": str(modelfile)}
    if args.dry_run:
        _print_json(payload)
        return 0
    if hf_dir is not None and not hf_dir.exists() and args.base_model is None:
        raise ContractError(f"HF directory does not exist: {hf_dir}")
    write_modelfile(modelfile, outfile)
    _print_json(payload)
    run_convert(commands, dry_run=False)
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    command = (
        "python -m guardtrain merge "
        f"--adapter {args.adapter} --base {args.base} --out {args.out}"
    )
    if args.dry_run:
        _print_json({"dry_run": True, "command": command})
        return 0
    merge_adapter(Path(args.adapter), args.base, Path(args.out))
    _print_json({"out": args.out})
    return 0


def _ollama_complete(base_url: str, model: str, num_predict: int):
    import httpx

    def complete(messages: list[dict[str, str]]) -> tuple[str, int, int]:
        response = httpx.post(
            base_url.rstrip("/") + "/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": num_predict},
            },
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()
        content = ((payload.get("message") or {}).get("content")) or ""
        return content, int(payload.get("prompt_eval_count") or 0), int(payload.get("eval_count") or 0)

    return complete


def _llama_complete(base_url: str, model: str, max_tokens: int):
    import httpx

    def complete(messages: list[dict[str, str]]) -> tuple[str, int, int]:
        response = httpx.post(
            base_url.rstrip("/") + "/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        usage = payload.get("usage") or {}
        return content, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)

    return complete


def cmd_serve(args: argparse.Namespace) -> int:
    if args.dry_run:
        _print_json(
            {
                "dry_run": True,
                "bind": "0.0.0.0:$PORT",
                "backend": args.backend,
                "start": [
                    "llama-server -m MODEL.gguf --host 0.0.0.0 --port 8081 -c 4096 -n 512 --temp 0",
                    "ollama serve",
                    "python -m guardtrain serve --backend ollama --ollama-model guard-qwen3",
                ],
            }
        )
        return 0
    if args.backend == "mock":
        complete = mock_complete
    elif args.backend == "ollama":
        complete = _ollama_complete(args.ollama_url, args.ollama_model, args.max_tokens)
    elif args.backend == "llama-cpp":
        complete = _llama_complete(args.llama_url, args.llama_model, args.max_tokens)
    else:
        raise ContractError(f"Unknown backend {args.backend}")
    app = create_app(
        complete,
        adapter=args.adapter,
        max_page_tokens=args.max_page_tokens,
        backend_name=args.backend,
    )
    serve(app, port=args.port)
    return 0


def _pages(args: argparse.Namespace) -> Path:
    return resolve_pages_dir(Path(args.labels), Path(args.pages_dir) if args.pages_dir else None)


def _price(args: argparse.Namespace, model: str):
    return lookup_price(
        model,
        input_usd_per_mtok=args.input_usd_per_mtok,
        output_usd_per_mtok=args.output_usd_per_mtok,
    )


def _finish_eval(args, rows, preds, price, page_set, stopped, model, round_name) -> Path:
    extra = {}
    if page_set in {"dev", "train"}:
        extra["rows_by_id"] = rows_by_id_map(rows[: len(preds)])
    report = build_report(
        model=model,
        round_name=round_name,
        page_set=page_set,
        rows=rows[: len(preds)],
        preds=preds,
        price=price,
        stopped_reason=stopped,
        extra=extra or None,
    )
    return write_report(_runs(args), report)


def cmd_eval(args: argparse.Namespace) -> int:
    rows = load_eval_rows(Path(args.labels), _pages(args))
    slice_ids = slice_ids_from(Path(args.slice) if args.slice else None)
    runs = _runs(args)
    targets = [(rows, args.page_set)]
    if args.also_slice:
        if not slice_ids:
            raise ContractError("--also-slice needs --slice")
        targets.append((prepare_page_set(rows, slice_ids=slice_ids, page_set="slice100")[0], "slice100"))
    price = _price(args, args.model)
    for subset, page_set in targets:
        if args.limit:
            subset = subset[: args.limit]
        if args.backend == "mock":
            checker = lambda row: check_mock(row, max_page_tokens=args.max_page_tokens)  # noqa: E731
        elif args.backend == "http":
            checker = lambda row: check_http_endpoint(row, url=args.url)  # noqa: E731
        elif args.backend == "ollama":
            checker = lambda row: check_ollama(  # noqa: E731
                row,
                model=args.ollama_model,
                base_url=args.ollama_url,
                max_page_tokens=args.max_page_tokens,
                adapter=args.adapter,
                num_predict=args.max_tokens,
            )
        elif args.backend == "llama-cpp":
            checker = lambda row: check_openai_compat(  # noqa: E731
                row,
                model=args.llama_model,
                base_url=args.llama_url,
                max_page_tokens=args.max_page_tokens,
                adapter=args.adapter,
                max_tokens=args.max_tokens,
            )
        else:
            raise ContractError(f"Unknown backend {args.backend}")
        preds, stopped = run_checks(
            subset,
            checker,
            price=price,
            max_output_tokens=args.max_tokens,
            max_page_tokens=args.max_page_tokens,
        )
        path = _finish_eval(args, subset, preds, price, page_set, stopped, args.model, args.round)
        _print_json({"wrote": str(path), "page_set": page_set, "n": len(preds), "stopped_reason": stopped})
    update_leaderboard(runs)
    return 0


def _dry_plan(rows, price, max_output_tokens, max_page_tokens, ledger, cap) -> dict:
    remaining = ledger.totals(cap).remaining
    fit = 0
    worsts = []
    for row in rows:
        worst = price.cost(prompt_token_estimate(row, max_page_tokens), max_output_tokens)
        worsts.append(worst)
        if remaining >= worst:
            remaining -= worst
            fit += 1
        else:
            break
    mean = (sum(worsts, Decimal("0")) / len(worsts)) if worsts else Decimal("0")
    return {
        "dry_run": True,
        "n_selected": len(rows),
        "n_affordable": fit,
        "worst_case_per_check_usd": format(mean, "f"),
        "worst_case_per_1000_usd": format(mean * 1000, "f"),
        "remaining_usd": format(ledger.totals(cap).remaining, "f"),
        "cap_usd": format(ledger.totals(cap).cap, "f"),
    }


def cmd_baseline_gemini(args: argparse.Namespace) -> int:
    if Decimal(str(args.spend_cap)) > Decimal(GEMINI_HARD_CAP_USD):
        raise SpendCapExceeded(
            f"Refusing Gemini spend cap ${args.spend_cap} above the ${GEMINI_HARD_CAP_USD} hard cap.",
            spent=Decimal("0"),
            attempted=Decimal(str(args.spend_cap)),
            cap=Decimal(GEMINI_HARD_CAP_USD),
        )
    rows = load_eval_rows(Path(args.labels), _pages(args))
    slice_ids = slice_ids_from(Path(args.slice) if args.slice else None)
    args.max_tokens = gemini_max_tokens(args.model, args.max_tokens)
    selected, page_set = prepare_page_set(
        rows,
        model=args.model,
        slice_ids=slice_ids,
        allow_full=args.allow_full_testset,
        probe=args.probe,
        seed=args.seed,
        page_set=args.page_set,
    )
    price = _price(args, args.model)
    runs = _runs(args)
    ledger = SpendLedger(runs / "baselines" / "gemini_spend_ledger.json", GEMINI_HARD_CAP_USD, quant="micro")
    if args.dry_run:
        plan = _dry_plan(selected, price, args.max_tokens, args.max_page_tokens, ledger, args.spend_cap)
        plan["model"] = args.model
        plan["page_set"] = page_set
        plan["thinking_level"] = args.thinking_level
        plan["max_tokens"] = args.max_tokens
        plan["gateway"] = "GEMINI_BASE_URL"
        if plan["n_selected"] and plan["n_affordable"] == 0:
            _print_json(plan)
            raise SpendCapExceeded(
                "Gemini spend cap cannot afford a single check.",
                spent=ledger.totals(args.spend_cap).committed,
                attempted=Decimal(plan["worst_case_per_check_usd"]),
                cap=ledger.totals(args.spend_cap).cap,
            )
        out = runs / "baselines" / f"{args.model}_dry_run.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        _print_json(plan)
        return 0
    _create, _base = default_gemini_create()

    def checker(row):
        return check_gemini(
            row,
            model=args.model,
            max_tokens=args.max_tokens,
            thinking_level=args.thinking_level,
            max_page_tokens=args.max_page_tokens,
            create_fn=_create,
        )

    preds, stopped = run_checks(
        selected,
        checker,
        price=price,
        max_output_tokens=args.max_tokens,
        max_page_tokens=args.max_page_tokens,
        ledger=ledger,
        requested_cap=str(args.spend_cap),
    )
    path = _finish_eval(args, selected, preds, price, page_set, stopped, args.model, args.round)
    _print_json({"wrote": str(path), "page_set": page_set, "n": len(preds), "stopped_reason": stopped})
    if stopped and not preds:
        return 3
    return 0


def cmd_baseline_anthropic(args: argparse.Namespace) -> int:
    if Decimal(str(args.spend_cap)) > Decimal(ANTHROPIC_HARD_CAP_USD):
        raise SpendCapExceeded(
            f"Refusing Anthropic spend cap ${args.spend_cap} above the ${ANTHROPIC_HARD_CAP_USD} safety ceiling.",
            spent=Decimal("0"),
            attempted=Decimal(str(args.spend_cap)),
            cap=Decimal(ANTHROPIC_HARD_CAP_USD),
        )
    rows = load_eval_rows(Path(args.labels), _pages(args))
    slice_ids = slice_ids_from(Path(args.slice) if args.slice else None)
    selected, page_set = prepare_page_set(
        rows,
        model=args.model,
        slice_ids=slice_ids,
        allow_full=True,
        probe=args.probe,
        seed=args.seed,
        page_set=args.page_set,
    )
    if args.also_slice and slice_ids and not args.probe:
        pass
    price = _price(args, args.model)
    runs = _runs(args)
    ledger = SpendLedger(
        runs / "baselines" / "anthropic_spend_ledger.json",
        ANTHROPIC_HARD_CAP_USD,
        quant="micro",
    )
    targets = [(selected, page_set)]
    if args.also_slice and slice_ids and page_set != "slice100" and not args.probe:
        sliced, _ = prepare_page_set(rows, slice_ids=slice_ids, page_set="slice100")
        targets.append((sliced, "slice100"))
    if args.dry_run:
        plan = _dry_plan(targets[0][0], price, args.max_tokens, args.max_page_tokens, ledger, args.spend_cap)
        plan["model"] = args.model
        plan["effort"] = args.effort
        plan["page_set"] = page_set
        if plan["n_selected"] and plan["n_affordable"] == 0:
            _print_json(plan)
            raise SpendCapExceeded(
                "Anthropic spend cap cannot afford a single check.",
                spent=ledger.totals(args.spend_cap).committed,
                attempted=Decimal(plan["worst_case_per_check_usd"]),
                cap=ledger.totals(args.spend_cap).cap,
            )
        _print_json(plan)
        return 0
    create = default_anthropic_create()

    def checker(row):
        return check_anthropic(
            row,
            model=args.model,
            max_tokens=args.max_tokens,
            effort=args.effort,
            max_page_tokens=args.max_page_tokens,
            create_fn=create,
        )

    for subset, subset_page_set in targets:
        preds, stopped = run_checks(
            subset,
            checker,
            price=price,
            max_output_tokens=args.max_tokens,
            max_page_tokens=args.max_page_tokens,
            ledger=ledger,
            requested_cap=str(args.spend_cap),
        )
        path = _finish_eval(args, subset, preds, price, subset_page_set, stopped, args.model, args.round)
        _print_json(
            {"wrote": str(path), "page_set": subset_page_set, "n": len(preds), "stopped_reason": stopped}
        )
        if stopped and not preds:
            return 3
    return 0


def cmd_baseline_local(args: argparse.Namespace) -> int:
    rows = load_eval_rows(Path(args.labels), _pages(args))
    slice_ids = slice_ids_from(Path(args.slice) if args.slice else None)
    price = _price(args, args.model)
    ollama_model = args.ollama_model or LOCAL_OLLAMA_MODELS[args.model]
    if args.dry_run:
        hf_model = QWEN3GUARD_HF if args.model == "qwen3guard-4b" else PRIMARY_BASE_MODEL
        _print_json(
            {
                "dry_run": True,
                "model": args.model,
                "backend": args.backend,
                "hf_model": hf_model,
                "gguf": LOCAL_GGUF[args.model],
                "ollama_model": ollama_model,
                "note": (
                    "Convert that HF repo locally with guardtrain convert, the same way as the "
                    "trained guard. Do not pull an Ollama library tag."
                ),
            }
        )
        return 0
    args.ollama_model = ollama_model
    targets = [(rows, args.page_set)]
    if args.also_slice:
        if not slice_ids:
            raise ContractError("--also-slice needs --slice")
        targets.append((prepare_page_set(rows, slice_ids=slice_ids, page_set="slice100")[0], "slice100"))
    for subset, page_set in targets:
        if args.backend == "http":
            checker = lambda row: check_http_endpoint(row, url=args.url)  # noqa: E731
        elif args.backend == "ollama":
            checker = lambda row: check_ollama(  # noqa: E731
                row,
                model=args.ollama_model,
                base_url=args.ollama_url,
                max_page_tokens=args.max_page_tokens,
                adapter=args.adapter,
            )
        elif args.backend == "llama-cpp":
            checker = lambda row: check_openai_compat(  # noqa: E731
                row,
                model=args.llama_model,
                base_url=args.llama_url,
                max_page_tokens=args.max_page_tokens,
                adapter=args.adapter,
            )
        else:
            raise ContractError(f"Unknown backend {args.backend}")
        preds, stopped = run_checks(
            subset,
            checker,
            price=price,
            max_output_tokens=args.max_tokens,
            max_page_tokens=args.max_page_tokens,
        )
        path = _finish_eval(args, subset, preds, price, page_set, stopped, args.model, args.round)
        _print_json({"wrote": str(path), "page_set": page_set, "n": len(preds)})
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    runs = _runs(args)
    which = args.which
    if which == "veri":
        ledger = SpendLedger(shared_veri_ledger_path(), VERI_HARD_CAP_USD, quant="cents")
        cap = args.spend_cap or VERI_HARD_CAP_USD
    elif which == "gemini":
        ledger = SpendLedger(runs / "baselines" / "gemini_spend_ledger.json", GEMINI_HARD_CAP_USD, quant="micro")
        cap = args.spend_cap or GEMINI_HARD_CAP_USD
    else:
        ledger = SpendLedger(
            runs / "baselines" / "anthropic_spend_ledger.json",
            ANTHROPIC_HARD_CAP_USD,
            quant="micro",
        )
        cap = args.spend_cap or ANTHROPIC_HARD_CAP_USD
    if args.action == "settle":
        ledger.settle(args.entry, args.actual, job_id=args.job_id or "")
    elif args.action == "release":
        ledger.release(args.entry, note=args.note or "manual release")
    _print_json(ledger.public_view(cap))
    return 0


def cmd_deploy_hint(args: argparse.Namespace) -> int:
    command = safe_deploy_hint(args.model)
    _print_json(
        {
            "do_not_run_during_the_hackathon": True,
            "reason": "Training does not host models on Veri. If an endpoint is ever created, min replicas must be 0.",
            "create_scale_to_zero": command,
            "stop": ["veri", "deployments", "stop", "<deployment_id>"],
        }
    )
    if "--min-replicas" not in command or "0" not in command:
        raise ContractError("scale-to-zero command is missing --min-replicas 0")
    return 0


def _add_runs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runs-dir", default=None, help="Default: <repo>/runs")


def _add_price_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-usd-per-mtok", default=None)
    parser.add_argument("--output-usd-per-mtok", default=None)


def _add_label_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--labels", required=True)
    parser.add_argument("--pages-dir", default=None)
    parser.add_argument("--slice", default=None)
    parser.add_argument("--max-page-tokens", type=int, default=2000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="guardtrain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    fmt = sub.add_parser("format", help="Write an SFT JSONL from label rows")
    fmt.add_argument("--labels", required=True)
    fmt.add_argument("--out", required=True)
    fmt.add_argument("--meta-out", default=None)
    fmt.add_argument("--pages-dir", default=None)
    fmt.add_argument("--max-page-tokens", type=int, default=2000)
    fmt.add_argument("--test-id-file", action="append", default=[])
    fmt.add_argument("--system-in-user", action="store_true")
    fmt.add_argument("--hide-held-out-labels", action="store_true")
    fmt.set_defaults(func=cmd_format)

    rnd = sub.add_parser("round", help="Train round N on Veri (or --dry-run)")
    rnd.add_argument("--round", type=int, required=True)
    rnd.add_argument("--labels", default=None, help="This round's train JSONL. Default: data/trainset/roundN/labels.jsonl")
    rnd.add_argument("--dev", default=None, help="Dev JSONL. Default: <train dir>/dev/labels.jsonl when that file exists.")
    rnd.add_argument(
        "--attacker",
        default=None,
        help="Optional attacker JSONL rendered from specs. Default: data/attacker/roundN/labels.jsonl when present.",
    )
    rnd.add_argument("--train-sample", type=int, default=64)
    rnd.add_argument("--misses", action="append", default=[])
    rnd.add_argument("--older-misses", action="append", default=[])
    rnd.add_argument("--replay-fraction", type=float, default=0.2)
    rnd.add_argument("--seed", type=int, default=0)
    rnd.add_argument("--dry-run", action="store_true")
    rnd.add_argument("--dpo", action="store_true")
    rnd.add_argument("--base-model", default=PRIMARY_BASE_MODEL)
    rnd.add_argument("--max-wall-minutes", type=int, default=None, help="Unset sizes the wall to the epoch plan.")
    rnd.add_argument(
        "--epochs",
        type=int,
        default=DEFAULT_EPOCHS,
        help="1 or 2. The cap is 2. Dev trick_f1 minus the false-block rate is the early-stop metric.",
    )
    rnd.add_argument("--retrain-from-base", action="store_true", help="Retrain from the public instruct base when a push did not land.")
    rnd.add_argument("--distilled", default=None, help="Teacher JSONL. Default: distilled.jsonl next to the train labels.")
    rnd.add_argument("--max-queue-minutes", type=int, default=30)
    rnd.add_argument("--max-steps", type=int, default=400)
    rnd.add_argument("--spend-cap", default=VERI_HARD_CAP_USD)
    rnd.add_argument("--poll-seconds", type=float, default=30)
    rnd.add_argument("--max-page-tokens", type=int, default=2000)
    rnd.add_argument("--system-in-user", action="store_true")
    rnd.add_argument("--hide-held-out-labels", action="store_true")
    rnd.add_argument("--lora-rank", type=int, default=16)
    rnd.add_argument("--lora-alpha", type=int, default=32)
    rnd.add_argument("--learning-rate", type=float, default=None)
    rnd.add_argument("--grad-accum", type=int, default=8)
    rnd.add_argument("--pages-dir", default=None)
    rnd.add_argument("--min-rows", type=int, default=MIN_TRAIN_ROWS)
    rnd.add_argument("--test-id-file", action="append", default=[])
    _add_runs(rnd)
    rnd.set_defaults(func=cmd_round)

    rev = sub.add_parser(
        "round-eval",
        help="Score train, dev, and the frozen test set. Writes runs/rN/replay.jsonl and summary.json.",
    )
    rev.add_argument("--round", type=int, required=True)
    rev.add_argument(
        "--train-labels",
        default=None,
        help="With --round 0, score the base model on these train pages before training.",
    )
    rev.add_argument("--dev", default=None, help="Dev JSONL for --round 0. Default: <train labels>/dev/labels.jsonl.")
    rev.add_argument("--labels", default=None, help="Frozen test labels. Default: data/testset/labels.jsonl")
    rev.add_argument("--pages-dir", default=None)
    rev.add_argument("--slice", default=None, help="Default: gym/testset/slice100.txt")
    rev.add_argument("--backend", choices=["mock", "http", "ollama", "llama-cpp"], default="ollama")
    rev.add_argument("--url", default="http://127.0.0.1:8000/check")
    rev.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    rev.add_argument("--ollama-model", default="guard-qwen3")
    rev.add_argument("--llama-url", default="http://127.0.0.1:8081/v1")
    rev.add_argument("--llama-model", default="guard")
    rev.add_argument("--adapter", default="json")
    rev.add_argument("--max-page-tokens", type=int, default=2000)
    _add_runs(rev)
    rev.set_defaults(func=cmd_round_eval)

    sw = sub.add_parser("sweep", help="Train up to 4 Veri jobs and pick the winner on dev")
    sw.add_argument("--round", type=int, required=True)
    sw.add_argument("--sweep", required=True, help="YAML or JSON grid of learning_rate and lora_rank")
    sw.add_argument("--labels", default=None)
    sw.add_argument("--dev", default=None)
    sw.add_argument("--attacker", default=None)
    sw.add_argument("--train-sample", type=int, default=64)
    sw.add_argument("--misses", action="append", default=[])
    sw.add_argument("--older-misses", action="append", default=[])
    sw.add_argument("--replay-fraction", type=float, default=0.2)
    sw.add_argument("--seed", type=int, default=0)
    sw.add_argument("--dry-run", action="store_true")
    sw.add_argument("--submit", action="store_true", help="Submit paid Veri jobs. Without this flag the sweep is a dry run.")
    sw.add_argument("--dpo", action="store_true", help="Ignored. Set dpo: true in the sweep file.")
    sw.add_argument("--base-model", default=PRIMARY_BASE_MODEL)
    sw.add_argument("--max-wall-minutes", type=int, default=None, help="Unset sizes the wall to the epoch plan.")
    sw.add_argument(
        "--epochs",
        type=int,
        default=DEFAULT_EPOCHS,
        help="1 or 2. The cap is 2. Dev trick_f1 minus the false-block rate is the early-stop metric.",
    )
    sw.add_argument("--retrain-from-base", action="store_true")
    sw.add_argument("--distilled", default=None)
    sw.add_argument("--max-queue-minutes", type=int, default=30)
    sw.add_argument("--max-steps", type=int, default=400)
    sw.add_argument("--spend-cap", default=VERI_HARD_CAP_USD)
    sw.add_argument("--poll-seconds", type=float, default=30)
    sw.add_argument("--max-page-tokens", type=int, default=2000)
    sw.add_argument("--system-in-user", action="store_true")
    sw.add_argument("--hide-held-out-labels", action="store_true")
    sw.add_argument("--lora-rank", type=int, default=16)
    sw.add_argument("--lora-alpha", type=int, default=32)
    sw.add_argument("--learning-rate", type=float, default=None)
    sw.add_argument("--grad-accum", type=int, default=8)
    sw.add_argument("--pages-dir", default=None)
    sw.add_argument("--min-rows", type=int, default=MIN_TRAIN_ROWS)
    sw.add_argument("--test-id-file", action="append", default=[])
    sw.add_argument("--backend", choices=["mock", "http", "ollama", "llama-cpp"], default=None)
    sw.add_argument("--score-test", action="store_true", help="Score the frozen test set for the dev winner only.")
    sw.add_argument("--test-labels", default=None)
    sw.add_argument("--slice", default=None)
    sw.add_argument("--url", default="http://127.0.0.1:8000/check")
    sw.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    sw.add_argument("--ollama-model", default="guard-qwen3")
    sw.add_argument("--llama-url", default="http://127.0.0.1:8081/v1")
    sw.add_argument("--llama-model", default="guard")
    sw.add_argument("--adapter", default="json")
    _add_runs(sw)
    sw.set_defaults(func=cmd_sweep)

    sws = sub.add_parser("sweep-score", help="Score sweep trials on dev. Test scores are the winner only.")
    sws.add_argument("--round", type=int, required=True)
    sws.add_argument("--trial", default=None, help="The one trial to score. Required.")
    sws.add_argument("--model", default=None, help="Served name guard-rN-<trial>. Required, and unique across trials.")
    sws.add_argument("--testset", action="store_true", help="Score the frozen test set for the dev winner only.")
    sws.add_argument(
        "--launch-dpo",
        action="store_true",
        help="After a dev winner exists, build dev-only pairs and launch one DPO job.",
    )
    sws.add_argument("--dry-run", action="store_true", help="With --launch-dpo, write pairs and do not call Veri.")
    sws.add_argument("--labels", default=None)
    sws.add_argument("--pages-dir", default=None)
    sws.add_argument("--slice", default=None)
    sws.add_argument("--backend", choices=["mock", "http", "ollama", "llama-cpp"], default="ollama")
    sws.add_argument("--url", default="http://127.0.0.1:8000/check")
    sws.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    sws.add_argument("--ollama-model", default="guard-qwen3")
    sws.add_argument("--llama-url", default="http://127.0.0.1:8081/v1")
    sws.add_argument("--llama-model", default="guard")
    sws.add_argument("--adapter", default="json")
    sws.add_argument("--max-page-tokens", type=int, default=2000)
    _add_runs(sws)
    sws.set_defaults(func=cmd_sweep_score)

    conv = sub.add_parser("convert", help="Plan or run llama.cpp GGUF conversion")
    conv.add_argument("--hf-dir", default=None)
    conv.add_argument("--hf-repo", default=None, help="Private merged repo to pull, under shardulmarathe/.")
    conv.add_argument("--base-model", default=None)
    conv.add_argument("--outfile", required=True)
    conv.add_argument("--outtype", default="q8_0")
    conv.add_argument("--llama-cpp-dir", default=None)
    conv.add_argument("--quantize", default=None)
    conv.add_argument("--dry-run", action="store_true")
    conv.set_defaults(func=cmd_convert)

    merge = sub.add_parser("merge", help="Merge a downloaded LoRA adapter into the base model")
    merge.add_argument("--adapter", required=True)
    merge.add_argument("--base", default=PRIMARY_BASE_MODEL)
    merge.add_argument("--out", required=True)
    merge.add_argument("--dry-run", action="store_true")
    merge.set_defaults(func=cmd_merge)

    srv = sub.add_parser("serve", help="FastAPI /check on 0.0.0.0:$PORT")
    srv.add_argument("--backend", choices=["mock", "ollama", "llama-cpp"], default="ollama")
    srv.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    srv.add_argument("--ollama-model", default="guard-qwen3")
    srv.add_argument("--llama-url", default="http://127.0.0.1:8081/v1")
    srv.add_argument("--llama-model", default="guard")
    srv.add_argument("--adapter", default="json", choices=["json", "qwen3guard", "auto"])
    srv.add_argument("--max-tokens", type=int, default=512)
    srv.add_argument("--max-page-tokens", type=int, default=2000)
    srv.add_argument("--port", type=int, default=None)
    srv.add_argument("--dry-run", action="store_true")
    srv.set_defaults(func=cmd_serve)

    ev = sub.add_parser("eval", help="Score a local or mock guard")
    _add_label_flags(ev)
    ev.add_argument("--model", required=True)
    ev.add_argument("--round", default="base")
    ev.add_argument("--page-set", default="testset")
    ev.add_argument("--also-slice", action="store_true")
    ev.add_argument("--backend", choices=["mock", "http", "ollama", "llama-cpp"], default="mock")
    ev.add_argument("--url", default="http://127.0.0.1:8000/check")
    ev.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ev.add_argument("--ollama-model", default="guard-qwen3")
    ev.add_argument("--llama-url", default="http://127.0.0.1:8081/v1")
    ev.add_argument("--llama-model", default="guard")
    ev.add_argument("--adapter", default="json")
    ev.add_argument("--max-tokens", type=int, default=512)
    ev.add_argument("--limit", type=int, default=None)
    _add_price_flags(ev)
    _add_runs(ev)
    ev.set_defaults(func=cmd_eval)

    loc = sub.add_parser("baseline-local", help="Untrained Qwen3-4B or Qwen3Guard via local GGUF")
    _add_label_flags(loc)
    loc.add_argument("--model", required=True, choices=["qwen3-4b", "qwen3guard-4b"])
    loc.add_argument("--round", default="base")
    loc.add_argument("--page-set", default="testset")
    loc.add_argument("--also-slice", action="store_true")
    loc.add_argument("--backend", choices=["http", "ollama", "llama-cpp"], default="ollama")
    loc.add_argument("--url", default="http://127.0.0.1:8000/check")
    loc.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    loc.add_argument("--ollama-model", default=None, help="Default: the local convert of the same HF repo")
    loc.add_argument("--llama-url", default="http://127.0.0.1:8081/v1")
    loc.add_argument("--llama-model", default="qwen3")
    loc.add_argument("--adapter", default="auto")
    loc.add_argument("--max-tokens", type=int, default=512)
    loc.add_argument("--dry-run", action="store_true")
    _add_price_flags(loc)
    _add_runs(loc)
    loc.set_defaults(func=cmd_baseline_local)

    gem = sub.add_parser("baseline-gemini", help="Gemini through the Stanford OpenAI-compatible gateway")
    _add_label_flags(gem)
    gem.add_argument("--model", default="gemini-3.7-flash")
    gem.add_argument("--round", default="base")
    gem.add_argument("--page-set", default="testset")
    gem.add_argument("--probe", type=int, default=None)
    gem.add_argument("--seed", type=int, default=0)
    gem.add_argument("--thinking-level", default="low")
    gem.add_argument("--max-tokens", type=int, default=None, help="Default 256, or 1024 for Gemini Pro")
    gem.add_argument("--spend-cap", default=GEMINI_HARD_CAP_USD)
    gem.add_argument("--allow-full-testset", action="store_true")
    gem.add_argument("--dry-run", action="store_true")
    _add_price_flags(gem)
    _add_runs(gem)
    gem.set_defaults(func=cmd_baseline_gemini)

    ant = sub.add_parser("baseline-anthropic", help="Claude Sonnet 5.5")
    _add_label_flags(ant)
    ant.add_argument("--model", default="claude-sonnet-5-5")
    ant.add_argument("--round", default="base")
    ant.add_argument("--page-set", default="testset")
    ant.add_argument("--also-slice", action="store_true")
    ant.add_argument("--probe", type=int, default=None)
    ant.add_argument("--seed", type=int, default=0)
    ant.add_argument("--effort", default="low")
    ant.add_argument("--max-tokens", type=int, default=512)
    ant.add_argument("--spend-cap", default=ANTHROPIC_DEFAULT_CAP_USD)
    ant.add_argument("--dry-run", action="store_true")
    _add_price_flags(ant)
    _add_runs(ant)
    ant.set_defaults(func=cmd_baseline_anthropic)

    led = sub.add_parser("ledger", help="Show or reconcile a spend ledger")
    led.add_argument("action", choices=["show", "settle", "release"])
    led.add_argument("--which", choices=["veri", "gemini", "anthropic"], default="veri")
    led.add_argument("--entry", default=None)
    led.add_argument("--actual", default=None)
    led.add_argument("--job-id", default=None)
    led.add_argument("--note", default=None)
    led.add_argument("--spend-cap", default=None)
    _add_runs(led)
    led.set_defaults(func=cmd_ledger)

    hint = sub.add_parser("deploy-hint", help="Print the only allowed Veri deploy command (do not run it)")
    hint.add_argument("--model", default=PRIMARY_BASE_MODEL)
    hint.set_defaults(func=cmd_deploy_hint)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SpendCapExceeded as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        return 3
    except MissingKeyError as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        return 4
    except ContractError as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        return 2
    except VeriCLIError as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        text = str(exc)
        if "VERI_API_KEY" in text or "not set" in text:
            return 4
        return 1
    except ApiCallError as exc:
        sys.stderr.write(redact(str(exc)) + "\n")
        return 1
