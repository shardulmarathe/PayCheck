# ec-darkpattern text

`dataset.tsv` is the Apache-2.0 release from [yamanalab/ec-darkpattern](https://github.com/yamanalab/ec-darkpattern) (`dataset/dataset.tsv` on `master`), retrieved 2026-10-17.

- SHA-256: `bd7bc7d93f5bf08591b10886d7aa3a7ba8ac266f5ce8206c00cd4daf7868508a`
- 2,356 rows. Columns: `page_id`, `text`, `label`, `Pattern Category`.
- 1,178 dark-pattern strings and 1,178 non-dark strings (Yada et al.).

The positive strings were originally drawn from Mathur et al. This repo uses only the Apache-2.0 Yada release. It does not use the GPL-3.0 Princeton crawl.

The page-id split is frozen in `gym/splits/`. Training code must not read strings whose `page_id` is in `test_page_ids.txt`.
