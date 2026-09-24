"""Cadastro fiscal do produto — o que falta para uma NF-e de mercadoria ser aceita (DGX Z1).

24/09/2026. O fato: existem DUAS tentativas de NF-e de saída no sistema, ambas de 11/04/2026,
ambas **rejeitadas** — a última com «Rejeição: Informado NCM inexistente [nItem: 1]». Sem cadastro
fiscal de produto correto nenhuma nota sai, e o dono precisa emitir.

O que foi CAVADO antes de construir (sandbox = cópia de produção de 23/09):

  · **A tabela oficial de NCM já está carregada**: `ncms` tem **10.515 códigos** vigentes, com
    capítulo/posição/subposição e o caminho hierárquico em `descricao_resumida` — carregada do
    Portal Único Siscomex por `scripts/orq/carregar_tabela_ncm.py` (27/08/2026). Logo **não nasce
    `fin_ncm`**: validar é `JOIN ncms`. O `fiscal_controller.py` tem a seção «NCM Endpoints» VAZIA
    (linha 46) — a validação não existia em lugar nenhum; é ela que entra aqui.
  · **As compras são fonte de verdade**: `nfe_compras_estoque` tem 147 itens com **95 NCMs
    distintos**, todos extraídos de NF-e reais de fornecedores pela F9. Desses 95, **94 existem na
    tabela oficial**; 1 não (`65119000`, «CAPACETE DE SEGURANCA BRANCO» — o fornecedor errou: o
    capítulo 65 termina em 6507). Esse produto nasce **inativo com o motivo escrito**, não
    corrigido por palpite: NCM errado é multa e glosa de crédito.
  · **`products` (867 linhas, catálogo do Bling) NÃO é isto.** É catálogo de compra de eletrônica,
    sem tributação por CNPJ e sem unidade tributável/CFOP por UF. Ver §5/§7 do relatório: unir os
    dois é decisão do dono, não do agente.

Duas tabelas porque a **mesma mercadoria tem tributação diferente nas duas empresas**:
`CONECTAMAIS ELETRONICA` (35.710.481/0001-03, lucro real, SUFRAMA 210140500, Manaus) usa CST de
ICMS; `CONECTAMAIS PATRIMONIAL` (66.014.833/0001-10, Simples Nacional) usa CSOSN.

**Nada nasce preenchido por chute.** O seed grava só o que veio do documento fiscal (descrição,
NCM, unidade comercial/tributável, GTIN, origem da mercadoria e CEST, lidos do XML da nota de
entrada). CFOP e CST/CSOSN nascem NULL e a tela diz «incompleto para emitir», listando o que
falta. Preencher em lote existe, mas é **ato explícito de uma pessoa**, e grava em `origem_regra`
quem, quando e com que fundamento legal — do mesmo jeito que `sugerir_ncm_produtos.py` separa
«o sistema achou» de «alguém classificou».

Este módulo NÃO toca o emissor de NF-e (`fiscal_contabil/notas_fiscais/nfe/`,
`financial/integrations/nfe_provider.py`) — é cadastro, e ligar o cadastro na emissão é a frente Z2.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date

from defusedxml.ElementTree import fromstring as _xml  # XML de terceiro: nunca o parser cru
from fastapi import HTTPException
from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Tabela A do CST (origem da mercadoria), NT 2011/004 — o `<orig>` do XML.
ORIGENS = {
    "0": "0 — Nacional, exceto 3/4/5/8",
    "1": "1 — Estrangeira, importação direta",
    "2": "2 — Estrangeira, adquirida no mercado interno",
    "3": "3 — Nacional, conteúdo de importação > 40% e <= 70%",
    "4": "4 — Nacional, processos produtivos básicos (Dec.-Lei 288/67 — ZFM)",
    "5": "5 — Nacional, conteúdo de importação <= 40%",
    "6": "6 — Estrangeira, importação direta, sem similar nacional (CAMEX)",
    "7": "7 — Estrangeira, mercado interno, sem similar nacional (CAMEX)",
    "8": "8 — Nacional, conteúdo de importação > 70%",
}

#: O que a SEFAZ responde quando o NCM do item não consta na nomenclatura. É a mensagem literal
#: da rejeição 778 que derrubou a nota 2 de 11/04/2026 — a tela repete essa frase, não outra.
MSG_NCM_INEXISTENTE = "Rejeição: Informado NCM inexistente [nItem: 1]"

#: Fundamento do preenchimento em lote. Vai INTEIRO para `origem_regra`, com quem e quando.
PADRAO_REGIME = {
    "lucro_real": {
        "cst_pis": "01",
        "aliquota_pis": "1.65",
        "cst_cofins": "01",
        "aliquota_cofins": "7.60",
        "fundamento": (
            "PIS 1,65% e COFINS 7,60% não-cumulativos, CST 01 (operação tributável com alíquota "
            "básica) — Lei 10.637/2002 art. 2º e Lei 10.833/2003 art. 2º, regime lucro real"
        ),
    },
    "simples_nacional": {
        "csosn": "102",
        "cst_pis": "49",
        "cst_cofins": "49",
        "fundamento": (
            "CSOSN 102 (tributada pelo Simples Nacional sem permissão de crédito) e CST 49 de "
            "PIS/COFINS — LC 123/2006; PIS/COFINS recolhidos dentro do DAS, sem destaque no item"
        ),
    },
}


def _dig(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


async def _ensure(db) -> None:
    """DDL idempotente. Chamada por `telas()` e por TODA ação (o contrato da casa)."""
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS fin_produtos (
                id SERIAL PRIMARY KEY,
                codigo VARCHAR(60) NOT NULL UNIQUE,
                descricao VARCHAR(200) NOT NULL,
                ncm VARCHAR(8),
                cest VARCHAR(7),
                origem VARCHAR(1),
                unidade_comercial VARCHAR(6),
                unidade_tributavel VARCHAR(6),
                ean VARCHAR(20),
                peso_liquido NUMERIC(15,3),
                peso_bruto NUMERIC(15,3),
                cfop_padrao_dentro_uf VARCHAR(4),
                cfop_padrao_fora_uf VARCHAR(4),
                ativo BOOLEAN NOT NULL DEFAULT true,
                motivo_inativo TEXT,
                origem_cadastro VARCHAR(20) NOT NULL DEFAULT 'manual',
                observacao TEXT,
                criado_em TIMESTAMP NOT NULL DEFAULT now(),
                atualizado_em TIMESTAMP
            )
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_fin_produtos_ncm ON fin_produtos(ncm)"))
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS fin_produto_tributacao (
                id SERIAL PRIMARY KEY,
                produto_id INTEGER NOT NULL REFERENCES fin_produtos(id) ON DELETE CASCADE,
                empresa_cnpj VARCHAR(18) NOT NULL,
                cst_icms VARCHAR(3),
                csosn VARCHAR(3),
                aliquota_icms NUMERIC(8,4),
                cst_pis VARCHAR(2),
                aliquota_pis NUMERIC(8,4),
                cst_cofins VARCHAR(2),
                aliquota_cofins NUMERIC(8,4),
                cst_ipi VARCHAR(2),
                aliquota_ipi NUMERIC(8,4),
                origem_regra TEXT NOT NULL,
                atualizado_em TIMESTAMP NOT NULL DEFAULT now(),
                UNIQUE (produto_id, empresa_cnpj)
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS fin_ncm_busca (
                codigo VARCHAR(8) PRIMARY KEY,
                descricao_resumida TEXT,
                doc TSVECTOR
            )  -- `descricao_resumida` aqui guarda o CAMINHO (ncms.descricao) — ver nota em _ensure_busca
            """
        )
    )
    await db.execute(text("CREATE INDEX IF NOT EXISTS ix_fin_ncm_busca_doc ON fin_ncm_busca USING gin(doc)"))
    await db.commit()


