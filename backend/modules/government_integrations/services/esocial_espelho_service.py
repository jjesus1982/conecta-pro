"""
Serviço — ESPELHO OFICIAL do eSocial (Missão D).

Baixa os eventos JÁ TRANSMITIDOS do empregador (CNPJ 35.710.481/0001-03) para
dentro do ERP, com dois objetivos:
1. HISTÓRICO COM FIDELIDADE — o XML integral de cada evento fica em
   esocial_eventos_espelho (fonte: webservices read-only do governo).
2. ANTI-DUPLICIDADE — detectar_ja_transmitidos() casa os eventos do governo
   com os registros locais (gp_asos ↔ S-2220, sst_afastamentos ↔ S-2230,
   gp_cats ↔ S-2210) e marca espelho_recibo/espelho_fonte — o pipeline de
   transmissão NÃO deve retransmitir o que já existe no governo.

ORÇAMENTO DO GOVERNO (Manual do Desenvolvedor 7.7.7/7.8.7 — imposto pelo
webservice, respeitado ANTES de chamar):
- 10 acessos/dia somando consulta identificadores + download;
- bloqueio total entre os dias 1 e 7 de cada mês;
- sem paralelismo; intervalo máx. 31 dias por consulta; 50 itens por resposta.
Por isso a enumeração é uma FILA de janelas CPF×período (esocial_espelho_janelas)
consumida aos poucos pelo beat semanal, e cada chamada real é logada em
esocial_espelho_acessos (base do orçamento).

HONESTIDADE: tudo que está em esocial_eventos_espelho veio do governo —
nada é fabricado. Falha/limite → status honesto no retorno e no log.
"""

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Relógio do eSocial = Brasília. O container roda em UTC — SEMPRE converter
# antes de formatar dtIni/dtFim (senão o "agora-1h" do governo estoura em 409).
TZ_GOV = ZoneInfo("America/Sao_Paulo")

TIPOS_PRIORITARIOS = ["S-2210", "S-2220", "S-2230", "S-2240", "S-2200", "S-2299"]

# tag do evento (evtXXXX) → tipo S-XXXX (leiautes eSocial S-1.x)
TAG_PARA_TIPO = {
    "evtCAT": "S-2210",
    "evtMonit": "S-2220",
    "evtAfastTemp": "S-2230",
    "evtExpRisco": "S-2240",
    "evtAdmissao": "S-2200",
    "evtDeslig": "S-2299",
    "evtAdmPrelim": "S-2190",
    "evtAltCadastral": "S-2205",
    "evtAltContratual": "S-2206",
    "evtReintegr": "S-2298",
    "evtAvPrevio": "S-2250",
    "evtConvInterm": "S-2260",
    "evtTSVInicio": "S-2300",
    "evtTSVAltContr": "S-2306",
    "evtTSVTermino": "S-2399",
    "evtCdBenPrRP": "S-2400",
    "evtRemun": "S-1200",
    "evtRmnRPPS": "S-1202",
    "evtBenPrRP": "S-1207",
    "evtPgtos": "S-1210",
    "evtComProd": "S-1260",
    "evtContratAvNP": "S-1270",
    "evtInfoComplPer": "S-1280",
    "evtReabreEvPer": "S-1298",
    "evtFechaEvPer": "S-1299",
    "evtInfoEmpregador": "S-1000",
    "evtTabEstab": "S-1005",
    "evtTabRubrica": "S-1010",
    "evtTabLotacao": "S-1020",
    "evtTabProcesso": "S-1070",
    "evtExclusao": "S-3000",
    "evtBasesTrab": "S-5001",
    "evtIrrfBenef": "S-5002",
    "evtBasesFGTS": "S-5003",
    "evtCS": "S-5011",
    "evtIrrf": "S-5012",
    "evtFGTS": "S-5013",
}

# campos de data-fato por prioridade (primeiro que aparecer no XML vence)
_CAMPOS_DT_EVENTO = ["dtAcid", "dtAso", "dtIniAfast", "dtIniCondicao", "dtAdm", "dtDeslig", "dtNascto"]


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


async def _carregar_empregador_cnpj(db: Any) -> str:
    row = (
        await db.execute(
            text(
                "SELECT cnpj FROM empresas WHERE cnpj IS NOT NULL AND btrim(cnpj) <> '' "
                "ORDER BY CASE WHEN cnpj LIKE '35.710.481%' THEN 0 ELSE 1 END LIMIT 1"
            )
        )
    ).scalar()
    if not row:
        raise ValueError("Espelho eSocial: nenhum empregador com CNPJ real na tabela empresas.")
    return _digits(row)


