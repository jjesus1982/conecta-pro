"""fase5.4 Onda C (🔴) — esocial_transmissao_propostas (proposta de transmissão eSocial)

eSocial = ATO LEGAL perante o governo. O agente só PROPÕE uma transmissão
(status='proposto'); a assinatura + envio real do evento S-22x0 ao gov é 100%
humana, no fluxo existente (people_management.hr.services.esocial_service.
transmitir_evento_sst, disparado pelas tasks sst.transmit_*_to_esocial). O
agente NUNCA transmite. Grão = 1 evento a transmitir.

Revision ID: fase54_esocial_prop
Revises: fase54_op_subst

NOTA DE DIVERGÊNCIA brief×real: o brief (task-8-brief.md) mandava "não confie no
nome do brief" para a head. Head real confirmada em disco: "fase54_op_subst"
(fase54_op_substituicao_propostas.py) — nenhuma migration aponta
down_revision="fase54_op_subst". Encadeado nela p/ não abrir 2º head na 5.4.

NOTA proposto_em: coluna timestamptz com DEFAULT now() (instante absoluto,
tz-aware, honesto). A regra "TZ Manaus no SQL" vale p/ DATAS DE NEGÓCIO
(competência/data de evento) — aqui não se computa data de negócio; proposto_em
é carimbo de auditoria de sistema, então now() é o correto (não AT TIME ZONE,
que descartaria o fuso e falsearia o instante).

Idempotência NATIVA (anti-dupla-proposta): índice único PARCIAL em
(tipo_evento, referencia) WHERE status='proposto' — nunca 2 propostas vivas p/
o mesmo evento. Migration aditiva/idempotente (IF NOT EXISTS) e reversível.
"""
from alembic import op

revision = "fase54_esocial_prop"
down_revision = "fase54_op_subst"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS esocial_transmissao_propostas (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tipo_evento   text NOT NULL,
            employee_id   uuid,
            referencia    text NOT NULL,
            empresa_id    uuid,
            status        text NOT NULL DEFAULT 'proposto',
            payload       jsonb,
            proposto_por  uuid,
            proposto_em   timestamptz NOT NULL DEFAULT now(),
            aprovado_por  uuid,
            aprovado_em   timestamptz,
            correlation_id text
        )
        """
    )
    # Idempotência NATIVA: no máximo 1 proposta 'proposto' por (tipo_evento, referencia).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_esocial_prop_idem
        ON esocial_transmissao_propostas (tipo_evento, referencia)
        WHERE status = 'proposto'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_esocial_prop_status
        ON esocial_transmissao_propostas (status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_esocial_prop_status")
    op.execute("DROP INDEX IF EXISTS uq_esocial_prop_idem")
    op.execute("DROP TABLE IF EXISTS esocial_transmissao_propostas")