# ------------------------------------------------------- sugerir NCM pela descrição

#: Régua de semelhança do `scripts/orq/sugerir_ncm_produtos.py` (27/08/2026). Copiada, não
#: importada: aquilo é um CLI com `sys.path` próprio, e serviço não importa script. O corte 0,80
#: foi MEDIDO lá — em 0,70 o casamento aceitou «Cabo de rede 4PX0,5 bobina 300MT» como «TESTADOR
#: DE CABO DE REDE» (1 erro em 6). Aqui o corte não barra: ele só separa «forte» de «fraco», e a
#: decisão continua sendo humana.
_CORTE_FORTE = 0.80
_VAZIAS = {
    "de",
    "da",
    "do",
    "com",
    "sem",
    "para",
    "por",
    "em",
    "e",
    "ou",
    "a",
    "o",
    "un",
    "kit",
    "cj",
    "pc",
    "pç",
    "tipo",
    "novo",
    "nova",
}


def _toks(s: str) -> set[str]:
    t = unicodedata.normalize("NFKD", str(s or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {p for p in re.sub(r"[^A-Z0-9]", " ", t).split() if len(p) > 1 and p.lower() not in _VAZIAS}


def _sim(a: set[str], b: set[str]) -> float:
    """Sobreposição sobre o MENOR conjunto — Jaccard puniria a descrição mais detalhada."""
    return (len(a & b) / min(len(a), len(b))) if a and b else 0.0


async def _ensure_busca(db) -> int:
    """Materializa o tsvector da nomenclatura UMA vez (10.515 linhas), com índice GIN.

    Calcular `to_tsvector` na hora custa ~0,8 s por consulta — o script de 27/08 estourou 590 s
    fazendo isso 736 vezes. Aqui a tabela é da frente (`fin_ncm_busca`), recarregada só quando a
    contagem da nomenclatura muda (carga nova do Siscomex).

    ⭐ **Medido, contra o que a documentação dizia:** quem guarda o CAMINHO hierárquico (capítulo →
    posição → subposição → item) é `ncms.descricao`; `ncms.descricao_resumida` é a folha, e em
    milhares de linhas é literalmente «Outro»/«Outras» (64039190 → «Outro»). Por isso o peso A vai
    para `descricao` e é ela que aparece na tela. O docstring de `carregar_tabela_ncm.py` afirma o
    inverso — está desatualizado em relação ao dado que existe no banco.
    """
    n_ncms = (await db.execute(text("SELECT count(*) FROM ncms WHERE active IS NOT false"))).scalar() or 0
    n_busca = (await db.execute(text("SELECT count(*) FROM fin_ncm_busca"))).scalar() or 0
    if n_ncms and n_busca != n_ncms:
        await db.execute(text("DELETE FROM fin_ncm_busca"))
        await db.execute(
            text(
                """
                INSERT INTO fin_ncm_busca (codigo, descricao_resumida, doc)
                SELECT codigo, coalesce(descricao, descricao_resumida),
                       setweight(to_tsvector('portuguese', unaccent(coalesce(descricao, ''))), 'A')
                    || setweight(to_tsvector('portuguese', unaccent(coalesce(descricao_resumida, ''))), 'B')
                  FROM ncms WHERE active IS NOT false
                ON CONFLICT (codigo) DO NOTHING
                """
            )
        )
        await db.commit()
        n_busca = n_ncms
    return n_busca


async def sugerir_ncm(db, descricao: str, limite: int = 5, ignorar_codigos: set[str] | None = None) -> list[dict]:
    """Candidatos a NCM para uma descrição — **cada um com a fonte declarada**.

    Ordem de força da evidência, a mesma do `sugerir_ncm_produtos.py` (27/08/2026):
      A · **nota de entrada** — `nfe_compras_estoque`: 147 itens que entraram por NF-e de
          fornecedor, com o NCM que ELE declarou num documento que já produziu efeito fiscal.
          A linha diz de qual nota veio.
      B · **cadastro próprio já classificado** — `products` (catálogo importado do Bling, 193 com
          NCM). Coerência interna vale como pista, mas fonte B PROPAGA ERRO: o cadastro dele já
          classificava «Placa de motor portão» como 8704.60.00 («veículos para transporte de
          mercadorias»). Por isso vem depois de A e nunca grava sozinha.
      C · **tabela oficial** — busca textual em português (`to_tsquery` OU entre as palavras +
          `unaccent`, com `ts_rank`) sobre o CAMINHO hierárquico capítulo → posição → subposição
          → item. Sem esse caminho metade da nomenclatura é literalmente «Outros».

    A ordem é A → B → C, e ela foi **medida**, não escolhida por gosto. Acerto do NCM certo entre
    os 5 primeiros, nos 147 itens de compra (ignorando o próprio item como fonte):

        A sozinho .................... 68/147 (46%)
        A + B ........................ 82/147 (56%)
        **A + B + C (esta) ........... 89/147 (61%)**
        C (tabela oficial) sozinho ... 10/147 ( 7%)
        oficial ANTES dos fracos de A  35/147 (24%)  ← tentado e descartado

    Duas coisas que a medição derrubou: pôr a tabela oficial à frente dos casamentos fracos de A
    despenca para 24% (vocabulário fiscal não é vocabulário comercial — «bota» não aparece no
    capítulo 64, que fala em «calçados»); e ler os 209 itens dos XMLs em vez das 147 linhas
    agregadas não muda nada (são os mesmos itens).

    **O teto é estrutural, não de algoritmo**: 71 dos 95 NCMs aparecem UMA vez só em toda a
    casa — tirando o próprio item, não existe segundo documento que os mencione. Ver §1/§5 do
    relatório da frente.

    Nenhum LLM entra aqui: palpite sem fonte é o que vira multa. Quem escolhe é a pessoa.
    """
    alvo = _toks(descricao)
    if not alvo:
        return []
    ignorar = {str(c) for c in (ignorar_codigos or set())}
    fortes: list[tuple[float, dict]] = []
    fracos: list[tuple[float, dict]] = []

    async def _cand(ncm: str, score: float, por_que: str, fonte: str) -> None:
        oficial = await ncm_oficial(db, ncm)
        d = {
            "ncm": ncm,
            "descricao_oficial": (oficial or {}).get("descricao") or (oficial or {}).get("descricao_resumida") or "",
            "score": round(score, 2),
            "fonte": fonte,
            "forte": score >= _CORTE_FORTE,
            "existe_na_tabela_oficial": oficial is not None,
            "por_que": por_que,
        }
        (fortes if d["forte"] else fracos).append((score, d))

    hist = (
        await db.execute(
            text(
                "SELECT e.item_code, e.descricao, e.ncm, coalesce(n.numero, '') numero, "
                "coalesce(n.emitente_nome, '') emitente "
                "FROM nfe_compras_estoque e "
                "LEFT JOIN nfe_entradas n ON n.chave_acesso = e.last_nfe_key "
                "WHERE e.ncm IS NOT NULL AND e.ncm <> '' AND e.descricao IS NOT NULL"
            )
        )
    ).fetchall()
    melhor: dict[str, tuple[float, str]] = {}
    for item_code, desc, ncm, numero, emitente in hist:
        if item_code in ignorar:
            continue
        sc = _sim(alvo, _toks(desc))
        if sc > 0 and sc > melhor.get(ncm, (0.0, ""))[0]:
            melhor[ncm] = (
                sc,
                f"usado em «{str(desc)[:48]}»"
                + (f", NF-e {numero}" if numero else "")
                + (f" de {str(emitente)[:26]}" if emitente else "")
                + f" — semelhança {sc:.2f}",
            )
    for ncm, (sc, porque) in melhor.items():
        await _cand(ncm, sc, porque, "nota_de_entrada")

    cadastro = (
        await db.execute(
            text(
                "SELECT coalesce(name, ''), regexp_replace(coalesce(ncm, ''), '[^0-9]', '', 'g') n, "
                "coalesce(code, '') FROM products "
                "WHERE ncm IS NOT NULL AND length(regexp_replace(ncm, '[^0-9]', '', 'g')) = 8"
            )
        )
    ).fetchall()
    melhor_b: dict[str, tuple[float, str]] = {}
    ja = {d["ncm"] for _, d in [*fortes, *fracos]}
    for nome, ncm, code in cadastro:
        if code in ignorar or ncm in ja:
            continue
        sc = _sim(alvo, _toks(nome))
        if sc > 0 and sc > melhor_b.get(ncm, (0.0, ""))[0]:
            melhor_b[ncm] = (sc, f"produto «{str(nome)[:48]}» do nosso catálogo já usa este NCM — semelhança {sc:.2f}")
    for ncm, (sc, porque) in melhor_b.items():
        await _cand(ncm, sc, porque, "cadastro_proprio")

    total = await _ensure_busca(db)
    vistos = {d["ncm"] for _, d in [*fortes, *fracos]}
    oficiais: list[dict] = []
    consulta = " | ".join(sorted(alvo))
    rows = (
        await db.execute(
            text(
                "SELECT codigo, descricao_resumida AS caminho, "
                "ts_rank(doc, to_tsquery('portuguese', unaccent(:q))) r "
                "FROM fin_ncm_busca WHERE doc @@ to_tsquery('portuguese', unaccent(:q)) "
                "ORDER BY r DESC, codigo LIMIT :n"
            ),
            {"q": consulta, "n": limite * 4},
        )
    ).fetchall()
    for codigo, dresc, rank in rows:
        if codigo in vistos:
            continue
        vistos.add(codigo)
        oficiais.append(
            {
                "ncm": codigo,
                "descricao_oficial": dresc or "",
                "score": round(float(rank or 0), 4),
                "fonte": "tabela_oficial",
                "forte": False,
                "existe_na_tabela_oficial": True,
                "por_que": (
                    f"tabela oficial ({total} códigos), busca em português por «{consulta}» — "
                    f"relevância {float(rank or 0):.4f}. Ponto de partida, NÃO classificação."
                ),
            }
        )

    def _ord(fonte: str) -> list[dict]:
        return [d for _, d in sorted([*fortes, *fracos], key=lambda x: -x[0]) if d["fonte"] == fonte]

    return (_ord("nota_de_entrada") + _ord("cadastro_proprio") + oficiais)[:limite]


async def aplicar_ncm_sugerido(db, produto_id: int, ncm: str, fonte: str, usuario: str) -> dict:
    """Grava a sugestão ACEITA por uma pessoa — com `origem_cadastro='sugerido'` para auditar."""
    await _ensure(db)
    oficial = await validar_ncm(db, ncm)
    r = await db.execute(
        text(
            "UPDATE fin_produtos SET ncm = :n, origem_cadastro = 'sugerido', atualizado_em = now(), "
            "observacao = coalesce(observacao || ' · ', '') || :obs WHERE id = :i"
        ),
        {
            "n": oficial["codigo"],
            "i": int(produto_id),
            "obs": (
                f"NCM {oficial['codigo']} sugerido pela descrição e ACEITO por {usuario} em "
                f"{date.today():%d/%m/%Y} — fonte: {str(fonte or 'não declarada')[:180]}"
            ),
        },
    )
    if not r.rowcount:
        raise HTTPException(status_code=404, detail=f"Produto {produto_id} não encontrado.")
    await db.commit()
    return {"produto_id": int(produto_id), "ncm": oficial["codigo"]}


# ----------------------------------------------------------------------------- NCM


async def ncm_oficial(db, ncm: str) -> dict | None:
    """A linha da nomenclatura oficial, se o código existir E estiver vigente hoje."""
    cod = _dig(ncm)
    if len(cod) != 8:
        return None
    r = (
        (
            await db.execute(
                text(
                    "SELECT codigo, descricao, descricao_resumida, valid_from, valid_until, active "
                    "FROM ncms WHERE codigo = :c"
                ),
                {"c": cod},
            )
        )
        .mappings()
        .first()
    )
    if not r:
        return None
    hoje = date.today()
    if r["valid_from"] and hoje < r["valid_from"]:
        return None
    if r["valid_until"] and hoje > r["valid_until"]:
        return None
    if r["active"] is False:
        return None
    return dict(r)


async def validar_ncm(db, ncm: str) -> dict:
    """Recusa com 422 e a MESMA frase que a SEFAZ deu. É a mordida da frente.

    Sem tabela oficial carregada isto seria teatro: por isso, se `ncms` estiver vazia, falha
    dizendo que a tabela não está carregada — nunca deixa passar calado.
    """
    cod = _dig(ncm)
    if len(cod) != 8:
        raise HTTPException(
            status_code=422,
            detail=f"{MSG_NCM_INEXISTENTE} — o NCM tem 8 dígitos numéricos; informado «{ncm}».",
        )
    total = (await db.execute(text("SELECT count(*) FROM ncms"))).scalar() or 0
    if total == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "Tabela oficial de NCM vazia — carregue-a antes de cadastrar produto: "
                "scripts/orq/carregar_tabela_ncm.py (Portal Único Siscomex)."
            ),
        )
    achado = await ncm_oficial(db, cod)
    if not achado:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{MSG_NCM_INEXISTENTE} — «{cod}» não consta na nomenclatura vigente "
                f"({total} códigos). Consulte a aba «Consultar NCM oficial»."
            ),
        )
    return achado


