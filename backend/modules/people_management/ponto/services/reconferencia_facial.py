"""Reconferência do rosto NO SERVIDOR — a batida offline não vale pela palavra do aparelho.

Frente 2 (13/09/2026). Offline o app compara o rosto no próprio celular (`face-api.js`,
`distance < threshold`). Isso é o que torna a batida possível sem sinal — e é também a porta que
o pré-mortem descreve: *"se o descriptor for comparado no aparelho e a batida aceita sem servidor,
quem controla o aparelho controla a batida"*.

Então a comparação do aparelho serve só para decidir se VALE A PENA guardar a batida. Quem decide
se ela é válida é este arquivo, na sincronização, com o MESMO limiar do fluxo online — e o limiar
vem de `system_configs`, não chumbado, porque constante de negócio que envelhece no código é
exatamente como duas réguas divergem e a que diverge cala.

Não há biblioteca de visão aqui: o descriptor do `face-api.js` é um vetor de 128 floats e a
comparação é a distância euclidiana entre ele e `employees.face_descriptor`. É a mesma conta que o
`compareFaces` do front faz — a diferença é QUEM a executa.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Parâmetros e o valor sugerido quando a chave não existe em `system_configs`. O default NUNCA é
#: mais permissivo que o valor proposto: dado ausente aperta a régua, não afrouxa.
PARAMETROS_PADRAO: dict[str, float] = {
    # mesmo limiar que o app usa hoje no navegador (FacialCapture.threshold = 0.68)
    "ponto.facial.limiar_distancia": 0.68,
    # 5 min entre o relógio do aparelho e o do servidor. Acima disso a batida é suspeita.
    "ponto.offline.divergencia_relogio_max_seg": 300,
    # validade do descriptor em cache no aparelho (LGPD: biometria não fica lá para sempre)
    "ponto.offline.validade_cache_horas": 24,
    # a mesma régua de 20 min do importador do Tangerino
    "ponto.offline.janela_idempotencia_min": 20,
}

#: 128 floats é o tamanho do descriptor do face-api.js. Vetor de outro tamanho não é comparável —
#: e comparar mesmo assim daria uma distância qualquer, que passaria por resultado.
DIM_DESCRIPTOR = 128


async def parametros(db) -> dict[str, float]:
    """Lê os parâmetros de `system_configs`, caindo no padrão declarado acima.

    `coalesce(nullif(valor,''), ...)` de propósito: chave existente com valor vazio é ausência,
    e `coalesce` puro não cai para o default em string vazia.
    """
    fora: dict[str, float] = dict(PARAMETROS_PADRAO)
    try:
        linhas = (
            await db.execute(
                text(
                    "SELECT chave, nullif(trim(valor),'') FROM system_configs "
                    "WHERE chave = ANY(:ks) AND ativo"
                ),
                {"ks": list(PARAMETROS_PADRAO)},
            )
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("reconferência: system_configs indisponível (%s) — usando os padrões", exc)
        return fora
    for chave, valor in linhas:
        if valor is None:
            continue
        try:
            fora[chave] = float(valor)
        except (TypeError, ValueError):
            logger.warning("reconferência: %s=%r não é número — mantendo o padrão", chave, valor)
    return fora


def distancia(a: list[float], b: list[float]) -> float | None:
    """Distância euclidiana entre dois descriptors. `None` quando não são comparáveis.

    None ≠ 999: devolver um número grande faria "não sei comparar" virar "não é a pessoa", e o
    chamador não teria como distinguir. Quem chama decide o que fazer com a ignorância.
    """
    if not a or not b or len(a) != len(b) or len(a) != DIM_DESCRIPTOR:
        return None
    try:
        return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b, strict=True)))
    except (TypeError, ValueError):
        return None


async def referencia(db, employee_id: str) -> list[float] | None:
    """`employees.face_descriptor` da pessoa, ou None se não houver rosto cadastrado."""
    bruto = (
        await db.execute(
            text("SELECT face_descriptor FROM employees WHERE id = CAST(:e AS uuid)"),
            {"e": str(employee_id)},
        )
    ).scalar()
    if not bruto:
        return None
    try:
        vetor = json.loads(bruto) if isinstance(bruto, str) else bruto
    except (ValueError, TypeError):
        return None
    return vetor if isinstance(vetor, list) and len(vetor) == DIM_DESCRIPTOR else None


async def reconferir(db, employee_id: str, descriptor: list[float], limiar: float) -> dict[str, Any]:
    """Compara, no SERVIDOR, o rosto capturado offline contra a referência cadastrada.

    Devolve `match`: True (passou), False (não é a pessoa) ou **None** (não deu para comparar —
    sem rosto cadastrado, descriptor ausente ou de outra dimensão). None é o caso sensível e o
    default da casa manda tratá-lo como bloqueio: quem chama manda a batida para a conferência do
    DP, nunca a aceita como definitiva.
    """
    ref = await referencia(db, employee_id)
    if ref is None:
        return {"match": None, "distancia": None, "limiar": limiar, "motivo": "sem_rosto_cadastrado"}
    d = distancia(descriptor, ref)
    if d is None:
        return {"match": None, "distancia": None, "limiar": limiar, "motivo": "descriptor_incomparavel"}
    return {
        "match": d < limiar,
        "distancia": round(d, 4),
        "limiar": limiar,
        # a confiança que se pode afirmar a partir da distância, na mesma escala do fluxo online
        "confianca": round(max(0.0, 1.0 - d / limiar), 4) if d < limiar else 0.0,
        "motivo": None if d < limiar else "nao_bateu",
    }


def demo() -> None:
    """Auto-checagem: roda com `python3 reconferencia_facial.py`. Sem framework, sem fixture."""
    a = [0.0] * DIM_DESCRIPTOR
    b = [0.0] * DIM_DESCRIPTOR
    b[0] = 0.5
    assert distancia(a, a) == 0.0
    assert abs(distancia(a, b) - 0.5) < 1e-9
    # incomparáveis devolvem None, nunca um número que passaria por veredito
    assert distancia(a, []) is None
    assert distancia(a, [0.0] * 64) is None
    assert distancia([], []) is None
    # a distância cresce com a diferença — a régua tem o sentido certo
    c = [0.0] * DIM_DESCRIPTOR
    c[0] = 1.5
    assert distancia(a, c) > distancia(a, b)
    print("OK reconferencia_facial: distância euclidiana, e incomparável é None (não é 'não bateu')")


if __name__ == "__main__":
    demo()
