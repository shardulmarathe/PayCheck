# Checkout guard training runbook

Run every command from the `train/` directory after the package is installed. The default output directory is the repository `runs/` folder (the showcase site reads it). This repository is private. Do not make it public, do not push it anywhere else, and do not put API keys in files, command lines, or logs.

`gym/schema/README.md` is the label contract: `page_id`, `store`, `family`, `attack_type`, `verdict`, `selector`, `bbox`, `evidence_text`, `instruction`, `source`, `split`, and `group_id` (the template or near-duplicate family). On a pass, `attack_type` is `none` and both `evidence_text` and `instruction` are empty strings. Page text is not inside the JSONL. It lives at `<directory of the labels file>/text/<page_id>.txt`. Every eval and round reads that directory by default and exits 2 if a row still has no text. Each round report records whether the schema file exists. If field names differ, update `FIELD_ALIASES` in `guardtrain/schema.py` before a paid run.

The model sees the shopper view only. The user message keeps the host from the `url:` line and the `domain:` and `storefront_domain:` lines, plus the page text and one fixed sentence. The path after the host is removed. Public ids (`p-` plus 8 hex) and legacy ids are not in the prompt. Attack names and the words trick, clean, and none appear only in the fixed system instructions. Empty reader sections are the literal `(none)` on disk and become `(empty)` in the prompt. The gold assistant JSON is the training target, not a field the shopper sees.

## Safety

- Veri hard cap is **$55** of the $60 credit, including spend already on the ledger (listed L4 rate is $1.05/GPU-hour plus about $0.24 checkpoint storage). `--spend-cap` can only lower it. The ledger file is `~/.guardgym/veri_spend_ledger.json`, shared across checkouts, with a lock so two processes cannot both pass the cap. Before every live launch the process reads that ledger and the live balance, including once for the whole sweep and again immediately before each job create. It refuses when the projected cost of the jobs about to start, plus what is already committed, would pass the cap, or when those jobs would leave less than $3 of balance. Veri kills running jobs when the balance hits $0. The offline dry-run below still passes a $50 cap so it cannot touch the live budget. A ledger file created at a lower cap stays there; this code will not raise a stored cap.
- Gemini hard cap is **$2.50**, persisted in `runs/baselines/gemini_spend_ledger.json`. The run stops when the next worst-case check does not fit.
- Anthropic baseline default cap is $5. A flag above the $20 safety ceiling exits 2. The Opus teacher is separate: `python -m gym.distill` hard-stops at a cumulative `--max-usd` of $50 in `~/.guardgym/anthropic_teacher_ledger.json`. That file is not the $20 baseline ledger.
- Do not host a model on Veri. `veri deployments create` is not part of training. If an endpoint is ever created, it must include `--min-replicas 0`. `python -m guardtrain deploy-hint` prints that command and nothing else; do not run it during the hackathon. `veri deployments stop <id>` is immediate if one was created by mistake.
- `copycat_domain` and `listing_injection` are removed from every training file. Their names stay in the system prompt so the JSON contract is valid on the test set. Pass `--hide-held-out-labels` only if you want those names gone from the prompt too.
- Mine the next round's misses on the previous round's dev eval only. The loader rejects a miss file tagged `testset`, `slice100`, `test`, `frozen`, `eval`, or `not_for_training`, and it rejects a miss whose page id is in the frozen test set. Test-set and slice misses are never a training file.
- The wall-clock limit is a cancel watcher in this process. It retries a failed status read with backoff. A fatal error cancels the job in a `finally` block, settles the ledger, and writes the round report. Keep the process alive. If it dies anyway, the job can run until `max_steps` or the platform's 24-hour cap. Cancel a stranded job with the cancel line in the Veri command block below.
- Do not send Veri heartbeats. A job that never received one is not subject to heartbeat timeout.
- Secrets stay in the environment: `VERI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GEMINI_BASE_URL`. Names only are listed in `.env.example`. The CLI redacts keys before it writes a round report or prints an error.
- A live round refuses a mix with fewer than 32 trainable rows (`--min-rows` lowers that only for a deliberate tiny run). The fixture below is dry-run only.
- Anthropic and OpenAI clients are constructed with `max_retries=0`. A transport retry would be billed again against one ledger reservation.

