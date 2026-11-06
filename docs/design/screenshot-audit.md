# Screenshot privacy audit

Scope: 198 images at HEAD (docs/design/logo, screenshots, screenshots-review) plus 72 further image blobs reachable only in history (old versions, deleted files), 270 total.

Method: macOS Vision OCR of every image, grep for `/Users/`, `/home/`, emails, `sk-ant`, `ghp_`, owner name/handles, shell prompts, URLs; every hyphenated Item-name token cross-checked against all text ever committed (demo*.json, fixtures, scripts). Unknown tokens were OCR noise of invented names (for example `scour-beacon-two`, `trace-anvil-pi`). Representative images in each family were also viewed by eye (1-rest, hook-1440, pp-d-04-by-project-desk, chat-answers/1440-compare, history 14-lens-this-repo, sky/r6-candidate-a-photograph).

Result: **no SUSPECT images**. No owner paths, usernames, emails, keys, terminal prompts or real project names found.

Notes:
- `~/.claude/...` paths shown are demo paths (`~` form, no username).
- Project names shown (`alpha-shop`, `thesis`) and pack `demo/field-tools`, `example-org/skill-pack` are present in demo JSON.
- Backgrounds (`sky/r6-candidate-*`, `bg/*`) are generated starfields, no text.
- Text files: no committed constellation-real*, .env or cache dumps. Every `/Users/` string in HEAD is a test fixture with invented names (someone, demo-person, invented-person, PLANTED_USERNAME, me). `eshansharif` appears only in docs/design/install-and-cli.md, inside a grep command used for this kind of check (and pyproject, public repo owner).

| Image family | Verdict | What was seen |
|---|---|---|
| `docs/design/logo/*` (3 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots-review/*` (8 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/1-rest*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/10-empty*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/11-offline*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/12-offline*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/13-offline*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/14*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/15*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/16*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/17*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/2-hover*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/23-after*` (22 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/23-before*` (22 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/3-selected*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/4-search*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/5-zoomed*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/6-drag*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/62-focus*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/62-hover*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/62-no*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/62-one*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/62-phone*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/62-popover*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/62-rest*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/7-phone*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/70-mid*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/70-newest*` (2 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/70-oldest*` (2 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/8-phone*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/9-phone*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/ask-placement*` (5 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/badge/*` (3 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/bg/*` (8 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/chat-answers/*` (14 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/demo250*` (1 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/inspector-b/*` (10 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/inspector-c*` (2 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/inspector/*` (9 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/lens*` (5 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/motion/*` (14 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/packs*` (4 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/pp-d*` (5 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/preview*` (5 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/sky/*` (21 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/weekly*` (2 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| `docs/design/screenshots/whatif/*` (6 files) | OK | App UI on invented demo data (demo*.json names, alpha-shop/thesis demo projects, ~/.claude/... demo paths only). |
| 72 history-only image blobs (old versions of the above, plus screenshots-review/01-23 deleted files) | OK | Same demo data (97-item demo with `shop-catalog-db`, `cart-checkout-audit`, `quarterly-ledger-reconciliation-helper`). |
