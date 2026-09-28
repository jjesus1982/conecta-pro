#!/usr/bin/env python3
"""Oráculo P7 — aprovar o dia é ato de DP, deixa trilha legível e não contamina o AFD.

Guarda CINCO regras. Nenhuma cita nome, id, data ou contagem: todos os alvos derivam da FONTE
(o banco, e o app montado), porque uma fotografia envelhece e uma regra não.

  1. O schema não pode RECUSAR um status que o banco TEM.
     Alvos = `SELECT DISTINCT status FROM gp_clock_punches`. Foi o defeito de partida desta
     frente: `TimeRecordStatus` listava sete valores de classificação (`falta`, `atestado`,
     `feriado`, …) que somavam ZERO linhas, e não listava os dois que somavam 11 mil
     (`approved`, `pending`) — o UPDATE existia e estava no ar, e o Pydantic devolvia 422 na
     porta. Contrato que descreve um vocabulário imaginado fecha a porta do código que funciona.

  2. Toda rota de `time-records` recusa quem não é do DP.
     Alvos = as rotas do app de verdade, não uma lista minha. Executa a dependency com um
     usuário `self:portal` (deve recusar) E com um `module:dp` (deve passar). A recusa sozinha
     seria cúmplice: passaria igual se a régua recusasse todo mundo.

  3. Decidir o dia grava trilha com AUTOR REAL e a OBSERVAÇÃO de quem decidiu.
     Não basta o status mudar: quem audita precisa de quem, quando e por quê, e o "quem" tem
     que ser nome de gente — não o UUID (defeito medido em 28/09/2026 na primeira chamada real).

  4. A decisão é idempotente E reversível.
     Reaplicar a mesma decisão não escreve trilha repetida; mudar de ideia SEMPRE pode, e fica
     registrado. A primeira versão desta frente travava o contrário: aprovar era irreversível e
     a resposta dizia `ok`.

  5. Batida que o DP pode desfazer NÃO entra no AFD, e a que ele não pode desfazer ENTRA.
     O AFD é memória inalterável (NSR sequencial, não volta atrás). As duas metades juntas:
     `rejected` fora, e a irmã de caminho feliz dentro.

Escreve para medir as regras 3/4/5 e DESFAZ tudo por rollback; a última coisa que faz é LER o
banco para provar que não sobrou nada. Roda no container.
"""

from __future__ import annotations

import asyncio
import pathlib
import re
import sys

from sqlalchemy import text

# A raiz sai do PRÓPRIO arquivo (scripts/orq/x.py -> ../..), nunca de "/app" fixo.
# Medido em 28/09/2026: com `/app` hardcoded eu rodei este oráculo contra uma cópia do código
# ANTERIOR em /tmp e ele passou VERDE em tudo — porque importava o código NOVO de /app o tempo
# inteiro. Oráculo que não sabe qual árvore está medindo não mede nada; é o mesmo erro de usar
# `docker exec` para medir a imagem.
_RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_RAIZ))

from core.database import async_session_factory  # noqa: E402
from modules.people_management.hr.schemas.time_record import TimeRecordStatus  # noqa: E402
from modules.people_management.hr.services.time_record_service import TimeRecordService  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _fixtures import bloqueado  # noqa: E402

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


class _Fake:
    """Usuário de mentira SÓ para executar a parede — nunca escreve nada."""

    def __init__(self, role, perms, email="ninguem@exemplo.invalid"):
        self.id, self.role, self.permissions, self.email = "00000000-0000-0000-0000-000000000000", role, perms, email
        self.is_active = True


async def _regra_1_schema_aceita_o_que_o_banco_tem(db) -> None:
    do_banco = {
        s for (s,) in (await db.execute(text("SELECT DISTINCT status FROM gp_clock_punches"))).all() if s
    }
    if not do_banco:
        bloqueado("gp_clock_punches vazia — não há status real para comparar")
    recusados = sorted(s for s in do_banco if s not in set(TimeRecordStatus))
    assert not recusados, (
        f"o schema RECUSA status que o banco tem: {recusados}. "
        "TimeRecordUpdate.status é a porta do PATCH: valor que existe no banco e não existe no "
        "enum vira 422 e a tela não consegue nem devolver a batida ao estado em que ela está."
    )
    print(f"OK 1 · schema aceita os {len(do_banco)} status reais do banco: {sorted(do_banco)}")


