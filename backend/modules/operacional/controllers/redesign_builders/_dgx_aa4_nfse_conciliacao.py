"""DGX AA4 — conciliação da NFS-e com o fisco, parametrização em dado, e as 14 de setembro.

Três telas, três problemas que o dono viveu em 24/09/2026:

1. **«O fisco tem 37 notas que o ERP não tem.»** Medido pela régua certa — a numeração por
   CNPJ, que é consecutiva por emitente. Pelo NSU daria 419 e seria mentira, porque o NSU
   carrega todo tipo de documento. A tela mostra o furo, dispara a conciliação e exibe o
   livro-razão: o que foi recuperado, o que o fisco disse que não existe, e o que ainda não
   foi perguntado.

2. **«O sistema chutava a série, o NBS e a alíquota.»** Agora é tabela: série 70000, um NBS
   por código de serviço, ISS nulo no Simples, IBS/CBS sobre a base menos ISS, PIS/COFINS
   não retidos por decisão judicial. Cada linha com a nota de onde saiu.

3. **«Digito 14 notas por mês à mão.»** A tela propõe as 14 com tudo montado e **para**.
   Cada nota exige o clique dele. Nada sai sozinho.

Prefixo `_` = o discovery pula. `fiscal.py` inclui o `router` e chama `telas(db, out)`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_permission
from core.database import get_db

router = APIRouter()

IDS = (
    "aa4-nfse-conciliacao",
    "aa4-nfse-livro",
    "aa4-nfse-parametros",
    "aa4-nfse-servicos",
    "aa4-nfse-lote",
    "aa4-nfse-emitir-do-mes",
)

EXTRA_MENU: list[dict] = [
    {
        "id": "aa4-nfse-conciliacao",
        "label": "Conciliar NFS-e com o fisco",
        "icon": "M4 12h16M12 4v16",
        "grupo": "Notas fiscais",
    },
    {
        "id": "aa4-nfse-lote",
        "label": "Notas do mês (cronograma)",
        "icon": "M3 5h18M3 12h18M3 19h18",
        "grupo": "Notas fiscais",
    },
    {
        "id": "aa4-nfse-emitir-do-mes",
        "label": "Emitir nota do cronograma",
        "icon": "M5 12h14M12 5l7 7-7 7",
        "grupo": "Notas fiscais",
    },
    {"id": "aa4-nfse-livro", "label": "Livro-razão da conciliação", "icon": "M4 4h16v16H4z", "grupo": "Notas fiscais"},
    {
        "id": "aa4-nfse-parametros",
        "label": "Parâmetros fiscais da NFS-e",
        "icon": "M12 3v18M3 12h18",
        "grupo": "Notas fiscais",
    },
    {"id": "aa4-nfse-servicos", "label": "Códigos de serviço e NBS", "icon": "M7 7h10v10H7z", "grupo": "Notas fiscais"},
]

_ACT = "/api/v1/redesign/action/"
_GATE = [Depends(require_permission("module:fiscal"))]


def _numero(v: Any) -> float | None:
    """Campo vazio volta `None`, não 0,00. Zero afirma «não houve»; vazio é «não sei»."""
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(v)
    except (TypeError, ValueError):
        return None


def _br(v: Any, prefixo: str = "R$ ") -> str:
    """Dinheiro em português. `None` vira travessão — nunca R$ 0,00 inventado."""
    if v is None:
        return "—"
    return prefixo + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ─────────────────────────────────────────────────────────────────────────────────────
# REGRA PURA — o oráculo importa ESTA. Sem banco, sem rede.
# ─────────────────────────────────────────────────────────────────────────────────────


def rotulo_do_estado(tipo: str, estado: str) -> str:
    """O que a tela pode honestamente dizer sobre um número da sequência.

    «Conferido» é afirmação sobre o FISCO: só vale quando ele respondeu. Enquanto não
    respondeu, o estado honesto é «ausente e ainda não conferido» — e é exatamente esse
    o estado que não pode sumir de vista, porque foi assim que 37 notas ficaram anos sem
    ninguém saber que faltavam.
    """
    mapa = {
        "recuperada": "recuperada do fisco",
        "encontrada": "o fisco devolveu a nota",
        "inexistente": "o fisco disse que não existe",
        "erro": "erro ao consultar — será tentado de novo",
        "pendente": "ausente e ainda NÃO conferido",
    }
    return mapa.get(str(estado or "").strip().lower(), str(estado or "—"))


def conferido(estado: str) -> bool:
    """Um número só está fechado quando o fisco falou. Aritmética não fecha número fiscal."""
    return str(estado or "").strip().lower() in ("recuperada", "encontrada", "inexistente")


# ─────────────────────────────────────────────────────────────────────────────────────
# AÇÕES
# ─────────────────────────────────────────────────────────────────────────────────────


@router.post("/action/aa4-conciliar-nfse", dependencies=_GATE)
async def rd_aa4_conciliar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Pergunta ao fisco sobre os números que faltam e grava o que ele responder.

    Só GET. Não emite, não cancela, não numera. A trava de produção da Z7 continua
    inteira no caminho que emite — este não passa por lá.
    """
    from modules.fiscal.services import nfse_conciliacao as cc

    quem = (getattr(current_user, "email", None) or "sistema")[:120]
    empresa = str(payload.get("empresa_cnpj") or "").strip() or None
    try:
        limite = max(1, min(200, int(payload.get("limite") or 25)))
    except (TypeError, ValueError):
        limite = 25
    semeado = await cc.semear(db)
    resultado = await cc.conciliar(db, empresa_cnpj=empresa, limite=limite, quem=quem)
    return {**semeado, **resultado}