# ============================================================================
# Orçamento (10 acessos/dia — governo)
# ============================================================================


async def acessos_hoje(db: Any) -> int:
    return (
        await db.execute(
            text("SELECT count(*) FROM esocial_espelho_acessos WHERE criado_em::date = CURRENT_DATE")
        )
    ).scalar() or 0


async def _registrar_acesso(
    db: Any, servico: str, parametros: dict, cd: str, desc: str, qtde: int, http_status: int
) -> None:
    await db.execute(
        text(
            "INSERT INTO esocial_espelho_acessos "
            "(servico, parametros, cd_resposta, desc_resposta, qtde_retornada, http_status) "
            "VALUES (:s, CAST(:p AS jsonb), :cd, :d, :q, :h)"
        ),
        {"s": servico, "p": json.dumps(parametros), "cd": cd, "d": desc[:2000], "q": qtde, "h": http_status},
    )
    await db.commit()


# ============================================================================
# Parse do XML do evento baixado
# ============================================================================


def parse_evento_xml(xml: str) -> dict[str, Any]:
    """Extrai tipo/cpf/data-fato/recibo/recepção/transmissor do XML baixado.

    O arquivo devolvido pelo download contém o evento (eSocial/evtXXXX) e,
    quando processado, também o retorno com recibo (nrRecibo/dhRecepcao).
    Campos ausentes ficam None — nunca fabricados.
    """
    from defusedxml import ElementTree as DET

    out: dict[str, Any] = {
        "tipo": None,
        "cpf": None,
        "dt_evento": None,
        "nr_recibo": None,
        "dt_recepcao": None,
        "transmissor_cnpj": None,
        "id_evento": None,
        "ver_proc": None,  # software transmissor (ex.: 'INDEXMED 2.0.0' = MB Consultoria)
        "per_apur": None,
    }
    try:
        root = DET.fromstring(xml.encode() if isinstance(xml, str) else xml)
    except Exception as e:  # noqa: BLE001
        logger.warning("Espelho: XML de evento não parseia: %s", e)
        return out

    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in TAG_PARA_TIPO and out["tipo"] is None:
            out["tipo"] = TAG_PARA_TIPO[tag]
            out["id_evento"] = el.get("Id") or el.get("id")
        elif tag == "cpfTrab" and out["cpf"] is None:
            out["cpf"] = _digits(el.text)
        elif tag in _CAMPOS_DT_EVENTO and out["dt_evento"] is None and (el.text or "").strip():
            out["dt_evento"] = el.text.strip()[:10]
        elif tag == "nrRecibo" and out["nr_recibo"] is None:
            out["nr_recibo"] = (el.text or "").strip()
        elif tag in ("dhRecepcao", "dhProcessamento") and out["dt_recepcao"] is None:
            out["dt_recepcao"] = (el.text or "").strip() or None
        elif tag == "nrInscTransmissor" and out["transmissor_cnpj"] is None:
            out["transmissor_cnpj"] = _digits(el.text)
        elif tag == "verProc" and out["ver_proc"] is None:
            out["ver_proc"] = (el.text or "").strip()[:40] or None
        elif tag == "perApur" and out["per_apur"] is None:
            out["per_apur"] = (el.text or "").strip() or None
    # eventos periódicos não têm data-fato pontual: usa a competência (perApur)
    if out["dt_evento"] is None and out["per_apur"] and re.fullmatch(r"\d{4}-\d{2}", out["per_apur"]):
        out["dt_evento"] = f"{out['per_apur']}-01"
    return out


# ============================================================================
# Upserts no espelho
# ============================================================================


async def _upsert_identificador(db: Any, id_evento: str, nr_recibo: str, cpf: str | None, fonte: str) -> bool:
    """Insere identificador se novo. Retorna True se inseriu."""
    r = await db.execute(
        text(
            "INSERT INTO esocial_eventos_espelho (id_evento, nr_recibo, cpf_trabalhador, fonte_consulta) "
            "VALUES (:i, :r, :c, :f) ON CONFLICT (id_evento) DO NOTHING"
        ),
        {"i": id_evento, "r": nr_recibo or None, "c": cpf, "f": fonte},
    )
    return r.rowcount > 0


