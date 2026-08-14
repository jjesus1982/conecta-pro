#!/usr/bin/env python3
"""Liga o intervalo de almoço nos postos — o que trava a batida do 12x36 em 2.

O DEFEITO, medido em 13/08/2026 com print e áudio de quem sofreu:

    ANTONIO WALCICLEY PEREIRA DA SILVA, 12x36, Condomínio Ideal Flores.
    Entrada 05:58, "Saída" 13:23 → o app mostrou "Jornada de hoje concluída
    (2)" e DESABILITOU o botão. Ele voltou do almoço e não conseguiu marcar.
    No áudio: "quando eu registrei para ir para o almoço, ele deu que eu
    estivesse saindo já da empresa. Aí eu não consegui registrar mais."

`_proxima_batida_info` decide o tamanho da sequência assim:

    quatro = ("44" in escala) or posts.tem_intervalo_almoco
    concluido = feitas >= len(seq)          # 2 >= 2 → trava

E os NOVE postos estavam com `tem_intervalo_almoco = false`, inclusive o Ideal Flores, que
o próprio docstring do controller dá como exemplo de 4 batidas "(decisão do Jordan)".
Efeito: os 36 ativos de 12x36 recebiam sequência de 2, a segunda batida era rotulada
"Saída" (fim de expediente), e o dia fechava no almoço. Os 16 de 44h escapavam só porque a
string "44" aparece no nome da escala.

Impacto do dia: 64 batidas contra 168 do dia anterior; 29 pessoas contra 42.

DECISÃO DO JORDAN, 13/08/2026: **todos os postos 12x36 têm intervalo**. Não é o que o
histórico sozinho diria (Laranjeiras 28% e Ideal Flores 26% dos dias com 4+ batidas, contra
2–3% dos demais) — mas aquele histórico é justamente o do sistema travando, então ele mede
o defeito, não a jornada. Quem decide jornada é quem opera.

Ensaio é o padrão. Para aplicar: --aplicar --forcar (são 9, acima do teto de 5).
Para voltar: --desligar --aplicar --forcar.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \\
      python3 /app/scripts/ligar_intervalo_postos.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/scripts/qa")

from _mutacao import Mutacao  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desligar", action="store_true", help="caminho de volta")
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--forcar", action="store_true")
    a = ap.parse_args()

    alvo = not a.desligar
    rumo = "LIGAR" if alvo else "DESLIGAR"
    m = Mutacao(f"{rumo} intervalo de almoço nos postos", teto=5)

    async with async_session_factory() as db:
        linhas = (await db.execute(text(
            "SELECT p.id::text AS id, p.name AS nome, "
            "       coalesce(p.tem_intervalo_almoco,false) AS atual, "
            "       (SELECT count(*) FROM employees e WHERE e.posto_atual_id = p.id "
            "        AND lower(e.status)='ativo' "
            "        AND lower(coalesce(e.escala_padrao,''))='12x36') AS pessoas_12x36 "
            "FROM posts p WHERE p.is_active "
            "  AND coalesce(p.tem_intervalo_almoco,false) IS DISTINCT FROM :alvo "
            "ORDER BY 4 DESC, p.name"
        ), {"alvo": alvo})).mappings().all()

        total_afetados = sum(r["pessoas_12x36"] for r in linhas)
        alvos = [(r["id"][:8], f"{r['nome']} — {r['pessoas_12x36']} pessoa(s) em 12x36 "
                              f"({'off' if not r['atual'] else 'on'} → "
                              f"{'on' if alvo else 'off'})")
                 for r in linhas]
        print(f"\n══ {rumo} intervalo — {len(linhas)} posto(s), "
              f"{total_afetados} pessoa(s) de 12x36 afetadas ══")

        if not m.confirmar(alvos):
            return 0

        n = (await db.execute(text(
            "UPDATE posts SET tem_intervalo_almoco = :alvo, updated_at = now() "
            "WHERE is_active AND coalesce(tem_intervalo_almoco,false) IS DISTINCT FROM :alvo"
        ), {"alvo": alvo})).rowcount
        await db.commit()
        m.feito(n)

        # conferência: quantas pessoas passam a ter 4 batidas previstas
        conf = (await db.execute(text(
            "SELECT count(*) FILTER (WHERE lower(coalesce(e.escala_padrao,'')) LIKE '%44%' "
            "                          OR coalesce(p.tem_intervalo_almoco,false)) AS com_4, "
            "       count(*) AS total "
            "FROM employees e LEFT JOIN posts p ON p.id = e.posto_atual_id "
            "WHERE lower(e.status)='ativo' "
            "  AND upper(coalesce(e.nome,'')) NOT LIKE '%TESTE%' "
            "  AND upper(coalesce(e.nome,'')) NOT LIKE '%HOMOLOGA%'"
        ))).first()
        print(f"  DEPOIS: {conf[0]} de {conf[1]} ativos com 4 batidas previstas")
        if alvo and conf[0] != conf[1]:
            print(f"  ⚠️ {conf[1] - conf[0]} pessoa(s) seguem em 2 batidas — "
                  f"provavelmente sem posto vinculado. Confira antes do turno.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
