# Repository Guidelines

## Project Structure & Module Organization

This is a Python-first MTG deck research and testing toolkit. The executable modules are in `tools/`:

- `mtg_tool.py` provides Scryfall/MTGCH search, legality checks, validation, and baselines.
- `set_preview_tool.py` tracks new-set preview seasons: incremental Scryfall snapshots, per-batch diffs, and preview-period limited ratings.
- `forge_tool.py` converts decks, runs Forge simulations, and tracks upstream Card-Forge/forge updates (`track`, clone at `Ref/forge`). For sets newer than the release jar's card DB (e.g. FRA), pass the source-built snapshot jar plus the source `res/` as working directory: `--jar Ref/forge/forge-gui-desktop/target/forge-gui-desktop-2.0.15-SNAPSHOT-jar-with-dependencies.jar --cwd Ref/forge/forge-gui`.
- `deck_image.py` renders a decklist (MTGA import format) into an Untapped.gg-style card grid image (Scryfall art cached under `tools/cache/card_images/`; the `mana/` and `type/` icon sets under `tools/assets/icons/` are rendered from the open-source Mana font (SIL OFL 1.1) by `tools/render_open_icons.py`; MTGA wildcard icons for the cost row are NOT distributed — a local MTGA install plus the optional UnityPy dependency can extract them via `tools/extract_mtga_icons.py`, and hand-drawn rarity chips are the fallback when icons are absent; Pillow lazily imported). Delivery convention: run it after `deck_version.py` + validate so each versioned deck carries a same-name `{Name}V{n}.png` next to its `.txt`/`.md`; regenerate on version bumps without overwriting older versions' images.
- `mtga_log_tool.py` and `mtga_auto_tool.py` analyze MTGA logs and provide live advice; `mtga_log_tool.py` also provides `inventory` (StartHook wildcard/currency/pack snapshot plus the union of saved decks, written to `MatchRecord/inventory.json`); `mtga_draft_tool.py` is the draft cockpit (17Lands win-rate anchors, direct-first with shiqidi same-schema proxy fallback and 3-day disk cache; the locally pre-generated rating table feeds the LLM as fact anchor; LLM pick advice) and provides `regress` (rating-vs-17Lands regression) and `brief` (pre-draft format environment brief, also auto-printed when `draft --watch` starts).
- `mtga_db_tool.py` queries the MTGA client SQLite card database (grpId → English name/set/number/rarity) as a fallback when Scryfall has no arena_id.
- `deck_version.py` scaffolds versioned deck deliveries under `DeckList/{format}_{colors}_{theme}/` (paired `.txt`/`.md`, max+1 versioning, no overwrite) with basic gate checks; pass Chinese text via `--config params.json`.
- `deck_core.py` contains the shared deterministic kernel; `roles.py` contains pure role tagging; `limited_strategy.py` and `constructed_strategy.py` contain deck selection; `draft_advisor.py` contains draft scoring; `deck_pooper.py` is the thin CLI layer.
- `deck_model.py` is the unified decklist model and parsing layer (Phase 1 of the parsing-consolidation plan): `CardRef`/`SkippedLine`/`Deck` frozen dataclasses plus `parse_deck`/`parse_text`; every `parse_deck`/`load_deck` in `tools/` and `tools/newbie/` (mtg_tool, deck_image, deck_version, rot_audit, deck_cost, mtga_cost, mana_audit, mana_audit2) is a thin delegate to it. New decklist parsing needs must extend `deck_model` rather than fork another parser. `BASIC_LANDS` (12, incl. Snow-Covered Wastes) and `ANY_NUMBER` are single-sourced here and re-exported by mtg_tool (`BASIC_LAND_NAMES`) and deck_version.
- `deck_config.py` holds all strategy/threshold parameters (Phase 2): `deck_core` (WASPAS axes, curve, signals, skeleton targets, land_count/land_check thresholds), `mtga_log_tool` (risk flags, category actions) and `rot_audit` (rotation date/sets) load via `load_params()` at import, keeping their old constant names as aliases. Users may copy `tools/data/config/strategy_params.example.json` → `strategy_params.json` (gitignored) to override; missing/corrupt JSON falls back to built-in defaults with one stderr warning, and the loader never writes the JSON back.
- `draft_*.py` contains draft evaluation and legacy prototype workflows.
- `rot_audit.py` audits Standard rotation survival per deck or card (`deck`/`card`; verdict by `set_type ∈ {core, expansion}` + non-digital + release date, immune to promo reprints); `cn_audit.py` is the Chinese-card-name gate (`check` reverse-lookups every Chinese name in a delivery doc against mtgch, cache sidecar in `tools/cache/_cn_audit_cache.json`).
- `mcp_server.py` is the zero-dependency stdio MCP server for chat-style Agent clients (CherryStudio / WorkBuddy / DeepSeek Harness): minimal JSON-RPC (initialize / ping / tools/list / tools/call), 6 read-only tools (`mtg_search`, `mtg_check`, `mtg_baseline`, `deck_validate`, `deck_cost`, `rot_audit`) executed as CLI subprocesses; coding Agents with shell access should use the CLI + `skills/` directly instead. Tool metadata is externalized to `tools/mcp_tools.json` (interface contract, tracked; fail-fast validated at startup — duplicate names/missing keys/unknown builders/missing scripts are fatal), with argv builders kept in code (`_ARGV_BUILDERS`) and referenced by name from the JSON. `run_tool` exits write run-attestation lines via `runlog.log_run` to `tools/data/run_log.jsonl` (gitignored, failures silently skipped, rotated to `run_log.1.jsonl` past 5MB — one generation kept); the same attestation is wired into the CLI exits of `deck_version.py` / `deck_image.py` / `deck_pooper.py` / `set_preview_tool.py` (outermost wrapper `runlog.run_logged` for exception paths, in-exit lines for success/business failures). Client config snippets live in `tools/README.md`.
- `init_workspace.py` recreates the gitignored workspace skeleton after cloning (see "Fresh Clone Setup").
- `tools/newbie/` holds the Standard newbie-series toolset (32 stdlib scripts): `deck_cost.py` / `mtga_cost.py` / `pack_points.py` (MTGA cost accounting), `sim_*.py` (per-deck goldfish simulators — Phase 3: all but `sim_dual.py` converged into the `goldfish/` package: `goldfish/engine.py` skeleton + `goldfish/data/*.json` card pools + `goldfish/decks/*.py` turn logic + `goldfish/mechanics.py` mechanic-tag registry; the `sim_*.py` files are compatibility shims with unchanged CLI/module API, and new decks should be added as data JSON + decks module rather than a new sim file; `sim_dual.py` is deprecated/frozen — kept as historical reference only, no longer evolving), and `*_axis_scan.py` / `land_sweep.py` (axis/land-count sweeps); they read shared snapshots from `tools/data/` (gitignored, ~21MB) via `../data` relative paths. Cards outside the snapshot are supplemented by a Scryfall fallback in `deck_cost.scryfall_look()` (lowest rarity among Arena printings; `DECK_COST_NO_FALLBACK=1` disables). Cost metric definitions and the MTGA-scheme MRUC visual spec live in `MtgDeckCostMetric.md`; a cost block is a default delivery item in the deck workflow (stage 5).
- `tools/test_*.py` are regression tests; `tools/testdata/` contains JSON, log, and decklist fixtures (`tools/testdata/decklists/` holds the golden decklists pinned by `test_parse_charter.py` / `test_deck_model.py`).

