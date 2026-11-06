# Dependency and test execution evidence

**Date:** 6 November 2026.
**Environment:** Windows, PowerShell 5.1, Python 3.14.7, `.venv` at the project root.
**Keys:** empty (`$env:GEMINI_API_KEY=""; $env:GOOGLE_API_KEY=""`) in every run of the
default suite. No provider call.

---

## 1. Before: Git treated `requirements.txt` as binary

```
$ git ls-files --eol requirements.txt
i/-text w/-text attr/          requirements.txt
```

`-text` is Git saying "this is not text". The cause is in the first bytes:

```
$ [System.IO.File]::ReadAllBytes("requirements.txt")[0..7] -join ','
255,254,97,0,110,0,110,0
```

`FF FE` is a UTF-16 LE BOM, and `97,0,110,0` is `a\0n\0`: the whole file carries a null
byte every other byte. It was produced by `pip freeze > requirements.txt` in PowerShell,
which writes UTF-16 by default. The effect on the diff:

```
$ git diff --stat -- requirements.txt
 requirements.txt | Bin 1420 -> 1450 bytes
 1 file changed, 0 insertions(+), 0 deletions(-)

$ git diff -- requirements.txt
Binary files a/requirements.txt and b/requirements.txt differ
```

The `git diff` above was provoked with one extra line and reverted right after
(`git checkout -- requirements.txt`). Not a single line was readable, and `--stat` reports
`0 insertions(+), 0 deletions(-)` for a file whose size changed.

**Original content:** 38 lines, of which six were direct runtime dependencies
(`fastapi`, `google-genai`, `httpx`, `pydantic`, `python-dotenv`, `uvicorn`) and three were
development tools (`black`, `ruff`, and `pytest` **was not in the freeze** even though it
was installed in the `.venv`).

## 2. Decision: pinned direct dependencies, not the full `pip freeze`

`requirements.txt` lists the six direct ones with pinned versions; `pip` resolves the
transitive ones at install time. The full `pip freeze` would also be reproducible today,
but it states no intent: 32 of the 38 lines were transitive (`certifi`, `anyio`,
`typing_extensions`, ...) and two were dev tools that should never have been there. A
snapshot of one installation is not a contract, and a lockfile is what would fix that — it
is out of scope for this ticket, as the DoR defined.

**The price of the decision, measured:** a fresh install drifts on the transitive ones.
Against the previous `.venv`, today's install brought `starlette 1.10.0` (was `1.6.0`),
`anyio 4.16.0` (was `4.15.1`) and `pydantic_core`/`typing-inspection` one revision ahead.
The suite passed the same, because it runs in 0.26 s and is deterministic — the drift is
detected, not ignored. If it ever stops being detected, the lockfile stops being optional.

## 3. After: readable text

```
$ git ls-files --eol requirements.txt requirements-dev.txt
i/lf    w/lf    attr/                 	requirements-dev.txt
i/lf    w/lf    attr/                 	requirements.txt
```

The final `requirements.txt`:

```
# Runtime dependencies. Development tools live in requirements-dev.txt.
#
# Direct dependencies only, pinned: the install resolves the transitive ones.
# A lockfile with hashes is the missing piece for byte-identical installs.
fastapi==0.141.1
google-genai==2.24.0
httpx==0.28.1
pydantic==2.13.5
python-dotenv==1.2.3
uvicorn==0.53.0
```

`requirements-dev.txt`:

```
# Development tools. Installs the runtime requirements first.
-r requirements.txt

black==26.5.1
pytest==9.2.0
ruff==0.16.8
```

**Honest caveat:** the `chore(deps)` commit still shows `Bin 1420 -> 333 bytes`, because the
*old* side of the comparison is the UTF-16 blob. From the next commit on, the same file
shows up as text.

## 4. `pythonpath` RED/GREEN

The empty root `conftest.py` existed only for the pytest console script. Proof, with it
removed and no configuration:

```
$ .\.venv\Scripts\pytest.exe -q
ImportError while loading conftest '...\tests\conftest.py'.
tests\conftest.py:11: in <module>
    from app import llm_client
E   ModuleNotFoundError: No module named 'app'
exit=4
```

With `pythonpath = ["."]` under `[tool.pytest.ini_options]`, the same command:

```
$ .\.venv\Scripts\pytest.exe -q
32 passed, 7 deselected, 3 warnings in 0.23s
exit=0
```

`python -m pytest` never failed in that scenario, because `-m` puts the current directory
on `sys.path`; that is why the defect never showed up for anyone running through `-m`.
`tests/conftest.py` (the `live` skip hook) was not touched.

## 5. Fresh `.venv`, installed only from `requirements-dev.txt`

```
$ python -m venv <redacted>/venv-check
$ .\venv-check\Scripts\python.exe -m pip install -q -r requirements-dev.txt
pip exit=0

$ .\venv-check\Scripts\pytest.exe -q
32 passed, 7 deselected, 2 warnings in 0.26s      exit=0

$ .\venv-check\Scripts\ruff.exe check .
All checks passed!                                 exit=0

$ .\venv-check\Scripts\black.exe --check .
12 files would be left unchanged                   exit=0
```

All three through the executables, not through `python -m`. The verification `.venv` was
created outside the project root and removed afterwards; the reference installation remains
the project's `.venv`.

## 6. The old `venv\` removed

```
$ Remove-Item -Recurse -Force venv
$ Test-Path venv
False

$ Get-Command pytest -All | Select-Object Source
<repo>\.venv\Scripts\pytest.exe

$ Test-Path .venv
True
```

The old `venv\` had 5,383 files and 108 MB, created with `--without-pip` against the Python
in `C:`, and its executables pointed at an interpreter that no longer exists. Recreating it
is `python -m venv venv`, and nothing of value lived there.

## 7. Test count: before and after

| Moment | Command | Result |
|---|---|---|
| `main`, before the changes | `python -m pytest -q` | `32 passed, 7 deselected, 3 warnings in 0.28s` |
| after, `pytest.exe` with `pythonpath` | `pytest.exe -q` | `32 passed, 7 deselected, 3 warnings in 0.23s` |
| fresh `.venv` from `requirements-dev.txt` | `pytest.exe -q` | `32 passed, 7 deselected, 2 warnings in 0.26s` |

Same count in all three, exit 0. The `7 deselected` are the `live` tests, excluded by
`addopts = "-m 'not live'"` since the live-split work.

## 8. What this ticket does not prove

- **Nothing about the model.** The `gemini-3.8-flash` default is still in the code and is
  still wrong; that is the default-model work.
- **Nothing about line endings in history.** There is no `.gitattributes` yet, and this
  machine's `core.autocrlf=true` turns LF into CRLF at checkout: the new file enters the
  index as LF and only shows `w/lf` because it has not been through a new checkout. That is
  the repository hygiene work.
- **Nothing about the README.** It still describes the previous environment: the README update.
