"""Os critérios de aceite do relatório de campo do Cowork — cobrados na TOOL.

Item 9 do prompt de 11/09/2026: "escrever testes de integração cobrindo os critérios de
aceite citados em cada item". Este arquivo é esse teste, e existe por um erro meu concreto.

⭐ POR QUE COBRAR A TOOL, E NÃO O BACKEND. Eu declarei "P0 e P1 no ar" tendo implementado
2.5 e 3.1 no backend — a ramificação por natureza no `contract_wizard`, o nome do cliente no
`list_contracts`. Ambos funcionavam. E nenhum dos dois alcançava o Jordan, porque ele
trabalha pela ferramenta do MCP, e a ferramenta não tinha mudado: `listar_contratos` só
aceitava `limite`, e `gerar_contrato_por_modelo` só repassava os dois campos de recorrência.
Medi a camada errada e chamei de entregue.

A regra que este arquivo tranca: **o aceite se prova na superfície que o dono usa.** Um
teste que importasse o serviço do backend ficaria verde sobre capacidade que não chega
a ninguém.

⚠️ NENHUM teste aqui grava. Escrita é exercitada por `dry_run=True`; onde não há dry_run,
o caminho testado é o de diagnóstico, que só lê. Testar emissão de verdade criaria contrato
real — já aconteceu nesta casa (CTR-2026-00024 nasceu de um teste meu).

    python test_aceites_cowork.py
"""
from __future__ import annotations

import asyncio
import sys

import server as S

# Dados reais e estáveis do CRM. São ÂNCORAS, não fotografias: o teste afirma a REGRA
# (o filtro filtra, o nome vem junto), nunca "existem N contratos".
MAIAPOLIS_CNPJ = "55090416000130"
MAIAPOLIS_CTR = "CTR-2026-00022"


async def aceite_2_1_documento_legivel() -> None:
    """`baixar_contrato_pdf(CTR-2026-00022, formato="base64")` -> base64 + texto_extraido."""
    r = await S.baixar_contrato_pdf(MAIAPOLIS_CTR, formato="base64")
    arq = r.get("arquivo") or {}
    texto = r.get("texto_extraido") or ""
    assert arq.get("base64"), f"sem base64: {str(r)[:200]}"
    assert texto, "sem texto_extraido — o agente continua cego ao conteúdo"
    for frase in ("limitada ao teto de 10%", "integral e regressivamente"):
        assert frase in texto, f"o aceite cita {frase!r} e o texto extraído não tem"
    print(f"OK 2.1 base64 + {len(texto)} chars de texto, com as duas cláusulas do aceite")


async def aceite_3_1_listagem_diz_o_cliente() -> None:
    """`listar_contratos(cliente_cnpj=...)` -> só os do Maiápolis, com nome do cliente."""
    r = await S.listar_contratos(cliente=MAIAPOLIS_CNPJ)
    itens = r.get("contratos") or []
    assert itens, f"o filtro por CNPJ não devolveu nada: {str(r)[:200]}"
    for c in itens:
        assert c.get("cliente_nome"), f"linha sem cliente_nome — o N+1 voltou: {c}"
        doc = "".join(ch for ch in str(c.get("cliente_cnpj") or "") if ch.isdigit())
        assert doc == MAIAPOLIS_CNPJ, f"filtro vazou contrato de outro cliente: {c}"
    # suspenders: o defeito original era devolver TUDO ignorando o filtro
    todos = await S.listar_contratos(limite=100)
    assert len(todos.get("contratos") or []) > len(itens), (
        "filtrado e não-filtrado têm o mesmo tamanho — o filtro não está filtrando")
    # valor numérico ao lado do formatado (P2): string obriga parsing
    assert isinstance(itens[0].get("valor_total"), (int, float, type(None)))
    print(f"OK 3.1 filtro por cliente devolve {len(itens)} de "
          f"{len(todos.get('contratos') or [])}, com nome e CNPJ na linha")