async def _gravar_xml_baixado(db: Any, id_evento: str, xml: str, fonte: str) -> dict[str, Any]:
    """Grava o XML integral + campos extraídos. Upsert por id_evento."""
    meta = parse_evento_xml(xml)
    idv = id_evento or meta["id_evento"]
    if not idv:
        return {"ok": False, "erro": "XML sem Id de evento"}
    dt_recepcao = None
    if meta["dt_recepcao"]:
        try:
            dt_recepcao = datetime.fromisoformat(meta["dt_recepcao"])
            if dt_recepcao.tzinfo is None:
                dt_recepcao = dt_recepcao.replace(tzinfo=TZ_GOV)  # governo = Brasília
        except ValueError:
            dt_recepcao = None
    dt_evento = None
    if meta["dt_evento"]:
        try:
            dt_evento = date.fromisoformat(meta["dt_evento"])
        except ValueError:
            dt_evento = None
    await db.execute(
        text(
            "INSERT INTO esocial_eventos_espelho "
            "(id_evento, tipo, cpf_trabalhador, nr_recibo, dt_recepcao, dt_evento, transmissor_cnpj, "
            " ver_proc, xml_completo, baixado_em, download_status, fonte_consulta) "
            "VALUES (:i, :t, :c, :r, :dr, :de, :tr, :vp, :x, now(), 'ok', :f) "
            "ON CONFLICT (id_evento) DO UPDATE SET "
            " tipo = COALESCE(EXCLUDED.tipo, esocial_eventos_espelho.tipo), "
            " cpf_trabalhador = COALESCE(EXCLUDED.cpf_trabalhador, esocial_eventos_espelho.cpf_trabalhador), "
            " nr_recibo = COALESCE(esocial_eventos_espelho.nr_recibo, EXCLUDED.nr_recibo), "
            " dt_recepcao = COALESCE(EXCLUDED.dt_recepcao, esocial_eventos_espelho.dt_recepcao), "
            " dt_evento = COALESCE(EXCLUDED.dt_evento, esocial_eventos_espelho.dt_evento), "
            " transmissor_cnpj = COALESCE(EXCLUDED.transmissor_cnpj, esocial_eventos_espelho.transmissor_cnpj), "
            " ver_proc = COALESCE(EXCLUDED.ver_proc, esocial_eventos_espelho.ver_proc), "
            " xml_completo = EXCLUDED.xml_completo, baixado_em = now(), download_status = 'ok', "
            " updated_at = now()"
        ),
        {
            "i": idv,
            "t": meta["tipo"],
            "c": meta["cpf"],
            "r": meta["nr_recibo"],
            "dr": dt_recepcao,
            "de": dt_evento,
            "tr": meta["transmissor_cnpj"],
            "vp": meta["ver_proc"],
            "x": xml,
            "f": fonte,
        },
    )
    return {"ok": True, "tipo": meta["tipo"], "cpf": meta["cpf"], "nr_recibo": meta["nr_recibo"]}


# ============================================================================
# Fila de janelas (enumeração por CPF, 31 dias máx por consulta)
# ============================================================================


async def gerar_janelas(
    db: Any, periodo_ini: date, periodo_fim: date, cpfs: list[str] | None = None
) -> int:
    """Cria janelas pendentes CPF×(31 dias) para o período de RECEPÇÃO dado.

    CPFs default: funcionários com registro SST local (CAT/ASO/afastamento) —
    são os que decidem o backlog — na frente; demais employees depois.
    """
    if cpfs is None:
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT regexp_replace(e.cpf, '\\D', '', 'g') AS cpf, prio FROM ("
                    "  SELECT employee_id::text AS eid, 0 AS prio FROM gp_cats "
                    "  UNION SELECT employee_id::text, 0 FROM gp_asos WHERE status = 'realizado' "
                    "  UNION SELECT employee_id::text, 0 FROM sst_afastamentos "
                    "  UNION SELECT id::text, 1 FROM employees WHERE status = 'ativo' OR status IS NULL"
                    ") s JOIN employees e ON e.id::text = s.eid "
                    "WHERE e.cpf IS NOT NULL AND length(regexp_replace(e.cpf, '\\D', '', 'g')) = 11 "
                    # PJ não tem obrigação SST/eSocial como empregado — fora do espelho.
                    "AND COALESCE(LOWER(e.tipo_contrato),'') <> 'pj' "
                    "ORDER BY prio, cpf"
                )
            )
        ).mappings().all()
        cpfs = list(dict.fromkeys(r["cpf"] for r in rows))
    else:
        cpfs = [_digits(c) for c in cpfs]

    criadas = 0
    for cpf in cpfs:
        ini = periodo_ini
        while ini <= periodo_fim:
            fim = min(ini + timedelta(days=30), periodo_fim)
            r = await db.execute(
                text(
                    "INSERT INTO esocial_espelho_janelas (cpf, dt_ini, dt_fim) "
                    "VALUES (:c, :i, :f) ON CONFLICT (cpf, dt_ini, dt_fim) DO NOTHING"
                ),
                {
                    "c": cpf,
                    "i": datetime(ini.year, ini.month, ini.day, tzinfo=TZ_GOV),
                    "f": datetime(fim.year, fim.month, fim.day, 23, 59, 59, tzinfo=TZ_GOV),
                },
            )
            criadas += r.rowcount
            ini = fim + timedelta(days=1)
    await db.commit()
    return criadas


