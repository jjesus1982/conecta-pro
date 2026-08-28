"""Oráculo — a descrição de cada consulta bate com a assinatura dela (28/08/2026).

`registrar_read` aceita QUALQUER texto como descrição e não confere nada contra o handler.
E a descrição é a única coisa que o modelo lê: o `filtros` do dispatcher é dict livre, sem
schema. Então os dois erros abaixo são silenciosos e opostos:

  FANTASMA  a descrição anuncia um filtro que o handler não tem. O modelo manda, o valor cai
            no `**_` e some. Ninguém vê erro — o filtro simplesmente não filtra. Caso real:
            `catalogo` anunciava `incluir_inativos`, que nunca existiu.

  MUDO      o handler tem um parâmetro que a descrição não nomeia. A capacidade existe e o
            modelo nunca vai pedir, porque não sabe que pode. Caso real: `catalogo` tinha
            `so_com_preco` e o José Luís não tinha como pedir "só os que têm preço".

⚠️ VALOR NÃO É PARÂMETRO. Descrições listam valores entre parênteses —
`status_filtro (todos|aprovado|em_admissao)` — e uma versão ingênua acusa `em_admissao` de
fantasma. Medido: 5 acusações, 4 delas valores. Por isso o conteúdo entre parênteses é
removido antes da busca. Sem essa regra o oráculo cria trabalho falso e é ignorado, que é
como oráculo morre.
"""
import inspect
import re
import sys

sys.path.insert(0, "/app")

IGNORAR = {"db", "user", "scope", "self"}
#: `page`/`skip` são paginação implícita em toda listagem — anunciá-las em 119 descrições é
#: ruído sem ganho. Ficam de fora do MUDO por decisão, não por acidente.
MUDO_TOLERADO = {"page", "skip", "limit", "limite"}
#: O módulo que ESTE terminal mantém. Achado em módulo alheio vira AVISO, não falha: a
#: descrição é de quem cuida do módulo, e oráculo que falha por dívida de outro time é
#: oráculo que alguém desliga.
MEU_MODULO = "crm"


def _sem_valores(desc: str) -> str:
    """Remove o conteúdo entre parênteses: ali moram VALORES, não nomes de parâmetro."""
    return re.sub(r"\([^)]*\)", " ", desc)


def main() -> int:
    import main_production  # noqa: F401
    from modules.ai.conversation.services.orquestrador import (  # noqa: F401
        tools_read_crm, tools_read_dp, tools_read_financeiro, tools_read_fiscal,
        tools_read_ged, tools_read_juridico,
    )
    from modules.ai.conversation.services.orquestrador.read_dispatcher import _READ_OPS

    fantasmas, mudos, total = [], [], 0
    for mod, ops in sorted(_READ_OPS.items()):
        for nome, op in sorted(ops.items()):
            total += 1
            reais = {p for p, v in inspect.signature(op["handler"]).parameters.items()
                     if p not in IGNORAR and v.kind is not inspect.Parameter.VAR_KEYWORD}
            desc = op["desc"]
            limpa = _sem_valores(desc)
            pos = limpa.lower().find("filtro")
            if pos >= 0:
                # só a FRASE do filtro. `revisar_funil` termina com "Depois use agir_crm
                # acao=resolver_propostas" — prosa útil que uma versão anterior acusou de
                # fantasma. O ponto final delimita.
                trecho = limpa[pos:].split(".")[0]
                # SÓ nome com `_`. Tentei aceitar palavra solta para pegar
                # `ged.documentos` anunciando `busca` quando a assinatura tem `q`/`search`
                # — e colhi 5 acusações de prosa ("lista", "com", "abre") num só registro.
                # A lista de exceções necessária cresceria a cada descrição nova, e oráculo
                # que acusa em falso é oráculo que alguém desliga.
                # O caso do `busca` NÃO se perde: ele aparece do outro lado, como MUDO
                # (`q` e `search` existem e a descrição não os nomeia). Um defeito, duas
                # faces — basta uma delas ser barata de detectar.
                for c in re.findall(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", trecho):
                    if c not in reais:
                        fantasmas.append(f"{mod}.{nome}: anuncia {c!r}, que não existe")
            for p in reais - MUDO_TOLERADO:
                if not re.search(r"\b%s\b" % re.escape(p), desc):
                    mudos.append(f"{mod}.{nome}: tem {p!r} e a descrição não o nomeia")

    meus = [x for x in fantasmas + mudos if x.startswith(MEU_MODULO + ".")]
    alheios = [x for x in fantasmas + mudos if not x.startswith(MEU_MODULO + ".")]

    print(f"\n  {total} consultas em {len(_READ_OPS)} módulos\n")
    for f in fantasmas:
        print(f"  {'FANTASMA' if f in fantasmas else 'MUDO':8} · {f}")
    for m in mudos:
        print(f"  MUDO     · {m}")
    if alheios:
        print(f"\n  ⚠️ {len(alheios)} achado(s) em MÓDULO ALHEIO — reportado, não consertado:")
        for a in alheios:
            print(f"      {a}")
    if meus:
        print(f"\n  ❌ {len(meus)} em {MEU_MODULO}: {'; '.join(meus)}")
        return 1
    print(f"\n  ✅ {MEU_MODULO}: toda descrição bate com a assinatura — nada anunciado a "
          "mais, nada escondido.")
    return 0


sys.exit(main())
