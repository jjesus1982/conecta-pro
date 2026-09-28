"""Oráculo — supervisão planejada tem DENOMINADOR (horizonte), 28/09/2026.

Por que existe: `op_supervisao_ocorrencias` estava com 0 linhas e a capacidade inteira já existia
(schema, escritor, beat com consumidor, builder, abas no menu, endpoint aceitando o payload do
form). O que não existia era o DENOMINADOR: `gerar_ocorrencias` só sabia fazer UM dia e os três
chamadores de produção — beat 00:30, a tela ao abrir, `criar_plano` — todos chamavam com «hoje».
Medido em 28/09/2026 com um plano semanal seg/qua vigente 01→30/09 (9 dias devidos em setembro):
o mapa dizia «Planejadas: 1». A coluna «A vencer» era estruturalmente impossível de ser > 0.
A frente U1 nasceu para responder «3 visitas no mês são 3 de 3 ou 3 de 20?» — sem horizonte ela
comparava o realizado contra ele mesmo e a % dava sempre ~100%.

O oráculo anterior (`test_oraculo_u1_movimentacao_supervisao.py`) dava verde nisso porque TRAZIA O
LAÇO CONSIGO: `for i in range(14): await gerar_ocorrencias(db, ini + timedelta(days=i))`. Provava
o algoritmo da frequência e escondia a ausência do motor. Este aqui nunca chama
`gerar_ocorrencias` para montar o cenário: chama `criar_plano` UMA vez, que é o que a tela faz.

O que afirma (recontado por SQL próprio, nunca pelo serviço):
  a. `criar_plano` sozinho — um POST do form, zero chamadas extras — produz as ocorrências de hoje
     até `horizonte()` (fim do mês seguinte), == `generate_series` recontado em SQL.
  b. Existe ao menos uma ocorrência com `data > hoje` e status `planejada`: é a coluna «A vencer»,
     o denominador. Antes do conserto isto era impossível.
  c. Do FUTURO, nunca do passado: nenhuma ocorrência nasce antes de hoje, mesmo com a vigência
     começando semanas atrás. Gerar o passado marcaria `nao_realizada` uma visita que pode ter
     acontecido sem ocorrência para fechar — inventaria a falta (regra da casa: nunca fabricar).
  d. Idempotente: repetir `gerar_ocorrencias(..., ate=horizonte())` não duplica (UNIQUE plano×data).
  e. O default continua sendo UM dia: quem chamar sem `ate` recebe um dia só — então o teste (a)
     não passa por acidente de default.
  f. O CHAMADOR de produção pede o horizonte: o beat `operacional.supervisao_planejada_gerar`
     passa `ate=` no código carregado (`inspect.getsource` da função viva, não grep de arquivo).
     A busca é auto-testada contra um texto falso antes de valer como prova.

Fixtures marcadas 'FIXTURE HORIZONTE U1' em `observacao`, apagadas no `finally` (ocorrências caem
por CASCADE) e a limpeza é conferida por leitura.

Roda no container (PYTHONPATH=/app):
  docker exec conecta-pro-backend python /app/scripts/orq/test_oraculo_supervisao_horizonte.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL falhas ...: N`.
"""

from __future__ import annotations

import asyncio
import inspect
import sys

