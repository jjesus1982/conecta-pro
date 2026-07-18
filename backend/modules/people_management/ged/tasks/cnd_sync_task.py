"""
Celery task: Sincronizacao diaria de CNDs.

Executa diariamente para verificar se ha certidoes negativas
renovadas e atualizar todos os kits EM_MONTAGEM com as versoes
mais recentes.

Tambem inclui busca ativa nos portais governamentais (GAP 2):
- CNDFederalClient → certidao_negativa_federal
- CNDTTrabalhistaClient → certidao_negativa_trabalhista
- CRFFGTSClient → certidao_negativa_fgts
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# CNPJ da empresa (Conecta Mais)
EMPRESA_CNPJ = os.environ.get("EMPRESA_CNPJ", "35710481000103")

# Mapeamento tipo → document_type no banco + nome exibicao + emissor
CERTIDAO_CONFIG: dict[str, dict] = {
    "cnd_federal": {
        "document_type": "certidao_negativa_federal",
        "name": "Certidão Negativa Federal",
        "issuing_body": "RFB/PGFN",
    },
    "cndt_trabalhista": {
        "document_type": "certidao_negativa_trabalhista",
        "name": "Certidão Negativa Trabalhista",
        "issuing_body": "TST",
    },
    "crf_fgts": {
        "document_type": "certidao_negativa_fgts",
        "name": "Certidão Negativa FGTS",
        "issuing_body": "CEF/FGTS",
    },
    "cnd_estadual": {
        "document_type": "certidao_negativa_estadual",
        "name": "CND Estadual — Sefaz-AM",
        "issuing_body": "Sefaz-AM",
    },
    "cnd_municipal": {
        "document_type": "certidao_negativa_municipal",
        "name": "CND Municipal — SEMEF Manaus",
        "issuing_body": "SEMEF/Manaus",
    },
}

try:
    from celery import shared_task
except ImportError:

    def shared_task(*args, **kwargs):
        def decorator(func):
            func.delay = lambda *a, **kw: func(*a, **kw)
            func.apply_async = lambda *a, **kw: func(*a, **kw)
            return func

        if args and callable(args[0]):
            return decorator(args[0])
        return decorator


# Mapeamento de tipos de CND para caminhos no storage
CND_STORAGE_PATHS = {
    "cnd_federal": "documents/fiscal/certidoes/cnd_federal.pdf",
    "cnd_estadual": "documents/fiscal/certidoes/cnd_estadual.pdf",
    "cnd_municipal": "documents/fiscal/certidoes/cnd_municipal.pdf",
    "crf_fgts": "documents/fiscal/certidoes/crf_fgts.pdf",
    "cndt_trabalhista": "documents/fiscal/certidoes/cndt_trabalhista.pdf",
}

GED_STORAGE_BASE = os.environ.get("GED_STORAGE_PATH", "/opt/conecta-pro/storage/ged")


@shared_task(
    name="ged.sync_cnds",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    queue="ged",
)
def ged_sync_cnds(self) -> dict:
    """Task Celery para sincronizacao de CNDs em kits.

    Verifica se alguma CND foi renovada (arquivo modificado recentemente)
    e atualiza em todos os kits EM_MONTAGEM.

    Execucao recomendada: diariamente via Celery Beat.

    Returns:
        Dicionario com resumo da sincronizacao.
    """
    import asyncio

    logger.info("Task ged_sync_cnds iniciada")

    async def _run():
        from core.database import async_session_factory

        async with async_session_factory() as db:
            try:
                from modules.people_management.ged.events.handlers import on_cnd_renewed

                total_updated = 0
                total_created = 0
                cnds_checked = 0
                cnds_renewed = []

                for cnd_type, relative_path in CND_STORAGE_PATHS.items():
                    full_path = os.path.join(GED_STORAGE_BASE, relative_path)
                    cnds_checked += 1

                    # Verificar se o arquivo existe e foi modificado nas ultimas 24h
                    if os.path.exists(full_path):
                        mod_time = datetime.fromtimestamp(os.path.getmtime(full_path))
                        now = datetime.utcnow()
                        hours_since_modified = (now - mod_time).total_seconds() / 3600

                        if hours_since_modified <= 24:
                            logger.info(
                                "CND %s renovada (modificada ha %.1fh): %s",
                                cnd_type,
                                hours_since_modified,
                                relative_path,
                            )

                            result = await on_cnd_renewed(
                                db=db,
                                cnd_type=cnd_type,
                                file_path=relative_path,
                            )

                            total_updated += result.get("documents_updated", 0)
                            total_created += result.get("documents_created", 0)
                            cnds_renewed.append(cnd_type)
                    else:
                        logger.debug("CND %s nao encontrada em %s", cnd_type, full_path)

                if cnds_renewed:
                    await db.commit()
                    logger.info(
                        "Task ged_sync_cnds: %d CNDs renovadas, %d docs atualizados, %d criados",
                        len(cnds_renewed),
                        total_updated,
                        total_created,
                    )
                else:
                    logger.info("Task ged_sync_cnds: nenhuma CND renovada nas ultimas 24h")

                return {
                    "cnds_checked": cnds_checked,
                    "cnds_renewed": cnds_renewed,
                    "documents_updated": total_updated,
                    "documents_created": total_created,
                    "executed_at": datetime.utcnow().isoformat(),
                }

            except Exception as e:
                await db.rollback()
                logger.error("Erro na task ged_sync_cnds: %s", e)
                raise

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _run())
                return future.result(timeout=300)
        else:
            return asyncio.run(_run())
    except RuntimeError:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Erro fatal na task ged_sync_cnds: %s", exc)
        if hasattr(self, "retry"):
            raise self.retry(exc=exc)
        return {"error": str(exc)}


# ── BUSCA ATIVA NOS PORTAIS GOVERNAMENTAIS ─────────────────────────────────────


async def _buscar_e_salvar_certidao(
    db: Any,
    cnpj: str,
    tipo: str,
    client_id: str = "",
    client_name: str = "",
) -> dict[str, Any]:
    """
    Busca certidao no portal governamental e salva/atualiza em ged_certidoes.

    Pula busca se certidao existente ainda valida por mais de 10 dias.

    Args:
        db: AsyncSession do SQLAlchemy
        cnpj: CNPJ da empresa (somente digitos)
        tipo: "cnd_federal" | "cndt_trabalhista" | "crf_fgts"
        client_id: ID do cliente (para publicacao de eventos)
        client_name: Nome do cliente (para logs)

    Returns:
        Dict com status ("pulada"|"criada"|"atualizada"|"erro"), cert_id e validade
    """
    from sqlalchemy import text as _t

    config = CERTIDAO_CONFIG.get(tipo)
    if not config:
        return {"status": "erro", "mensagem": f"Tipo desconhecido: {tipo}"}

    doc_type = config["document_type"]

    # Verificar se certidao existente ainda valida por 10+ dias
    check = await db.execute(
        _t(
            "SELECT id, expiry_date FROM ged_certidoes "
            "WHERE document_type = :doc_type AND cnpj = :cnpj "
            "AND expiry_date > CURRENT_DATE + INTERVAL '10 days' "
            "LIMIT 1"
        ),
        {"doc_type": doc_type, "cnpj": cnpj},
    )
    existing = check.mappings().first()
    if existing:
        logger.debug(
            "Certidao %s valida ate %s — pulando busca no portal",
            doc_type,
            existing["expiry_date"],
        )
        return {
            "status": "pulada",
            "cert_id": str(existing["id"]),
            "validade": str(existing["expiry_date"]),
        }

    # Buscar no portal governamental
    resultado: dict[str, Any] = {}
    try:
        if tipo == "cnd_federal":
            from modules.bidding.integrations.receita_federal.cnd_client import (
                CNDFederalClient,
            )

            async with CNDFederalClient() as client:
                resultado = await client.consultar_cnd(cnpj)
        elif tipo == "cndt_trabalhista":
            from modules.bidding.integrations.receita_federal.cndt_client import (
                CNDTTrabalhistaClient,
            )

            # CNDTTrabalhistaClient NÃO é context manager (bug pré-existente:
            # toda busca CNDT desta task falhava com "object does not support
            # the asynchronous context manager protocol")
            resultado = await CNDTTrabalhistaClient().consultar_cndt(cnpj)
        elif tipo == "crf_fgts":
            from modules.bidding.integrations.receita_federal.crf_client import (
                CRFFGTSClient,
            )

            async with CRFFGTSClient() as client:
                resultado = await client.consultar_crf(cnpj)
        elif tipo == "cnd_estadual":
            from modules.bidding.integrations.receita_federal.sefaz_am_client import (
                SefazAMClient,
            )

            async with SefazAMClient() as client:
                resultado = await client.consultar_cnd(cnpj)
        elif tipo == "cnd_municipal":
            from modules.bidding.integrations.receita_federal.prefeitura_manaus_client import (
                PrefeituraManausClient,
            )

            async with PrefeituraManausClient() as client:
                resultado = await client.consultar_cnd(cnpj)
    except Exception as exc:
        logger.error("Erro ao consultar portal %s para CNPJ %s: %s", tipo, cnpj, exc)
        return {"status": "erro", "mensagem": str(exc)}

    if not resultado or resultado.get("situacao") == "erro_consulta":
        return {
            "status": "erro",
            "mensagem": resultado.get("mensagem", "Consulta retornou erro"),
        }

    # Converter data_validade para objeto date
    data_validade = None
    validade_raw = resultado.get("data_validade")
    if validade_raw:
        try:
            data_validade = datetime.fromisoformat(validade_raw.split("T")[0]).date()
        except (ValueError, AttributeError):
            pass
    if data_validade is None:
        # fallback: validade padrao pelo tipo
        dias = {
            "cnd_federal": 180,
            "cndt_trabalhista": 180,
            "crf_fgts": 30,
            "cnd_estadual": 180,
            "cnd_municipal": 180,
        }.get(tipo, 30)
        data_validade = (datetime.utcnow() + timedelta(days=dias)).date()

    issue_date = datetime.utcnow().date()
    notes = f"Atualizado automaticamente via portal governamental. Situacao: {resultado.get('situacao', 'regular')}. CNPJ: {cnpj}"

    # Verificar se ja existe registro para este document_type
    existing_row = await db.execute(
        _t("SELECT id FROM ged_certidoes WHERE document_type = :doc_type AND cnpj = :cnpj LIMIT 1"),
        {"doc_type": doc_type, "cnpj": cnpj},
    )
    existing_id = existing_row.scalar_one_or_none()

    if existing_id:
        await db.execute(
            _t(
                "UPDATE ged_certidoes SET "
                "issue_date = :issue_date, expiry_date = :expiry_date, "
                "notes = :notes, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "id": str(existing_id),
                "issue_date": issue_date,
                "expiry_date": data_validade,
                "notes": notes,
            },
        )
        cert_id = str(existing_id)
        status = "atualizada"
    else:
        cert_id = str(uuid4())
        await db.execute(
            _t(
                "INSERT INTO ged_certidoes "
                "(id, name, document_type, issuing_body, issue_date, expiry_date, notes, cnpj, created_at, updated_at) "
                "VALUES (:id, :name, :doc_type, :issuing_body, :issue_date, :expiry_date, :notes, :cnpj, NOW(), NOW())"
            ),
            {
                "id": cert_id,
                "name": config["name"],
                "doc_type": doc_type,
                "issuing_body": config["issuing_body"],
                "issue_date": issue_date,
                "expiry_date": data_validade,
                "notes": notes,
                "cnpj": cnpj,
            },
        )
        status = "criada"

    # Publicar evento de renovacao
    try:
        from modules.fiscal.publishers import publish_certidao_renovada

        await publish_certidao_renovada(
            certidao_id=cert_id,
            tipo=tipo,
            nova_validade=data_validade,
            cliente_id=client_id or None,
            extra={"cnpj": cnpj, "fonte": "auto_sync"},
        )
    except Exception as exc:
        logger.warning("publish_certidao_renovada falhou (nao critico): %s", exc)

    logger.info(
        "Certidao %s %s para %s — validade %s",
        doc_type,
        status,
        client_name or cnpj,
        data_validade,
    )
    return {"status": status, "cert_id": cert_id, "validade": str(data_validade)}


async def buscar_todas_certidoes(db: Any) -> dict[str, Any]:
    """
    Busca certidoes de todos os tipos nos portais governamentais.

    Itera sobre todos os clientes ativos com CNPJ cadastrado na tabela clients.
    Para cada cliente × tipo, verifica validade no banco e busca renovacao
    quando necessario. Se nenhum cliente com CNPJ for encontrado, usa EMPRESA_CNPJ.

    Args:
        db: AsyncSession do SQLAlchemy

    Returns:
        Dict com total, renovadas, puladas, erros, clientes e detalhes
    """
    import re

    from sqlalchemy import text as _t

    # Buscar clientes ativos com CNPJ (document_type='cnpj', document_number nao nulo)
    try:
        rows = await db.execute(
            _t(
                "SELECT id::text, name, document_number AS cnpj "
                "FROM clients "
                "WHERE document_type = 'cnpj' "
                "AND document_number IS NOT NULL "
                "AND LENGTH(REGEXP_REPLACE(document_number, '[^0-9]', '', 'g')) = 14 "
                "AND status = 'active' "
                "ORDER BY name"
            )
        )
        clientes = rows.mappings().all()
    except Exception as exc:
        logger.warning("Erro ao buscar clientes com CNPJ: %s — usando EMPRESA_CNPJ", exc)
        clientes = []

    # Fallback: usar CNPJ da empresa se nenhum cliente encontrado
    if not clientes:
        cnpj_empresa = re.sub(r"\D", "", EMPRESA_CNPJ)
        logger.info(
            "buscar_todas_certidoes: nenhum cliente com CNPJ — usando EMPRESA_CNPJ %s",
            cnpj_empresa,
        )
        clientes = [{"id": "", "name": "Conecta Mais", "cnpj": cnpj_empresa}]

    # Multi-CNPJ E6: as empresas DO GRUPO vêm SEMPRE primeiro (as duas — CNPJ1 e
    # CNPJ2/empregador dos CLT). Cada (cnpj × tipo) tem linha própria em
    # ged_certidoes; um verde do CNPJ1 nunca mascara o CNPJ2 (pré-mortem F4).
    try:
        grupo_rows = await db.execute(
            _t(
                "SELECT '' AS id, razao_social AS name, "
                "REGEXP_REPLACE(cnpj, '[^0-9]', '', 'g') AS cnpj "
                "FROM empresas WHERE status = 'ativa' AND cnpj IS NOT NULL "
                "ORDER BY is_principal DESC"
            )
        )
        grupo = list(grupo_rows.mappings().all())
        cnpjs_grupo = {g["cnpj"] for g in grupo}
        clientes = grupo + [c for c in clientes if re.sub(r"\D", "", str(c["cnpj"])) not in cnpjs_grupo]
    except Exception as exc:  # noqa: BLE001
        logger.warning("buscar_todas_certidoes: falha ao carregar empresas do Grupo (%s)", exc)

    logger.info(
        "buscar_todas_certidoes iniciado — %d cliente(s) com CNPJ",
        len(clientes),
    )

    TIPOS = [t for t in CERTIDAO_CONFIG if t in ("cnd_federal", "cndt_trabalhista", "crf_fgts")]

    renovadas = 0
    puladas = 0
    erros = 0
    detalhes: list[dict] = []

    for cliente in clientes:
        cid = str(cliente["id"]) if cliente["id"] else ""
        nome = cliente["name"]
        cnpj = re.sub(r"\D", "", str(cliente["cnpj"]))

        for tipo in TIPOS:
            resultado = await _buscar_e_salvar_certidao(db, cnpj, tipo, cid, nome)
            resultado["tipo"] = tipo
            resultado["cliente"] = nome
            detalhes.append(resultado)

            st = resultado.get("status", "erro")
            if st in ("criada", "atualizada"):
                renovadas += 1
            elif st == "pulada":
                puladas += 1
            else:
                erros += 1

    if renovadas > 0:
        await db.commit()

    logger.info(
        "buscar_todas_certidoes concluido — clientes=%d, renovadas=%d, puladas=%d, erros=%d",
        len(clientes),
        renovadas,
        puladas,
        erros,
    )
    return {
        "total": len(clientes) * len(TIPOS),
        "renovadas": renovadas,
        "puladas": puladas,
        "erros": erros,
        "clientes": len(clientes),
        "detalhes": detalhes,
        "executado_em": datetime.utcnow().isoformat(),
    }


@shared_task(
    name="ged.buscar_certidoes_portais",
    bind=True,
    max_retries=2,
    default_retry_delay=900,
    queue="ged",
)
def ged_buscar_certidoes_portais(self) -> dict:
    """Task Celery para busca ativa de certidoes nos portais governamentais.

    Consulta CND Federal (RFB/PGFN), CNDT Trabalhista (TST), CRF/FGTS (Caixa),
    CND Estadual (Sefaz-AM) e CND Municipal (SEMEF Manaus)
    para o CNPJ da empresa. Skips certidoes ainda validas por 10+ dias.

    Execucao recomendada: diariamente via Celery Beat (06h30).

    Returns:
        Dicionario com resumo da busca.
    """
    import asyncio

    logger.info("Task ged_buscar_certidoes_portais iniciada")

    async def _run():
        from core.database import async_session_factory

        async with async_session_factory() as db:
            try:
                return await buscar_todas_certidoes(db)
            except Exception as e:
                await db.rollback()
                logger.error("Erro na task ged_buscar_certidoes_portais: %s", e)
                raise

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _run())
                return future.result(timeout=300)
        else:
            return asyncio.run(_run())
    except RuntimeError:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Erro fatal na task ged_buscar_certidoes_portais: %s", exc)
        if hasattr(self, "retry"):
            raise self.retry(exc=exc)
        return {"error": str(exc)}
