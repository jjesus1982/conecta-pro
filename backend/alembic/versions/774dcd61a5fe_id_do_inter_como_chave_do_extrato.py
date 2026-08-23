"""o extrato do Inter passa a ter identidade propria (idTransacao)

Revision ID: 774dcd61a5fe
Revises: 42ddd4d1cb20
Create Date: 2026-08-23

`inter_transactions` deduplicava por (data_lancamento, tipo_operacao, valor, DESCRICAO), e
o Inter MUDA o texto da descricao entre importacoes:

    12/08 09:07  "PAGAMENTO DE TITULO - BANCO TOYOTA DO BRASIL SA"
    14/08 12:00  "BANCO TOYOTA DO BRASIL SA"

Texto instavel usado como identidade: a constraint nao pega e a mesma transacao entra
duas vezes. Foi assim que o saldo do Inter divergiu R$1.999,34 do que o proprio banco
informa, e apagar do extrato nao resolvia — a ponte recriava a partir daqui.

⚠️ Ja tentamos so trocar o endpoint. Em 14/08/2026 o `/extrato` virou `/extrato/completo`
para ganhar a contraparte e o sync das 12:00 DUPLICOU 47 linhas (R$1.497,79), porque o
`completo` devolve a descricao noutro formato. Reverteram. A licao esta escrita no proprio
adapter: trocar o endpoint SEM trocar a chave duplica; e o que resolve e a chave.

`id_transacao` vem do proprio banco (`idTransacao` em /banking/v2/extrato/completo):

    "MDAxXzAwMDE5XzM3MDk5MDA3Ml8yMDI2LTA4LTExXzM3MzMwNTYyMQ=="

⚠️ NAO se remove `descricao` da chave antiga: sem ela, dois VT de R$32,00 para pessoas
DIFERENTES no mesmo dia viram "duplicata" e um seria suprimido — e pagamento gemeo
legitimo existe (12 pares ja adjudicados contra o extrato do banco). Por isso a chave
antiga CONTINUA valendo para as linhas sem id, e a nova vale para as com id. Duas chaves
convivendo enquanto o backfill nao termina; nenhuma linha fica sem alguma protecao.
"""
from alembic import op

revision = "774dcd61a5fe"
down_revision = "42ddd4d1cb20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE inter_transactions ADD COLUMN IF NOT EXISTS id_transacao varchar(120)")
    # PARCIAL: enquanto houver linha sem id (as herdadas), o indice nao pode exigir
    # preenchimento — exigir tornaria a coluna NOT NULL na pratica e quebraria o import
    # antes do backfill.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_inter_tx_id_transacao
            ON inter_transactions (id_transacao)
         WHERE id_transacao IS NOT NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_inter_tx_data_valor "
               "ON inter_transactions (data_lancamento, valor, tipo_operacao)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_inter_tx_id_transacao")
    op.execute("DROP INDEX IF EXISTS ix_inter_tx_data_valor")
    op.execute("ALTER TABLE inter_transactions DROP COLUMN IF EXISTS id_transacao")