async def buscar_ncm(db, termo: str, limite: int = 30) -> list[dict]:
    """Busca na nomenclatura por código ou por qualquer palavra do caminho hierárquico.

    `descricao_resumida` guarda capítulo → posição → subposição → item; sem ele a busca por
    «capacete» não acharia nada (metade da tabela é literalmente «Outros»).
    """
    termo = (termo or "").strip()
    if not termo:
        return []
    cod = _dig(termo)
    if len(cod) >= 4 and cod == termo.replace(".", "").replace(" ", ""):
        sql = "SELECT codigo, coalesce(descricao_resumida, descricao) d FROM ncms WHERE codigo LIKE :p ORDER BY codigo LIMIT :n"
        params = {"p": f"{cod}%", "n": limite}
    else:
        sql = (
            "SELECT codigo, coalesce(descricao, descricao_resumida) d FROM ncms "
            "WHERE unaccent(lower(coalesce(descricao, descricao_resumida))) LIKE unaccent(lower(:p)) "
            "ORDER BY codigo LIMIT :n"
        )
        params = {"p": f"%{termo}%", "n": limite}
    try:
        rows = (await db.execute(text(sql), params)).fetchall()
    except Exception:  # noqa: BLE001 — sem extensão unaccent: cai para LIKE simples
        await db.rollback()
        rows = (
            await db.execute(
                text(
                    "SELECT codigo, coalesce(descricao, descricao_resumida) d FROM ncms "
                    "WHERE lower(coalesce(descricao, descricao_resumida)) LIKE lower(:p) ORDER BY codigo LIMIT :n"
                ),
                params,
            )
        ).fetchall()
    return [{"codigo": r[0], "descricao": r[1]} for r in rows]


