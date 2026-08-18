"""onvio: cada documento sabe de qual CNPJ e, e cada empresa sabe seu clientId no Onvio

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-18

Ate hoje o sincronizador do Onvio tinha UM clientId chumbado no codigo
(o da CONECTAMAIS ELETRONICA) e a tabela `onvio_documents` nao guardava de
quem era cada documento. Consequencia medida em 18/08/2026: 989 documentos da Eletronica
no banco, ZERO da Patrimonial — e os kits dos 7 condominios carregando o DCTFWeb da
ELETRONICA. Quem emprega os porteiros e ASG daqueles postos e a PATRIMONIAL (52 alocados
ativos contra 1). O kit existe para provar que a EMPREGADORA recolheu; guia da outra
empresa nao prova nada disso e foi removida (21 arquivos, 3 documentos x 7 kits).

Com a conta jjesus@conectamais.pro as duas aparecem:
    code= 25  (clientId da Eletronica)   CONECTAMAIS ELETRONICA LTDA   988 docs
    code=102  (clientId da Patrimonial)  CONECTAMAIS PATRIMONIAL LTDA    94 docs

Puxar as duas SEM esta coluna recriaria o problema que acabamos de limpar, so que com
mais material para errar: 1.083 documentos indistinguiveis na mesma tabela.

Duas colunas, nenhuma logica:

1. `empresas.onvio_client_id` — o mapa mora na tabela de empresas, que ja e a fonte da
   verdade de CNPJ e regime. Nao em dicionario no codigo: empresa nova entra por INSERT.

2. `onvio_documents.empresa_id` — FK, NULA por enquanto (documento antigo sem dono
   declarado nao vira mentira). O backfill abaixo marca os existentes como Eletronica
   porque foi de la que todos vieram — o clientId estava chumbado, nao havia outra origem.

A trava por CNPJ no nome do arquivo (`_e_de_outra_empresa`) continua valendo e vira a
SEGUNDA linha de defesa: ela pega o caso do arquivo que carrega CNPJ no nome, esta coluna
pega o caso do arquivo que nao carrega.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c5d6e7f8a9b0"  # pragma: allowlist secret
down_revision = "b4c5d6e7f8a9"  # pragma: allowlist secret
branch_labels = None
depends_on = None

# Identificadores de empresa no Onvio — aparecem na URL do client center, não são
# segredo. O detect-secrets os lê como hex de alta entropia.
ELETRONICA = "92A4D531C6314E309B62FDF3D9F1359C"  # pragma: allowlist secret
PATRIMONIAL = "8D844F0DC37144ABB513DEF5AA43418C"  # pragma: allowlist secret


def upgrade() -> None:
    op.add_column("empresas", sa.Column("onvio_client_id", sa.String(64), nullable=True))
    op.create_index("ix_empresas_onvio_client_id", "empresas", ["onvio_client_id"], unique=True)

    op.add_column("onvio_documents", sa.Column("empresa_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_onvio_documents_empresa", "onvio_documents", "empresas", ["empresa_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_onvio_documents_empresa_id", "onvio_documents", ["empresa_id"])

    # Mapa clientId -> empresa. Por SLUG, nao por uuid colado: uuid muda entre ambientes.
    op.execute(f"UPDATE empresas SET onvio_client_id = '{ELETRONICA}' WHERE slug = 'conecta_eletronica'")
    op.execute(f"UPDATE empresas SET onvio_client_id = '{PATRIMONIAL}' WHERE slug = 'conecta_patrimonial'")

    # Backfill: tudo que ja esta na tabela veio da Eletronica — era o unico clientId que
    # o sincronizador conhecia. Nao e chute, e a unica origem que existiu.
    op.execute(
        "UPDATE onvio_documents SET empresa_id = (SELECT id FROM empresas WHERE slug = 'conecta_eletronica') "
        "WHERE empresa_id IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_onvio_documents_empresa_id", table_name="onvio_documents")
    op.drop_constraint("fk_onvio_documents_empresa", "onvio_documents", type_="foreignkey")
    op.drop_column("onvio_documents", "empresa_id")
    op.drop_index("ix_empresas_onvio_client_id", table_name="empresas")
    op.drop_column("empresas", "onvio_client_id")
