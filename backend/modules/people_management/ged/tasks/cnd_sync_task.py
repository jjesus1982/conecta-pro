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

import json as _json
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# CNPJ da empresa (Conecta Mais)
EMPRESA_CNPJ = os.environ.get("EMPRESA_CNPJ", "35710481000103")

# Mapeamento tipo → document_type no banco + nome exibicao + emissor
#: Tipos em que o Infosimples PROVOU entregar o documento — medido em 14/08/2026, chamando os
#: dois CNPJs do grupo: CRF-FGTS e CNDT voltaram com número e validade do órgão.
#:
#: `cnd_federal` está DE FORA, e o motivo é externo ao código:
#:
#:     code 603: O token informado não tem autorização de acesso ao serviço.
#:
#: A conta não tem o serviço `receita-federal/pgfn` habilitado. Enquanto ficar assim, forçar a
#: rebusca da CND Federal só martela o portal — a varredura de 14/08 tomou HTTP 429 varrendo os
#: CNPJs dos clientes — e nunca traz certidão. Habilitado o serviço na conta, é só acrescentar
#: aqui: `_buscar_e_salvar_certidao` passa a rebuscar as federais fabricadas e a substituí-las.
_FONTE_QUE_ENTREGA = ("crf_fgts", "cndt_trabalhista")

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

    # ⚠️ VALIDADE SOZINHA NÃO AUTORIZA PULAR — e essa era a raiz de um registro falso eterno.
    # Medido em 14/08/2026: a CND Federal da Eletrônica "vale" até 06/01/2027, mas veio do
    # fallback da BrasilAPI, que grava `"situacao": "indeterminado_portal_indisponivel"` e
    # `"regular": null` — o portal nunca confirmou nada. Como 06/01/2027 é mais de 10 dias
    # à frente, este guard pulava a busca todo dia: **a validade fabricada protegia o próprio
    # registro que a fabricou**. O mesmo valia para a CNDT da Eletrônica, cujo `numero` era
    # a string "EGATIVA" (parse quebrado de "NEGATIVA") — o portal do TST responde de
    # verdade, com número 69676057/2026 e validade 10/02/2027, e nunca era consultado.
    #
    # Agora só pula quando o documento veio do EMISSOR. Quando não há fonte melhor a tentar
    # para o tipo (sem serviço no Infosimples), o comportamento antigo continua valendo — do
    # contrário a estadual e a municipal voltariam para o raspador, que já provou mentir.
    from modules.bidding.integrations.receita_federal import infosimples_cnd_service as _isimp

    # ⚠️ O bypass tem TETO. A versão de 14/08 rebuscava TODA certidão de fonte
    # não-autoritativa a cada execução — com ~22 clientes × 3 tipos, isso é uma varredura
    # paga por dia. Em 17/08 o Infosimples passou a responder `code 603: o token não tem
    # autorização de acesso ao serviço... verifique se não possui limite de uso` nos TRÊS
    # serviços, sendo que dois funcionavam em 14/08. Consumo provavelmente meu.
    #
    # A intenção do bypass continua: validade fabricada não pode proteger a si mesma para
    # sempre. Mas uma vez por SEMANA basta para corrigir um registro falso — diariamente é
    # só queimar cota paga contra um portal que já disse não.
    _RETENTAR_APOS_DIAS = 7
    tem_fonte_melhor = _isimp.habilitado() and tipo in _FONTE_QUE_ENTREGA
    filtro_fonte = (
        "AND (coalesce(notes, '') LIKE '%Infosimples/%' "
        f"     OR updated_at > NOW() - INTERVAL '{_RETENTAR_APOS_DIAS} days') "
        if tem_fonte_melhor else "")

    # ⚠️ Registro que NÃO confirma nada não pode bloquear a busca do que confirma.
    #
    # Medido em 19/08/2026: a CND Federal da Eletrônica devolvia `status=pulada, validade
    # 06/01/2027` — e essa linha é um FALLBACK da BrasilAPI cuja própria nota diz "Status
    # CND/PGFN NÃO confirmado via fonte oficial. Apenas situação cadastral RFB conhecida".
    # Ou seja: um carimbo que só sabe que o CNPJ está ativo estava impedindo, por mais de um
    # ano, que se buscasse a certidão de verdade. É a mesma doença da estadual anulada — um
    # espantalho ocupando o lugar do documento.
    #
    # `regular: null` e `situacao: indeterminado*` são a assinatura do não-confirmado. Linha
    # assim nunca satisfaz o "já tenho, não preciso buscar".
    _NAO_CONFIRMA = (
        "AND coalesce(notes, '') NOT LIKE '%\"regular\": null%' "
        "AND coalesce(notes, '') NOT LIKE '%indeterminado%' "
    )

    check = await db.execute(
        _t(
            "SELECT id, expiry_date FROM ged_certidoes "
            "WHERE document_type = :doc_type AND cnpj = :cnpj "
            "AND expiry_date > CURRENT_DATE + INTERVAL '10 days' "
            f"{_NAO_CONFIRMA}"
            f"{filtro_fonte}"
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

    # ── Fonte 1: Infosimples (API paga que resolve captcha/gov.br) ───────────────
    # Os raspadores abaixo não emitem mais: a RFB e a Caixa exigem login gov.br, e o cliente
    # da SEMEF chegava a dizer `irregular` para qualquer CNPJ (provado em 11/08/2026 com o
    # CNPJ do Banco do Brasil como controle). O Infosimples respondeu code 200 para os dois
    # CNPJs do grupo, com número de CRF e validade reais — é ele que tem chance de trazer
    # documento. O raspador fica como reserva: quando o Infosimples não sabe, ainda se tenta.
    resultado: dict[str, Any] = {}
    try:
        from modules.bidding.integrations.receita_federal import infosimples_cnd_service as _isimp

        if _isimp.habilitado() and tipo in _isimp.SERVICOS:
            resultado = await _isimp.consultar(tipo, cnpj)
            sit = str(resultado.get("situacao") or "").lower()
            if resultado.get("data_validade") and sit in ("regular", "negativa", "nada_consta"):
                logger.info("[cnd] %s de %s veio do Infosimples (validade %s)",
                            tipo, cnpj, resultado["data_validade"])
            else:
                logger.info("[cnd] Infosimples não confirmou %s de %s (%s) — tentando portal",
                            tipo, cnpj, sit or "sem situação")
                resultado = {}
    except Exception as exc:  # noqa: BLE001 — fonte 1 falhar não pode impedir a fonte 2
        logger.warning("[cnd] Infosimples indisponível para %s/%s: %s", tipo, cnpj, exc)
        resultado = {}

    # ── Fonte 2: portal direto (reserva) ─────────────────────────────────────────
    try:
        if resultado:
            pass
        elif tipo == "cnd_federal":
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

    # ── Certidão só se grava quando o órgão CONFIRMOU ────────────────────────────
    # Em 11/08/2026 este trecho fabricou compliance fiscal. A guarda só rejeitava
    # `erro_consulta`, então `indeterminado_portal_indisponivel` (portal fora do ar) e
    # `irregular` (empresa COM pendência) passavam direto — e, logo abaixo, quando o portal
    # não devolvia validade, havia um "fallback: validade padrao pelo tipo" que INVENTAVA
    # hoje+180 dias. Resultado medido: quatro linhas nasceram/renovaram parecendo certidões
    # válidas até 2027 sem que nenhuma consulta tivesse sido respondida. Uma delas era a
    # CRF-FGTS vencida da Eletrônica, que passou a exibir-se em dia.
    #
    # Isso é pior que não ter a certidão: sem ela, a tela mostra "FALTA" e alguém providencia;
    # com uma falsa, o painel fica verde e a empresa descobre na hora de faturar ou licitar.
    situacao = str(resultado.get("situacao") or "").lower()
    if not resultado or situacao == "erro_consulta" or situacao.startswith("indeterminado"):
        return {
            "status": "indisponivel",
            "situacao": situacao or "sem_resposta",
            "mensagem": resultado.get("mensagem", "portal não confirmou — nada foi gravado"),
        }
    if situacao and situacao not in ("regular", "negativa", "positiva_com_efeito_negativa", "nada_consta"):
        # `irregular`/`positiva` é ACHADO (há pendência no órgão), não certidão. Gravar como
        # documento válido esconderia justamente a dívida que impede a empresa de operar.
        return {
            "status": "irregular",
            "situacao": situacao,
            "mensagem": f"órgão respondeu '{situacao}' — não existe certidão negativa a registrar",
        }

    data_validade = None
    validade_raw = resultado.get("data_validade")
    if validade_raw:
        try:
            data_validade = datetime.fromisoformat(validade_raw.split("T")[0]).date()
        except (ValueError, AttributeError):
            pass
    if data_validade is None:
        # Sem data do órgão não há certidão. O fallback que existia aqui era a fábrica de
        # validade: qualquer resposta virava 180 dias de regularidade.
        return {
            "status": "sem_validade",
            "situacao": situacao,
            "mensagem": "órgão não devolveu data de validade — nada foi gravado (validade não se estima)",
        }

    issue_date = datetime.utcnow().date()
    # PROCEDÊNCIA gravada, e não só "atualizado automaticamente". Duas razões, ambas medidas
    # em 14/08/2026:
    #   1. o NÚMERO do documento era jogado fora. Certidão sem número não se confere no
    #      portal nem se anexa a licitação — e foi assim que sobrou um registro com o
    #      `numero` "EGATIVA", sem ninguém conseguir dizer de onde tinha vindo.
    #   2. sem saber a FONTE, o guard de "válida por 10+ dias" não consegue distinguir o
    #      documento do emissor do palpite do fallback, e acaba protegendo o palpite.
    # Formato JSON porque é o que os registros bons já usavam.
    notes = _json.dumps({
        "situacao": resultado.get("situacao", "regular"),
        "numero": resultado.get("numero"),
        "fonte": resultado.get("fonte") or "portal governamental (raspador)",
        "consultado_em": resultado.get("consultado_em") or datetime.utcnow().isoformat(),
        "cnpj": cnpj,
    }, ensure_ascii=False)

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
    # Cinco portais do governo em sequência não cabem nos 300 s globais: a task morria
    # por SoftTimeLimitExceeded todo dia (sino de 06/09) depois de atualizar só o FGTS —
    # a municipal ficou vencida desde 01/09 sem ninguém ver.
    soft_time_limit=1500,
    time_limit=1800,
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
                return future.result(timeout=1500)
        else:
            return asyncio.run(_run())
    except RuntimeError:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Erro fatal na task ged_buscar_certidoes_portais: %s", exc)
        if hasattr(self, "retry"):
            raise self.retry(exc=exc)
        return {"error": str(exc)}