# ----------------------------------------------------------------- pronto para emitir


def faltas_produto(p: dict) -> list[str]:
    """O que falta no CADASTRO para o item sair numa NF-e (layout 4.00, grupo `prod`)."""
    f: list[str] = []
    if not (p.get("ncm") or "").strip():
        f.append("NCM")
    if not (p.get("unidade_comercial") or "").strip():
        f.append("unidade comercial")
    if not (p.get("unidade_tributavel") or "").strip():
        f.append("unidade tributável")
    if not (p.get("ean") or "").strip():
        f.append("GTIN (use «SEM GTIN» quando não houver)")
    if not (p.get("origem") or "").strip():
        f.append("origem da mercadoria (0-8)")
    if not (p.get("cfop_padrao_dentro_uf") or "").strip():
        f.append("CFOP dentro do estado")
    if not (p.get("cfop_padrao_fora_uf") or "").strip():
        f.append("CFOP fora do estado")
    return f


def faltas_tributacao(regime: str, trib: dict | None) -> list[str]:
    """O que falta no grupo `imposto` — e o que falta depende do REGIME da empresa."""
    if not trib:
        return ["tributação não cadastrada para esta empresa"]
    f: list[str] = []
    if (regime or "") == "simples_nacional":
        if not (trib.get("csosn") or "").strip():
            f.append("CSOSN")
    elif not (trib.get("cst_icms") or "").strip():
        f.append("CST de ICMS")
    if not (trib.get("cst_pis") or "").strip():
        f.append("CST de PIS")
    if not (trib.get("cst_cofins") or "").strip():
        f.append("CST de COFINS")
    return f


