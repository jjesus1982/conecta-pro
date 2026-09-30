"""A fronteira fiscal entre os dois CNPJs, em UM lugar só.

Regra dura do Jordan (30/09/2026), a mesma que já estava escrita na migration
`empresa_id_catalogo_20260828` e que até hoje ninguém EXECUTAVA:

    material        → ELETRÔNICA  · 35.710.481/0001-03 · Lucro Real  · nota de MATERIAL
    servico_tecnico → ELETRÔNICA  · 35.710.481/0001-03 · NFS-e · ISS 5%
    mao_de_obra     → PATRIMONIAL · 66.014.833/0001-10 · NFS-e · ISS 0% + INSS 11%

Material NUNCA sai pela Patrimonial (o objeto social não cobre e o Anexo IV não
comporta revenda). A PROPOSTA pode misturar as três classes; a NOTA nunca pode.

⭐ POR QUE A ALÍQUOTA DE ISS MORA NA EMPRESA E NÃO NO CÓDIGO DE SERVIÇO
Medido em 30/09/2026 sobre as 160 notas reais de `nfse_emitidas_nacional`:

    empresa      código   notas   ISS
    eletrônica   071001       8   5%
    eletrônica   071002      11   5%
    eletrônica   110201      47   5%
    eletrônica   140101      10   5%
    eletrônica   140601      42   5%
    patrimonial  071002      12   0%
    patrimonial  110201      28   0%  (28 a 0%; o resto é legado anterior ao Anexo IV)

O MESMO código 110201 sai a 5% pela Eletrônica e a 0% pela Patrimonial. Quem manda
é o REGIME, não o item da lista: a Patrimonial é Simples Anexo IV e o ISS dela já
está dentro do DAS. `fin_codigos_servico.aliquota_iss` traz 4,35% para o 110201 —
número que não corresponde a NENHUMA das 75 notas com esse código. Por isso a
alíquota não é lida de lá.

⚠️ AS 47 NOTAS DE «VIGILÂNCIA» (110201) PELA ELETRÔNICA SÃO EXATAMENTE O ERRO que este
módulo existe para impedir: mão de obra faturada no CNPJ errado, no regime errado.
Não são corrigidas aqui — nota autorizada é decisão do contador.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Os dois CNPJs. Ver a migration `empresa_id_catalogo_20260828`.
ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
PATRIMONIAL = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"

#: classe fiscal → CNPJ emitente. Esta tabela é a regra do dono, não uma heurística:
#: uma vez declarada a classe, a empresa NÃO é escolha de ninguém.
CLASSE_EMPRESA: dict[str, str] = {
    "material": ELETRONICA,
    "servico_tecnico": ELETRONICA,
    "mao_de_obra": PATRIMONIAL,
}
CLASSES = tuple(CLASSE_EMPRESA)

#: ISS por EMPRESA (medido, ver docstring). Patrimonial é Simples Anexo IV: ISS no DAS.
ISS_POR_EMPRESA: dict[str, float] = {ELETRONICA: 5.0, PATRIMONIAL: 0.0}

#: Retenção previdenciária do art. 31 da Lei 9.711/98 — só cessão de mão de obra.
INSS_RETENCAO = 0.11

#: Código de serviço SUGERIDO por classe. `fin_codigos_servico.ctribnac` é a chave.
#: Sugestão, não imposição: quem orça confirma (é o que o prompt 2 [4] pede).
CODIGO_SUGERIDO: dict[str, str] = {
    "servico_tecnico": "140601",  # Instalação e montagem de aparelhos e equipamentos
    "mao_de_obra": "110201",  # Vigilância, segurança ou monitoramento
}

#: Apelidos aceitos para a empresa em argumento de tool/tela.
_SLUG_EMPRESA = {
    "eletronica": ELETRONICA,
    "eletrônica": ELETRONICA,
    "conecta_eletronica": ELETRONICA,
    "35710481000103": ELETRONICA,
    "patrimonial": PATRIMONIAL,
    "conecta_patrimonial": PATRIMONIAL,
    "66014833000110": PATRIMONIAL,
}


def empresa_uuid(v) -> str | None:
    """'eletronica' | 'patrimonial' | CNPJ | uuid → uuid. Desconhecido → None (vira recusa)."""
    t = str(v or "").strip().lower()
    if not t:
        return None
    if t in _SLUG_EMPRESA:
        return _SLUG_EMPRESA[t]
    d = re.sub(r"\D", "", t)
    if d in _SLUG_EMPRESA:
        return _SLUG_EMPRESA[d]
    return t if len(t) == 36 and t.count("-") == 4 else None


def normalizar_classe(v) -> str | None:
    """Aceita a classe escrita com acento, espaço ou hífen. Fora das três → None."""
    t = _sem_acento(str(v or "")).strip().replace("-", "_").replace(" ", "_")
    return t if t in CLASSE_EMPRESA else None


def empresa_da_classe(classe) -> str | None:
    c = normalizar_classe(classe)
    return CLASSE_EMPRESA.get(c) if c else None


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(c))


# ── RESOLUÇÃO DA EMPRESA DE CADA ITEM ──────────────────────────────────────────────────
# A ordem é deliberada e vai do mais explícito ao menos:
#   1. empresa_id já no item          — quem montou resolveu; ninguém revoga
#   2. classe_fiscal do item          — regra do dono, determinística
#   3. empresa padrão da proposta     — o operador declarou uma vez para todos
#   4. RECUSA nomeando os itens       — nunca NULL, nunca chute
#
# O passo 4 é o coração: era ele que faltava. Sem ele, `empresa_id=None` chegava ao
# INSERT e o Postgres devolvia NotNullViolation — que o FastAPI virava 500 "Internal
# Server Error", sem dizer o que faltava. Seis tentativas do Jordan em 30/09 morreram
# assim, todas com a mesma mensagem que não ensinava nada.


def resolver_empresa_dos_itens(itens: list, padrao=None) -> list[str]:
    """Carimba `empresa_id` em cada item IN-PLACE. Devolve a lista dos que não deu.

    `itens` são objetos com os atributos `empresa_id`, `classe_fiscal` e `name`
    (ProposalItemCreate) — ou dicts com as mesmas chaves.

    ⚠️ CLASSE DECLARADA VENCE `empresa_id` DIGITADO, e contradição entre os dois RECUSA.
    É o que garante «material nunca sai pela Patrimonial»: se a classe manda numa empresa
    e o campo manda noutra, aceitar em silêncio qualquer um dos dois esconderia um erro
    de fronteira fiscal que só apareceria na nota. Quem discorda muda a classe.
    """
    pad = empresa_uuid(padrao)
    faltando: list[str] = []
    for i, it in enumerate(itens, 1):
        get = it.get if isinstance(it, dict) else (lambda k, _o=it: getattr(_o, k, None))
        rotulo = str(get("name") or get("descricao") or "?")[:44]
        classe = normalizar_classe(get("classe_fiscal"))
        da_classe = CLASSE_EMPRESA.get(classe) if classe else None
        atual = str(get("empresa_id")) if get("empresa_id") else None

        if da_classe and atual and atual != da_classe:
            faltando.append(
                f"{i}. {rotulo} — classe '{classe}' sai pela {_nome_curto(da_classe)}, "
                f"mas o item veio carimbado com a {_nome_curto(atual)}"
            )
            continue

        alvo = da_classe or atual or pad
        if alvo:
            if isinstance(it, dict):
                it["empresa_id"] = alvo
            else:
                it.empresa_id = alvo
        else:
            faltando.append(f"{i}. {rotulo}")
    return faltando


def _nome_curto(empresa_id: str) -> str:
    return {ELETRONICA: "ELETRÔNICA", PATRIMONIAL: "PATRIMONIAL"}.get(empresa_id, empresa_id[:8])


def recusa_por_empresa(faltando: list[str]) -> str:
    """A mensagem que o 500 não dava. Diz o que faltou E como resolver."""
    return (
        "não sei por qual dos dois CNPJs estes itens saem: "
        + "; ".join(faltando)
        + ". Declare `classe_fiscal` em cada item (material e servico_tecnico saem pela "
        "ELETRÔNICA 35.710.481/0001-03; mao_de_obra sai pela PATRIMONIAL "
        "66.014.833/0001-10), ou informe `empresa` para a proposta inteira. "
        "Escolher o CNPJ por você seria fabricar fronteira fiscal, e o erro só "
        "apareceria na nota."
    )


# ── TIPO DE NEGÓCIO (prompt 2 [1]) ─────────────────────────────────────────────────────
# A → recorrente (gera receita mensal com vigência)
# B → projeto/obra (instala sistema novo: material + serviço técnico juntos)
# D → só material, sem mão de obra e sem serviço
# C → nenhuma das anteriores (avulso)
#
# ⚠️ O critério é a NATUREZA das linhas, nunca o VALOR. Green Hills R$ 500 e Maiápolis
# R$ 23.160 são os dois avulsos; separar por faixa de valor classificaria os dois errado.


def derivar_tipo_negocio(itens: list, *, recorrente: bool = False) -> str:
    """A|B|C|D a partir das classes dos itens. `recorrente` vem de billing_type/term_options."""
    if recorrente:
        return "A"
    classes = {
        normalizar_classe(it.get("classe_fiscal") if isinstance(it, dict) else getattr(it, "classe_fiscal", None))
        for it in (itens or [])
    }
    classes.discard(None)
    if not classes:
        return "C"
    if classes == {"material"}:
        return "D"
    if "material" in classes and "servico_tecnico" in classes:
        return "B"
    if "mao_de_obra" in classes:
        return "A"
    return "C"


#: Tipos que EXIGEM contrato antes de faturar (prompt 2 [1]).
TIPOS_COM_CONTRATO = frozenset({"A", "B"})
#: Tipos que exigem `data_execucao` antes de faturar (prompt 2 [7]). A é recorrente.
TIPOS_COM_EXECUCAO = frozenset({"B", "C", "D"})


# ── DADOS BANCÁRIOS POR EMPRESA (prompt 2 [6]) ─────────────────────────────────────────
# ⚠️ MEDIDO EM 30/09/2026 — 4 NOTAS DA PATRIMONIAL MANDARAM O CLIENTE PAGAR NA CONTA
# DA ELETRÔNICA. A discriminação é texto colado, e o texto colado envelhece:
#
#     nº  1  25/06  R$ 42.544,50  Residencial Laranjeiras Village
#     nº  2  25/06  R$ 42.544,50  Residencial Laranjeiras Village
#     nº  3  25/06  R$ 42.544,50  Residencial Laranjeiras Village
#     nº 22  20/08  R$  3.879,60  Condomínio Prime Arena
#                   R$ 131.513,10 mandados para o CNPJ errado
#
# O prompt do Jordan citava só a nº 22. São quatro, e as três de junho são as maiores.
# O contrário não acontece: ZERO notas da Eletrônica citam a Cora. O erro tem direção —
# a Patrimonial nasceu depois, e quem copiava a discriminação copiava a da Eletrônica.
#
# A conta não é escolha de quem digita: é atributo do EMITENTE.

DADOS_BANCARIOS: dict[str, dict[str, str]] = {
    ELETRONICA: {
        "banco": "INTER",
        "codigo": "077",
        "agencia": "0001",
        "conta": "37099007-2",
        "pix": "35.710.481/0001-03",
    },
    PATRIMONIAL: {
        "banco": "CORA SCD",
        "codigo": "403",
        "agencia": "0001",
        "conta": "7382527-7",
        "pix": "66.014.833/0001-10",
    },
}


def linha_bancaria(empresa_id: str) -> str:
    """A linha de dados bancários do EMITENTE, montada — nunca colada."""
    b = DADOS_BANCARIOS.get(str(empresa_id))
    if not b:
        raise ValueError(
            f"não tenho dados bancários para a empresa {empresa_id!r} — "
            f"e chutar conta é mandar o cliente pagar no lugar errado"
        )
    return f"BANCO {b['banco']}: {b['codigo']} AGÊNCIA: {b['agencia']} CONTA: {b['conta']} CHAVE PIX: CNPJ {b['pix']}."


def cnpj_da_empresa(empresa_id: str) -> str:
    return {ELETRONICA: "35710481000103", PATRIMONIAL: "66014833000110"}[str(empresa_id)]


# ── RETENÇÃO DE INSS (prompt 2 [5]) ────────────────────────────────────────────────────
# Art. 31 da Lei 9.711/98: 11% sobre o valor bruto dos serviços de CESSÃO DE MÃO DE OBRA,
# deduzidos VT e VA quando destacados. Só `mao_de_obra` — serviço técnico não retém.
#
# Conferido contra a NFS-e nº 35 real (Laranjeiras Village):
#     bruto    R$ 42.544,50
#     deduções R$  3.688,00  (VA 2.552,00 + VT 1.136,00)
#     base     R$ 38.856,50
#     11%      R$  4.274,21   ← e 38856.50 × 0.11 = 4274.215, que arredonda para 4.274,22
#
# O centavo de diferença é o arredondamento do fisco (trunca, não arredonda). Por isso
# a função TRUNCA: copiar o comportamento do fisco vale mais que a matemática redonda.


def retencao_inss(valor_bruto: float, deducoes: float = 0.0) -> dict[str, float]:
    """Base e retenção de INSS. TRUNCA no centavo, como a NFS-e nº 35 comprova."""
    base = max(0.0, float(valor_bruto) - float(deducoes))
    return {"base": round(base, 2), "retencao": int(base * INSS_RETENCAO * 100) / 100, "aliquota": INSS_RETENCAO * 100}


# ── DDL IDEMPOTENTE ────────────────────────────────────────────────────────────────────
# Mesmo padrão de `item_do_catalogo.garantir_coluna`: a coluna nasce na primeira chamada.
# `alembic/versions/` é zona proibida por CLAUDE.md e este caminho já é o da casa.

DDL = (
    "ALTER TABLE proposal_items ADD COLUMN IF NOT EXISTS classe_fiscal varchar(20)",
    "COMMENT ON COLUMN proposal_items.classe_fiscal IS "
    "'material | servico_tecnico | mao_de_obra. Determina o CNPJ emitente (ver "
    "modules/crm/services/classe_fiscal.py). NULO = item anterior a 30/09/2026, que "
    "carrega empresa_id mas não a razão dela.'",
    "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS tipo_negocio varchar(1)",
    "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS tipo_negocio_por varchar(120)",
    "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS tipo_negocio_em timestamp",
    "COMMENT ON COLUMN proposals.tipo_negocio IS "
    "'A recorrente | B projeto/obra | C avulso | D material. Derivado dos itens; "
    "`tipo_negocio_por` preenchido = sobrescrito à mão por aquela pessoa.'",
    "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS data_execucao date",
    "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS executado_por varchar(160)",
    "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS aceite_cliente jsonb",
    "COMMENT ON COLUMN proposals.data_execucao IS "
    "'Quando o serviço foi executado. Substitui a OS, que o dono decidiu não usar "
    "(30/09/2026). Tipo B/C/D não fatura sem ela.'",
    "ALTER TABLE fin_codigos_servico ADD COLUMN IF NOT EXISTS classe_fiscal varchar(20)",
)


async def garantir_colunas(db: AsyncSession) -> None:
    for ddl in DDL:
        await db.execute(text(ddl))
    await db.commit()
