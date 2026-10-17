"""GGUF conversion and LoRA merge commands.

``veri jobs download`` returns an HF checkpoint. For QLoRA the checkpoint is
the adapter. Merged dense weights are produced locally with PEFT, then
``convert_hf_to_gguf.py``. The same commands convert the untrained base model,
which is how conversion is proven before any paid job.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from guardtrain.schema import PRIMARY_BASE_MODEL, ContractError
from guardtrain.veri import classify_checkpoint


def llama_cpp_convert(llama_cpp_dir: str | None = None) -> str:
    directory = llama_cpp_dir or os.environ.get("LLAMA_CPP_DIR") or "$LLAMA_CPP_DIR"
    return str(Path(directory) / "convert_hf_to_gguf.py")


def plan_conversion(
    *,
    hf_dir: Path | None,
    outfile: Path,
    base_model: str | None = None,
    outtype: str = "q8_0",
    llama_cpp_dir: str | None = None,
    quantize: str | None = None,
    hf_repo: str | None = None,
) -> list[str]:
    commands: list[str] = []
    source = hf_dir
    full_model = False
    if hf_repo:
        if not str(hf_repo).startswith("shardulmarathe/"):
            raise ContractError(
                f"Refusing to pull {hf_repo}. Local conversion of a trained guard "
                "only pulls a shardulmarathe repo, or an explicit directory."
            )
        source = Path("models") / hf_repo.split("/")[-1]
        commands.append(f"hf download {hf_repo} --local-dir {source}")
        full_model = True
    elif source is None:
        if not base_model:
            raise ContractError("Pass --hf-dir, --hf-repo, or --base-model.")
        source = Path("models") / base_model.split("/")[-1]
        commands.append(f"hf download {base_model} --local-dir {source}")
    kind = "full" if full_model else (classify_checkpoint(source) if source.exists() else "unknown")
    convert_input = source
    if not full_model and (kind == "adapter" or (hf_dir is not None and (hf_dir / "adapter_config.json").exists())):
        merged = source / "merged"
        base = base_model or PRIMARY_BASE_MODEL
        commands.append(
            "python -m guardtrain merge "
            f"--adapter {source} --base {base} --out {merged}"
        )
        convert_input = merged
    script = llama_cpp_convert(llama_cpp_dir)
    commands.append(
        f"python {script} {convert_input} --outfile {outfile} --outtype {outtype}"
    )
    if quantize:
        quant_out = outfile.with_name(outfile.stem + f"-{quantize}" + outfile.suffix)
        llama_quantize = str(Path(llama_cpp_dir or "$LLAMA_CPP_DIR") / "build" / "bin" / "llama-quantize")
        commands.append(f"{llama_quantize} {outfile} {quant_out} {quantize}")
    modelfile = outfile.with_suffix(".Modelfile")
    commands.append(f"ollama create guard-qwen3 -f {modelfile}")
    return commands


def modelfile_text(gguf: Path, *, num_ctx: int = 4096, num_predict: int = 512) -> str:
    return (
        f"FROM {gguf.resolve()}\n"
        "PARAMETER temperature 0\n"
        f"PARAMETER num_ctx {num_ctx}\n"
        f"PARAMETER num_predict {num_predict}\n"
    )


def merge_adapter(adapter_dir: Path, base_model: str, out_dir: Path) -> None:
    """Load the base in fp16 and merge the LoRA adapter. Needs the base weights on disk or HF cache."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer_source: str | Path = adapter_dir if (adapter_dir / "tokenizer_config.json").exists() else base_model
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_source)
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="cpu",
        low_cpu_mem_usage=True,
    )
    merged = PeftModel.from_pretrained(base, adapter_dir).merge_and_unload()
    out_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)


def parse_merge_command(command: str) -> tuple[Path, str, Path]:
    parts = command.split()

    def flag(name: str) -> str:
        if name not in parts or parts.index(name) + 1 >= len(parts):
            raise ContractError(f"merge command is missing {name}: {command}")
        return parts[parts.index(name) + 1]

    return Path(flag("--adapter")), flag("--base"), Path(flag("--out"))


def run_convert(commands: list[str], *, dry_run: bool, merge_fn=None) -> None:
    """Run download, merge, and GGUF conversion.

    An adapter directory is merged in this process. If torch/peft are missing,
    the command fails with ``run merge first`` instead of converting the adapter
    as if it were a full model. Ollama ``create`` is left for the operator.
    """
    if dry_run:
        return
    merger = merge_fn or merge_adapter
    for command in commands:
        if command.startswith("ollama create"):
            continue
        if command.startswith("python -m guardtrain merge"):
            adapter, base, out = parse_merge_command(command)
            try:
                merger(adapter, base, out)
            except ImportError as exc:
                raise ContractError(
                    "run merge first: pip install -e \".[merge]\" "
                    f"({exc}). Then run: {command}"
                ) from None
            continue
        subprocess.run(command, shell=True, check=True)


def write_modelfile(path: Path, gguf: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(modelfile_text(gguf), encoding="utf-8")


def safe_deploy_hint(model: str) -> list[str]:
    """Not part of the training path. If an endpoint is ever created, scale to zero."""
    return [
        "veri",
        "deployments",
        "create",
        "--from-hf",
        model,
        "--name",
        "guard-do-not-leave-running",
        "--gpu-type",
        "L4-24GB",
        "--min-replicas",
        "0",
        "--max-replicas",
        "1",
        "--no-cache",
    ]
