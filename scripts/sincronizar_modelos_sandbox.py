#!/usr/bin/env python3
"""Copia os MODELOS de contrato de produção para o sandbox.

Auditoria do Cowork, 11/09/2026 (§3.2): o sandbox tinha 2 modelos (`ferias`, `admissao`) e
produção tinha 6. Nenhum comercial. O fluxo *criar → vincular modelo → emitir → conferir*
não podia ser ensaiado lá — que é exatamente o caso de uso que justifica o sandbox existir.
O `criar_contrato_por_modelo` parava em `sem_modelo` e o auditor não conseguiu completar o
passo 8.

⭐ Copia SÓ a fôrma, nunca o negócio. Modelo é texto jurídico e vocabulário — não tem dado
de cliente, valor nem assinatura. Copiar contrato, proposta ou cliente para o sandbox seria
levar dado real de gente real para um ambiente que existe para ser sujo à vontade.

⚠️ IDEMPOTENTE por `service_type`: o mesmo tipo é ATUALIZADO, não duplicado. Dois modelos
ativos do mesmo tipo fariam `criar_contrato` escolher por `ORDER BY version DESC` — e a
escolha silenciosa entre duas fôrmas é como um contrato sai com a cláusula errada.

    python3 scripts/sincronizar_modelos_sandbox.py          # mostra o que faria
    python3 scripts/sincronizar_modelos_sandbox.py --aplicar
"""
from __future__ import annotations

import json
import subprocess
import sys

PROD = ("conecta-pro-postgres", "conecta_pro")
SANDBOX = ("conecta-pro-postgres-staging", "conecta_pro_staging")
COLUNAS = ("name", "description", "service_type", "content_template", "clauses",
           "variables", "version", "approved_by_legal", "is_active")


def _psql(alvo: tuple[str, str], sql: str) -> str:
    container, db = alvo
    r = subprocess.run(  # noqa: S603
        ["docker", "exec", container, "psql", "-U", "postgres", "-d", db, "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"psql em {db}: {r.stderr.strip()[:200]}")
    return r.stdout


def _ler_producao() -> list[dict]:
    linha = _psql(PROD, (
        "SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM ("
        "  SELECT " + ", ".join(COLUNAS) + " FROM contract_templates"
        "   WHERE coalesce(is_active, true) ORDER BY service_type) t"))
    return json.loads(linha.strip() or "[]")


def main() -> int:
    aplicar = "--aplicar" in sys.argv
    try:
        modelos = _ler_producao()
        no_sandbox = {ln.strip() for ln in _psql(
            SANDBOX, "SELECT service_type FROM contract_templates WHERE coalesce(is_active,true);"
        ).splitlines() if ln.strip()}
    except Exception as e:  # noqa: BLE001
        print(f"  NÃO VERIFICADO: {e}")
        return 0

    faltando = [m for m in modelos if m["service_type"] not in no_sandbox]
    print(f"  produção: {len(modelos)} modelos · sandbox: {len(no_sandbox)} · "
          f"faltando: {len(faltando)}")
    for m in modelos:
        estado = "NOVO" if m["service_type"] in {x["service_type"] for x in faltando} else "atualiza"
        print(f"    {estado:8} {m['service_type']:26} {len(m['content_template'] or '')} chars")

    if not aplicar:
        print("\n  (ensaio — nada foi gravado; use --aplicar)")
        return 0

    for m in modelos:
        # `ON CONFLICT` exigiria índice único em service_type, que não existe. DELETE do
        # tipo + INSERT é o mesmo efeito e não depende de um índice que eu não controlo.
        _psql(SANDBOX, "DELETE FROM contract_templates WHERE service_type = "
                       f"{_lit(m['service_type'])};")
        campos = ", ".join(COLUNAS)
        valores = ", ".join(_lit(m[c], c) for c in COLUNAS)
        _psql(SANDBOX, f"INSERT INTO contract_templates (id, {campos}, created_at, updated_at) "
                       f"VALUES (gen_random_uuid(), {valores}, now(), now());")

    # prova por LEITURA POSTERIOR, nunca pela linha do INSERT
    depois = {ln.strip() for ln in _psql(
        SANDBOX, "SELECT service_type FROM contract_templates WHERE coalesce(is_active,true);"
    ).splitlines() if ln.strip()}
    esperados = {m["service_type"] for m in modelos}
    if not esperados.issubset(depois):
        print(f"  ❌ faltaram depois de aplicar: {sorted(esperados - depois)}")
        return 1
    print(f"\n  OK sandbox com {len(depois)} modelos: {', '.join(sorted(depois))}")
    return 0


def _lit(v, coluna: str = "") -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (list, dict)):
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    texto = "'" + str(v).replace("'", "''") + "'"
    return texto


if __name__ == "__main__":
    sys.exit(main())
