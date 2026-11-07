# AI Handover Intelligence (P1)

API that receives a conversation transcript (bot + customer) and returns a structured handover
package (`HandoverPackage`), using an LLM with structured output validated against a Pydantic
schema.

## Essential commands

- Run the API locally: `uvicorn app.main:app --reload`
- Tests: `pytest`
- Live tests only: `pytest -m live -v`
- Single test: `pytest tests/test_api.py::test_case_name -v`
- Lint: `ruff check .`
- Formatting: `black --check .`
- Typecheck (if configured): `mypy app/`

## Stack

Python, FastAPI, Pydantic, Google Gemini (`google-genai` SDK), pytest, Black, Ruff.

## Repository structure

```
app/            # production code (main.py, schema.py, llm_client.py, errors.py)
tests/          # tests + fixtures/transcripts.py (synthetic transcripts)
docs/           # problem analysis, architecture decisions and verification evidence
```

## Code conventions

- Black decides formatting — no style debate. Maximum line length 88 characters.
- Full type hints on every public function in `app/`.
- Naming: `snake_case` (files/functions), `PascalCase` (classes), `UPPER_SNAKE_CASE` (constants).
- Short docstrings: what it does, not how it does it. Referring to the origin of a product
  decision is acceptable (e.g. "Origin: Discovery requirement R3"), because it speaks about the
  requirement, not about internal process.
- Never hardcode API keys. `.env` stays untracked; `.env.example` is versioned with placeholders.
- Input limits live in one place (`app/schema.py`) and are asserted independently in the tests,
  so a change to a limit fails the contract instead of silently updating it.

## Git and commits

- Never commit directly to `main`. One branch per change.
- Conventional Commits: `<type>(<scope>): <imperative description>`.
  Types: `feat`, `fix`, `test`, `refactor`, `docs`, `chore`.
- A commit speaks about the code or the artefact, never about internal coordination.
- Good example: `feat(schema): add the confidence field to HandoverPackage`
- Bad examples: `wip`, `update`, `final changes`

## Verification — TDD in the agent loop

Before any implementation: write the failing test first, confirm the failure (`failing test`),
and only then implement the minimum needed for the test to pass. No task counts as complete on a
verbal claim — present the real output of the test command (exit code `0`) as evidence.

## Out of scope (do not change without explicit authorisation)

- The folder structure described above.
- Any real data, system or operational detail from any organisation.
