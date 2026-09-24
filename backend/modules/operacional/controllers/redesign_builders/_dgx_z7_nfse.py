"""DGX Z7 — NFS-e de serviço para os DOIS CNPJs, provada em HOMOLOGAÇÃO (24/09/2026).

O pedido do dono, no dia em que viu a primeira NF-e de produto autorizada:

    «a patrimonial tem apenas inscrição municipal, homologa também.
     nf de serviço e nf de produto pra eletronica e nf de serviço para a patrimonial»

O que havia antes — medido, não lido
------------------------------------
  · `nfses`: **27 linhas dizendo `autorizada`, zero com protocolo, zero com código de
    verificação, zero com XML enviado ou recebido** (todas criadas no mesmo batch de
    23/03/2026). O status era palavra escrita localmente, não fato do órgão. A tela
    chamava as 27 de «autorizada».
  · o transmissor (`government_integrations`) sabia emitir e **não guardava nada**: nem
    linha, nem XML, nem número. O número da DPS era `int(time.time())`.
  · a tela «NFS-e nacional — emitir DPS» mandava a DPS para o controller do governo e
    devolvia o JSON cru. Nada disso chegava a `nfses`.

O caminho de homologação, com a medição (24/09/2026)
----------------------------------------------------
  · `nfse-hml.manaus.am.gov.br` — **NÃO RESOLVE** (NXDOMAIN). O ABRASF de Manaus
    (`nfse-prd…`, WSDL HTTP 200) **não tem ambiente de homologação**. A constante
    `NFSeManausManager.URL_BASE_HOMOLOGACAO` aponta para um host que não existe.
  · **Manaus ADERIU ao Padrão Nacional**: `nfse_emitidas_nacional` tem 114 notas REAIS
    das duas empresas, jan–set/2026, com chave nacional começando em `1302603` (IBGE de
    Manaus) — inclusive 25 da Patrimonial. Não é previsão: é nota emitida.
  · o ambiente de teste do Padrão Nacional chama-se **PRODUÇÃO RESTRITA** e tem host
    próprio: `sefin.producaorestrita.nfse.gov.br` (189.9.67.145, TLS válido, HTTP 403
    sem certificado — mTLS, como se espera).

  Então o caminho é UM: **Padrão Nacional, produção restrita, `tpAmb=2`.**

O que esta frente acrescenta
----------------------------
  · `modules/fiscal/services/nfse_emissao.py` — numeração atômica, persistência em
    `nfses`, guarda do XML em disco E no banco;
  · a trava de produção em `nfse_nacional` (duas camadas + gate humano), onde TODO
    chamador passa;
  · `modules/fiscal/services/documentos_da_empresa.py` — a decisão do dono virou dado:
    a Patrimonial não emite NF-e modelo 55, e a recusa diz isso e aponta esta tela;
  · esta tela, com o estado REAL de cada nota. As 27 antigas aparecem como
    **«sem comprovação — nunca transmitida»**, que é o que elas sempre foram.

O que NÃO faz
-------------
  · **não apaga nem reescreve as 27 linhas.** O contrato desta onda proíbe UPDATE em
    dado que a frente não criou, e apagar prova é pior que exibir prova ruim. Elas ficam
    exatamente como estão; o que muda é o rótulo, que passa a ser verdade.
  · não emite em produção. Nem para testar.
  · não cancela NFS-e (evento de cancelamento do Padrão Nacional não implementado).

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

IDS = ("nfse-emitir-dps", "z7-nfse-emitidas")

EXTRA_MENU: list[dict] = [
    # A tela de emitir REUSA o id e a entrada de menu que já existiam («NFS-e nacional —
    # emitir DPS»): dois caminhos de emissão, um deles sem persistência, é exatamente a
    # armadilha que a frente Z2 desmontou na NF-e. Aqui há um caminho só.
    {"id": "z7-nfse-emitidas", "label": "NFS-e emitidas pelo ERP", "icon": "M3 3v18h18", "grupo": "Notas fiscais"},
]

_ACT = "/api/v1/redesign/action/"
_GATE = [Depends(require_permission("module:fiscal"))]


# ─────────────────────────────────────────────────────────────────────────────────────
# REGRA PURA — o oráculo importa ESTA. Sem banco, sem rede.
# ─────────────────────────────────────────────────────────────────────────────────────


def estado_real(status: str | None, protocolo: str | None, xml_retorno: str | None) -> tuple[str, str]:
    """O que a tela pode honestamente dizer sobre uma NFS-e.

    «Autorizada» é afirmação sobre o FISCO, não sobre o nosso banco. Sem o número que o
    órgão devolveu (`nDFSe`, guardado em `protocolo`) E sem o XML `<NFSe>` que ele
    assinou, não há como saber se a nota existe lá — e foi assim que 27 linhas passaram
    meses se dizendo autorizadas sem nunca terem saído desta casa.

    Devolve (código, rótulo em PT-BR).
    """
    st = (status or "").strip().lower()
    tem_prova = bool((protocolo or "").strip()) and bool((xml_retorno or "").strip())
    if st in ("cancelada", "rejeitada", "erro"):
        return st, {"cancelada": "cancelada", "rejeitada": "rejeitada", "erro": "erro na transmissão"}[st]
    if tem_prova:
        return ("autorizada", "autorizada") if st == "autorizada" else (st or "enviada", st or "enviada")
    return "sem_comprovacao", "sem comprovação — nunca transmitida"


# ─────────────────────────────────────────────────────────────────────────────────────
# AÇÃO
# ─────────────────────────────────────────────────────────────────────────────────────


def _campo(p: dict, *nomes: str) -> str:
    for n in nomes:
        v = p.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return ""


@router.post("/action/z7-nfse-emitir", dependencies=_GATE)
async def rd_z7_nfse_emitir(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Emite UMA NFS-e pelo Padrão Nacional, grava a linha e guarda o XML.

    O ambiente NÃO é escolhido aqui: vem de `empresas.nfse_ambiente` (hoje 'homologacao'
    nas duas). Produção ainda exige a frase-senha em `NFSE_PRODUCAO_LIBERADA`.
    """
    from modules.fiscal.services.nfse_emissao import NFSeErro, emitir

    # Lido ANTES de qualquer commit: `_ensure` commita, o commit EXPIRA o `current_user`
    # da sessão, e ler `.email` depois disso dispara lazy-load fora do greenlet.
    quem = (getattr(current_user, "email", None) or "sistema")[:120]

    tomador = {
        "cpf_cnpj": _campo(payload, "tomador_documento"),
        "razao_social": _campo(payload, "tomador_razao"),
        "logradouro": _campo(payload, "tomador_logradouro"),
        "numero": _campo(payload, "tomador_numero") or "S/N",
        "bairro": _campo(payload, "tomador_bairro"),
        "municipio": _campo(payload, "tomador_municipio") or "Manaus",
        "codigo_municipio": _campo(payload, "tomador_cod_municipio") or "1302603",
        "uf": _campo(payload, "tomador_uf") or "AM",
        "cep": _campo(payload, "tomador_cep"),
        "email": _campo(payload, "tomador_email"),
    }
    servico = {
        "codigo_tributacao_nacional": _campo(payload, "codigo_servico"),
        "descricao": _campo(payload, "descricao"),
        "valor_servico": _campo(payload, "valor") or "0",
        "aliquota_iss": _campo(payload, "aliquota_iss") or "0",
    }
    try:
        return await emitir(
            db,
            empresa=_campo(payload, "empresa"),
            tomador=tomador,
            servico=servico,
            competencia=_campo(payload, "competencia") or None,
            dry_run=str(payload.get("dry_run", "sim")).lower() in ("sim", "true", "1"),
            quem=quem,
        )
    except NFSeErro as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": str(e), **e.details}) from e


