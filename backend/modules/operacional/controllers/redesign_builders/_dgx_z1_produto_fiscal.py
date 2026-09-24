"""DGX Z1 — Cadastro fiscal do produto: sem ele a NF-e é rejeitada (24/09/2026).

O dono: *«preciso urgente emitir notas fiscais»*. O sistema tem DUAS tentativas de NF-e de saída,
ambas de 11/04/2026, ambas rejeitadas — a última com **«Rejeição: Informado NCM inexistente
[nItem: 1]»**. A regra e a medição moram em `financial/services/produto_fiscal.py` (docstring lá:
o que foi cavado, por que duas tabelas, por que nada nasce preenchido). Aqui só tela e ação.

**Por que no módulo Fiscal e não em Suprimentos:** o cadastro existe para EMITIR, e quem emite
mora aqui — `fiscal.py` já tem o grupo «Notas fiscais» com «NFS-e nacional — emitir DPS»,
«Importar XML de NF-e de compra» e «NFS-e emitidas». Em Suprimentos o mesmo produto aparece como
ESTOQUE (`materiais`/`almoxarifado`, da F9), que é outra pergunta. O elo entre os dois é o
`codigo` (= `nfe_compras_estoque.item_code`), e a tela diz isso.

Prefixo `_` = o discovery pula; `fiscal.py` importa `router`/`MENU` no topo e chama
`telas(db, out)` no fim do `build()`. DDL idempotente em `produto_fiscal._ensure`.

**Não toca o emissor de NF-e** (`fiscal_contabil/notas_fiscais/nfe/`, `integrations/nfe_provider.py`)
— ligar o cadastro na emissão é a frente Z2.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (o ciclo de import fecha com o router pronto) — igual F1/V5.
router = APIRouter()

from modules.financial.services import produto_fiscal as pf  # noqa: E402
from modules.operacional.controllers.redesign_data_controller import b, t  # noqa: E402

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_ICO = "M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"

ABAS = [
    ("produtos-fiscais", "Produtos fiscais (NF-e)"),
    ("produto-fiscal-novo", "Novo produto fiscal"),
    ("produto-tributacao", "Tributação por empresa"),
    ("ncm-consulta", "NCM em uso"),
    ("ncm-sugerir", "Sugerir NCM pela descrição"),
    ("ncm-aplicar", "Aplicar NCM sugerido"),
    ("produto-tributacao-lote", "Tributação — padrão do regime"),
]
MENU: list[dict] = [{"id": i, "label": r, "icon": _ICO, "grupo": "Notas fiscais"} for i, r in ABAS]

_OPC_ORIGEM = [{"value": k, "label": v} for k, v in pf.ORIGENS.items()]
#: Rótulo humano da fonte de cada sugestão de NCM. Sugestão sem fonte não sai daqui.
_ROTULO_FONTE = {
    "nota_de_entrada": "nota do fornecedor",
    "cadastro_proprio": "nosso catálogo",
    "tabela_oficial": "tabela oficial",
}


def _curto(cnpj: str, razao: str) -> str:
    r = (razao or "").upper()
    if "ELETRON" in r:
        return "Eletrônica"
    if "PATRIMON" in r:
        return "Patrimonial"
    return (razao or cnpj)[:18]


def _campos_produto(p: dict | None = None) -> list[dict]:
    p = p or {}
    v = lambda k: (p.get(k) if p.get(k) is not None else "")  # noqa: E731
    return [
        {
            "key": "descricao",
            "label": "Descrição do produto*",
            "type": "text",
            "span": "span 2",
            "value": v("descricao"),
        },
        {
            "key": "ncm",
            "label": "NCM (8 dígitos)*",
            "type": "text",
            "span": "span 1",
            "value": v("ncm"),
            "ph": "recusado se não existir na tabela oficial",
        },
        {"key": "cest", "label": "CEST (só se houver ST)", "type": "text", "span": "span 1", "value": v("cest")},
        {
            "key": "origem",
            "label": "Origem da mercadoria*",
            "type": "select",
            "span": "span 2",
            "value": v("origem"),
            "options": _OPC_ORIGEM,
        },
        {
            "key": "unidade_comercial",
            "label": "Unidade comercial*",
            "type": "text",
            "span": "span 1",
            "value": v("unidade_comercial"),
            "ph": "UN, PR, CX…",
        },
        {
            "key": "unidade_tributavel",
            "label": "Unidade tributável*",
            "type": "text",
            "span": "span 1",
            "value": v("unidade_tributavel"),
        },
        {
            "key": "ean",
            "label": "GTIN/EAN*",
            "type": "text",
            "span": "span 1",
            "value": v("ean") or "SEM GTIN",
            "ph": "SEM GTIN quando não houver",
        },
        {
            "key": "cfop_padrao_dentro_uf",
            "label": "CFOP dentro do estado* (5xxx)",
            "type": "text",
            "span": "span 1",
            "value": v("cfop_padrao_dentro_uf"),
            "ph": "5102 = venda de mercadoria de terceiros",
        },
        {
            "key": "cfop_padrao_fora_uf",
            "label": "CFOP para outro estado* (6xxx)",
            "type": "text",
            "span": "span 1",
            "value": v("cfop_padrao_fora_uf"),
            "ph": "6102",
        },
        {
            "key": "peso_liquido",
            "label": "Peso líquido (kg)",
            "type": "text",
            "span": "span 1",
            "value": v("peso_liquido"),
        },
        {"key": "peso_bruto", "label": "Peso bruto (kg)", "type": "text", "span": "span 1", "value": v("peso_bruto")},
        {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2", "value": v("observacao")},
    ]


async def _tela_produtos(db) -> dict:
    prods = await pf.listar(db)
    res = await pf.resumo(db)
    emps = await pf.empresas(db)
    curtos = {e["cnpj"]: _curto(e["cnpj"], e["razao_social"]) for e in emps}
    rows = []
    for p in prods:
        faltas_por_emp = []
        for cnpj, e in (p.get("empresas") or {}).items():
            if e["pronto"]:
                continue
            f = list(e["faltas"])
            if f:
                faltas_por_emp.append(f"{curtos.get(cnpj, cnpj)}: {', '.join(f)}")
        tudo = list(p["faltas_produto"]) + faltas_por_emp
        if not p["ativo"]:
            pronto = b("inativo", "mut")
        elif p["pronto"]:
            pronto = b("sim", "ok")
        elif any(e["pronto"] for e in (p.get("empresas") or {}).values()):
            pronto = b("só em uma empresa", "warn")
        else:
            pronto = b("não", "bad")
        rows.append(
            {
                "cells": [
                    t(str(p["codigo"])[:18], 600, _ND),
                    t(str(p["descricao"])[:52]),
                    t(str(p["ncm"] or "—")),
                    b("oficial", "ok") if p["ncm_oficial"] else b("NÃO consta", "bad"),
                    t(str(p["ncm_descricao"] or "—")[:70]),
                    t(f"{p['unidade_comercial'] or '—'} / {p['unidade_tributavel'] or '—'}"),
                    t(str(p["origem"] or "—")),
                    t(f"{p['cfop_padrao_dentro_uf'] or '—'} / {p['cfop_padrao_fora_uf'] or '—'}"),
                    pronto,
                    t((" · ".join(tudo) or p["motivo_inativo"] or "—")[:220]),
                    b(str(p["origem_cadastro"]), "info"),
                ],
                "filtros": {
                    "Pronto para emitir": ("inativo" if not p["ativo"] else ("sim" if p["pronto"] else "não")),
                    "NCM oficial": "sim" if p["ncm_oficial"] else "não",
                    "Origem do cadastro": str(p["origem_cadastro"]),
                },
                "edit": {
                    "endpoint": f"{_ACT}produto-fiscal-salvar",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "okMsg": "Produto salvo. Recarregue a aba.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(p["id"]), "span": "span 1"},
                        *_campos_produto(p),
                    ],
                },
                "actions": [
                    {
                        "title": ("Inativar" if p["ativo"] else "Ativar") + f" «{str(p['descricao'])[:36]}»",
                        "endpoint": f"{_ACT}produto-fiscal-salvar",
                        "method": "POST",
                        "btnLabel": "Inativar" if p["ativo"] else "Ativar",
                        "btnStyle": "outline",
                        "submitLabel": "Confirmar",
                        "okMsg": "Feito. Recarregue a aba.",
                        "fields": [
                            {"key": "id", "label": "id", "type": "text", "value": str(p["id"]), "span": "span 1"},
                            {
                                "key": "ativo",
                                "label": "ativo",
                                "type": "text",
                                "value": "0" if p["ativo"] else "1",
                                "span": "span 1",
                            },
                        ],
                    },
                    {
                        "title": f"Sugerir NCM pela descrição de «{str(p['descricao'])[:36]}»",
                        "endpoint": f"{_ACT}ncm-sugerir",
                        "method": "POST",
                        "btnLabel": "Sugerir NCM",
                        "btnStyle": "outline",
                        "submitLabel": "Buscar candidatos",
                        "okMsg": "Candidatos abaixo — cada um com a fonte. Escolha e aplique na aba «Sugerir NCM».",
                        "showResult": True,
                        "fields": [
                            {
                                "key": "produto_id",
                                "label": "id",
                                "type": "text",
                                "value": str(p["id"]),
                                "span": "span 1",
                            },
                            {
                                "key": "descricao",
                                "label": "Descrição",
                                "type": "text",
                                "value": str(p["descricao"]),
                                "span": "span 2",
                            },
                        ],
                    },
                ],
            }
        )
    por_emp = " · ".join(
        f"{curtos.get(c, c)}: {n} pronto(s)" for c, n in (res.get("prontos_por_empresa") or {}).items()
    )
    return {
        "title": "Produtos fiscais (NF-e)",
        "sub": (
            f"**{res['produtos']} produto(s)**, {res['ativos']} ativo(s) · **{res['prontos']} pronto(s) para emitir "
            f"nas DUAS empresas** ({por_emp}). "
            f"Semeado das compras reais: {res['ncm_compras']} NCM(s) distintos em `nfe_compras_estoque`, "
            f"{res['ncm_compras_oficiais']} deles existem na tabela oficial ({res['ncms_carregados']} códigos "
            "carregados do Portal Único Siscomex). "
            "O que falta em cada linha está escrito: **CFOP e CST nascem vazios de propósito** — NCM ou CST "
            "chutado é multa e glosa de crédito, e quem classifica é gente. "
            "O código é o mesmo `item_code` do estoque (Suprimentos → Materiais), então o produto fiscal e o "
            "saldo falam do mesmo item. "
            "Esta tela **não emite nota** e não toca o emissor — é cadastro."
        ),
        "cta": "Novo produto",
        "ctaTo": "produto-fiscal-novo",
        "type": "table",
        "searchHint": "Descrição, NCM, código…",
        "filtros": [
            {"key": "Pronto para emitir", "label": "Pronto para emitir"},
            {"key": "NCM oficial", "label": "NCM oficial"},
            {"key": "Origem do cadastro", "label": "Origem do cadastro"},
        ],
        "grid": "0.9fr 2.2fr 0.8fr 0.8fr 2.4fr 0.9fr 0.5fr 0.9fr 0.9fr 2.6fr 0.8fr",
        "cols": [
            "Código",
            "Descrição",
            "NCM",
            "Na tabela oficial?",
            "O que a nomenclatura diz",
            "Un. com./trib.",
            "Orig.",
            "CFOP dentro/fora",
            "Pronto para emitir?",
            "O que falta",
            "Origem do cadastro",
        ],
        "rows": rows,
    }


def _tela_novo() -> dict:
    return {
        "title": "Novo produto fiscal",
        "sub": (
            "O NCM é **validado contra a tabela oficial** (`ncms`, Portal Único Siscomex): código que não existe "
            "é recusado com a mesma frase que a SEFAZ deu na nota 2 de 11/04/2026 — "
            f"«{pf.MSG_NCM_INEXISTENTE}». Não sabe o NCM? Use a aba «Sugerir NCM pela descrição». "
            "CFOP dentro do estado começa em 5 e para outro estado em 6 (Ajuste SINIEF 07/01) — trocar os dois é "
            "rejeição na hora. A tributação (CST/CSOSN) é cadastrada depois, na aba «Tributação por empresa», "
            "porque a mesma mercadoria tem tributação diferente nos dois CNPJs."
        ),
        "cta": "Salvar",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "produto-fiscal-salvar",
            "okMsg": "Produto criado. A tributação das duas empresas nasceu junto, vazia — preencha na aba «Tributação por empresa».",
            "showResult": True,
        },
        "fields": [
            {
                "key": "codigo",
                "label": "Código interno",
                "type": "text",
                "span": "span 1",
                "ph": "em branco = gerado a partir do NCM",
            },
            *_campos_produto(),
        ],
    }


async def _tela_tributacao(db) -> dict:
    prods = await pf.listar(db)
    emps = {e["cnpj"]: e for e in await pf.empresas(db)}
    rows = []
    for p in prods:
        for cnpj, e in (p.get("empresas") or {}).items():
            trib = e.get("trib") or {}
            simples = e["regime"] == "simples_nacional"
            campo_cst = "csosn" if simples else "cst_icms"
            rows.append(
                {
                    "cells": [
                        t(_curto(cnpj, e["razao_social"]), 600, _ND),
                        b("Simples Nacional" if simples else "Lucro real", "info"),
                        t(str(p["codigo"])[:16]),
                        t(str(p["descricao"])[:44]),
                        t(str(p["ncm"] or "—")),
                        t(str(trib.get(campo_cst) or "—")),
                        t(str(trib.get("cst_pis") or "—")),
                        t(str(trib.get("cst_cofins") or "—")),
                        b("sim", "ok") if e["pronto"] else b("não", "bad" if p["ativo"] else "mut"),
                        t((", ".join(e["faltas"]) or "—")[:110]),
                        t(str(trib.get("origem_regra") or "—")[:220]),
                    ],
                    "filtros": {
                        "Empresa": _curto(cnpj, e["razao_social"]),
                        "Pronto para emitir": "sim" if e["pronto"] else "não",
                    },
                    "edit": {
                        "endpoint": f"{_ACT}produto-tributacao-salvar",
                        "method": "POST",
                        "btnLabel": "Editar",
                        "submitLabel": "Salvar",
                        "okMsg": "Tributação salva. Recarregue a aba.",
                        "fields": [
                            {
                                "key": "produto_id",
                                "label": "produto_id",
                                "type": "text",
                                "value": str(p["id"]),
                                "span": "span 1",
                            },
                            {
                                "key": "empresa_cnpj",
                                "label": "empresa_cnpj",
                                "type": "text",
                                "value": cnpj,
                                "span": "span 1",
                            },
                            (
                                {
                                    "key": "csosn",
                                    "label": "CSOSN* (Simples Nacional)",
                                    "type": "text",
                                    "span": "span 1",
                                    "value": trib.get("csosn") or "",
                                    "ph": "102, 101, 500…",
                                }
                                if simples
                                else {
                                    "key": "cst_icms",
                                    "label": "CST de ICMS*",
                                    "type": "text",
                                    "span": "span 1",
                                    "value": trib.get("cst_icms") or "",
                                    "ph": "00, 20, 40, 41…",
                                }
                            ),
                            {
                                "key": "aliquota_icms",
                                "label": "Alíquota de ICMS (%)",
                                "type": "text",
                                "span": "span 1",
                                "value": trib.get("aliquota_icms") or "",
                            },
                            {
                                "key": "cst_pis",
                                "label": "CST de PIS*",
                                "type": "text",
                                "span": "span 1",
                                "value": trib.get("cst_pis") or "",
                            },
                            {
                                "key": "aliquota_pis",
                                "label": "Alíquota de PIS (%)",
                                "type": "text",
                                "span": "span 1",
                                "value": trib.get("aliquota_pis") or "",
                            },
                            {
                                "key": "cst_cofins",
                                "label": "CST de COFINS*",
                                "type": "text",
                                "span": "span 1",
                                "value": trib.get("cst_cofins") or "",
                            },
                            {
                                "key": "aliquota_cofins",
                                "label": "Alíquota de COFINS (%)",
                                "type": "text",
                                "span": "span 1",
                                "value": trib.get("aliquota_cofins") or "",
                            },
                            {
                                "key": "cst_ipi",
                                "label": "CST de IPI",
                                "type": "text",
                                "span": "span 1",
                                "value": trib.get("cst_ipi") or "",
                            },
                            {
                                "key": "aliquota_ipi",
                                "label": "Alíquota de IPI (%)",
                                "type": "text",
                                "span": "span 1",
                                "value": trib.get("aliquota_ipi") or "",
                            },
                            {
                                "key": "origem_regra",
                                "label": "De onde veio a regra*",
                                "type": "textarea",
                                "span": "span 2",
                                "value": "",
                                "ph": "obrigatório — ex.: «orientação do contador em 24/09/2026», «Lei 10.637/2002 art. 2º»",
                            },
                        ],
                    },
                }
            )
    return {
        "title": "Tributação por empresa (CNPJ)",
        "sub": (
            "A **mesma mercadoria tem tributação diferente nas duas empresas** — por isso são duas tabelas. "
            + " · ".join(
                f"**{_curto(c, e['razao_social'])}** ({c}, {e['regime_tributario'].replace('_', ' ')}) usa "
                + ("CSOSN" if e["regime_tributario"] == "simples_nacional" else "CST de ICMS")
                for c, e in emps.items()
            )
            + ". Toda linha guarda **`origem_regra`**: de onde veio a decisão. Campo em branco é campo que "
            "ninguém decidiu ainda — não é zero, e a tela não finge que é. "
            "O botão «Padrão do regime» preenche em lote só o que está vazio, carimbando quem/quando/lei; "
            "**ICMS fica de fora** porque a alíquota depende da UF de destino e do benefício ZFM/SUFRAMA."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Produto, NCM, CST…",
        "filtros": [
            {"key": "Empresa", "label": "Empresa"},
            {"key": "Pronto para emitir", "label": "Pronto para emitir"},
        ],
        "grid": "0.9fr 0.9fr 0.8fr 1.9fr 0.8fr 0.6fr 0.5fr 0.6fr 0.8fr 1.6fr 2.4fr",
        "cols": [
            "Empresa",
            "Regime",
            "Código",
            "Produto",
            "NCM",
            "CST/CSOSN",
            "PIS",
            "COFINS",
            "Pronto?",
            "O que falta",
            "De onde veio a regra",
        ],
        "rows": rows,
    }


async def _tela_lote(db) -> dict:
    emps = await pf.empresas(db)
    opc = [
        {
            "value": e["cnpj"],
            "label": f"{_curto(e['cnpj'], e['razao_social'])} — {e['cnpj']} ({e['regime_tributario'].replace('_', ' ')})",
        }
        for e in emps
        if e["regime_tributario"] in pf.PADRAO_REGIME
    ]
    fund = " · ".join(f"**{k.replace('_', ' ')}**: {v['fundamento']}" for k, v in pf.PADRAO_REGIME.items())
    return {
        "title": "Tributação — aplicar o padrão do regime",
        "sub": (
            "Preenche o CST/CSOSN padrão do regime **apenas nas linhas ainda vazias** da empresa escolhida "
            "(nunca sobrescreve o que alguém já decidiu) e grava em `origem_regra` quem aplicou, quando e o "
            f"fundamento legal. {fund}. "
            "**O ICMS não entra**: a alíquota depende da UF de destino e do benefício ZFM/SUFRAMA, e isso é caso "
            "a caso — fica vazio e a tela continua acusando. "
            "Isto é um ATO DE UMA PESSOA, não uma inferência do sistema: só o contador confirma se o padrão vale "
            "para cada mercadoria."
        ),
        "cta": "Aplicar padrão",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "produto-tributacao-lote",
            "okMsg": "Aplicado — veja a aba «Tributação por empresa».",
            "showResult": True,
            "confirm": (
                "Vai preencher CST/CSOSN em todas as linhas vazias desta empresa, com o seu nome gravado como "
                "quem decidiu"
            ),
        },
        "fields": [
            {"key": "empresa_cnpj", "label": "Empresa (CNPJ)*", "type": "select", "span": "span 2", "options": opc}
        ],
    }


async def _tela_ncm_consulta(db) -> dict:
    from sqlalchemy import text as _sql

    rows_db = (
        await db.execute(
            _sql(
                """
                SELECT e.ncm, count(*) AS itens, min(e.descricao) AS exemplo,
                       n.codigo IS NOT NULL AS oficial,
                       coalesce(n.descricao, n.descricao_resumida, '') AS oficial_desc,
                       (SELECT count(*) FROM fin_produtos p WHERE p.ncm = e.ncm) AS produtos
                  FROM nfe_compras_estoque e
                  LEFT JOIN ncms n ON n.codigo = e.ncm
                 WHERE e.ncm IS NOT NULL AND e.ncm <> ''
                 GROUP BY e.ncm, n.codigo, n.descricao_resumida, n.descricao
                 ORDER BY (n.codigo IS NULL) DESC, count(*) DESC, e.ncm
                """
            )
        )
    ).fetchall()
    total = (await db.execute(_sql("SELECT count(*) FROM ncms"))).scalar() or 0
    maus = sum(1 for r in rows_db if not r[3])
    rows = [
        {
            "cells": [
                t(str(r[0]), 600, _ND),
                b("existe", "ok") if r[3] else b("NÃO existe", "bad"),
                t(str(r[4] or "—")[:110]),
                t(str(r[1])),
                t(str(r[2] or "—")[:50]),
                t(str(r[5])),
            ],
            "filtros": {"Na tabela oficial": "sim" if r[3] else "não"},
        }
        for r in rows_db
    ]
    return {
        "title": "NCM em uso (compras reais × tabela oficial)",
        "sub": (
            f"Os NCMs que entraram por NF-e de fornecedor, conferidos contra a nomenclatura oficial "
            f"(**{total} códigos** carregados do Portal Único Siscomex por `scripts/orq/carregar_tabela_ncm.py`). "
            + (
                f"**{maus} NCM(s) desta lista NÃO existem na tabela** — o fornecedor errou na nota dele, e um "
                "produto com esse código seria rejeitado pela SEFAZ. Esses produtos nascem INATIVOS, com o motivo "
                "escrito: corrigir é classificar, e classificar é trabalho de gente."
                if maus
                else "Todos existem na tabela oficial."
            )
            + " Para achar o NCM de um produto novo, use a aba «Sugerir NCM pela descrição»."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "NCM, descrição…",
        "filtros": [{"key": "Na tabela oficial", "label": "Na tabela oficial"}],
        "grid": "0.7fr 0.8fr 3.2fr 0.6fr 2fr 0.7fr",
        "cols": ["NCM", "Situação", "O que a nomenclatura diz", "Itens", "Exemplo na nota", "Produtos"],
        "rows": rows,
    }


def _tela_sugerir() -> dict:
    return {
        "title": "Sugerir NCM pela descrição",
        "sub": (
            "Escreva a descrição do produto e o sistema devolve candidatos **com a fonte de cada um**, "
            "em ordem de força da evidência: primeiro o **histórico real da casa** (as 147 linhas de "
            "`nfe_compras_estoque`, onde o fornecedor já declarou o NCM numa nota que produziu efeito fiscal — "
            "a linha diz de qual nota veio), depois a **busca textual na tabela oficial** (português, com "
            "`unaccent`, sobre o caminho capítulo → posição → subposição → item). "
            "**Nenhum modelo de linguagem inventa NCM aqui**: palpite sem fonte é o que vira multa. "
            "A escolha é sua — aceitar grava `origem_cadastro = 'sugerido'` e registra a fonte na observação "
            "do produto, para auditar depois."
        ),
        "cta": "Buscar candidatos",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "ncm-sugerir",
            "okMsg": "Candidatos abaixo. Para gravar num produto, use «Aplicar NCM escolhido».",
            "showResult": True,
        },
        "fields": [
            {
                "key": "descricao",
                "label": "Descrição do produto*",
                "type": "text",
                "span": "span 2",
                "ph": "ex.: BOTA DE SEGURANCA COM BICO PVC",
            },
            {
                "key": "limite",
                "label": "Quantos candidatos",
                "type": "select",
                "span": "span 1",
                "value": "5",
                "options": [{"value": str(n), "label": str(n)} for n in (5, 10, 20)],
            },
        ],
    }


async def _tela_aplicar(db) -> dict:
    prods = await pf.listar(db)
    opc = [{"value": str(p["id"]), "label": f"[{p['codigo']}] {str(p['descricao'])[:46]}"} for p in prods[:400]]
    return {
        "title": "Aplicar NCM sugerido",
        "sub": (
            "Depois de olhar os candidatos na aba «Sugerir NCM pela descrição», grave aqui o que VOCÊ escolheu. "
            "O NCM é validado contra a tabela oficial antes de entrar, o produto passa a ter "
            "`origem_cadastro = 'sugerido'` e a fonte que você colar fica na observação do produto — é assim que "
            "dá para auditar depois quem classificou o quê e com base em quê."
        ),
        "cta": "Aplicar",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "produto-ncm-aplicar",
            "okMsg": "NCM gravado com origem «sugerido». Veja a aba «Produtos fiscais».",
            "showResult": True,
        },
        "fields": [
            {"key": "produto_id", "label": "Produto*", "type": "select", "span": "span 2", "options": opc},
            {
                "key": "ncm",
                "label": "NCM escolhido*",
                "type": "text",
                "span": "span 1",
                "ph": "8 dígitos — validado contra a tabela oficial",
            },
            {
                "key": "fonte",
                "label": "Fonte da sugestão*",
                "type": "textarea",
                "span": "span 2",
                "ph": "cole o «por que» do candidato escolhido — ex.: «usado em BOTA S/CADARCO…, NF-e 12345 de BRACOL»",
            },
        ],
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    try:
        await pf._ensure(db)
        await pf.semear(db)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx z1: _ensure/semear falhou: %s", exc, exc_info=True)
    for tid, titulo, fn in (
        ("produtos-fiscais", "Produtos fiscais (NF-e)", lambda: _tela_produtos(db)),
        ("produto-fiscal-novo", "Novo produto fiscal", _tela_novo),
        ("produto-tributacao", "Tributação por empresa", lambda: _tela_tributacao(db)),
        ("ncm-consulta", "NCM em uso", lambda: _tela_ncm_consulta(db)),
        ("ncm-sugerir", "Sugerir NCM pela descrição", _tela_sugerir),
        ("ncm-aplicar", "Aplicar NCM sugerido", lambda: _tela_aplicar(db)),
        ("produto-tributacao-lote", "Tributação — padrão do regime", lambda: _tela_lote(db)),
    ):
        try:
            r = fn()
            mine[tid] = await r if hasattr(r, "__await__") else r
        except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
            await db.rollback()
            logger.error("dgx z1: tela %s falhou: %s", tid, exc, exc_info=True)
            from ._dgx_f7_ponto import _falhou

            mine[tid] = _falhou(titulo, exc)
    if out is not None:
        out.update(mine)
    return mine


# --------------------------------------------------------------------------- ações


def _quem(u) -> str:
    return (
        str((u or {}).get("email") or (u or {}).get("nome") or "usuário")
        if isinstance(u, dict)
        else str(getattr(u, "email", None) or getattr(u, "nome", None) or "usuário")
    )


@router.post("/action/produto-fiscal-salvar")
async def rd_produto_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Cria/edita/ativa. NCM fora da tabela oficial → 422 com a frase da SEFAZ."""
    await pf._ensure(db)
    r = await pf.salvar_produto(db, payload or {}, _quem(current_user))
    return {"ok": True, "result": r, "message": f"Produto {r.get('acao', 'salvo')} (id {r['id']})."}


