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
    # ⚠️ O contrato MUDOU em 11/09/2026 (§3.1): acima de 256 KB o base64 é omitido de
    # propósito, porque 469 KB estouravam a conversa. A regra que vale agora é "ou vem o
    # arquivo, ou vem o motivo de não ter vindo" — nunca sumir em silêncio.
    if not arq.get("base64"):
        assert r.get("aviso"), f"omitiu o arquivo sem dizer por quê: {str(r)[:200]}"
        forcado = await S.baixar_contrato_pdf(MAIAPOLIS_CTR, formato="base64",
                                              forcar_base64=True)
        assert (forcado.get("arquivo") or {}).get("base64"), (
            "acima do teto E o escape não traz o arquivo — ficou impossível baixar")
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

    # ⭐ O RAMO DA JANELA. Com 19 contratos de 19 ele nunca executa, então ficaria aqui sem
    # nunca ter rodado — e um ramo que gateia escrita e nunca rodou é promessa, não parede.
    # Simula o dia em que a coleção passar de 100: a guarda tem de recusar por não enxergar
    # o conjunto, em vez de concluir "ninguém usa" a partir da amostra.
    original = S.erp.get

    async def com_total_maior(path, params=None):
        d = await original(path, params=params)
        if path == "/crm/contracts" and isinstance(d, dict):
            d = {**d, "total": 340}
        return d

    S.erp.get = com_total_maior
    try:
        janela = await S.atualizar_modelo_contrato(tid, descricao="ESTE TESTE NAO PODE GRAVAR")
        assert janela.get("codigo") == "NAO_CONSIGO_MEDIR_O_USO", (
            f"a janela não alcançava o conjunto e ela decidiu assim mesmo: {str(janela)[:200]}")
    finally:
        S.erp.get = original
    assert await S.listar_modelos_contrato() == antes, "o ramo da janela gravou"
    print(f"OK 2.3 as 5 ferramentas; guarda recusou citando "
          f"{len(r['contratos_afetados'])} contrato(s) e não gravou nada")


async def aceite_2_1_todas_as_geradoras() -> None:
    """O aceite cita `baixar_contrato_pdf`, mas o item 2.1 diz **todas** as baixar_/gerar_.

    Eu tinha convertido 3 de 19 e declarado o item feito. Este teste mede a família inteira,
    não o caso que apareceu: ferramenta que devolve DOCUMENTO precisa aceitar `formato` e
    trazer texto; ferramenta que devolve JSON não precisa de nada disso.
    """
    import inspect
    import re

    todas = [n for n in dir(S)
             if (n.startswith("baixar_") or n.startswith("gerar_")) and callable(getattr(S, n))]
    mudas = []
    for n in todas:
        if "formato" in inspect.signature(getattr(S, n)).parameters:
            continue
        try:
            src = inspect.getsource(getattr(S, n))
        except Exception:  # noqa: BLE001
            continue
        if re.search(r"download_url|pdf_base64|_pdf_b64|_gerar_doc", src):
            mudas.append(n)
    assert not mudas, f"devolvem documento e não aceitam formato=: {mudas}"

    # e funciona de verdade, não só na assinatura
    r = await S._pdf_b64("/crm/reports/comercial/pdf", formato="base64", nome="rel.pdf")
    arq_r = r.get("arquivo") or {}
    assert arq_r.get("base64") or r.get("aviso"), (
        f"sem base64 e sem aviso — sumiu em silêncio: {list(r)}")
    assert r.get("texto_extraido"), "envelope sem texto — assinatura nova, comportamento velho"
    com = [n for n in todas if "formato" in inspect.signature(getattr(S, n)).parameters]
    print(f"OK 2.1 {len(com)}/{len(todas)} baixar_/gerar_ com formato; nenhuma geradora muda")


