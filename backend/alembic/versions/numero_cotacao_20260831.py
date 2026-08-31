"""Alarga `purchase_quotations.number` — varchar(20) estourou com dado real.

31/08/2026 18:35. O Jordan aprovou a cotação da Kely, **a mensagem SAIU** e o INSERT
falhou: `value too long for type character varying(20)`. O gerador montava
`<NOME_DO_FORNECEDOR>-<YYYYMMDDHHMM>`, e "FUTURA TECNOLOGIA INDUSTRIA E COMERCIO DE
PRODUTOS ELETRONIC" não cabe em lugar nenhum.

⚠️ Os dois do Hawk Eye têm EXATAMENTE 20 caracteres. Passaram por sorte — o mesmo defeito
estava a uma letra de acontecer com o Renier.

Alargar é metade: o gerador também encurtou para `COT-YYYYMMDDHHMM-XXXX`, que não depende
do nome. O vínculo com o fornecedor já existe pela FK — pôr o nome no identificador era
enfeite com custo.

Revision ID: numero_cotacao_20260831
"""
from alembic import op
import sqlalchemy as sa

revision = "numero_cotacao_20260831"
down_revision = "parametros_projeto_20260831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("purchase_quotations", "number",
                    type_=sa.String(40), existing_type=sa.String(20), existing_nullable=False)


def downgrade() -> None:
    # ⚠️ Só volta se nenhum número passar de 20 — senão o downgrade corrompe dado.
    conn = op.get_bind()
    n = conn.execute(sa.text(
        "SELECT count(*) FROM purchase_quotations WHERE length(number) > 20")).scalar()
    if n:
        raise RuntimeError(f"{n} cotação(ões) com número maior que 20 — downgrade truncaria")
    op.alter_column("purchase_quotations", "number",
                    type_=sa.String(20), existing_type=sa.String(40), existing_nullable=False)
