#!/usr/bin/env python3
"""Remove a CÓPIA de um documento que ocupa o mesmo slot duas vezes.

⚠️ A PREMISSA DO PROMPT ESTAVA ERRADA, e por isso este script existe do jeito que existe.
O diagnóstico dizia "2.625 documentos · 1.164 únicos (kit+tipo+nome) → 1.461 DUPLICADOS,
56% do acervo, pior caso 23 cópias". Aquela chave IGNORA o `employee_id` — e um kit tem um
slot de contracheque POR FUNCIONÁRIO. Somando o funcionário, sobram 59 linhas extras em
2.625, e não 1.461.

Das 59, medindo direito: **31 são cópia de verdade** e 28 são documentos DIFERENTES com
rótulo genérico (`document_type='outros'`, `document_name='Outros'`). Apagar pela chave do
prompt destruiria 28 documentos reais.

O QUE DISTINGUE UMA DA OUTRA É O NOME LÓGICO DO ARQUIVO. O `file_path` guarda um prefixo
aleatório de armazenamento, então duas linhas do mesmo documento parecem diferentes:

    .../ce4_Boleto_portaria_limpeza_novembro_NF803.pdf
    .../a70_Boleto_portaria_limpeza_novembro_NF803.pdf

Tirando o prefixo, é o mesmo boleto duas vezes. É essa a chave usada aqui — e ela cobre 31
linhas, 1,2% do acervo.

QUAL FICA: a mais ANTIGA do grupo, e com preferência absoluta para quem tem `file_path`. A
mais antiga porque é a que o resto do sistema já pode ter referenciado; nunca se apaga a
única linha com arquivo.

💾 O ARQUIVO EM DISCO NÃO É TOCADO. Isto remove a LINHA do slot, não o PDF. Se a decisão se
mostrar errada, o backup em `_dedup_backup_20260814` tem cada linha removida na íntegra.

Ensaio é o padrão. Aplicar: --aplicar --forcar (são 31, acima do teto de 10).

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
      python3 /app/scripts/dedup_kit_documents.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/qa")

from _mutacao import Mutacao  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

#: Tira o prefixo aleatório de armazenamento (`ce4_`, `a70_`…) e o diretório, deixando o
#: nome com que o documento foi gerado. É o que revela a cópia.
_LOGICO = "regexp_replace(coalesce(file_path,''), '^.*/[0-9a-f]{3,}_', '')"

SQL_SOBRANDO = text(
    f"WITH n AS ( "
    f"  SELECT id, kit_id, document_type, document_name, employee_id, file_path, created_at, "
    f"         {_LOGICO} AS logico "
    f"  FROM ged_kit_documents), "
    f"ranked AS ( "
    f"  SELECT n.*, row_number() OVER ( "
    f"    PARTITION BY kit_id, document_type, document_name, "
    f"                 coalesce(employee_id::text,'-'), logico "
    # quem tem arquivo fica na frente; entre iguais, a mais antiga
    f"    ORDER BY (file_path IS NULL OR file_path = ''), created_at, id) AS pos "
    f"  FROM n) "
    f"SELECT r.id::text AS id, to_char(k.reference_month,'YYYY-MM') AS comp, "
    f"       r.document_type, left(r.logico, 40) AS arquivo, r.pos "
    f"FROM ranked r JOIN ged_document_kits k ON k.id = r.kit_id "
    f"WHERE r.pos > 1 ORDER BY 2 DESC, 3"
)


async def main() -> int:
    m = Mutacao("remover cópia do mesmo documento no mesmo slot", teto=10)

    async with async_session_factory() as db:
        linhas = (await db.execute(SQL_SOBRANDO)).mappings().all()
        if not linhas:
            print("\nNenhuma cópia — o acervo já está limpo.")
            return 0

        alvos = [
            (r["id"][:8], f'{r["comp"]} · {r["document_type"]} · {r["arquivo"]} '
                          f'(cópia nº {r["pos"]})')
            for r in linhas
        ]
        print(f"\n══ cópias do MESMO arquivo no MESMO slot — {len(linhas)} linha(s) ══")
        print("   (o PDF em disco NÃO é tocado; sai a linha duplicada do slot)")

        if not m.confirmar(alvos):
            return 0

        # backup íntegro ANTES de remover — 31 linhas cabem inteiras numa tabela
        await db.execute(text(
            "CREATE TABLE IF NOT EXISTS _dedup_backup_20260814 "
            "AS SELECT * FROM ged_kit_documents WHERE false"))
        ids = [r["id"] for r in linhas]
        await db.execute(text(
            "INSERT INTO _dedup_backup_20260814 "
            "SELECT * FROM ged_kit_documents WHERE id::text = ANY(:ids)"), {"ids": ids})

        n = (await db.execute(text(
            "DELETE FROM ged_kit_documents WHERE id::text = ANY(:ids)"), {"ids": ids})).rowcount
        await db.commit()
        m.feito(n)

        # o denominador da completude muda quando slot sai — recalcula tudo
        from modules.gedeon.services.completude_slots import _SQL_COMPETENCIA  # noqa: F401

        await db.execute(text(
            "UPDATE ged_document_kits k SET completion_percentage = round(100.0 * "
            "  (SELECT count(*) FROM ged_kit_documents d WHERE d.kit_id=k.id "
            "   AND d.file_path IS NOT NULL AND d.file_path<>'') "
            "  / nullif(k.total_documents,0), 2), updated_at = now() "
            "WHERE k.total_documents > 0"))
        await db.commit()

        resta = (await db.execute(SQL_SOBRANDO)).rowcount
        print(f"  DEPOIS: {resta} cópia(s) restante(s) · backup em _dedup_backup_20260814")
        print("  ⚠️ `total_documents` NÃO foi mexido: ele é o número de slots que o kit "
              "declara ter, e reduzi-lo mudaria a meta do kit, não a duplicata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