## Setup

```bash
cd /path/to/guard-gym
python3 -m venv .venv
source .venv/bin/activate
pip install -e "./train[dev]"
cd train
```

On the Linux machine that will spend money, also install the API extra, the merge extra, and the Veri CLI (skill baseline veri-sdk 0.2.44 or newer). Do not echo the values.

```bash
pip install -e ".[api]"
pip install -e ".[merge]"
pip install -e ".[convert]"
uv tool install --upgrade 'veri-sdk[mcp]'
veri whoami
veri doctor
export VERI_API_KEY
export ANTHROPIC_API_KEY
export GEMINI_API_KEY
export GEMINI_BASE_URL
export LLAMA_CPP_DIR
export PORT=8000
```

`[api]` is `anthropic` and `openai`. `[merge]` is `torch`, `transformers`, and `peft` (required before converting a Veri adapter). `[convert]` is `huggingface_hub` (the `hf` CLI) and `gguf`. GGUF conversion also needs llama.cpp's `convert_hf_to_gguf.py` on `LLAMA_CPP_DIR`. Download a base with `hf download`, not an Ollama library tag:

```bash
hf download Qwen/Qwen3-4B-Instruct-2507 --local-dir ../models/Qwen3-4B-Instruct-2507
hf download Qwen/Qwen3Guard-Gen-4B --local-dir ../models/Qwen3Guard-Gen-4B
```

Each round is a fresh gym generation, not a reused `data/trainset/labels.jsonl`. From this directory, `python -m gym.train --round N --n-train 1500 --n-dev 300 --out ../data/trainset/roundN` writes that round's train labels, `text/`, and `dev/`. Rounds start at 1. The default round is 1500 train pages and 300 dev pages. The dev split holds out whole `group_id` families. A group never appears on both sides. Public page ids are `p-` plus 8 hex. Labels keep `legacy_page_id`. Frozen test labels carry `slice`: `in_dist`, `heldout_template`, or `heldout_attack`. Clean and trick pages must match within 15 points on checkbox, popup, fee line, and strike-through, on train and on dev, once a round generates at least 100 pages. Frozen pages live under `../data/testset/` with text at `../data/testset/text`. The 100-page slice list is `../gym/testset/slice100.txt`. The test-set hash is read at runtime from `gym/testset/manifest.json` (`content_hash`). Do not paste that hash into code or this file; the set can be re-frozen. The prompt still does not print the page id or the URL path.

## Commands, in order

Offline proof first. Paid commands are last, and only on the machine that has the keys.

```bash
python -m pytest
```

```bash
python -m guardtrain format \
  --labels fixtures/mini_labels.jsonl \
  --out /tmp/sft.jsonl
```

```bash
python -m guardtrain round \
  --round 0 \
  --labels fixtures/mini_labels.jsonl \
  --max-wall-minutes 60 \
  --spend-cap 50 \
  --dry-run
```

Dry-run writes `runs/training/round0.json` with `dry_run: true`, the reservation (`$1.29` at 60 minutes), and the Veri command list. It does not talk to Veri, does not move the ledger, and does not write a Modelfile. The fixture has fewer than 32 trainable rows, so the same command without `--dry-run` exits 2.

```bash
python -m guardtrain convert \
  --base-model Qwen/Qwen3-4B-Instruct-2507 \
  --outfile ../models/qwen3-4b-instruct-2507-q8_0.gguf \
  --dry-run
```

Prove conversion on the untrained base before any paid job. The real convert, after the `hf download` above, is the same command without `--dry-run` and with `--hf-dir ../models/Qwen3-4B-Instruct-2507`. Optional `--quantize Q4_K_M`. On out-of-memory QLoRA, rerun training with `--base-model Qwen/Qwen3-1.7B`. Do not auto-resubmit a failed job. `--dry-run` prints the plan and does not write a Modelfile.

SFT jobs, DPO jobs, and the GGUF convert all use `Qwen/Qwen3-4B-Instruct-2507`, the non-thinking instruct model. Veri's SFT Unsloth demo submits that id as `base_model` with `method="sft_text"`. There is no public catalog of every trainable base (`GET /v1/models` lists models already in the account), and this environment has no `VERI_API_KEY`, so the demo is the check. The hybrid `Qwen/Qwen3-4B` is not the training base and is not the merge base. An adapter directory is merged with `Qwen/Qwen3-4B-Instruct-2507` and then passed to `convert_hf_to_gguf.py`, including when `--base-model` is omitted on `convert`.

