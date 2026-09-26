"""Encerra a competência: receita e despesa viram Patrimônio Líquido.

Sem isto o razão nunca fecha um exercício. Medido em 13/08/2026: **zero
lançamentos no grupo 3.x** — as contas de resultado acumulavam desde janeiro sem
nunca serem encerradas, e 2027 somaria em cima de 2026.

E é o que faz o balanço existir. Hoje a equação até fecha por construção
(Ativo R$27.629,39 − Passivo R$266.894,30 = Resultado −R$239.264,91), mas o PL
é R$0,00: o patrimônio está escondido dentro das contas de resultado, onde
ninguém o lê como patrimônio.

Como funciona, e por que precisa de conta de passagem:
  `accounting_entries` tem UM débito e UM crédito por linha. Para levar N contas
  de resultado ao PL, cada uma vira uma linha contra `3.3.1.01 Apuração do
  Resultado`, e no fim a apuração inteira vai para `3.2.1.01 Lucros ou Prejuízos
  Acumulados`. A conta de passagem volta a ZERO na mesma operação — se sobrar
  saldo nela, a apuração ficou pela metade.

Paredes:
  • idempotente por `documento_ref` = APURACAO-{competência};
  • recusa competência do mês CORRENTE — resultado de mês em curso não é
    resultado, é meio caminho (a receita entra na emissão da NFS-e, entre os dias
    2 e 31, e a folha sai no dia 7: em 12/08 o mês mostrava −R$152 mil e isso é
    artefato de competência, não prejuízo);
  • o período fechado (< corte) é recusado pelo trigger do banco, não aqui —
    a apuração do que veio antes entra como saldo de ABERTURA, na data do corte.
"""

from __future__ import annotations

import logging
from datetime import date

import psycopg2
import psycopg2.extras

from modules.financial.services.ledger_auto_service import _raw_db_url
from modules.financial.services.periodo_contabil import corte_da_empresa

logger = logging.getLogger(__name__)

CONTA_APURACAO = "3.3.1.01"
CONTA_ACUMULADO = "3.2.1.01"


def _conn():
    return psycopg2.connect(_raw_db_url())