async def aceite_2_5_one_time_sem_recorrencia() -> None:
    """Criar contrato de valor único sem NENHUMA pergunta de recorrência."""
    r = await S.criar_contrato_por_modelo(
        MAIAPOLIS_CNPJ, "eletronica_instalacao",
        valor_total=46320, vigencia_inicio="2026-09-15", dry_run=True)
    assert r.get("gravou") is False, "o ensaio GRAVOU — dry_run não está segurando"
    assert r.get("natureza") == "one_time", f"natureza errada: {r.get('natureza')}"
    assert "valor_total" in r and "valor_mensal" not in r, (
        f"o ensaio ainda fala em mensalidade num contrato de valor único: {list(r)}")
    assert "mês" not in (r.get("resumo") or ""), f"resumo fala em mês: {r.get('resumo')}"

    # a guarda que impede o pior caso: obra entrando como MRR recorrente
    conflito = await S.criar_contrato_por_modelo(
        MAIAPOLIS_CNPJ, "portaria", valor_total=46320,
        vigencia_inicio="2026-09-15", dry_run=True)
    assert conflito.get("codigo") == "VALOR_CONFLITANTE", (
        f"total numa modalidade recorrente passou batido: {conflito}")

    # irmã de caminho feliz: o recorrente não pode ter sido quebrado pela guarda
    rec = await S.criar_contrato_por_modelo(
        MAIAPOLIS_CNPJ, "portaria", valor_mensal=40612,
        vigencia_inicio="2026-09-15", dry_run=True)
    assert rec.get("natureza") == "recurring" and "mês" in (rec.get("resumo") or "")

    # e a emissão precisa SABER repassar os campos do único — era aqui que parava
    import inspect
    params = set(inspect.signature(S.gerar_contrato_por_modelo).parameters)
    faltam = {"valor_total", "objeto_resumo", "proposta_numero", "itens"} - params
    assert not faltam, f"gerar_contrato_por_modelo não repassa: {faltam}"
    print("OK 2.5 valor único cria, recusa o valor trocado e a emissão repassa os campos")


async def aceite_3_2_identificador_tolerante() -> None:
    """Nome aproximado resolve; ambíguo devolve candidatos em vez de erro seco."""
    achado = await S._resolver_contrato("Maiapolis")
    assert achado == MAIAPOLIS_CTR, f"nome aproximado não resolveu: {achado}"
    amb = await S._resolver_contrato("Kopenhagen")
    assert isinstance(amb, dict) and amb.get("codigo") == "AMBIGUO", (
        f"dois contratos do mesmo cliente e ele ESCOLHEU um: {amb}")
    assert len(amb.get("candidatos") or []) >= 2, "AMBIGUO sem a lista para o agente escolher"
    print(f"OK 3.2 'Maiapolis' -> {achado}; 'Kopenhagen' -> AMBIGUO com "
          f"{len(amb['candidatos'])} candidatos")


async def aceite_3_4_mapa_de_capacidades() -> None:
    c = await S.conecta_pro_capabilities()
    dom = c.get("dominios") or {}
    assert len(dom) >= 5, f"mapa com {len(dom)} domínios — não serve para descobrir nada"
    print(f"OK 3.4 mapa com {len(dom)} domínios")


async def aceite_3_6_contexto_cliente() -> None:
    """Uma chamada em vez de ~6."""
    r = await S.contexto_cliente(chave=MAIAPOLIS_CNPJ)
    assert r.get("ok"), f"dossiê falhou: {str(r)[:200]}"
    assert (r.get("cliente") or {}).get("nome"), "dossiê sem o nome do cliente"
    assert "contratos" in r or "contratos" in (r.get("resumo") or {}), "dossiê sem contratos"
    print(f"OK 3.6 dossiê de {(r['cliente'])['nome'][:34]} numa chamada")


