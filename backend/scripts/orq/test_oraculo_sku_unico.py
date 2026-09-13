"""Oráculo — uniforme/EPI: um SKU é um só, e todo item tem tamanho, mínimo e máximo (frente 10, 12/09/2026).

Pré-mortem da frente 10: *"Blazer Feminino M" e "BLAZER FEMININO - M" viram dois itens, e o
estoque mínimo passa a ser conferido por metade.* Decisão tomada: SKU normalizado NA ESCRITA com a
régua do `_normalize` do Hermes (`modules/gedeon/agents/hermes.py`): NFKD, maiúsculas, sem acento,
separadores colapsados.

Estado medido no nascimento (staging, 12/09): não existia grade nenhuma — `health_epi_catalog`
tinha 5 itens ativos sem tamanho, sem mínimo, sem máximo; `health_epi_inventory` (que tem as
colunas) tinha 0 linhas; `gp_epi_deliveries` tinha 220 entregas com o nome do item em texto livre.
A tabela `sst_uniforme_grade` não existia → VERMELHO por ausência do mecanismo.

Três afirmações:
  1. Nenhum par de linhas da grade normaliza para o mesmo SKU, e o `sku_norm` gravado é o que a
     régua produz (uma escrita que passe por fora do normalizador aparece aqui).
  2. Toda linha ativa da grade tem tamanho, mínimo e máximo, com mínimo ≤ máximo.
  3. Todo item ATIVO do catálogo de EPI (`health_epi_catalog`) tem ao menos uma linha de grade —
     item sem grade é item cujo mínimo ninguém confere.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    falhas: list[str] = []
    try:
        # régua única: a MESMA função que grava. Cópia local divergiria e calaria.
        from modules.operacional.controllers.redesign_builders._frente_10 import sku_norm
    except ImportError as e:
        print(f"FALHOU: normalizador de SKU não existe ({e}) — SKU não é normalizado na escrita")
        raise AssertionError("normalizador ausente") from e
    gen = get_db()
    db = await gen.__anext__()
    try:
        existe = (await db.execute(text("SELECT to_regclass('public.sst_uniforme_grade')"))).scalar()
        if not existe:
            print("FALHOU: tabela sst_uniforme_grade não existe — não há grade de tamanho nem mínimo/máximo por SKU")
            raise AssertionError("mecanismo de grade ausente")

        grade = (await db.execute(text(
            "SELECT id, item, tamanho, sku_norm, minimo, maximo FROM sst_uniforme_grade WHERE ativo ORDER BY id"
        ))).fetchall()

        # 1) SKU único pela régua, e a régua foi a que gravou
        vistos: dict[str, int] = {}
        for gid, item, tam, norm, _mi, _ma in grade:
            esperado = sku_norm(item, tam)
            if norm != esperado:
                falhas.append(f"grade #{gid} '{item} {tam}': sku_norm gravado '{norm}' ≠ régua '{esperado}'")
            if esperado in vistos:
                falhas.append(f"grade #{gid} '{item} {tam}' duplica #{vistos[esperado]} (mesmo SKU '{esperado}')")
            else:
                vistos[esperado] = gid

        # 2) tamanho + mínimo + máximo em toda linha
        for gid, item, tam, _n, mi, ma in grade:
            if not (tam or "").strip():
                falhas.append(f"grade #{gid} '{item}': sem tamanho")
            if mi is None or ma is None:
                falhas.append(f"grade #{gid} '{item} {tam}': mínimo/máximo ausente")
            elif mi > ma:
                falhas.append(f"grade #{gid} '{item} {tam}': mínimo {mi} > máximo {ma}")

        # 3) item ativo do catálogo sem grade
        sem_grade = (await db.execute(text(
            "SELECT c.nome FROM health_epi_catalog c WHERE coalesce(c.ativo,true) "
            "AND NOT EXISTS (SELECT 1 FROM sst_uniforme_grade g WHERE g.catalog_id = c.id AND g.ativo) ORDER BY 1"
        ))).fetchall()
        for (nome,) in sem_grade:
            falhas.append(f"catálogo '{nome}': ativo e sem nenhuma linha de grade (tamanho/mínimo/máximo)")

        print(f"grade: {len(grade)} SKU(s) ativo(s) · {len(vistos)} distintos pela régua · "
              f"catálogo sem grade: {len(sem_grade)}")
    finally:
        try:
            await gen.aclose()
        except Exception:  # noqa: BLE001
            pass

    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na grade de uniforme/EPI")
    print("OK sku_unico: nenhum SKU duplicado pela régua e todo item tem tamanho, mínimo e máximo")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print("VERMELHO:", e)
        sys.exit(1)
