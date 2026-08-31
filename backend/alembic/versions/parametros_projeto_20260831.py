"""Parâmetros do projeto em campo ESTRUTURADO, cada um com sua origem.

31/08/2026. O dimensionador não pode ler prosa. O `panorama` do The Sun é um log
append-only: as três primeiras entradas dizem "32 câmeras" e a quarta diz 64. Quem trunca
o texto dimensiona meio projeto.

E medido: NENHUM campo estruturado do sistema dizia "64 câmeras". O número existia só na
conversa do WhatsApp e na prosa do relatório. Um dimensionador honesto precisa de um lugar
onde o dado tem VALOR e ORIGEM — sem origem, número é palpite com cara de fato.

Formato de cada parâmetro:
    {"valor": 64, "origem": "Jordan, WhatsApp 31/08/2026", "unidade": "câmeras"}

Revision ID: parametros_projeto_20260831
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "parametros_projeto_20260831"
down_revision = "cotacao_visita_20260831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    ja = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='crm_visit_reports' AND column_name='parametros'")).scalar()
    if not ja:
        op.add_column("crm_visit_reports",
                      sa.Column("parametros", postgresql.JSONB(), nullable=True))

    # Só o The Sun, e só o que tem ORIGEM verificável. O que não tem fica de fora —
    # a ausência é informação: vira incógnita nomeada na tela, não estimativa.
    conn.execute(sa.text("""
        UPDATE crm_visit_reports SET parametros = cast(:p as jsonb)
        WHERE id::text LIKE '5307691d%' AND parametros IS NULL
    """), {"p": """{
      "cameras":            {"valor": 64, "unidade": "câmeras IP PoE",
                             "origem": "Jordan, WhatsApp 31/08/2026 — subiu de 32 para 64"},
      "canais_por_nvr":     {"valor": 16, "unidade": "canais",
                             "origem": "VTV-074 é NVR 16CH — NF-e Futura 19.535"},
      "slots_hd_por_nvr":   {"valor": 2, "unidade": "slots",
                             "origem": "Jordan pediu 8 HDs para 4 NVR (WhatsApp 31/08) — 8÷4"},
      "nobreak_por_rack":   {"valor": 1, "unidade": "nobreak",
                             "origem": "Jordan, WhatsApp 31/08/2026 — regra da casa"},
      "topologia":          {"valor": "descentralizada", "unidade": "",
                             "origem": "Jordan, 31/08 — 'conexões entre um rack e outro'"}
    }"""})


def downgrade() -> None:
    op.drop_column("crm_visit_reports", "parametros")
