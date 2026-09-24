"""Oráculo — frota operacional (DGX F10, 24/09/2026): saída/retorno, multa com desconto em folha,
trocas tipadas e requisição de abastecimento.

Por que existe: a frente 10 deixou a frota com KM, abastecimento e vistoria — e a decisão de NÃO
apontar condutor de multa sem posse datada. A F10 do DGX cria a posse datada (`frota_saidas`) e,
com ela, a multa pode sugerir o condutor. Cada uma dessas peças tem uma regra que, quebrada,
vira dinheiro errado (multa descontada de quem não dirigia, título sem leitura) ou dado
impossível (carro que saiu duas vezes sem voltar, hodômetro que anda para trás).

O que afirma (re-derivado por SQL próprio, não pelo serviço):
  a) nenhum veículo tem duas saídas abertas — e o BANCO impede (índice único parcial);
  b) retorno com km < saída é recusado pelo banco (CHECK), provado num savepoint que é desfeito;
  c) toda multa com `desconto_folha` aponta para um `employee_deductions` do MESMO condutor;
  d) o `Restam` da tela `frota-trocas` == (próxima KM da última troca do tipo) − (KM atual nos
     últimos PERIODO_KM_DIAS dias), recomputado aqui; sem KM recente → "sem dado";
  e) toda requisição de abastecimento `realizada` tem exatamente UMA leitura de abastecimento
     ligada, e nenhuma leitura serve a duas requisições.

Estado medido no nascimento (sandbox, 24/09/2026 00:40): `frota_veiculos`, `frota_leituras`,
`frota_vistorias` existem com 0 linhas; `frota_saidas`, `frota_multas`, `frota_locacoes`,
`frota_requisicoes` não existem; `frota_leituras.tipo` só aceita km|abastecimento. VERMELHO por
ausência do mecanismo.

Como roda (container efêmero contra o sandbox, ver docs/dgx/CONTRATO_AGENTE.md):
  docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
    --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest \
    python3 /app/scripts/orq/test_oraculo_frota_operacional.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL frota_operacional: N`.
"""

from __future__ import annotations

import asyncio
import re
import sys

