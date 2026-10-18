"""Label contract for the checkout guard.

``gym/schema/README.md`` is the source of truth. On a pass, evidence and
instruction are empty strings and attack_type is none. Page text is loaded
from ``<labels dir>/text/<page_id>.txt`` when the JSONL row does not carry it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FAMILIES = ("upsell", "scam", "clean")
ATTACK_TYPES = (
    "hidden_fees",
    "preselected_addon",
    "price_change",
    "subscription_trap",
    "copycat_domain",
    "fake_card_verification",
    "listing_injection",
    "none",
)
VERDICTS = ("block", "pass")
HELD_OUT_ATTACKS = frozenset({"copycat_domain", "listing_injection"})
# Miss files tagged with these page sets are never training data.
FORBIDDEN_TRAIN_PAGE_SETS = frozenset(
    {"testset", "slice100", "test", "frozen", "eval"}
)
FORBIDDEN_SPLITS = frozenset({"test", "eval", "frozen", "slice", "slice100"})
OUTPUT_KEYS = ("verdict", "attack_type", "evidence", "instruction")

PRIMARY_BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
FALLBACK_BASE_MODEL = "Qwen/Qwen3-1.7B"
QWEN3GUARD_HF = "Qwen/Qwen3Guard-Gen-4B"
# Local names created from those HF repos. Not Ollama library tags.
LOCAL_OLLAMA_MODELS = {
    "qwen3-4b": "qwen3-4b-instruct-2507",
    "qwen3guard-4b": "qwen3guard-gen-4b",
}
LOCAL_GGUF = {
    "qwen3-4b": "models/qwen3-4b-instruct-2507-q8_0.gguf",
    "qwen3guard-4b": "models/qwen3guard-gen-4b-q8_0.gguf",
}
MIN_TRAIN_ROWS = 32

VERI_HARD_CAP_USD = "55.00"
VERI_BALANCE_FLOOR_USD = "3.00"
VERI_MAX_PARALLEL = 4
GEMINI_HARD_CAP_USD = "2.50"
ANTHROPIC_DEFAULT_CAP_USD = "5.00"
ANTHROPIC_HARD_CAP_USD = "20.00"
L4_LISTED_USD_PER_HOUR = "1.05"
CHECKPOINT_STORAGE_USD = "0.24"

DEFAULT_MAX_WALL_MINUTES = 60
DEFAULT_MAX_QUEUE_MINUTES = 30
DEFAULT_MAX_STEPS = 400
DEFAULT_EPOCHS = 2
MAX_EPOCHS = 2
DEFAULT_MAX_PAGE_TOKENS = 2000
DEFAULT_MAX_SEQ_LENGTH = 4096
DEFAULT_LORA_RANK = 16
DEFAULT_LORA_ALPHA = 32
DEFAULT_GRAD_ACCUM = 8
HF_NAMESPACE = "shardulmarathe"
HF_REPO_PREFIX = "sureshop-guard"


def guard_model_name(round_index: int, trial: str) -> str:
    """Served name for one sweep trial. Two trials never share a name."""
    return f"guard-r{int(round_index)}-{trial}"


def hf_repo_name(round_index: int, trial: str) -> str:
    """Private Hugging Face repo for that trial's merged weights."""
    return f"{HF_NAMESPACE}/{HF_REPO_PREFIX}-r{int(round_index)}-{trial}"

VERDICT_ALIASES = {
    "block": "block",
    "pass": "pass",
    "allow": "pass",
    "reject": "block",
    "fail": "block",
    "ok": "pass",
}
ATTACK_ALIASES = {
    "hidden_fee": "hidden_fees",
    "hidden_fees": "hidden_fees",
    "preselected_addon": "preselected_addon",
    "preselected": "preselected_addon",
    "price_change": "price_change",
    "subscription_trap": "subscription_trap",
    "subscription": "subscription_trap",
    "copycat_domain": "copycat_domain",
    "copycat": "copycat_domain",
    "fake_card_verification": "fake_card_verification",
    "card_verification": "fake_card_verification",
    "listing_injection": "listing_injection",
    "none": "none",
    "": "none",
    "null": "none",
}

FIELD_ALIASES = {
    "page_id": ("page_id", "id", "page"),
    "store": ("store", "store_name", "merchant"),
    "family": ("family", "label_family"),
    "attack_type": ("attack_type", "attack"),
    "verdict": ("verdict", "decision"),
    "selector": ("selector", "css_selector"),
    "bbox": ("bbox", "bounding_box", "box"),
    "evidence_text": ("evidence_text", "evidence", "quote"),
    "instruction": ("instruction", "agent_instruction", "avoidance"),
    "source": ("source", "origin"),
    "split": ("split", "partition"),
    "page_text": (
        "page_text",
        "text",
        "extracted_text",
        "page_content",
        "visible_text",
        "body",
        "content",
    ),
    "page_set": ("page_set",),
    "model_output": ("model_output", "prediction_raw"),
}


class ContractError(Exception):
    """A dataset or flag violates the training contract."""


@dataclass
class LabelRow:
    page_id: str
    store: str = ""
    family: str = ""
    attack_type: str = ""
    verdict: str = ""
    selector: str = ""
    bbox: Any = None
    evidence_text: str = ""
    instruction: str = ""
    source: str = ""
    split: str = ""
    page_text: str = ""
    page_set: str = ""
    model_output: str = ""
    mix_source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "page_id": self.page_id,
            "store": self.store,
            "family": self.family,
            "attack_type": self.attack_type,
            "verdict": self.verdict,
            "selector": self.selector,
            "bbox": self.bbox,
            "evidence_text": self.evidence_text,
            "instruction": self.instruction,
            "source": self.source,
            "split": self.split,
            "page_text": self.page_text,
            "page_set": self.page_set,
            "model_output": self.model_output,
            "mix_source": self.mix_source,
        }
        if self.extra.get("group_id"):
            payload["group_id"] = self.extra["group_id"]
        return payload


def gym_schema_readme(root: Path | None = None) -> str | None:
    from guardtrain.paths import repo_root

    base = root or repo_root()
    path = base / "gym" / "schema" / "README.md"
    if path.is_file():
        return str(path)
    return None
