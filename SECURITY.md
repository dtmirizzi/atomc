# Security Policy

`atomc` is pre-alpha software. We still take security seriously.

## Supported versions

Only the latest `0.x` release line receives security fixes. Once `1.0.0` ships,
the two most recent minor releases will be supported.

| Version | Supported |
| ------- | --------- |
| 0.x.y (latest) | ✅ |
| older | ❌ |

## Reporting a vulnerability

**Please do not report security issues in public GitHub issues.**

Use GitHub's private vulnerability reporting:
[Security → Report a vulnerability](https://github.com/dtmirizzi/atomc/security/advisories/new)
(GitHub → *Security* tab → *Advisories* → *Report a vulnerability*).

If you cannot use GitHub, email the maintainer listed in `package.json` /
`PLAN.md` with the subject line `atomc security`.

Please include:

- a description of the issue and its impact,
- reproduction steps or a minimal proof of concept,
- affected version(s)/commit,
- any suggested remediation.

We aim to acknowledge reports within 72 hours and to provide a remediation
timeline within 7 days. We will credit reporters in the advisory unless asked
otherwise.

## Scope notes

- The daemon binds to `127.0.0.1` by default; exposing `atomcd` on a public
  interface is unsupported without an authenticated reverse proxy.
- Vendored/recorded vendor API cassettes may contain fixture data but never real
  credentials; if you find a leaked secret in the repo, treat it as a
  vulnerability and report it privately.
- Supply-chain: releases are published to npm with provenance and to PyPI via
  Trusted Publishing (OIDC). Report anything that looks like a tampered artifact.