_NUM = re.compile(r"-?[\d.]+")


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    try:
        from modules.operacional.controllers.redesign_builders import _dgx_f10_frotas as f10
        from modules.operacional.controllers.redesign_builders._frente_10 import PERIODO_KM_DIAS
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: builder _dgx_f10_frotas não importa: {e}")
        print("TOTAL frota_operacional: 1")
        return 1

    async with async_session_factory() as db:
        await f10._ensure(db)  # o mesmo DDL idempotente que o 1º acesso à tela aplica
        for tb in ("frota_saidas", "frota_multas", "frota_locacoes", "frota_requisicoes"):
            if not (await db.execute(text(f"SELECT to_regclass('public.{tb}')"))).scalar():
                falhas.append(f"tabela {tb} não existe")
        if falhas:
            for f in falhas:
                print("FALHOU:", f)
            print(f"TOTAL frota_operacional: {len(falhas)}")
            return 1

        # a) saída aberta é única por veículo — no dado e no mecanismo
        dup = (
            await db.execute(
                text(
                    "SELECT veiculo_id, count(*) FROM frota_saidas WHERE data_retorno IS NULL GROUP BY 1 HAVING count(*) > 1"
                )
            )
        ).fetchall()
        for v, n in dup:
            falhas.append(f"(a) veículo #{v} com {n} saídas abertas")
        if not (
            await db.execute(
                text(
                    "SELECT 1 FROM pg_indexes WHERE tablename = 'frota_saidas' AND indexdef ILIKE '%UNIQUE%' AND indexdef ILIKE '%data_retorno IS NULL%'"
                )
            )
        ).first():
            falhas.append("(a) sem índice único parcial em frota_saidas (veiculo_id) WHERE data_retorno IS NULL")

        # b) km_retorno < km_saida é recusado pelo banco (savepoint desfeito; nada fica)
        try:
            async with db.begin_nested():
                vid = (
                    await db.execute(
                        text("INSERT INTO frota_veiculos (placa, modelo) VALUES ('ORQ0O00', 'ORACULO') RETURNING id")
                    )
                ).scalar()
                await db.execute(
                    text(
                        "INSERT INTO frota_saidas (veiculo_id, motorista_employee_id, km_saida, km_retorno, data_retorno) "
                        "VALUES (:v, gen_random_uuid(), 1000, 999, now())"
                    ),
                    {"v": vid},
                )
            falhas.append("(b) banco aceitou retorno com km 999 < saída 1000")
        except Exception:  # noqa: BLE001 — esperado: CHECK recusa
            pass
        await db.rollback()

        # c) multa descontada em folha tem desconto do MESMO condutor
        ruins = (
            await db.execute(
                text(
                    "SELECT m.id FROM frota_multas m WHERE m.desconto_folha AND NOT EXISTS ("
                    "SELECT 1 FROM employee_deductions d WHERE d.id = m.deduction_id AND d.employee_id = m.condutor_employee_id)"
                )
            )
        ).fetchall()
        for (mid,) in ruins:
            falhas.append(f"(c) multa #{mid} marcada desconto_folha sem employee_deductions do condutor")
        n_multas_folha = (await db.execute(text("SELECT count(*) FROM frota_multas WHERE desconto_folha"))).scalar()

        # d) Restam da tela == recomputado
        esperado: dict[tuple[str, str], str] = {}
        rows = (
            await db.execute(
                text(
                    "SELECT v.placa, l.tipo, l.proxima_km, "
                    f"(SELECT max(km) FROM frota_leituras k WHERE k.veiculo_id = v.id AND k.lida_em > now() - interval '{PERIODO_KM_DIAS} days') "
                    "FROM frota_veiculos v JOIN LATERAL (SELECT DISTINCT ON (tipo) tipo, proxima_km FROM frota_leituras "
                    "WHERE veiculo_id = v.id AND tipo LIKE 'troca_%' ORDER BY tipo, lida_em DESC, id DESC) l ON true WHERE v.ativo"
                )
            )
        ).fetchall()
        for placa, tipo, prox, km_atual in rows:
            if km_atual is None:
                esperado[(placa, tipo)] = "sem dado"
            elif prox is None:
                esperado[(placa, tipo)] = "—"
            else:
                esperado[(placa, tipo)] = str(prox - km_atual)
        telas = await f10.telas(db, {})
        scr = telas.get("frota-trocas")
        if not scr:
            falhas.append("(d) telas() não devolve 'frota-trocas'")
        else:
            visto: dict[tuple[str, str], str] = {}
            for r in scr.get("rows") or []:
                c = r["cells"]
                placa, tipo_lbl, restam = c[0]["v"], c[1]["v"], c[5]["v"]
                tipo = {lab: k for k, lab, _ in f10.TROCAS}[tipo_lbl]
                m = _NUM.search(restam.replace(".", ""))
                visto[(placa, tipo)] = m.group(0) if m else restam
            if visto != esperado:
                falhas.append(f"(d) Restam da tela {visto} ≠ recomputado {esperado}")

        # e) requisição de abastecimento realizada ↔ exatamente uma leitura de abastecimento
        req = (
            await db.execute(
                text(
                    "SELECT r.id, r.leitura_id, l.tipo, (SELECT count(*) FROM frota_requisicoes x WHERE x.leitura_id = r.leitura_id) "
                    "FROM frota_requisicoes r LEFT JOIN frota_leituras l ON l.id = r.leitura_id "
                    "WHERE r.tipo = 'abastecimento' AND r.status = 'realizada'"
                )
            )
        ).fetchall()
        for rid, lid, ltipo, n in req:
            if lid is None or ltipo != "abastecimento":
                falhas.append(
                    f"(e) requisição #{rid} realizada sem leitura de abastecimento (leitura {lid}, tipo {ltipo})"
                )
            elif n != 1:
                falhas.append(f"(e) leitura #{lid} serve a {n} requisições")
        n_pend = (
            await db.execute(
                text(
                    "SELECT count(*) FROM frota_requisicoes WHERE tipo = 'abastecimento' AND status <> 'realizada' AND leitura_id IS NOT NULL"
                )
            )
        ).scalar()
        if n_pend:
            falhas.append(f"(e) {n_pend} requisição(ões) não realizadas com leitura ligada")

        saidas = (
            await db.execute(text("SELECT count(*), count(*) FILTER (WHERE data_retorno IS NULL) FROM frota_saidas"))
        ).first()
        print(
            f"saídas: {saidas[0]} (abertas {saidas[1]}) · multas em folha: {n_multas_folha} · "
            f"trocas conferidas: {len(esperado)} · requisições realizadas: {len(req)}"
        )

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL frota_operacional: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na frota operacional")
    print(
        "OK frota_operacional: saída única, hodômetro não recua, multa desconta do condutor, Restam fecha, requisição gera uma leitura"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print("VERMELHO:", e)
        sys.exit(1)