# ============================================================================
# Sincronização (consome orçamento REAL do governo)
# ============================================================================


async def sincronizar_espelho(
    tipos: list[str] | None = None,
    periodo: str | None = None,
    cpfs: list[str] | None = None,
    max_acessos: int = 8,
    max_downloads: int = 50,
) -> dict[str, Any]:
    """Sincroniza o espelho: consulta identificadores pendentes + baixa XMLs.

    - tipos: prioridade de correlação (default TIPOS_PRIORITARIOS). A consulta
      por trabalhador devolve TODOS os não-periódicos do CPF — o espelho guarda
      tudo (histórico com fidelidade); tipos só afeta a ordem de downloads.
    - periodo: 'AAAA' ou 'AAAA-MM' — gera janelas de recepção para esse período.
    - max_acessos: teto DESTA execução (o teto do dia é 10, do governo).
    """
    from core.database import async_session_factory
    from modules.government_integrations.core.esocial_eventos_client import (
        ESocialEventosClient,
        EspelhoClientError,
        MAX_ITENS_DOWNLOAD,
        dia_bloqueado,
        MAX_ACESSOS_DIA,
    )

    resumo: dict[str, Any] = {
        "status": "ok",
        "acessos_usados": 0,
        "janelas_consultadas": 0,
        "identificadores_novos": 0,
        "xmls_baixados": 0,
        "correlacoes": {},
        "avisos": [],
    }

    if dia_bloqueado():
        resumo["status"] = "bloqueado_dias_1_7"
        resumo["avisos"].append(
            "O eSocial bloqueia consulta/download de eventos entre os dias 1 e 7 de cada mês. Nada foi chamado."
        )
        return resumo

    tipos = tipos or TIPOS_PRIORITARIOS
    async with async_session_factory() as db:
        usados = await acessos_hoje(db)
        orcamento = min(max_acessos, MAX_ACESSOS_DIA - usados)
        if orcamento <= 0:
            resumo["status"] = "orcamento_esgotado"
            resumo["avisos"].append(
                f"Orçamento diário do governo esgotado ({usados}/{MAX_ACESSOS_DIA} acessos hoje)."
            )
            return resumo

        cnpj = await _carregar_empregador_cnpj(db)

        # 1) gerar janelas para o período pedido
        if periodo:
            if re.fullmatch(r"\d{4}", periodo):
                p_ini, p_fim = date(int(periodo), 1, 1), min(date(int(periodo), 12, 31), date.today())
            elif re.fullmatch(r"\d{4}-\d{2}", periodo):
                ano, mes = int(periodo[:4]), int(periodo[5:7])
                prox = date(ano + (mes == 12), (mes % 12) + 1, 1)
                p_ini, p_fim = date(ano, mes, 1), min(prox - timedelta(days=1), date.today())
            else:
                raise ValueError(f"periodo inválido: {periodo!r} (use AAAA ou AAAA-MM)")
            novas = await gerar_janelas(db, p_ini, p_fim, cpfs)
            resumo["janelas_novas"] = novas

        client = ESocialEventosClient()

        # 2) consultar janelas pendentes (1 acesso cada)
        filtro_cpf = ""
        params_j: dict[str, Any] = {}
        if cpfs:
            filtro_cpf = "AND cpf = ANY(:cpfs)"
            params_j["cpfs"] = [_digits(c) for c in cpfs]
        janelas = (
            await db.execute(
                text(
                    "SELECT id, cpf, dt_ini, dt_fim FROM esocial_espelho_janelas "
                    f"WHERE status = 'pendente' {filtro_cpf} "
                    "ORDER BY dt_ini DESC, cpf LIMIT :lim"
                ),
                {**params_j, "lim": max(orcamento - 1, 0) or 1},
            )
        ).mappings().all()

        for j in janelas:
            if resumo["acessos_usados"] >= orcamento - 1:  # reserva 1 acesso p/ download
                break
            ini_gov = j["dt_ini"].astimezone(TZ_GOV)
            dt_ini = ini_gov.strftime("%Y-%m-%dT%H:%M:%S")
            # dtFim deve ser <= agora-1h no relógio do GOVERNO (Brasília)
            teto = datetime.now(TZ_GOV) - timedelta(hours=1, minutes=5)
            dt_fim_dt = min(j["dt_fim"].astimezone(TZ_GOV), teto)
            if dt_fim_dt <= ini_gov:
                continue  # janela ainda no futuro
            dt_fim = dt_fim_dt.strftime("%Y-%m-%dT%H:%M:%S")
            try:
                resp = await asyncio.to_thread(
                    client.consultar_identificadores_trabalhador, cnpj, j["cpf"], dt_ini, dt_fim
                )
            except EspelhoClientError as e:
                resumo["avisos"].append(f"Janela {j['cpf']} {dt_ini}: falha de infra: {e}")
                await _registrar_acesso(
                    db, "consulta_trabalhador", {"cpf": j["cpf"], "dt_ini": dt_ini, "dt_fim": dt_fim},
                    "", f"infra: {e}", 0, 0,
                )
                resumo["acessos_usados"] += 1
                continue

            resumo["acessos_usados"] += 1
            await _registrar_acesso(
                db, "consulta_trabalhador", {"cpf": j["cpf"], "dt_ini": dt_ini, "dt_fim": dt_fim},
                resp.cd_resposta, resp.desc_resposta, len(resp.itens), resp.http_status,
            )

            if resp.cd_resposta in ("403", "404", "405"):
                # limite/bloqueio do governo — para TUDO honestamente
                resumo["status"] = "limitado_pelo_governo"
                resumo["avisos"].append(f"Governo: [{resp.cd_resposta}] {resp.desc_resposta}")
                await db.commit()
                return resumo

            if resp.sucesso:
                for item in resp.itens:
                    if item["id"] and await _upsert_identificador(
                        db, item["id"], item["nr_recibo"], j["cpf"], "consulta_trabalhador"
                    ):
                        resumo["identificadores_novos"] += 1
                # paginação: mais de 50 → nova janela a partir do último retornado
                if resp.qtde_total > len(resp.itens) and resp.dh_ultimo_evento:
                    try:
                        prox_ini = datetime.fromisoformat(resp.dh_ultimo_evento)
                        if prox_ini.tzinfo is None:
                            prox_ini = prox_ini.replace(tzinfo=TZ_GOV)
                        await db.execute(
                            text(
                                "INSERT INTO esocial_espelho_janelas (cpf, dt_ini, dt_fim) "
                                "VALUES (:c, :i, :f) ON CONFLICT (cpf, dt_ini, dt_fim) DO NOTHING"
                            ),
                            {"c": j["cpf"], "i": prox_ini, "f": j["dt_fim"]},
                        )
                    except ValueError:
                        resumo["avisos"].append(
                            f"Janela {j['cpf']}: dhUltimoEvtRetornado não parseia: {resp.dh_ultimo_evento!r}"
                        )
                novo_status = "consultada"
            elif resp.vazio:
                novo_status = "vazia"
            else:
                novo_status = "erro"
                resumo["avisos"].append(
                    f"Janela {j['cpf']} {dt_ini}: [{resp.cd_resposta}] {resp.desc_resposta}"
                )
            await db.execute(
                text(
                    "UPDATE esocial_espelho_janelas SET status = :s, qtde_encontrada = :q, "
                    "cd_resposta = :cd, consultada_em = now() WHERE id = :i"
                ),
                {"s": novo_status, "q": resp.qtde_total or len(resp.itens), "cd": resp.cd_resposta, "i": j["id"]},
            )
            await db.commit()
            resumo["janelas_consultadas"] += 1

        # 3) baixar XMLs pendentes (lotes de até 50 ids = 1 acesso cada)
        while resumo["acessos_usados"] < orcamento:
            pendentes = (
                await db.execute(
                    text(
                        "SELECT id_evento, tipo FROM esocial_eventos_espelho "
                        "WHERE xml_completo IS NULL AND download_status IS NULL "
                        "ORDER BY created_at LIMIT :lim"
                    ),
                    {"lim": min(max_downloads, MAX_ITENS_DOWNLOAD)},
                )
            ).mappings().all()
            if not pendentes:
                break
            ids = [p["id_evento"] for p in pendentes]
            try:
                dresp = await asyncio.to_thread(client.solicitar_download_por_id, cnpj, ids)
            except EspelhoClientError as e:
                resumo["avisos"].append(f"Download: falha de infra: {e}")
                await _registrar_acesso(db, "download_id", {"ids": len(ids)}, "", f"infra: {e}", 0, 0)
                resumo["acessos_usados"] += 1
                break
            resumo["acessos_usados"] += 1
            await _registrar_acesso(
                db, "download_id", {"ids": len(ids)},
                dresp.cd_resposta, dresp.desc_resposta, len(dresp.arquivos), dresp.http_status,
            )
            if dresp.cd_resposta in ("403", "404", "405"):
                resumo["status"] = "limitado_pelo_governo"
                resumo["avisos"].append(f"Governo: [{dresp.cd_resposta}] {dresp.desc_resposta}")
                break
            if not dresp.sucesso:
                resumo["avisos"].append(f"Download: [{dresp.cd_resposta}] {dresp.desc_resposta}")
                break
            baixados_ids: set[str] = set()
            for arq in dresp.arquivos:
                if arq["cd"] == "201" and arq["xml"]:
                    res = await _gravar_xml_baixado(db, arq.get("id_evento") or "", arq["xml"], "download_id")
                    if res.get("ok"):
                        resumo["xmls_baixados"] += 1
                        baixados_ids.add(arq.get("id_evento") or "")
            # ids que NÃO vieram (ex.: 401 p/ ids gerados pelo governo — totalizadores):
            # se têm recibo conhecido, tentam na fase por-recibo; senão, param honesto.
            for pid in ids:
                if pid not in baixados_ids:
                    await db.execute(
                        text(
                            "UPDATE esocial_eventos_espelho SET download_status = "
                            "CASE WHEN nr_recibo IS NOT NULL THEN 'tentar_recibo' ELSE 'nao_encontrado' END, "
                            "download_erro = :e, updated_at = now() "
                            "WHERE id_evento = :i AND xml_completo IS NULL"
                        ),
                        {
                            "i": pid,
                            "e": "; ".join(
                                f"[{a['cd']}] {a['desc']}" for a in dresp.arquivos if a["cd"] != "201"
                            )[:500]
                            or None,
                        },
                    )
            await db.commit()

        # 3b) fallback por NR RECIBO (ids não-baixáveis por Id, ex. totalizadores)
        while resumo["acessos_usados"] < orcamento:
            pend_rec = (
                await db.execute(
                    text(
                        "SELECT id_evento, nr_recibo FROM esocial_eventos_espelho "
                        "WHERE xml_completo IS NULL AND download_status = 'tentar_recibo' "
                        "AND nr_recibo IS NOT NULL ORDER BY created_at LIMIT :lim"
                    ),
                    {"lim": min(max_downloads, MAX_ITENS_DOWNLOAD)},
                )
            ).mappings().all()
            if not pend_rec:
                break
            recibos = [p["nr_recibo"] for p in pend_rec]
            try:
                rresp = await asyncio.to_thread(client.solicitar_download_por_recibo, cnpj, recibos)
            except EspelhoClientError as e:
                resumo["avisos"].append(f"Download por recibo: falha de infra: {e}")
                await _registrar_acesso(db, "download_recibo", {"recibos": len(recibos)}, "", f"infra: {e}", 0, 0)
                resumo["acessos_usados"] += 1
                break
            resumo["acessos_usados"] += 1
            await _registrar_acesso(
                db, "download_recibo", {"recibos": len(recibos)},
                rresp.cd_resposta, rresp.desc_resposta, len(rresp.arquivos), rresp.http_status,
            )
            if rresp.cd_resposta in ("403", "404", "405"):
                resumo["status"] = "limitado_pelo_governo"
                resumo["avisos"].append(f"Governo: [{rresp.cd_resposta}] {rresp.desc_resposta}")
                break
            baixados_rec: set[str] = set()
            if rresp.sucesso:
                for arq in rresp.arquivos:
                    if arq["cd"] == "201" and arq["xml"]:
                        res = await _gravar_xml_baixado(db, arq.get("id_evento") or "", arq["xml"], "download_recibo")
                        if res.get("ok"):
                            resumo["xmls_baixados"] += 1
                            if res.get("nr_recibo"):
                                baixados_rec.add(res["nr_recibo"])
                            if arq.get("id_evento"):
                                baixados_rec.add(arq["id_evento"])
            for p in pend_rec:
                if p["nr_recibo"] not in baixados_rec and p["id_evento"] not in baixados_rec:
                    await db.execute(
                        text(
                            "UPDATE esocial_eventos_espelho SET download_status = 'nao_encontrado', "
                            "updated_at = now() WHERE id_evento = :i AND xml_completo IS NULL"
                        ),
                        {"i": p["id_evento"]},
                    )
            await db.commit()
            if not rresp.sucesso:
                resumo["avisos"].append(f"Download por recibo: [{rresp.cd_resposta}] {rresp.desc_resposta}")
                break

        # 4) correlação anti-duplicidade (não gasta acesso — é local)
        resumo["correlacoes"] = await detectar_ja_transmitidos(db)
        await db.commit()

    return resumo


