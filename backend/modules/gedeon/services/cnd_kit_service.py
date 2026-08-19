"""GEDEON — Arquiva as CNDs REAIS (emitidas pelo Conecta PRO) nos kits.

Multi-CNPJ E6: as CNDs deixaram de ser "empresa-wide" — cada CNPJ do Grupo tem
seu conjunto em ged_certidoes (chave cnpj × document_type). Na JANELA HÍBRIDA
da segmentação (kits de ago+set/2026, definição do Jordan: documentos das DUAS
empresas convivem por datas retroativas), os kits recebem as certidões de
ambas: Eletrônica com os nomes legados (idempotente com kits já montados) e
Patrimonial com sufixo do nome de exibição. Após a janela
(MULTICNPJ_KITS_HIBRIDOS_ATE, default 2026-09), mantém ambas até o mapeamento
condomínio→empresa dos kits entrar (E8) — nunca esconde certidão por suposição.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo

logger = logging.getLogger(__name__)

# document_type → nome do arquivo no kit (nomes LEGADOS = Eletrônica/CNPJ1)
CND_NOMES = {
    "certidao_negativa_estadual": "CND Estadual (SEFAZ-AM).pdf",
    "certidao_negativa_trabalhista": "CND Trabalhista (CNDT).pdf",
    "certidao_negativa_municipal": "CND Municipal (Manaus).pdf",
    "certidao_negativa_federal": "CND Federal (RFB-PGFN).pdf",
    "certidao_negativa_fgts": "CRF FGTS (Caixa).pdf",
}

_CNPJ_ELETRONICA = "35710481000103"


def _nome_arquivo(document_type: str, cnpj: str, fantasia: str, sempre_com_empresa: bool = False) -> str | None:
    """Nome do PDF no kit.

    `sempre_com_empresa` liga o sufixo para TODO mundo, inclusive a Eletrônica. Sem isso
    ela ficava com o nome limpo ("CND Estadual (SEFAZ-AM).pdf") e quem abrisse o kit não
    tinha como saber de que empresa era a certidão — medido em 19/08/2026: 5 certidões
    anônimas em cada um dos 7 kits. Certidão sem dono em kit de compliance é o mesmo
    defeito do DCTFWeb da empresa errada, só que mais difícil de enxergar.
    """
    base = CND_NOMES.get(document_type)
    if not base:
        return None
    if cnpj == _CNPJ_ELETRONICA and not sempre_com_empresa:
        return base
    sufixo = (fantasia or cnpj).strip()
    return base.replace(".pdf", f" — {sufixo}.pdf")


# ── A REGRA DO JORDAN, 19/08/2026 ────────────────────────────────────────────
# "A partir da competência 08 o kit deve conter documentação apenas da CONECTA
#  PATRIMONIAL para os condomínios com mão de obra alocada, e da CONECTA ELETRÔNICA
#  para os de segurança eletrônica."
#
# O kit de JULHO fica como está — decisão explícita dele. Por isso a regra tem corte de
# competência em vez de valer para trás: mexer no kit que já vai ser entregue dia 25 é
# reescrever história, não corrigir processo.
#
# Não é "uma empresa por kit". É a empresa DE CADA CONTRATO: o VILLA DOS PÁSSAROS tem
# mão de obra pela Patrimonial E CFTV pela Eletrônica, e responde pelas duas. Por isso a
# fonte é `contracts.empresa_id`, não um mapa de condomínio.
REGRA_EMPREGADORA_DESDE = "08.2026"

_SQL_CNPJS_DO_CLIENTE = text(
    """
    SELECT DISTINCT regexp_replace(coalesce(em.cnpj,''), '[^0-9]', '', 'g') AS cnpj
      FROM clients c
      JOIN contracts ct ON ct.client_id = c.id AND ct.status::text = 'active'
      JOIN empresas em ON em.id = ct.empresa_id
     WHERE upper(btrim(c.name)) = upper(btrim(:nome))
        OR upper(btrim(c.name)) LIKE '%' || upper(btrim(:nome)) || '%'
        OR upper(btrim(:nome)) LIKE '%' || upper(btrim(c.name)) || '%'
    """
)


def _competencia_ge(a: str, b: str) -> bool:
    """'08.2026' >= '08.2026'. Compara por (ano, mês), não por string."""
    ma, aa = int(a.split(".")[0]), int(a.split(".")[1])
    mb, ab = int(b.split(".")[0]), int(b.split(".")[1])
    return (aa, ma) >= (ab, mb)


def cnpjs_do_kit(db, condominio: str) -> set[str]:
    """CNPJs que podem aparecer no kit deste condomínio — os das empresas que EMITEM os
    contratos ativos dele. Vazio = não sei, e aí não filtro nada (na dúvida, não escondo
    documento de compliance)."""
    from modules.gedeon.services.kit_layout import nome_pasta_condominio

    # O apelido de CONDOMINIOS_PADRAO ("VILLA PÁSSAROS", com acento) não casa com a razão
    # social ("CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS"). O mesmo tradutor que resolve a
    # pasta do Drive resolve aqui — um lugar só para as duas línguas da casa.
    alvo = nome_pasta_condominio(condominio) or condominio
    try:
        return {r[0] for r in db.execute(_SQL_CNPJS_DO_CLIENTE, {"nome": alvo}).fetchall() if r[0]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("cnpjs_do_kit(%s): %s", condominio, exc)
        return set()


def arquivar_cnds(competencia: str, condominios: list[str], dry_run: bool = False) -> dict:
    """Replica as CNDs emitidas (com PDF e válidas) nos kits de cada condomínio.

    Kit híbrido: certidões de TODAS as empresas ativas do Grupo entram em todos
    os kits durante a transição — princípio: melhor certidão a mais que
    compliance invisível (pré-mortem F4).
    """
    from core.database.session import get_sync_db

    if not gdrive_service._service:
        gdrive_service.check_status()
    rel = {"competencia": competencia, "cnds": [], "replicas": 0, "sem_pdf": []}

    with get_sync_db() as db:
        rows = db.execute(
            text(
                "SELECT g.document_type, g.file_path, g.expiry_date, g.cnpj, "
                "       COALESCE(e.nome_fantasia, g.cnpj) AS fantasia "
                "FROM ged_certidoes g "
                "LEFT JOIN empresas e "
                "  ON REGEXP_REPLACE(e.cnpj, '[^0-9]', '', 'g') = g.cnpj AND e.status = 'ativa' "
                "WHERE g.document_type = ANY(:dts) "
                "ORDER BY (g.cnpj = :cnpj1) DESC, g.document_type"
            ),
            {"dts": list(CND_NOMES.keys()), "cnpj1": _CNPJ_ELETRONICA},
        ).fetchall()

    aplica_regra = _competencia_ge(competencia, REGRA_EMPREGADORA_DESDE)
    rel["regra_por_empresa"] = aplica_regra
    rel["barradas"] = []

    cnpjs_por_cond: dict[str, set] = {}
    if aplica_regra:
        with get_sync_db() as db:
            cnpjs_por_cond = {c: cnpjs_do_kit(db, c) for c in condominios}

    for document_type, file_path, _expiry, cnpj, fantasia in rows:
        _cnpj = cnpj or _CNPJ_ELETRONICA
        fn = _nome_arquivo(document_type, _cnpj, fantasia, sempre_com_empresa=aplica_regra)
        if not fn or not file_path or not os.path.exists(file_path):
            rel["sem_pdf"].append(f"{document_type} ({fantasia})")
            continue
        rel["cnds"].append(fn)
        if dry_run:
            continue
        for cond in condominios:
            # Da competência REGRA_EMPREGADORA_DESDE em diante, o kit só recebe certidão
            # das empresas que EMITEM os contratos ativos daquele condomínio. Conjunto
            # vazio = não consegui descobrir: aí não filtro, porque esconder certidão por
            # dúvida é pior que mostrar uma a mais.
            permitidos = cnpjs_por_cond.get(cond) or set()
            if aplica_regra and permitidos and _cnpj not in permitidos:
                rel["barradas"].append(f"{fn} → {cond}")
                continue
            folder = pasta_kit_arquivo(cond, competencia, fn)  # subpasta "3. Impostos e Certidões"
            if folder and not _arquivo_ja_existe(folder, fn):
                if gdrive_service.fazer_upload_arquivo(file_path, folder, fn):
                    rel["replicas"] += 1
    rel["barradas"] = sorted(set(rel["barradas"]))[:12]
    return rel
