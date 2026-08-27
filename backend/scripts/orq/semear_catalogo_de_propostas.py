#!/usr/bin/env python3
"""Semeia `crm_products` com os itens que o Jordan JÁ digitou nas propostas.

Por que existe: em 27/08/2026 a medição foi

    proposal_items          162 itens em 33 propostas
      code preenchido         0    ← nenhum item veio de catálogo
      nomes distintos       116    ← 46 itens são REDIGITAÇÃO
    crm_products              0    ← a tabela existe, com CRUD pronto, VAZIA

Ele já faz orçamento de material e de projeto (NVR, HD Purple, câmera bullet, fibra
óptica, torre) — digitando cada linha, toda vez. O catálogo não estava faltando: estava
DESLIGADO, com as 4 rotas CRUD montadas e nenhuma linha dentro.

⭐ NÃO FABRICA PREÇO. Cada produto entra com o preço da proposta MAIS RECENTE em que o
item apareceu, e a `description` carimba de onde veio: número da proposta e data. Se o
preço envelheceu, o carimbo denuncia — o que não pode acontecer é um número sem origem
chegar num cliente.

Decisão do Jordan (27/08/2026): semear TUDO com o último preço praticado. Ele corrige na
tela o que envelheceu.

Idempotente por NOME: rodar de novo não duplica e NÃO sobrescreve produto que alguém
editou à mão depois (só insere o que ainda não existe).

    # ver o que faria, sem escrever nada:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/semear_catalogo_de_propostas.py

    # escrever:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/semear_catalogo_de_propostas.py --gravar

    # desfazer (só o que ESTE script criou — o carimbo é a marca):
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/semear_catalogo_de_propostas.py --desfazer
"""
from __future__ import annotations

import asyncio
import hashlib
import sys

sys.path.insert(0, "/app")

#: Carimbo de origem. É a marca que torna o seeder reversível: só some o que ele pôs.
_CARIMBO = "[catálogo semeado do histórico de propostas]"

#: Categoria por palavra-chave no nome do item. Serve para FILTRAR no chat ("me mostra o
#: que tenho de CFTV"), não para contabilidade. Primeira regra que casar vence — por isso
#: a ordem importa: "instalação de câmera" é serviço de CFTV, e CFTV é mais específico.
_CATEGORIAS: list[tuple[str, tuple[str, ...]]] = [
    # Locação vem PRIMEIRO de propósito: "locação mensal do sistema de videomonitoramento"
    # é receita recorrente de aluguel, não venda de CFTV. A modalidade manda na categoria,
    # porque é ela que decide como o item entra no orçamento e no contrato.
    ("Locação", ("locação", "locacao", "aluguel", "comodato")),
    ("Software / plataforma", ("conecta plus", "app ", "aplicativo", "licença", "licenca",
                               "plataforma", "sentinela", "ia de voz")),
    ("CFTV", ("camera", "câmera", "nvr", "dvr", "cftv", "purple", "surveillance", "lente",
              "videomonitoramento", "monitoramento", "gravação", "gravacao")),
    ("Cerca elétrica", ("cerca", "eletrificador", "choque", "haste", "isolador",
                        "arame", "aço inox", "aco inox")),
    ("Alarme", ("alarme", "sensor", "sirene", "infravermelho", "ivp", "giroflex",
                "sinalização ostensiva", "sinalizacao ostensiva")),
    ("Controle de acesso", ("catraca", "facial", "biometr", "tag", "cancela", "barreira",
                            "interfone", "porteiro eletr", "motor deslizante", "portão",
                            "portao")),
    ("Energia e proteção", ("dps", "disjuntor", "surto", "aterramento", "solar",
                            "off-grid", "bateria", "painel solar", "nobreak", "no-break",
                            "base de concreto", "energia")),
    ("Rede e infraestrutura", ("fibra", "óptic", "optic", "eletroduto", "vala", "switch",
                               "poe", "cabo", "cat6", "cat 6", "rack", "torre", "poste",
                               "infraestrutura", "patch", "keystone", "pigtail", "dio ",
                               "dio-", "sfp", "transceiver", "mikrotik", "roteador",
                               "cordão", "cordao", "backbone", "cabeamento")),
    ("Mão de obra", ("agp ", "porteiro", "portaria", "vigilan", "vigilân", "zelador",
                     "limpeza", "12x36", "diurno", "noturno", "caseiro")),
    ("Serviço técnico", ("instala", "manuten", "configura", "comissionamento", "suporte",
                         "projeto", "visita", "treinamento", "montagem", "serviço:",
                         "servico:", "certifica", "as-built", "documentação técnica",
                         "fusão", "fusao", "migração", "migracao", "reorganização",
                         "reorganizacao")),
]

