"""sprint81: cria tabela marketing_brand_voice + seed inicial

Revision ID: sprint81_marketing_brand_voice
Revises: sprint80b_fin_cols_sync
Create Date: 2026-05-13

Cria a tabela marketing_brand_voice (1 brand voice por condominio) e
faz seed com o conteudo atual hardcoded na pagina
/modulos/marketing/brand-voice/page.tsx (frontend), apontado pro
condominio-teste a1b2c3d4-e5f6-7890-abcd-ef1234567890.
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "sprint81_marketing_brand_voice"
down_revision = "sprint80b_fin_cols_sync"
branch_labels = None
depends_on = None


# Condominio-teste mencionado no CLAUDE.md (Jordan)
CONDOMINIO_TESTE_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# Conteudo atual hardcoded em frontend/src/app/modulos/marketing/brand-voice/page.tsx
SEED_PERSONALITY = [
    {"label": "Profissional", "description": "Transmitimos expertise em seguranca patrimonial"},
    {"label": "Confiavel", "description": "Dados e resultados comprovados, nao promessas"},
    {"label": "Tecnologico", "description": "Inovacao com portaria remota e monitoramento inteligente"},
    {"label": "Proximo", "description": "Atendimento humanizado, acessivel e transparente"},
]

SEED_TONE_OF_VOICE = [
    {"title": "Formal mas acessivel", "description": "sem jargoes excessivos"},
    {"title": "Direto e objetivo", "description": "o sindico nao tem tempo"},
    {"title": "Orientado a solucao", "description": "'como resolver' nao 'o que vender'"},
    {"title": "Empatico", "description": "entendemos as dores do gestor condominial"},
]

SEED_KEYWORDS = [
    "seguranca",
    "tranquilidade",
    "tecnologia",
    "economia",
    "eficiencia",
    "monitoramento 24h",
    "portaria inteligente",
    "patrimonio protegido",
    "gestao profissional",
    "Manaus",
]

SEED_AVOID_LIST = [
    "Linguagem agressiva ou alarmista",
    "Promessas de 'seguranca 100%'",
    "Comparacao direta com concorrentes",
    "Termos tecnicos sem explicacao",
    "Informalidade excessiva (girias, emojis demais)",
]

SEED_SLOGAN = (
    "Conecta Mais — Seguranca inteligente para quem valoriza o patrimonio"
)


def upgrade() -> None:
    # === Cria a tabela ===
    op.create_table(
        "marketing_brand_voice",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "condominio_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "personality",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "tone_of_voice",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "avoid_list",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("slogan", sa.Text(), nullable=True),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    # Constraints + indexes
    op.create_unique_constraint(
        "uq_marketing_brand_voice_condominio",
        "marketing_brand_voice",
        ["condominio_id"],
    )
    op.create_index(
        "ix_marketing_brand_voice_condominio_id",
        "marketing_brand_voice",
        ["condominio_id"],
    )

    # === Seed inicial pro condominio-teste ===
    op.execute(
        sa.text(
            """
            INSERT INTO marketing_brand_voice
                (id, condominio_id, personality, tone_of_voice, keywords,
                 avoid_list, slogan, is_active)
            VALUES
                (
                    :id,
                    :condominio_id,
                    CAST(:personality AS jsonb),
                    CAST(:tone_of_voice AS jsonb),
                    CAST(:keywords AS text[]),
                    CAST(:avoid_list AS jsonb),
                    :slogan,
                    TRUE
                )
            ON CONFLICT (condominio_id) DO NOTHING
            """
        ).bindparams(
            id=str(uuid.uuid4()),
            condominio_id=CONDOMINIO_TESTE_ID,
            personality=json.dumps(SEED_PERSONALITY),
            tone_of_voice=json.dumps(SEED_TONE_OF_VOICE),
            keywords="{" + ",".join(SEED_KEYWORDS) + "}",
            avoid_list=json.dumps(SEED_AVOID_LIST),
            slogan=SEED_SLOGAN,
        )
    )


def downgrade() -> None:
    op.drop_index("ix_marketing_brand_voice_condominio_id", "marketing_brand_voice")
    op.drop_constraint("uq_marketing_brand_voice_condominio", "marketing_brand_voice")
    op.drop_table("marketing_brand_voice")