@router.post("/action/aa4-emitir-do-cronograma", dependencies=_GATE)
async def rd_aa4_emitir_do_cronograma(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Emite UMA nota do cronograma — a que o dono escolheu, com o que ele conferiu.

    UMA. Não há laço, não há «emitir todas», não há agendamento que chame isto. O dono
    olha a proposta, corrige o que quiser e clica por nota. Em HOMOLOGAÇÃO, porque é o
    que `empresas.nfse_ambiente` diz — e produção continua exigindo a frase-senha da Z7.
    """
    from modules.fiscal.services import nfse_lote as lote
    from modules.fiscal.services import nfse_parametros as par_mod
    from modules.fiscal.services.nfse_emissao import NFSeErro, emitir

    quem = (getattr(current_user, "email", None) or "sistema")[:120]
    try:
        linha_id = int(payload.get("linha_id") or 0)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=422, detail={"code": "LINHA_INVALIDA", "message": "Escolha uma linha."}) from e

    propostas = {p["id"]: p for p in await lote.propor(db, str(payload.get("competencia") or "2026-09"))}
    p = propostas.get(linha_id)
    if not p:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "LINHA_DESCONHECIDA",
                "message": f"Linha {linha_id} não está no cronograma desta competência.",
            },
        )
    if not p["empresa_cnpj"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EMPRESA_SEM_FONTE",
                "message": (
                    "Esta linha do cronograma não diz qual empresa emite — não traz dados bancários e o "
                    "tomador não tem nota anterior. Escolher o CNPJ de um documento fiscal no escuro é "
                    "pior do que parar aqui. Diga qual empresa e eu emito."
                ),
            },
        )
    if not p["codigo_servico"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SERVICO_SEM_FONTE",
                "message": (
                    f"O rótulo «{p['rotulo_servico']}» junta duas naturezas numa nota só e o fisco, para "
                    "este tomador, emitiu SEPARADAS em 08/2026. Escolha o código de serviço."
                ),
            },
        )

    slug = (
        await db.execute(
            text("SELECT slug FROM empresas WHERE regexp_replace(cnpj,'\\D','','g') = :c"),
            {"c": p["empresa_cnpj"]},
        )
    ).scalar()
    try:
        valor = float(payload.get("valor") or p["valor_bruto"])
    except (TypeError, ValueError):
        valor = float(p["valor_bruto"])

    # ── A dedução de VA e VT antes dos 11% (regra do dono, 24/09/2026) ───────────────
    # O gatilho é o EMITENTE, lido do parâmetro — não palavra na descrição. E o valor é
    # DIGITADO: o sistema não sabe, de forma confiável, quanto de vale-alimentação e
    # vale-transporte foi entregue por contrato no mês (ver §7 do relatório). Campo vazio
    # NÃO vira zero silencioso: a nota sai sem dedução e `aviso` diz isso em voz alta.
    par_emp = await par_mod.parametros_de(db, p["empresa_cnpj"])
    bloco = lote.bloco_inss(
        valor,
        par_emp,
        va=_numero(payload.get("va")),
        vt=_numero(payload.get("vt")),
        competencia_beneficio=str(payload.get("competencia_beneficio") or p["competencia_beneficio"]),
        pessoas=(int(payload.get("pessoas") or 0) or None),
    )
    # A dedução só se sustenta com VA, VT e a base ESCRITOS na própria nota — sem isso o
    # fisco glosa e a economia vira autuação. Por isso o bloco entra na descrição aqui,
    # nunca depois, e nunca a conta sem o texto.
    descricao = lote.montar_descricao(str(payload.get("descricao") or p["descricao"]), bloco)

    try:
        r = await emitir(
            db,
            empresa=slug,
            tomador={
                "cpf_cnpj": p["tomador_cnpj"],
                "razao_social": p["tomador_nome"],
                "municipio": "Manaus",
                "codigo_municipio": "1302603",
                "uf": "AM",
                "numero": "S/N",
            },
            servico={
                "codigo_tributacao_nacional": str(payload.get("codigo_servico") or p["codigo_servico"]),
                "descricao": descricao,
                "valor_servico": valor,
                "aliquota_iss": (p["iss_aliquota"] or 0) / 100 if p["iss_aliquota"] else 0,
            },
            competencia=p["competencia"],
            dry_run=str(payload.get("dry_run", "sim")).lower() in ("sim", "true", "1"),
            quem=quem,
        )
    except NFSeErro as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": str(e), **e.details}) from e

    if r.get("gravou") and r.get("status") == "autorizada":
        await lote.marcar_emitida(db, linha_id, r.get("id"))
    return {
        **r,
        "linha_do_cronograma": linha_id,
        "tomador": p["tomador_nome"],
        "cessao_de_mao_de_obra": bloco["aplica"],
        "inss_base": bloco["base"],
        "inss_retido": bloco["inss"],
        "inss_deducao": bloco["deducao"],
        "descricao_enviada": descricao,
        # Em voz alta, sempre no topo do resultado: dedução que não aconteceu é dinheiro.
        "aviso": bloco["aviso"],
    }


# ─────────────────────────────────────────────────────────────────────────────────────
# TELAS
# ─────────────────────────────────────────────────────────────────────────────────────


async def telas(db: AsyncSession, out: dict | None = None) -> dict:
    from modules.fiscal.services import nfse_conciliacao as cc
    from modules.fiscal.services import nfse_lote as lote
    from modules.fiscal.services import nfse_parametros as par

    await cc._ensure(db)
    await lote._ensure(db)
    out = out if out is not None else {}

    await _tela_conciliacao(db, out, cc)
    await _tela_parametros(db, out, par)
    await _tela_lote(db, out, lote)
    return out


async def _tela_conciliacao(db: AsyncSession, out: dict, cc: Any) -> None:
    furo = await cc.medir_furo(db)
    livro = (
        (
            await db.execute(
                text(
                    "SELECT c.prestador_cnpj, e.razao_social, c.tipo, c.serie, c.numero, c.estado,"
                    " coalesce(c.chave_acesso,'') AS chave, coalesce(c.numero_nfse,'') AS nnfse,"
                    " c.http_status, coalesce(c.mensagem,'') AS msg, c.conferido_em, c.tentativas"
                    " FROM nfse_conciliacao c"
                    " LEFT JOIN empresas e ON regexp_replace(e.cnpj,'\\D','','g') = c.prestador_cnpj"
                    " ORDER BY c.tipo, c.prestador_cnpj, c.numero LIMIT 600"
                )
            )
        )
        .mappings()
        .all()
    )
    n_pend = sum(1 for r in livro if r["tipo"] == "nfse" and not conferido(r["estado"]))
    n_rec = sum(1 for r in livro if r["tipo"] == "nfse" and r["estado"] == "recuperada")
    n_nao = sum(1 for r in livro if r["tipo"] == "nfse" and r["estado"] == "inexistente")

    resumo_furo = (
        " · ".join(
            f"{f['slug']}: nº {f['lo']}–{f['hi']}, temos {f['qtd']}, faltam {len(f['faltam'] or [])}" for f in furo
        )
        or "sem nota emitida registrada"
    )

    out["aa4-nfse-conciliacao"] = {
        "title": "Conciliar NFS-e com o fisco",
        "sub": (
            f"A régua é a NUMERAÇÃO POR CNPJ, consecutiva por emitente — {resumo_furo}. "
            "Medir pelo NSU do ADN acusaria centenas e seria mentira: o NSU carrega nota recebida, "
            "evento e cancelamento, não só nota emitida. "
            "Esta rotina pergunta ao fisco, um número de DPS por vez, e grava o que ele responder — "
            "inclusive quando ele diz que o número NÃO existe (cancelado, pulado). Sem esse registro "
            "ela reconsultaria o mesmo número para sempre. "
            f"Hoje: {n_rec} recuperada(s), {n_nao} que o fisco negou, {n_pend} ainda NÃO conferida(s). "
            "A consulta é só leitura — não emite, não cancela, não gasta número. Ela roda também "
            "sozinha, todo dia, depois da sincronia do ADN."
        ),
        "cta": "Conciliar agora",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "aa4-conciliar-nfse",
            "okMsg": "Conciliação executada — veja o resultado.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "empresa_cnpj",
                "label": "Empresa (vazio = todas)",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "", "label": "Todas as empresas"}]
                + [{"value": f["cnpj"], "label": f"{f['slug']} — faltam {len(f['faltam'] or [])}"} for f in furo],
                "value": "",
            },
            {
                "key": "limite",
                "label": "Quantos números perguntar nesta rodada",
                "type": "number",
                "span": "span 1",
                "value": 25,
                "ph": "25",
            },
        ],
    }

    rows = []
    for r in livro:
        rows.append(
            {
                "cells": [
                    r["razao_social"] or r["prestador_cnpj"],
                    "NFS-e" if r["tipo"] == "nfse" else f"DPS série {r['serie']}",
                    str(r["numero"]),
                    rotulo_do_estado(r["tipo"], r["estado"]),
                    r["chave"] or "—",
                    r["nnfse"] or "—",
                    str(r["http_status"] or "—"),
                    r["conferido_em"].strftime("%d/%m/%Y %H:%M") if r["conferido_em"] else "—",
                    str(r["tentativas"]),
                    (r["msg"] or "—")[:200],
                ]
            }
        )
    out["aa4-nfse-livro"] = {
        "title": "Livro-razão da conciliação",
        "sub": (
            f"{len(rows)} linha(s). Cada número da sequência de cada CNPJ tem uma linha aqui, e "
            "nenhuma some: «ausente e ainda NÃO conferido» é um estado, não um esquecimento. "
            "O número de NFS-e só fecha quando o fisco fala — recuperado (apareceu a nota) ou negado "
            "(a varredura de DPS do CNPJ terminou e ele negou todas as que poderiam tê-lo gerado). "
            "Nunca por dedução aritmética."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar número, chave, motivo…",
        "cols": [
            "Empresa",
            "O quê",
            "Número",
            "Estado",
            "Chave de acesso",
            "NFS-e",
            "HTTP",
            "Conferido em",
            "Tentativas",
            "O que o fisco disse",
        ],
        "grid": "1.2fr 0.9fr 0.6fr 1.5fr 2.2fr 0.6fr 0.5fr 1fr 0.7fr 2fr",
        "rows": rows,
    }


async def _tela_parametros(db: AsyncSession, out: dict, par: Any) -> None:
    emps = (
        (
            await db.execute(
                text(
                    "SELECT p.*, coalesce(e.razao_social, p.prestador_cnpj) AS nome"
                    " FROM nfse_parametros_empresa p"
                    " LEFT JOIN empresas e ON regexp_replace(e.cnpj,'\\D','','g') = p.prestador_cnpj"
                    " ORDER BY nome"
                )
            )
        )
        .mappings()
        .all()
    )
    rows = []
    for e in emps:
        rows.append(
            {
                "cells": [
                    e["nome"],
                    e["serie_dps"],
                    e["regime"],
                    # ISS nulo NÃO vira 0% — vira travessão com o motivo ao lado.
                    (f"{float(e['iss_aliquota']):.2f}%".replace(".", ",") if e["iss_aliquota"] is not None else "—"),
                    f"IBS-UF {float(e['ibs_uf_aliquota'] or 0):.2f}% · IBS-Mun {float(e['ibs_mun_aliquota'] or 0):.2f}%"
                    f" · CBS {float(e['cbs_aliquota'] or 0):.2f}%".replace(".", ","),
                    f"CST {e['cst_ibs_cbs']} / {e['cclass_trib']}",
                    e["retencao_federal_rotulo"] or "—",
                    (f"{float(e['csll_aliquota']):.2f}%".replace(".", ",") if e["csll_aliquota"] is not None else "—"),
                    (f"{float(e['inss_aliquota']):.2f}%".replace(".", ",") if e["inss_aliquota"] is not None else "—"),
                    "SEM FONTE" if e["irrf_aliquota"] is None else f"{float(e['irrf_aliquota']):.2f}%",
                    f"{e['banco_nome']} {e['banco_codigo']} · ag {e['agencia']} · c/c {e['conta']}",
                    str(e["ultimo_dps_observado"] or "—"),
                    (e["fonte"] or "")[:400],
                ]
            }
        )
    out["aa4-nfse-parametros"] = {
        "title": "Parâmetros fiscais da NFS-e — por empresa e por serviço",
        "sub": (
            "O que o sistema chutava até 24/09/2026 virou tabela, com a nota do fisco de onde cada "
            "número saiu. Mudar é um UPDATE numa linha. "
            "Três regras aqui são dinheiro: a base do IBS/CBS é o valor MENOS o ISS (cobrar sobre o "
            "valor cheio pagaria a mais); PIS e COFINS NÃO são retidos na Eletrônica por decisão "
            "judicial citada na própria NFS-e 121 (processo nº 1038495-94.2024.4.01.3200); e a "
            "Patrimonial é do Simples — ISS vazio, nunca 0%, porque o ISSQN dela vai no DAS. "
            "O IRRF está declarado SEM FONTE de propósito: aparece só numa das nove notas."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar empresa, banco, fonte…",
        "cols": [
            "Empresa",
            "Série DPS",
            "Regime",
            "ISS",
            "IBS/CBS (transição 2026)",
            "CST/cClass",
            "Retenção federal",
            "CSLL",
            "INSS",
            "IRRF",
            "Conta para pagamento",
            "Último nº de DPS visto",
            "Fonte",
        ],
        "grid": "1.3fr 0.6fr 0.9fr 0.5fr 1.8fr 0.9fr 1.6fr 0.5fr 0.5fr 0.7fr 1.6fr 0.7fr 2.4fr",
        "rows": rows,
    }

    servs = await par.servicos(db)
    out["aa4-nfse-servicos"] = {
        "title": "Códigos de serviço e o NBS de cada um",
        "sub": (
            f"{len(servs)} código(s), cada um com UM NBS e a nota onde ele foi lido. O `cNBS` que "
            "estava chumbado no emissor era 1.2003.29.00 em TODA nota — certo só para 14.06.01 e "
            "errado nos outros três; por isso o fisco devolvia «serviços de instalação de "
            "maquinários» nas notas de vigilância. Código sem NBS aqui sai da nota SEM a tag, e é "
            "assim que tem de ser: NBS inventado é número fiscal inventado."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar código, NBS, serviço…",
        "cols": ["Código", "NBS", "Serviço (rótulo da casa)", "Descrição oficial do fisco", "Fonte"],
        "grid": "0.6fr 0.9fr 1.6fr 3fr 2fr",
        "rows": [
            {"cells": [s["codigo_formatado"], s["nbs"] or "SEM FONTE", s["rotulo"], s["descricao_oficial"], s["fonte"]]}
            for s in servs
        ],
    }


async def _tela_lote(db: AsyncSession, out: dict, lote: Any) -> None:
    props = await lote.propor(db, "2026-09")
    total = sum(p["valor_bruto"] for p in props)
    sem_fonte = [p for p in props if not p["empresa_cnpj"] or not p["codigo_servico"]]
    divergem = [p for p in props if p["codigo_diverge"]]

    rows = []
    for p in props:
        prec = p["precedente"] or {}
        rows.append(
            {
                "cells": [
                    str(p["ordem"]),
                    p["tomador_nome"],
                    _br(p["valor_bruto"]),
                    (
                        f"{p['codigo_servico']} ({p['codigo_fonte']})"
                        if p["codigo_servico"]
                        else f"SEM FONTE — {p['rotulo_servico']}"
                    )
                    + (f" · rótulo diria {p['codigo_por_rotulo']}" if p["codigo_diverge"] else ""),
                    p["nbs"] or "—",
                    (p["empresa_fonte"] or "—")
                    if not p["empresa_cnpj"]
                    else f"{p['empresa_cnpj']} — {p['empresa_fonte']}",
                    (f"{p['iss_aliquota']:.2f}%".replace(".", ",") if p["iss_aliquota"] is not None else "— (Simples)"),
                    # As duas contas de INSS, lado a lado. A tela não escolhe.
                    (
                        "SIM — deduz VA+VT antes dos 11%"
                        if p["cessao_de_mao_de_obra"]
                        else "não — sem retenção do Art. 31"
                    ),
                    (
                        f"{_br(p['inss_com_deducao'])} (base {_br(p['base_com_deducao'])})"
                        if p["cessao_de_mao_de_obra"]
                        else "—"
                    ),
                    (
                        f"{_br(p['inss_sem_deducao'])} (base {_br(p['base_sem_deducao'])})"
                        if p["cessao_de_mao_de_obra"]
                        else "—"
                    ),
                    (
                        f"VA {_br(p['va_folha'])} · VT {_br(p['vt_folha'])}"
                        + (
                            f" · {p['vt_sem_valor_na_folha']} linha(s) de VT sem valor"
                            if p["vt_sem_valor_na_folha"]
                            else ""
                        )
                        + f" · {p['pessoas_na_folha']} pessoa(s)"
                    )
                    if p["pessoas_na_folha"]
                    else "sem funcionário alocado neste tomador",
                    (
                        f"nº {prec['numero']} ({prec['competencia']}): {_br(prec['valor'])}, "
                        f"INSS {_br(prec['inss'])} — {prec['empresa']}"
                    )
                    if prec
                    else "—",
                    p["estado"],
                ]
            }
        )

    out["aa4-nfse-lote"] = {
        "title": "Notas do mês — cronograma de 09/2026",
        "sub": (
            f"{len(props)} nota(s), {_br(total)} de valor bruto. Esta tela **propõe**; quem emite é "
            "você, uma nota por clique, pela tela «Emitir NFS-e (serviço)» ou pela ação desta. "
            "Nada sai sozinho e não há «emitir todas». "
            "O código de serviço vem da ÚLTIMA nota que o fisco registrou para o tomador — melhor "
            "fonte que o rótulo da planilha, e "
            + (
                f"em {len(divergem)} linha(s) os dois discordam (as duas aparecem). "
                if divergem
                else "hoje os dois concordam. "
            )
            + "A empresa emitente vem dos dados bancários que você escreveu na descrição. "
            + (f"{len(sem_fonte)} linha(s) estão SEM FONTE e o sistema se recusa a adivinhar. " if sem_fonte else "")
            + "O INSS aparece nas DUAS contas porque as fontes discordam: a folha deste sistema e a "
            "planilha não dão o mesmo VA/VT, o VT está sem valor em sete dos oito condomínios, e as "
            "cinco notas da Patrimonial de 08/2026 saíram com 11% sobre o BRUTO, sem dedução nenhuma. "
            "A coluna «o que o fisco fez antes» é o árbitro mais confiável dos três."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar tomador, código, empresa…",
        "cols": [
            "#",
            "Tomador",
            "Valor bruto",
            "Código do serviço (fonte)",
            "NBS",
            "Empresa que emite (fonte)",
            "ISS",
            "Cessão de mão de obra?",
            "INSS com dedução VA+VT",
            "INSS sobre o bruto",
            "VA/VT na folha (REFERÊNCIA, não é a fonte)",
            "O que o fisco fez antes",
            "Estado",
        ],
        "grid": "0.3fr 1.5fr 0.8fr 2.2fr 0.9fr 2fr 0.6fr 1.5fr 1.4fr 1.4fr 1.8fr 2fr 0.7fr",
        "rows": rows,
    }

    # ── A porta de transmitir: UMA nota, com VA e VT digitados por quem assina ────────
    cessao = [p for p in props if p["cessao_de_mao_de_obra"]]
    out["aa4-nfse-emitir-do-mes"] = {
        "title": "Emitir nota do cronograma — uma por vez",
        "sub": (
            "Escolha a nota, confira o valor e transmita. **Uma por clique** — não existe "
            "«emitir todas» e nada aqui roda sozinho. "
            f"{len(cessao)} das {len(props)} notas são de CESSÃO DE MÃO DE OBRA (as da CONECTAMAIS "
            "PATRIMONIAL) e só nessas há retenção do Art. 31 da Lei 9.711/98. Quem decide isso é o "
            "CNPJ que assina, não palavra na descrição: «Portaria Remota» do Gelain tem a palavra "
            "portaria e NÃO é cessão — não há pessoa posta no cliente —, e é da Eletrônica. "
            "**Nessas notas, informe o vale-alimentação e o vale-transporte do mês:** os 11% incidem "
            "sobre o bruto MENOS os dois, e o sistema escreve os valores e a base dentro da nota — "
            "sem isso escrito, o fisco glosa a dedução e a economia vira autuação. "
            "Se você deixar os campos vazios a nota sai SEM dedução, sobre o valor cheio, e o "
            "resultado avisa. O sistema não inventa esses números: hoje ele não sabe, de forma "
            "confiável, quanto de VA e VT foi entregue por contrato no mês. "
            "Deixe «Simulação» em SIM para ver o XML sem transmitir."
        ),
        "cta": "Emitir esta nota",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "aa4-emitir-do-cronograma",
            "okMsg": "Processado — leia o campo «aviso» no resultado.",
            "showResult": True,
            "confirm": "Confere tomador, valor, VA, VT e a empresa que emite. Emitir?",
        },
        "fields": [
            {
                "key": "linha_id",
                "label": "Nota do cronograma*",
                "type": "select",
                "span": "span 2",
                "options": [
                    {
                        "value": str(p["id"]),
                        "label": (
                            f"{p['ordem']:02d} · {p['tomador_nome']} · {_br(p['valor_bruto'])} · "
                            + (f"{p['rotulo_servico']} · ")
                            + ("CESSÃO (deduz VA+VT)" if p["cessao_de_mao_de_obra"] else "sem retenção do Art. 31")
                        ),
                    }
                    for p in props
                ],
                "value": (str(props[0]["id"]) if props else None),
            },
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1", "value": "2026-09"},
            {"key": "valor", "label": "Valor bruto (R$) — vazio usa o do cronograma", "type": "text", "span": "span 1"},
            {
                "key": "va",
                "label": "Vale-alimentação do mês (R$) — só cessão de mão de obra",
                "type": "text",
                "span": "span 1",
                "ph": "1804.00",
            },
            {
                "key": "vt",
                "label": "Vale-transporte do mês (R$) — só cessão de mão de obra",
                "type": "text",
                "span": "span 1",
                "ph": "880.00",
            },
            {
                "key": "pessoas",
                "label": "Funcionários no contrato (vai escrito na nota)",
                "type": "number",
                "span": "span 1",
            },
            {
                "key": "competencia_beneficio",
                "label": "Competência do VA/VT (AAAA-MM)",
                "type": "text",
                "span": "span 1",
                "ph": "2026-08",
            },
            {
                "key": "descricao",
                "label": "Descrição — vazio usa a do cronograma (o bloco do INSS é acrescentado)",
                "type": "textarea",
                "span": "span 2",
            },
            {
                "key": "dry_run",
                "label": "Simulação (não transmite)?*",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "sim", "label": "Sim — só montar o XML"},
                    {"value": "nao", "label": "Não — transmitir de verdade"},
                ],
                "value": "sim",
            },
        ],
    }