```bash
python -m guardtrain eval \
  --model mock-guard \
  --round base \
  --backend mock \
  --labels fixtures/mini_labels.jsonl \
  --slice fixtures/slice.txt \
  --also-slice \
  --page-set testset
```

This writes `runs/eval/mock-guard_base.json` and `runs/eval/mock-guard_base_slice100.json` (catch rate, clean false blocks, evidence-quote match, latency, cost per check, cost per 1,000 checks, the page set, and `testset_content_hash` from the manifest). `mock-guard` rows are left out of `runs/eval/leaderboard.json`. A row with no inline text and no `<labels>/text/<page_id>.txt` fails the command.

```bash
python -m guardtrain serve --backend mock --dry-run
python -m guardtrain serve --backend ollama --ollama-model guard-qwen3
```

`/check` accepts `{"page_text", "page_id", "store"}` and returns `verdict`, `attack_type`, `evidence`, `instruction`. It binds `0.0.0.0:$PORT` (default 8000). Page text is not logged. Unparseable model text is HTTP 422. An upstream failure from Ollama or llama.cpp is HTTP 502.

Qwen3 thinking is off on every local call: Ollama JSON sends `"think": false`, llama.cpp sends `chat_template_kwargs.enable_thinking: false`, and the parser strips a `<think>` block before it reads the JSON or the `Safety:` line.

Local llama.cpp server, then either backend:

```bash
llama-server -m ../models/qwen3-4b-instruct-2507-q8_0.gguf --host 0.0.0.0 --port 8081 -c 4096 -n 512 --temp 0
python -m guardtrain serve --backend llama-cpp --llama-url http://127.0.0.1:8081/v1 --llama-model guard
```

Ollama, after the Modelfile written next to the GGUF by a real convert:

```bash
ollama create guard-qwen3 -f ../models/qwen3-4b-instruct-2507-q8_0.Modelfile
ollama serve
```

The untrained baseline is the same Hugging Face base as the guard, `Qwen/Qwen3-4B-Instruct-2507`, converted locally to `models/qwen3-4b-instruct-2507-q8_0.gguf` and created in Ollama as `qwen3-4b-instruct-2507`. Do not pull the library tag `qwen3:4b`. Qwen3Guard is a local conversion of `Qwen/Qwen3Guard-Gen-4B` to `models/qwen3guard-gen-4b-q8_0.gguf` (`qwen3guard-gen-4b`). There is no `qwen3guard:4b` library tag. Neither baseline calls Veri, so neither spends the $50 budget and no replica is hosted. Qwen3Guard's native line is `Safety: Safe|Unsafe|Controversial`; `--adapter auto` maps that into the JSON contract. Safe is pass with an empty instruction. Unsafe or Controversial is block with `attack_type` `none` (type accuracy will be low). That is honest.

```bash
python -m guardtrain baseline-local \
  --model qwen3-4b \
  --backend ollama \
  --labels fixtures/mini_labels.jsonl \
  --slice fixtures/slice.txt \
  --also-slice \
  --adapter json \
  --dry-run

python -m guardtrain baseline-local \
  --model qwen3guard-4b \
  --backend ollama \
  --labels fixtures/mini_labels.jsonl \
  --slice fixtures/slice.txt \
  --also-slice \
  --adapter auto \
  --dry-run
```

Drop `--dry-run` on the machine that has the GGUF loaded. Score the frozen set and the slice with `--labels ../data/testset/labels.jsonl --pages-dir ../data/testset/text --slice ../gym/testset/slice100.txt`.

Gemini goes through the Stanford gateway (`GEMINI_BASE_URL`, Bearer `GEMINI_API_KEY`, OpenAI-compatible SDK). Thinking is `reasoning_effort=low` only. Temperature is omitted. Flash output is capped at 256 tokens. Pro defaults to 1024 because thinking tokens count against the output cap. Probe five pages before any full run. The pro preview model refuses to run unless `--slice` is set (or you explicitly pass `--allow-full-testset`).