async def _regra_2_parede_de_dp() -> None:
    from main_production import app

    portal, dp = _Fake("funcionario", ["self:portal"]), _Fake("operator", ["module:dp"])
    rotas = [r for r in app.routes if "time-records" in getattr(r, "path", "")]
    if not rotas:
        bloqueado("nenhuma rota de time-records montada no app")

    async def _passa(rota, user) -> bool:
        """Executa TODAS as dependencies da rota com este usuário. False = alguma recusou."""
        for d in rota.dependencies:
            fn = getattr(d, "dependency", None)
            if fn is None:
                continue
            try:
                r = fn(current_user=user)
                if asyncio.iscoroutine(r):
                    await r
            except Exception:
                return False
        return True

    sem_parede = []
    trava_o_dp = []
    for r in rotas:
        if await _passa(r, portal):
            sem_parede.append(f"{sorted(r.methods or [])} {r.path}")
        if not await _passa(r, dp):
            trava_o_dp.append(f"{sorted(r.methods or [])} {r.path}")
    assert not sem_parede, (
        f"rota(s) de ponto SEM parede de DP — um token `self:portal` passa: {sem_parede}. "
        "Batida é documento trabalhista; estar logado não é ter o papel."
    )
    # A irmã de caminho feliz: sem ela, uma parede que recusa TODO MUNDO passaria neste oráculo
    # e a Pyetra descobriria pela tela.
    assert not trava_o_dp, f"a parede recusa até quem TEM module:dp: {trava_o_dp}"
    print(f"OK 2 · as {len(rotas)} rotas de time-records recusam self:portal e aceitam module:dp")


async def _dia_cobaia(db):
    """Um dia-pessoa real com batida decidível. Preferência: colaborador de HOMOLOGAÇÃO."""
    for so_homologacao in (True, False):
        r = (
            await db.execute(
                text(
                    "SELECT CAST(p.employee_id AS TEXT), to_char(p.punch_timestamp,'YYYY-MM-DD'), "
                    "       min(p.punch_id), count(*) "
                    "  FROM gp_clock_punches p JOIN employees e ON e.id = p.employee_id "
                    " WHERE p.status <> 'pendente_de_conferencia' "
                    + ("   AND coalesce(e.is_homologacao,false) " if so_homologacao else "")
                    + " GROUP BY p.employee_id, to_char(p.punch_timestamp,'YYYY-MM-DD') "
                    " ORDER BY count(*) DESC LIMIT 1"
                )
            )
        ).first()
        if r:
            return r
    return None


async def _regras_3_4_trilha_e_reversibilidade(db) -> None:
    cobaia = await _dia_cobaia(db)
    if not cobaia:
        bloqueado("nenhum dia-pessoa com batida decidível para medir a trilha")
    emp, dia, punch, qtd = cobaia
    svc = TimeRecordService(db)
    antes = (
        await db.execute(
            text("SELECT status FROM gp_clock_punches WHERE punch_id = :p"), {"p": punch}
        )
    ).scalar()
    alvo = "rejected" if antes != "rejected" else "approved"
    frase = "oráculo P7 — escrita de teste, desfeita por rollback"

    r1 = await svc.decidir_dia(
        employee_id=emp, dia=dia, decisao=alvo, observacao=frase, updated_by=await _um_usuario(db)
    )
    assert r1["batidas"] > 0, f"decidir o dia não alcançou nenhuma das {qtd} batidas de {dia}"

    hist = await svc.get_historico(punch)
    assert hist, "o status mudou e o histórico ficou VAZIO — estado sem autor não é trilha"
    topo = hist[0]
    assert topo["observacao"] == frase, (
        f"a observação de quem decidiu não chegou ao histórico: {topo['observacao']!r}. "
        "Trilha vazia é pior que trilha ausente — parece que ninguém explicou nada."
    )
    assert not _UUID.match(str(topo["por"])), (
        f"o histórico mostra UUID em vez de NOME no autor: {topo['por']!r}. "
        "A tela mostra este campo como «quem»; UUID ali não é trilha legível."
    )
    assert (topo["mudou"] or {}).get("status", {}).get("para") == alvo, (
        f"a trilha não registra a mudança de status: {topo['mudou']!r}"
    )
    print(f"OK 3 · decisão de {r1['batidas']} batida(s) virou trilha com autor «{topo['por']}» e observação")

    # 4 · idempotência (mesma decisão não repete trilha) + reversibilidade (mudar de ideia pode)
    r2 = await svc.decidir_dia(
        employee_id=emp, dia=dia, decisao=alvo, observacao=frase, updated_by=await _um_usuario(db)
    )
    assert r2["batidas"] == 0, f"reaplicar a MESMA decisão mexeu em {r2['batidas']} batida(s) — trilha duplicada"
    volta = "approved" if alvo == "rejected" else "rejected"
    r3 = await svc.decidir_dia(
        employee_id=emp, dia=dia, decisao=volta, observacao=frase, updated_by=await _um_usuario(db)
    )
    assert r3["batidas"] > 0, (
        f"depois de {alvo} o DP não consegue mais decidir {volta}: a decisão ficou IRREVERSÍVEL. "
        "Conferência em que não se pode mudar de ideia não é conferência — e a resposta da rota "
        "devolve `ok` com 0 batidas, então ninguém percebe."
    )
    print(f"OK 4 · reaplicar não repete trilha ({r2['batidas']}) e mudar de ideia funciona ({r3['batidas']})")