def apurar(competencia: str, preview: bool = True, empresa_id: str | None = None) -> dict:
    """Encerra `competencia` (YYYY-MM) de UMA empresa: zera 4.x e 5.x dela contra o PL.

    `competencia` é o mês do RESULTADO. Os lançamentos entram no último dia dele.

    `empresa_id=None` encerra TODAS as empresas, uma a uma, e devolve o agregado em
    `por_empresa` — é o que os chamadores antigos (o beat e o oráculo do balanço) fazem.

    ⚠️ POR EMPRESA DESDE 26/09/2026. Antes a consulta de saldo não filtrava `empresa_id` e
    o `_post` não o gravava: os 277 lançamentos de encerramento existentes somavam as DUAS
    pessoas jurídicas num só, e a ECD de cada CNPJ — que filtra por empresa — saía sem
    nenhum deles. Uma empresa cujo resultado é encerrado junto com o da irmã não tem
    balanço próprio, e era justamente o que a Patrimonial precisava ter para pedir crédito.
    """
    if empresa_id is None:
        return _apurar_todas(competencia, preview)
    hoje = date.today()
    if competencia >= f"{hoje:%Y-%m}":
        return {
            "ok": False,
            "erro": (
                f"competência {competencia} ainda não fechou — resultado de mês em curso é meio caminho, não resultado"
            ),
        }

    ano, mes = int(competencia[:4]), int(competencia[5:7])
    ultimo = date(ano + (mes // 12), (mes % 12) + 1, 1)
    fim = date.fromordinal(ultimo.toordinal() - 1)
    # Antes do corte não se escreve: o trigger do banco recusa, e com razão. O que
    # veio de lá entra como saldo de ABERTURA, na data do corte.
    data = max(fim, corte_da_empresa(empresa_id))

    conn = _conn()
    linhas = []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                -- ⚠️ 18/09/2026 — OS LANÇAMENTOS DE APURAÇÃO ENTRAM NA CONTA.
                -- Antes esta consulta os excluía (`tipo_lancamento <> 'apuracao'`), e por isso
                -- ela enxergava SEMPRE o valor cheio: rodar duas vezes fecharia o mês duas
                -- vezes. A defesa contra isso era a trava por `documento_ref`, e ela criava um
                -- buraco pior: competência apurada que RECEBE LANÇAMENTO RETROATIVO fica com
                -- resíduo aberto PARA SEMPRE, porque a apuração se recusa a rodar de novo.
                --
                -- Foi o que aconteceu com 2026-08: apurada em 07/09, e depois chegaram uma
                -- folha manual de R$ 132.524,09 (07 a 10/09) e notas tomadas até 17/09. Sobrou
                -- R$ 21.175,06 aberto, o balanço acusando todo dia e ninguém conseguindo fechar.
                --
                -- Incluindo a apuração, o saldo vira o RESÍDUO de verdade: conta já encerrada dá
                -- zero e o `HAVING` a descarta sozinha. A idempotência passa a vir de «não
                -- sobrou nada», que é um FATO, e não de «já rodei», que é uma lembrança.
                SELECT conta, coalesce(sum(deb), 0) - coalesce(sum(cred), 0) AS saldo
                FROM (
                    SELECT conta_debito AS conta, valor AS deb, 0 AS cred
                      FROM accounting_entries
                     WHERE periodo_competencia = %s AND empresa_id = %s
                    UNION ALL
                    SELECT conta_credito, 0, valor
                      FROM accounting_entries
                     WHERE periodo_competencia = %s AND empresa_id = %s
                ) x
                WHERE conta LIKE '4%%' OR conta LIKE '5%%'
                GROUP BY conta
                HAVING abs(coalesce(sum(deb), 0) - coalesce(sum(cred), 0)) > 0.005
                ORDER BY conta
                """,
                (competencia, empresa_id, competencia, empresa_id),
            )
            contas = cur.fetchall()
            resultado = 0.0
            for r in contas:
                saldo = float(r["saldo"])
                # despesa tem saldo DEVEDOR (>0) → credita a conta para zerar;
                # receita tem saldo CREDOR (<0) → debita.
                if saldo > 0:
                    cd, cc = CONTA_APURACAO, r["conta"]
                else:
                    cd, cc = r["conta"], CONTA_APURACAO
                linhas.append({"conta": r["conta"], "valor": round(abs(saldo), 2), "debito": cd, "credito": cc})
                resultado -= saldo  # receita positiva, despesa negativa

            resultado = round(resultado, 2)

            # A RODADA. A primeira apuração da competência é a R1; se lançamento retroativo
            # chegar depois e reabrir saldo, a complementar vira R2, R3… Sem isso o
            # `documento_ref` colidiria com o da rodada anterior e o resíduo não fecharia —
            # que é exatamente o defeito de 2026-08. O `WHERE NOT EXISTS` do `_post` segue de
            # pé: ele protege de duplo clique DENTRO da mesma rodada.
            #
            # ⚠️ A RODADA VEM DE TODAS AS REFERÊNCIAS, NÃO SÓ DAS DE RESULTADO.
            #
            # Contar só `...-RESULTADO%` dessincroniza os dois numeradores, e o preço é um
            # lançamento ÓRFÃO. Medido em 26/09/2026, na competência 2026-03:
            #
            #   14:32  rodada 3 fecha 4 contas que SE ANULAM (soma zero) → como
            #          `abs(resultado) <= 0.005`, a linha de RESULTADO **não é postada**.
            #          O número 3 foi gasto pelas contas e não pelo resultado.
            #   17:03  aparece resíduo novo. `rodada` conta RESULTADO (só o R2 existe) e
            #          devolve 3 DE NOVO. A conta `...-5.1.1.07-R3` já existe e o
            #          `WHERE NOT EXISTS` a pula — mas `...-RESULTADO-R3` é inédito e
            #          ENTRA. Resultado lançado sem a contrapartida que o originou.
            #   17:03  a chamada seguinte, com rodada 4, posta os dois — e agora há DUAS
            #          transferências de R$ 2.650,00 para o PL.
            #
            # O saldo de `3.3.1.01` ficou em −R$ 5.456,14 e o oráculo do balanço acusou
            # «a apuração ficou pela metade e o balanço fecha mentindo». Tomando o MAIOR
            # sufixo `-R<n>` de qualquer referência da competência, os dois numeradores
            # voltam a ser um só.
            prefixo = f"APURACAO-{empresa_id[:8]}-{competencia}"
            cur.execute(
                "SELECT documento_ref FROM accounting_entries WHERE documento_ref LIKE %s",
                (f"{prefixo}-%",),
            )
            import re as _re

            usadas = [
                int(m.group(1))
                for r in cur.fetchall()
                for m in [_re.search(r"-R(\d+)$", (r["documento_ref"] if isinstance(r, dict) else r[0]) or "")]
                if m
            ]
            rodada = (max(usadas) if usadas else 0) + 1

            if not preview:
                for ln in linhas:
                    _post(
                        cur,
                        data,
                        ln["debito"],
                        ln["credito"],
                        ln["valor"],
                        f"Apuração {competencia}: encerra {ln['conta']}",
                        f"{prefixo}-{ln['conta']}-R{rodada}",
                        competencia,
                        empresa_id,
                    )
                if abs(resultado) > 0.005:
                    # lucro credita o acumulado; prejuízo debita
                    cd, cc = (CONTA_APURACAO, CONTA_ACUMULADO) if resultado > 0 else (CONTA_ACUMULADO, CONTA_APURACAO)
                    _post(
                        cur,
                        data,
                        cd,
                        cc,
                        abs(resultado),
                        f"Apuração {competencia}: {'lucro' if resultado > 0 else 'prejuízo'} para o PL",
                        f"{prefixo}-RESULTADO-R{rodada}",
                        competencia,
                        empresa_id,
                    )
                conn.commit()
            else:
                conn.rollback()
        return {
            "ok": True,
            "modo": "preview" if preview else "aplicado",
            "competencia": competencia,
            "data_lancamento": str(data),
            "contas_encerradas": len(linhas),
            "resultado": resultado,
            "linhas": linhas,
            "empresa_id": empresa_id,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _apurar_todas(competencia: str, preview: bool) -> dict:
    """Encerra a competência de cada empresa, uma a uma, e agrega."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id::text FROM empresas ORDER BY razao_social")
            ids = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    por_empresa = {eid: apurar(competencia, preview, eid) for eid in ids}
    erros = [r["erro"] for r in por_empresa.values() if not r.get("ok")]
    return {
        "ok": not erros,
        "erro": erros[0] if erros else None,
        "modo": "preview" if preview else "aplicado",
        "competencia": competencia,
        "contas_encerradas": sum(r.get("contas_encerradas", 0) for r in por_empresa.values()),
        "resultado": round(sum(r.get("resultado", 0) or 0 for r in por_empresa.values()), 2),
        "linhas": [ln for r in por_empresa.values() for ln in r.get("linhas", [])],
        "por_empresa": por_empresa,
    }


def _post(cur, data, cd, cc, valor, hist, ref, competencia, empresa_id) -> None:
    cur.execute(
        """
        INSERT INTO accounting_entries
            (data_lancamento, conta_debito, conta_credito, valor, historico,
             tipo_lancamento, documento_ref, periodo_competencia, status, empresa_id)
        SELECT %s, %s, %s, %s, %s, 'apuracao', %s, %s, 'confirmado', %s
        WHERE NOT EXISTS (SELECT 1 FROM accounting_entries WHERE documento_ref = %s)
        """,
        (data, cd, cc, float(valor), hist[:250], ref, competencia, empresa_id, ref),
    )


def saldo_da_apuracao() -> float:
    """Saldo da conta de passagem. Tem que ser ZERO — se sobrou, a apuração
    ficou pela metade e o balanço mente."""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT coalesce(sum(CASE WHEN conta_debito = %s THEN valor ELSE -valor END), 0) "
                "FROM accounting_entries WHERE conta_debito = %s OR conta_credito = %s",
                (CONTA_APURACAO, CONTA_APURACAO, CONTA_APURACAO),
            )
            return round(float(cur.fetchone()[0] or 0), 2)
    finally:
        conn.close()
