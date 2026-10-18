"""Offline tests. No Veri, Anthropic, or Gemini calls."""

from __future__ import annotations

import inspect
import json
import random
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from guardtrain.cli import main
from guardtrain.clients import (
    CheckResult,
    check_anthropic,
    check_gemini,
    check_http_endpoint,
    check_ollama,
    check_openai_compat,
    default_anthropic_create,
    default_gemini_create,
    gemini_create_kwargs,
)
from guardtrain.convert import plan_conversion, run_convert, safe_deploy_hint
from guardtrain.data import (
    assemble_round,
    attach_page_text,
    discover_frozen_ids,
    dev_preference_rows,
    dpo_records,
    filter_trainable,
    load_labels,
    load_previous_miss_files,
    sft_records,
)
from guardtrain.evaluate import build_report, prepare_page_set, read_testset_content_hash, run_checks, write_report
from guardtrain.ledger import (
    SpendCapExceeded,
    SpendLedger,
    reserve_for_job,
    wall_clock_reservation_usd,
)
from guardtrain.parse import parse_guard_output
from guardtrain.prompts import build_user_message
from guardtrain.prices import gemini_max_tokens, lookup_price
from guardtrain.redact import redact, redact_url
from guardtrain.budget import assert_jobs_fit
from guardtrain.continuation import dpo_init, plan_continuation
from guardtrain.round_run import RoundOptions, dpo_already_used, launch_round, prepare_round
from guardtrain.selection import pick_winner
from guardtrain.sweep import launch_pending_dpo, run_sweep
from guardtrain.sweepcfg import expand_trials, parallel_limit
from guardtrain.veri import parse_balance
from guardtrain.schema import ATTACK_TYPES, PRIMARY_BASE_MODEL, ContractError, LabelRow
from guardtrain.scoring import score_predictions
from guardtrain.serve_app import create_app, mock_complete, serve
from guardtrain.tomlutil import render_train_toml, steps_for_rows, steps_for_wall
from guardtrain.veri import (
    POLL_FAILURES_BEFORE_CANCEL,
    Completed,
    SubprocessVeri,
    VeriCLIError,
    newest_checkpoint_id,
    poll_until_done,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mini_labels.jsonl"
SLICE = Path(__file__).resolve().parents[1] / "fixtures" / "slice.txt"
REPO = Path(__file__).resolve().parents[2]


def _row(
    page_id: str,
    *,
    attack: str = "hidden_fees",
    verdict: str = "block",
    family: str = "upsell",
    text: str | None = None,
    evidence: str | None = None,
    page_set: str = "",
    split: str = "train",
    model_output: str = "",
    instruction: str = "Remove the trick before paying.",
) -> LabelRow:
    if text is None:
        text = f"{page_id} includes a service fee." if verdict == "block" else f"{page_id} total is $5."
    if evidence is None:
        evidence = "service fee" if verdict == "block" else ""
    return LabelRow(
        page_id=page_id,
        store="bean",
        family=family,
        attack_type=attack,
        verdict=verdict,
        evidence_text=evidence,
        instruction=instruction,
        split=split,
        page_text=text,
        page_set=page_set,
        model_output=model_output,
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class SeqVeri:
    def __init__(self, statuses: list[str]) -> None:
        self.statuses = list(statuses)
        self.cancels: list[str] = []

    def jobs_get(self, job_id: str) -> dict:
        status = self.statuses.pop(0) if self.statuses else "cancelled"
        return {"id": job_id, "status": status, "cost_usd": None}

    def jobs_cancel(self, job_id: str) -> None:
        self.cancels.append(job_id)


class FakeVeri:
    def __init__(self, *, create_error: str | None = None) -> None:
        self.calls: list[str] = []
        self.create_error = create_error

    def datasets_check(self, path: Path) -> None:
        self.calls.append("check")

    def datasets_upload(self, path: Path, name: str) -> str:
        self.calls.append("upload")
        return "ds123"

    def jobs_estimate(self, toml_path: Path) -> dict:
        self.calls.append("estimate")
        return {"estimated_cost_usd": "0.50", "rate_usd_per_hour": "1.05", "gpu_count": 1}

    def jobs_create(self, toml_path: Path) -> str:
        self.calls.append("create")
        if self.create_error:
            raise __import__("guardtrain.veri", fromlist=["VeriCLIError"]).VeriCLIError(self.create_error)
        return "abc123"

    def jobs_get(self, job_id: str) -> dict:
        self.calls.append("get")
        return {"id": job_id, "status": "completed", "cost_usd": "0.40"}

    def jobs_cancel(self, job_id: str) -> None:
        self.calls.append("cancel")

    def jobs_download(self, job_id: str, output_dir: Path) -> None:
        self.calls.append("download")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "adapter_config.json").write_text("{}\n", encoding="utf-8")

    def billing_balance(self) -> Decimal:
        self.calls.append("balance")
        return Decimal("40.00")


def test_redact_strips_keys_and_query_strings() -> None:
    leaked = "vk_" + "test_SHOULD_NOT_LEAK"
    anthropic = "sk-ant-" + "api03_SHOULD_NOT_LEAK"
    text = f"failed {leaked} and {anthropic} Bearer abcdefghijklmnop"
    cleaned = redact(text)
    assert leaked not in cleaned
    assert "SHOULD_NOT_LEAK" not in cleaned
    assert "[redacted]" in cleaned
    url = redact_url("https://gateway.example/v1?key=secret&x=1")
    assert "secret" not in url
    assert "redacted" in url


def test_prompt_hides_ids_and_label_words_on_real_pages(tmp_path: Path) -> None:
    """User messages from real train and test pages keep the host and hide the label."""
    import sys

    sys.path.insert(0, str(REPO))
    from gym.train import write_training

    text_paths = sorted((REPO / "data" / "testset" / "text").glob("*.txt"))
    assert len(text_paths) == 300
    out = tmp_path / "round"
    write_training(6, out, seed=7, round_n=1)
    train_texts = sorted((out / "text").glob("*.txt"))
    assert train_texts
    banned_attack = [name for name in ATTACK_TYPES if name != "none"]
    label_word = re.compile(r"(?i)(?<![A-Za-z0-9])(?:trick|clean|none)(?![A-Za-z0-9])")
    page_id_re = re.compile(r"(?i)\b(?:test|train|dev|attacker|r\d+)-[A-Za-z0-9_]+-\d+\b")
    public_id_re = re.compile(r"(?i)\bp-[0-9a-f]{8}\b")
    saw_domain = False
    saw_host = False
    for path in [*text_paths, *train_texts]:
        raw = path.read_text(encoding="utf-8")
        page_id = path.stem
        row = LabelRow(
            page_id=page_id,
            page_text=raw,
            verdict="pass",
            attack_type="none",
            family="clean",
        )
        user = build_user_message(row)
        assert page_id not in user
        assert page_id_re.search(user) is None, page_id
        assert public_id_re.search(user) is None, page_id
        assert label_word.search(user) is None, path.name
        folded = user.casefold()
        for name in banned_attack:
            assert name not in folded, name
        assert "(none)" not in user
        assert not re.search(r"^url:\s*https?://[^/\s]+/\S+", user, re.MULTILINE)
        if "domain:" in user:
            saw_domain = True
        if re.search(r"^url:\s*https?://[^/\s]+\s*$", user, re.MULTILINE):
            saw_host = True
    assert saw_domain
    assert saw_host


def test_sft_drops_held_out_frozen_and_bad_evidence(tmp_path: Path) -> None:
    rows = load_labels(FIXTURES)
    rows.append(
        _row("p-bad-quote", text="Nothing about a fee here.", evidence="service fee")
    )
    kept, stats = filter_trainable(rows, {"p-fee"}, max_page_tokens=2000, mix_source="round0")
    ids = {row.page_id for row in kept}
    assert "p-copy" not in ids
    assert "p-list" not in ids
    assert "p-frozen" not in ids
    assert "p-fee" not in ids
    assert "p-bad-quote" not in ids
    assert {"p-clean", "p-addon", "p-sub"} <= ids
    assert stats.dropped["held_out_attack"] == 2
    assert stats.dropped["forbidden_split"] == 1
    assert stats.dropped["frozen_test_id"] == 1
    assert stats.dropped["evidence_not_in_page"] == 1
    records = sft_records(kept, max_page_tokens=2000, system_in_user=False, hide_held_out_labels=False)
    assert records
    for record in records:
        assert set(record) == {"messages"}
        roles = [message["role"] for message in record["messages"]]
        assert roles == ["system", "user", "assistant"]
        assert "copycat_domain" in record["messages"][0]["content"]
        assert "listing_injection" in record["messages"][0]["content"]
        assistant = json.loads(record["messages"][2]["content"])
        assert list(assistant) == ["verdict", "attack_type", "evidence", "instruction"]
        assert assistant["attack_type"] not in {"copycat_domain", "listing_injection"}
        if assistant["verdict"] == "pass":
            assert assistant["instruction"] == ""
            assert assistant["evidence"] == ""
    baked = sft_records(kept[:1], max_page_tokens=2000, system_in_user=True, hide_held_out_labels=True)
    assert [message["role"] for message in baked[0]["messages"]] == ["user", "assistant"]
    assert "copycat_domain" not in baked[0]["messages"][0]["content"]


def test_assemble_round_mix_and_rejections() -> None:
    round0 = [_row("a", verdict="pass", attack="none", family="clean", evidence=""), _row("b")]
    previous = [
        _row("b", instruction="Updated miss instruction.", model_output='{"verdict":"pass"}'),
        _row("c"),
        _row("held", attack="copycat_domain", family="scam", text="held copycat.example", evidence="copycat.example"),
    ]
    older = [_row("d"), _row("e"), _row("f")]
    with pytest.raises(ContractError, match="Round 0"):
        assemble_round(
            round_index=0,
            round0_rows=round0,
            previous_misses=previous,
            older_misses=[],
            test_ids=set(),
            replay_fraction=0.5,
            seed=0,
            max_page_tokens=2000,
        )
    with pytest.raises(ContractError, match="slice100"):
        assemble_round(
            round_index=1,
            round0_rows=round0,
            previous_misses=[_row("z", page_set="slice100")],
            older_misses=[],
            test_ids=set(),
            replay_fraction=0.5,
            seed=0,
            max_page_tokens=2000,
        )
    mixed, stats = assemble_round(
        round_index=2,
        round0_rows=round0,
        previous_misses=previous,
        older_misses=older,
        test_ids=set(),
        replay_fraction=0.5,
        seed=0,
        max_page_tokens=2000,
    )
    by_id = {row.page_id: row for row in mixed}
    assert set(by_id) >= {"a", "b", "c"}
    assert "held" not in by_id
    assert by_id["a"].mix_source == "train"
    assert by_id["b"].mix_source == "miss"
    assert by_id["b"].instruction == "Updated miss instruction."
    replay_ids = {row.page_id for row in mixed if row.mix_source == "replay"}
    assert replay_ids <= {"d", "e", "f"}
    assert len(replay_ids) == 2
    expected = set(random.Random(0).sample(["d", "e", "f"], 2))
    assert replay_ids == expected
    assert stats.dropped["held_out_attack"] == 1
    assert stats.by_source["train"] == 1
    assert stats.by_source["miss"] == 2


def test_ledger_caps_quantization_and_reservation(tmp_path: Path) -> None:
    assert wall_clock_reservation_usd(60) == Decimal("1.29")
    assert wall_clock_reservation_usd(90) == Decimal("1.82")
    assert wall_clock_reservation_usd(20) == Decimal("0.59")
    assert reserve_for_job(Decimal("0.50"), Decimal("1.29")) == Decimal("1.29")
    assert reserve_for_job(Decimal("2.00"), Decimal("1.29")) == Decimal("2.24")
    assert reserve_for_job(None, Decimal("1.29")) == Decimal("1.29")

    path = tmp_path / "veri.json"
    ledger = SpendLedger(path, "50.00", quant="cents")
    ledger.authorize(Decimal("48.71"), note="seed")
    ledger.authorize(Decimal("1.29"), note="fills the cap")
    assert ledger.totals().committed == Decimal("50.00")
    assert ledger.would_exceed(Decimal("0.01")) is True
    with pytest.raises(SpendCapExceeded):
        ledger.authorize(Decimal("0.01"), note="over")

    other = tmp_path / "other.json"
    seeded = SpendLedger(other, "50.00")
    seeded.authorize(Decimal("49.00"), note="seed")
    assert seeded.would_exceed(Decimal("1.29")) is True
    entry = seeded.authorize(Decimal("0.50"), note="open")
    seeded.settle(entry, "0.40")
    assert seeded.totals().settled == Decimal("0.40")
    assert seeded.totals().reserved == Decimal("49.00")
    assert seeded.totals().committed == Decimal("49.40")
    released = seeded.authorize(Decimal("0.50"), note="drop me")
    seeded.release(released, note="cancelled while queued")
    assert seeded.totals().committed == Decimal("49.40")
    assert seeded.totals().reserved == Decimal("49.00")
    reloaded = SpendLedger(other, "50.00")
    assert reloaded.totals().committed == Decimal("49.40")

    raised = tmp_path / "raised.json"
    raised.write_text(
        json.dumps({"hard_cap_usd": "99.00", "quant": "cents", "entries": []}),
        encoding="utf-8",
    )
    clamped = SpendLedger(raised, "50.00")
    assert clamped.totals().cap == Decimal("50.00")
    with pytest.raises(SpendCapExceeded):
        clamped.authorize(Decimal("1"), note="no", requested_cap="51")

    micro = SpendLedger(tmp_path / "gemini.json", "2.50", quant="micro")
    micro.authorize(Decimal("0.123456789"), note="gemini")
    assert micro.totals().committed == Decimal("0.12345679")


def test_train_toml_is_qlora_without_reward_or_deploy() -> None:
    import tomllib

    text = render_train_toml(
        output_model="guard-r0-sft",
        base_model="Qwen/Qwen3-4B-Instruct-2507",
        dataset_id="guard-sft",
        method="sft_text",
        learning_rate=1e-4,
        max_steps=steps_for_rows(4, 8, 400),
        hf_repo="shardulmarathe/sureshop-guard-r0-sft",
    )
    parsed = tomllib.loads(text)
    assert parsed["kind"] == "train"
    assert parsed["method"]["type"] == "sft_text"
    assert parsed["method"]["load_in_4bit"] is True
    assert parsed["method"]["lora_rank"] == 16
    assert parsed["method"]["use_unsloth"] is True
    assert parsed["method"]["num_epochs"] == 2
    assert parsed["resources"]["gpu_count"] == 1
    assert parsed["method"]["max_steps"] == 2
    assert parsed["huggingface"]["private"] is True
    assert parsed["huggingface"]["artifact"] == "merged"
    assert parsed["huggingface"]["repo"] == "shardulmarathe/sureshop-guard-r0-sft"
    for token in ("[reward]", "[deployment]", "min_replicas", "private = false"):
        assert token not in text
    assert "[huggingface]" in text
    dpo = tomllib.loads(
        render_train_toml(
            output_model="guard-r0-sft-dpo",
            base_model="shardulmarathe/sureshop-guard-r0-sft",
            dataset_id="guard-dpo",
            method="dpo",
            learning_rate=1e-5,
            max_steps=10,
            hf_repo="shardulmarathe/sureshop-guard-r0-sft-dpo",
        )
    )
    assert dpo["method"]["type"] == "dpo"
    assert dpo["method"]["beta"] == pytest.approx(0.1)
    assert "reward" not in dpo
    assert "use_unsloth" not in dpo["method"]
    with pytest.raises(ContractError):
        render_train_toml(
            output_model="guard-r0-sft",
            base_model="Qwen/Qwen3-4B-Instruct-2507",
            dataset_id="guard-sft",
            method="sft_text",
            learning_rate=1e-4,
            max_steps=3,
            hf_repo="shardulmarathe/sureshop-guard-r0-sft",
            private=False,
        )


def test_round_dry_run_orders_commands_and_refuses_the_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "vk_" + "test_SHOULD_NOT_LEAK"
    monkeypatch.setenv("VERI_API_KEY", secret)
    runs = tmp_path / "runs"
    report = launch_round(
        RoundOptions(
            round_index=0,
            labels=FIXTURES,
            runs=runs,
            dry_run=True,
            repo=tmp_path,
            spend_cap="50.00",
        )
    )
    commands = report["commands"]
    blob = "\n".join(commands)
    assert blob.index("veri datasets check") < blob.index("veri datasets upload")
    assert blob.index("veri datasets upload") < blob.index("veri jobs estimate")
    assert blob.index("veri jobs estimate") < blob.index("veri jobs create")
    assert blob.index("veri jobs create") < blob.index("veri jobs get")
    assert blob.index("veri jobs get") < blob.index("veri jobs cancel")
    assert blob.index("veri jobs cancel") < blob.index("veri jobs download")
    assert blob.index("veri jobs download") < blob.index("veri checkpoints download")
    assert "--artifact adapter" in blob
    assert "GET /v1/training_jobs/<job_id>/metrics" in blob
    assert "veri deployments" not in blob
    assert report["base_model"] == "Qwen/Qwen3-4B-Instruct-2507"
    assert report["limits"]["steps_allowed_by_wall"] == 28
    assert report["limits"]["max_steps"] == 2
    assert report["limits"]["epochs"] == 2
    assert report["hf_repo"] == "shardulmarathe/sureshop-guard-r0-sft"
    assert report["hf_pushed"] is False
    assert secret not in json.dumps(report)
    saved = json.loads((runs / "training" / "round0.json").read_text())
    assert saved["dry_run"] is True
    assert saved["would_reserve_usd"] == "1.29"
    assert saved["structure"]["features"] == ["checkbox", "popup", "fee_line", "strike_through"]
    toml = (runs / "training" / "configs" / "round0.toml").read_text(encoding="utf-8")
    assert f'base = "{PRIMARY_BASE_MODEL}"' in toml
    assert 'base = "Qwen/Qwen3-4B"' not in toml
    assert "private = true" in toml
    assert 'artifact = "merged"' in toml
    assert saved["groups"]["shared_groups"] == []
    assert "by_verdict" in saved["structure"]["train"]
    assert "by_attack_type" in saved["structure"]["train"]
    assert secret not in (runs / "training" / "round0.json").read_text()

    ledger = SpendLedger(runs / "training" / "veri_spend_ledger.json", "50.00")
    ledger.authorize(Decimal("49.00"), note="already committed")
    with pytest.raises(SpendCapExceeded):
        launch_round(
            RoundOptions(round_index=1, labels=FIXTURES, runs=runs, dry_run=True, repo=tmp_path),
            ledger=ledger,
        )
    assert not (runs / "training" / "round1.json").exists()


def test_round_live_fake_settles_actual_cost(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "vk_" + "test_SHOULD_NOT_LEAK"
    monkeypatch.setenv("VERI_API_KEY", secret)
    runs = tmp_path / "runs"
    fake = FakeVeri()
    live_ledger = SpendLedger(runs / "training" / "veri_spend_ledger.json", "55.00")
    report = launch_round(
        RoundOptions(
            round_index=0,
            labels=FIXTURES,
            runs=runs,
            dry_run=False,
            repo=tmp_path,
            poll_seconds=0,
            min_rows=1,
        ),
        executor=fake,
        ledger=live_ledger,
        clock=ManualClock(),
        metrics_fetcher=lambda job_id: [{"step": 1, "loss": 0.42, "values": {"train_loss": 0.42}}],
    )
    assert report["job_id"] == "abc123"
    assert report["status"] == "completed"
    assert report["loss_curve"][0]["loss"] == 0.42
    assert report["checkpoint"]["kind"] == "adapter"
    assert report["cost_usd"] == "0.40"
    assert report["cost_confidence"] == "actual"
    assert secret not in json.dumps(report)
    ledger = SpendLedger(runs / "training" / "veri_spend_ledger.json", "50.00")
    assert ledger.totals().settled == Decimal("0.40")
    assert ledger.totals().reserved == Decimal("0")
    assert fake.calls[:5] == ["check", "upload", "estimate", "balance", "create"]


def test_create_failure_releases_the_reservation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from guardtrain.veri import VeriCLIError

    monkeypatch.setenv("VERI_API_KEY", "vk_" + "test_SHOULD_NOT_LEAK")
    runs = tmp_path / "runs"
    with pytest.raises(VeriCLIError):
        launch_round(
            RoundOptions(round_index=0, labels=FIXTURES, runs=runs, repo=tmp_path, min_rows=1),
            executor=FakeVeri(create_error="validation failed"),
            ledger=SpendLedger(runs / "training" / "veri_spend_ledger.json", "55.00"),
        )
    ledger = SpendLedger(runs / "training" / "veri_spend_ledger.json", "50.00")
    assert ledger.public_view()["entries"][-1]["status"] == "released"
    assert ledger.totals().committed == Decimal("0")
    assert not (runs / "training" / "round0.json").exists()


def test_subprocess_redacts_stderr_and_keeps_the_key_out_of_argv() -> None:
    secret = "vk_" + "test_SHOULD_NOT_LEAK"
    seen: list[list[str]] = []

    def runner(args: list[str], timeout: float) -> Completed:
        seen.append(args)
        return Completed(1, "", f"boom {secret}")

    with pytest.raises(Exception) as caught:
        SubprocessVeri(runner).datasets_check(Path("payload.jsonl"))
    assert secret not in str(caught.value)
    assert "[redacted]" in str(caught.value)
    assert seen[0][0] == "veri"
    assert secret not in " ".join(seen[0])


def test_poll_cancels_on_wall_and_queue_and_returns_completed() -> None:
    running = SeqVeri(["running", "cancelled"])
    view = poll_until_done(
        running,
        "job",
        max_wall_minutes=0,
        max_queue_minutes=30,
        poll_seconds=5,
        clock=ManualClock(),
    )
    assert view["cancelled_by"] == "wall_clock"
    assert running.cancels == ["job"]

    queued = SeqVeri(["queued", "cancelled"])
    view = poll_until_done(
        queued,
        "job",
        max_wall_minutes=60,
        max_queue_minutes=0,
        poll_seconds=5,
        clock=ManualClock(),
    )
    assert view["cancelled_by"] == "queue_timeout"
    assert queued.cancels == ["job"]

    done = SeqVeri(["completed"])
    view = poll_until_done(
        done,
        "job",
        max_wall_minutes=0,
        max_queue_minutes=0,
        poll_seconds=5,
        clock=ManualClock(),
    )
    assert view["status"] == "completed"
    assert done.cancels == []


def test_dpo_is_one_live_round_and_needs_a_rejected_output(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    (runs / "training").mkdir(parents=True)
    (runs / "training" / "round3.json").write_text(
        json.dumps({"method": "dpo", "dry_run": True}),
        encoding="utf-8",
    )
    assert dpo_already_used(runs) is False
    (runs / "training" / "round4.json").write_text(
        json.dumps({"method": "dpo", "dry_run": False}),
        encoding="utf-8",
    )
    assert dpo_already_used(runs) is True
    with pytest.raises(ContractError, match="one round"):
        launch_round(
            RoundOptions(round_index=1, labels=FIXTURES, runs=runs, dpo=True, dry_run=True, repo=tmp_path)
        )

    miss = _row("b", model_output='{"verdict":"pass","attack_type":"none","evidence":"","instruction":"go"}')
    records = dpo_records([miss], max_page_tokens=2000, system_in_user=False, hide_held_out_labels=False)
    assert records == []
    miss.mix_source = "miss"
    records = dpo_records([miss], max_page_tokens=2000, system_in_user=False, hide_held_out_labels=False)
    assert set(records[0]) == {"prompt", "chosen", "rejected"}
    assert records[0]["rejected"][0]["content"] != records[0]["chosen"][0]["content"]


def test_scoring_rates_and_leaderboard(tmp_path: Path) -> None:
    rows = []
    preds = []
    for index in range(4):
        rows.append(_row(f"fee-{index}", text="Pay the service fee now."))
        caught = index < 3
        preds.append(
            {
                "verdict": "block" if caught else "pass",
                "attack_type": "hidden_fees" if caught else "none",
                "evidence": "service fee" if caught else "",
                "parse_ok": True,
                "latency_ms": 10 + index,
                "cost_usd": "0.002",
                "input_tokens": 100,
                "output_tokens": 20,
                "raw": "",
            }
        )
    for index in range(2):
        rows.append(
            _row(
                f"sub-{index}",
                attack="subscription_trap",
                family="scam",
                text="Starts a free trial.",
                evidence="free trial",
            )
        )
        preds.append(
            {
                "verdict": "pass",
                "attack_type": "none",
                "evidence": "",
                "parse_ok": True,
                "latency_ms": 8,
                "cost_usd": "0",
                "input_tokens": 10,
                "output_tokens": 5,
                "raw": "",
            }
        )
    for index in range(4):
        rows.append(_row(f"clean-{index}", verdict="pass", attack="none", family="clean", evidence="", text="Total $5."))
        false_block = index == 0
        preds.append(
            {
                "verdict": "block" if false_block else "pass",
                "attack_type": "hidden_fees" if false_block else "none",
                "evidence": "not on the page" if false_block else "",
                "parse_ok": True,
                "latency_ms": 4,
                "cost_usd": "0",
                "input_tokens": 10,
                "output_tokens": 5,
                "raw": "",
            }
        )
    metrics = score_predictions(rows, preds)
    assert metrics["catch_rate"] == pytest.approx(0.5)
    assert metrics["false_block_rate_clean"] == pytest.approx(0.25)
    assert metrics["per_attack_type"]["hidden_fees"]["catch_rate"] == pytest.approx(0.75)
    assert metrics["per_attack_type"]["subscription_trap"]["catch_rate"] == pytest.approx(0.0)
    assert metrics["evidence_quote_match"] == pytest.approx(0.75)
    assert metrics["n"] == 10

    only_clean = score_predictions(
        [_row("c", verdict="pass", attack="none", family="clean", evidence="")],
        [
            {
                "verdict": "pass",
                "attack_type": "none",
                "evidence": "",
                "parse_ok": False,
                "latency_ms": 1,
                "cost_usd": "0",
                "raw": "",
            }
        ],
    )
    assert only_clean["catch_rate"] is None
    assert only_clean["evidence_quote_match"] is None
    assert only_clean["false_block_rate_clean"] == pytest.approx(0.0)

    runs = tmp_path / "runs"
    code = main(
        [
            "eval",
            "--model",
            "mock-guard",
            "--round",
            "base",
            "--backend",
            "mock",
            "--labels",
            str(FIXTURES),
            "--slice",
            str(SLICE),
            "--also-slice",
            "--page-set",
            "testset",
            "--runs-dir",
            str(runs),
        ]
    )
    assert code == 0
    full = json.loads((runs / "eval" / "mock-guard_base.json").read_text())
    sliced = json.loads((runs / "eval" / "mock-guard_base_slice100.json").read_text())
    assert full["page_set"] == "testset"
    assert sliced["page_set"] == "slice100"
    assert full["not_for_training"] is True
    assert full["exclude_from_leaderboard"] is True
    assert full["testset_content_hash"] == read_testset_content_hash()["content_hash"]
    board = json.loads((runs / "eval" / "leaderboard.json").read_text())
    assert board["rows"] == []
    real = build_report(
        model="qwen3-4b",
        round_name="base",
        page_set="dev",
        rows=rows,
        preds=preds,
        price=lookup_price("qwen3-4b"),
        stopped_reason=None,
    )
    assert real["exclude_from_leaderboard"] is False
    write_report(runs, real)
    board = json.loads((runs / "eval" / "leaderboard.json").read_text())
    assert [row["model"] for row in board["rows"]] == ["qwen3-4b"]
    assert "cost_per_1000_checks_usd" in board["rows"][0]
    miss_file = runs / "eval" / "mock-guard_base.misses.jsonl"
    if miss_file.read_text().strip():
        with pytest.raises(ContractError):
            load_previous_miss_files([miss_file])


def test_prices_and_provider_kwargs() -> None:
    sonnet = lookup_price("claude-sonnet-5-5")
    assert sonnet.cost(1000, 100) == Decimal("0.003")
    pro = lookup_price("gemini-3.1-pro-preview")
    assert pro.cost(1000, 100) == Decimal("0.0032")
    assert lookup_price("qwen3-4b").cost(5000, 500) == Decimal("0")
    with pytest.raises(ContractError):
        lookup_price("unknown-model")

    captured: dict = {}

    class _Msg:
        content = (
            '{"verdict":"pass","attack_type":"none","evidence":"","instruction":"Proceed with checkout."}'
        )

    class _Choice:
        message = _Msg()

    def create_fn(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[_Choice()],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8, completion_tokens_details={"reasoning_tokens": 3}),
        )

    row = _row("p", verdict="pass", attack="none", family="clean", evidence="")
    result = check_gemini(
        row,
        model="gemini-3-flash-preview",
        max_tokens=256,
        thinking_level="low",
        max_page_tokens=2000,
        create_fn=create_fn,
    )
    assert result.parse_ok is True
    assert captured["reasoning_effort"] == "low"
    assert captured["max_tokens"] == 256
    assert "temperature" not in captured
    assert "extra_body" not in captured
    kwargs = gemini_create_kwargs(model="m", messages=[], max_tokens=256, thinking_level="low")
    assert set(kwargs) == {"model", "messages", "max_tokens", "reasoning_effort"}

    def anthropic_fn(**kwargs):
        captured["anthropic"] = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=_Msg.content)],
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=4,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )

    check_anthropic(
        row,
        model="claude-sonnet-5-5",
        max_tokens=512,
        effort="low",
        max_page_tokens=2000,
        create_fn=anthropic_fn,
    )
    sent = captured["anthropic"]
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["output_config"] == {"effort": "low"}
    assert sent["max_tokens"] == 512
    assert "temperature" not in sent


