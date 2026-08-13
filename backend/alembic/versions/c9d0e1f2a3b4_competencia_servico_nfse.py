"""nfse: competencia do SERVICO quando o ADN manda a data de emissao

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-13

O painel mostrava julho/2026 com R$378.286,98 — R$108.386,92 acima dos outros
meses. Nao havia nota duplicada: n109 (Laranjeiras, R$42.544,50) e n111 (Ideal
Flores, R$65.842,42) sao o faturamento de JUNHO, emitido pela Eletronica em
09/07 e 14/07. Julho saiu pela Patrimonial (n13 e n21). A prova e aritmetica:
atribuindo as duas a junho, os meses ficam chapados —
marco 268.886,96 · abril 271.971,46 · maio 262.604,96 · junho 271.916,59 ·
julho 269.900,06.

A causa: o `dCompet` que o ADN devolve vem preenchido com a DATA DE EMISSAO, nao
com o mes do servico. Nota emitida com atraso cai no mes errado — e como junho e
julho foram os meses da transicao de CNPJ, os dois meses viraram um so.

`competencia_origem_adn` guarda o que o gov mandou, e a presenca dela marca a
linha como CORRIGIDA POR NOS. O sync (recarga limpa diaria) passa a preservar
essas linhas: sem isso a correcao viveria ate as 08:30 do dia seguinte.
"""
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE nfse_emitidas_nacional "
        "ADD COLUMN IF NOT EXISTS competencia_origem_adn VARCHAR(7)"
    )
    op.execute(
        "COMMENT ON COLUMN nfse_emitidas_nacional.competencia_origem_adn IS "
        "'Competencia que o ADN devolveu, guardada quando corrigimos `competencia` para o mes "
        "do SERVICO. NULL = intocada. Preenchida = o sync nao sobrescreve mais esta linha.'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE nfse_emitidas_nacional SET competencia = competencia_origem_adn "
        "WHERE competencia_origem_adn IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE nfse_emitidas_nacional DROP COLUMN IF EXISTS competencia_origem_adn"
    )