# ----------------------------------------------------------------------------- seed


def _itens_do_xml(xml: str) -> dict[str, dict]:
    """cProd → o que o FORNECEDOR declarou no item. Só leitura de documento fiscal."""
    out: dict[str, dict] = {}
    try:
        raiz = _xml(xml)
    except Exception:  # noqa: BLE001 — XML corrompido de fornecedor não derruba o seed
        return out
    for det in raiz.iter():
        if not det.tag.endswith("}det") and det.tag != "det":
            continue
        prod = next((c for c in det if c.tag.endswith("prod")), None)
        if prod is None:
            continue
        campos = {c.tag.split("}")[-1]: (c.text or "").strip() for c in prod}
        cprod = campos.get("cProd")
        if not cprod:
            continue
        orig = ""
        for no in det.iter():
            if no.tag.split("}")[-1] == "orig":
                orig = (no.text or "").strip()
                break
        out[cprod] = {
            "ean": campos.get("cEAN") or "",
            "ucom": campos.get("uCom") or "",
            "utrib": campos.get("uTrib") or campos.get("uCom") or "",
            "cest": campos.get("CEST") or "",
            "orig": orig,
            "xprod": campos.get("xProd") or "",
        }
    return out


async def _mapa_xml(db) -> dict[str, dict]:
    rows = (
        await db.execute(text("SELECT xml_raw FROM nfe_entradas WHERE xml_raw IS NOT NULL AND length(xml_raw) > 500"))
    ).fetchall()
    mapa: dict[str, dict] = {}
    for (xml,) in rows:
        for k, v in _itens_do_xml(xml).items():
            mapa.setdefault(k, v)
    return mapa