@router.post("/action/produto-tributacao-salvar")
async def rd_tributacao_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await pf._ensure(db)
    r = await pf.salvar_tributacao(db, payload or {}, _quem(current_user))
    return {"ok": True, "result": r, "message": "Tributação salva com a origem da regra registrada."}


@router.post("/action/produto-tributacao-lote")
async def rd_tributacao_lote(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Preenche o padrão do regime nas linhas VAZIAS — ato explícito, com fundamento gravado."""
    r = await pf.aplicar_padrao_regime(db, str((payload or {}).get("empresa_cnpj") or ""), _quem(current_user))
    return {
        "ok": True,
        "result": r,
        "message": (
            f"{r['linhas']} linha(s) de {r['empresa']} preenchidas. Fundamento gravado em origem_regra: "
            f"{r['fundamento']}. O ICMS continua vazio (depende da UF de destino e do benefício ZFM)."
        ),
    }


@router.post("/action/ncm-sugerir")
async def rd_ncm_sugerir(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Candidatos a NCM pela descrição, cada um com a fonte. Não grava nada."""
    p = payload or {}
    desc = str(p.get("descricao") or "").strip()
    try:
        limite = max(1, min(50, int(str(p.get("limite") or 5))))
    except ValueError:
        limite = 5
    cands = await pf.sugerir_ncm(db, desc, limite)
    if not cands:
        return {
            "ok": True,
            "result": {"candidatos": []},
            "message": (
                "Nenhum candidato para essa descrição — nem no histórico de compras nem na tabela oficial. "
                "Classifique com o contador; o sistema não vai inventar um NCM."
            ),
        }
    linhas = [
        f"{i + 1}. {c['ncm']} — {c['descricao_oficial'][:80] or '(sem descrição oficial)'} "
        f"[{_ROTULO_FONTE.get(c['fonte'], c['fonte'])}] {c['por_que']}"
        + ("" if c["existe_na_tabela_oficial"] else "  ⚠ este código NÃO consta na nomenclatura vigente")
        for i, c in enumerate(cands)
    ]
    return {
        "ok": True,
        "result": {"candidatos": cands},
        "message": "Candidatos (a decisão é sua):\n" + "\n".join(linhas),
    }


@router.post("/action/produto-ncm-aplicar")
async def rd_ncm_aplicar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Grava a sugestão ACEITA — `origem_cadastro='sugerido'` + a fonte na observação."""
    p = payload or {}
    r = await pf.aplicar_ncm_sugerido(
        db,
        int(str(p.get("produto_id") or 0) or 0),
        str(p.get("ncm") or ""),
        str(p.get("fonte") or ""),
        _quem(current_user),
    )
    return {"ok": True, "result": r, "message": f"NCM {r['ncm']} gravado (origem do cadastro: sugerido)."}