```bash
python -m guardtrain baseline-gemini \
  --model gemini-3.7-flash \
  --probe 5 \
  --spend-cap 2.50 \
  --thinking-level low \
  --labels fixtures/mini_labels.jsonl \
  --dry-run
```

Read `worst_case_per_check_usd` in the printed plan. Then the same command without `--dry-run` and without `--probe` for the flash model on the label file you intend to score, with `--pages-dir ../data/testset/text` when that file is the frozen set. Then the pro model on the slice only:

```bash
python -m guardtrain baseline-gemini \
  --model gemini-3.1-pro-preview \
  --labels ../data/testset/labels.jsonl \
  --pages-dir ../data/testset/text \
  --slice ../gym/testset/slice100.txt \
  --spend-cap 2.50 \
  --thinking-level low \
  --max-tokens 1024 \
  --dry-run
```

Drop `--dry-run` only after the probe price looks safe. The ledger stops the run when the next worst-case check would cross $2.50. One in-flight call can settle slightly above its reservation if the bill exceeds the pre-check; the next call does not start. A crash leaves the open reservation counting against the cap.

```bash
python -m guardtrain baseline-anthropic \
  --model claude-sonnet-5-5 \
  --spend-cap 5 \
  --effort low \
  --max-tokens 512 \
  --labels fixtures/mini_labels.jsonl \
  --slice fixtures/slice.txt \
  --also-slice \
  --dry-run
```

Sonnet 5.5 is called with `output_config.effort=low` and no temperature, top_p, or thinking budget. List price used for the cost column is $2 / MTok input and $10 / MTok output. Cache is not used. Drop `--dry-run` for the real score. Published prices, retrieved 2026-10-17: Gemini 3 Flash preview $0.50 / $3, Gemini 3.7 Flash $0.75 / $3.75 through 2026-12-31 and $1.50 / $7.50 after that, Gemini 3.1 Pro preview $2 / $12 (output includes thinking, prompts at or under 200k). Unknown model names are refused rather than priced at $0. Override both `--input-usd-per-mtok` and `--output-usd-per-mtok` if the gateway markup differs.

Show the ledger, generate round 1, distill the train pages, then launch the round. Round 1 starts from `Qwen/Qwen3-4B-Instruct-2507`.

```bash
python -m guardtrain ledger show --which veri
```

```bash
python -m gym.train --round 1 --n-train 1500 --n-dev 300 --out ../data/trainset/round1
```

```bash
python -m gym.distill --round 1 --max-usd 50 --labels ../data/trainset/round1/labels.jsonl
```

Score the base model on that round before any paid training. This writes `runs/r0/replay.jsonl` and `runs/r0/summary.json`. Test pages are scored into the summary and are not written into the replay.

```bash
python -m guardtrain round-eval \
  --round 0 \
  --backend ollama \
  --ollama-model qwen3-4b-instruct-2507 \
  --train-labels ../data/trainset/round1/labels.jsonl \
  --dev ../data/trainset/round1/dev/labels.jsonl \
  --pages-dir ../data/trainset/round1/text
```

```bash
python -m guardtrain round \
  --round 1 \
  --labels ../data/trainset/round1/labels.jsonl \
  --dev ../data/trainset/round1/dev/labels.jsonl \
  --pages-dir ../data/trainset/round1/text \
  --max-queue-minutes 30 \
  --max-steps 400 \
  --spend-cap 55
```

`--max-steps 400` is a ceiling. The launched config asks for at most 2 epochs and sets `max_steps` to that same plan, because Veri treats `max_steps` as an override of `num_epochs` when both are set. Early stopping uses dev trick F1 minus the clean false-block rate: when per-epoch dev scores exist, a later epoch that does not beat the best so far is not kept. Veri's managed job does not see the dev split, so the hard cap of 2 epochs is what the config launches. `use_unsloth` is true. Veri's managed `sft_text` path has no completion-only loss, so the system prompt stays short. Omitting `--max-wall-minutes` sizes the wall to that epoch plan (90 seconds per step, plus 8 minutes to boot and 10 minutes to flush). Passing `--max-wall-minutes 60`, as the dry-run above does, still caps the job at 28 steps and reserves $1.29. The round report records `max_steps`, `epochs`, `step_seconds`, `cost_usd`, and `steps_allowed_by_wall`. Distill runs on this box with `ANTHROPIC_API_KEY`. The only teacher is `claude-opus-5-5`. It reads train pages only, caches by page hash, and hard-stops at the cumulative $50. SFT uses the short teacher JSON when the verdict matches the label, and the label JSON otherwise. Dev and test scoring still use the labels.

