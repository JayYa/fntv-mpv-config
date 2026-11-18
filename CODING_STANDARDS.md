# Coding standards

Apply every rule to the diff. CI already runs `ruff check .` and the tests, so these are the judgement calls only.

## Docs match the code

- When the diff changes behaviour, check every place that describes it for **drift**: README, GLOSSARY.md, `--help` text, docstrings, error messages. Any statement the new code contradicts is a violation. Universal claims ("every failure raises X", "only raises Y") drift first.
- Use the GLOSSARY.md term for each concept, never a word from its _Avoid_ list. A new domain concept gets a GLOSSARY.md entry in the same diff.
- README serves users: how to run it, config fields, the manifest format. Leave module and test inventories to the code itself.

## Layering

- `main.py` alone speaks in CLI flags. In `build()` and everything below it, errors, logs, and docstrings name the build scope or the option itself (`offline`, `keep_temp`), not `--skip-package`.
- The package config validates every field at load time. Code downstream trusts the loaded values and adds no second validation, so a bad config surfaces as `ConfigError`, never as a stray `ValueError`.
- A failure raises with its reason (`BuildFailed`, `ConfigError`, `FetchError`, …) and chains the original with `from`. Logging and returning `None`, or a catch-all `except Exception`, hides the reason from callers and tests.

## Tests

- Test through the module's interface (`load_package_config`, `load_layout`, `fetch`, `build()`, `main(argv)`), not through the staging layout or private attributes behind it.
- One rule per test, named for the rule.
- Assert a rule, not a copy of checked-in data. A test that restates a data file's values is a **change detector**: it catches no bug and fails only on legitimate edits.

  ```python
  # Bad: change detector
  def test_uosc_uses_latest_stable_release(self):
      config = json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))
      self.assertEqual(config["dependencies"]["uosc"]["version"], "5.13.0")
  ```

## Commits

- Refactors and fixes land in separate commits; structural cleanup done along the way goes in the refactor.
