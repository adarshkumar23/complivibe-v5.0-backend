# Fix Report: Issue 4 — Threshold Breach Logic & Source Type Pattern

## Scope
- Fix inverted `comparison_direction='above'` breach detection in data-quality and AI-monitoring services.
- Update affected tests whose assertions encoded the bug as expected behavior.
- Audit the codebase for any additional inverted threshold checks.
- Widen the `Issue.source_type` allowed values to include `risk_assessment` and keep the schema/model/migration in sync.

---

## 1. Service logic fixes

### `app/data_observability/services/quality_service.py` (lines 63-66)
```python
# Before — inverted
if config.comparison_direction == 'above':
    return value <= config.threshold_value
return value >= config.threshold_value

# After — corrected
if config.comparison_direction == 'above':
    return value >= config.threshold_value
return value <= config.threshold_value
```

### `app/ai_governance/services/ai_monitoring_service.py` (lines 79-82)
Same exact before/after change as above.

### Correct semantics
| `comparison_direction` | True meaning | `within_threshold` condition |
|---|---|---|
| `above` | Metric must stay above the threshold | `value >= threshold` |
| `below` | Metric must stay below the threshold | `value <= threshold` |

Previously a reading below an `above` threshold was wrongly marked healthy, and a reading above it was wrongly marked a breach.

---

## 2. Test updates

The existing assertions were locked to the buggy behavior. They were updated to assert the correct semantics.

| Test file | Change | Reason |
|---|---|---|
| `tests/unit/test_lineage_quality_c75_c76.py` | Breach reading value `0.90` -> `1.10`; OK reading value `0.90` -> `0.99`; expected `last_value` updated to `0.99` | `'below'` breach = value above threshold; `'above'` OK = value above threshold |
| `tests/unit/test_ai_monitoring_a66.py` | Swapped `'above'` within/breach values (`120.0` <-> `250.0`); `'below'` breach value `0.8` -> `0.95`; updated `last_reading_value` to `120.0`; corrected comments | Same corrected semantics; the last submitted reading is now the 120.0 breach |
| `tests/unit/test_incidents_dashboard_c79_c80.py` | `q_breach` value `0.90` -> `1.10`; `q_pass` value `0.98` -> `0.90` | With `'below'`, `1.10` breaches and `0.90` is within threshold |
| `tests/integration/test_full_platform_smoke.py` | Monitoring inbound value `'0.7'` -> `'0.85'`; Quality breach value `'0.5'` -> `'1.1'` | Both use `'below'`; a breach now requires value above threshold |
| `tests/integration/test_full_platform_smoke.py` | Migration head assertion updated to `0198_add_risk_assessment_to_issue_source_type` | New 0198 migration is now head |

No assertions were weakened — only the expected values/directions were corrected to match reality.

---

## 3. Codebase sweep for additional instances

Search patterns used:
- `comparison_direction` across all `.py` files
- `return value [<>]= .*threshold_value`
- `check_threshold`
- `threshold_direction` / `breach_direction`

**Result:** Only the two service files above used the `comparison_direction` + inverted `value <= / >= threshold_value` pattern. No third instance exists.

**Noted but not changed:** `app/ai_governance/services/ai_depth_service.py` uses a `lower_is_better` boolean for threshold passing (`metric_value <= threshold` if lower is better, else `>= threshold`). It is logically correct and unrelated to this bug class.

---

## 4. Issue source type widening

### Changes
- `app/schemas/issue.py`: Added `'risk_assessment'` to `ISSUE_SOURCE_TYPES`; `ISSUE_SOURCE_TYPE_PATTERN` is now derived from that tuple.
- `app/models/issue.py`: Updated `ck_issues_source_type` CHECK constraint to include `'risk_assessment'`.
- New migration: `alembic/versions/0198_add_risk_assessment_to_issue_source_type.py`
  - Drops the old `ck_issues_source_type` constraint.
  - Recreates it with `risk_assessment` in the allowed list.
  - `down_revision` points to `0197_add_timestamp_defaults_to_framework_review_tables`.

### Deployment verification
The migration was applied successfully to the disposable `complivibe_e2e` database:

```text
Running upgrade 0197_add_timestamp_defaults_to_framework_review_tables -> 0198_add_risk_assessment_to_issue_source_type, add risk_assessment to issue source_type
```

The production `complivibe` database was not touched.

---

## 5. Test results

| Suite | Result |
|---|---|
| Targeted threshold/quality/AI-monitoring/incident tests | Passed |
| Issue source-type regression tests | Passed |
| Full test suite (`pytest tests/ -q --disable-warnings`) | Passed — 0 failures, 1 skip |
| Alembic head | `0198_add_risk_assessment_to_issue_source_type` |

---

## 6. Addendum — `data_incident` source type status

**Confirmed:** `'data_incident'` was already present before the `risk_assessment` widening. No additional code changes were required.

It is present in all three layers:

- `app/schemas/issue.py` — `ISSUE_SOURCE_TYPES` tuple:
  ```python
  ISSUE_SOURCE_TYPES = (
      'manual',
      'monitoring_alert',
      'audit_finding',
      'vendor_assessment',
      'external_report',
      'data_incident',
      'risk_assessment',
  )
  ```

- `app/models/issue.py` — `ck_issues_source_type`:
  ```python
  'source_type IN (\'manual\', \'monitoring_alert\', \'audit_finding\', \'vendor_assessment\', \'external_report\', \'data_incident\', \'risk_assessment\')'
  ```

- `alembic/versions/0198_add_risk_assessment_to_issue_source_type.py` — `_SOURCE_TYPES`:
  ```python
  _SOURCE_TYPES = (
      '\'manual\'',
      '\'monitoring_alert\'',
      '\'audit_finding\'',
      '\'vendor_assessment\'',
      '\'external_report\'',
      '\'data_incident\'',
      '\'risk_assessment\'',
  )
  ```

The regression guard `tests/unit/test_issues_source_type_regression.py::test_list_issues_with_data_incident_does_not_500` already end-to-end verifies that a `data_incident`-sourced issue does not 500 the `GET /compliance/issues` list endpoint. That test passed as part of the full suite.

---

## Files modified

### Application code
- `app/data_observability/services/quality_service.py`
- `app/ai_governance/services/ai_monitoring_service.py`
- `app/schemas/issue.py`
- `app/models/issue.py`

### Migrations
- `alembic/versions/0198_add_risk_assessment_to_issue_source_type.py`

### Tests
- `tests/unit/test_lineage_quality_c75_c76.py`
- `tests/unit/test_ai_monitoring_a66.py`
- `tests/unit/test_incidents_dashboard_c79_c80.py`
- `tests/integration/test_full_platform_smoke.py`

### Documentation
- `docs/fix_report_issue_4_threshold_and_source_type.md`
