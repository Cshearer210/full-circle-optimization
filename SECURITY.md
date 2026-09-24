# Security Policy

## Supported versions

This project is pre-1.0 and released from `main`. Security fixes land on `main` and in the next
tagged release. Older tags are not separately patched.

| Version | Supported |
|---------|-----------|
| `main` / latest `0.x` | ✅ |
| older tags | ❌ |

## Threat model, briefly

`full-circle-optimization` is a static analysis tool, and its design keeps the attack surface small:

- **Zero runtime dependencies.** It is pure Python standard library, so there is no third-party
  supply chain in the runtime.
- **No network calls.** It never phones home, downloads, or uploads anything.
- **It does not execute the target's code.** Detection is AST- and filesystem-based. The one
  component that runs code is the mutation-testing module (`mutation.py`), which runs a *target's own
  test command* against mutated copies **inside an isolated temporary directory**, never the
  original.
- **The fixer never edits in place unverified.** Every fix is tried on a throwaway clone, verified
  in both directions, and rolled back if anything changes; only then is it merged back.

The most relevant risks are therefore the ordinary ones for a tool you point at code: running it over
**untrusted repositories** (a malicious `conftest.py` or test command could execute if you invoke the
mutation module against it) and passing untrusted paths on the command line.

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** — do not open a public issue for a security
problem.

- Preferred: open a private report via **GitHub Security Advisories** on this repository
  ("Security" tab → "Report a vulnerability").
- Alternatively, contact the maintainer through their GitHub profile: **@Cshearer210**.

Please include a minimal reproduction and the impact you observed. You can expect an acknowledgement
within a few days. Once a fix is available it will be released on `main` and credited (unless you
prefer to remain anonymous).