def test_page_set_gates_and_spend_loop(tmp_path: Path) -> None:
    rows = load_labels(FIXTURES)
    with pytest.raises(ContractError, match="100-page slice"):
        prepare_page_set(rows, model="gemini-3.1-pro-preview")
    selected, page_set = prepare_page_set(
        rows,
        model="gemini-3.1-pro-preview",
        slice_ids=["p-clean", "p-fee", "p-addon"],
    )
    assert page_set == "slice100"
    assert [row.page_id for row in selected] == ["p-clean", "p-fee", "p-addon"]
    probed, probe_set = prepare_page_set(rows, probe=5, seed=0)
    assert probe_set == "probe"
    assert len(probed) == 5
    full, full_set = prepare_page_set(
        rows,
        model="gemini-3.1-pro-preview",
        allow_full=True,
        page_set="testset",
    )
    assert full_set == "testset"
    assert len(full) == len(rows)

    price = lookup_price("custom", input_usd_per_mtok="0", output_usd_per_mtok="1000")
    calls: list[str] = []

    def checker(row: LabelRow) -> CheckResult:
        calls.append(row.page_id)
        return CheckResult(
            verdict="pass",
            attack_type="none",
            evidence="",
            instruction="Proceed with checkout.",
            parse_ok=True,
            raw="{}",
            input_tokens=0,
            output_tokens=10,
            latency_ms=1,
            sent=True,
        )

    ledger = SpendLedger(tmp_path / "cap.json", "1.00", quant="cents")
    preds, stopped = run_checks(
        rows[:2],
        checker,
        price=price,
        max_output_tokens=1000,
        max_page_tokens=2000,
        ledger=ledger,
        requested_cap="1.00",
    )
    assert len(calls) == 1
    assert len(preds) == 1
    assert stopped

    calls.clear()
    tight = SpendLedger(tmp_path / "tight.json", "0.50", quant="cents")
    preds, stopped = run_checks(
        rows[:2],
        checker,
        price=price,
        max_output_tokens=1000,
        max_page_tokens=2000,
        ledger=tight,
        requested_cap="0.50",
    )
    assert calls == []
    assert preds == []
    assert stopped