async def aceite_3_3_rede_de_protecao() -> None:
    """`dry_run` em TODA ferramenta de escrita — via `ensaiar`, que serve às 82 de uma vez.

    O aceite escrito cita idempotência ("duas chamadas com a mesma chave criam UM
    contrato"), e isso já existe em `criar_contrato_por_modelo`. O que faltava era a outra
    metade: ver o que a chamada FARIA antes de deixá-la gravar. Dar `dry_run` a 82
    assinaturas seria esquecer algumas — e a esquecida é justamente a que grava sem avisar.
    Por isso a interceptação fica no único ponto por onde o conector escreve.
    """
    r = await S.ensaiar("criar_cliente",
                        {"nome": "TESTE ENSAIO LTDA", "cnpj": "11222333000181"})
    assert r.get("ok"), f"o ensaio falhou: {str(r)[:200]}"
    assert r.get("gravou") is False
    escritas = r.get("escritas") or []
    assert escritas, "criar_cliente não registrou nenhuma escrita — a interceptação furou"
    assert any(e["metodo"] in ("POST", "PUT", "PATCH") for e in escritas), escritas
    assert all(e.get("rota") and "corpo" in e for e in escritas), (
        "escrita registrada sem rota ou sem corpo não deixa ninguém decidir nada")

    # ⭐ A prova que importa: o banco NÃO recebeu. Código de saída não é evidência de nada.
    todos = await S.erp.get("/crm/clients", params={"page_size": 200})
    achou = [c for c in (todos.get("items") or [])
             if "11222333000181" in str(c.get("cnpj") or c.get("document_number") or "")]
    assert not achou, f"O ENSAIO GRAVOU: {achou}"

    # irmã: ferramenta que só lê tem de dizer "nenhuma escrita", não ficar muda
    so_leitura = await S.ensaiar("listar_contratos", {"limite": 3})
    assert not (so_leitura.get("escritas") or []), so_leitura
    assert "Nenhuma escrita" in (so_leitura.get("resumo") or "")
    print(f"OK 3.3 ensaio mostra {len(escritas)} escrita(s) sem gravar; leitura pura diz que "
          f"não gravaria")


async def aceite_3_3_intercepta_os_QUATRO_metodos() -> None:
    """A promessa do `ensaiar` é "não grava". Eu só tinha provado isso para POST.

    ⭐ Havia 6 tools em DELETE, 6 em PUT e 2 em PATCH cuja interceptação eu nunca exercitei.
    O código diz `method != "GET"`, então "deveria" cobrir — e `deveria` é exatamente a
    palavra em que esta casa se queimou hoje: o `conecta-pro-d4` argumentou no commit que o
    hook `on_call_tool` era o ponto do desenho e nunca o executou.

    ⚠️ A sonda é uma rota INEXISTENTE de propósito: se a interceptação falhar, o custo é um
    404, nunca uma escrita. Trava não pode ser a coisa que quebra o que ela vigia.
    """
    import httpx

    saiu: list = []
    original = httpx.AsyncClient.request

    async def espia(self, method, url, **kw):  # noqa: ANN001
        saiu.append(f"{method} {url}")
        return await original(self, method, url, **kw)

    registro: list = []
    marca = S._ENSAIO.set(registro)
    httpx.AsyncClient.request = espia
    try:
        for metodo in ("POST", "PUT", "PATCH", "DELETE"):
            r = await S.erp.request(metodo, "/rota-inexistente-sonda", json={"x": 1})
            assert r.get("ensaio") is True, f"{metodo} NÃO foi interceptado: {r}"
            assert r.get("id") == "00000000-ensaio", (
                f"{metodo} devolveu resposta sem a marca de ensaio: {r}")
        # GET tem de PASSAR: é assim que o ensaio resolve cliente, modelo e valor
        await S.erp.request("GET", "/crm/contracts", params={"page_size": 1})
    finally:
        httpx.AsyncClient.request = original
        S._ENSAIO.reset(marca)

    # a prova real: NENHUMA escrita chegou à rede. Login é autenticação, não dado de negócio,
    # e sai por outro caminho (`_login` não passa por `request`) — por isso a auth não quebra
    # dentro do ensaio.
    escritas_na_rede = [x for x in saiu
                        if not x.startswith("GET") and "auth/login" not in x]
    assert not escritas_na_rede, f"O ENSAIO DEIXOU ESCRITA SAIR: {escritas_na_rede}"
    assert any(x.startswith("GET") for x in saiu), (
        "nem o GET saiu — o ensaio bloqueou a leitura e não resolveria nada")
    assert len(registro) == 4, f"registrou {len(registro)} escritas, esperava 4"
    print(f"OK 3.3 POST/PUT/PATCH/DELETE interceptados, GET passa, "
          f"{len(escritas_na_rede)} escritas na rede")


