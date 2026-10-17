# Frozen page-id split

`train_page_ids.txt` and `test_page_ids.txt` are the only split. Do not reshuffle them.

- Seed: `20261017` (`gym.taxonomy.SPLIT_SEED`)
- Test fraction: `0.25`, round half up, and both piles stay non-empty when a stratum has at least two pages
- Unit: `page_id`. Every string from a page stays in one pile
- Strata: the page's dark pattern category, or `Not Dark Pattern` when the page has no dark row
- Within a stratum, ids are shuffled with an explicit Fisher-Yates driven by `random.Random(sha256(f"{seed}:{stratum}")[:8])`
- Files are numeric order, one id per line

`python -m gym.dataset --check` exits non-zero if the files disagree with that algorithm.

`copycat_domain` and `listing_injection` are not in this dataset. They are template-only and appear only in the frozen test set.
