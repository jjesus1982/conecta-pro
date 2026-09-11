"""Oráculo — TODO funcionário ativo consegue bater o ponto pelo app (11/09/2026).

Jordan, 11/09: *"preciso que todos batam ponto normalmente"*. Este oráculo é o que impede que
isso volte a ser falso sem ninguém perceber — e a pergunta que ele faz é a que faltava.

O que o sistema sabia dizer até hoje era quem BATEU. Quem não conseguia era invisível, por três
motivos diferentes e todos medidos em 11/09:
  · 2 pessoas SEM CONTA no portal — não entravam nem para tentar;
  · 4 SEM ROSTO cadastrado — o app não tinha com o que comparar;
  · 6 com tudo em ordem e o app parado há semanas — cinco delas cadastraram o rosto entre 11 e
    12/08, bateram UMA vez e nunca mais, porque a referência ficou ruim e o app só dizia
    "tente novamente".

Nenhuma delas gerava alarme. Voltavam para o Tangerino em silêncio, e do lado de dentro estava
tudo verde — 42 pessoas batendo, nenhum vermelho em lugar nenhum.

As três condições afirmadas aqui, para todo CLT ativo:
  1. tem conta de portal ativa;
  2. tem rosto de referência cadastrado;
  3. registrou ao menos UMA batida pelo app (mobile/web) nos últimos `DIAS` dias.

A (3) tolera quem acabou de ser destravado: quem teve a referência limpa ou a conta criada nos
últimos `CARENCIA` dias ainda não teve tempo, e aparece como "aguardando", sem reprovar.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys

DIAS = 21
CARENCIA = 7

_SQL = """
SELECT e.nome,
       EXISTS (SELECT 1 FROM users u WHERE u.employee_id = e.id AND u.is_active) AS tem_conta,
       (e.face_descriptor IS NOT NULL) AS tem_rosto,
       (SELECT count(*) FROM gp_clock_punches p WHERE p.employee_id = e.id
         AND p.device_type IN ('mobile','web')
         AND p.punch_timestamp > current_date - make_interval(days => :dias)) AS bateu_no_app,
       greatest(coalesce(e.face_enrolled_at, e.updated_at), e.updated_at) > (
         (now() AT TIME ZONE 'America/Manaus') - make_interval(days => :carencia)) AS mexido_agora
  FROM employees e
 WHERE coalesce(e.status,'ativo') = 'ativo'
   AND coalesce(e.is_homologacao,false) = false
   AND (e.tipo_contrato = 'clt' OR e.tipo_contrato IS NULL)
 ORDER BY e.nome
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    linhas = (await db.execute(text(_SQL), {"dias": DIAS, "carencia": CARENCIA})).mappings().all()

    falhas, aguardando, ok = [], [], 0
    for r in linhas:
        if not r["tem_conta"]:
            falhas.append(f"{r['nome']}: SEM CONTA no portal — não consegue nem entrar")
        elif not r["tem_rosto"]:
            (aguardando if r["mexido_agora"] else falhas).append(
                f"{r['nome']}: sem rosto cadastrado"
                + (" (destravado há pouco, aguardando ele cadastrar)" if r["mexido_agora"] else ""))
        elif int(r["bateu_no_app"]) == 0:
            (aguardando if r["mexido_agora"] else falhas).append(
                f"{r['nome']}: tem conta e rosto e NÃO bateu pelo app em {DIAS} dias"
                + (" (mexido há pouco, aguardando)" if r["mexido_agora"] else ""))
        else:
            ok += 1

    for a in aguardando:
        print(f"  (aguardando, não reprova) {a}")
    for f in falhas:
        print(f"FALHOU: {f}")
    print(f"CLT ativos: {len(linhas)} · batendo pelo app: {ok} · aguardando: {len(aguardando)} · "
          f"travados: {len(falhas)}")
    if falhas:
        raise AssertionError(
            f"{len(falhas)} pessoa(s) não conseguem bater o ponto pelo app. Destravar com "
            "`backend/scripts/destravar_ponto_todos.py --aplicar` (cria conta, limpa referência "
            "ruim e avisa cada um pelo canal que alcança).")
    print("OK: todo funcionário ativo tem como bater o ponto pelo app")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