import identidade  # noqa: E402

TIMEOUT_ESPERADO = S.TIMEOUT_JOB


async def aceite_3_5_teto_real_do_job() -> None:
    """Dentro do job o httpx recebe 600s de verdade — não só `_EM_JOB is True`.

    ⭐ A versão anterior deste teste conferia a FLAG. Flag ligada é um proxy: ela prova que o
    contexto foi marcado, não que alguém leu a marca. Se o `timeout=` de alguma chamada
    tivesse ficado literal, a flag continuaria verde e a operação longa morreria aos 40s do
    mesmo jeito — com o agente achando que o job protegia.

    E o login fica em 20s nos dois: login lento é login quebrado, não operação longa.
    """
    import httpx

    visto: list = []
    original = httpx.AsyncClient.request

    async def espia(self, method, url, **kw):  # noqa: ANN001
        visto.append((method, str(url), kw.get("timeout")))
        return await original(self, method, url, **kw)

    async def roda() -> None:
        httpx.AsyncClient.request = espia
        # Este teste mede o TETO, não as paredes — e elas têm teste próprio acima. Sem
        # identidade o despacho é recusado antes de qualquer HTTP, e o teste mediria o
        # silêncio de uma recusa em vez do timeout. Desligar a parede aqui é explícito e
        # restaurado no `finally`; o que NÃO pode é o teste passar sem medir nada.
        modo_antes = identidade.MODO_AGENTE
        identidade.MODO_AGENTE = False
        identidade._TOKEN.set(None)
        try:
            await S.erp.get("/crm/contracts", params={"page_size": 1})
            fora = [t for m, u, t in visto if "contracts" in u]
            assert fora and fora[-1] == 40, f"fora do job o teto mudou: {fora}"
            logins = [t for m, u, t in visto if "login" in u]
            assert all(t == 20 for t in logins), f"o login saiu do teto de 20s: {logins}"

            visto.clear()
            j = await S.executar_em_segundo_plano("listar_contratos", {"limite": 1})
            for _ in range(40):
                if (await S.status_job(j["job_id"])).get("pronto"):
                    break
                await asyncio.sleep(0.2)
            dentro = [t for m, u, t in visto if "contracts" in u]
            assert dentro and dentro[-1] == TIMEOUT_ESPERADO, (
                f"dentro do job o teto continuou {dentro} — o job só mudaria a espera de "
                f"lugar e morreria no mesmo ponto")
            logins = [t for m, u, t in visto if "login" in u]
            assert all(t == 20 for t in logins), f"o login herdou o teto do job: {logins}"
        finally:
            httpx.AsyncClient.request = original
            identidade.MODO_AGENTE = modo_antes

    await roda()
    print(f"OK teto real: 40s fora, {TIMEOUT_ESPERADO}s dentro, login em 20s nos dois")



