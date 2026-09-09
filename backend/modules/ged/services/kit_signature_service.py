"""GED — Fiação da assinatura universal nos DOCUMENTOS DO KIT (task #26).

Quando o kit documental por condomínio é montado, os documentos que precisam
da assinatura do FUNCIONÁRIO (contracheque, folha de ponto, comprovantes VT/VA/VR,
contrato de trabalho, ficha de registro, férias, aviso prévio, rescisão, etc.)
passam a gerar uma solicitação de assinatura no MOTOR UNIVERSAL
(`garantir_solicitacao_assinatura`), exatamente como contrato/proposta/holerite.

Regras (decididas na task):
- Signatário = EMPLOYEE (o funcionário assina pelo Portal / painel de assinaturas).
  Nível SIMPLE (não é contrato de serviço com A1). A empresa NÃO co-assina os
  documentos do kit — são documentos do funcionário.
- IDEMPOTENTE: reprocessar o kit não duplica signatário (o motor já garante 1
  request por (document_type, document_id)).
- NÃO duplica a FICHA DE EPI: ela tem fluxo próprio (portal_digital_signatures) e
  fica FORA da lista de tipos assináveis aqui — se entrar no kit, é ignorada.
- Documentos da EMPRESA/GOVERNO já vêm assinados na origem (CNDs/CRF/CNDT emitidas
  pelo órgão; guias/DCTFWeb; NFS-e/boleto) → NÃO exigem assinatura do funcionário.
- O gate de fechamento/entrega do kit é CONSERVADOR: NÃO perde documento; apenas
  lista as pendências de assinatura para que dê pra ver o que falta e coletar.

`document_type` no motor = 'kit_documento' (política em solicitar_assinatura_documento).
O `document_id` é o id do `ged_kit_documents` (UUID). Assim, o status por documento
é consultável em GET /signatures/document/kit_documento/{doc_id} e o funcionário
assina em POST /signatures/{request_id}/sign — reusando 100% o motor.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Tipos de documento do kit (ged_kit_documents.document_type) que EXIGEM assinatura
# do FUNCIONÁRIO. Cobre os nomes canônicos e as variações já presentes no banco.
# NÃO inclui: ficha_epi (fluxo próprio), CNDs/CRF/CNDT (assinadas pelo órgão),
# guias/DCTFWeb/DAS/GPS (empresa), nfse/boleto (sem signatário funcionário).
EMPLOYEE_SIGNABLE_KIT_TYPES: frozenset[str] = frozenset(
    {
        # contracheque / folha de pagamento individual
        "contracheque",
        "recibo_folha",
        "comp_salario_individual",
        # folha de ponto
        "folha_ponto",
        # 09/09: escala do mês e recibo de adiantamento também são do funcionário
        "escala_mes",
        "recibo_adiantamento",
        "folhas_ponto",
        "ponto",
        # benefícios (comprovantes de VT/VA/VR do funcionário)
        "comprovante_vt",
        "comprovante_va",
        "comprovante_vr",
        "vale_vt_vr",
        "vale_transporte",
        "comp_vt_individual",
        "comp_va_solides",
        "comp_vt_va_combinado",
        "recibo_vt_va",
        "declaracao_vt",
        # eventos trabalhistas / cadastro
        "contrato_trabalho",
        "ficha_empregado",
        "ficha_registro",
        "ferias",
        "aviso_previo",
        "aviso_previo_ferias",
        "rescisao",
        "rescisao_contrato",
    }
)

# Tipos que NUNCA passam pela assinatura do funcionário (defesa em profundidade:
# mesmo que caiam com employee_id não nulo por engano, ficam de fora).
NAO_ASSINAVEIS_PELO_FUNCIONARIO: frozenset[str] = frozenset(
    {
        "ficha_epi",  # fluxo próprio portal_digital_signatures — NÃO duplicar
    }
)


def _kit_documento_precisa_assinatura(document_type: str | None, employee_id: Any) -> bool:
    """Um documento do kit exige assinatura do funcionário?"""
    if employee_id is None:
        return False
    dt = (document_type or "").strip().lower()
    if dt in NAO_ASSINAVEIS_PELO_FUNCIONARIO:
        return False
    return dt in EMPLOYEE_SIGNABLE_KIT_TYPES


# 09/09: quem leva o campo do DIRETOR no PDF — espelho de ponto e recibo de adiantamento (a escala é da supervisão)
COASSINADOS: frozenset[str] = frozenset({"folha_ponto", "folhas_ponto", "ponto", "recibo_adiantamento"})


async def sincronizar_assinaturas_kit(db: AsyncSession, kit_id: str) -> dict[str, Any]:
    """Traz para ged_kit_documents o que o motor já sabe: PDF assinado (selos) e is_signed. Idempotente.
    Cobre assinaturas feitas antes do hook de 09/09 existir e qualquer descompasso."""
    import os
    import shutil

    rows = (await db.execute(text(
        """
        SELECT gkd.id, gkd.file_path, gkd.is_signed,
               sum(CASE WHEN sr.status::text IN ('SIGNED','COMPLETED') THEN 1 ELSE 0 END) AS assinadas,
               count(sr.id) FILTER (WHERE sr.status::text NOT IN ('CANCELLED','REJECTED','EXPIRED')) AS total,
               (array_agg(sr.signed_document_path ORDER BY coalesce(sr.signed_at, sr.updated_at) DESC NULLS LAST))[1] AS ultimo_pdf,
               max(sr.signed_at) AS signed_at
        FROM ged_kit_documents gkd
        JOIN sig_signature_requests sr ON sr.document_type IN ('kit_documento','kit_documento_coassinado') AND sr.document_id = gkd.id
        WHERE gkd.kit_id = :kid AND sr.status::text NOT IN ('CANCELLED','REJECTED','EXPIRED')
        GROUP BY gkd.id, gkd.file_path, gkd.is_signed
        """), {"kid": kit_id})).mappings().all()
    rel = {"documentos_com_pedido": len(rows), "atualizados": 0, "assinados": 0, "parciais": 0}
    for r in rows:
        if not r["ultimo_pdf"] or not os.path.exists(r["ultimo_pdf"]):
            continue
        completo = int(r["assinadas"] or 0) >= int(r["total"] or 0) and int(r["total"] or 0) > 0
        if int(r["assinadas"] or 0) == 0:
            continue
        destino = r["file_path"] or r["ultimo_pdf"]
        try:
            if destino != r["ultimo_pdf"]:
                shutil.copyfile(r["ultimo_pdf"], destino)
        except OSError as exc:
            logger.warning("sincronizar_assinaturas_kit: cópia falhou %s: %s", destino, exc)
            continue
        await db.execute(text(
            "UPDATE ged_kit_documents SET file_path = :fp, is_signed = :ok, signed_at = CASE WHEN :ok THEN :ts ELSE signed_at END, "
            "updated_at = now() WHERE id = :i"), {"fp": destino, "ok": completo, "ts": r["signed_at"], "i": r["id"]})
        rel["atualizados"] += 1
        rel["assinados" if completo else "parciais"] += 1
    return rel


async def solicitar_assinaturas_kit(
    db: AsyncSession,
    kit_id: str,
    *,
    requested_by: str | None = None,
) -> dict[str, Any]:
    """Cria a solicitação de assinatura (EMPLOYEE) para cada documento assinável do kit.

    Idempotente — reprocessar não duplica. Nunca quebra a montagem do kit: erros
    por documento são logados e contabilizados, mas não abortam o lote.

    Returns:
        Resumo {kit_id, assinaveis, solicitadas, ja_existentes, ignorados, erros}.
    """
    from modules.signatures.helpers.solicitar_assinatura_documento import (
        garantir_solicitacao_assinatura,
    )

    rows = (
        await db.execute(
            text(
                """
                SELECT gkd.id, gkd.document_type, gkd.document_name, gkd.employee_id,
                       gkd.file_path, e.nome AS employee_name, e.cpf AS employee_cpf
                FROM ged_kit_documents gkd
                LEFT JOIN employees e ON e.id = gkd.employee_id
                WHERE gkd.kit_id = :kid
                  AND gkd.file_path IS NOT NULL
                  AND COALESCE(gkd.document_name,'') NOT ILIKE '%PLACEHOLDER%'
                """
            ),
            {"kid": kit_id},
        )
    ).mappings().all()

    resumo = {
        "kit_id": kit_id,
        "assinaveis": 0,
        "solicitadas": 0,
        "ja_existentes": 0,
        "ignorados": 0,
        "erros": 0,
    }

    for d in rows:
        if not _kit_documento_precisa_assinatura(d["document_type"], d["employee_id"]):
            resumo["ignorados"] += 1
            continue

        resumo["assinaveis"] += 1
        titulo = d["document_name"] or f"Documento do kit ({d['document_type']})"
        # 09/09: espelho de ponto e escala levam o campo do diretor → funcionário E empresa (central de assinaturas)
        dtype = "kit_documento_coassinado" if (d["document_type"] or "").lower() in COASSINADOS else "kit_documento"
        try:
            res = await garantir_solicitacao_assinatura(
                db,
                document_type=dtype,
                document_id=str(d["id"]),
                title=titulo,
                document_path=d["file_path"],
                employee_id=d["employee_id"],
                employee_name=d["employee_name"],
                employee_document=d["employee_cpf"],
                requested_by=requested_by,
            )
            if res is None:
                resumo["erros"] += 1
            elif res.get("created"):
                resumo["solicitadas"] += 1
            else:
                resumo["ja_existentes"] += 1
        except Exception as exc:  # noqa: BLE001 — nunca quebra a montagem
            resumo["erros"] += 1
            logger.warning("Falha ao solicitar assinatura do kit_documento %s: %s", d["id"], exc)

    logger.info(
        "Assinaturas do kit %s: %d assináveis, %d solicitadas, %d já existentes, %d erros",
        kit_id,
        resumo["assinaveis"],
        resumo["solicitadas"],
        resumo["ja_existentes"],
        resumo["erros"],
    )
    return resumo


async def status_assinaturas_kit(db: AsyncSession, kit_id: str) -> dict[str, Any]:
    """Status de assinatura dos documentos assináveis do kit (fonte: motor universal).

    Lê `sig_signature_requests` (document_type='kit_documento') casando pelo id do
    documento do kit. Devolve o agregado e a lista de PENDÊNCIAS (quem/qual doc
    ainda falta assinar) — é a visibilidade que o painel/tela de montagem usa.

    Returns:
        {kit_id, assinaveis, com_solicitacao, assinados, pendentes,
         sem_solicitacao, pode_fechar, pendencias:[...]}.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT gkd.id, gkd.document_type, gkd.document_name, gkd.employee_id,
                       e.nome AS employee_name,
                       sr.id AS request_id, sr.status AS req_status, sr.signed_at
                FROM ged_kit_documents gkd
                LEFT JOIN employees e ON e.id = gkd.employee_id
                LEFT JOIN sig_signature_requests sr
                       ON sr.document_type IN ('kit_documento', 'kit_documento_coassinado')
                      AND sr.document_id = gkd.id
                      AND sr.signer_type = 'employee'
                WHERE gkd.kit_id = :kid
                  AND gkd.file_path IS NOT NULL
                  AND COALESCE(gkd.document_name,'') NOT ILIKE '%PLACEHOLDER%'
                """
            ),
            {"kid": kit_id},
        )
    ).mappings().all()

    assinaveis = 0
    com_solicitacao = 0
    assinados = 0
    sem_solicitacao = 0
    pendencias: list[dict[str, Any]] = []

    for d in rows:
        if not _kit_documento_precisa_assinatura(d["document_type"], d["employee_id"]):
            continue
        assinaveis += 1
        if not d["request_id"]:
            sem_solicitacao += 1
            pendencias.append(
                {
                    "document_id": str(d["id"]),
                    "document_type": d["document_type"],
                    "document_name": d["document_name"],
                    "employee_name": d["employee_name"],
                    "situacao": "sem_solicitacao",
                }
            )
            continue
        com_solicitacao += 1
        if str(d["req_status"]).lower() in {"signed", "completed", "assinado"} or d["signed_at"]:
            assinados += 1
        else:
            pendencias.append(
                {
                    "document_id": str(d["id"]),
                    "document_type": d["document_type"],
                    "document_name": d["document_name"],
                    "employee_name": d["employee_name"],
                    "request_id": str(d["request_id"]),
                    "situacao": "aguardando_assinatura",
                }
            )

    pendentes = assinaveis - assinados
    return {
        "kit_id": kit_id,
        "assinaveis": assinaveis,
        "com_solicitacao": com_solicitacao,
        "assinados": assinados,
        "pendentes": pendentes,
        "sem_solicitacao": sem_solicitacao,
        # gate conservador: só está "pronto de assinatura" quando não há pendência
        "pode_fechar": pendentes == 0,
        "pendencias": pendencias,
    }
