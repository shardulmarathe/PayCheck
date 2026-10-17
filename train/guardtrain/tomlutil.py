"""Write the flat Veri train configs. No reward block and no deploy block."""

from __future__ import annotations

import json
import math
from pathlib import Path

from guardtrain.schema import (
    DEFAULT_EPOCHS,
    DEFAULT_GRAD_ACCUM,
    DEFAULT_LORA_ALPHA,
    DEFAULT_LORA_RANK,
    DEFAULT_MAX_SEQ_LENGTH,
    DEFAULT_MAX_STEPS,
    ContractError,
)


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"Cannot encode {type(value)} as TOML")


def assert_private_hf(repo: str, private: bool, artifact: str = "merged") -> None:
    """Every pushed repo is a private merged model. Anything else is refused."""
    if private is not True:
        raise ContractError(
            "Hugging Face repos must be private. Refusing a config that is not private=true."
        )
    if artifact != "merged":
        raise ContractError('Hugging Face artifact must be "merged".')
    if not isinstance(repo, str) or not repo.startswith("shardulmarathe/sureshop-guard-r"):
        raise ContractError(
            f"Refusing Hugging Face repo {repo!r}. "
            "Use shardulmarathe/sureshop-guard-rN-trial, and keep it private."
        )


def render_train_toml(
    *,
    output_model: str,
    base_model: str,
    dataset_id: str,
    method: str,
    learning_rate: float,
    max_steps: int,
    hf_repo: str,
    private: bool = True,
    artifact: str = "merged",
    num_epochs: int = DEFAULT_EPOCHS,
    max_seq_length: int = DEFAULT_MAX_SEQ_LENGTH,
    lora_rank: int = DEFAULT_LORA_RANK,
    lora_alpha: int = DEFAULT_LORA_ALPHA,
    grad_accum: int = DEFAULT_GRAD_ACCUM,
    beta: float = 0.1,
) -> str:
    if method not in {"sft_text", "dpo"}:
        raise ValueError(f"Unsupported method {method}")
    assert_private_hf(hf_repo, private, artifact)
    if method == "sft_text":
        method_rows = [
            ("type", method),
            ("learning_rate", learning_rate),
            ("num_epochs", int(num_epochs)),
            ("max_steps", int(max_steps)),
            ("max_seq_length", int(max_seq_length)),
            ("lora_rank", int(lora_rank)),
            ("lora_alpha", int(lora_alpha)),
            ("load_in_4bit", True),
            ("use_unsloth", True),
            ("packing", False),
            ("micro_batch_size", 1),
            ("gradient_accumulation_steps", int(grad_accum)),
            ("gradient_checkpointing", True),
        ]
    else:
        method_rows = [
            ("type", method),
            ("learning_rate", learning_rate),
            ("beta", beta),
            ("max_steps", int(max_steps)),
            ("max_length", int(max_seq_length)),
            ("max_prompt_length", int(max_seq_length) - 512),
            ("lora_rank", int(lora_rank)),
            ("lora_alpha", int(lora_alpha)),
            ("load_in_4bit", True),
            ("micro_batch_size", 1),
            ("gradient_accumulation_steps", int(grad_accum)),
            ("gradient_checkpointing", True),
        ]
    lines = [
        "kind = \"train\"",
        "",
        "[job]",
        f"output_model = {_toml_value(output_model)}",
        "",
        "[model]",
        f"base = {_toml_value(base_model)}",
        "",
        "[dataset]",
        f"id = {_toml_value(dataset_id)}",
        "",
        "[method]",
    ]
    for key, value in method_rows:
        lines.append(f"{key} = {_toml_value(value)}")
    lines.extend(
        [
            "",
            "[huggingface]",
            f"repo = {_toml_value(hf_repo)}",
            f"artifact = {_toml_value(artifact)}",
            "private = true",
            "",
            "[resources]",
            'gpu_type = "L4-24GB"',
            "gpu_count = 1",
            "",
        ]
    )
    text = "\n".join(lines)
    forbidden = ("[reward]", "[deployment]", "[autoscaling]", "min_replicas", "private = false")
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"train toml must not contain {token}")
    if "private = true" not in text or 'artifact = "merged"' not in text:
        raise RuntimeError("train toml is missing the private merged Hugging Face block")
    return text


# Qwen3-4B QLoRA at sequence length 4096, micro-batch 1, on one L4.
# 400 optimizer steps at this rate is several hours, so a 60-minute wall must not schedule 400.
STEP_SECONDS_BUDGET = 90
BOOT_RESERVE_MINUTES = 8
TAIL_RESERVE_MINUTES = 10


def steps_for_wall(max_wall_minutes: int | float, *, step_seconds: float = STEP_SECONDS_BUDGET) -> int:
    """Optimizer steps that should finish before the cancel watcher fires.

    Boot time is billed and is not training. The tail is room for the last
    checkpoint to flush and for this process to cancel if a step runs long.
    """
    usable = max(1.0, float(max_wall_minutes) - BOOT_RESERVE_MINUTES - TAIL_RESERVE_MINUTES)
    return max(1, int(usable * 60 / step_seconds))


def wall_minutes_for_steps(steps: int, *, step_seconds: float = STEP_SECONDS_BUDGET) -> int:
    """Wall that can finish ``steps`` at the budgeted step time, plus boot and tail."""
    train_minutes = int(steps) * float(step_seconds) / 60
    return max(1, math.ceil(train_minutes + BOOT_RESERVE_MINUTES + TAIL_RESERVE_MINUTES))


def steps_for_rows(
    n_rows: int,
    grad_accum: int,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_wall_minutes: int | float | None = None,
    epochs: int = DEFAULT_EPOCHS,
) -> int:
    """``epochs`` passes, capped by ``max_steps`` and by the wall when one is set.

    Veri treats ``max_steps`` as an override of ``num_epochs`` when both are set,
    so the step cap written into the config is this same number.
    """
    global_batch = max(1, grad_accum)  # micro_batch 1, gpu_count 1
    per_epoch = max(1, math.ceil(n_rows / global_batch))
    planned = max(1, per_epoch * max(1, int(epochs)))
    cap = int(max_steps)
    if max_wall_minutes is not None:
        cap = min(cap, steps_for_wall(max_wall_minutes))
    return max(1, min(planned, cap))


def observed_step_seconds(
    loss_curve: list[dict] | None,
    *,
    run_started: float | None,
    finished: float | None,
    steps: int,
) -> float | None:
    """Seconds per optimizer step from metric timestamps, else the watcher clock."""
    stamps: list[float] = []
    for point in loss_curve or []:
        if not isinstance(point, dict):
            continue
        raw = None
        for key in ("timestamp", "created_at", "time"):
            if point.get(key) is not None:
                raw = point[key]
                break
        if isinstance(raw, (int, float)):
            stamps.append(float(raw))
        elif isinstance(raw, str):
            try:
                stamps.append(float(raw))
            except ValueError:
                continue
    if len(stamps) >= 2 and stamps[-1] > stamps[0]:
        return (stamps[-1] - stamps[0]) / max(1, len(stamps) - 1)
    if (
        run_started is not None
        and finished is not None
        and finished > run_started
        and steps > 0
    ):
        return (float(finished) - float(run_started)) / int(steps)
    return None


def write_toml(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