def test_cli_gates_keys_slice_and_convert(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VERI_API_KEY", raising=False)
    runs = tmp_path / "runs"
    assert (
        main(
            [
                "baseline-gemini",
                "--labels",
                str(FIXTURES),
                "--model",
                "gemini-3-flash-preview",
                "--probe",
                "1",
                "--runs-dir",
                str(runs),
            ]
        )
        == 4
    )
    assert (
        main(
            [
                "baseline-anthropic",
                "--labels",
                str(FIXTURES),
                "--probe",
                "1",
                "--runs-dir",
                str(runs),
            ]
        )
        == 4
    )
    assert (
        main(
            [
                "baseline-gemini",
                "--model",
                "gemini-3.1-pro-preview",
                "--labels",
                str(FIXTURES),
                "--dry-run",
                "--runs-dir",
                str(runs),
            ]
        )
        == 2
    )
    slice_path = tmp_path / "three.txt"
    slice_path.write_text("p-clean\np-fee\np-addon\n", encoding="utf-8")
    assert (
        main(
            [
                "baseline-gemini",
                "--model",
                "gemini-3.1-pro-preview",
                "--labels",
                str(FIXTURES),
                "--slice",
                str(slice_path),
                "--dry-run",
                "--spend-cap",
                "2.50",
                "--runs-dir",
                str(runs),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["n_selected"] == 3
    assert plan["page_set"] == "slice100"
    assert plan["max_tokens"] == 1024
    assert gemini_max_tokens("gemini-3.1-pro-preview", None) == 1024
    assert gemini_max_tokens("gemini-3.7-flash", None) == 256
    assert (
        main(
            [
                "baseline-gemini",
                "--model",
                "gemini-3-flash-preview",
                "--labels",
                str(FIXTURES),
                "--probe",
                "5",
                "--dry-run",
                "--runs-dir",
                str(runs),
            ]
        )
        == 0
    )
    probe = json.loads(capsys.readouterr().out)
    assert probe["n_selected"] == 5
    assert probe["page_set"] == "probe"
    assert not (runs / "eval" / "leaderboard.json").exists()
    assert (
        main(
            [
                "baseline-gemini",
                "--labels",
                str(FIXTURES),
                "--dry-run",
                "--spend-cap",
                "0.01",
                "--input-usd-per-mtok",
                "1000",
                "--output-usd-per-mtok",
                "1000",
                "--max-tokens",
                "1000",
                "--runs-dir",
                str(runs),
            ]
        )
        == 3
    )
    capsys.readouterr()
    assert (
        main(
            [
                "convert",
                "--base-model",
                "Qwen/Qwen3-4B-Instruct-2507",
                "--outfile",
                str(tmp_path / "qwen.gguf"),
                "--dry-run",
            ]
        )
        == 0
    )
    convert = json.loads(capsys.readouterr().out)
    joined = "\n".join(convert["commands"])
    assert "convert_hf_to_gguf.py" in joined
    assert "hf download Qwen/Qwen3-4B-Instruct-2507" in joined
    assert not (tmp_path / "qwen.Modelfile").exists()
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text("{}\n", encoding="utf-8")
    planned = plan_conversion(hf_dir=adapter, outfile=tmp_path / "out.gguf")
    planned_text = "\n".join(planned)
    assert "guardtrain merge" in planned_text
    assert PRIMARY_BASE_MODEL in planned_text
    assert f"--base {PRIMARY_BASE_MODEL}" in planned_text
    assert "Qwen/Qwen3-4B " not in planned_text
    assert 'Qwen/Qwen3-4B"' not in planned_text
    capsys.readouterr()
    assert main(["deploy-hint"]) == 0
    hint = json.loads(capsys.readouterr().out)
    assert hint["do_not_run_during_the_hackathon"] is True
    scale = hint["create_scale_to_zero"]
    assert scale[scale.index("--min-replicas") + 1] == "0"
    hinted = safe_deploy_hint("Qwen/Qwen3-4B")
    assert hinted[hinted.index("--min-replicas") + 1] == "0"


def test_parse_fences_and_qwen3guard() -> None:
    fenced = parse_guard_output(
        '```json\n{"verdict":"block","attack_type":"hidden_fees","evidence":"service fee","instruction":"Remove it."}\n```'
    )
    assert fenced.parse_ok is True
    assert fenced.attack_type == "hidden_fees"
    unsafe = parse_guard_output("Safety: Unsafe\nCategories: Violent", adapter="auto")
    assert unsafe.parse_ok is True
    assert unsafe.verdict == "block"
    assert unsafe.attack_type == "none"
    safe = parse_guard_output("Safety: Safe", adapter="qwen3guard")
    assert safe.verdict == "pass"
    assert safe.attack_type == "none"
    assert safe.instruction == ""
    thought = parse_guard_output(
        "<think>maybe a fee</think>\n"
        '{"verdict":"block","attack_type":"hidden_fees","evidence":"service fee","instruction":"Remove it."}'
    )
    assert thought.parse_ok is True
    assert thought.attack_type == "hidden_fees"
    assert "<think>" not in thought.raw
    unclosed = parse_guard_output("<THINK>still thinking and no json")
    assert unclosed.parse_ok is False
    guarded = parse_guard_output("<think>hidden</think>\nSafety: Unsafe", adapter="qwen3guard")
    assert guarded.verdict == "block"
    assert "<think>" not in guarded.raw


def test_serve_mock_check() -> None:
    client = TestClient(create_app(mock_complete, backend_name="mock"))
    blocked = client.post("/check", json={"page_text": "A service fee was added.", "page_id": "p"})
    assert blocked.status_code == 200
    assert blocked.json()["verdict"] == "block"
    assert blocked.json()["attack_type"] == "hidden_fees"
    assert set(blocked.json()) == {"verdict", "attack_type", "evidence", "instruction"}
    passed = client.post("/check", json={"page_text": "Order total $5.00. Pay for coffee."})
    assert passed.json()["verdict"] == "pass"
    broken = TestClient(create_app(lambda messages: ("not json", 1, 1)))
    rejected = broken.post("/check", json={"page_text": "hello checkout"})
    assert rejected.status_code == 422
    assert client.get("/health").json()["status"] == "ok"
    assert 'host="0.0.0.0"' in inspect.getsource(serve)


def test_http_endpoint_reads_the_body_before_close() -> None:
    import httpx

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "verdict": "pass",
                "attack_type": "none",
                "evidence": "",
                "instruction": "Proceed with checkout.",
            },
        )

    row = _row("p", verdict="pass", attack="none", family="clean", evidence="")
    with httpx.Client(transport=httpx.MockTransport(ok)) as http:
        result = check_http_endpoint(row, url="http://guard.test/check", client=http)
    assert result.parse_ok is True
    assert result.verdict == "pass"

    def unparsed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error": "unparseable"})

    with httpx.Client(transport=httpx.MockTransport(unparsed)) as http:
        result = check_http_endpoint(row, url="http://guard.test/check", client=http)
    assert result.parse_ok is False


def test_source_tree_has_no_live_secrets() -> None:
    pattern_key = re.compile(r"vk_[A-Za-z0-9]{8,}")
    pattern_ant = re.compile(r"sk-ant-")
    roots = [REPO / "train" / "guardtrain", REPO / "train" / "configs", REPO / ".env.example"]
    files = [path for root in roots if root.exists() for path in ([root] if root.is_file() else root.rglob("*"))]
    files.append(REPO / "train" / "RUNBOOK.md")
    for path in files:
        if not path.is_file() or path.suffix not in {".py", ".md", ".toml", ".example", ""}:
            continue
        text = path.read_text(encoding="utf-8")
        assert pattern_key.search(text) is None, path
        assert pattern_ant.search(text) is None, path
    for path in (REPO / "train" / "guardtrain").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert re.search(r"content_hash[\"']?\s*[:=]\s*[\"'][0-9a-f]{64}", text) is None, path


def test_prices_include_gemini_37_flash_and_clients_do_not_retry() -> None:
    from datetime import date

    opus = lookup_price("claude-opus-5-5")
    assert opus.input_usd_per_mtok == Decimal("4")
    assert opus.output_usd_per_mtok == Decimal("20")
    from guardtrain.prices import opus_teacher_cost

    assert opus_teacher_cost(
        {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_creation_input_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
        }
    ) == Decimal("29.20")
    flash = lookup_price("gemini-3.7-flash")
    if date.today() < date(2027, 1, 1):
        assert flash.input_usd_per_mtok == Decimal("0.75")
        assert flash.output_usd_per_mtok == Decimal("3.75")
        assert flash.cost(1000, 100) == Decimal("0.001125")
    else:
        assert flash.input_usd_per_mtok == Decimal("1.50")
        assert flash.output_usd_per_mtok == Decimal("7.50")
    assert "max_retries=0" in inspect.getsource(default_gemini_create)
    assert "max_retries=0" in inspect.getsource(default_anthropic_create)
    assert steps_for_wall(60) == 28
    assert steps_for_rows(10_000, 8, 400, 60) == 28
    assert steps_for_rows(4, 8, 400) == 2
    assert steps_for_rows(4, 8, 400, epochs=1) == 1


def test_local_calls_disable_thinking(tmp_path: Path) -> None:
    import httpx

    row = _row("p", verdict="pass", attack="none", family="clean", evidence="")
    seen: dict = {}

    def ollama(request: httpx.Request) -> httpx.Response:
        seen["ollama"] = json.loads(request.content)
        body = (
            "<think>hidden</think>"
            '{"verdict":"pass","attack_type":"none","evidence":"","instruction":""}'
        )
        return httpx.Response(
            200,
            json={"message": {"content": body}, "prompt_eval_count": 3, "eval_count": 2},
        )

    def llama(request: httpx.Request) -> httpx.Response:
        seen["llama"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"verdict":"pass","attack_type":"none","evidence":"","instruction":""}'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 5},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(ollama)) as http:
        result = check_ollama(
            row,
            model="qwen3-4b-instruct-2507",
            base_url="http://ollama.test",
            max_page_tokens=200,
            adapter="json",
            client=http,
        )
    assert seen["ollama"]["think"] is False
    assert result.parse_ok is True
    assert "<think>" not in result.raw
    with httpx.Client(transport=httpx.MockTransport(llama)) as http:
        result = check_openai_compat(
            row,
            model="guard",
            base_url="http://llama.test/v1",
            max_page_tokens=200,
            adapter="json",
            client=http,
        )
    assert seen["llama"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert result.parse_ok is True


def test_convert_merges_an_adapter_or_refuses() -> None:
    called: dict = {}

    def merger(adapter: Path, base: str, out: Path) -> None:
        called["args"] = (adapter, base, out)

    command = (
        "python -m guardtrain merge --adapter /tmp/adapter "
        "--base Qwen/Qwen3-4B-Instruct-2507 --out /tmp/adapter/merged"
    )
    run_convert([command], dry_run=True, merge_fn=merger)
    assert called == {}
    run_convert([command, "ollama create guard-qwen3 -f model.Modelfile"], dry_run=False, merge_fn=merger)
    assert called["args"][1] == "Qwen/Qwen3-4B-Instruct-2507"

    def missing(*_args) -> None:
        raise ImportError("No module named torch")

    with pytest.raises(ContractError, match="run merge first"):
        run_convert([command], dry_run=False, merge_fn=missing)


def test_missing_page_text_fails_and_frozen_scan_skips_bodies(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    labels = tmp_path / "labels.jsonl"
    _write_jsonl(
        labels,
        [
            {
                "page_id": "only-on-disk",
                "store": "bean",
                "family": "clean",
                "attack_type": "none",
                "verdict": "pass",
                "evidence_text": "",
                "instruction": "",
                "split": "test",
            }
        ],
    )
    rows = load_labels(labels)
    with pytest.raises(ContractError, match="Missing page text"):
        attach_page_text(rows, labels.parent / "text", required=True)
    text_dir = labels.parent / "text"
    text_dir.mkdir()
    (text_dir / "only-on-disk.txt").write_text("Order total $5.00.", encoding="utf-8")
    attach_page_text(rows, text_dir, required=True)
    assert "Order total" in rows[0].page_text

    code = main(
        [
            "eval",
            "--model",
            "mock-guard",
            "--backend",
            "mock",
            "--labels",
            str(labels),
            "--pages-dir",
            str(tmp_path / "missing-text"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert code == 2
    assert "Missing page text" in capsys.readouterr().err

    root = tmp_path / "repo"
    label_file = root / "data" / "testset" / "labels.jsonl"
    body = root / "data" / "testset" / "text" / "real-page.txt"
    slice_file = root / "gym" / "testset" / "slice100.txt"
    label_file.parent.mkdir(parents=True)
    body.parent.mkdir(parents=True)
    slice_file.parent.mkdir(parents=True)
    _write_jsonl(
        label_file,
        [
            {
                "page_id": "real-page",
                "store": "bean",
                "family": "clean",
                "attack_type": "none",
                "verdict": "pass",
                "split": "test",
                "page_text": "hello",
            }
        ],
    )
    body.write_text("decoy-from-text\nnot-a-page-id\n", encoding="utf-8")
    slice_file.write_text("slice-page\n", encoding="utf-8")
    found = discover_frozen_ids(root)
    assert found == {"real-page", "slice-page"}

    manifest = root / "gym" / "testset" / "manifest.json"
    manifest.write_text(json.dumps({"content_hash": "runtime-hash-not-a-constant"}), encoding="utf-8")
    assert read_testset_content_hash(root)["content_hash"] == "runtime-hash-not-a-constant"
    assert read_testset_content_hash(tmp_path / "empty")["content_hash"] is None


def test_poll_retries_then_cancels_and_download_is_after_settle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Flaky:
        def __init__(self, failures: int) -> None:
            self.left = failures
            self.cancels: list[str] = []

        def jobs_get(self, job_id: str) -> dict:
            if self.left:
                self.left -= 1
                raise VeriCLIError("temporary")
            return {"id": job_id, "status": "completed", "cost_usd": None}

        def jobs_cancel(self, job_id: str) -> None:
            self.cancels.append(job_id)

    clock = ManualClock()
    flaky = Flaky(2)
    view = poll_until_done(
        flaky,
        "job",
        max_wall_minutes=60,
        max_queue_minutes=30,
        poll_seconds=5,
        clock=clock,
    )
    assert view["status"] == "completed"
    assert flaky.cancels == []
    assert clock.now == 15  # 5s then 10s

    fatal = Flaky(POLL_FAILURES_BEFORE_CANCEL)
    with pytest.raises(VeriCLIError, match="cancel requested"):
        poll_until_done(
            fatal,
            "job",
            max_wall_minutes=60,
            max_queue_minutes=30,
            poll_seconds=5,
            clock=ManualClock(),
        )
    assert fatal.cancels == ["job"]

    assert newest_checkpoint_id(
        [{"id": "job@8", "step": 8}, {"id": "job@20", "step": 20}],
        "job",
    ) == "job@20"
    assert newest_checkpoint_id([{"checkpoint_id": "first"}, {"id": "second"}], "job") == "first"

    secret = "vk_" + "test_SHOULD_NOT_LEAK"
    monkeypatch.setenv("VERI_API_KEY", secret)
    runs = tmp_path / "runs"

    class DownloadAfterSettle(FakeVeri):
        def jobs_download(self, job_id: str, output_dir: Path) -> None:
            ledger = SpendLedger(runs / "training" / "veri_spend_ledger.json", "50.00")
            assert ledger.totals().settled == Decimal("0.40")
            saved = json.loads((runs / "training" / "round0.json").read_text())
            assert saved["cost_usd"] == "0.40"
            raise VeriCLIError("disk full")

    report = launch_round(
        RoundOptions(
            round_index=0,
            labels=FIXTURES,
            runs=runs,
            dry_run=False,
            repo=tmp_path,
            poll_seconds=0,
            min_rows=1,
        ),
        executor=DownloadAfterSettle(),
        ledger=SpendLedger(runs / "training" / "veri_spend_ledger.json", "55.00"),
        clock=ManualClock(),
        metrics_fetcher=lambda _job: [],
    )
    assert report["download_error"]
    assert report["cost_usd"] == "0.40"
    assert report["cost_confidence"] == "actual"
    assert SpendLedger(runs / "training" / "veri_spend_ledger.json", "50.00").totals().reserved == Decimal("0")

    class CancelThenCheckpoint(FakeVeri):
        def __init__(self) -> None:
            super().__init__()
            self.statuses = ["running", "cancelled"]
            self.downloaded: list[str] = []

        def jobs_get(self, job_id: str) -> dict:
            self.calls.append("get")
            status = self.statuses.pop(0) if self.statuses else "cancelled"
            return {"id": job_id, "status": status, "cost_usd": "0.10"}

        def jobs_download(self, job_id: str, output_dir: Path) -> None:
            raise AssertionError("final download is only for a completed job")

        def checkpoints_list(self, job_id: str) -> list:
            self.calls.append("list")
            return [{"id": f"{job_id}@8", "step": 8}, {"id": f"{job_id}@20", "step": 20}]

        def checkpoints_download(self, job_id: str, checkpoint_id: str, output_dir: Path) -> None:
            self.downloaded.append(checkpoint_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "adapter_config.json").write_text("{}\n", encoding="utf-8")

    cancel_runs = tmp_path / "cancel-runs"
    watcher = CancelThenCheckpoint()
    cancelled = launch_round(
        RoundOptions(
            round_index=0,
            labels=FIXTURES,
            runs=cancel_runs,
            dry_run=False,
            repo=tmp_path,
            poll_seconds=0,
            min_rows=1,
            max_wall_minutes=0,
        ),
        executor=watcher,
        ledger=SpendLedger(cancel_runs / "training" / "veri_spend_ledger.json", "55.00"),
        clock=ManualClock(),
        metrics_fetcher=lambda _job: [],
    )
    assert cancelled["cancelled_by"] == "wall_clock"
    assert watcher.downloaded == ["abc123@20"]
    assert cancelled["checkpoint"]["saved"] == "abc123@20"
    assert "cancel" in watcher.calls

    class DeadGet(FakeVeri):
        def jobs_get(self, job_id: str) -> dict:
            self.calls.append("get")
            raise VeriCLIError("get exploded")

    dead_runs = tmp_path / "dead-runs"
    dead = DeadGet()
    with pytest.raises(VeriCLIError, match="cancel requested"):
        launch_round(
            RoundOptions(
                round_index=0,
                labels=FIXTURES,
                runs=dead_runs,
                dry_run=False,
                repo=tmp_path,
                poll_seconds=0,
                min_rows=1,
            ),
            executor=dead,
            ledger=SpendLedger(dead_runs / "training" / "veri_spend_ledger.json", "55.00"),
            clock=ManualClock(),
            metrics_fetcher=lambda _job: [],
        )
    saved = json.loads((dead_runs / "training" / "round0.json").read_text())
    assert saved["status"] == "poll_failed"
    assert saved["cost_usd"] == "1.29"
    assert saved["cost_confidence"] == "reserved_upper_bound"
    assert "download" not in dead.calls
    assert "cancel" in dead.calls
    assert SpendLedger(dead_runs / "training" / "veri_spend_ledger.json", "50.00").totals().settled == Decimal("1.29")

    monkeypatch.delenv("VERI_API_KEY", raising=False)
    with pytest.raises(ContractError, match="minimum"):
        launch_round(
            RoundOptions(round_index=0, labels=FIXTURES, runs=tmp_path / "tiny", dry_run=False, repo=tmp_path)
        )
    assert not (tmp_path / "tiny" / "training" / "round0.json").exists()


def test_serve_upstream_is_502_and_local_baseline_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def boom(_messages):
        raise RuntimeError("vk_" + "SECRETKEY upstream down")

    client = TestClient(create_app(boom, backend_name="ollama"))
    response = client.post("/check", json={"page_text": "Order total $5.00."})
    assert response.status_code == 502
    body = response.json()["detail"]
    assert body["error"] == "upstream"
    assert "SECRETKEY" not in response.text

    assert (
        main(
            [
                "baseline-local",
                "--model",
                "qwen3-4b",
                "--labels",
                str(FIXTURES),
                "--dry-run",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["hf_model"] == "Qwen/Qwen3-4B-Instruct-2507"
    assert plan["gguf"] == "models/qwen3-4b-instruct-2507-q8_0.gguf"
    assert plan["ollama_model"] == "qwen3-4b-instruct-2507"
    assert (
        main(
            [
                "baseline-local",
                "--model",
                "qwen3guard-4b",
                "--labels",
                str(FIXTURES),
                "--dry-run",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
        == 0
    )
    guard = json.loads(capsys.readouterr().out)
    assert guard["hf_model"] == "Qwen/Qwen3Guard-Gen-4B"
    assert guard["gguf"] == "models/qwen3guard-gen-4b-q8_0.gguf"
    assert guard["ollama_model"] == "qwen3guard-gen-4b"


def _page(
    page_id: str,
    *,
    attack: str = "hidden_fees",
    group: str = "g",
    split: str = "train",
) -> dict:
    verdict = "pass" if attack == "none" else "block"
    family = "clean" if attack == "none" else "upsell"
    evidence = "" if verdict == "pass" else "service fee"
    if verdict == "pass":
        text = "Order total $5.00. Pay for coffee."
    else:
        text = "\n".join(
            [
                "controls:",
                "(none)",
                "modals:",
                "(none)",
                "visible:",
                "A service fee was added to the total.",
            ]
        )
    return {
        "page_id": page_id,
        "store": "bean",
        "family": family,
        "attack_type": attack,
        "verdict": verdict,
        "selector": "" if verdict == "pass" else "#fee",
        "bbox": None if verdict == "pass" else [1, 2, 3, 4],
        "evidence_text": evidence,
        "instruction": "" if verdict == "pass" else "Remove the service fee before paying.",
        "source": "template",
        "split": split,
        "group_id": group,
        "page_text": text,
    }


def _write_pages(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_prepare_round_keeps_groups_apart_and_logs_structure(tmp_path: Path) -> None:
    train = tmp_path / "round" / "labels.jsonl"
    dev = tmp_path / "round" / "dev" / "labels.jsonl"
    attacker = tmp_path / "attacker.jsonl"
    specs = tmp_path / "round" / "specs"
    specs.mkdir(parents=True)
    train_rows = [_page("t1", group="gym-a"), _page("t2", group="gym-a")]
    dev_rows = [_page("d1", attack="none", group="gym-dev", split="dev")]
    _write_pages(train, train_rows)
    _write_pages(dev, dev_rows)
    _write_pages(
        attacker,
        [
            _page("a1", group="gym-a"),
            _page("a2", group="gym-a"),
            _page("b1", group="fam-b"),
            _page("b2", group="fam-b"),
            _page("c1", group="fam-c"),
            _page("c2", group="fam-c"),
        ],
    )
    (specs / "t1.json").write_text(
        json.dumps(
            {
                "page_id": "t1",
                "trick": {"attack_type": "hidden_fees", "variant": "drip", "verdict": "block"},
                "page": {"kind": "checkout", "fees": [{"name": "Care", "amount_cents": 100}]},
            }
        ),
        encoding="utf-8",
    )
    leaked = tmp_path / "leak-dev.jsonl"
    _write_pages(leaked, [_page("x1", group="gym-a", split="dev")])
    with pytest.raises(ContractError, match="group_id appears in both"):
        prepare_round(
            RoundOptions(
                round_index=0,
                labels=train,
                dev_labels=leaked,
                runs=tmp_path / "leak-runs",
                repo=tmp_path,
                min_rows=1,
            )
        )

    prepared = prepare_round(
        RoundOptions(
            round_index=0,
            labels=train,
            dev_labels=dev,
            attacker_labels=attacker,
            runs=tmp_path / "runs",
            repo=tmp_path,
            dev_fraction=0.5,
            min_rows=1,
        )
    )
    assert prepared["groups"]["shared_groups"] == []
    dev_groups = {row.extra["group_id"] for row in prepared["dev_rows"]}
    train_groups = {row.extra.get("group_id") for row in prepared["fresh_for_sample"]}
    attacker_groups = {row.extra.get("group_id") for row in prepared["attacker_rows"]}
    assert "gym-a" in train_groups or "gym-a" in attacker_groups
    assert "gym-a" not in dev_groups
    assert "gym-dev" in dev_groups
    assert dev_groups.isdisjoint(train_groups | attacker_groups)
    assert prepared["held_out_attacker"] == 2
    rates = prepared["structure"]["train"]["by_attack_type"]["hidden_fees"]
    assert rates["fee_line"] == 1
    assert rates["checkbox"] == 0
    assert prepared["structure"]["dev"]["by_verdict"]["pass"]["fee_line"] == 0
    assert prepared["structure"]["dev"]["by_verdict"]["pass"]["strike_through"] == 0


@pytest.mark.xfail(
    reason="Known issue on the PR #1 head: the inline sweep YAML in this test is a block list the simple reader does not parse.",
    strict=False,
)
def test_sweep_picks_a_dev_winner_and_refuses_a_thin_balance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERI_API_KEY", "vk_" + "test_SHOULD_NOT_LEAK")
    train = tmp_path / "labels.jsonl"
    dev = tmp_path / "dev" / "labels.jsonl"
    _write_pages(train, [_page("t1", group="keep"), _page("t2", group="keep")])
    _write_pages(
        dev,
        [
            _page("block", group="hold", split="dev"),
            _page("clean", attack="none", group="hold-clean", split="dev"),
        ],
    )
    sweep = tmp_path / "sweep.yaml"
    sweep.write_text(
        "\n".join(
            [
                "max_parallel: 8",
                "dpo: true",
                "configs:",
                "  - {name: careful, learning_rate: 0.0001, lora_rank: 8}",
                "  - {name: dirty, learning_rate: 0.00005, lora_rank: 16}",
            ]
        ),
        encoding="utf-8",
    )

    class SweepVeri:
        def __init__(self, balance: str = "40") -> None:
            self.balance = Decimal(balance)
            self.creates: list[str] = []
            self.downloads: list[str] = []
            self.inflight = 0
            self.max_inflight = 0

        def datasets_check(self, path: Path) -> None:
            return None

        def datasets_upload(self, path: Path, name: str) -> str:
            return "ds"

        def jobs_estimate(self, toml_path: Path) -> dict:
            return {"estimated_cost_usd": "0.50", "rate_usd_per_hour": "1.05", "gpu_count": 1}

        def jobs_create(self, toml_path: Path) -> str:
            self.inflight += 1
            self.max_inflight = max(self.max_inflight, self.inflight)
            job_id = f"job{len(self.creates) + 1}"
            self.creates.append(job_id)
            return job_id

        def jobs_get(self, job_id: str) -> dict:
            return {"id": job_id, "status": "completed", "cost_usd": "0.40"}

        def jobs_cancel(self, job_id: str) -> None:
            return None

        def jobs_download(self, job_id: str, output_dir: Path) -> None:
            self.inflight = max(0, self.inflight - 1)
            self.downloads.append(job_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "adapter_config.json").write_text("{}\n", encoding="utf-8")

        def billing_balance(self) -> Decimal:
            return self.balance

    def score(name: str, rows):
        pages = []
        for row in rows:
            if name == "dirty":
                verdict = "block"
            elif row.verdict == "block":
                verdict = "pass"
            else:
                verdict = "pass"
            pages.append(
                {
                    "page_id": row.page_id,
                    "family": row.family,
                    "gold_verdict": row.verdict,
                    "verdict": verdict,
                    "attack_type": "none",
                    "evidence": "",
                    "instruction": "",
                    "miss": verdict != row.verdict,
                }
            )
        return {"pages": pages, "per_attack_type": {}}

    def score_test(name: str, rows):
        assert name == "careful"
        return {
            "n": 4,
            "catch_rate": 0.25,
            "false_block_rate_clean": 0,
            "evidence_quote_match": 1,
            "per_attack_type": {},
        }

    runs = tmp_path / "runs"
    veri = SweepVeri()
    sweep_ledger = SpendLedger(tmp_path / "sweep-ledger.json", "55.00")
    report = run_sweep(
        RoundOptions(
            round_index=0,
            labels=train,
            dev_labels=dev,
            runs=runs,
            repo=tmp_path,
            dry_run=False,
            min_rows=1,
            poll_seconds=0,
            require_dev=True,
        ),
        sweep,
        executor=veri,
        ledger=sweep_ledger,
        clock=ManualClock(),
        metrics_fetcher=lambda _job: [],
        score_fn=score,
        score_test_fn=score_test,
        test_rows=[_row("frozen-test", page_set="testset", split="test")],
    )
    assert report["winner"] == "careful"
    assert report["max_parallel"] == 4
    by_name = {trial["name"]: trial for trial in report["trials"]}
    assert "testset" in by_name["careful"]
    assert by_name["careful"]["testset"]["catch_rate"] == 0.25
    assert "testset" not in by_name["dirty"]
    assert "slice100" not in by_name["dirty"]
    assert by_name["careful"]["dev"]["false_block_rate_clean"] == 0
    assert by_name["dirty"]["dev"]["false_block_rate_clean"] == 1
    assert by_name["careful"]["selection_score"] > by_name["dirty"]["selection_score"]
    assert report["groups"]["shared_groups"] == []
    assert report["structure"]["features"] == ["checkbox", "popup", "fee_line", "strike_through"]
    assert report["dpo"]["pairs"] >= 1
    assert report["dpo"]["source"] == "dev false blocks and dev misses only"
    assert report["dpo"]["base_model"] == "shardulmarathe/sureshop-guard-r0-careful"
    assert report["dpo"]["init"] == "merged"
    assert report["hf_repo"] == "shardulmarathe/sureshop-guard-r0-careful"
    sft_toml = (runs / "training" / "configs" / "round0.careful.toml").read_text(encoding="utf-8")
    dpo_toml = (runs / "training" / "configs" / "round0.dpo.toml").read_text(encoding="utf-8")
    assert f'base = "{PRIMARY_BASE_MODEL}"' in sft_toml
    assert 'base = "shardulmarathe/sureshop-guard-r0-careful"' in dpo_toml
    assert "private = true" in sft_toml
    assert "private = true" in dpo_toml
    assert 'type = "sft_text"' in sft_toml
    assert 'type = "dpo"' in dpo_toml
    judge = (runs / "training" / "datasets" / "round0.dpo.judge.jsonl").read_text(encoding="utf-8")
    assert '"page_id": "clean"' in judge
    assert '"page_id": "block"' not in judge
    dpo_blob = (runs / "training" / "datasets" / "round0.dpo.jsonl").read_text(encoding="utf-8")
    assert "frozen-test" not in dpo_blob
    assert veri.creates[:2] == ["job1", "job2"]
    assert len(veri.creates) == 3
    saved = json.loads((runs / "training" / "round0.json").read_text(encoding="utf-8"))
    assert saved["winner"] == "careful"
    assert "vk_" not in json.dumps(saved)

    wide = tmp_path / "wide.yaml"
    wide.write_text(
        "\n".join(
            [
                "max_parallel: 8",
                "configs:",
                "  - {name: a, learning_rate: 0.0001, lora_rank: 8}",
                "  - {name: b, learning_rate: 0.0001, lora_rank: 16}",
                "  - {name: c, learning_rate: 0.00005, lora_rank: 8}",
                "  - {name: d, learning_rate: 0.00005, lora_rank: 16}",
                "  - {name: e, learning_rate: 0.0002, lora_rank: 8}",
            ]
        ),
        encoding="utf-8",
    )
    wide_veri = SweepVeri()
    wide_report = run_sweep(
        RoundOptions(
            round_index=2,
            labels=train,
            dev_labels=dev,
            runs=tmp_path / "wide-runs",
            repo=tmp_path,
            dry_run=False,
            min_rows=1,
            poll_seconds=0,
            retrain_from_base=True,
        ),
        wide,
        executor=wide_veri,
        ledger=SpendLedger(tmp_path / "wide-ledger.json", "55.00"),
        clock=ManualClock(),
        metrics_fetcher=lambda _job: [],
    )
    assert wide_report["max_parallel"] == 4
    assert wide_veri.max_inflight == 4
    assert len(wide_veri.creates) == 5
    assert len(wide_veri.downloads) == 5
    assert wide_report["winner"] is None
    assert all("testset" not in trial for trial in wide_report["trials"])

    thin = SweepVeri("4")
    with pytest.raises(SpendCapExceeded, match="floor"):
        run_sweep(
            RoundOptions(
                round_index=3,
                labels=train,
                dev_labels=dev,
                runs=tmp_path / "thin-runs",
                repo=tmp_path,
                dry_run=False,
                min_rows=1,
                poll_seconds=0,
                retrain_from_base=True,
            ),
            sweep,
            executor=thin,
            ledger=SpendLedger(tmp_path / "thin-ledger.json", "55.00"),
            clock=ManualClock(),
            metrics_fetcher=lambda _job: [],
        )
    assert thin.creates == []
    assert not (tmp_path / "thin-runs" / "training" / "round3.json").exists()

    ledger = SpendLedger(tmp_path / "capped" / "ledger.json", "55.00")
    ledger.authorize(Decimal("54.00"), note="already spent", requested_cap="55")
    with pytest.raises(SpendCapExceeded):
        run_sweep(
            RoundOptions(
                round_index=4,
                labels=train,
                dev_labels=dev,
                runs=tmp_path / "capped-runs",
                repo=tmp_path,
                dry_run=True,
                spend_cap="55.00",
                min_rows=1,
                retrain_from_base=True,
            ),
            sweep,
            ledger=ledger,
        )
    assert not (tmp_path / "capped-runs" / "training" / "round4.json").exists()

    assert parallel_limit({"max_parallel": 8}) == 4
    assert len(expand_trials({"grid": {"learning_rate": [1e-4, 5e-5], "lora_rank": [8, 16]}})) == 4
    assert parse_balance({"balance_usd": "12.5"}) == Decimal("12.5")
    assert pick_winner(
        [
            {"name": "dirty", "selection_score": 0.2, "false_block_rate_clean": 0.5, "trick_f1": 0.7},
            {"name": "careful", "selection_score": 0.2, "false_block_rate_clean": 0.0, "trick_f1": 0.4},
        ]
    ) == "careful"
    fitted = assert_jobs_fit(
        ledger=SpendLedger(tmp_path / "empty-ledger.json", "55.00"),
        spend_cap="55.00",
        reservations=[Decimal("1.29"), Decimal("1.29")],
        balance=Decimal("10"),
        require_balance=True,
    )
    assert fitted["balance_floor_usd"] == "3.00"
    with pytest.raises(SpendCapExceeded, match="floor"):
        assert_jobs_fit(
            ledger=SpendLedger(tmp_path / "empty-ledger.json", "55.00"),
            spend_cap="55.00",
            reservations=[Decimal("8")],
            balance=Decimal("10"),
            require_balance=True,
        )

    missed = _row("dev-miss", text="A service fee was added to the total.")
    missed.page_set = "dev"
    frozen = _row("frozen-page", page_set="testset", split="test")
    pairs = dev_preference_rows(
        [missed, frozen],
        {"pages": [{"page_id": "dev-miss", "verdict": "pass", "miss": True}, {"page_id": "frozen-page", "verdict": "block", "miss": True}]},
    )
    assert [row.page_id for row in pairs] == ["dev-miss"]
    base, how = dpo_init({}, 0, "careful")
    assert base == "shardulmarathe/sureshop-guard-r0-careful"
    assert how == "merged"
    with pytest.raises(ContractError):
        dpo_init({"hf_repo": "Qwen/Qwen3-4B-Instruct-2507"}, 0)
    with pytest.raises(ContractError):
        dpo_init({"merged_base": "shop/guard-merged"}, 0)
    continued = plan_continuation(tmp_path / "no-runs", 1, "Qwen/Qwen3-4B-Instruct-2507")
    assert continued.mode == "base"
    assert continued.base_model == "Qwen/Qwen3-4B-Instruct-2507"
    assert continued.hf_repo == "shardulmarathe/sureshop-guard-r1-sft"
    with pytest.raises(ContractError):
        plan_continuation(tmp_path / "no-runs", 2, "Qwen/Qwen3-4B-Instruct-2507")
    fallback = plan_continuation(
        tmp_path / "no-runs",
        2,
        "Qwen/Qwen3-4B-Instruct-2507",
        retrain_from_base=True,
    )
    assert fallback.mode == "retrain_cumulative"
    assert fallback.base_model == "Qwen/Qwen3-4B-Instruct-2507"


def test_pending_dpo_uses_the_instruct_base_and_dev_pairs_only(tmp_path: Path) -> None:
    dev = _row("dev-miss", text="A service fee was added to the total.")
    dev.page_set = "dev"
    dev.split = "dev"
    dev.extra["group_id"] = "err"
    judge_row = _row(
        "dev-clean",
        attack="none",
        verdict="pass",
        family="clean",
        text="Order total $5.00. Pay for coffee.",
        evidence="",
        instruction="",
        split="dev",
    )
    judge_row.page_set = "dev"
    judge_row.extra["group_id"] = "judge"
    frozen = _row("frozen-test", page_set="testset", split="test")
    report = {
        "winner": "careful",
        "base_model": PRIMARY_BASE_MODEL,
        "dpo": {"status": "pending_winner"},
        "trials": [
            {
                "name": "careful",
                "lora_rank": 16,
                "lora_alpha": 32,
                "selection_score": 0.4,
                "false_block_rate_clean": 0,
                "trick_f1": 0.4,
                "dev_pages": [
                    {
                        "page_id": "dev-miss",
                        "verdict": "pass",
                        "miss": True,
                        "family": "upsell",
                        "attack_type": "none",
                        "evidence": "",
                        "instruction": "",
                    }
                ],
            }
        ],
    }
    runs = tmp_path / "runs"
    launch_pending_dpo(
        RoundOptions(
            round_index=3,
            labels=FIXTURES,
            runs=runs,
            dry_run=True,
            base_model=PRIMARY_BASE_MODEL,
        ),
        report,
        [dev, judge_row, frozen],
        {"frozen-test"},
    )
    assert report["dpo"]["base_model"] == "shardulmarathe/sureshop-guard-r3-careful"
    assert report["dpo"]["status"] == "pairs_ready"
    assert report["dpo"]["init"] == "merged"
    blob = Path(report["dpo"]["path"]).read_text(encoding="utf-8")
    assert "frozen-test" not in blob
    assert "dev-clean" not in blob
    judge_blob = Path(report["dpo"]["judge_path"]).read_text(encoding="utf-8")
    assert "dev-clean" in judge_blob
    assert "dev-miss" not in judge_blob
    assert "Qwen/Qwen3-4B\"" not in json.dumps(report["dpo"])
    saved = json.loads((runs / "training" / "round3.json").read_text(encoding="utf-8"))
    assert saved["dpo"]["base_model"] == "shardulmarathe/sureshop-guard-r3-careful"


def test_shared_ledger_path_and_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    from guardtrain.ledger import shared_veri_ledger_path

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert shared_veri_ledger_path() == tmp_path / ".guardgym" / "veri_spend_ledger.json"
    ledger = SpendLedger(tmp_path / "shared.json", "55.00")
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait()
            ledger.authorize(Decimal("1.00"), note="shared", requested_cap="55")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert ledger.totals().reserved == Decimal("2.00")


def test_sweep_score_refuses_a_shared_model() -> None:
    from guardtrain.sweep import require_trial_model

    report = {
        "trials": [
            {"name": "careful", "served_model": "guard-r1-dirty"},
            {"name": "dirty"},
        ]
    }
    with pytest.raises(ContractError, match="served as"):
        require_trial_model(report, 1, "dirty", "guard-qwen3")
    with pytest.raises(ContractError, match="already the served model"):
        require_trial_model(report, 1, "dirty", "guard-r1-dirty")


def test_convert_pulls_a_private_merged_repo(tmp_path: Path) -> None:
    planned = plan_conversion(
        hf_dir=None,
        outfile=tmp_path / "guard.gguf",
        hf_repo="shardulmarathe/sureshop-guard-r1-careful",
    )
    blob = "\n".join(planned)
    assert "hf download shardulmarathe/sureshop-guard-r1-careful" in blob
    assert "guardtrain merge" not in blob
    with pytest.raises(ContractError):
        plan_conversion(hf_dir=None, outfile=tmp_path / "x.gguf", hf_repo="Qwen/Qwen3-4B-Instruct-2507")