Root workflow documents (`MtgDeckCacuWorkFlow.md`, `MtgSetReviewWorkFlow.md`, and related design/template files) define research and reporting conventions; `README.md` is the illustrated project overview (images under `docs/img/`). `DeckList/`, `MatchRecord/`, `SetReview/`, `SimResult/`, and `AuditReport/` hold local or generated artifacts and are ignored by Git — local research notes and scratch results also go to `AuditReport/` rather than the repo root. Runtime caches, Forge/JDK downloads, and automation sessions under `tools/` are also ignored.

## Build, Test, and Development Commands

There is no compile step or package manager; use Python 3.7+ with the standard library. Optional dependency: the portable JDK + Forge install under `tools/jdk` and `tools/forge` is only required for `forge_tool.py sim/play` (download instructions in `tools/README.md`); everything else runs without it:

```powershell
python -m unittest discover -s tools -p "test_*.py"
python tools/mtg_tool.py validate <deck.txt> --format pioneer --bo3
python tools/mtg_tool.py check "Card Name" --format pioneer --platform arena
python tools/forge_tool.py sim <deck-a.txt> <deck-b.txt> --games 20
python tools/mtga_log_tool.py scan
python tools/mtga_log_tool.py inventory
python tools/deck_version.py --config params.json
python tools/deck_pooper.py limited --pool pool.txt --set HOB --strategy mid --out deck.txt --report report.md
python tools/deck_pooper.py draft --watch --set HOB --llm --port 8643
python tools/deck_pooper.py constructed --format pioneer --seed seeds.txt --candidates result.json --bo3 --out deck.txt --report report.md
```

