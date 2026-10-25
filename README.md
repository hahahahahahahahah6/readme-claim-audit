# readme-claim-audit

Version 0.1.0. Deterministic, offline, stdlib-only Python 3.9+ README claim auditing.
Reads the root README and repository files; no network, subprocesses, git, keys,
or repository code execution. Changes nothing.

```sh
pip install readme-claim-audit
readme-claim-audit audit . --json
readme-claim-audit audit . --fail-on medium --ignore 'old-*' --ignore 'legacy/*'
python -m build
```

The repository argument defaults to the current directory. Exit codes: 0 PASS,
1 WARN, 2 FAIL or argument error. HIGH findings fail by default; MEDIUM findings
warn. With `--fail-on medium`, all findings fail. Read/UTF-8 errors are counted
and produce WARN unless findings already fail. Ignore globs match claim strings,
with each excluded finding counted once.

Checks install names against project metadata, documented flags against Python
sources, local Markdown links, backtick file references, the first badge/prose
version, Makefile targets, and Python module commands. Only fenced triple-backtick
and four-space code blocks supply command checks. Flags using `=value` are checked.
Generic flags skipped: --help, --version, --json, --verbose, --quiet, --dry-run,
--force, --output, --config. Toolchain modules build, pip, unittest and venv are skipped.

Uses README.md first, otherwise the first sorted case-insensitive root match.
Skips .git, node_modules, dist, build, __pycache__, .venv, venv and symlinked
source directories. Metadata uses a line scanner, not TOML evaluation; project
script names are collected. Versions inside recognized Markdown CHANGELOG
sections are excluded. Local link anchors are stripped; directories count.
Reports sort by file, line, kind and claim, deduplicate that tuple, display at most
500 findings and at most 20 dead-file-reference findings. Totals and verdict
include omitted findings. JSON and human output include severity/kind counts,
ignored and parse-error counts, and explicit truncation. Detail snippets are
limited to 120 characters; other source file contents are never printed.

Fixtures under examples/sample-repo/good and examples/sample-repo/broken give
PASS and FAIL respectively. They contain only synthetic data.

Development: `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
Build with setuptools build-meta using the standard build command above.

## Honest limitations
Pattern matching, not semantic judgement. A finding means "check this claim".
Flags defined via config files, entry-point wrappers, or non-argparse/click
parsers are not seen and will flag if documented — check, don't auto-fix.
Version comparison uses the first badge/prose version only; a README that
documents old versions in a changelog-style section may still flag if the
CHANGELOG heading is not recognised. Internal-link checking is filesystem
only: it cannot tell you a link is wrong for a hosted docs site. A README
with no checkable claims passes with a note, which is not a quality score.

## Differentiation
- instruction-drift: AGENTS.md/CLAUDE.md claims vs disk. This is README
  claims vs disk — the public face, not the instruction files.
- skill-drift: SKILL.md frontmatter + referenced files. This is README
  install/usage/version/link claims, not skill packages.
- readmeta: README links only, and it rewrites them at build time. This
  audits install names, flags, versions, make targets and module commands
  too, and never rewrites anything.
- readme-drift (PyPI 3.2.0, name taken): Makefile-target drift only. This
  covers the wider claim surface above and is a different package.
- dokken / LLM doc regenerators: they rewrite docs with a model. This is a
  deterministic offline audit that changes nothing.
- Heavy link checkers: they need network. This is filesystem-only.