# ─────────────────────────────────────────────────────────────────────────────────────
# TELAS
# ─────────────────────────────────────────────────────────────────────────────────────


def _sel(key: str, label: str, opcoes: list[tuple[str, str]], span: str = "span 1", valor: str | None = None) -> dict:
    d: dict[str, Any] = {
        "key": key,
        "label": label,
        "type": "select",
        "span": span,
        "options": [{"value": v, "label": r} for v, r in opcoes],
    }
    if valor is not None:
        d["value"] = valor
    return d


def _txt(key: str, label: str, span: str = "span 1", valor: str | None = None, ph: str | None = None) -> dict:
    d: dict[str, Any] = {"key": key, "label": label, "type": "text", "span": span}
    if valor is not None:
        d["value"] = valor
    if ph:
        d["ph"] = ph
    return d


async def _empresas(db: AsyncSession) -> list[dict]:
    linhas = (
        (
            await db.execute(
                text(
                    "SELECT slug, razao_social, regexp_replace(cnpj,'\\D','','g') AS cnpj,"
                    " coalesce(inscricao_municipal,'') AS im,"
                    " coalesce(nfse_ambiente,'homologacao') AS amb,"
                    " coalesce(regime_tributario::text,'') AS regime"
                    " FROM empresas WHERE status = 'ativa' ORDER BY razao_social"
                )
            )
        )
        .mappings()
        .all()
    )
    return [dict(x) for x in linhas]