What that command runs, in order:

```text
veri datasets check <payload.jsonl>
veri datasets upload <payload.jsonl> --name guard-sft_text-r0-<sha8> --format json
veri jobs estimate <round0.toml> --format json
veri billing balance --format json
veri jobs create <round0.toml> --format json
veri jobs get <job_id> --format json
veri jobs cancel <job_id>
veri jobs download <job_id> --output-dir runs/training/checkpoints/round0
veri checkpoints list <job_id> --format json
veri checkpoints download <job_id> <ckpt> --output runs/training/checkpoints/round0 --artifact adapter
GET /v1/training_jobs/<job_id>/metrics
python -m guardtrain merge --adapter <checkpoint> --base Qwen/Qwen3-4B-Instruct-2507 --out <checkpoint>/merged
```

The cancel line runs if the queue limit or the wall-clock limit trips, if you interrupt the process, or if status reads keep failing. The watcher retries those reads with exponential backoff (capped at 60 seconds) and cancels after five failures. The ledger is settled and `runs/training/roundN.json` is written before either download. A download error is recorded on that report and does not reopen the reservation. Final weights are fetched only after status `completed`. If the GPU ran and the job was cancelled, the newest intermediate adapter is fetched instead (`--artifact adapter`). A cancel that never left the queue downloads nothing and settles at $0. The metrics GET runs when the job reaches a terminal status. The config is `kind = "train"`, `[method] type = "sft_text"`, QLoRA (`lora_rank` 16, `lora_alpha` 32, `load_in_4bit` true, `use_unsloth` true), one L4-24GB. There is no `[reward]` or `[deployment]` block. `[huggingface]` is required: `artifact = "merged"` and `private = true`, repo `shardulmarathe/sureshop-guard-rN-<trial>`. A public repo is refused. A failed push does not fail the Veri job; the round log records `hf_repo_url` only when the push landed.

The round file is `runs/training/round0.json` (job id, cost, loss curve, command list). Loss comes from `GET /v1/training_jobs/{id}/metrics`. The first values key whose name contains `loss` is stored, plus the raw values.

## After round 0

Download is inside the live round. QLoRA downloads are adapters (`adapter_config.json`) unless the private merged repo was recorded. `convert --hf-repo shardulmarathe/sureshop-guard-rN-<trial>` pulls that merged repo and converts it as a full model. An adapter directory is still merged locally when you pass `--hf-dir`. If torch, transformers, or peft are missing, that path exits with `run merge first` and does not treat the adapter as a full model. Repos outside `shardulmarathe/` are refused. Serve and score the frozen test set and the slice. Every pushed repo stays private.

```bash
python -m guardtrain merge \
  --adapter ../runs/training/checkpoints/round0 \
  --base Qwen/Qwen3-4B-Instruct-2507 \
  --out ../runs/training/checkpoints/round0/merged \
  --dry-run

python -m guardtrain convert \
  --hf-dir ../runs/training/checkpoints/round0 \
  --base-model Qwen/Qwen3-4B-Instruct-2507 \
  --outfile ../models/guard-round0-q8_0.gguf \
  --dry-run
```

Drop `--dry-run` when the adapter and `LLAMA_CPP_DIR` are on disk. Then serve as above and score. Missing page text fails this command:

```bash
python -m guardtrain eval \
  --model guard-round0 \
  --round round0 \
  --backend ollama \
  --ollama-model guard-qwen3 \
  --labels ../data/testset/labels.jsonl \
  --pages-dir ../data/testset/text \
  --slice ../gym/testset/slice100.txt \
  --also-slice \
  --page-set testset
```