async def aceite_4x_request_id_em_toda_resposta() -> None:
    """`request_id` no caminho feliz E no erro, nas duas representações, e propagado ao ERP.

    Antes ele só existia quando o ERP devolvia `x-request-id` num erro — quase nunca, e
    nunca no sucesso. O que sobrava para investigar era "deu erro às 14h".

    ⭐ As DUAS representações: o `ToolResult` carrega o mesmo dado em `structured_content`
    (dict) e em `content` (texto JSON). Carimbar só uma faz os dois leitores discordarem.
    """
    import json as _json

    import httpx
    from fastmcp import Client

    vistos, enviados = [], []
    original = httpx.AsyncClient.request

    async def espia(self, method, url, **kw):  # noqa: ANN001
        enviados.append((kw.get("headers") or {}).get("X-Request-ID"))
        return await original(self, method, url, **kw)

    httpx.AsyncClient.request = espia
    try:
        async with Client(S.mcp) as c:
            feliz = await c.call_tool("listar_contratos", {"limite": 2})
            d = feliz.structured_content
            rid = d.get("request_id")
            assert rid and rid.startswith("req_"), f"sucesso sem request_id: {list(d)}"
            texto = _json.loads(feliz.content[0].text)
            assert texto.get("request_id") == rid, (
                f"dict e texto discordam: {rid} vs {texto.get('request_id')}")
            vistos.append(rid)

            ruim = await c.call_tool("baixar_contrato_pdf", {"contrato_id": "zzz-nao-existe"})
            rid2 = ruim.structured_content.get("request_id")
            assert rid2, "ERRO sem request_id — justamente a resposta que alguém vai rastrear"
            vistos.append(rid2)

            outra = await c.call_tool("ping_conecta_pro", {})
            vistos.append(outra.structured_content.get("request_id"))
    finally:
        httpx.AsyncClient.request = original

    assert len(set(vistos)) == len(vistos), f"ids repetidos entre chamadas: {vistos}"
    assert vistos[0] in enviados, (
        "o id NÃO foi ao ERP — seria um número que só existe deste lado, e "
        "consultar_auditoria(request_id=...) não teria o que achar")
    print(f"OK 4.x request_id em sucesso e erro, dict==texto, único por chamada, "
          f"propagado ao ERP")


async def aceite_4x_sandbox_grava_longe_da_producao() -> None:
    """`no_sandbox` executa DE VERDADE num ERP de mentira — e a produção não sente.

    Item 4: "hoje qualquer teste vira registro real (foi o caso do CTR-2026-00022)".
    `ensaiar` mostra o que faria; o sandbox faz, num banco descartável — é o que permite
    ver o que só existe DEPOIS de gravar (numeração, diagnóstico, pendências).
    """
    antes = await S.listar_contratos(limite=100)
    sb = await S.no_sandbox("listar_contratos", {"limite": 100})
    assert sb.get("ok") and sb.get("sandbox") is True, f"sandbox não respondeu: {str(sb)[:200]}"
    la = (sb.get("resultado") or {}).get("total")
    aqui = antes.get("total")
    assert la is not None and aqui is not None
    assert la != aqui, (
        f"sandbox e produção têm o MESMO total ({aqui}) — ou a rota não trocou de ambiente, "
        f"ou estou lendo o banco de produção achando que é o de ensaio")

    # o contexto não pode vazar: a chamada seguinte tem de voltar a produção
    assert S._SANDBOX.get() is False, "o contexto de sandbox vazou para fora da chamada"
    depois = await S.listar_contratos(limite=100)
    assert depois.get("total") == aqui, "produção mudou de tamanho depois do sandbox"

    # As paredes valem igual lá: sandbox muda ONDE, não O QUÊ.
    #
    # ⚠️ A parede de `propose` só existe em MODO_AGENTE — este conector é o PÚBLICO, onde
    # nem a chamada direta passa por ela. Cobrar recusa aqui seria exigir do sandbox uma
    # rigidez que a porta da frente não tem, e o teste ficaria vermelho sobre um acerto.
    # Por isso ligo o modo explicitamente para medir a parede, e restauro depois.
    import gate_propose

    propose = next((n for n, c in __import__("tool_risk_manifest").TOOL_RISK.items()
                    if c == "propose" and hasattr(S, n)), None)
    assert propose, "nenhuma tool propose — não dá para provar esta parede"
    modo_antes = gate_propose.MODO_AGENTE
    gate_propose.MODO_AGENTE = True
    try:
        r = await S.no_sandbox(propose, {})
    finally:
        gate_propose.MODO_AGENTE = modo_antes
    assert r.get("codigo") == "PRECISA_APROVACAO", (
        f"`{propose}` executou no sandbox com a parede LIGADA — vira caminho alternativo "
        f"para aprovação humana: {r}")

    # ensaio e sandbox são promessas opostas; aninhar tem de recusar
    marca = S._ENSAIO.set([])
    try:
        conflito = await S.no_sandbox("listar_contratos", {"limite": 1})
    finally:
        S._ENSAIO.reset(marca)
    assert conflito.get("codigo") == "ENSAIO_E_SANDBOX", (
        f"um ensaio caiu no sandbox e gravaria: {conflito}")
    print(f"OK 4.x sandbox com {la} contratos × produção com {aqui}; paredes valem lá; "
          f"ensaio aninhado recusado")