Run focused tests while iterating (for example, `python tools/test_limited_strategy.py` or `python tools/test_roles.py`). Network-backed commands should use the built-in cache and respect API throttling; use `--no-cache` only when deliberately refreshing data.

## Fresh Clone Setup

After cloning, run `python tools/init_workspace.py` to recreate the gitignored workspace skeleton (`tools/cache/`, `tools/data/`, `MatchRecord/`, `DeckList/`, `SetReview/`, `SimResult/`, `AuditReport/`) and to copy `tools/llm_config.example.json` → `tools/llm_config.json` (never overwrite an existing one; fill in `api_key` or prefer the `DEEPSEEK_API_KEY` env var). Pass `--with-data` to regenerate `tools/data/rarity_map.json` via `tools/newbie/fetch_rarity.py` (network, disk-cached). Optional capabilities that stay unavailable without local installs: Pillow (deck images), UnityPy (MTGA icon extraction), Forge/JDK (simulations), MTGA client (log tools).

## Agent Integration

`skills/` is the canonical, versioned source of Agent skills (`mtg-deckbuilding`, `mtg-set-review`, `mtg-limited-draft`); each SKILL.md assumes the repo root as working directory. Per-harness wiring: Kimi Code copies them into `.kimi-code/skills/` (gitignored, local only); Claude Code reads `CLAUDE.md` (a one-line pointer here); chat-style clients without shell/repo access (CherryStudio, WorkBuddy, DeepSeek Harness) connect via `tools/mcp_server.py` (config snippets in `tools/README.md`); other harnesses read this file directly. Skill content changes must land in `skills/` first, then be mirrored to any local copies.

## Coding Style & Naming Conventions

Use UTF-8 Python source, four-space indentation, and standard-library patterns already present in `tools/`. Name modules and functions in `snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`. Keep CLI behavior in `argparse` subcommands and preserve the existing explicit error/exit-code handling. No formatter or linter is configured, so keep changes small and style-consistent.

## Testing Guidelines

Tests use `unittest`; test files are named `test_*.py` and methods `test_*`. Add deterministic fixture coverage under `tools/testdata/` and mock HTTP, filesystem, and subprocess boundaries rather than contacting MTGA or external APIs in tests. Run the full discovery command before submitting behavior changes.

## Commit & Pull Request Guidelines

Use short, descriptive, imperative subjects (recent history commonly starts with equivalents of `fix`, `add`, or `introduce`; no strict Conventional Commits rule is enforced). Keep commits focused. PRs should explain the user-visible or data-format impact, list validation commands and results, link relevant issues or workflow sections, and include screenshots only for GUI/dashboard changes. Do not commit ignored outputs, downloaded dependencies, `tools/llm_config.json`, or API keys; use `DEEPSEEK_API_KEY` for local LLM access.
