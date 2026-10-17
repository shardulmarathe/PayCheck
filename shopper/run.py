"""Shopper CLI.

``python -m shopper.run --errand all --mode both --mock --guard-backend mock``
runs every gym errand with and without the guard, offline. Without ``--mock``
the shopper is Claude Haiku through the open-source Browser Use library.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import urllib.request
import uuid
from pathlib import Path

from shopper.cost import CostLedger
from shopper.guard import GuardClient, load_catalog
from shopper.replay import is_synthetic, output_dir, write_tally

DEFAULT_MODEL = "claude-haiku-5-5"
_OK_OUTCOMES = {"clean", "protected", "fell", "incomplete", "stopped"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the checkout-guard shopper against the gym.")
    parser.add_argument("--errand", default="all", help="errand id, or 'all'")
    parser.add_argument("--mode", choices=("unguarded", "guarded", "both"), default="both")
    parser.add_argument("--guard-url", default=os.environ.get("GUARD_URL") or "", help="guard origin; /check is appended")
    parser.add_argument("--guard-backend", choices=("mock", "http"), default="http")
    parser.add_argument("--mock", action="store_true", help="offline shopper; no Anthropic key and no Browser Use cloud")
    parser.add_argument("--max-usd", type=float, default=3.0, help="stop when cumulative Anthropic spend reaches this many dollars")
    parser.add_argument("--ledger", default="runs/shopper/ledger.json", help="cumulative spend file checked by --max-usd")
    parser.add_argument("--reset-ledger", action="store_true", help="zero the ledger before this invocation")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765", help="gym server, from python -m gym.serve")
    parser.add_argument("--out", default=None, help="replay directory; default splits real and synthetic runs")
    parser.add_argument("--video", action="store_true", help="save a Playwright webm per run under shots/")
    parser.add_argument("--max-steps", type=int, default=18)
    parser.add_argument("--model", default=os.environ.get("SHOPPER_MODEL") or DEFAULT_MODEL)
    return parser


def _modes(value: str) -> list[str]:
    if value == "both":
        return ["unguarded", "guarded"]
    return [value]


def _health(base_url: str) -> None:
    url = base_url.rstrip("/") + "/health"
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read().decode()
    if "ok" not in body:
        raise RuntimeError(f"gym health check failed at {url}")


def _select(catalog: list[dict], errand: str) -> list[dict]:
    if errand == "all":
        return list(catalog)
    chosen = [row for row in catalog if row.get("id") == errand]
    if not chosen:
        known = ", ".join(row.get("id", "") for row in catalog)
        raise SystemExit(f"unknown errand {errand!r}; known: {known}")
    return chosen


async def _run(args: argparse.Namespace) -> int:
    from shopper.drive import run_errand

    logging.getLogger("browser_use").setLevel(logging.WARNING)
    base_url = args.base_url.rstrip("/")
    _health(base_url)
    catalog = load_catalog(base_url)
    errands = _select(catalog, args.errand)
    modes = _modes(args.mode)
    guard = None
    if "guarded" in modes:
        guard = GuardClient(backend=args.guard_backend, guard_url=args.guard_url or None, catalog=catalog)
    ledger_path = Path(args.ledger) if args.ledger else None
    ledger = CostLedger(args.max_usd, ledger_path)
    if args.reset_ledger:
        ledger.reset()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    run_id = uuid.uuid4().hex
    exit_code = 0
    written: list[Path] = []
    for errand in errands:
        for mode in modes:
            synthetic = is_synthetic(
                mock=args.mock,
                mode=mode,
                guard_backend=args.guard_backend if mode == "guarded" else None,
            )
            dest = output_dir(args.out, synthetic)
            try:
                document = await run_errand(
                    errand=errand,
                    mode=mode,
                    base_url=base_url,
                    out_dir=dest,
                    guard=guard if mode == "guarded" else None,
                    mock=args.mock,
                    model=args.model,
                    ledger=ledger,
                    video=args.video,
                    max_steps=args.max_steps,
                    api_key=api_key,
                    run_id=run_id,
                    synthetic=synthetic,
                )
            except Exception as exc:
                print(f"{errand.get('id')} {mode} error {type(exc).__name__}: {exc}", file=sys.stderr)
                exit_code = 1
                continue
            written.append(dest)
            print(
                f"{document['errand_id']} {document['mode']} {document['outcome']} "
                f"charged={document['amount_charged_cents']} "
                f"overcharge={document['overcharge_usd']} "
                f"exposed={document['exposed']} "
                f"usd={document['usd_spent']}"
            )
            if document["outcome"] not in _OK_OUTCOMES:
                exit_code = 1
    for dest in dict.fromkeys(written):
        tally = write_tally(dest, run_id)
        print(
            f"tally {dest} synthetic={tally['synthetic']} "
            f"without_guard overcharge={tally['without_guard']['overcharge_usd']} "
            f"exposed={tally['without_guard']['exposed']} "
            f"with_guard overcharge={tally['with_guard']['overcharge_usd']} "
            f"spent={ledger.usd:.4f}"
        )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_usd < 0:
        print("--max-usd must be >= 0", file=sys.stderr)
        return 1
    flags = {
        is_synthetic(mock=args.mock, mode=mode, guard_backend=args.guard_backend if mode == "guarded" else None)
        for mode in _modes(args.mode)
    }
    if args.out and len(flags) > 1:
        print("refusing to mix synthetic and real runs in one --out directory", file=sys.stderr)
        return 1
    if args.max_steps < 1:
        print("--max-steps must be >= 1", file=sys.stderr)
        return 1
    if not args.mock and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is required unless --mock is set", file=sys.stderr)
        return 1
    if "guarded" in _modes(args.mode) and args.guard_backend == "http" and not (args.guard_url or "").strip():
        print("GUARD_URL or --guard-url is required when --guard-backend http", file=sys.stderr)
        return 1
    try:
        return asyncio.run(_run(args))
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        print(exc, file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
