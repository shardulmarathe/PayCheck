# Attacker rounds

Round 1 is a training batch for the checkout guard. The specs live in `attacker/specs/round1/`. Each file is a trick spec (`gym/schema/trick_spec.json`) with `split` `train` and `source` `attacker-round1`.

Training attacks only:

| attack_type | variant | pages |
| --- | --- | ---: |
| `hidden_fees` | `drip` | 30 |
| `preselected_addon` | `checkbox` | 10 |
| `preselected_addon` | `modal` | 10 |
| `preselected_addon` | `one_click` | 10 |
| `price_change` | `drift` | 30 |
| `subscription_trap` | `autorenew` | 30 |
| `fake_card_verification` | `phishing` | 30 |
| `none` | `disclosed_fee` | 30 |
| `none` | `opt_in_clear` | 30 |
| `none` | `real_drop` | 30 |
| `none` | `legit_card` | 30 |
| `none` | `mixed_honest` | 30 |

`copycat_domain` and `listing_injection` stay out of every attacker round. They belong only to the frozen test set.

Clean pages (`attack_type` `none`, verdict `pass`) are honest pages that resemble tricks: a fee that was already printed on the tag, an add-on that is offered and left off, a real drop from last week's tag, or a card form on the shop's own host that does not ask for a bank-site secret.

## Near-duplicate check

Do not reuse text from `gym/build.py`, `data/testset/`, or any row in `data/ec-darkpattern/dataset.tsv` whose `page_id` is listed in `gym/splits/test_page_ids.txt`. That includes short lines.

```bash
python attacker/check_near_duplicates.py
python attacker/check_near_duplicates.py attacker/specs/round2
```

The check normalizes by lowercasing, turning punctuation into spaces, and collapsing whitespace. A spec fails when any copy window matches a test line, a test-spec string, a test-pile row, or a `gym/build.py` string constant, at any length. A field that is only a short test line (for example a line beginning "No thanks") fails even when that line is a prefix of a longer test sentence. Schema tokens that the renderer requires (`kind`, `attack_type`, `verdict`, and a known `variant` such as `checkbox`) are not copy. With no directory argument the script also requires the round-1 mix above. Another directory may use different counts, but every spec must still be `split` `train`, `source` `attacker-roundN`, and a training attack.

Render only after the check passes:

```bash
python -m gym.render_specs --specs-dir attacker/specs/round1 --out data/attacker-round1 --source attacker-round1
```

`gym/render_specs.py` rejects held-out attacks and any spec string that matches the frozen test pile. If `main` has moved, rebase onto it and rerun the near-duplicate check before rendering. A re-frozen test set changes the banned lines.

Regenerate round 1 from the writer, then rerun the check:

```bash
python -m attacker.build_round1
```

## Next round, from a misses file

After a dev eval, the misses file is `runs/eval/*_misses.json`. It may be a list, or an object with one of `misses`, `errors`, or `pages`. Each item names the page and what the guard got wrong:

```json
{
  "misses": [
    {
      "page_id": "dev-hidden_fees-014",
      "gold": {"attack_type": "hidden_fees", "variant": "drip", "verdict": "block", "evidence_text": "..."},
      "pred": {"attack_type": "none", "verdict": "pass", "evidence_text": ""},
      "miss_kind": "false_pass"
    }
  ]
}
```

If `miss_kind` is absent, infer it:

| Situation | miss_kind |
| --- | --- |
| Gold verdict is `block` and the prediction is `pass` | `false_pass` |
| Gold verdict is `pass` and the prediction is `block` | `false_block` |
| Verdicts agree and `attack_type` differs | `wrong_type` |
| Verdict and attack type agree, but the quoted evidence misses the trick text | `evidence_miss` |

Group the misses by `miss_kind`, gold `attack_type`, and gold `variant`. Write the next batch under `attacker/specs/roundN/` aimed at those groups. Spend the pages on the misses, and keep a similar share of hard clean pages so a model cannot pass by blocking everything. Use new shops, new prices, and new sentences. Do not quote the missed page, the test set, or `gym/build.py`.

Then:

```bash
python attacker/check_near_duplicates.py attacker/specs/roundN
python -m gym.render_specs --specs-dir attacker/specs/roundN --out data/attacker-roundN --source attacker-roundN
```

### Template prompt

Copy this, fill the bracketed parts, and give it to the attacker for that round.

```
You are the attacker for the checkout-guard gym. Write round [N] as JSON trick specs under attacker/specs/round[N]/. Validate them against gym/schema/trick_spec.json. Use split "train" and source "attacker-round[N]".

Training attacks only: hidden_fees (drip), preselected_addon (checkbox, modal, and one_click), price_change (drift), subscription_trap (autorenew), fake_card_verification (phishing), and hard clean pages (attack_type none, verdict pass). Never write copycat_domain or listing_injection.

A dev eval wrote [path to runs/eval/*_misses.json]. Read it. Aim this batch at the miss kinds in that file (false_pass, false_block, wrong_type, evidence_miss), grouped by gold attack_type and variant. Keep a large set of honest pages that look like tricks: disclosed fees, unchecked opt-in add-ons, real price drops, and card forms on the real host.

Write the copy yourself. Subtle store wording, varied placement, prices, and shops, decoys that look scary but are honest, and tricks split across blocks. The evidence_text must be the exact on-page quote for #trick.

Do not copy, paraphrase, or reuse text from gym/build.py, data/testset/, or any page id in gym/splits/test_page_ids.txt. Match on normalized text: lowercase, punctuation stripped, whitespace collapsed, at any length, including short lines.

Run python attacker/check_near_duplicates.py attacker/specs/round[N] and fix every hit. If main has moved, rebase onto main and rerun that check before rendering. Then render:

python -m gym.render_specs --specs-dir attacker/specs/round[N] --out data/attacker-round[N] --source attacker-round[N]

Fix any spec that fails validation. Do not merge.
```
