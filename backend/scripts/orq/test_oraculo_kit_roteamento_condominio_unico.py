"""Oráculo — o documento do kit vai para UM condomínio, decidido pela FK, nunca pelo empate (28/09/2026).

Por que existe: a Pyetra viu kit de condomínio com documento de gente de OUTRO condomínio. O
conserto da vez mirou os dois montadores de kit (`kit_builder_service.get_employees_for_client` e
`kit_real_controller._get_employees_for_client`) e o oráculo daquela rodada observa só esses dois.

Medido no banco em 28/09/2026, porém: dos 1.541 documentos gravados no condomínio errado
(`ged_kit_documents` × janela de `allocations`), NENHUM saiu dos dois montadores — 890 vieram com
`source_module='dp'` e 466 com `'fiscal'`, os dois de um TERCEIRO gravador,
`client_portal/services/portal_kit_materializar_service.py`, que ninguém estava observando. 51
deles foram escritos no próprio dia 28/09. `gedeon_tasks/kronos_tasks.py` já avisava em
comentário: são NOVE lugares que fazem `INSERT INTO ged_kit_documents`.

Esse terceiro gravador decidia o condomínio por SUBSTRING de nome e deixava o ÚLTIMO a casar
vencer, sem nunca ler `posts.ged_client_id` — a FK autoritativa, preenchida em 16 dos 17 postos.
Resultado provado: os postos 'Portaria Principal - Mirante das Flores' e 'Condomínio Mirante das
Flores' têm FK = MIRANTE, mas o token 'FLORES' casava também com IDEAL FLORES DA CIDADE, que vinha
depois no laço e ganhava — 9 dos 17 postos tinham mais de um candidato.

A regra afirmada (não a fotografia — nada de UUID, nome de condomínio ou contagem chumbada):

  1. todo posto com `ged_client_id` preenchido é roteado para ESSE ged_client. A FK manda sobre
     qualquer semelhança de nome;
  2. nenhum posto é roteado quando o nome aponta para mais de um ged_client — empate não escolhe,
     fica de fora (fail-closed: documento faltando é buraco visível, documento no kit errado é o
     cliente lendo a folha do vizinho);
  3. `_ged_por_condominio` nunca devolve vencedor num empate de tokens.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "/app")


def main() -> int:
    from sqlalchemy import create_engine, text

    from modules.client_portal.services.portal_kit_materializar_service import (
        GENERICOS,
        _ged_por_condominio,
        _mapa_funcionarios,
        _norm,
    )
    from modules.client_portal.services.portal_operacao_service import ALIAS_POSTO

    url = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg", "postgresql+psycopg2")
    if not url:
        print("BLOQUEADO: DATABASE_URL ausente")
        return 3

    falhas: list[str] = []
    with create_engine(url).connect() as db:
        gname = {str(r["id"]): r["name"] for r in db.execute(text("SELECT id, name FROM ged_clients")).mappings()}
        posts = db.execute(text("SELECT id, name, client_id, ged_client_id FROM posts")).mappings().all()
        geds = (
            db.execute(
                text(
                    """SELECT g.id AS gid, g.name AS gnome, g.cnpj, c.id AS cliente_id, cond.nome AS cond_nome
                   FROM ged_clients g
                   LEFT JOIN clients c ON regexp_replace(c.document_number,'[^0-9]','','g')
                                        = regexp_replace(COALESCE(g.cnpj,''),'[^0-9]','','g') AND g.cnpj IS NOT NULL
                   LEFT JOIN condominios cond ON cond.client_id=c.id"""
                )
            )
            .mappings()
            .all()
        )
        mapa = _mapa_funcionarios(db)
        post2ged = {}
        # o mapa expõe emp2ged; post2ged é interno, então reconstruo a verdade INDEPENDENTE aqui:
        # candidatos por nome, do mesmo jeito que o código monta, para poder cobrar as duas regras.
        candidatos: dict[str, set[str]] = {}
        for g in geds:
            cond_nome = g["cond_nome"] or g["gnome"]
            toks = [t for t in _norm(cond_nome).split() if len(t) > 3 and t not in GENERICOS]
            alias = ALIAS_POSTO.get(_norm(cond_nome))
            for p in posts:
                pn = _norm(p["name"])
                if (
                    (g["cliente_id"] and str(p["client_id"] or "") == str(g["cliente_id"]))
                    or (alias and alias.upper() in pn)
                    or any(t in pn for t in toks)
                ):
                    candidatos.setdefault(str(p["id"]), set()).add(str(g["gid"]))

        # (1) e (2): o roteamento efetivo de cada posto, medido através de emp2ged — a saída que o
        # gravador realmente usa. Pessoa alocada num posto tem de cair no ged_client da FK.
        alocados = (
            db.execute(
                text(
                    """SELECT DISTINCT e.id::text AS emp, e.nome, a.post_id::text AS post
                     FROM allocations a JOIN employees e ON e.id=a.employee_id
                    WHERE a.status='active'"""
                )
            )
            .mappings()
            .all()
        )
        fk = {str(p["id"]): (str(p["ged_client_id"]) if p["ged_client_id"] else None) for p in posts}
        nome_posto = {str(p["id"]): p["name"] for p in posts}

        # Pessoa com DUAS alocações ativas não testa o roteamento: `emp2ged` guarda um destino por
        # PESSOA, e `/uploads/ponto/<emp_id>/<MM.AAAA>/` não diz em qual posto aquele mês foi
        # trabalhado. Não é o defeito consertado aqui e não se resolve em código sem alguém decidir
        # (duplicar o documento nos dois kits, ou recusar). Sai NOMEADA no fim, não escondida.
        nome_pessoa = {r["emp"]: r["nome"] for r in alocados}
        por_pessoa: dict[str, set[str]] = {}
        for r in alocados:
            por_pessoa.setdefault(r["emp"], set()).add(r["post"])
        multi = {e: ps for e, ps in por_pessoa.items() if len(ps) > 1}

        for r in alocados:
            if r["emp"] in multi:
                continue
            destino = mapa["emp2ged"].get(r["emp"])
            esperado = fk.get(r["post"])
            post2ged[r["post"]] = destino
            if esperado and destino and destino != esperado:
                falhas.append(
                    f"posto {nome_posto.get(r['post'])!r}: FK aponta "
                    f"{gname.get(esperado)!r} mas o kit roteia para {gname.get(destino)!r}"
                )
            if not esperado and destino and len(candidatos.get(r["post"], set())) > 1:
                falhas.append(
                    f"posto {nome_posto.get(r['post'])!r}: sem FK e com "
                    f"{len(candidatos[r['post']])} candidatos por nome, mas roteou para "
                    f"{gname.get(destino)!r} — empate escolheu"
                )

        # (3) empate de tokens nunca elege vencedor. Constrói o empate a partir dos DADOS: dois
        # ged_clients que compartilham um token viram um texto com só aquele token em comum.
        por_token: dict[str, list[str]] = {}
        for gid, toks in mapa["ged_tokens"].items():
            for t in toks:
                por_token.setdefault(t, []).append(gid)
        empates = {t: g for t, g in por_token.items() if len(g) > 1}
        for t, gids in empates.items():
            if _ged_por_condominio(t, mapa) is not None:
                falhas.append(
                    f"token {t!r} é de {len(gids)} condomínios "
                    f"({[gname.get(g) for g in gids]}) e ainda assim elegeu um vencedor"
                )

    print(f"postos auditados: {len(post2ged)} · com FK: {sum(1 for v in fk.values() if v)}/{len(fk)} · "
          f"tokens ambíguos exercitados: {len(empates)}")
    if multi:
        print(f"⚠️  {len(multi)} pessoa(s) com DUAS alocações ativas — o destino do ponto é escolhido "
              f"por ordem de dicionário e a pasta do ponto não diz o posto. Precisa de decisão "
              f"humana (duplicar nos dois kits ou recusar), não de código:")
        for emp, ps in multi.items():
            print(f"     {nome_pessoa.get(emp, emp)}: {sorted(nome_posto.get(p, p) for p in ps)}")
    if falhas:
        for f in sorted(set(falhas)):
            print(f"FALHOU: {f}")
        print(f"\n{len(set(falhas))} violação(ões) de roteamento de condomínio no kit")
        return 1
    print("✅ FK manda, empate não escolhe — nenhum documento roteado para o condomínio do vizinho")
    return 0


if __name__ == "__main__":
    sys.exit(main())