async def semear(db) -> dict:
    """Um produto por NCM distinto das compras — descrição, unidade e origem do documento.

    Idempotente (`ON CONFLICT (codigo) DO NOTHING`). CFOP e CST **não** entram: nascem NULL.
    NCM que não existe na tabela oficial nasce INATIVO com o motivo escrito.
    """
    await _ensure(db)
    ja = (await db.execute(text("SELECT count(*) FROM fin_produtos WHERE origem_cadastro = 'nfe_entrada'"))).scalar()
    mapa = await _mapa_xml(db) if not ja else {}
    # representante por NCM: o item de menor id (a primeira nota que trouxe aquele NCM)
    reps = (
        await db.execute(
            text(
                "SELECT DISTINCT ON (e.ncm) e.ncm, e.item_code, e.descricao, e.unidade "
                "FROM nfe_compras_estoque e WHERE e.ncm IS NOT NULL AND e.ncm <> '' "
                "ORDER BY e.ncm, e.id"
            )
        )
    ).fetchall()
    criados = 0
    for ncm, item_code, descricao, unidade in reps:
        x = mapa.get(item_code, {})
        oficial = await ncm_oficial(db, ncm)
        motivo = (
            None
            if oficial
            else (
                f"{MSG_NCM_INEXISTENTE} — «{ncm}» veio da NF-e do fornecedor mas não consta na "
                "nomenclatura vigente. Classificar com o contador antes de ativar; não foi "
                "corrigido por inferência."
            )
        )
        r = await db.execute(
            text(
                """
                INSERT INTO fin_produtos
                  (codigo, descricao, ncm, cest, origem, unidade_comercial, unidade_tributavel, ean,
                   ativo, motivo_inativo, origem_cadastro, observacao)
                VALUES
                  (:cod, :desc, :ncm, :cest, :orig, :ucom, :utrib, :ean,
                   :ativo, :motivo, 'nfe_entrada', :obs)
                ON CONFLICT (codigo) DO NOTHING
                RETURNING id
                """
            ),
            {
                "cod": item_code,
                "desc": (x.get("xprod") or descricao or item_code)[:200],
                "ncm": _dig(ncm)[:8],
                "cest": (x.get("cest") or None),
                "orig": (x.get("orig") or None),
                "ucom": (x.get("ucom") or unidade or None),
                "utrib": (x.get("utrib") or unidade or None),
                "ean": (x.get("ean") or "SEM GTIN"),
                "ativo": oficial is not None,
                "motivo": motivo,
                "obs": "Semeado da NF-e de entrada do fornecedor (nfe_compras_estoque + XML em nfe_entradas).",
            },
        )
        if r.scalar():
            criados += 1
    await db.commit()
    tribs = await semear_tributacao(db)
    return {"produtos_criados": criados, "ncms_das_compras": len(reps), **tribs}


async def semear_tributacao(db) -> dict:
    """Uma linha por produto × empresa, com `origem_regra` dizendo de onde veio o regime.

    Campos de imposto ficam NULL de propósito: quem preenche é gente, e o preenchimento em lote
    (`aplicar_padrao_regime`) carimba quem/quando/fundamento em `origem_regra`.
    """
    emps = await empresas(db)
    n = 0
    for e in emps:
        r = await db.execute(
            text(
                """
                INSERT INTO fin_produto_tributacao (produto_id, empresa_cnpj, origem_regra)
                SELECT p.id, :cnpj, :regra FROM fin_produtos p
                ON CONFLICT (produto_id, empresa_cnpj) DO NOTHING
                """
            ),
            {
                "cnpj": e["cnpj"],
                "regra": (
                    f"Regime «{e['regime_tributario']}» lido de `empresas` (CNPJ {e['cnpj']}, "
                    f"{e['razao_social']}). CST/CSOSN e alíquotas NÃO foram preenchidos: aguardam "
                    "confirmação do contador — nada aqui nasce por inferência."
                ),
            },
        )
        n += r.rowcount or 0
    await db.commit()
    return {"tributacoes_criadas": n}


# ----------------------------------------------------------------------------- leitura


async def empresas(db) -> list[dict]:
    rows = (
        (
            await db.execute(
                text(
                    "SELECT cnpj, razao_social, regime_tributario, coalesce(inscricao_suframa,'') suframa "
                    "FROM empresas WHERE cnpj IS NOT NULL ORDER BY razao_social"
                )
            )
        )
        .mappings()
        .fetchall()
    )
    return [dict(r) for r in rows]


async def listar(db) -> list[dict]:
    """Produtos + tributação por empresa + o que falta para emitir em cada uma."""
    emps = {e["cnpj"]: e for e in await empresas(db)}
    prods = (
        (
            await db.execute(
                text(
                    "SELECT p.*, n.codigo IS NOT NULL AS ncm_oficial, "
                    "coalesce(n.descricao, n.descricao_resumida, '') AS ncm_descricao "
                    "FROM fin_produtos p LEFT JOIN ncms n ON n.codigo = p.ncm "
                    "ORDER BY p.ativo DESC, p.descricao"
                )
            )
        )
        .mappings()
        .fetchall()
    )
    tribs: dict[int, dict[str, dict]] = {}
    for r in (await db.execute(text("SELECT * FROM fin_produto_tributacao"))).mappings().fetchall():
        tribs.setdefault(r["produto_id"], {})[r["empresa_cnpj"]] = dict(r)
    saida = []
    for p in prods:
        d = dict(p)
        fp = faltas_produto(d)
        if not d["ncm_oficial"] and (d.get("ncm") or ""):
            fp.append(f"NCM «{d['ncm']}» não existe na tabela oficial")
        d["faltas_produto"] = fp
        d["empresas"] = {}
        for cnpj, e in emps.items():
            t = (tribs.get(d["id"]) or {}).get(cnpj)
            ft = faltas_tributacao(e["regime_tributario"], t)
            d["empresas"][cnpj] = {
                "razao_social": e["razao_social"],
                "regime": e["regime_tributario"],
                "trib": t,
                "faltas": ft,
                "pronto": bool(d["ativo"]) and not fp and not ft,
            }
        d["pronto"] = all(v["pronto"] for v in d["empresas"].values()) if d["empresas"] else False
        saida.append(d)
    return saida


