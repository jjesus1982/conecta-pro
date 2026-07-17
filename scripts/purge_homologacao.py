"""Purga TODA a base de homologação (testadores + ponto + turnos + logins).

Uso (dentro do container backend):
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/../scripts/purge_homologacao.py
ou copie para /tmp e rode. Idempotente. NÃO toca em nada com is_homologacao=false.

Remove, na ordem das FKs:
  - gp_clock_punches dos employees is_homologacao
  - shifts dos employees is_homologacao
  - communication_notifications dos users de homologação
  - users vinculados aos employees is_homologacao
  - employees is_homologacao
Mantém o cliente HOMOLOG, o posto Conecta Base e a escala (reutilizáveis).
Passe --tudo para remover também posto/cliente/escala.
"""

import sys

from sqlalchemy import text

from core.database.session import SyncSessionLocal


def purge(tudo: bool = False) -> None:
    s = SyncSessionLocal()
    try:
        emps = [r[0] for r in s.execute(
            text("SELECT id::text FROM employees WHERE is_homologacao = true")
        ).fetchall()]
        print(f"Testadores de homologação: {len(emps)}")
        if emps:
            n_p = s.execute(text(
                "DELETE FROM gp_clock_punches WHERE employee_id IN "
                "(SELECT id FROM employees WHERE is_homologacao = true)"
            )).rowcount
            n_s = s.execute(text(
                "DELETE FROM shifts WHERE employee_id IN "
                "(SELECT id FROM employees WHERE is_homologacao = true)"
            )).rowcount
            # notificações e logins dos users vinculados
            n_n = s.execute(text(
                "DELETE FROM communication_notifications WHERE user_id IN "
                "(SELECT id FROM users WHERE employee_id IN "
                " (SELECT id FROM employees WHERE is_homologacao = true))"
            )).rowcount
            n_u = s.execute(text(
                "DELETE FROM users WHERE employee_id IN "
                "(SELECT id FROM employees WHERE is_homologacao = true)"
            )).rowcount
            n_e = s.execute(text("DELETE FROM employees WHERE is_homologacao = true")).rowcount
            print(f"  batidas={n_p} turnos={n_s} notificacoes={n_n} logins={n_u} employees={n_e}")
        if tudo:
            s.execute(text("DELETE FROM scales WHERE post_id = (SELECT id FROM posts WHERE code='CONECTA-BASE')"))
            s.execute(text("DELETE FROM posts WHERE code='CONECTA-BASE'"))
            s.execute(text("DELETE FROM clients WHERE code='HOMOLOG'"))
            print("  posto/cliente/escala Conecta Base removidos (--tudo)")
        s.commit()
        print("Purga concluída.")
    finally:
        s.close()


if __name__ == "__main__":
    purge(tudo="--tudo" in sys.argv)
