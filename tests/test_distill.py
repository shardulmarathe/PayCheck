"""Opus distillation stays offline. The teacher client is injected."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))

from gym.distill import (  # noqa: E402
    DEFAULT_MAX_USD,
    TEACHER_MODEL,
    distill_round,
    teacher_request,
)
from guardtrain.ledger import SpendLedger  # noqa: E402
from guardtrain.prompts import dump_output  # noqa: E402


def _write_round(tmp: Path, rows: list[dict]) -> Path:
    labels = tmp / "labels.jsonl"
    text = tmp / "text"
    text.mkdir(parents=True)
    lines = []
    for row in rows:
        page_id = row["page_id"]
        (text / f"{page_id}.txt").write_text(row.pop("page_text"), encoding="utf-8")
        lines.append(json.dumps(row))
    labels.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return labels


def _row(page_id: str, *, verdict: str = "block", attack: str = "hidden_fees", text: str | None = None) -> dict:
    if text is None:
        text = "url: http://shop.example/checkout/order\nA service fee was added to the total."
    family = "clean" if verdict == "pass" else "upsell"
    return {
        "page_id": page_id,
        "store": "bean",
        "family": family,
        "attack_type": "none" if verdict == "pass" else attack,
        "verdict": verdict,
        "selector": "" if verdict == "pass" else "#fee",
        "bbox": None,
        "evidence_text": "" if verdict == "pass" else "service fee",
        "instruction": "" if verdict == "pass" else "Remove the service fee before paying.",
        "source": "template",
        "split": "train",
        "page_text": text,
    }


def _reply(payload: dict, *, usage: dict | None = None):
    body = json.dumps(payload)
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=body)],
        usage=SimpleNamespace(
            input_tokens=(usage or {}).get("input_tokens", 20),
            output_tokens=(usage or {}).get("output_tokens", 30),
            cache_creation_input_tokens=(usage or {}).get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=(usage or {}).get("cache_read_input_tokens", 0),
        ),
    )


def test_default_cap_is_fifty_and_only_opus() -> None:
    assert DEFAULT_MAX_USD == "50"
    request = teacher_request("system text", "user text")
    assert request["model"] == TEACHER_MODEL == "claude-opus-5-5"
    assert request["output_config"] == {"effort": "low"}
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert request["system"][0]["text"] == "system text"


def test_keeps_matching_verdicts_and_falls_back_on_disagreement(tmp_path: Path) -> None:
    labels = _write_round(
        tmp_path / "round",
        [
            _row("r1-hidden_fees-000"),
            _row("r1-none-000", verdict="pass", text="url: http://shop.example/cart/page\nOrder total $5.00."),
            _row(
                "r1-hidden_fees-001",
                text="url: http://shop.example/checkout/order\nA service fee was added. second checkout",
            ),
        ],
    )
    seen = []

    def create_fn(**kwargs):
        seen.append(kwargs)
        user = kwargs["messages"][0]["content"]
        if "Order total" in user:
            return _reply(
                {
                    "verdict": "pass",
                    "attack_type": "none",
                    "evidence": "",
                    "instruction": "",
                }
            )
        if "second checkout" in user:
            return _reply(
                {
                    "verdict": "pass",
                    "attack_type": "none",
                    "evidence": "",
                    "instruction": "",
                }
            )
        return _reply(
            {
                "verdict": "block",
                "attack_type": "hidden_fees",
                "evidence": "service fee",
                "instruction": "Remove the service fee before paying.",
            }
        )

    result = distill_round(
        round_index=1,
        labels=labels,
        max_usd="50",
        ledger_path=tmp_path / "teacher.json",
        cache_dir=tmp_path / "cache",
        repo=tmp_path,
        create_fn=create_fn,
        workers=2,
    )
    assert result["model"] == "claude-opus-5-5"
    assert result["stopped_for_cap"] is False
    rows = [json.loads(line) for line in Path(result["out"]).read_text().splitlines()]
    by_id = {row["page_id"]: row for row in rows}
    assert by_id["r1-hidden_fees-000"]["source"] == "teacher"
    assert by_id["r1-hidden_fees-000"]["verdict_agreement"] is True
    assert "service fee" in by_id["r1-hidden_fees-000"]["target"]
    assert by_id["r1-none-000"]["source"] == "teacher"
    assert by_id["r1-hidden_fees-001"]["source"] == "label"
    assert by_id["r1-hidden_fees-001"]["verdict_agreement"] is False
    assert '"verdict":"block"' in by_id["r1-hidden_fees-001"]["target"]
    assert seen
    assert seen[0]["model"] == "claude-opus-5-5"
    assert "r1-hidden_fees-000" not in seen[0]["messages"][0]["content"]
    assert "/checkout/" not in seen[0]["messages"][0]["content"]
    ledger = SpendLedger(tmp_path / "teacher.json", "50", quant="micro")
    assert ledger.totals().settled > 0
    assert ledger.totals().reserved == 0


def test_cache_hit_does_not_call_and_cap_is_cumulative(tmp_path: Path) -> None:
    labels = _write_round(tmp_path / "round", [_row("r1-hidden_fees-000")])
    calls = {"n": 0}

    def create_fn(**kwargs):
        calls["n"] += 1
        return _reply(
            {
                "verdict": "block",
                "attack_type": "hidden_fees",
                "evidence": "service fee",
                "instruction": "Leave the extra fee off the total.",
            },
            usage={"input_tokens": 10, "output_tokens": 12, "cache_creation_input_tokens": 40},
        )

    first = distill_round(
        round_index=1,
        labels=labels,
        max_usd="50",
        ledger_path=tmp_path / "teacher.json",
        cache_dir=tmp_path / "cache",
        repo=tmp_path,
        create_fn=create_fn,
    )
    spent = SpendLedger(tmp_path / "teacher.json", "50", quant="micro").totals().settled
    assert calls["n"] == 1
    assert spent > 0
    second = distill_round(
        round_index=1,
        labels=labels,
        max_usd="50",
        ledger_path=tmp_path / "teacher.json",
        cache_dir=tmp_path / "cache",
        repo=tmp_path,
        create_fn=create_fn,
    )
    assert calls["n"] == 1
    assert second["cache_hits"] == 1
    again = SpendLedger(tmp_path / "teacher.json", "50", quant="micro").totals().settled
    assert again == spent
    assert first["teacher_kept"] == 1

    seeded = SpendLedger(tmp_path / "full.json", "50", quant="micro")
    entry = seeded.authorize("49.99", note="earlier rounds", requested_cap="50")
    seeded.settle(entry, "49.99")

    def boom(**_kwargs):
        raise AssertionError("cap must stop before the call")

    stopped = distill_round(
        round_index=1,
        labels=labels,
        max_usd="50",
        ledger_path=tmp_path / "full.json",
        cache_dir=tmp_path / "empty-cache",
        repo=tmp_path,
        create_fn=boom,
    )
    assert stopped["stopped_for_cap"] is True
    assert stopped["asked"] == 0


def test_retries_429_then_keeps_the_answer(tmp_path: Path) -> None:
    labels = _write_round(tmp_path / "round", [_row("r1-hidden_fees-000")])
    sleeps = []
    state = {"n": 0}

    class Limited(Exception):
        status_code = 429

    def create_fn(**_kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise Limited("slow down")
        return _reply(
            {
                "verdict": "block",
                "attack_type": "hidden_fees",
                "evidence": "service fee",
                "instruction": "Remove the service fee before paying.",
            }
        )

    result = distill_round(
        round_index=1,
        labels=labels,
        ledger_path=tmp_path / "teacher.json",
        cache_dir=tmp_path / "cache",
        repo=tmp_path,
        create_fn=create_fn,
        sleeper=lambda attempt: sleeps.append(attempt),
    )
    assert sleeps == [0]
    assert state["n"] == 2
    assert result["teacher_kept"] == 1
    assert SpendLedger(tmp_path / "teacher.json", "50", quant="micro").totals().reserved == 0


def test_refuses_dev_and_frozen_ids(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    labels = _write_round(dev, [_row("r1-hidden_fees-000")])
    with pytest.raises(SystemExit, match="train pages only"):
        distill_round(
            round_index=1,
            labels=labels,
            ledger_path=tmp_path / "teacher.json",
            cache_dir=tmp_path / "cache",
            repo=tmp_path,
            create_fn=lambda **_kwargs: None,
        )

    frozen_root = tmp_path / "repo"
    frozen_dir = frozen_root / "data" / "testset"
    frozen_dir.mkdir(parents=True)
    (frozen_dir / "labels.jsonl").write_text(
        json.dumps({"page_id": "test-hidden_fees-000", "verdict": "block", "attack_type": "hidden_fees"}) + "\n",
        encoding="utf-8",
    )
    train = _write_round(tmp_path / "train", [_row("test-hidden_fees-000")])
    with pytest.raises(SystemExit, match="frozen-test"):
        distill_round(
            round_index=1,
            labels=train,
            ledger_path=tmp_path / "teacher.json",
            cache_dir=tmp_path / "cache2",
            repo=frozen_root,
            create_fn=lambda **_kwargs: None,
        )


def test_concurrency_stays_at_eight(tmp_path: Path) -> None:
    rows = [_row(f"r1-hidden_fees-{index:03d}") for index in range(10)]
    labels = _write_round(tmp_path / "round", rows)
    inflight = {"n": 0, "max": 0}
    lock = threading.Lock()

    def create_fn(**_kwargs):
        with lock:
            inflight["n"] += 1
            inflight["max"] = max(inflight["max"], inflight["n"])
        time.sleep(0.05)
        with lock:
            inflight["n"] -= 1
        return _reply(
            {
                "verdict": "block",
                "attack_type": "hidden_fees",
                "evidence": "service fee",
                "instruction": "Remove the service fee before paying.",
            }
        )

    result = distill_round(
        round_index=1,
        labels=labels,
        ledger_path=tmp_path / "teacher.json",
        cache_dir=tmp_path / "cache",
        repo=tmp_path,
        create_fn=create_fn,
        workers=32,
    )
    assert result["workers"] == 8
    assert result["max_inflight"] <= 8
    assert inflight["max"] <= 8
    assert result["rows"] == 10


def test_long_teacher_json_falls_back_to_the_label(tmp_path: Path) -> None:
    labels = _write_round(tmp_path / "round", [_row("r1-hidden_fees-000")])

    def create_fn(**_kwargs):
        return _reply(
            {
                "verdict": "block",
                "attack_type": "hidden_fees",
                "evidence": "service fee " + ("extra " * 80),
                "instruction": "Remove the service fee before paying. " + ("now " * 40),
            }
        )

    # Evidence must be a substring. A long quote that is not in the page falls back too.
    result = distill_round(
        round_index=1,
        labels=labels,
        ledger_path=tmp_path / "teacher.json",
        cache_dir=tmp_path / "cache",
        repo=tmp_path,
        create_fn=create_fn,
    )
    row = json.loads(Path(result["out"]).read_text().splitlines()[0])
    assert row["source"] == "label"
    assert row["verdict_agreement"] is True
    assert len(row["target"]) < 400
    assert dump_output(
        {
            "verdict": "block",
            "attack_type": "hidden_fees",
            "evidence": "service fee",
            "instruction": "Remove the service fee before paying.",
        }
    ) == row["target"]


def test_missing_key_exits_before_a_live_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    labels = _write_round(tmp_path / "round", [_row("r1-hidden_fees-000")])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ANTHROPIC_API_KEY"):
        distill_round(
            round_index=1,
            labels=labels,
            ledger_path=tmp_path / "teacher.json",
            cache_dir=tmp_path / "cache",
            repo=tmp_path,
            create_fn=None,
        )