#: Nomes que são RESÍDUO DE TESTE dentro de proposta real. Não entram no catálogo — mas o
#: script os NOMEIA em vez de sumir com eles: item de teste numa proposta de cliente é um
#: achado, não sujeira para varrer para debaixo do tapete.
#:
#: ⚠️ Casa o NOME INTEIRO, não substring. A primeira versão procurava "teste" em qualquer
#: posição e condenou "Serviço: terminação de fibra em DIO, fusão e TESTES ópticos" — um
#: serviço real de R$ 4 mil. Substring em heurística de descarte tem falso positivo caro:
#: o item some do catálogo e ninguém percebe.
_RESIDUO_EXATO = frozenset({"item qa", "teste", "test", "xxx", "asdf", "aaa", "item teste"})
_RESIDUO_PREFIXO = ("zzteste", "zz_", "[teste]")


def _eh_residuo(nome: str) -> bool:
    n = nome.strip().lower()
    return n in _RESIDUO_EXATO or n.startswith(_RESIDUO_PREFIXO)

#: Produto do portfólio → service_type do motor de precificação (define ISS/impostos).
#: Fora do mapa fica NULL: preferimos vazio a chute. Mesmo mapa de tools_comercial_doc.py.
_SERVICE_TYPES = {
    "Mão de obra": "portaria",
}


def _categoria(nome: str) -> str:
    n = nome.lower()
    for cat, chaves in _CATEGORIAS:
        if any(k in n for k in chaves):
            return cat
    return "Outros"


