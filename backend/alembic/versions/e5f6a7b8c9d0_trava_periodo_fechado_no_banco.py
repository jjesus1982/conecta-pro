"""trava o periodo fechado no BANCO, nao em cada servico

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-12

O corte de 01/08/2026 era checado em Python, em dois serviços
(`extrato_para_razao` e `ledger_auto_service`). O questionário do T1 perguntou se
havia outro caminho — havia TRÊS, e nenhum checava:

  conciliacao_liquido_service  ← alcançável por BOTÃO (/action/conciliar-liquido)
  estoque_real_service
  accounting_seed_service

Ou seja: a trava tinha três portas por fora, e a que mais fechava era justamente a
que um humano alcança clicando. Remendar serviço por serviço não resolve o
próximo escritor que aparecer — por isso a regra desce para o banco.

Só INSERT. UPDATE segue livre de propósito: corrigir um lançamento errado do
passado é legítimo (foi o que se fez hoje com a transferência entre CNPJs); o que
não pode é lançamento NOVO nascer num período que já foi fechado.

⚠️ A data está aqui E em `periodo_contabil.CORTE_CONTABIL`. Mudar o corte exige
mexer nos dois — a alternativa (ler de uma tabela de config) custaria mais
máquina do que a regra vale hoje, com um corte só.
"""

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_bloqueia_periodo_fechado()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.data_lancamento < DATE '2026-08-01' THEN
                RAISE EXCEPTION
                    'periodo contabil fechado: lancamento em % e anterior ao corte de 01/08/2026 (%, R$ %)',
                    NEW.data_lancamento, coalesce(NEW.documento_ref, '(sem ref)'), NEW.valor
                    USING HINT = 'De janeiro a julho a empresa operou fora do sistema. '
                                 'Lancamento novo no periodo fechado contamina todo relatorio '
                                 'acumulado em silencio. Corrigir lancamento existente (UPDATE) e permitido.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS trg_bloqueia_periodo_fechado ON accounting_entries;
        CREATE TRIGGER trg_bloqueia_periodo_fechado
            BEFORE INSERT ON accounting_entries
            FOR EACH ROW EXECUTE FUNCTION fn_bloqueia_periodo_fechado();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_bloqueia_periodo_fechado ON accounting_entries")
    op.execute("DROP FUNCTION IF EXISTS fn_bloqueia_periodo_fechado()")