async def baixar_por_recibos(recibos: list[str]) -> dict[str, Any]:
    """Baixa eventos por número de recibo (1 acesso). Ex.: prova da CAT da Cintia."""
    from core.database import async_session_factory
    from modules.government_integrations.core.esocial_eventos_client import (
        ESocialEventosClient,
        dia_bloqueado,
    )

    if dia_bloqueado():
        return {"status": "bloqueado_dias_1_7"}

    out: dict[str, Any] = {"status": "ok", "baixados": 0, "arquivos": []}
    async with async_session_factory() as db:
        cnpj = await _carregar_empregador_cnpj(db)
        client = ESocialEventosClient()
        resp = await asyncio.to_thread(client.solicitar_download_por_recibo, cnpj, recibos)
        await _registrar_acesso(
            db, "download_recibo", {"recibos": recibos},
            resp.cd_resposta, resp.desc_resposta, len(resp.arquivos), resp.http_status,
        )
        out["cd_resposta"] = resp.cd_resposta
        out["desc_resposta"] = resp.desc_resposta
        for arq in resp.arquivos:
            if arq["cd"] == "201" and arq["xml"]:
                res = await _gravar_xml_baixado(db, arq.get("id_evento") or "", arq["xml"], "download_recibo")
                if res.get("ok"):
                    out["baixados"] += 1
                out["arquivos"].append(res)
            else:
                out["arquivos"].append({"ok": False, "cd": arq["cd"], "desc": arq["desc"]})
        out["correlacoes"] = await detectar_ja_transmitidos(db)
        await db.commit()
    return out


