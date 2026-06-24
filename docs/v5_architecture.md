# CompliVibe Backend v5.0 Architecture

## Three Pillar Overview

CompliVibe backend v5.0 introduces a three-pillar module boundary under `app/`:

1. `app/compliance`
2. `app/ai_governance`
3. `app/data_observability`

These directories are scaffolded as domain anchors only. Existing v4.0 code remains in place and unchanged.

## Boundary Intent

- `compliance`: Core compliance domain capabilities and workflows.
- `ai_governance`: AI governance policies, controls, and adjudication logic.
- `data_observability`: Monitoring, diagnostics, and data-quality/telemetry concerns.

## Migration Posture

- No code has been moved in this scaffolding step.
- No imports were changed.
- Future migrations should move functionality incrementally behind stable interfaces.
