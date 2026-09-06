# Knowledge Catalog OKF specification fixtures

These fixture bundles are copied from the Google Cloud Platform Knowledge Catalog
repository to verify that the OKF parser accepts real example bundles without
requiring raw-span sidecars.

## Attribution and license

- **Source repository:** https://github.com/GoogleCloudPlatform/knowledge-catalog.git
- **Pinned source commit:** `d44368c15e38e7c92481c5992e4f9b5b421a801d`
- **Source paths:** `okf/bundles/crypto_bitcoin`, `okf/bundles/ga4`, and
  `okf/bundles/stackoverflow`
- **License:** Apache License, Version 2.0. A complete license copy is in
  [`LICENSE.md`](LICENSE.md), copied from `okf/LICENSE.md` at the pinned commit.

All Markdown trees from the three listed bundle paths are included. The optional
non-Markdown `viz.html` visualization files are intentionally omitted because the
parser fixture exercises Markdown bundle scanning only.
