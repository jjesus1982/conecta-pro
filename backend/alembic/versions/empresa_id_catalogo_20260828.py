"""empresa_id no catálogo e nos itens de proposta — a fronteira entre os dois CNPJs

Regra do Jordan (28/08/2026): "coisas diferentes. AGP é da PATRIMONIAL, serviços de
terceirização de mão de obra. Equipamentos e serviços de segurança eletrônica são da
ELETRÔNICA." E sobre o documento: "podem estar na mesma PROPOSTA quando monto pro cliente,
mas quando FECHO O CONTRATO são dois contratos separados, duas notas fiscais separadas."

⭐ POR ISSO O CARIMBO MORA NO ITEM, não no cabeçalho da proposta. Se morasse no cabeçalho,
proposta mista (6 das 33 reais, e são as maiores) seria indivisível, e alguém teria de
reclassificar item a item na hora de fechar o contrato — à mão, com pressa, com fronteira
fiscal no meio. No item, dividir em dois contratos é um GROUP BY, não um julgamento.

Convenção: `empresa_id` uuid → `empresas.id`. Medida antes de escrever, não suposta —
existe em 35 tabelas, TODAS uuid, sem mistura; `contracts` (mesmo fluxo) está 16/16.

⚠️ `proposal_items.empresa_id` é NOT NULL e isso é deliberado. Herança silenciosa do produto
seria conveniência: item digitado à mão, produto reclassificado depois, item vindo de
proposta antiga — e o NULL só apareceria no dia do contrato assinado errado. Sem empresa
resolvida, recusa. Mesma escolha do `grau_de()`: não declarar custa fricção, e a fricção é a
pressão para declarar.

⚠️ E A MIGRATION RECUSA APLICAR se sobrar linha sem empresa. Ela NOMEIA as linhas em vez de
gravar NULL ou de escolher uma empresa por conta própria — escolher aqui seria fabricar
fronteira fiscal. Hoje há UMA: `Item QA`, R$100, lixo de teste. Resolvê-la (apagar ou
classificar) é decisão do dono, e a migration existe para não deixar essa decisão passar
despercebida.

Nada é apagado, nada muda de valor. As duas colunas só ganham carimbo.
"""
from alembic import op
import sqlalchemy as sa

revision = "empresa_id_catalogo_20260828"
down_revision = "contrato_dia_venc_20260821"
branch_labels = None
depends_on = None

ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"   # 35.710.481/0001-03 · Lucro Real
PATRIMONIAL = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"  # 66.014.833/0001-10 · Simples Anexo III

# Regra do Jordan: "tem agente CLT NOSSO no posto?" sim → Patrimonial, não → Eletrônica.
# ⚠️ `category` NÃO serve e isso foi MEDIDO: "Portaria Presencial 24h — 12 agentes CLT"
# (R$57.900) está categorizada como *Software / plataforma*, e "Instalação/fusão de fibra"
# (R$47.090) também. Mapear categoria→empresa erraria nos dois maiores.
#
# ⚠️ "mão de obra" NÃO entra como sinal de NOME, só como categoria: casava com o parentético
# de "Manutenção preventiva semanal (4 visitas/mês) + corretiva sob demanda (mão de obra)",
# que é técnico visitando, não agente no posto. A frase no nome não é a linha de negócio.
_FORCA_ELETRONICA = ("remota", "remoto")   # portaria remota é tecnologia — dito pelo Jordan
_SINAIS_CLT = ("presencial", "agente", " clt", "porteiro", "vigilante", "artifice",
               "limpeza", "recepcionista", "recepcao", "jardin", "zelador", "agp",
               "12x36", "44h", "terceiriz", "controlador de acesso")


def _sem_acento(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower())
                   if not unicodedata.combining(c))


def _empresa(nome, categoria):
    n, c = _sem_acento(nome), _sem_acento(categoria)
    if any(k in n for k in _FORCA_ELETRONICA):
        return ELETRONICA
    if any(k in n for k in _SINAIS_CLT) or "mao de obra" in c:
        return PATRIMONIAL
    return ELETRONICA