FIX = "FIXTURE HORIZONTE U1"
SQL_POSTO = "SELECT id::text FROM posts WHERE is_active ORDER BY name LIMIT 1"
SQL_SUP = "SELECT id::text FROM employees WHERE status IN ('ativo','pj_ativo') ORDER BY nome LIMIT 1"
SQL_OCORR = (
    "SELECT o.data, o.status FROM op_supervisao_ocorrencias o JOIN op_supervisao_planos p ON p.id = o.plano_id "
    "WHERE p.observacao LIKE :f ORDER BY o.data"
)
SQL_ESPERADO_DIARIO = "SELECT count(*) FROM generate_series(CAST(:a AS date), CAST(:b AS date), '1 day') d"
LIMPA = "DELETE FROM op_supervisao_planos WHERE observacao LIKE :f"
SQL_SOBRAS = "SELECT count(*) FROM op_supervisao_planos WHERE observacao LIKE :f"


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    try:
        from modules.operacional.services import supervisao_planejada as sp

        sp.horizonte  # noqa: B018 — AttributeError no código de ontem (não existia)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ (a–f) supervisão planejada sem horizonte(): {type(exc).__name__}: {exc}")
        print("TOTAL falhas supervisão horizonte: 1")
        return 1

    # ── f. o chamador de produção pede o horizonte (código vivo, não arquivo) ──
    try:
        from modules.operacional.tasks import supervisao_planejada_gerar

        src = inspect.getsource(supervisao_planejada_gerar)
    except Exception as exc:  # noqa: BLE001
        src = ""
        ok(False, f"(f) não consegui ler o código do beat: {type(exc).__name__}: {exc}")
    if src:
        # a busca antes do achado: se ela acusar um texto que NÃO tem o padrão, não vale como prova
        falso = "r = await gerar_ocorrencias(db, d0)"
        ok(
            "ate=" not in falso and "horizonte" not in falso,
            "(f) a busca por 'ate='/'horizonte' rejeita o código de ontem (auto-teste do casador)",
        )
        ok(
            "ate=" in src and "horizonte" in src,
            "(f) beat operacional.supervisao_planejada_gerar chama gerar_ocorrencias com ate=horizonte(...)",
        )

    async with async_session_factory() as db:
        await sp._ensure(db)

        async def limpar() -> None:
            await db.rollback()
            await db.execute(text(LIMPA), {"f": FIX + "%"})
            await db.commit()

        await limpar()
        try:
            posto = (await db.execute(text(SQL_POSTO))).scalar()
            sup = (await db.execute(text(SQL_SUP))).scalar()
            if not posto or not sup:
                ok(False, f"sem posto ativo ou colaborador ativo para a fixture: posto={posto} sup={sup}")
                raise RuntimeError("fixture impossível")

            hoje = sp.hoje_manaus()
            horiz = sp.horizonte(hoje)
            ok(horiz > hoje, f"horizonte({hoje}) = {horiz} é depois de hoje")

            # vigência começando 40 dias ATRÁS de propósito: (c) mede que o passado não nasce
            passado = hoje.replace(day=1) if hoje.day > 1 else hoje
            plano = await sp.criar_plano(
                db,
                supervisor_employee_id=sup,
                frequencia="diaria",
                posto_id=posto,
                vigencia_inicio=passado,
                observacao=FIX,
                user_id=None,
            )

            # ── a. criar_plano sozinho gera hoje…horizonte (recontado por SQL) ──
            linhas = (await db.execute(text(SQL_OCORR), {"f": FIX + "%"})).fetchall()
            esperado = (await db.execute(text(SQL_ESPERADO_DIARIO), {"a": hoje, "b": horiz})).scalar()
            ok(
                len(linhas) == esperado and esperado > 1,
                f"(a) criar_plano gerou {len(linhas)} ocorrências == generate_series {hoje}…{horiz} = {esperado}",
            )

            # ── b. «A vencer» existe: ocorrência futura em status planejada ──
            futuras = [r for r in linhas if r[0] > hoje and r[1] == "planejada"]
            ok(bool(futuras), f"(b) ocorrências futuras 'planejada' (coluna «A vencer»): {len(futuras)}")

            # ── c. nada antes de hoje, mesmo com vigência retroativa ──
            antes = [r for r in linhas if r[0] < hoje]
            ok(
                not antes and passado < hoje,
                f"(c) vigência desde {passado} e nenhuma ocorrência anterior a hoje: {len(antes)} encontradas",
            )

            # ── d. repetir não duplica ──
            await sp.gerar_ocorrencias(db, ate=horiz, plano_id=plano["id"])
            n2 = len((await db.execute(text(SQL_OCORR), {"f": FIX + "%"})).fetchall())
            ok(n2 == len(linhas), f"(d) gerar de novo não duplica: {len(linhas)} → {n2}")

            # ── e. o default é UM dia (o (a) não passou por default generoso) ──
            r_um = await sp.gerar_ocorrencias(db, plano_id=plano["id"])
            ok(
                r_um.get("ate") == r_um.get("dia") == hoje.isoformat(),
                f"(e) sem `ate` a janela é só hoje: {r_um.get('dia')}…{r_um.get('ate')}",
            )
        except sp.SupervisaoPlanejadaErro as exc:
            ok(False, f"supervisão recusou a fixture: {exc.status} {exc}")
        except RuntimeError:
            pass
        finally:
            await limpar()
            sobras = (await db.execute(text(SQL_SOBRAS), {"f": FIX + "%"})).scalar() or 0
            orfas = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM op_supervisao_ocorrencias o "
                        "WHERE NOT EXISTS (SELECT 1 FROM op_supervisao_planos p WHERE p.id = o.plano_id)"
                    )
                )
            ).scalar() or 0
            ok(sobras == 0 and orfas == 0, f"fixtures apagadas ao fim: {sobras} planos, {orfas} ocorrências órfãs")

    print(f"TOTAL falhas supervisão horizonte: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
