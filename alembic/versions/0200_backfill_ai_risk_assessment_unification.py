"""Backfill completed ai_risk_assessments rows into the authoritative
ai_system_risk_assessments table.

Two AI risk-assessment tables existed: `ai_risk_assessments` (the guided
bias/fairness/explainability/privacy/misuse/security questionnaire, 6
dimension-rating columns) and `ai_system_risk_assessments` (the richer
"AI Risk Assessment Engine" table — scoring profiles, dimension templates,
classification linkage, residual risk, snapshots — read by the AI
governance dashboard/diagnostics and most of the AI governance module).

Completing a questionnaire only wrote to `ai_risk_assessments`, so the
dashboard's "needs risk assessment" warning (which reads
`ai_system_risk_assessments`) never cleared. The application code has been
fixed to mirror new completions onto `ai_system_risk_assessments` going
forward; this migration backfills previously-completed questionnaire rows
so historical completions aren't silently lost.

Revision ID: 0200_backfill_ai_risk_assessment_unification
Revises: 0199_audit_engagement_source_schedule_link
Create Date: 2026-07-09 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0200_backfill_ai_risk_assessment_unification"
down_revision: str | None = "0199_audit_engagement_source_schedule_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO ai_system_risk_assessments (
            id,
            organization_id,
            ai_system_id,
            title,
            description,
            assessment_type,
            status,
            owner_user_id,
            risk_level,
            likelihood,
            impact,
            inherent_risk_score,
            residual_risk_score,
            risk_dimensions_json,
            methodology_version,
            calculated_risk_level,
            completed_at,
            created_by_user_id,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            ara.organization_id,
            ara.ai_system_id,
            'AI Risk Questionnaire v' || ara.assessment_version || ' (migrated)',
            'Backfilled from the legacy ai_risk_assessments table during table unification.',
            CASE WHEN ara.assessment_version = 1 THEN 'initial' ELSE 'periodic' END,
            'completed',
            NULL,
            COALESCE(
                CASE
                    WHEN ara.overall_risk_score IS NULL THEN NULL
                    WHEN ara.overall_risk_score <= 25 THEN 'low'
                    WHEN ara.overall_risk_score <= 50 THEN 'medium'
                    WHEN ara.overall_risk_score <= 75 THEN 'high'
                    ELSE 'critical'
                END,
                'unknown'
            ),
            COALESCE(
                CASE
                    WHEN ara.overall_risk_score IS NULL THEN NULL
                    WHEN ara.overall_risk_score <= 25 THEN 'low'
                    WHEN ara.overall_risk_score <= 50 THEN 'medium'
                    WHEN ara.overall_risk_score <= 75 THEN 'high'
                    ELSE 'critical'
                END,
                'unknown'
            ),
            COALESCE(
                CASE
                    WHEN ara.overall_risk_score IS NULL THEN NULL
                    WHEN ara.overall_risk_score <= 25 THEN 'low'
                    WHEN ara.overall_risk_score <= 50 THEN 'medium'
                    WHEN ara.overall_risk_score <= 75 THEN 'high'
                    ELSE 'critical'
                END,
                'unknown'
            ),
            ara.overall_risk_score::int,
            ara.overall_risk_score::int,
            json_build_object(
                'bias', ara.bias_risk_rating,
                'fairness', ara.fairness_risk_rating,
                'explainability', ara.explainability_risk_rating,
                'privacy', ara.privacy_risk_rating,
                'misuse', ara.misuse_risk_rating,
                'security', ara.security_risk_rating
            ),
            'ai_risk_questionnaire_v1',
            CASE
                WHEN ara.overall_risk_score IS NULL THEN NULL
                WHEN ara.overall_risk_score <= 25 THEN 'low'
                WHEN ara.overall_risk_score <= 50 THEN 'medium'
                WHEN ara.overall_risk_score <= 75 THEN 'high'
                ELSE 'critical'
            END,
            ara.completed_at,
            ara.completed_by,
            ara.created_at,
            ara.updated_at
        FROM ai_risk_assessments ara
        WHERE ara.status = 'completed'
          AND NOT EXISTS (
              SELECT 1
              FROM ai_system_risk_assessments asra
              WHERE asra.organization_id = ara.organization_id
                AND asra.ai_system_id = ara.ai_system_id
                AND asra.methodology_version = 'ai_risk_questionnaire_v1'
                AND asra.title LIKE 'AI Risk Questionnaire v' || ara.assessment_version || '%'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM ai_system_risk_assessments
        WHERE methodology_version = 'ai_risk_questionnaire_v1'
          AND title LIKE '%(migrated)'
        """
    )
