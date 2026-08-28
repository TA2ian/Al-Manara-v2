# ADR-007: Python Runtime Baseline

## Status

Accepted.

## Decision

Al-Manara v2 uses **Python 3.13.x** as its runtime baseline.

Production, local development, and CI must use the same Python major/minor baseline. Patch versions may be pinned independently through the deployment/tooling policy.

## Rationale

Python 3.13 provides a modern, stable runtime baseline for the async Telegram/application architecture while avoiding unnecessary dependence on bleeding-edge interpreter features.

The choice is independent of the legacy Al-Manara runtime. Legacy implementation or dependency constraints must not force the v2 runtime backwards.

## Constraints

- Dependencies must be compatible with Python 3.13.
- CI must test against the pinned baseline.
- Production images must declare the same Python major/minor version.
- No production dependency may be introduced solely to preserve legacy runtime behavior.
- Runtime version changes require an explicit architecture decision and compatibility test before adoption.