# ============================================================================
# Correlação anti-duplicidade (local, zero acesso ao governo)
# ============================================================================


async def detectar_ja_transmitidos(db: Any) -> dict[str, int]:
    """Marca registros locais cujo evento JÁ EXISTE no governo.

    Casamento (CPF + data-fato):
    - gp_asos       ↔ S-2220 por CPF + data_realizacao == dtAso
    - sst_afastamentos ↔ S-2230 por CPF + data_inicio == dtIniAfast
    - gp_cats       ↔ S-2210 por CPF + data_acidente == dtAcid
    Marca espelho_recibo + espelho_fonte (CNPJ do transmissor se conhecido).
    NÃO toca esocial_status (que rastreia a NOSSA transmissão).

    EXCLUSÕES (provado em produção 2026-07-08, caso Cintia): eventos podem ter
    sido EXCLUÍDOS via S-3000 e retransmitidos — um recibo referenciado em
    <nrRecEvt> de um S-3000 NÃO vale mais. A correlação ignora esses recibos
    (e desfaz marcações antigas que apontem para recibo excluído).
    """
    res: dict[str, int] = {}

    # recibos excluídos por S-3000 (extraídos dos XMLs do próprio espelho)
    cte_excluidos = (
        "WITH excluidos AS ("
        " SELECT DISTINCT substring(xml_completo from '<nrRecEvt>([0-9.]+)</nrRecEvt>') AS rec"
        " FROM esocial_eventos_espelho WHERE tipo = 'S-3000' AND xml_completo IS NOT NULL"
        ") "
    )

    # desfaz marcações que apontem para recibo excluído
    for tabela in ("gp_asos", "sst_afastamentos", "gp_cats"):
        await db.execute(
            text(
                cte_excluidos
                + f"UPDATE {tabela} SET espelho_recibo = NULL, espelho_fonte = NULL "
                "WHERE espelho_recibo IN (SELECT rec FROM excluidos WHERE rec IS NOT NULL)"
            )
        )

    nao_excluido = (
        "AND NOT EXISTS (SELECT 1 FROM esocial_eventos_espelho ex WHERE ex.tipo = 'S-3000' "
        "AND ex.xml_completo LIKE '%<nrRecEvt>' || esp.nr_recibo || '</nrRecEvt>%') "
    )

    r = await db.execute(
        text(
            "UPDATE gp_asos a SET espelho_recibo = esp.nr_recibo, "
            " espelho_fonte = COALESCE(NULLIF(esp.transmissor_cnpj, ''), NULLIF(esp.ver_proc, ''), 'espelho_esocial') "
            "FROM esocial_eventos_espelho esp "
            "JOIN employees e ON regexp_replace(e.cpf, '\\D', '', 'g') = esp.cpf_trabalhador "
            "WHERE esp.tipo = 'S-2220' AND esp.nr_recibo IS NOT NULL AND esp.dt_evento IS NOT NULL "
            "AND a.employee_id = e.id AND a.data_realizacao = esp.dt_evento "
            + nao_excluido
            + "AND a.espelho_recibo IS DISTINCT FROM esp.nr_recibo"
        )
    )
    res["asos_s2220"] = r.rowcount

    r = await db.execute(
        text(
            "UPDATE sst_afastamentos a SET espelho_recibo = esp.nr_recibo, "
            " espelho_fonte = COALESCE(NULLIF(esp.transmissor_cnpj, ''), NULLIF(esp.ver_proc, ''), 'espelho_esocial') "
            "FROM esocial_eventos_espelho esp "
            "JOIN employees e ON regexp_replace(e.cpf, '\\D', '', 'g') = esp.cpf_trabalhador "
            "WHERE esp.tipo = 'S-2230' AND esp.nr_recibo IS NOT NULL AND esp.dt_evento IS NOT NULL "
            "AND a.employee_id = e.id AND a.data_inicio = esp.dt_evento "
            + nao_excluido
            + "AND a.espelho_recibo IS DISTINCT FROM esp.nr_recibo"
        )
    )
    res["afastamentos_s2230"] = r.rowcount

    r = await db.execute(
        text(
            "UPDATE gp_cats c SET espelho_recibo = esp.nr_recibo, "
            " espelho_fonte = COALESCE(NULLIF(esp.transmissor_cnpj, ''), NULLIF(esp.ver_proc, ''), 'espelho_esocial') "
            "FROM esocial_eventos_espelho esp "
            "JOIN employees e ON regexp_replace(e.cpf, '\\D', '', 'g') = esp.cpf_trabalhador "
            "WHERE esp.tipo = 'S-2210' AND esp.nr_recibo IS NOT NULL AND esp.dt_evento IS NOT NULL "
            "AND c.employee_id = e.id::text AND c.data_acidente = esp.dt_evento "
            + nao_excluido
            + "AND c.espelho_recibo IS DISTINCT FROM esp.nr_recibo"
        )
    )
    res["cats_s2210"] = r.rowcount
    return res