The round report is the record of that round. After the adapter is served, score the train sample, the dev split, and the frozen test set into `runs/training/round1.json`. That command writes `runs/training/datasets/round1.dev.misses.jsonl` and `runs/r1/replay.jsonl` plus `runs/r1/summary.json`. It does not replace `runs/r0/`, which is the base model scored before training. A hash change is recorded as `testset_hash_changed_since_train` and does not fail the score. The manual test eval above does not write a miss file. `heldout_template` is the headline slice. `heldout_attack` is reported as recall only, and its `false_block_rate` is null because that slice has no clean pages.

```bash
python -m guardtrain round-eval \
  --round 1 \
  --backend ollama \
  --ollama-model guard-qwen3 \
  --labels ../data/testset/labels.jsonl \
  --pages-dir ../data/testset/text \
  --slice ../gym/testset/slice100.txt
```

`summary.json` keys are exactly `round`, `winner_trial`, `new_pages`, `seeded_from_misses`, `train`, `dev`, `test`, and `in_dist_vs_heldout_template_gap` (in-distribution F1 minus heldout-template F1). `train`, `dev`, and each of `test.in_dist`, `test.heldout_template`, and `test.heldout_attack` are `{catch_rate, false_block_rate, f1, n}`. Each `replay.jsonl` line is one train or dev page: `round`, `page_id` (`p-` plus 8 hex), `store`, `page_kind`, `trick`, `split`, `label`, `verdict`, `correct`, `fed_back`, `source` (`fresh` or `from_miss`). Test page ids are refused. `roundN.json` then has catch rate, clean false blocks, and evidence-quote match per attack type for the train sample, the dev split, and the frozen test set, plus the three slices, the slice file, the train-dev gap, and the test-set hash read from the manifest. It also records `groups` (train and dev group ids, shared groups empty) and `structure` (class-conditional rates of checkbox, popup, fee line, and strike-through on train and on dev, by verdict and by attack type). Those rates are a check for a structure shortcut. They are not training features.

A live later round refuses to start until the previous round's dev eval is scored, and it refuses if the gym overlap check finds test-set strings in the train mix or the dev split. The mix is this round's fresh train pages, this round's attacker pages when that JSONL exists (held out by the same `group_id` rule), the previous round's dev misses, and a small replay of older dev misses. No step in this pipeline calls Grok. Train and dev pages come from the seeded template generator. Attacker pages are rendered specs, not model prose. Distillation calls Claude Opus (`claude-opus-5-5`) and nothing else. Replay is stratified by attack type and capped at the larger of 8 and one fifth of the fresh rows that survived the filters. Dev groups are dropped from the mix. `copycat_domain` and `listing_injection` stay out.

Round 1 starts from `Qwen/Qwen3-4B-Instruct-2507`. Later SFT rounds start from the previous round's private merged winner. Veri `resume_from` is not used: it keeps the previous method, dataset, and LoRA settings, so it cannot train a new page set and it cannot turn SFT into DPO. If that push was not recorded, pass `--retrain-from-base` to retrain from `Qwen/Qwen3-4B-Instruct-2507` on the cumulative train pages plus the fresh pages aimed at the previous dev misses. A dry-run repo name is not a push.

```bash
python -m gym.train --round 2 --n-train 1500 --n-dev 300 --out ../data/trainset/round2
```

```bash
python -m guardtrain round \
  --round 2 \
  --labels ../data/trainset/round2/labels.jsonl \
  --dev ../data/trainset/round2/dev/labels.jsonl \
  --pages-dir ../data/trainset/round2/text \
  --spend-cap 55
```

Omit `--misses` to load `runs/training/datasets/round0.dev.misses.jsonl`. For round 2 and later, older dev-miss files load on their own. Attacker labels are picked up from `data/attacker/roundN/labels.jsonl` when that file exists; pass `--attacker` to point elsewhere.

## Sweep