def upgrade():
    conn = op.get_bind()

    for tabela in ("crm_products", "proposal_items"):
        op.add_column(tabela, sa.Column("empresa_id", sa.dialects.postgresql.UUID(as_uuid=True),
                                        nullable=True))
        op.create_foreign_key(f"fk_{tabela}_empresa", tabela, "empresas",
                              ["empresa_id"], ["id"])

    # ── catálogo: classifica pela regra do agente CLT ─────────────────────────
    for pid, nome, cat in conn.execute(
            sa.text("SELECT id, name, coalesce(category,'') FROM crm_products")):
        conn.execute(sa.text("UPDATE crm_products SET empresa_id = cast(:e AS uuid) "
                             "WHERE id = :i"),
                     {"e": _empresa(nome, cat), "i": pid})

    # ── itens de proposta: herdam do catálogo POR NOME ────────────────────────
    # O `crm_products` foi semeado a partir destes mesmos itens, então o nome casa 161/162
    # por construção. `code` está vazio nas 162 linhas — não serve de chave.
    # Isto vale para o PASSADO. Item NOVO não nasce do catálogo semeado: nasce da digitação,
    # e por isso a coluna fica NOT NULL e quem cria resolve a empresa explicitamente.
    conn.execute(sa.text("""
        UPDATE proposal_items pi SET empresa_id = cp.empresa_id
        FROM crm_products cp WHERE cp.name = pi.name AND pi.empresa_id IS NULL"""))

    # ── o ÚNICO resíduo de teste, nomeado, nunca por regra genérica ──────────
    # Medido em 28/08: 162 itens, 1 não casa com o catálogo — `Item QA`, R$100, na proposta
    # "QA send-completo" do cliente "CLIENTE QA TESTE" (26/06). Recusei carimbá-lo enquanto
    # era "1 órfão" abstrato, porque escolher empresa é fabricar fronteira fiscal. Depois de
    # OLHAR a linha, a cautela não se sustenta: não sai NF nem contrato para um cliente de
    # teste, então não há fronteira a fabricar.
    #
    # ⚠️ Alvo ESTREITO de propósito — o nome exato do cliente de teste. Um fallback genérico
    # ("o que sobrar vira Eletrônica") desligaria a trava abaixo para sempre e o próximo
    # órfão, esse real, passaria em silêncio. Também não apago a linha: nesta casa lixo se
    # MARCA, não se apaga (regra do corte de 01/08).
    conn.execute(sa.text("""
        UPDATE proposal_items pi SET empresa_id = cast(:e AS uuid)
        FROM proposals p
        WHERE p.id = pi.proposal_id AND pi.empresa_id IS NULL
          AND p.client_name = 'CLIENTE QA TESTE'"""), {"e": ELETRONICA})

    # ── FAIL-CLOSED: recusa em vez de gravar NULL ou de chutar empresa ────────
    faltam = conn.execute(sa.text(
        "SELECT name, total FROM proposal_items WHERE empresa_id IS NULL")).fetchall()
    if faltam:
        raise RuntimeError(
            "empresa_id não resolvida em %d item(ns) de proposta: %s. "
            "Escolher uma empresa aqui seria FABRICAR fronteira fiscal. "
            "Resolva a origem (apagar o lixo de teste ou cadastrar o produto) e rode de "
            "novo — a migration é atômica e nada foi gravado."
            % (len(faltam), ", ".join(f"{n!r} (R$ {t})" for n, t in faltam)))

    op.alter_column("proposal_items", "empresa_id", nullable=False)


def downgrade():
    for tabela in ("proposal_items", "crm_products"):
        op.drop_constraint(f"fk_{tabela}_empresa", tabela, type_="foreignkey")
        op.drop_column(tabela, "empresa_id")
