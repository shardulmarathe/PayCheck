# Renderer

`gym.render` turns one trick spec into one HTML page. The function signatures below are stable. Attackers and the test-set builder use the same ones.

```python
render_html(spec: dict, *, check: bool = True) -> str
trick_mode(spec: dict) -> str
due_cents(spec: dict) -> int
page_url(spec: dict) -> str
structural_features(html: str) -> dict[str, bool]
```

`check=True` validates the spec before rendering. `trick_mode` is `none` on a clean page and otherwise one of `fee`, `checkbox`, `modal`, `one_click`, `price`, `subscription`, `domain`, `phishing`, `offscreen`, `banner`. `due_cents` is the amount the page presents as due. `page_url` is `http://{domain}/{kind}/{page_id}`.

`structural_features` reports whether the rendered HTML contains a checkbox, a popup (`role="dialog"` or `aria-modal="true"`), a fee line (`data-fee`), a strike-through (`class="was"`, `<s>`, or `<del>`), or a radio. The stylesheet mentions `line-through` on every page; that rule alone is not a strike-through.

## Controls on clean pages

A clean page has `trick.attack_type` `none`, an empty selector, and empty evidence. It still may show the same widgets a trick page shows. Those widgets are honest:

| Control | How to ask for it | What the shopper gets |
| --- | --- | --- |
| Disclosed fee | `page.fees`: `{name, amount_cents}` | A summary row with `data-fee`, included in the total. Use a name like Shipping or Sales tax. Put it on the product or cart page when it should be visible before checkout. |
| Unticked checkbox | `page.offers.checkbox` with `checked: false`, or `page.addon` with `checked: false` | An opt-in checkbox. It is not checked and it is not in the cart, so `due_cents` ignores it. |
| Radios | `page.offers.radios` with exactly one `checked` option, or `page.subscription` with `checked: false` | Radio buttons. The selected option is the plain one (one-time purchase, or the included delivery). The other option is not selected and is not charged. |
| Honest popup | `page.offers.modal` | A dialog. `decline` is the primary button (use `No thanks`). Nothing is added to the cart. |
| Honest sale | `page.offers.was_cents` | A struck `was $X` next to the current price. `was_cents` is higher than `checkout_price_cents`. The charged price stays `checkout_price_cents`, which stays equal to `listed_price_cents`. |

`page.offers` is rejected on a trick page. A clean page is rejected when its checkbox or add-on is checked, when its subscription is pre-selected, when the struck price is not higher than the price charged, or when a popup has a `trick_item` cart line.

Fee rows render for every attack, including `none`. On a trick they are the hidden fee. On a clean page they are the disclosed fee. The row carries `data-fee` either way.

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

Training rounds set `presentation`. The frozen test set does not, so its chrome stays put.

## Training rounds

```bash
python -m gym.train --round 1 --n 50
python -m gym.train --round 2 --n 50 --attacker data/attacker-round2
```

`--seed` defaults to `SPLIT_SEED + round * 1000003`. Output defaults to `data/trainset/roundN`. Each round generates new store brands, domains, products, prices, fee names, add-on names, and subscription and verification wording. The round fails if any page overlaps the frozen test set: a normalized test-pile string at any length, a test-pile string of four or more words inside a longer string, a `(store, product)` pair, a price, a fee name, an add-on name, or an evidence string. Real brand names from the Yada strings are rejected too.

About 15% of the generated pages are written to `data/trainset/roundN/dev/` and are not part of the training labels. That holdout is from the round. It is not the frozen test set. Rounds 2 and later also overlap-check `data/attacker-roundN` when that directory exists.
