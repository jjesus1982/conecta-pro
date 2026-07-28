"""fase5.5 Task 1 — colunas de curadoria em consultor_memorias + quarentena

Fundação da Fase 5.5 (memória que aprende). Hoje `consultor_memorias` recebe
write-back automático (extrator gpt-4o-mini) SEM nenhuma curadoria humana —
36 linhas já existentes, várias envenenadas (Jordan). Esta migration:

1. Adiciona 5 colunas de curadoria (aditivo, IF NOT EXISTS, nunca destrutivo):
   - status            text        NOT NULL DEFAULT 'pendente_revisao'
   - confidence        real                  (score do extrator/curador)
   - autor             text                  (quem/o-que gerou a memória)
   - curator_veredito  jsonb                 (decisão do curador humano/IA)
   - expira_em         timestamptz           (TTL opcional da memória)
2. QUARENTENA: todo registro pré-existente com status fora de
   ('ativo','rejeitado') vira 'pendente_revisao' — inclui as 36 linhas atuais,
   que passam a exigir curadoria antes de voltar a alimentar os consultores.
   NENHUMA linha é apagada (migration puramente aditiva).

O filtro em `contexto_compartilhado` (consultor_hub.py) passa a exigir
status='ativo' AND (expira_em IS NULL OR expira_em > now()) — isso é feito no
código Python, não aqui; esta migration só prepara o schema.

Revision ID: fase55_mem_curadoria
Revises: fase54_esocial_prop

NOTA head: confirmada via `python3 -m alembic heads` em disco (2026-07-28) —
único head real é "fase54_esocial_prop" (fase54_esocial_transmissao_propostas.py).
Encadeado nela p/ não abrir 2º head.
"""
from alembic import op

revision = "fase55_mem_curadoria"
down_revision = "fase54_esocial_prop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE consultor_memorias
            ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'pendente_revisao'
        """
    )
    op.execute("ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS confidence real")
    op.execute("ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS autor text")
    op.execute("ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS curator_veredito jsonb")
    op.execute("ALTER TABLE consultor_memorias ADD COLUMN IF NOT EXISTS expira_em timestamptz")

    # Quarentena: tudo que não é explicitamente 'ativo' ou 'rejeitado' vira
    # 'pendente_revisao' — cobre as linhas pré-existentes (DEFAULT já as
    # populou com 'pendente_revisao' no ADD COLUMN, mas o UPDATE explícito
    # documenta a intenção e cobre qualquer valor divergente futuro).
    op.execute(
        """
        UPDATE consultor_memorias
        SET status = 'pendente_revisao'
        WHERE status NOT IN ('ativo', 'rejeitado')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE consultor_memorias DROP COLUMN IF EXISTS expira_em")
    op.execute("ALTER TABLE consultor_memorias DROP COLUMN IF EXISTS curator_veredito")
    op.execute("ALTER TABLE consultor_memorias DROP COLUMN IF EXISTS autor")
    op.execute("ALTER TABLE consultor_memorias DROP COLUMN IF EXISTS confidence")
    op.execute("ALTER TABLE consultor_memorias DROP COLUMN IF EXISTS status")
