# Coding standards

Apply every rule to the diff. CI already runs `ruff check .`, `python check_comments.py` and the tests, so these are the judgement calls only.

## No comments

- Project-owned Python and Lua carry no comments; `check_comments.py` enforces this. Name the thing instead of explaining it. A non-obvious decision goes into `docs/adr/`; a hack that needs a comment to excuse it gets an issue, not a comment.

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

- A rejection case breaks exactly one rule and asserts that rule's error message. A case that breaks a second rule as a side effect and checks only that some error came back is **masked**: delete the rule it names and the other rule's error keeps it green.

  ```python
  # Bad: masked. Line 1 is not the include (the rule under test), and line 2
  # is no longer profile=fntv-defaults, so either check alone rejects it.
  cases = {
      "首个有效行不是 include": (
          b'vo=gpu\ninclude="~~/fntv/defaults.conf"\nprofile=fntv-defaults\n', None),
  }
  for problem, (mpv_conf, defaults) in cases.items():
      with self.subTest(problem):
          self.assertTrue(contract_test(self.make_zip(portable_files=...), ...))
  ```

- A test's case reaches the rule its name states. A case that trips a neighbouring rule instead (often the other half of one condition) is **misnamed**: delete the rule the name states and the test stays green. Build the case so the named rule is the only one it breaks; a check with two halves gets one test per half.

  ```python
  # Bad: misnamed. "fonts" is no dependency's managed_dir, so the case trips
  # that half of the check and never reaches "the entry is in the zip".
  def test_every_managed_dir_holds_a_client_entry(self):
      def add_dir(m):
          m["managedDirs"].append("fonts")
      self.assertFailsWith(self.make_zip(edit_manifest=add_dir, ...), "fonts")
  ```

## Commits

- Refactors and fixes land in separate commits; structural cleanup done along the way goes in the refactor.