# ----------------------------------------------------------------------------- escrita


_CAMPOS_PRODUTO = (
    "descricao",
    "ncm",
    "cest",
    "origem",
    "unidade_comercial",
    "unidade_tributavel",
    "ean",
    "peso_liquido",
    "peso_bruto",
    "cfop_padrao_dentro_uf",
    "cfop_padrao_fora_uf",
    "observacao",
)
_NUM = {"peso_liquido", "peso_bruto"}


#: CFOP de SAÍDA: 5xxx é operação dentro do estado, 6xxx para outro estado (Ajuste SINIEF 07/01).
#: Trocar os dois é rejeição na hora — por isso cada campo exige o seu primeiro dígito.
_CFOP_PREFIXO = {"cfop_padrao_dentro_uf": ("5", "dentro do estado"), "cfop_padrao_fora_uf": ("6", "para outro estado")}


def _cfop(v: str, campo: str) -> str | None:
    v = _dig(v)
    if not v:
        return None
    pref, onde = _CFOP_PREFIXO[campo]
    if len(v) != 4 or not v.startswith(pref):
        raise HTTPException(
            status_code=422,
            detail=f"CFOP {onde} tem 4 dígitos e começa em {pref} (informado «{v}»).",
        )
    return v


async def salvar_produto(db, dados: dict, usuario: str) -> dict:
    """Cria ou edita. NCM inválido é recusado com 422 — a mesma frase da SEFAZ."""
    await _ensure(db)
    pid = str(dados.get("id") or "").strip()
    campos: dict = {}
    for k in _CAMPOS_PRODUTO:
        if k not in dados:
            continue
        v = dados.get(k)
        v = None if v is None or str(v).strip() == "" else str(v).strip()
        if k in _NUM and v is not None:
            try:
                v = str(float(v.replace(",", ".")))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"{k}: número inválido «{dados.get(k)}».") from exc
        campos[k] = v
    if "ncm" in campos and campos["ncm"]:
        oficial = await validar_ncm(db, campos["ncm"])
        campos["ncm"] = oficial["codigo"]
    if "origem" in campos and campos["origem"] and campos["origem"] not in ORIGENS:
        raise HTTPException(
            status_code=422, detail="Origem da mercadoria deve ser um dígito de 0 a 8 (tabela A do CST)."
        )
    for k in ("cfop_padrao_dentro_uf", "cfop_padrao_fora_uf"):
        if k in campos:
            campos[k] = _cfop(campos.get(k) or "", k)
    ativo = dados.get("ativo")
    if pid:
        if not campos and ativo is None:
            raise HTTPException(status_code=422, detail="Nada para salvar.")
        if str(ativo or "") in ("1", "true", "True"):
            atual = (await db.execute(text("SELECT ncm FROM fin_produtos WHERE id = :i"), {"i": int(pid)})).scalar()
            await validar_ncm(db, campos.get("ncm") or atual or "")
            campos["ativo"] = True
            campos["motivo_inativo"] = None
        elif str(ativo or "") in ("0", "false", "False"):
            campos["ativo"] = False
            campos["motivo_inativo"] = f"Inativado por {usuario} em {date.today():%d/%m/%Y}."
        sets = ", ".join(f"{k} = :{k}" for k in campos)
        await db.execute(
            text(f"UPDATE fin_produtos SET {sets}, atualizado_em = now() WHERE id = :id"),
            {**campos, "id": int(pid)},
        )
        await db.commit()
        return {"id": int(pid), "acao": "editado"}
    if not (campos.get("descricao") or "").strip():
        raise HTTPException(status_code=422, detail="Descrição é obrigatória.")
    if not campos.get("ncm"):
        raise HTTPException(status_code=422, detail=f"{MSG_NCM_INEXISTENTE} — o NCM é obrigatório para emitir NF-e.")
    codigo = str(dados.get("codigo") or "").strip()
    if not codigo:
        n = (
            await db.execute(text("SELECT count(*) FROM fin_produtos WHERE ncm = :n"), {"n": campos["ncm"]})
        ).scalar() or 0
        codigo = f"NCM{campos['ncm']}-{n + 1}"
    campos.setdefault("ean", "SEM GTIN")
    cols = ["codigo", "origem_cadastro", *campos.keys()]
    vals = {"codigo": codigo, "origem_cadastro": "manual", **campos}
    novo = (
        await db.execute(
            text(
                f"INSERT INTO fin_produtos ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) "
                "ON CONFLICT (codigo) DO NOTHING RETURNING id"
            ),
            vals,
        )
    ).scalar()
    if not novo:
        raise HTTPException(status_code=422, detail=f"Já existe produto com o código «{codigo}».")
    await semear_tributacao(db)
    await db.commit()
    return {"id": novo, "codigo": codigo, "acao": "criado"}


_CAMPOS_TRIB = (
    "cst_icms",
    "csosn",
    "aliquota_icms",
    "cst_pis",
    "aliquota_pis",
    "cst_cofins",
    "aliquota_cofins",
    "cst_ipi",
    "aliquota_ipi",
)