Compare against the `claude-sonnet-5-5` baseline on the frozen test set by searching on dev, not by fitting the test set. A sweep launches at most 4 Veri QLoRA jobs at once (Veri's concurrency cap), for example learning rate by LoRA rank. `configs/sweep.example.yaml` is that grid, with `spend_cap` `55.00` and `max_parallel` 4. The launch checks the shared ledger and the live balance for every job in the sweep before the first create, and checks the balance again immediately before each create. A config that would cross $55, including prior spend, or leave less than $3 of balance, is not created. `gym.train --sweep` and `guardtrain sweep` are dry runs unless `--submit` is passed. Passing both `--submit` and `--dry-run` is an error. Each finished job is downloaded, including a checkpoint adapter when the wall clock or the queue limit cancels a job that already reached a GPU. Served names are `guard-rN-<trial>`.

The winner is the highest dev score: F1 on tricks minus the false-block rate on clean dev pages. Ties prefer fewer clean false blocks. Every config's train-sample and dev scores are stored on `roundN.json`. The frozen test set and the slice are scored only for the winner.

Generate the round and launch the sweep together:

```bash
python -m gym.train --round 1 --n-train 1500 --n-dev 300 --out ../data/trainset/round1 --sweep configs/sweep.example.yaml --submit
```

Score one downloaded adapter at a time, after that adapter is the model behind the server. Do not pass one backend for every trial: that would score four different adapters as if they were the same model.

```bash
python -m guardtrain sweep-score \
  --round 1 \
  --trial lr1e-04-r16 \
  --model guard-r1-lr1e-04-r16 \
  --backend ollama
```

Repeat for each trial, with that trial's own `--model guard-r1-<trial>`. Two trials that resolve to the same model are refused. Then score the frozen set for the winner only:

```bash
python -m guardtrain sweep-score \
  --round 1 \
  --trial lr1e-04-r16 \
  --model guard-r1-lr1e-04-r16 \
  --testset \
  --backend ollama \
  --labels ../data/testset/labels.jsonl \
  --pages-dir ../data/testset/text \
  --slice ../gym/testset/slice100.txt
```

Optional DPO, once, from that winner. Set `dpo: true` in the sweep file when the sweep can score inside the same process. When the adapters were scored later, launch DPO only after the winner exists. Pairs are the winner's dev false blocks and dev misses, and only from groups the judge split does not use. The judge file is `roundN.dpo.judge.jsonl`. Test pages are not pairs. DPO starts from this round's private merged SFT winner, never from `Qwen/Qwen3-4B-Instruct-2507`. A second live DPO round exits 2. A DPO launch that would break the $55 cap or the $3 floor is recorded as `refused_budget` and does not undo the SFT jobs.

```bash
python -m guardtrain sweep-score \
  --round 1 \
  --trial lr1e-04-r16 \
  --model guard-r1-lr1e-04-r16 \
  --launch-dpo \
  --dry-run
```

Drop `--dry-run` to submit the DPO job. The dry-run writes the pair file and names the base. It does not call Veri.

If `cost_confidence` in the round report is `reserved_upper_bound`, the job payload did not include a known cost field. The ledger kept the reservation so the cap stays honest. Reconcile from `veri billing transactions` and settle:

```bash
python -m guardtrain ledger show --which veri
python -m guardtrain ledger settle --which veri --entry <entry id> --actual 1.39 --job-id <job id>
python -m guardtrain ledger show --which gemini
python -m guardtrain ledger show --which anthropic
```

A cancel while the job is still queued settles at $0 (no GPU, no storage). A create that fails before a job id releases the reservation.

## Veri CLI details

Checked against the public docs and the veri-sdk 0.2.44 skill:

- SFT is a config file with `method.type = "sft_text"`. Inline `veri jobs create --base-model --dataset` is GRPO and requires a reward. This pipeline never sends a reward.
- QLoRA is `lora_rank` plus `load_in_4bit`, and it is single-GPU. `gpu_count` is 1. Multi-GPU 4-bit is HTTP 400.
- `veri jobs estimate` is GPU time only. The reservation is the larger of (estimate + $0.24) and (wall minutes × $1.05 + $0.24), rounded to the cent. 60 minutes is $1.29. 90 minutes is $1.82. 20 minutes is $0.59.
- Job ids are bare hex. Upload of identical bytes returns the existing dataset id. The trainer file contains only `messages` (or `prompt` / `chosen` / `rejected` for DPO), not label metadata.
- `veri jobs download` returns the Hugging Face checkpoint directory. For LoRA that is the adapter. There is no documented `veri jobs download --artifact merged`. The train config's `[huggingface] artifact = "merged"` and `private = true` ask Veri to merge and upload a private repo. Intermediate checkpoints use `veri checkpoints list` and `veri checkpoints download <job_id> <ckpt> --artifact adapter` (`--output` chooses the directory). That feature may be behind a flag; if the list is empty the round report records `download_error` after the ledger is already settled. Do not relaunch.
- LoRA jobs cannot `veri deploy <job_id>` (known 400, VS-559). We do not deploy.
- Billing starts at instance boot, including failed jobs that got a GPU. Queue cancel and capacity failure before a GPU are not billed. Total is rounded to the cent. Concurrency cap is 4 in-flight jobs. HTTP 402 means the account is out of credit. HTTP 429 concurrent-job limit is not a retry.
- Listed L4 rate $1.05/GPU-hour; the exact card rate in the docs is $1.0462. The ledger uses $1.05 unless `rate_usd_per_hour` comes back on the estimate.

Unsure, and what the code does about it:

- No submit-time wall-clock field shorter than the platform 24-hour running cap was found. The hard limit is this process polling `veri jobs get` and calling `veri jobs cancel` after the wall, measured from the first status that is neither queued nor terminal. The CLI leaves the wall unset so it fits the 2-epoch cap. Pass `--max-wall-minutes 60` to cap a job at 28 steps. `--max-queue-minutes` (default 30) is separate because queue time is unbilled. If the poller is not running, cancel the job yourself.
- The 90-second step budget is a planning cap so 400 steps cannot be scheduled into a 60-minute wall. It is not a measured step time on this hardware. If a real job is slower, the watcher still cancels and then tries the newest adapter checkpoint.
- The loss key inside metrics `values` is not a fixed name. The curve stores the first key containing `loss` and the full `values` object. There is no documented `veri jobs metrics` subcommand; metrics are `GET /v1/training_jobs/{id}/metrics` with `Authorization: Bearer` from `VERI_API_KEY`.
- The billed-cost field on `veri jobs get` is not documented. The parser looks for `cost_usd`, `billed_cost_usd`, `actual_cost_usd`, `total_cost_usd`, `cost`, then `usage` / `billing`. If the GPU ran and none of those exist, the ledger settles the reserved upper bound. Reconcile with `veri billing transactions`.
- The checkpoint list JSON may be a list or an object with `checkpoints`, `data`, or `items`. The newest numeric `step` wins; otherwise the first id is used (the docs say the list is newest-first).
- Whether the SFT trainer accepts a `system` role was not confirmed against `training_runtime.py`. The default dataset uses a real system message, because the guard prompt is the system prompt. `--system-in-user` bakes that prompt into the user message if a job rejects the system role.
- The Stanford gateway may or may not forward `reasoning_effort`. Sending `extra_body.google.thinking_config` as well makes Google's compat layer return 400, so only `reasoning_effort` is sent. The spend cap is the real stop.
- DPO from the SFT adapter via `veri jobs resume` is not supported (resume keeps the same method, dataset, and LoRA). A new DPO job sets `base_model` to this round's private merged SFT repo. It does not start from `Qwen/Qwen3-4B-Instruct-2507`. Pairs come from the winner's dev false blocks and dev misses only, on groups the judge split does not include.

## Do not

- Do not run a deployment. Do not drop `--min-replicas 0` if you ever do.
- Do not train on test-set or slice misses. Do not score the frozen test set for a sweep config that lost on dev.
- Do not put `page_id` or the URL path in the guard prompt. The shopper view keeps the host, the domain lines, and the page text.
- Do not distill dev pages or the frozen test set. Do not raise the Opus teacher cap past the cumulative $50 without changing `--max-usd`, and do not let a later round ignore spend already in the teacher ledger.
- Do not push a public Hugging Face repo. `private` must be true.
- Do not train or merge the hybrid `Qwen/Qwen3-4B`. SFT, DPO, and GGUF conversion use `Qwen/Qwen3-4B-Instruct-2507`.
- Do not commit `.env`, `models/`, `*.gguf`, checkpoints, or `runs/training/datasets/*.jsonl`.
- Do not launch a second live job for a round whose reservation is still open. Settle or release it first. Do not launch a wave that would leave the Veri balance under $3.
- Do not hard-code the test-set content hash.
