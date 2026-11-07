# Agent entry point

This file tells an automated agent where to start in this repository. It does not define
product scope, an active ticket or a role assignment.

- Read [`README.md`](README.md) first: it documents installation, configuration, the endpoint,
  the test suites and the limitations.
- The architectural decisions are in [`docs/04_adr_001_arquitetura.md`](docs/04_adr_001_arquitetura.md)
  and [`docs/05_adr_003_provider_gemini.md`](docs/05_adr_003_provider_gemini.md).
- The problem analysis, from problem statement to root cause, is in `docs/01` to `docs/03`.
- Evidence of the runs that the README summarises is in the `docs/tech-*-evidence.md` files.

Rules that apply to any change:

1. One change, one branch, one pull request. Never commit directly to `main`.
2. Write the failing test first and show the failure before implementing.
3. Commands, terminal output and configuration names are reproduced exactly as they were run;
   only the prose around them is edited.
4. No credential, customer data or personal path is committed. `.env` stays untracked; the
   versioned example carries placeholders only.
5. `ruff check .` and `black --check .` must pass, and the default test suite must be green,
   before a pull request is opened.

See [`CLAUDE.md`](CLAUDE.md) for the code conventions and the commit rules.
