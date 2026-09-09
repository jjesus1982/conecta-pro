"""Oráculo — quem assina cada documento e em que NÍVEL, afirmado pela DECISÃO e não pela lista (09/09/2026).

Por que existe: em 09/09 a sessão t6 achou que o contrato do comercial era assinado pela empresa em nível SIMPLES.
Causa: dois vocabulários para a mesma coisa — o DP grava `contract`, o CRM grava `contrato`, e só o inglês estava
em DOCUMENTOS_QUALIFICADOS. O oráculo que existia afirmava o mapa DECLARADO contra ele mesmo, então passava verde.

Este afirma as DECISÕES do dono, pelo texto delas, e não pela lista de constantes:

  1. Todo documento que É UM CONTRATO — na língua que for — a empresa assina com ICP-Brasil (A1).
     Origem: 21/08/2026, contrato como título executivo (CPC 784 §4º, sem testemunha).
  2. Documento do kit que leva o campo do diretor (espelho de ponto, recibo de adiantamento) é CO-ASSINADO:
     funcionário em nível simples, empresa com ICP-Brasil. Origem: 09/09/2026 (revisão do Jordan).
  3. Holerite e recibo de VT/VR são do FUNCIONÁRIO — a empresa não assina. Origem: 21/08/2026.
     Se um dia voltarem a ter signatário COMPANY, o nível tem de ser revisto ANTES: hoje assinariam simples e
     ninguém perceberia (medido: 118 pedidos company desses tipos, todos cancelados, entre 05 e 18/08).
  4. Todo `document_type` GRAVADO no banco tem de estar na política — o que o sistema escreve e a política não
     conhece cai no default calado.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys

CONTRATOS = ("contract", "contrato", "service_contract", "prorrogacao_contrato")
CO_ASSINADOS_DO_KIT = ("kit_documento_coassinado", "espelho_ponto")
SO_DO_FUNCIONARIO = ("payslip", "recibo_vt_vr", "kit_documento")


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db
    from modules.signatures.helpers.solicitar_assinatura_documento import POLITICA_ASSINANTES, nivel_assinatura
    from modules.signatures.services.universal_signature_service import SignerType

    falhas: list[str] = []

    # 1) contrato assina com ICP-Brasil, na língua que for
    for t in CONTRATOS:
        if t not in POLITICA_ASSINANTES:
            falhas.append(f"contrato '{t}' não está na política de assinantes — cai no default calado")
            continue
        if str(nivel_assinatura(t, SignerType.COMPANY)) != "qualified":
            falhas.append(f"contrato '{t}': a empresa assinaria em nível '{nivel_assinatura(t, SignerType.COMPANY)}' "
                          "— a decisão de 21/08 é ICP-Brasil (título executivo sem testemunha)")

    # 2) co-assinado do kit: funcionário + empresa, empresa com ICP
    for t in CO_ASSINADOS_DO_KIT:
        tipos = POLITICA_ASSINANTES.get(t) or []
        papeis = {str(x) for x in tipos}
        if not {"employee", "company"} <= papeis:
            falhas.append(f"'{t}' deveria ser co-assinado (funcionário + empresa) e a política diz {sorted(papeis)}")
        if str(nivel_assinatura(t, SignerType.COMPANY)) != "qualified":
            falhas.append(f"'{t}': a empresa assinaria em '{nivel_assinatura(t, SignerType.COMPANY)}' — decisão de 09/09 é ICP-Brasil")

    # 3) holerite e recibo: só o funcionário
    for t in SO_DO_FUNCIONARIO:
        papeis = {str(x) for x in (POLITICA_ASSINANTES.get(t) or [])}
        if "company" in papeis:
            falhas.append(f"'{t}' voltou a ter signatário COMPANY na política — a decisão de 21/08 é só funcionário; "
                          f"se mudou de propósito, reveja o NÍVEL antes (hoje assinaria "
                          f"'{nivel_assinatura(t, SignerType.COMPANY)}')")

    # 4) todo tipo gravado está na política
    gen = get_db()
    db = await gen.__anext__()
    gravados = [r[0] for r in (await db.execute(text(
        "SELECT DISTINCT document_type FROM sig_signature_requests WHERE document_type IS NOT NULL"))).fetchall()]
    for t in sorted(gravados):
        if t not in POLITICA_ASSINANTES:
            falhas.append(f"o sistema grava '{t}' e a política não conhece esse tipo — assinantes e nível vêm do default")

    print(f"tipos na política: {len(POLITICA_ASSINANTES)} · tipos gravados no banco: {len(gravados)}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) entre a decisão do dono e a política de assinatura")
    print("OK política de assinatura: contratos e co-assinados do kit em ICP-Brasil; holerite e recibo só do funcionário")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
