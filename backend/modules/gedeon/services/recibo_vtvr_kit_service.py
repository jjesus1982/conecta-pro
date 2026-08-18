"""GEDEON — Recibo de VT e VR por funcionário, arquivado no kit do posto onde ele trabalha.

O comprovante de pagamento ao Sólides/Sinetran é da EMPRESA e vai replicado nos 7 kits
(mesmo tratamento do INSS), porque o pagamento não é fatiado por condomínio: medido no
extrato, o Sólides recebeu de 8 a 20 pagamentos por mês e o Sinetran de 5 a 6 — se fosse
rateio de posto seriam 7 todos os meses. O que o condomínio consegue CONFERIR é este
recibo: uma folha por pessoa, com os dias e os valores da nossa própria folha, na pasta
do posto onde essa pessoa trabalha.

Reusa o motor de sempre (`calcular_folha_colaborador` → `montar_recibo_vt_vr_pdf`), o
mesmo que gera o recibo do portal do funcionário. Aqui só decide ONDE cada um é arquivado.
"""

from __future__ import annotations

import logging
import os
import tempfile

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo, primeiro_e_ultimo

logger = logging.getLogger(__name__)

# Roster + posto. O posto vem da alocação vigente; quem não tem alocação fica de fora do
# kit (o recibo dele continua saindo pelo portal — só não há condomínio a quem entregar).
_SQL_ROSTER_POSTO = text(
    """
    SELECT e.id::text AS eid, e.nome, e.cpf, e.pis, e.matricula,
           to_char(e.data_admissao,'YYYY-MM-DD') AS adm, p.name AS posto
      FROM employees e
      JOIN empresas em ON em.id = e.empresa_id
      JOIN allocations a ON a.employee_id = e.id AND a.is_active
      JOIN posts p ON p.id = a.post_id
     WHERE em.slug = 'conecta_patrimonial' AND e.nome NOT ILIKE '%teste%'
       AND lower(coalesce(e.status,'')) IN ('ativo','afastado_inss','suspenso')
     ORDER BY p.name, e.nome
    """
)


def _nome_arquivo(nome: str) -> str:
    """'Recibo de Vale Transporte e Vale Alimentação — Marta Silva.pdf'.

    O 'Vale Transporte' por extenso não é enfeite: é o que faz `subpasta_do_arquivo`
    classificar em '03 - Benefícios (VA/VT)'. Abreviar para 'VT e VR' joga o recibo na
    pasta de pessoal.
    """
    return f"Recibo de Vale Transporte e Vale Alimentacao - {primeiro_e_ultimo(nome)}.pdf"


def arquivar_recibos_vtvr(competencia: str, db, dry_run: bool = False) -> dict:
    """Gera o recibo de VT/VR de cada funcionário alocado e arquiva no kit do posto dele."""
    from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador
    from modules.people_management.folha.services.recibo_vt_vr_pdf import montar_recibo_vt_vr_pdf

    mes, ano = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    if not dry_run and not gdrive_service._service:
        gdrive_service.check_status()

    rel: dict = {
        "competencia": competencia,
        "roster": 0,
        "gerados": 0,
        "pulados": 0,
        "falhas": 0,
        "por_condominio": {},
    }
    cache: dict = {}

    for r in db.execute(_SQL_ROSTER_POSTO).mappings().all():
        rel["roster"] += 1
        posto = r["posto"]
        try:
            hol = calcular_folha_colaborador(db, r["eid"], mes, ano)
            if not hol or "error" in hol:
                rel["pulados"] += 1
                continue
            fn = _nome_arquivo(r["nome"])
            if dry_run:
                rel["gerados"] += 1
                rel["por_condominio"][posto] = rel["por_condominio"].get(posto, 0) + 1
                continue

            pdf = montar_recibo_vt_vr_pdf(
                hol,
                {
                    "cpf": r["cpf"],
                    "pis": r["pis"],
                    "matricula": r["matricula"],
                    "data_admissao": r["adm"],
                },
            )
            folder = pasta_kit_arquivo(posto, competencia, fn, cache)
            if not folder:
                rel["falhas"] += 1
                continue
            if _arquivo_ja_existe(folder, fn):
                rel["pulados"] += 1
                continue
            path = os.path.join(tempfile.gettempdir(), fn)
            with open(path, "wb") as fh:
                fh.write(pdf)
            if gdrive_service.fazer_upload_arquivo(path, folder, fn):
                rel["gerados"] += 1
                rel["por_condominio"][posto] = rel["por_condominio"].get(posto, 0) + 1
            else:
                rel["falhas"] += 1
        except Exception as exc:  # noqa: BLE001 — um recibo ruim não derruba os outros 51
            rel["falhas"] += 1
            logger.warning("recibo VT/VR %s (%s): %s", r["nome"], posto, exc)

    return rel