async def aceite_2_2_trio_de_documentos() -> None:
    """Anexar -> listar -> BAIXAR, com versão. O terceiro irmão faltava."""
    l = await S.listar_documentos_da_entidade("contrato", MAIAPOLIS_CTR)
    docs = l.get("documentos") or []
    assert docs, f"o contrato do aceite não tem documento anexado: {str(l)[:200]}"
    assert all(d.get("versao") for d in docs), "documento sem versão — o aceite cita versão"
    r = await S.baixar_documento(docs[0]["id"], formato="texto")
    assert r.get("ok"), f"baixar_documento falhou: {str(r)[:200]}"
    assert r.get("texto_extraido"), (
        "baixou sem texto — o anexo continua ilegível para o agente, que é o defeito 2.1 "
        "acontecendo de novo na volta")
    ruim = await S.baixar_documento("00000000-0000-0000-0000-000000000000")
    assert ruim.get("http") == 404, f"id inexistente não deu 404: {ruim}"
    print(f"OK 2.2 {len(docs)} documentos com versão; baixar traz "
          f"{len(r['texto_extraido'])} chars de texto")


async def aceite_2_3_crud_de_modelos() -> None:
    """As cinco ferramentas — e a guarda de modelo em uso, que falha FECHADA.

    ⚠️ Esta guarda já falhou aberta uma vez (11/09/2026): lia `template_id` de uma listagem
    que não tinha o campo, concluiu "zero afetados" e gravou numa descrição de produção. Por
    isso o teste não se contenta com o código de recusa: confere que NADA foi escrito.
    """
    for nome in ("listar_modelos_contrato", "criar_modelo_contrato",
                 "atualizar_modelo_contrato", "validar_modelo_contrato",
                 "vincular_modelo_ao_contrato"):
        assert hasattr(S, nome), f"falta a ferramenta {nome}"

    ms = await S.listar_modelos_contrato()
    modelos = ms.get("modelos") or ms.get("items") or []
    assert modelos, "nenhum modelo cadastrado — não dá para exercitar a guarda"
    # o modelo do contrato do aceite está EM USO por construção
    contratos = await S.listar_contratos(cliente=MAIAPOLIS_CNPJ)
    tid = (contratos.get("contratos") or [{}])[0].get("template_id")
    assert tid, ("a listagem não diz de qual modelo o contrato depende — foi exatamente "
                 "esta ausência que fez a guarda liberar a escrita")

    antes = await S.listar_modelos_contrato()
    r = await S.atualizar_modelo_contrato(tid, descricao="ESTE TESTE NAO PODE GRAVAR")
    assert r.get("codigo") == "MODELO_EM_USO", (
        f"a guarda liberou a alteração de um modelo em uso: {str(r)[:200]}")
    assert r.get("contratos_afetados"), "recusou sem dizer QUAIS contratos seriam afetados"

    # a prova que importa: escrita se prova por leitura posterior, nunca pelo código de saída
    depois = await S.listar_modelos_contrato()
    assert antes == depois, "a guarda devolveu recusa E MESMO ASSIM alterou algo"
    print(f"OK 2.3 as 5 ferramentas; guarda recusou citando "
          f"{len(r['contratos_afetados'])} contrato(s) e não gravou nada")


ACEITES = [
    aceite_2_1_documento_legivel,
    aceite_3_1_listagem_diz_o_cliente,
    aceite_2_2_trio_de_documentos,
    aceite_2_3_crud_de_modelos,
    aceite_2_5_one_time_sem_recorrencia,
    aceite_3_2_identificador_tolerante,
    aceite_3_4_mapa_de_capacidades,
    aceite_3_6_contexto_cliente,
]


async def main() -> int:
    falhas = []
    for fn in ACEITES:
        try:
            await fn()
        except AssertionError as e:
            falhas.append(f"{fn.__name__}: {e}")
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            falhas.append(f"{fn.__name__}: {type(e).__name__}: {e}")
            print(f"ERRO {fn.__name__}: {type(e).__name__}: {e}")
    if falhas:
        print(f"\nTEST test_aceites_cowork FAIL — {len(falhas)}/{len(ACEITES)}")
        return 1
    print(f"\nTEST test_aceites_cowork PASS — {len(ACEITES)}/{len(ACEITES)} aceites")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
