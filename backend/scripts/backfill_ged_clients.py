"""Backfill: espelha em `ged_clients` os clientes ATIVOS do CRM que ainda não têm espelho.

Passada ÚNICA de recuperação. O subscriber `ged/subscribers/espelhar_cliente.py` cuida dos
clientes NOVOS (reage a `gedeon.cliente.espelhar`), mas não olha para trás — quem já estava
ativo antes de 2026-08-07 ficou sem espelho. Medido: 21 ativos no CRM, 12 em ged_clients.

MESMA REGRA DO SUBSCRIBER: casa por nome normalizado (trim + espaço colapsado + minúsculo).
`ged_clients.id` e `clients.id` são UUIDs diferentes e não há coluna de referência cruzada —
o nome é o único vínculo que existe hoje.

EXCLUSÕES DELIBERADAS (não são clientes de documento):
  - CNPJ/documento só de zeros → registro de teste/homologação
  - as próprias empresas do grupo (ver _CNPJ_PROPRIOS)
Criar pasta de cliente para esses seria poluir a base.

Rodar do host:
    cd /opt/conecta-pro && python3 backend/scripts/backfill_ged_clients.py           # dry-run
    cd /opt/conecta-pro && python3 backend/scripts/backfill_ged_clients.py --aplicar
"""

import re
import subprocess
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

#: CNPJs do próprio grupo — aparecem em `clients` para faturamento interno, não são
#: clientes de kit documental.
_CNPJ_PROPRIOS = {"35710481000103", "66014833000110"}

_SQL_FALTANDO = """
SELECT c.name, coalesce(c.document_number,'')
FROM clients c
WHERE c.status = 'active'
  AND NOT EXISTS (
    SELECT 1 FROM ged_clients g
    WHERE lower(regexp_replace(trim(g.name), '\\s+', ' ', 'g'))
        = lower(regexp_replace(trim(c.name), '\\s+', ' ', 'g'))
  )
ORDER BY c.name;
"""


def _psql(sql: str) -> str:
    return subprocess.run(  # noqa: S603 — argv local, sem shell nem entrada externa
        ["/usr/bin/docker", "exec", "conecta-pro-postgres", "psql", "-U", "postgres",
         "-d", "conecta_pro", "-t", "-A", "-F", "|", "-c", sql],
        capture_output=True, text=True, timeout=60,
    ).stdout


def _pular(nome: str, doc: str) -> str | None:
    """Motivo para NÃO espelhar, ou None se deve espelhar."""
    so_digitos = re.sub(r"\D", "", doc or "")
    if so_digitos and set(so_digitos) == {"0"}:
        return "documento só de zeros (teste/homologação)"
    if so_digitos in _CNPJ_PROPRIOS:
        return "empresa do próprio grupo, não é cliente"
    return None


def main() -> None:
    aplicar = "--aplicar" in sys.argv
    linhas = [ln for ln in _psql(_SQL_FALTANDO).splitlines() if ln.strip()]
    if not linhas:
        print("Nenhum cliente ativo sem espelho. Nada a fazer.")
        return

    criar: list[str] = []
    print(f"=== {len(linhas)} cliente(s) ativo(s) sem espelho em ged_clients ===\n")
    for ln in linhas:
        nome, _, doc = ln.partition("|")
        motivo = _pular(nome, doc)
        if motivo:
            print(f"  PULA   {nome:46} → {motivo}")
        else:
            print(f"  CRIA   {nome}")
            criar.append(nome)

    print(f"\na criar: {len(criar)} · a pular: {len(linhas) - len(criar)}")
    if not aplicar:
        print("\n(dry-run — nada foi escrito. Rode com --aplicar para criar.)")
        return

    for nome in criar:
        seguro = nome.replace("'", "''")
        _psql(
            "INSERT INTO ged_clients (id, name, type, is_active, created_at, updated_at) "
            f"VALUES ('{uuid.uuid4()}', '{seguro}', 'condominio', true, now(), now());"
        )
    total = _psql("SELECT count(*) FROM ged_clients;").strip()
    print(f"\n{len(criar)} criado(s). ged_clients agora tem {total} linha(s).")


if __name__ == "__main__":
    main()