def _sku(nome: str) -> str:
    """SKU determinístico a partir do nome.

    Sequencial (CAT-0001, CAT-0002…) seria mais bonito e ERRADO: item novo entrando no
    meio da ordem alfabética renumeraria os de baixo, e SKU que muda não é SKU. O hash do
    nome não se move.
    """
    h = hashlib.md5(nome.strip().lower().encode()).hexdigest()[:6].upper()
    return f"CAT-{h}"


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    gravar = "--gravar" in sys.argv
    desfazer = "--desfazer" in sys.argv

    async with async_session_factory() as db:
        if desfazer:
            n = (await db.execute(text(
                "DELETE FROM crm_products WHERE description LIKE :c"),
                {"c": f"%{_CARIMBO}%"})).rowcount
            await db.commit()
            print(f"  desfeito: {n} produto(s) semeado(s) removido(s); "
                  f"o que foi cadastrado à mão continua lá")
            return 0

        # Último preço praticado: DISTINCT ON pelo nome, ordenando pela proposta mais
        # recente. `issue_date` é a data do documento; `created_at` desempata quando duas
        # propostas saem no mesmo dia.
        linhas = (await db.execute(text("""
            SELECT DISTINCT ON (lower(btrim(i.name)))
                   btrim(i.name)                        AS nome,
                   coalesce(i.unit, 'un')               AS unidade,
                   i.unit_price                         AS preco,
                   p.number                             AS proposta,
                   coalesce(p.issue_date::date, p.created_at::date) AS data,
                   count(*) OVER (PARTITION BY lower(btrim(i.name))) AS vezes
            FROM proposal_items i
            JOIN proposals p ON p.id = i.proposal_id
            WHERE btrim(coalesce(i.name, '')) <> ''
            ORDER BY lower(btrim(i.name)),
                     coalesce(p.issue_date::date, p.created_at::date) DESC,
                     p.created_at DESC
        """))).mappings().all()

        existentes = {n.strip().lower() for n in (await db.execute(text(
            "SELECT name FROM crm_products"))).scalars().all()}

        residuo = [r for r in linhas if _eh_residuo(r["nome"])]
        uteis = [r for r in linhas if r not in residuo]
        novos = [r for r in uteis if r["nome"].strip().lower() not in existentes]
        pulados = len(uteis) - len(novos)

        # Quase-duplicatas: "Patch cords Cat6 2,5m" aparece em 3 grafias. NÃO fundimos
        # sozinhos — preços podem divergir por motivo real (kit vs avulso). Só apontamos,
        # porque fundir errado esconde um preço; apontar não esconde nada.
        def _chave(s: str) -> str:
            return "".join(ch for ch in s.lower() if ch.isalnum())

        grupos: dict[str, list[str]] = {}
        for r in novos:
            grupos.setdefault(_chave(r["nome"])[:34], []).append(r["nome"])
        quase = {k: v for k, v in grupos.items() if len(v) > 1}

        por_cat: dict[str, int] = {}
        for r in novos:
            por_cat[_categoria(r["nome"])] = por_cat.get(_categoria(r["nome"]), 0) + 1

        print(f"  itens distintos no histórico: {len(linhas)}")
        print(f"  já existem no catálogo:       {pulados}  (não serão tocados)")
        print(f"  a inserir:                    {len(novos)}")
        for cat, n in sorted(por_cat.items(), key=lambda x: -x[1]):
            print(f"      {cat:24} {n}")
        print()
        for r in novos[:8]:
            rec = " · recorrente" if "mensal" in r["nome"].lower() else ""
            print(f"      {_sku(r['nome'])}  R$ {float(r['preco'] or 0):>10,.2f}/{r['unidade']:<4} "
                  f"{r['nome'][:52]}{rec}")
        if len(novos) > 8:
            print(f"      … e mais {len(novos) - 8}")

        if residuo:
            print(f"\n  ⚠️  {len(residuo)} item(ns) de TESTE dentro de proposta REAL — não "
                  f"entram no catálogo, mas alguém precisa olhar a proposta:")
            for r in residuo:
                print(f"      {r['nome'][:44]:46} proposta {r['proposta']} ({r['data']:%d/%m/%Y})")

        if quase:
            print(f"\n  ℹ️  {len(quase)} grupo(s) de quase-duplicata — entram como produtos "
                  f"SEPARADOS (fundir por conta própria esconderia um preço); junte na tela "
                  f"se forem a mesma coisa:")
            for v in list(quase.values())[:4]:
                print("      • " + "\n        ".join(x[:70] for x in v))

        if not gravar:
            print("\n  ENSAIO — nada foi escrito. Rode com --gravar para valer.")
            return 0

        for r in novos:
            nome = r["nome"]
            cat = _categoria(nome)
            await db.execute(text("""
                INSERT INTO crm_products (id, sku, name, description, category, unit,
                                          unit_price, is_recurring, service_type,
                                          is_active, created_at, updated_at)
                VALUES (gen_random_uuid(), :sku, :name, :desc, :cat, :unit, :preco,
                        :rec, :stype, true, now(), now())
            """), {
                "sku": _sku(nome), "name": nome, "cat": cat, "unit": r["unidade"],
                "preco": r["preco"],
                "rec": "mensal" in nome.lower(),
                "stype": _SERVICE_TYPES.get(cat),
                # O carimbo é a prova de origem E a marca de desfazer. Sem ele, o preço
                # vira número sem procedência dentro de um documento que vai a cliente.
                "desc": (f"Preço praticado em {r['data']:%d/%m/%Y}, proposta {r['proposta']}"
                         f" (usado {r['vezes']}x). {_CARIMBO}"),
            })
        await db.commit()

        total = (await db.execute(text("SELECT count(*) FROM crm_products"))).scalar()
        print(f"\n  GRAVADO: {len(novos)} inseridos · catálogo agora tem {total} produtos")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
