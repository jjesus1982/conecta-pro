"""GEDEON — Orquestrador mensal: monta o kit documental de TODOS os condomínios.

Amarra os motores (que rodam DENTRO do container) numa execução única, idempotente,
com relatório por etapa/condomínio:
  Onvio (folha+contracheques+guias) → Inter (salário+INSS+VA/VT+boletos+extrato) → NFS-e (DANFSe).

Cada etapa é isolada por try/except — uma falha não derruba as demais; o relatório
diz o que entrou e o que ficou pendente (ex.: sessão Onvio expirada, rate-limit Inter).

NÃO cobre (dependem do HOST, fora do container): ponto assinado (robô Sólides) e
atribuição de VA/VT por condomínio (portal Benefícios). O relatório sinaliza isso.

Competência no formato 'MM.YYYY' (ex.: '05.2026'). O kit do mês seguinte ("Junho")
recebe a competência de maio (salário pago em arrears).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Condomínios canônicos do kit (não-Innovare — os que o GEDEON monta hoje).
# Innovare (Laranjeiras, Prime Arena) entram quando suas folhas estiverem no Onvio.
CONDOMINIOS_PADRAO = [
    "IDEAL FLORES",
    "MICHELANGELO",
    "MIRANTE",
    "VILLA PÁSSAROS",
    "VILLA DEI FIORI",
    "LARANJEIRAS",
    "PRIME ARENA",
]


def _mes_kit(competencia: str) -> tuple[int, int]:
    """Mês do KIT = competência + 1 (kit do trabalho de maio = 'Junho'). Devolve (ano, mes)."""
    mes, ano = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    return (ano, mes + 1) if mes < 12 else (ano + 1, 1)


def _mes_emissao_nfse(competencia: str) -> str:
    """NFS-e/Boleto do kit = mês do KIT (competência+1). Ex.: kit do trabalho de maio (05.2026)
    leva a NFS de JUNHO ('2026-06') — serviço faturado no mês de entrega, pago no início do
    mês seguinte. (folha/VT/impostos são da competência; a NOTA é do mês do kit.)"""
    a, m = _mes_kit(competencia)
    return f"{a}-{m:02d}"


def _range_boletos(competencia: str) -> tuple[str, str]:
    """Janela de emissão dos boletos do kit = mês do KIT (competência+1) + folga até dia 15 do
    mês seguinte (boleto da nota emitida no fim do mês, com vencimento no início do próximo)."""
    a, m = _mes_kit(competencia)
    ini = f"{a}-{m:02d}-01"
    a2, m2 = (a, m + 1) if m < 12 else (a + 1, 1)
    return ini, f"{a2}-{m2:02d}-15"


def _prog_writer(task_id: str | None, competencia: str):
    """Devolve um callback que grava o progresso da montagem no Redis (lido pela UI ao vivo).
    Sem task_id (ex.: beat agendado) vira no-op. Nunca levanta — feedback é best-effort."""
    if not task_id:
        return lambda *_a, **_k: None
    import json
    import os
    import time

    import redis

    try:
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/1"))
    except Exception:
        return lambda *_a, **_k: None
    estado = {"task_id": task_id, "competencia": competencia, "atual": None, "etapas": {}}

    def _prog(nome: str, st: str):
        try:
            estado["etapas"][nome] = st
            estado["atual"] = nome if st == "running" else estado["atual"]
            estado["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            r.set(f"gedeon:montagem:progresso:{task_id}", json.dumps(estado), ex=1800)
        except Exception:
            pass

    return _prog


async def montar_kits_mensais(
    competencia: str,
    condominios: list[str] | None = None,
    dry_run: bool = False,
    blocos: list[str] | None = None,
    task_id: str | None = None,
) -> dict:
    """Monta o kit de cada condomínio para a competência. Devolve relatório agregado.

    `blocos`: se informado, monta SÓ os blocos pedidos (montagem incremental — ex.: só
    "folha" assim que sai a folha, só "pagamentos" depois do pagamento). None = tudo.
    Blocos válidos: folha, guias, pagamentos, vavt, cnds, nfse (ponto é host, no task)."""
    from core.database.session import get_sync_db
    from modules.gedeon.services.cnd_kit_service import arquivar_cnds
    from modules.gedeon.services.inter_boleto_service import arquivar_boletos
    from modules.gedeon.services.inter_comprovantes_gerais import (
        gerar_comprovantes_empresa,
        gerar_comprovantes_va_vt,
    )
    from modules.gedeon.services.inter_kit_service import (
        baixar_extrato_oficial,
        buscar_extrato_pagamento,
        montar_comprovantes,
    )
    from modules.gedeon.services.nfse_kit_service import arquivar_danfse
    from modules.gedeon.services.onvio_kit_service import (
        _condominio_do_nome,
        arquivar_guias_empresa_flat,
        arquivar_onvio_flat,
    )
    from modules.integrations.inter.inter_sync_service import _build_adapter

    condominios = condominios or CONDOMINIOS_PADRAO
    pedido = set(blocos) if blocos else None  # None = todos os blocos

    def quer(b: str) -> bool:
        return pedido is None or b in pedido

    precisa_onvio = quer("folha") or quer("guias") or quer("pagamentos") or quer("vavt") or quer("rescisao")
    precisa_inter = quer("pagamentos") or quer("vavt") or quer("rescisao")

    emitido_em = datetime.now().strftime("%d/%m/%Y")
    rel: dict = {
        "competencia": competencia,
        "condominios": condominios,
        "dry_run": dry_run,
        "blocos": sorted(pedido) if pedido else "todos",
        "etapas": {},
        "pendencias_host": [
            "Ponto assinado (robô Sólides — roda no host)",
            "Atribuição de VA/VT por condomínio (portal Benefícios)",
        ],
    }

    prog = _prog_writer(task_id, competencia)

    def etapa(nome, fn):
        """Roda uma etapa isolada, grava resultado/erro no relatório + progresso ao vivo."""
        prog(nome, "running")
        try:
            r = fn()
            rel["etapas"][nome] = {"ok": True, "resultado": r}
            prog(nome, "ok")
            logger.info("GEDEON orquestrador [%s] OK: %s", nome, r)
            return r
        except Exception as exc:
            rel["etapas"][nome] = {"ok": False, "erro": str(exc)}
            prog(nome, "erro")
            logger.warning("GEDEON orquestrador [%s] FALHOU: %s", nome, exc)
            return None

    # ── Onvio: RENOVA a sessão proativamente (login HTTP + save no Redis) ──────
    # Auth0 (resume ou OTP via IMAP) → cookies+LongToken frescos. Não-fatal: se falhar,
    # segue com a sessão atual do Redis (pode ainda estar válida).
    onvio_client = None
    if precisa_onvio:
        prog("onvio_sessao", "running")
        rel["etapas"]["onvio_sessao"] = {"ok": True, "resultado": garantir_sessao_onvio()}
        prog("onvio_sessao", "ok")
        # ── Onvio: SYNC do mês (baixa docs → /app/uploads/onvio + popula onvio_documents) ──
        # Roda ANTES de arquivar (folha/guias/salário leem de onvio_documents). Não-fatal.
        etapa("onvio_sync", lambda: _onvio_sync(get_sync_db, competencia))
        try:
            from modules.gedeon.onvio.onvio_client import OnvioClient

            onvio_client = OnvioClient()
        except Exception as exc:
            rel["etapas"]["onvio_client"] = {"ok": False, "erro": str(exc)}
            logger.warning("GEDEON: cliente Onvio indisponível: %s", exc)

    if onvio_client is not None and quer("folha"):
        etapa(
            "onvio_folha_contracheques",
            lambda: _onvio_flat(arquivar_onvio_flat, get_sync_db, competencia, onvio_client, dry_run),
        )
    if onvio_client is not None and quer("guias"):
        etapa(
            "onvio_guias",
            lambda: _onvio_guias(
                arquivar_guias_empresa_flat, get_sync_db, competencia, condominios, onvio_client, dry_run
            ),
        )

    # ── Inter: TODO o trabalho async num ÚNICO event loop ─────────────────────
    # (o adapter httpx fica preso ao loop onde nasce; reusar entre asyncio.run quebraria)
    txs: list[dict] = []
    if precisa_inter:
        prog("inter", "running")
        folha_por_cond = _folhas_por_condominio(get_sync_db, _condominio_do_nome, onvio_client, competencia)
        try:
            txs, inter_rel = await _inter_tudo(
                _build_adapter,
                competencia,
                condominios,
                folha_por_cond,
                emitido_em,
                dry_run,
                buscar_extrato_pagamento,
                montar_comprovantes,
                arquivar_boletos,
                baixar_extrato_oficial,
            )
            rel["etapas"]["inter"] = {"ok": True, "resultado": inter_rel}
            prog("inter", "ok")
        except Exception as exc:
            rel["etapas"]["inter"] = {"ok": False, "erro": str(exc)}
            prog("inter", "erro")
            logger.warning("GEDEON orquestrador [inter] FALHOU: %s", exc)

    # INSS (replicado em cada kit) e VA/VT (a atribuir) — SYNC, usam os txs já buscados
    if txs and quer("pagamentos"):
        # No KIT do cliente vai SÓ o comprovante de INSS (decisão Jordan);
        # FGTS/FGTS Consignado/Parcelamento ficam fora. Guias FGTS/DCTFWeb vêm do Onvio.
        etapa(
            "inss_tributario",
            lambda: gerar_comprovantes_empresa(
                competencia, condominios, txs, emitido_em, dry_run=dry_run, apenas=["INSS"]
            ),
        )
    if txs and quer("vavt"):
        etapa("va_vt", lambda: gerar_comprovantes_va_vt(competencia, txs, emitido_em, dry_run=dry_run))

    # ── RESCISÃO: demitidos do mês → TRCT/ASO/Carta (Onvio, busca ampla) + comprovante de
    #    verbas (Inter, ancorado no valor do TRCT). Demitido que trabalhou o mês fica no kit. ──
    if quer("rescisao"):
        from modules.gedeon.services.rescisao_kit_service import arquivar_rescisao

        def _rescisao():
            with get_sync_db() as _db:
                return arquivar_rescisao(
                    competencia, condominios, _db, onvio_client, txs=txs, emitido_em=emitido_em, dry_run=dry_run
                )

        etapa("rescisao", _rescisao)

    # ── CNDs REAIS (emitidas pelo Conecta PRO) replicadas em cada kit ──────────
    if quer("cnds"):
        etapa("cnds", lambda: arquivar_cnds(competencia, condominios, dry_run=dry_run))

    # ── NFS-e: DANFSe das notas emitidas no mês ───────────────────────────────
    if quer("nfse"):
        etapa(
            "nfse_danfse",
            lambda: arquivar_danfse(competencia, mes_emissao=_mes_emissao_nfse(competencia), dry_run=dry_run),
        )

    # resumo
    rel["resumo"] = {
        "etapas_ok": sum(1 for e in rel["etapas"].values() if e.get("ok")),
        "etapas_falha": sum(1 for e in rel["etapas"].values() if not e.get("ok")),
    }
    prog("_concluido", "ok")
    return rel


# ── helpers ───────────────────────────────────────────────────────────────────
def garantir_sessao_onvio() -> dict:
    """Renova a sessão Onvio no Redis (login Auth0 HTTP + save). Roda no container
    (alcança onvio.com.br/auth.thomsonreuters.com/imap.titan.email; OTP lido via IMAP).
    Não-fatal: se falhar, o orquestrador segue com a sessão atual do Redis."""
    try:
        from modules.gedeon.onvio.onvio_auth import login_onvio, save_to_redis

        data = login_onvio()
        ok = save_to_redis(data)
        logger.info("GEDEON: sessão Onvio renovada (save=%s)", ok)
        return {"renovada": bool(ok)}
    except Exception as exc:
        logger.warning("GEDEON: renovação Onvio falhou (segue com sessão atual): %s", exc)
        return {"renovada": False, "erro": str(exc)}


async def _inter_tudo(
    build_adapter,
    competencia,
    condominios,
    folha_por_cond,
    emitido_em,
    dry_run,
    buscar_extrato_pagamento,
    montar_comprovantes,
    arquivar_boletos,
    baixar_extrato_oficial,
):
    """Roda TODO o Inter num único event loop (extrato → salário/cond → boletos → extrato oficial).
    Devolve (txs, relatorio). Cada sub-etapa é isolada por try/except."""
    adapter = build_adapter()
    out: dict = {"salario": {}, "boletos": None, "extrato_oficial": None}
    try:
        txs = await buscar_extrato_pagamento(competencia, adapter)
        out["txs"] = len(txs)
    except Exception as exc:
        out["extrato_erro"] = str(exc)
        try:
            await adapter.close()
        except Exception:
            pass
        return [], out

    for cond in condominios:
        folha = folha_por_cond.get(cond)
        if not folha:
            out["salario"][cond] = "folha não encontrada"
            continue
        try:
            out["salario"][cond] = await montar_comprovantes(
                competencia, cond, folha, adapter, emitido_em, dry_run=dry_run, txs=txs
            )
        except Exception as exc:
            out["salario"][cond] = {"erro": str(exc)}

    try:
        _bi, _bf = _range_boletos(competencia)  # boletos do mês do KIT (competência+1)
        out["boletos"] = await arquivar_boletos(
            competencia, adapter, emitido_em, data_inicial=_bi, data_final=_bf, dry_run=dry_run
        )
    except Exception as exc:
        out["boletos"] = {"erro": str(exc)}

    try:
        out["extrato_oficial"] = await baixar_extrato_oficial(competencia, condominios[0], adapter)
    except Exception as exc:
        out["extrato_oficial"] = {"erro": str(exc)}

    try:
        await adapter.close()
    except Exception:
        pass
    return txs, out


def _onvio_sync(get_sync_db, competencia):
    """Sincroniza os documentos do Onvio do mês (baixa binários + popula onvio_documents)."""
    from modules.gedeon.onvio.onvio_sync_service import OnvioSyncService

    with get_sync_db() as db:
        return OnvioSyncService(db).sync_completo(mes_ref=competencia)


def _onvio_flat(fn, get_sync_db, competencia, onvio_client, dry_run):
    with get_sync_db() as db:
        return fn(competencia, db, onvio_client, dry_run=dry_run)


def _onvio_guias(fn, get_sync_db, competencia, condominios, onvio_client, dry_run):
    with get_sync_db() as db:
        return fn(competencia, condominios, db, onvio_client, dry_run=dry_run)


def _folhas_por_condominio(get_sync_db, _condominio_do_nome, onvio_client, competencia) -> dict[str, bytes]:
    """Mapeia condomínio → bytes do PDF da folha (disco ou re-fetch Onvio)."""
    from sqlalchemy import text

    out: dict[str, bytes] = {}
    try:
        with get_sync_db() as db:
            rows = db.execute(
                text(
                    "SELECT nome_arquivo, caminho_local, onvio_folder_id, onvio_id "
                    "FROM onvio_documents WHERE mes_ref = :m AND categoria = 'folha_pagamento'"
                ),
                {"m": competencia},
            ).fetchall()
    except Exception as exc:
        logger.warning("GEDEON: erro lendo folhas do banco: %s", exc)
        return out

    for nome_arquivo, caminho_local, folder_id, onvio_id in rows:
        cond = _condominio_do_nome(nome_arquivo)
        if not cond or cond in out:
            continue
        pdf = None
        if caminho_local and os.path.exists(caminho_local):
            try:
                with open(caminho_local, "rb") as fh:
                    pdf = fh.read()
            except Exception:
                pdf = None
        if pdf is None and onvio_client is not None and folder_id and onvio_id:
            try:
                pdf = onvio_client.baixar_pdf(folder_id, onvio_id)
            except Exception as exc:
                logger.warning("GEDEON: re-fetch folha %s falhou: %s", nome_arquivo, exc)
        if pdf:
            out[cond] = pdf
    return out
