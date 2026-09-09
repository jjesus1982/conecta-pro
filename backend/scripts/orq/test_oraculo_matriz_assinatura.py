"""Quem assina o quê — a matriz definida pelo Jordan em 21/08/2026.

    Folha de ponto (espelho_ponto) ....... funcionário + EMPRESA
    Contrato de trabalho ................. funcionário + EMPRESA
    Prorrogação de contrato .............. funcionário + EMPRESA
    Contracheque (payslip) ............... só o FUNCIONÁRIO
    Recibo de VT e VR .................... só o FUNCIONÁRIO

Na palavra dele: "folha de ponto pelas duas partes, empresa e funcionários; contracheque
e recibo de vt e vr assinados apenas pelos funcionários; contratos de trabalho,
prorrogações assinados pelas duas partes".

Esta regra REVOGA a de 05/08/2026, que fazia holerite e recibo co-assinados. O custo da
antiga foi medido: 67 holerites e 51 recibos parados no lado da empresa, e 14 documentos
que o FUNCIONÁRIO já tinha assinado presos em SIGNED esperando uma contraparte que nunca
vinha — 3 de 107 recibos assinados desde 15/07.

Afirma a REGRA, não a fotografia: não conta pendências nem fixa quantidades. Se amanhã
houver 500 holerites, o oráculo continua valendo.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402
from modules.signatures.helpers.solicitar_assinatura_documento import (  # noqa: E402
    POLITICA_ASSINANTES,
    nivel_assinatura,
)
from modules.signatures.services.universal_signature_service import (  # noqa: E402
    SignatureLevel,
    SignerType,
)

SO_FUNCIONARIO = {"payslip", "recibo_vt_vr"}
DUAS_PARTES = {"espelho_ponto", "contract", "prorrogacao_contrato"}


async def main() -> None:
    erros: list[str] = []

    for dt in sorted(SO_FUNCIONARIO):
        tipos = POLITICA_ASSINANTES.get(dt)
        if tipos != [SignerType.EMPLOYEE]:
            erros.append(f"{dt}: deveria ser só EMPLOYEE, é {tipos}")

    for dt in sorted(DUAS_PARTES):
        tipos = POLITICA_ASSINANTES.get(dt) or []
        if SignerType.EMPLOYEE not in tipos or SignerType.COMPANY not in tipos:
            erros.append(f"{dt}: deveria ter EMPLOYEE e COMPANY, é {tipos}")

    assert not erros, "matriz de assinatura divergente — " + " ; ".join(erros)

    # Coerência: quem não tem COMPANY na política não pode estar marcado como qualificado,
    # porque só COMPANY assina em nível QUALIFIED. Estar lá seria letra morta enganosa.
    incoerentes = [dt for dt in SO_FUNCIONARIO if nivel_assinatura(dt, SignerType.COMPANY) == SignatureLevel.QUALIFIED]
    assert not incoerentes, f"{incoerentes} marcados como qualificados sem ter COMPANY na política — letra morta"

    with get_sync_db() as db:
        # ── O VOCABULÁRIO DECLARADO É O MESMO QUE O BANCO GRAVA? ──────────────────────
        # Este oráculo passou verde por semanas afirmando `contract`, enquanto o CRM
        # gravava `contrato` — e `nivel_assinatura("contrato", COMPANY)` devolvia SIMPLE.
        # O contrato, documento de maior consequência jurídica da casa, era o único que a
        # empresa assinava SEM o A1 ICP-Brasil, enquanto holerite e espelho de ponto
        # assinavam com ele. Medido em 09/09/2026.
        #
        # A lição que vira trava: afirmar o mapa DECLARADO não prova nada sobre o que o
        # sistema escreve. Todo `document_type` que existe no banco tem de ser conhecido
        # pela política — tipo que ninguém declarou cai no default e assina fraco calado.
        reais = {r[0] for r in db.execute(text(
            "SELECT DISTINCT document_type FROM sig_signature_requests "
            " WHERE document_type IS NOT NULL AND document_type <> ''")).fetchall()}
        desconhecidos = sorted(reais - set(POLITICA_ASSINANTES))
        assert not desconhecidos, (
            f"tipos gravados que a política NÃO conhece: {desconhecidos} — caem no default "
            "e assinam em nível simples sem ninguém perceber")
        print(f"OK os {len(reais)} tipos gravados no banco são todos declarados na política")

        # E todo tipo que É contrato assina QUALIFIED pela empresa, escrito em que língua for.
        for dt in sorted(t for t in reais if "contrat" in t or "contract" in t):
            nivel = nivel_assinatura(dt, SignerType.COMPANY)
            assert nivel == SignatureLevel.QUALIFIED, (
                f"'{dt}' é contrato e a empresa o assina em nível {nivel.value} — "
                "contrato exige A1 ICP-Brasil")
            print(f"OK {dt}: empresa assina em {nivel.value}")

        # Nenhuma exigência VIVA da empresa nos documentos que são só do funcionário.
        vivas = (
            db.execute(
                text(
                    "SELECT document_type, count(*) FROM sig_signature_requests "
                    " WHERE signer_type = 'company' AND document_type = ANY(:dts) "
                    "   AND status NOT IN ('CANCELLED','REJECTED') GROUP BY 1"
                ),
                {"dts": sorted(SO_FUNCIONARIO)},
            )
            .mappings()
            .all()
        )
        assert not vivas, "exigência viva da empresa em documento que é só do funcionário — " + " ; ".join(
            f"{r['document_type']}: {r['count']}" for r in vivas
        )

        # Suspenders: o defeito era o funcionário assinar e o documento não fechar.
        presos = db.execute(
            text(
                "SELECT count(*) FROM sig_signature_requests r "
                " WHERE r.signer_type = 'employee' AND r.status = 'SIGNED' "
                "   AND r.document_type = ANY(:dts)"
            ),
            {"dts": sorted(SO_FUNCIONARIO)},
        ).scalar()
        assert not presos, (
            f"{presos} documento(s) assinados pelo funcionário sem fechar — "
            "só ele era exigido, deveriam estar COMPLETED"
        )

    print(f"OK só o funcionário assina: {sorted(SO_FUNCIONARIO)}")
    print(f"OK duas partes assinam: {sorted(DUAS_PARTES)}")
    print("OK nenhuma exigência viva da empresa onde ela não assina")
    print("TEST oraculo_matriz_assinatura PASS")


if __name__ == "__main__":
    asyncio.run(main())