# ============================================================================
# Leituras (resumo + timeline)
# ============================================================================


async def resumo_espelho(db: Any) -> dict[str, Any]:
    por_tipo_ano = (
        await db.execute(
            text(
                "SELECT COALESCE(tipo, '(id_sem_xml)') AS tipo, "
                " COALESCE(to_char(COALESCE(dt_evento, dt_recepcao::date), 'YYYY'), '?') AS ano, "
                " count(*) AS qtde, count(*) FILTER (WHERE xml_completo IS NOT NULL) AS com_xml "
                "FROM esocial_eventos_espelho GROUP BY 1, 2 ORDER BY 1, 2"
            )
        )
    ).mappings().all()
    janelas = (
        await db.execute(
            text("SELECT status, count(*) AS qtde FROM esocial_espelho_janelas GROUP BY status")
        )
    ).mappings().all()
    correl = (
        await db.execute(
            text(
                "SELECT "
                " (SELECT count(*) FROM gp_asos WHERE espelho_recibo IS NOT NULL) AS asos_ja_no_governo, "
                " (SELECT count(*) FROM gp_asos WHERE status = 'realizado' AND espelho_recibo IS NULL "
                "   AND recibo_s2220 IS NULL) AS asos_backlog_real, "
                " (SELECT count(*) FROM sst_afastamentos WHERE espelho_recibo IS NOT NULL) AS afast_ja_no_governo, "
                " (SELECT count(*) FROM sst_afastamentos WHERE espelho_recibo IS NULL "
                "   AND recibo_s2230 IS NULL) AS afast_backlog_real, "
                " (SELECT count(*) FROM gp_cats WHERE espelho_recibo IS NOT NULL) AS cats_ja_no_governo"
            )
        )
    ).mappings().first()
    return {
        "por_tipo_ano": [dict(r) for r in por_tipo_ano],
        "janelas": {r["status"]: r["qtde"] for r in janelas},
        "acessos_hoje": await acessos_hoje(db),
        "limite_diario_governo": 10,
        "anti_duplicidade": dict(correl) if correl else {},
    }


async def timeline_cpf(db: Any, cpf: str) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                "SELECT id_evento, tipo, nr_recibo, dt_evento, dt_recepcao, transmissor_cnpj, "
                " (xml_completo IS NOT NULL) AS xml_disponivel, baixado_em "
                "FROM esocial_eventos_espelho WHERE cpf_trabalhador = :c "
                "ORDER BY COALESCE(dt_evento, dt_recepcao::date) NULLS LAST, id_evento"
            ),
            {"c": _digits(cpf)},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