async def salvar_tributacao(db, dados: dict, usuario: str) -> dict:
    await _ensure(db)
    pid = int(str(dados.get("produto_id") or "0") or 0)
    cnpj = str(dados.get("empresa_cnpj") or "").strip()
    if not pid or not cnpj:
        raise HTTPException(status_code=422, detail="Produto e empresa são obrigatórios.")
    emps = {e["cnpj"]: e for e in await empresas(db)}
    if cnpj not in emps:
        raise HTTPException(status_code=422, detail=f"CNPJ «{cnpj}» não é uma empresa do grupo.")
    campos: dict = {}
    for k in _CAMPOS_TRIB:
        if k not in dados:
            continue
        v = dados.get(k)
        v = None if v is None or str(v).strip() == "" else str(v).strip()
        if k.startswith("aliquota") and v is not None:
            try:
                v = str(float(v.replace(",", ".")))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"{k}: número inválido «{dados.get(k)}».") from exc
        campos[k] = v
    if not campos:
        raise HTTPException(status_code=422, detail="Nada para salvar.")
    regra = str(dados.get("origem_regra") or "").strip()
    if not regra:
        raise HTTPException(
            status_code=422,
            detail="«De onde veio a regra» é obrigatório — CST sem fundamento escrito é chute, e chute vira multa.",
        )
    campos["origem_regra"] = f"{regra} · gravado por {usuario} em {date.today():%d/%m/%Y}"
    sets = ", ".join(f"{k} = :{k}" for k in campos)
    r = await db.execute(
        text(
            f"UPDATE fin_produto_tributacao SET {sets}, atualizado_em = now() "
            "WHERE produto_id = :p AND empresa_cnpj = :c"
        ),
        {**campos, "p": pid, "c": cnpj},
    )
    if not r.rowcount:
        await db.execute(
            text(
                "INSERT INTO fin_produto_tributacao (produto_id, empresa_cnpj, origem_regra) "
                "VALUES (:p, :c, :regra) ON CONFLICT (produto_id, empresa_cnpj) DO NOTHING"
            ),
            {"p": pid, "c": cnpj, "regra": campos["origem_regra"]},
        )
        await db.execute(
            text(f"UPDATE fin_produto_tributacao SET {sets} WHERE produto_id = :p AND empresa_cnpj = :c"),
            {**campos, "p": pid, "c": cnpj},
        )
    await db.commit()
    return {"produto_id": pid, "empresa_cnpj": cnpj}


async def aplicar_padrao_regime(db, cnpj: str, usuario: str) -> dict:
    """Preenche em lote o CST/CSOSN padrão do regime — ATO DE UMA PESSOA, com fundamento.

    Só toca linhas ainda vazias (nunca sobrescreve o que alguém já decidiu) e carimba quem,
    quando e a lei em `origem_regra`. ICMS **não** entra: a alíquota depende da UF de destino e
    do benefício (ZFM/SUFRAMA), e isso é caso a caso — fica NULL e a tela continua acusando.
    """
    await _ensure(db)
    emps = {e["cnpj"]: e for e in await empresas(db)}
    e = emps.get(str(cnpj or "").strip())
    if not e:
        raise HTTPException(status_code=422, detail=f"CNPJ «{cnpj}» não é uma empresa do grupo.")
    padrao = PADRAO_REGIME.get(e["regime_tributario"])
    if not padrao:
        raise HTTPException(
            status_code=422,
            detail=f"Regime «{e['regime_tributario']}» sem padrão declarado — preencha produto a produto.",
        )
    campos = {k: v for k, v in padrao.items() if k != "fundamento"}
    regra = (
        f"Padrão do regime aplicado em lote por {usuario} em {date.today():%d/%m/%Y}: "
        f"{padrao['fundamento']}. Confirmar produto a produto com o contador — o ICMS não foi "
        "preenchido (depende da UF de destino e do benefício ZFM/SUFRAMA)."
    )
    sets = ", ".join(f"{k} = coalesce({k}, :{k})" for k in campos)
    cond = " OR ".join(f"{k} IS NULL" for k in campos)
    r = await db.execute(
        text(
            f"UPDATE fin_produto_tributacao SET {sets}, origem_regra = :regra, atualizado_em = now() "
            f"WHERE empresa_cnpj = :c AND ({cond})"
        ),
        {**campos, "regra": regra, "c": e["cnpj"]},
    )
    await db.commit()
    return {"linhas": r.rowcount or 0, "empresa": e["razao_social"], "fundamento": padrao["fundamento"]}


async def resumo(db) -> dict:
    """Os números do §1: quantos NCMs das compras passam, quantos produtos prontos."""
    await _ensure(db)
    prods = await listar(db)
    emps = await empresas(db)
    ncm_compras = (
        await db.execute(
            text("SELECT count(DISTINCT ncm) FROM nfe_compras_estoque WHERE ncm IS NOT NULL AND ncm <> ''")
        )
    ).scalar() or 0
    ncm_ok = (
        await db.execute(
            text("SELECT count(DISTINCT e.ncm) FROM nfe_compras_estoque e JOIN ncms n ON n.codigo = e.ncm")
        )
    ).scalar() or 0
    return {
        "produtos": len(prods),
        "ativos": sum(1 for p in prods if p["ativo"]),
        "prontos": sum(1 for p in prods if p["pronto"]),
        "prontos_por_empresa": {
            e["cnpj"]: sum(1 for p in prods if p["empresas"].get(e["cnpj"], {}).get("pronto")) for e in emps
        },
        "ncm_compras": ncm_compras,
        "ncm_compras_oficiais": ncm_ok,
        "ncms_carregados": (await db.execute(text("SELECT count(*) FROM ncms"))).scalar() or 0,
    }