#: Códigos de serviço MEDIDOS nas notas reais das duas empresas (`nfse_emitidas_nacional`,
#: 114 notas de 2026). Não são convenção: é o que cada CNPJ de fato usou no fisco.
CODIGOS_MEDIDOS = (
    ("110201", "11.02 — Vigilância, segurança ou monitoramento (usado pela Patrimonial)"),
    ("071002", "7.10 — Limpeza, manutenção e conservação de imóveis (usado pela Patrimonial)"),
    ("140601", "14.06 — Instalação e montagem de aparelhos e equipamentos (usado pela Eletrônica)"),
    ("140101", "14.01 — Lubrificação, limpeza, revisão, manutenção de máquinas (usado pela Eletrônica)"),
)


async def telas(db, out: dict | None = None) -> dict:
    from modules.fiscal.services.nfse_emissao import SERIE_PADRAO, _ensure, estado_da_trava

    await _ensure(db)
    out = out if out is not None else {}
    emps = await _empresas(db)
    trava = estado_da_trava()

    amb_txt = ", ".join(f"{e['razao_social']}: {e['amb'].upper()}" for e in emps) or "sem empresa ativa"

    # ── 1) EMITIR (reusa o id e a porta de menu que já existiam) ──────────────────────
    out["nfse-emitir-dps"] = {
        "title": "Emitir NFS-e (serviço) — Padrão Nacional",
        "sub": (
            "Emite pelo Padrão Nacional (o mesmo sistema onde as notas de 2026 desta casa já "
            f"estão). Ambiente por empresa, lido da tabela `empresas` — hoje: {amb_txt}. Em "
            "HOMOLOGAÇÃO a nota vai para a PRODUÇÃO RESTRITA do fisco "
            f"({trava['host_homologacao']}) e não tem valor fiscal. "
            "Produção está "
            + ("LIBERADA — cuidado." if trava["producao_liberada"] else "TRAVADA")
            + f" (a chave humana é a variável {trava['variavel']}); NFS-e autorizada em produção é "
            "irreversível e gera ISS devido. A empresa escolhida define CNPJ, inscrição "
            "municipal e o certificado A1 que assina. Deixe «Simulação» em SIM para conferir o "
            "XML sem transmitir — a simulação não gasta número."
        ),
        "cta": "Emitir",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "z7-nfse-emitir",
            "okMsg": "Processado — veja o resultado.",
            "showResult": True,
            "confirm": "Confere empresa, tomador, código do serviço e valor. Emitir?",
        },
        "fields": [
            _sel(
                "empresa",
                "Empresa que emite*",
                [
                    (
                        e["slug"],
                        f"{e['razao_social']} — CNPJ {e['cnpj']}"
                        + (f" · IM {e['im']}" if e["im"] else " · SEM inscrição municipal")
                        + f" · {e['amb']}",
                    )
                    for e in emps
                ],
                "span 2",
                valor=(emps[0]["slug"] if emps else None),
            ),
            _txt("tomador_documento", "Tomador — CNPJ ou CPF*", "span 1", ph="23147782000191"),
            _txt("tomador_razao", "Tomador — razão social / nome*", "span 1"),
            _txt("tomador_logradouro", "Logradouro", "span 2"),
            _txt("tomador_numero", "Número", "span 1", valor="S/N"),
            _txt("tomador_bairro", "Bairro", "span 1"),
            _txt("tomador_municipio", "Município", "span 1", valor="Manaus"),
            _txt("tomador_uf", "UF", "span 1", valor="AM"),
            _txt("tomador_cod_municipio", "Código IBGE do município", "span 1", valor="1302603"),
            _txt("tomador_cep", "CEP", "span 1", ph="69050001"),
            _txt("tomador_email", "E-mail do tomador", "span 2"),
            _sel("codigo_servico", "Código do serviço (cTribNac)*", list(CODIGOS_MEDIDOS), "span 2"),
            {
                "key": "descricao",
                "label": "Descrição do serviço na nota*",
                "type": "textarea",
                "span": "span 2",
                "ph": "Ref. competência 09/2026 — vigilância patrimonial, posto 12x36",
            },
            _txt("valor", "Valor do serviço (R$)*", "span 1", ph="1000.00"),
            _txt("competencia", "Competência (AAAA-MM)", "span 1", ph="2026-09"),
            _txt(
                "aliquota_iss",
                "Alíquota de ISS informada (0,05 = 5%)",
                "span 1",
                ph="0.05",
            ),
            _sel(
                "dry_run",
                "Simulação (não transmite)?*",
                [("sim", "Sim — só montar o XML"), ("nao", "Não — transmitir de verdade")],
                "span 1",
                valor="sim",
            ),
        ],
    }

    # ── 2) EMITIDAS pelo ERP, com o estado REAL ───────────────────────────────────────
    linhas_bd = (
        (
            await db.execute(
                text(
                    "SELECT coalesce(n.empresa_slug, e.slug, '—') AS slug, n.prestador_razao_social,"
                    " coalesce(n.ambiente,'') AS ambiente, coalesce(n.serie_rps,'') AS serie,"
                    " n.numero_rps, coalesce(n.numero_nfse,'') AS nnfse, coalesce(n.chave_acesso,'') AS chave,"
                    " coalesce(n.protocolo,'') AS protocolo, n.status, n.tomador_razao_social,"
                    " n.valor_servicos, n.iss_aliquota, n.iss_valor, n.data_emissao,"
                    " coalesce(n.mensagem_retorno,'') AS msg, coalesce(n.xml_retorno,'') AS xml_ret,"
                    " coalesce(n.xml_path,'') AS xml_path, coalesce(n.c_stat,'') AS c_stat"
                    " FROM nfses n LEFT JOIN empresas e ON e.id = n.empresa_id"
                    " WHERE coalesce(n.active, true)"
                    " ORDER BY n.created_at DESC, n.data_emissao DESC LIMIT 400"
                )
            )
        )
        .mappings()
        .all()
    )

    rows, n_prova, n_sem = [], 0, 0
    for r in linhas_bd:
        codigo, rotulo = estado_real(r["status"], r["protocolo"], r["xml_ret"])
        if codigo == "sem_comprovacao":
            n_sem += 1
        elif codigo == "autorizada":
            n_prova += 1
        num = f"{r['serie'] or '—'}/{r['numero_rps'] if r['numero_rps'] is not None else '—'}"
        if r["nnfse"]:
            num += f" · NFS-e {r['nnfse']}"
        aliq = float(r["iss_aliquota"] or 0)
        rows.append(
            {
                "cells": [
                    r["prestador_razao_social"] or r["slug"],
                    r["ambiente"] or "(não registrado)",
                    num,
                    r["chave"] or "—",
                    r["tomador_razao_social"] or "—",
                    f"R$ {float(r['valor_servicos'] or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                    # ISS: o que o FISCO devolveu. Vazio não vira 0% — vira travessão.
                    (f"{aliq * 100:.2f}%".replace(".", ",") if aliq else "—"),
                    rotulo,
                    (r["protocolo"] or "—"),
                    (r["msg"] or "—")[:180],
                ]
            }
        )

    out["z7-nfse-emitidas"] = {
        "title": "NFS-e emitidas pelo ERP",
        "sub": (
            f"{len(rows)} linha(s) · {n_prova} com prova do órgão · {n_sem} SEM comprovação. "
            "«Autorizada» aqui é afirmação sobre o FISCO: só aparece quando a linha tem o número "
            "que o órgão devolveu (nDFSe, na coluna Protocolo) E o XML <NFSe> que ele assinou. "
            "As notas de 01–02/2026, importadas em 23/03/2026, nunca foram transmitidas por este "
            "sistema — elas aparecem como «sem comprovação» e ficam intactas, porque apagar ou "
            "reescrever registro que não é desta frente é pior do que mostrá-lo como ele é. "
            f"Série padrão do ERP: {SERIE_PADRAO} — cada empresa pode declarar a sua em `empresas.nfse_serie_rps`, "
            "e precisa: sandbox, produção e o portal da contabilidade batem na MESMA homologação do fisco "
            "com o mesmo CNPJ, e série repetida volta como E0014. "
            "As notas que a empresa emite fora do ERP estão na tela «NFS-e emitidas (nacional)»."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar tomador, chave, protocolo, motivo…",
        "cols": [
            "Empresa",
            "Ambiente",
            "Série/Nº",
            "Chave de acesso",
            "Tomador",
            "Valor",
            "ISS (fisco)",
            "Estado real",
            "Protocolo (nDFSe)",
            "Retorno do órgão",
        ],
        "grid": "1.3fr 0.8fr 1fr 2.4fr 1.4fr 0.9fr 0.7fr 1.3fr 0.9fr 2fr",
        "rows": rows,
    }
    return out
