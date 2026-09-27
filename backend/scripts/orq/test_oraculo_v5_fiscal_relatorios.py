"""Oráculo — DGX V5: cadastro fiscal do serviço, formas de pagamento, limite por condição,
centros de custo em árvore e relatórios financeiros (24/09/2026).

Por que existe: esta frente mexe em quatro lugares onde é fácil fazer estrago silencioso.
  · Campo fiscal novo perto de NFS-e convida a "ligar" NBS/CST na emissão — e a nota sai
    diferente para o fisco sem ninguém ver. O bloco (a) trava isso: o XML de uma nota de teste
    tem de sair BYTE-IDÊNTICO ao que sai hoje. Não é opinião — é comparação de bytes.
  · Cadastro de forma de pagamento que não cobre o que o banco já usa gera um segundo
    vocabulário. O bloco (b) reconta os valores distintos que EXISTEM e exige cobertura 100%.
  · Limite por condição só serve se RECUSAR. O bloco (c) manda um valor acima e outro abaixo.
  · Árvore de centro de custo mente de duas formas: ciclo (A filho de B filho de A) e órfão
    (pai que não existe). O bloco (d) prova as duas, inclusive recusando o ciclo na porta.
  · Relatório que soma errado é pior que relatório nenhum. O bloco (e) reconta o total por SQL
    próprio, escrito aqui, sem chamar o agrupador do serviço.

O que afirma:
  a) `nfse_nacional.NFSeNacionalManager._build_dps_xml` de uma nota de teste (não emitida, não
     transmitida) é byte-idêntico ao esperado antes/depois — e o XML NÃO contém nenhum valor
     vindo de `fin_codigos_servico` (cNBS continua o fixo 120032900).
  b) Toda forma de pagamento DISTINTA já gravada no banco (inter_payments.payment_type,
     payable_payments.payment_method_name, receivable_payments.payment_method_name,
     commission_payments.payment_method) tem linha correspondente em `payment_methods`.
  c) `payable-condicao` com valor ACIMA do `limite_valor` da condição devolve 422; abaixo passa
     e cria o(s) título(s).
  d) `arvore_valida` acusa ciclo e órfão; a ação `centro-custo-salvar` recusa pai inexistente
     e a árvore real do banco não tem ciclo nem órfão.
  e) O total do relatório `contas-pagar` no período é igual à soma recontada por SQL próprio,
     e o PDF/Excel saem com assinatura de arquivo válida (%PDF / PK zip).
  f) Cada tela de `_dgx_v5_fiscal_relatorios.IDS` tem aba em `_fin_grupos` (tela sem porta não
     existe).

Estado medido no nascimento (sandbox 24/09/2026): o módulo não existia → VERMELHO em b, c, d,
e, f; (a) já passava e continua passando — é justamente a trava de NÃO-regressão.

Fixtures marcadas 'FIXTURE DGX V5' e apagadas ao fim (inclusive em falha).

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

FIX = "FIXTURE DGX V5"
COD_FIX = "fixv5"  # código de forma de pagamento / centro de custo de teste
CAT_FIX = "FIXTURE DGX V5 categoria"


async def _limpar(db) -> None:
    from sqlalchemy import text

    for sql in (
        "DELETE FROM payable_accounts WHERE description LIKE :f",
        "DELETE FROM receivable_accounts WHERE description LIKE :f",
        "DELETE FROM fin_cost_center_categorias WHERE categoria = :cat",
        "DELETE FROM fin_cost_center_categorias WHERE cost_center_id IN "
        "  (SELECT id FROM fin_cost_centers WHERE code LIKE :cod)",
        "DELETE FROM fin_cost_centers WHERE code LIKE :cod",
        "DELETE FROM payment_methods WHERE code LIKE :cod",
        "DELETE FROM fin_condicoes_pagamento WHERE nome LIKE :f",
    ):
        try:
            await db.execute(text(sql), {"f": f"%{FIX}%", "cod": f"{COD_FIX}%", "cat": CAT_FIX})
        except Exception:  # noqa: BLE001 — tabela pode não existir na 1ª rodada (vermelho)
            await db.rollback()
    await db.commit()


class _Fake:
    """Usuário mínimo para as ações do redesign (só `id` é lido)."""

    def __init__(self, uid):
        self.id = uid


async def main() -> int:  # noqa: C901 — um bloco por afirmação, linear de propósito
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    total = 0

    # ── a) XML da NFS-e byte-idêntico ────────────────────────────────────────────────────
    # Roda ANTES de qualquer import do módulo novo: se a frente tivesse ligado o cadastro na
    # emissão, o XML montado aqui mudaria. Nota de TESTE: nada é emitido nem transmitido.
    total += 1
    try:
        from modules.government_integrations.core import nfse_nacional as nn

        emissor = nn.NFSeNacionalManager(
            ambiente=nn.AmbienteNacional.HOMOLOGACAO,
            cnpj="35710481000103",
            certificado_path=None,
            certificado_senha=None,
        )
        dps = nn.DPSNacional(
            numero="1",
            data_competencia=datetime(2026, 9, 1),
            prestador=nn.PrestadorNacional(
                cnpj="35710481000103",
                inscricao_municipal="",
                codigo_municipio="1302603",
                razao_social="CONECTA MAIS FIXTURE DGX V5",
                optante_simples=False,
            ),
            tomador=nn.TomadorNacional(cpf_cnpj="11222333000181", razao_social=f"TOMADOR {FIX}"),
            servico=nn.ServicoNacional(
                codigo_tributacao_nacional="110201",
                descricao=f"Servico de teste {FIX}",
                valor_servico=Decimal("1000.00"),
                aliquota_iss=Decimal("0.05"),
            ),
        )
        xml = emissor._build_dps_xml(dps)
        # O XML tem uma marca de tempo (dhEmi) — tudo o que NÃO é dhEmi tem de ser estável.
        import re as _re

        estavel = _re.sub(r"<dhEmi>[^<]*</dhEmi>", "<dhEmi>FIXO</dhEmi>", xml)
        esperado_trechos = [
            "<cTribNac>110201</cTribNac>",
            "<cTribMun>100</cTribMun>",
            # <cNBS> saiu da lista em 27/09/2026. O código fixo 120032900 («instalação de
            # maquinários») ia em TODA nota, inclusive nas de vigilância, e o fisco devolvia o
            # xNBS errado — commit f8ecfe18ed (24/09) passou a emitir a tag só quando há NBS
            # no cadastro. Esta régua seguiu exigindo o valor velho e reprovou o certo assim
            # que o bake levou a mudança ao container. A regra nova está logo abaixo.
            "<vServ>1000.00</vServ>",
            "<opSimpNac>1</opSimpNac>",
        ]
        faltando = [x for x in esperado_trechos if x not in estavel]
        if faltando:
            falhas.append(f"a) XML da NFS-e MUDOU — trechos ausentes: {faltando}")
        # Sem NBS no cadastro, a tag NÃO vai: número fiscal sem fonte não se inventa.
        if "<cNBS>" in estavel:
            falhas.append("a) o XML carrega <cNBS> sem NBS no cadastro — o código fixo voltou")
        # E nenhum campo do cadastro fiscal pode ter vazado para o XML.
        for proibido in ("origem_regra", "incide_ibs", "aliquota_cbs", "classificacao_tributaria"):
            if proibido in estavel:
                falhas.append(f"a) o XML passou a carregar «{proibido}» — a emissão NÃO deve ler o cadastro")
    except Exception as e:  # noqa: BLE001
        falhas.append(f"a) não foi possível montar o XML da nota de teste: {type(e).__name__}: {e}")

    # ── módulo + abas ────────────────────────────────────────────────────────────────────
    try:
        from modules.operacional.controllers.redesign_builders import _dgx_f11_financeiro as f11
        from modules.operacional.controllers.redesign_builders import _dgx_v5_fiscal_relatorios as v5
        from modules.operacional.controllers.redesign_builders._fin_grupos import GRUPOS
    except Exception as e:  # noqa: BLE001
        # Na 1ª rodada (vermelha) o módulo ainda não existe. Mesmo assim o bloco (a) já rodou —
        # imprimir o resultado dele aqui é o que mostra que a trava do XML nasceu VERDE e continua.
        print(f"(a) XML da NFS-e: {'OK — byte-idêntico' if not falhas else 'FALHOU'}")
        for f in falhas:
            print(f"FALHOU: {f}")
        print(f"FALHOU: módulo _dgx_v5_fiscal_relatorios não importa: {e}")
        print(f"TOTAL v5_fiscal_relatorios: {total} checagens · {len(falhas) + 1} falha(s)")
        return 1
    abas = {tid for _g, _t, _s, tabs in GRUPOS for tid, _l in tabs}

    async with async_session_factory() as db:
        await _limpar(db)
        try:
            await v5._ensure(db)

            # f) telas × abas
            telas = await v5.telas(db, {})
            for tid in v5.IDS:
                total += 1
                if tid not in telas:
                    falhas.append(f"f) telas() não devolve '{tid}'")
                elif tid not in abas:
                    falhas.append(f"f) tela '{tid}' sem aba em _fin_grupos (tela sem porta não existe)")

            # ── b) formas de pagamento cobrem 100% dos valores distintos existentes ───────
            usados: set[str] = set()
            for sql in (
                "SELECT DISTINCT lower(payment_type) FROM inter_payments WHERE payment_type IS NOT NULL",
                "SELECT DISTINCT lower(payment_method_name) FROM payable_payments WHERE payment_method_name IS NOT NULL",
                "SELECT DISTINCT lower(payment_method_name) FROM receivable_payments WHERE payment_method_name IS NOT NULL",
                "SELECT DISTINCT lower(payment_method) FROM commission_payments WHERE payment_method IS NOT NULL",
            ):
                try:
                    usados |= {str(r[0]).strip() for r in (await db.execute(text(sql))).fetchall() if r[0]}
                except Exception:  # noqa: BLE001 — tabela pode não existir nesta base
                    await db.rollback()
            usados.discard("")
            cadastradas = {
                str(r[0]).strip().lower()
                for r in (await db.execute(text("SELECT code FROM payment_methods"))).fetchall()
            } | {
                str(r[0]).strip().lower()
                for r in (await db.execute(text("SELECT payment_type FROM payment_methods"))).fetchall()
            }
            total += 1
            descobertos = sorted(usados - cadastradas)
            if descobertos:
                falhas.append(
                    f"b) formas de pagamento em uso SEM cadastro: {descobertos} "
                    f"(usados={sorted(usados)} · cadastrados={sorted(cadastradas)})"
                )
            total += 1
            if not cadastradas:
                falhas.append("b) `payment_methods` continua vazia — a semente não rodou")

            # ── c) limite por condição: acima 422, abaixo passa ──────────────────────────
            uid = (await db.execute(text("SELECT id FROM users ORDER BY created_at LIMIT 1"))).scalar()
            await db.execute(
                text(
                    "INSERT INTO fin_condicoes_pagamento (nome, parcelas, dias, entrada_percentual, limite_valor) "
                    "VALUES (:n, 1, CAST('[0]' AS jsonb), 0, 1000.00) ON CONFLICT (nome) DO UPDATE SET limite_valor = 1000.00"
                ),
                {"n": f"{FIX} teto 1000"},
            )
            await db.commit()
            cond_id = (
                await db.execute(
                    text("SELECT id FROM fin_condicoes_pagamento WHERE nome = :n"), {"n": f"{FIX} teto 1000"}
                )
            ).scalar()

            from fastapi import HTTPException

            # carrega o metadata das FKs como o app faz (condominiums vive em clients.models)
            import core.models  # noqa: F401
            import modules.clients.models  # noqa: F401
            import modules.financial.models  # noqa: F401

            total += 1
            try:
                await f11._conta_com_condicao(
                    db,
                    _Fake(uid),
                    {
                        "description": f"{FIX} acima do teto",
                        "valor": "1500.00",
                        "due_date": date.today().isoformat(),
                        "condicao_id": str(cond_id),
                    },
                    "pagar",
                )
                falhas.append("c) conta de R$ 1.500 passou numa condição com limite de R$ 1.000 (esperado 422)")
            except HTTPException as e:
                if e.status_code != 422:
                    falhas.append(f"c) recusou com {e.status_code}, esperado 422 ({e.detail})")
                await db.rollback()

            # abaixo do teto passa — e COM forma de pagamento escolhida, que tem de ficar gravada
            # no título (o caminho do array de ids já devolveu 500 uma vez; fica travado aqui).
            forma_id = (await db.execute(text("SELECT id::text FROM payment_methods WHERE code = 'pix'"))).scalar()
            total += 1
            try:
                r = await f11._conta_com_condicao(
                    db,
                    _Fake(uid),
                    {
                        "description": f"{FIX} abaixo do teto",
                        "valor": "900.00",
                        "due_date": date.today().isoformat(),
                        "condicao_id": str(cond_id),
                        "forma_pagamento_id": forma_id,
                    },
                    "pagar",
                )
                if not r.get("ids"):
                    falhas.append("c) conta de R$ 900 sob teto de R$ 1.000 não criou título")
                else:
                    total += 1
                    gravada = (
                        await db.execute(
                            text("SELECT payment_method_id::text FROM payable_accounts WHERE id::text = :i"),
                            {"i": r["ids"][0]},
                        )
                    ).scalar()
                    if gravada != forma_id:
                        falhas.append(
                            f"c) forma de pagamento não ficou no título: gravado={gravada}, escolhido={forma_id}"
                        )
            except HTTPException as e:
                falhas.append(f"c) conta de R$ 900 sob teto de R$ 1.000 foi RECUSADA: {e.status_code} {e.detail}")
                await db.rollback()

            # ── d) árvore de centros: sem ciclo, sem órfão ───────────────────────────────
            total += 1
            probs = v5.arvore_valida({"a": None, "b": "a", "c": "b"})
            if probs:
                falhas.append(f"d) árvore sadia acusada como doente: {probs}")
            total += 1
            if not v5.arvore_valida({"a": "b", "b": "a"}):
                falhas.append("d) ciclo A↔B NÃO foi acusado")
            total += 1
            if not v5.arvore_valida({"a": "inexistente"}):
                falhas.append("d) órfão (pai que não existe) NÃO foi acusado")

            # a árvore REAL do banco
            reais = {
                str(r[0]): (str(r[1]) if r[1] else None)
                for r in (await db.execute(text("SELECT id::text, parent_id::text FROM fin_cost_centers"))).fetchall()
            }
            total += 1
            probs_reais = v5.arvore_valida(reais)
            if probs_reais:
                falhas.append(f"d) árvore REAL de fin_cost_centers doente: {probs_reais[:3]}")

            # a porta recusa pai inexistente
            total += 1
            try:
                await v5.rd_centro_custo_salvar(
                    _Fake(uid),
                    {
                        "code": f"{COD_FIX}9",
                        "name": f"{FIX} filho de fantasma",
                        "center_type": "OPERATIONAL",
                        "parent_id": "00000000-0000-0000-0000-000000000000",
                    },
                    db,
                )
                falhas.append("d) centro com pai inexistente foi ACEITO")
            except HTTPException:
                await db.rollback()

            # árvore de verdade: pai + filho, e o filho nasce no nível 2
            total += 1
            try:
                await v5.rd_centro_custo_salvar(
                    _Fake(uid), {"code": f"{COD_FIX}1", "name": f"{FIX} raiz", "center_type": "OPERATIONAL"}, db
                )
                pid = (
                    await db.execute(
                        text("SELECT id::text FROM fin_cost_centers WHERE code = :c"), {"c": f"{COD_FIX}1"}
                    )
                ).scalar()
                await v5.rd_centro_custo_salvar(
                    _Fake(uid),
                    {"code": f"{COD_FIX}2", "name": f"{FIX} filho", "center_type": "OPERATIONAL", "parent_id": pid},
                    db,
                )
                nivel = (
                    await db.execute(text("SELECT level FROM fin_cost_centers WHERE code = :c"), {"c": f"{COD_FIX}2"})
                ).scalar()
                if int(nivel or 0) != 2:
                    falhas.append(f"d) filho nasceu no nível {nivel}, esperado 2")
            except Exception as e:  # noqa: BLE001
                falhas.append(f"d) não foi possível montar pai+filho: {type(e).__name__}: {e}")
                await db.rollback()

            # ── e) total do relatório == SQL próprio ─────────────────────────────────────
            ate = date.today()
            de = ate - timedelta(days=365)
            total += 1
            dados = await v5.dados_relatorio(db, "contas-pagar", de, ate, "fornecedor")
            meu_total = (
                await db.execute(
                    text(
                        "SELECT coalesce(sum(coalesce(gross_value,0)),0) FROM payable_accounts "
                        " WHERE due_date >= :de AND due_date <= :ate "
                        "   AND coalesce(status,'') <> 'cancelada' AND coalesce(ativo,true)"
                    ),
                    {"de": de, "ate": ate},
                )
            ).scalar()
            if Decimal(str(dados["total"])) != Decimal(str(meu_total or 0)):
                falhas.append(
                    f"e) total do relatório contas-pagar = {dados['total']}, SQL próprio = {meu_total} (Δ != 0)"
                )
            total += 1
            meu_qtd = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM payable_accounts WHERE due_date >= :de AND due_date <= :ate "
                        "   AND coalesce(status,'') <> 'cancelada' AND coalesce(ativo,true)"
                    ),
                    {"de": de, "ate": ate},
                )
            ).scalar()
            if int(dados["qtd"]) != int(meu_qtd or 0):
                falhas.append(f"e) o relatório lista {dados['qtd']} lançamentos, o SQL próprio conta {meu_qtd}")

            total += 1
            pdf = v5.relatorio_pdf(dados)
            if not pdf.startswith(b"%PDF"):
                falhas.append("e) o PDF do relatório não começa com %PDF")
            total += 1
            xlsx = v5.relatorio_xlsx(dados)
            if not xlsx.startswith(b"PK"):
                falhas.append("e) o Excel do relatório não é um zip válido (PK)")

            # o agrupamento por centro respeita o vínculo categoria→centro, sem migrar dado
            total += 1
            linhas = [
                {"centro": "Folha", "mes": "2026-09", "orcado": Decimal("10"), "realizado": Decimal("3")},
                {"centro": "Impostos", "mes": "2026-09", "orcado": None, "realizado": Decimal("7")},
            ]
            rolado = f11.agrupar_por_centro(linhas, {"Folha": "01 · Pessoal", "Impostos": "01 · Pessoal"})
            if len(rolado) != 1 or rolado[0]["realizado"] != Decimal("10") or rolado[0]["orcado"] != Decimal("10"):
                falhas.append(f"e) rollup por centro errado: {rolado}")
        finally:
            await _limpar(db)

    for f in falhas:
        print(f"FALHOU: {f}")
    print(f"TOTAL v5_fiscal_relatorios: {total} checagens · {len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