async def aceite_auditoria_efeito_externo() -> None:
    """§1.1 — o P0. Aprovação humana em QUALQUER modo, nos QUATRO caminhos.

    `enviar_link_assinatura` ESTAVA classificada `propose` e mesmo assim chegava ao ERP no
    conector público, porque a parede só era instalada em modo agente. Teria mandado o
    e-mail para a síndica do Maiápolis.
    """
    import gate_propose as G

    assert G.EFEITO_EXTERNO, "a lista de efeito externo sumiu"
    alvo = "enviar_link_assinatura"
    assert G.precisa_aprovacao(alvo), f"`{alvo}` passaria em modo {G.MODO_AGENTE=}"
    for caminho, fn in (("ensaiar", S.ensaiar),
                        ("no_sandbox", S.no_sandbox),
                        ("segundo_plano", S.executar_em_segundo_plano)):
        r = await fn(alvo, {"contrato": "CTR-2026-00022"})
        assert r.get("codigo") == "PRECISA_APROVACAO", f"{caminho} deixou passar: {r}"
    assert G.efeito_externo(alvo), "a recusa não diz o que sairia da empresa"
    print(f"OK §1.1 {len(G.EFEITO_EXTERNO)} ações externas barradas nos 3 despachantes "
          f"(+ middleware na chamada direta)")


async def aceite_auditoria_erro_util() -> None:
    """§1.2 e §2.2 — argumento faltando é 422, e nada sai sem envelope nem `request_id`."""
    def falta(contrato):  # noqa: ANN001, ARG001
        pass

    try:
        falta()
    except TypeError as e:
        env = S.erro_envelope(e)
    assert env["codigo"] == "PARAMETRO_OBRIGATORIO" and env["http"] == 422, env
    assert env["campos_faltantes"] == ["contrato"], env
    assert "positional" not in env["mensagem"], f"a assinatura da função vazou: {env}"

    r = await S.obter_contrato("ID-QUE-NAO-EXISTE-ZZZ")
    assert r.get("http") == 404, f"id inválido devia ser 404: {r}"
    print("OK §1.2/§2.2 argumento faltando = 422 sem vazar assinatura; id inválido = 404")


async def aceite_auditoria_contrato_com_itens() -> None:
    """§2.2 — `obter_contrato` quebrava em TODO contrato com item (5 de 19).

    O enum `ServiceType` declarava `security`/`remote_gatehouse` e a tabela guardava
    `manutencao_cftv`/`maodeobra`/`entrada`/`parcela` — interseção ZERO. Os 14 que
    "passavam" passavam por estarem vazios.
    """
    r = await S.obter_contrato(MAIAPOLIS_CTR)
    assert r.get("contract_number") == MAIAPOLIS_CTR, f"não abriu: {str(r)[:160]}"
    itens = r.get("items") or []
    assert itens, "o contrato do aceite tem 4 itens e vieram 0 — a leitura regrediu"
    tipos = {str(i.get("service_type")) for i in itens}
    assert tipos & {"entrada", "parcela", "retida"}, (
        f"o papel da parcela sumiu de service_type: {tipos}")
    print(f"OK §2.2 contrato com {len(itens)} itens abre; papéis {sorted(tipos)}")


async def aceite_auditoria_teto_de_conversa() -> None:
    """§3.1 — 469 KB viravam 651 mil chars e estouravam a sessão."""
    import json as _json

    r = await S.baixar_contrato_pdf(MAIAPOLIS_CTR, formato="base64")
    tamanho = len(_json.dumps(r, ensure_ascii=False))
    assert tamanho < 60_000, f"a resposta voltou a inchar: {tamanho} chars"
    assert not (r.get("arquivo") or {}).get("base64"), "base64 embutido acima do teto"
    assert r.get("texto_extraido"), "cortou o base64 E o texto — sobrou nada para conferir"
    assert r.get("aviso"), "omitiu o arquivo sem dizer por quê"

    forcado = await S.baixar_contrato_pdf(MAIAPOLIS_CTR, formato="base64", forcar_base64=True)
    assert (forcado.get("arquivo") or {}).get("base64"), "o escape consciente sumiu"
    print(f"OK §3.1 resposta em {tamanho} chars com texto íntegro; forcar_base64 ainda traz")


