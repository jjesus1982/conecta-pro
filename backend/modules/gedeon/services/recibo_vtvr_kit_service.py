"""GEDEON — publica no kit do posto o Recibo de VT/VR ASSINADO pelo funcionário.

🔴 ESTE MÓDULO JÁ ESTEVE ERRADO, e o erro era de desenho. Na primeira versão (18/08/2026)
ele gerava o PDF e subia direto para o Drive. Isso fura o desenho do GEDEON, que o Jordan
descreveu assim: *"todos os documentos do trabalhador — contracheque, recibo de VT e VA —
devem ser assinados pelo funcionário; o sistema gera, disponibiliza no portal, cada um com
seu acesso, ele assina pelo sistema, e ISSO sobe para o kit"*.

O estrago medido: 7 recibos e 38 comprovantes de salário nos kits, ZERO assinados. O
condomínio receberia papel sem valor probatório num kit anunciado como 100%.

O fluxo correto tem três donos, e este arquivo é só o terceiro:

    1. `gerar_docs_mes_service`  gera o PDF e ABRE a solicitação de assinatura
    2. o FUNCIONÁRIO assina no portal            → nasce o PDF selado em /uploads/signed
    3. aqui                                       → o PDF SELADO sobe para o kit do posto

Documento não assinado NÃO sobe. Fica pendente no portal, e o kit fica honestamente
incompleto — o que é melhor que completo e falso.

⚠️ NÃO BASTA O BANCO DIZER "ASSINADO". Em 21/08/2026, de 51 registros marcados como
assinados, 42 não tinham PDF selado em disco (o selo era best-effort e a request virava
SIGNED assim mesmo). O critério aqui é o ARQUIVO EXISTIR, não o status.
"""

from __future__ import annotations

import logging
import os
import uuid

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo, primeiro_e_ultimo

logger = logging.getLogger(__name__)

#: Mesmo namespace de `gerar_docs_mes_service` — o `document_id` do recibo é determinístico
#: por (funcionário, competência). Divergir aqui criaria um segundo documento para a mesma
#: pessoa no mesmo mês, e nenhum dos dois fecharia.
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "coassinatura-patrimonial")

_SQL_ROSTER_POSTO = text(
    """
    SELECT e.id::text AS eid, e.nome, e.cpf, p.name AS posto
      FROM employees e
      JOIN empresas em ON em.id = e.empresa_id
      JOIN allocations a ON a.employee_id = e.id AND a.is_active
      JOIN posts p ON p.id = a.post_id
     WHERE em.slug = 'conecta_patrimonial' AND e.nome NOT ILIKE '%teste%'
       AND lower(coalesce(e.status,'')) IN ('ativo','afastado_inss','suspenso')
     ORDER BY p.name, e.nome
    """
)

#: A assinatura VÁLIDA daquele documento: status assinado E arquivo selado em disco.
_SQL_ASSINATURA = text(
    "SELECT signed_document_path FROM sig_signature_requests "
    " WHERE document_type = 'recibo_vt_vr' AND CAST(document_id AS text) = :did "
    "   AND status IN ('SIGNED','COMPLETED') AND coalesce(signed_document_path,'') <> '' "
    " ORDER BY signed_at DESC NULLS LAST LIMIT 1"
)


def _nome_arquivo(nome: str) -> str:
    """'Recibo de Vale Transporte e Vale Alimentacao - Marta Silva.pdf'.

    O "Vale Transporte" por extenso não é enfeite: é o que faz `subpasta_do_arquivo`
    classificar em '02 - Benefícios (VA/VT)'. Abreviar joga o recibo na pasta de pessoal.
    """
    return f"Recibo de Vale Transporte e Vale Alimentacao - {primeiro_e_ultimo(nome)}.pdf"


def arquivar_recibos_vtvr(competencia: str, db, dry_run: bool = False) -> dict:
    """Sobe para o kit de cada posto os recibos de VT/VR que o funcionário ASSINOU."""
    mes, ano = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    comp = f"{ano:04d}-{mes:02d}"
    if not dry_run and not gdrive_service._service:
        gdrive_service.check_status()

    rel: dict = {
        "competencia": competencia,
        "roster": 0,
        "publicados": 0,
        "aguardando_assinatura": 0,
        "falhas": 0,
        "por_condominio": {},
    }
    cache: dict = {}

    for r in db.execute(_SQL_ROSTER_POSTO).mappings().all():
        rel["roster"] += 1
        posto = r["posto"]
        try:
            did = str(uuid.uuid5(_NS, f"vtvr:{r['eid']}:{comp}"))
            assinado = db.execute(_SQL_ASSINATURA, {"did": did}).scalar()
            if not assinado or not os.path.exists(assinado):
                # Sem assinatura válida o recibo NÃO entra no kit. Quem abre a solicitação
                # é `gerar_docs_mes_service`; aqui só se constata e se conta.
                rel["aguardando_assinatura"] += 1
                continue

            fn = _nome_arquivo(r["nome"])
            if dry_run:
                rel["publicados"] += 1
                rel["por_condominio"][posto] = rel["por_condominio"].get(posto, 0) + 1
                continue

            folder = pasta_kit_arquivo(posto, competencia, fn, cache)
            if not folder:
                rel["falhas"] += 1
                continue
            if _arquivo_ja_existe(folder, fn):
                rel["publicados"] += 1
                continue
            if gdrive_service.fazer_upload_arquivo(assinado, folder, fn):
                rel["publicados"] += 1
                rel["por_condominio"][posto] = rel["por_condominio"].get(posto, 0) + 1
            else:
                rel["falhas"] += 1
        except Exception as exc:  # noqa: BLE001 — um recibo ruim não derruba os outros
            rel["falhas"] += 1
            logger.warning("recibo VT/VR %s (%s): %s", r["nome"], posto, exc)

    return rel
