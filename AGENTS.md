# Repository Guidelines

## Project Structure & Module Organization

This is a Python-first MTG deck research and testing toolkit. The executable modules are in `tools/`:

- `mtg_tool.py` provides Scryfall/MTGCH search, legality checks, validation, and baselines.
- `forge_tool.py` converts decks and runs Forge simulations.
- `mtga_log_tool.py` and `mtga_auto_tool.py` analyze MTGA logs and provide live advice.
- `deck_core.py` contains the shared deterministic kernel; `roles.py` contains pure role tagging; `limited_strategy.py` and `constructed_strategy.py` contain deck selection; `draft_advisor.py` contains draft scoring; `deck_pooper.py` is the thin CLI layer.
- `draft_*.py` contains draft evaluation and legacy prototype workflows.
- `tools/test_*.py` are regression tests; `tools/testdata/` contains JSON and log fixtures.

Root workflow documents (`MtgDeckCacuWorkFlow.md`, `MtgSetReviewWorkFlow.md`, and related design/template files) define research and reporting conventions. `DeckList/`, `MatchRecord/`, `SetReview/`, `SimResult/`, and `AuditReport/` hold local or generated artifacts and are ignored by Git. Runtime caches, Forge/JDK downloads, and automation sessions under `tools/` are also ignored.

## Build, Test, and Development Commands

There is no compile step or package manager; use Python 3.7+ with the standard library:

```powershell
python -m unittest discover -s tools -p "test_*.py"
python tools/mtg_tool.py validate <deck.txt> --format pioneer --bo3
python tools/mtg_tool.py check "Card Name" --format pioneer --platform arena
python tools/forge_tool.py sim <deck-a.txt> <deck-b.txt> --games 20
python tools/mtga_log_tool.py scan
python tools/deck_pooper.py limited --pool pool.txt --set HOB --strategy mid --out deck.txt --report report.md
python tools/deck_pooper.py draft --watch --set HOB --llm --port 8643
python tools/deck_pooper.py constructed --format pioneer --seed seeds.txt --candidates result.json --bo3 --out deck.txt --report report.md
```

Run focused tests while iterating (for example, `python tools/test_limited_strategy.py` or `python tools/test_roles.py`). Network-backed commands should use the built-in cache and respect API throttling; use `--no-cache` only when deliberately refreshing data.

## Coding Style & Naming Conventions

Use UTF-8 Python source, four-space indentation, and standard-library patterns already present in `tools/`. Name modules and functions in `snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`. Keep CLI behavior in `argparse` subcommands and preserve the existing explicit error/exit-code handling. No formatter or linter is configured, so keep changes small and style-consistent.

## Testing Guidelines

Tests use `unittest`; test files are named `test_*.py` and methods `test_*`. Add deterministic fixture coverage under `tools/testdata/` and mock HTTP, filesystem, and subprocess boundaries rather than contacting MTGA or external APIs in tests. Run the full discovery command before submitting behavior changes.

## Commit & Pull Request Guidelines

Use short, descriptive, imperative subjects (recent history commonly starts with equivalents of `fix`, `add`, or `introduce`; no strict Conventional Commits rule is enforced). Keep commits focused. PRs should explain the user-visible or data-format impact, list validation commands and results, link relevant issues or workflow sections, and include screenshots only for GUI/dashboard changes. Do not commit ignored outputs, downloaded dependencies, `tools/llm_config.json`, or API keys; use `DEEPSEEK_API_KEY` for local LLM access.
