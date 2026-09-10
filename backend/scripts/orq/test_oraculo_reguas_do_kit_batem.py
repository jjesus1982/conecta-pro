"""Oráculo — as réguas do kit falam do MESMO documento (10/09/2026).

Esta casa tem sete lugares que respondem "onde este documento pertence?": o bloco do contrato
(`completude_slots._BLOCO_DE_TIPO`, que dá o percentual), a pasta do Drive
(`google_drive_service.PASTA_DO_TIPO`), a categoria dentro de Funcionarios, o checklist do Drive,
o classificador por NOME do arquivo (`kit_layout.subpasta_do_arquivo`), o `kit_structure` do Onvio
e o `drive_kit_classifier`. Sete respostas para uma pergunta é uma promessa de divergência.

Medido em 10/09/2026, antes deste oráculo existir:

    22 tipos tinham PASTA e bloco NENHUM  →  o documento chegava ao cliente e a completude o
                                             ignorava (das_simples_nacional, gps_inss, grf_fgts,
                                             os 5 do SINETRAM/Sólides, dctfweb_*, nfs_servico)
     5 tipos tinham BLOCO e pasta NENHUMA →  contavam no percentual e não tinham para onde ir
     1 tipo satisfazia o bloco errado     →  `escala_mes` valia como "ponto", e a escala saiu do
                                             kit por decisão do Jordan em 09/09: um kit com escala
                                             e sem folha de ponto lia como se tivesse o ponto

A primeira linha é metade da explicação para "55 kits montados, ZERO aprovados, UM enviado em oito
meses": o kit não fechava porque a régua não enxergava o que estava lá.

Afirma três coisas:
  1. Todo tipo GRAVADO no banco tem pasta declarada (senão vai para Financeiro por omissão).
  2. Todo tipo com bloco tem pasta — contar sem saber onde guardar é meio caminho.
  3. Todo bloco usado é um bloco do CHECKLIST do Drive, e a escala não é bloco de ponto.

Nem todo tipo precisa de BLOCO: admissional (aso, ficha_empregado), 13º e "outros" existem no kit
e não entram na completude do mês. Isso é decisão, não esquecimento — e está nomeado em FORA_DA_REGUA.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import sys

#: Tipos que EXISTEM no kit e de propósito não contam na completude do mês.
FORA_DA_REGUA = {
    "aso",
    "ficha_empregado",
    "ficha_registro",
    "aviso_previo",
    "aviso_previo_ferias",
    "atestado",
    "ferias",
    "rescisao",
    "contrato_trabalho",
    "decimo_terceiro",
    "recibo_decimo_terceiro",
    "outros",
    "outro",
    "escala_mes",
    "certidao",
    "contracheque_onvio",
    "comp_fgts_rescisao",
    "gfd_fgts_rescisao",
    "relatorio_gfd_rescisao",
    "recibo_adiantamento",
    "comprovante_pagamento",
}


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db
    from modules.gedeon.services.completude_slots import _BLOCO_DE_TIPO
    from modules.gedeon.services.kit_completude_service import CHECKLIST
    from modules.people_management.ged.services.google_drive_service import (
        CATEGORIA_FUNCIONARIO,
        PASTA_DO_TIPO,
    )

    blocos_validos = {c["key"] for c in CHECKLIST}
    falhas: list[str] = []

    gen = get_db()
    db = await gen.__anext__()
    gravados = {
        r[0]: r[1]
        for r in (await db.execute(text("SELECT document_type, count(*) FROM ged_kit_documents GROUP BY 1"))).fetchall()
    }

    # 1) todo tipo gravado tem pasta (por-funcionário resolve por CATEGORIA_FUNCIONARIO)
    for t, n in sorted(gravados.items()):
        if t not in PASTA_DO_TIPO and t not in CATEGORIA_FUNCIONARIO:
            falhas.append(f"'{t}' ({n} documentos) não tem pasta declarada — Financeiro por omissão")

    # 2) todo tipo com bloco tem pasta
    for t, bloco in sorted(_BLOCO_DE_TIPO.items()):
        if t not in PASTA_DO_TIPO and t not in CATEGORIA_FUNCIONARIO:
            falhas.append(
                f"'{t}' conta no bloco '{bloco}' e não tem pasta — o percentual sobe e o arquivo não sabe onde morar"
            )

    # 3) todo bloco é do checklist, e a escala não é ponto
    for t, bloco in sorted(_BLOCO_DE_TIPO.items()):
        if bloco not in blocos_validos:
            falhas.append(f"'{t}' aponta para o bloco '{bloco}', que não existe no CHECKLIST do Drive")
    if _BLOCO_DE_TIPO.get("escala_mes"):
        falhas.append(
            "'escala_mes' voltou a ter bloco na régua — a escala saiu do kit em 09/09 e, "
            "valendo como ponto, um kit sem folha de ponto lê como completo"
        )

    # 4) o que existe no kit, não está fora da régua de propósito, e mesmo assim não conta
    sem_bloco = sorted(t for t in gravados if t not in _BLOCO_DE_TIPO and t not in FORA_DA_REGUA and gravados[t] >= 5)
    for t in sem_bloco:
        falhas.append(
            f"'{t}' ({gravados[t]} documentos) chega ao cliente e não conta em bloco nenhum "
            "— ou entra na régua, ou entra em FORA_DA_REGUA com o motivo"
        )

    print(
        f"tipos no banco: {len(gravados)} · com pasta: "
        f"{sum(1 for t in gravados if t in PASTA_DO_TIPO or t in CATEGORIA_FUNCIONARIO)} · "
        f"com bloco: {sum(1 for t in gravados if t in _BLOCO_DE_TIPO)} · "
        f"fora da régua de propósito: {sum(1 for t in gravados if t in FORA_DA_REGUA)}"
    )
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} divergência(s) entre as réguas do kit")
    print("OK: pasta, bloco e checklist falam do mesmo documento")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
