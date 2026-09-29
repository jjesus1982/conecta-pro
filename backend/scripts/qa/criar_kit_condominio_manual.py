"""Cria `kit_condominio_manual` — onde a Pyetra grava o condomínio que o dado não sabe.

Rodar UMA VEZ. Idempotente: se a tabela existe, não faz nada e diz isso.

## Por que existe

O roster do kit resolve 60 de 63 pessoas pelo `posto_id` gravado na batida. As que sobram não
têm posto em NENHUMA batida do mês — e para elas a única fonte é um humano. Em 28/09 eu
perguntei ao Jordan por WhatsApp e escrevi a resposta no código
(`RESOLVIDO_PELO_JORDAN`). Isso não escala: a Pyetra não edita Python, e decisão de produção não
mora em constante de script.

## Por que uma tabela nova, e não uma existente

- **`employee_alocacoes`**: é curada à mão pelo Jordan, é READ-ONLY para agentes, e as datas dela
  são ficção (a alocação do RILEM ao GREEN HILLS diz `data_inicio = 2026-01-01` num condomínio
  que abriu em 01/09). Escrever ali contaminaria a fonte que ele cura.
- **`gedeon_kit_config`**: é do Gedeon, e o Jordan pediu para não tocar.
- **`gp_clock_punches.posto_id`**: seria o conserto NA FONTE e é tentador — mas preencher o posto
  de uma batida antiga é afirmar sobre registro trabalhista por dedução de terceiro. Ato desse
  tamanho é do Jordan, não meu.

⭐ DDL **uma vez, por script**, nunca por requisição: em 28/09 um `ALTER TABLE` por requisição
pôs 146 de 150 processos do Postgres em `waiting` e derrubou o banco. `IF NOT EXISTS` é
idempotente no RESULTADO, não no LOCK.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

TABELA = "kit_condominio_manual"

DDL = f"""
CREATE TABLE {TABELA} (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id   uuid NOT NULL,
    competencia   date NOT NULL,
    condominio    text NOT NULL,
    motivo        text,
    definido_por  text NOT NULL,
    definido_em   timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'America/Manaus'),
    CONSTRAINT {TABELA}_unq UNIQUE (employee_id, competencia)
)
"""
#: A busca do roster é sempre (competência) → lista. Índice por competência, não por pessoa.
IDX = f"CREATE INDEX {TABELA}_comp_idx ON {TABELA} (competencia)"


def main() -> None:
    with get_sync_db() as db:
        existe = db.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{TABELA}"}
        ).scalar()
        if existe:
            n = db.execute(text(f"SELECT count(*) FROM {TABELA}")).scalar()  # noqa: S608
            print(f"OK `{TABELA}` já existe ({n} linha(s)) — nada a fazer.")
            return
        db.execute(text(DDL))
        db.execute(text(IDX))
        db.commit()

    # PROVA POR LEITURA POSTERIOR, em conexão nova: `CREATE` que não commitou também "funciona"
    # até alguém olhar de fora.
    with get_sync_db() as db2:
        ok = db2.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{TABELA}"}
        ).scalar()
        cols = [
            r[0]
            for r in db2.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    " WHERE table_name = :t ORDER BY ordinal_position"
                ),
                {"t": TABELA},
            ).all()
        ]
    assert ok, f"`{TABELA}` não existe depois do commit — a criação não se confirmou na leitura"
    print(f"OK `{TABELA}` criada · colunas: {', '.join(cols)}")
    print("OK chave única (employee_id, competencia) — a mesma pessoa não tem dois condomínios no mês")


if __name__ == "__main__":
    main()