async def aceite_auditoria_texto_fiel() -> None:
    """§3.3 — `[[...]]` sobrevivia no texto e o agente auditava documento que não existe."""
    import re

    t = (await S.baixar_contrato_pdf(MAIAPOLIS_CTR, formato="texto")).get("texto_extraido") or ""
    sobrou = re.findall(r"\[\[[A-Z_]+\]\]", t)
    assert not sobrou, f"token não resolvido no texto: {sobrou}"
    assert "COMPOSIÇÃO DO VALOR" in t, "a tabela de composição não virou texto"
    assert "ASSINATURAS" in t, "o bloco de assinaturas não virou texto"
    # o que se confere antes de mandar ao cliente: a soma e o endereço
    assert "46.320,00" in t, "o total da composição sumiu do texto"
    assert "Rodovia Manoel Urbano" in t, "o endereço do contratante voltou a sair truncado"
    print("OK §3.3 texto fiel: composição, assinaturas, total e endereço completo")


async def aceite_auditoria_listagem_de_clientes() -> None:
    """§3.5 — era a única listagem fora do envelope, e buscava só por nome."""
    por_nome = await S.listar_clientes(busca="Maiapolis")
    assert por_nome.get("ok") and por_nome.get("total") is not None, por_nome
    por_cnpj = await S.listar_clientes(busca=MAIAPOLIS_CNPJ)
    assert por_cnpj.get("total") == por_nome.get("total"), (
        f"buscar por CNPJ não acha o que buscar por nome acha: "
        f"{por_cnpj.get('total')} vs {por_nome.get('total')}")
    todos = await S.listar_clientes()
    assert todos.get("total", 0) > por_nome.get("total", 0), "o filtro não filtra"
    linha = (por_nome.get("clientes") or [{}])[0]
    assert isinstance(linha.get("mrr"), (int, float, type(None))), "mrr voltou a ser string"
    print(f"OK §3.5 envelope com total; CNPJ e nome acham o mesmo ({por_nome['total']} de "
          f"{todos['total']})")


async def aceite_auditoria_sandbox_emite() -> None:
    """§3.2 — o fluxo comercial não rodava no sandbox por falta de modelo."""
    r = await S.no_sandbox("listar_modelos_contrato", {})
    modelos = (r.get("resultado") or {}).get("modelos") or (r.get("resultado") or {}).get("items") or []
    tipos = {str(m.get("tipo") or m.get("service_type")) for m in modelos}
    faltam = {"eletronica_servico_unico", "portaria_mao_de_obra", "manutencao_cftv"} - tipos
    assert not faltam, (
        f"o sandbox não tem os modelos comerciais: {faltam}. "
        f"Rode scripts/refrescar_sandbox.sh — sem eles o passo que justifica o sandbox "
        f"(criar → emitir → conferir) não roda lá.")
    print(f"OK §3.2 sandbox com {len(tipos)} tipos de modelo, comerciais inclusos")


ACEITES = [
    aceite_auditoria_efeito_externo,
    aceite_auditoria_erro_util,
    aceite_auditoria_contrato_com_itens,
    aceite_auditoria_teto_de_conversa,
    aceite_auditoria_texto_fiel,
    aceite_auditoria_listagem_de_clientes,
    aceite_auditoria_sandbox_emite,
    aceite_2_1_documento_legivel,
    aceite_2_1_todas_as_geradoras,
    aceite_3_1_listagem_diz_o_cliente,
    aceite_2_2_trio_de_documentos,
    aceite_2_3_crud_de_modelos,
    aceite_2_5_one_time_sem_recorrencia,
    aceite_3_2_identificador_tolerante,
    aceite_3_3_rede_de_protecao,
    aceite_3_3_intercepta_os_QUATRO_metodos,
    aceite_3_5_teto_real_do_job,
    aceite_3_4_mapa_de_capacidades,
    aceite_3_6_contexto_cliente,
    aceite_4x_request_id_em_toda_resposta,
    aceite_4x_sandbox_grava_longe_da_producao,
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
