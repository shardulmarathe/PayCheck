# Renderer

`gym.render` turns one trick spec into one HTML page. The function signatures below are stable. Attackers and the test-set builder use the same ones.

```python
render_html(spec: dict, *, check: bool = True) -> str
trick_mode(spec: dict) -> str
due_cents(spec: dict) -> int
page_url(spec: dict) -> str
structural_features(html: str) -> dict[str, bool]
```

`check=True` validates the spec before rendering. `trick_mode` is `none` on a clean page and otherwise one of `fee`, `checkbox`, `modal`, `one_click`, `price`, `subscription`, `domain`, `phishing`, `offscreen`, `banner`. `due_cents` is the amount the page presents as due. `page_url` is `http://{domain}/p/{slug}/{page_id}` on a product page and `http://{domain}/{kind}/{page_id}` otherwise. The public `page_id` is an opaque `p-` id. It does not name the attack.

`structural_features` reports whether the rendered HTML contains a checkbox, a popup (`role="dialog"` or `aria-modal="true"`), a fee line (`data-fee`), a strike-through (`class="was"`, `<s>`, or `<del>`), or a radio. The stylesheet mentions `line-through` on every page; that rule alone is not a strike-through.

## Controls on clean pages

A clean page has `trick.attack_type` `none`, an empty selector, and empty evidence. It still may show the same widgets a trick page shows. Those widgets are honest:

| Control | How to ask for it | What the shopper gets |
| --- | --- | --- |
| Disclosed fee | `page.fees`: `{name, amount_cents}` | A summary row with `data-fee`, included in the total. Use a name like Shipping or Sales tax. Put it on the product or cart page when it should be visible before checkout. |
| Checkbox | `page.offers.checkbox`, or `page.addon` with `checked: false` | A paid opt-in is left unticked. A free box (`price_cents: 0`) may already be ticked. Neither one changes `due_cents`. |
| Radios | `page.offers.radios` with exactly one `checked` option, or `page.subscription` with `checked: false` | Radio buttons. The selected option is the plain one (one-time purchase, or the included delivery). The other option is not selected and is not charged. |
| Honest popup | `page.offers.modal` | A dialog. `decline` is the primary button (use `No thanks`). Nothing is added to the cart. |
| Honest sale | `page.offers.was_cents` | A struck `was $X` next to the current price. `was_cents` is higher than `checkout_price_cents`. The charged price stays `checkout_price_cents`, which stays equal to `listed_price_cents`. |

`page.offers` is rejected on a trick page. A clean page is rejected when a paid checkbox or add-on is checked, when its subscription is pre-selected, when the struck price is not higher than the price charged, or when a popup has a `trick_item` cart line. A checkbox that costs nothing may be checked.

Fee rows use one shape on every page. The inner `[data-price]` element is only the amount, and `data-price-label` is the fee name, so the reader prints `$X.XX | Name`. On a drip fee the outer element's text is the evidence. The row carries `data-fee` either way. Trick evidence lives in `#offer-1`. A clean page puts that same id on its first fee row, or on the first price when it has no fee.

## Optional chrome

`page.presentation` changes headings, button labels, and layout without changing the trick. Omitted, the page uses the historical test-set wording and puts the summary on the right.

| Field | Default |
| --- | --- |
| `layout` | `summary-right` (`summary-left` or `stacked`) |
| `summary` | `Order summary` |
| `about` | `About this item` |
| `add_label` | `Add to cart` |
| `continue_label` | `Continue to payment` |
| `pay_label` | `Pay now` |
| `verify_label` | `Verify card` |
| `review_line` | `Review the total before you pay {brand}.` |

Training rounds set `presentation`. In-distribution test pages omit it, so their chrome stays on the historical wording. The 60 `heldout_template` pages set `page_template` to `reserved` and use `gym/templates/reserved.html.j2` plus the stores in `gym/heldout.py`. The train generator does not import that module.

## Training rounds

```bash
python -m gym.train --round 1 --n-train 1500 --n-dev 300
python -m gym.train --round 2 --n-train 1500 --n-dev 300 --attacker data/attacker-round2
```

`--seed` defaults to `SPLIT_SEED + round * 1000003`. Output defaults to `data/trainset/roundN`. Each round generates new store brands, domains, products, prices, fee names, add-on names, and subscription and verification wording. The round fails if any page overlaps the frozen test set: a normalized test-pile string at any length, a test-pile string of four or more words inside a longer string, a `(store, product)` pair, a price, a fee name, an add-on name, an evidence string, or a frozen test-set button label. Real brand names from the Yada strings are rejected too.

`--n-train` pages are the training labels. `--n-dev` pages are written to `data/trainset/roundN/dev/` and are not part of those labels. Dev is a set of whole `group_id` families from this round, so a seed family is not split across the two directories. It is not the frozen test set. `--n` still generates one pool and holds out `--dev-percent` (default 15) the same way. The manifest records the distinct-sentence ratio before and after product, store, and price masking. Rounds 2 and later also overlap-check `data/attacker-roundN` when that directory exists.