async def _um_usuario(db) -> str:
    return str(
        (await db.execute(text("SELECT CAST(id AS TEXT) FROM users WHERE is_active LIMIT 1"))).scalar()
    )


async def _regra_5_rejected_fora_do_afd(db) -> None:
    from modules.hr.rep_integration.services.rep_p import CORTE, gerar_afd_desde_corte

    cand = (
        await db.execute(
            text(
                "SELECT p.punch_id FROM gp_clock_punches p "
                "  LEFT JOIN afd_records a ON a.punch_id = p.punch_id "
                "  JOIN employees e ON e.id = p.employee_id "
                " WHERE p.punch_timestamp >= :corte AND a.id IS NULL "
                "   AND p.status <> 'pendente_de_conferencia' "
                "   AND e.empresa_id IS NOT NULL "
                "   AND length(regexp_replace(coalesce(e.cpf,''),'\\D','','g')) = 11 "
                " LIMIT 1"
            ),
            {"corte": CORTE},
        )
    ).scalar()
    if not cand:
        bloqueado("nenhuma batida pós-CORTE sem linha AFD para medir a regra do AFD")

    async def _gerou(p) -> bool:
        await gerar_afd_desde_corte(db, commit=False)
        return bool(
            (
                await db.execute(text("SELECT 1 FROM afd_records WHERE punch_id = :p"), {"p": p})
            ).scalar()
        )

    await db.execute(
        text("UPDATE gp_clock_punches SET status = 'rejected' WHERE punch_id = :p"), {"p": cand}
    )
    assert not await _gerou(cand), (
        "batida REPROVADA pelo DP ganhou linha de AFD. O AFD é memória inalterável de marcação: "
        "o NSR é sequencial e não volta atrás, então escrever nele um fato que o DP acabou de "
        "desfazer é afirmar integridade sobre o que não está confirmado."
    )
    print("OK 5a · batida `rejected` NÃO entrou no AFD")

    # irmã de caminho feliz — sem ela, um `WHERE false` passaria em 5a
    await db.execute(
        text("UPDATE gp_clock_punches SET status = 'approved' WHERE punch_id = :p"), {"p": cand}
    )
    assert await _gerou(cand), (
        "a MESMA batida, aprovada, também não entrou no AFD — a exclusão está larga demais e o "
        "AFD está perdendo marcação legítima (que é exatamente o que a Portaria 671 cobra)."
    )
    print("OK 5b · a mesma batida, aprovada, ENTROU no AFD")


async def main() -> None:
    # Tudo numa transação só, desfeita no fim: o oráculo roda contra o banco de PRODUÇÃO e as
    # regras 3/4/5 só se provam escrevendo. Ler depois do rollback é a prova de que não sobrou.
    async with async_session_factory() as db:
        await _regra_1_schema_aceita_o_que_o_banco_tem(db)
        await _regra_2_parede_de_dp()
        marca = "oráculo P7 — escrita de teste, desfeita por rollback"
        try:
            await _regras_3_4_trilha_e_reversibilidade(db)
            await _regra_5_rejected_fora_do_afd(db)
        finally:
            await db.rollback()

    async with async_session_factory() as db2:
        sobrou = (
            await db2.execute(
                text("SELECT count(*) FROM gp_audit_logs WHERE extra_data->>'observacao' = :m"),
                {"m": marca},
            )
        ).scalar()
        assert sobrou == 0, f"o rollback NÃO desfez: {sobrou} linha(s) de teste ficaram em gp_audit_logs"
    print("OK 6 · nada do teste sobrou no banco (lido DEPOIS do rollback)")
    print("\nP7 VERDE — aprovar o dia é ato de DP, deixa trilha legível e não contamina o AFD.")


if __name__ == "__main__":
    asyncio.run(main())
