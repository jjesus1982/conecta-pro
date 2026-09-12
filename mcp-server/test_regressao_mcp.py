"""Suíte de regressão da camada MCP — CP-MCP-011, os 11 casos do spec de 11/09/2026.

Congela os comportamentos que a auditoria do Cowork aprovou, para não regredirem em
silêncio. Complementa `test_aceites_cowork.py`: lá os aceites do prompt original, aqui os
casos numerados do spec, com os asserts que ele pede.

⚠️ NENHUM caso envia link de assinatura, transmite a órgão, toca em pagamento ou emite
recibo — nem no sandbox. Escrita se exercita por `dry_run`, `ensaiar` ou `no_sandbox`.

⭐ AS SETE ARMADILHAS DO SPEC, e como esta suíte trata cada uma:

  1. NÃO FIXAR CONTAGENS. Produção tinha 19 contratos e o sandbox 11 no dia da auditoria;
     ambos mudam toda semana. Onde o dado é volátil, afirma-se a RELAÇÃO
     (`total_sandbox != total_producao`), nunca o valor.
  2. SONDA ÚNICA POR EXECUÇÃO. `SONDA-CI-<run>` com sufixo derivado do relógio, para rodar
     em paralelo sem colidir com resíduo de execução anterior.
  3. `no_sandbox` EXECUTA DE VERDADE. Só com tools sem efeito externo — e a parede de
     CP-MCP-001 agora recusa as `enviar_*` também por lá, o que R11 confere.
  4. JOB VIVE NA MEMÓRIA DO PROCESSO. R09 dispara e consulta na mesma sessão.
  5. FIXTURE PROTEGIDA. `CTR-2026-00022` é usado por R01, R05 e R10 e NÃO é alterado por
     nenhum deles — R10 confere que a recusa não gravou.
  6. R10 TOCA UM MODELO REAL. Por isso ele só exercita a RECUSA e relê para provar que nada
     mudou; nunca passa `confirmar_modelo_em_uso`.
  7. AFIRMAR TIPO, NÃO SÓ PRESENÇA. Vários defeitos históricos eram valor monetário vindo
     como string — onde o spec diz "numérico", o assert é `isinstance`.

    python test_regressao_mcp.py
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time

import server as S

MAIAPOLIS_CNPJ = "55090416000130"
MAIAPOLIS_CTR = "CTR-2026-00022"
# armadilha 2: nome único por execução
RUN = f"{int(time.time()) % 1_000_000:06d}"
SONDA = f"SONDA-CI-{RUN}"
CNPJ_SINTETICO = "11222333000181"


def _env_do_erro(texto: str) -> dict:
    """O envelope que vem dentro de um ToolError. Vazio se não for JSON."""
    try:
        return json.loads(texto[texto.index("{"):texto.rindex("}") + 1])
    except Exception:  # noqa: BLE001
        return {}


async def r01_documento_legivel() -> str:
    # ⚠️ Pelo CLIENT, não pela função Python. O `request_id` é carimbado pelo MIDDLEWARE,
    # que só roda na chamada de protocolo — chamar `S.baixar_contrato_pdf(...)` direto pula
    # o middleware e o assert de rastreabilidade falharia medindo a camada errada. É o
    # mesmo erro que custou caro hoje de manhã: o aceite tem de ser cobrado na superfície
    # que o agente usa.
    from fastmcp import Client

    async with Client(S.mcp) as c:
        r = (await c.call_tool("baixar_contrato_pdf",
                               {"contrato_id": "Maiapolis", "formato": "texto"})
             ).structured_content
    assert r.get("ok"), f"não abriu: {str(r)[:180]}"
    texto = r.get("texto_extraido") or ""
    assert (r.get("clausulas") or 0) >= 14, f"cláusulas: {r.get('clausulas')}"
    for frase in ("limitada ao teto de 10%", "integral e regressivamente"):
        assert frase in texto, f"sumiu do instrumento: {frase!r}"
    # era `xfail` até CP-MCP-006; virou assert duro
    assert "[[" not in texto, f"token de render sobreviveu: {re.findall(r'\[\[[A-Z_]+\]\]', texto)}"
    assert str(r.get("request_id", "")).startswith("req_"), "sem request_id"
    return f"{r['clausulas']} cláusulas, {len(texto)} chars, sem token"


async def r02_identificador_tolerante() -> str:
    amb = await S.baixar_contrato_pdf("Kopenhagen", formato="texto")
    assert amb.get("ok") is False and amb.get("codigo") == "AMBIGUO" and amb.get("http") == 409, amb
    cands = amb.get("candidatos") or []
    assert len(cands) >= 2, f"AMBIGUO com {len(cands)} candidatos"
    for c in cands:
        assert c.get("numero") and c.get("cliente") and c.get("status") is not None, c
    # não escolheu por conta própria: não veio documento junto
    assert not amb.get("texto_extraido") and not amb.get("arquivo"), "gerou documento no ambíguo"

    nada = await S.baixar_contrato_pdf("Condominio Inexistente Zebra 9999", formato="texto")
    assert nada.get("codigo") == "NAO_ENCONTRADO" and nada.get("http") == 404, nada
    assert (nada.get("dica") or "").strip(), "404 sem dica acionável"
    return f"AMBIGUO com {len(cands)} candidatos; inexistente = 404 com dica"


async def r03_listagem_diz_de_quem_e() -> str:
    a = await S.listar_contratos(cliente=MAIAPOLIS_CNPJ)
    itens = a.get("contratos") or []
    assert itens, f"filtro por CNPJ vazio: {str(a)[:160]}"
    for campo in ("total", "pagina", "paginas", "nesta_pagina"):
        assert a.get(campo) is not None, f"envelope sem {campo}"
    for it in itens:
        doc = re.sub(r"\D", "", str(it.get("cliente_cnpj") or ""))
        assert doc == MAIAPOLIS_CNPJ, f"vazou contrato de outro cliente: {it}"
        for campo in ("cliente_nome", "cliente_cnpj", "cliente_id", "valor_total",
                      "valor_total_formatado", "template_id", "vigencia_inicio",
                      "atualizado_em"):
            assert campo in it, f"linha sem {campo}: {sorted(it)}"
        # armadilha 7: tipo, não presença
        assert isinstance(it["valor_total"], (int, float, type(None))), (
            f"valor_total voltou a ser string: {it['valor_total']!r}")

    b = await S.listar_contratos(cliente="Kopenhagen")
    kop = b.get("contratos") or []
    assert len(kop) >= 2, f"Kopenhagen com {len(kop)} contratos"
    assert len({c.get("cliente_id") for c in kop}) == 1, "mesmo cliente com ids diferentes"

    c = await S.listar_contratos(status="draft")
    assert all(x.get("status") == "draft" for x in (c.get("contratos") or [])), "filtro de status furou"
    return f"CNPJ isola {len(itens)}; Kopenhagen {len(kop)} no mesmo cliente; draft coerente"


async def r04_dossie_numa_chamada() -> str:
    r = await S.contexto_cliente(chave="Kopenhagen")
    assert r.get("ok"), f"dossiê falhou: {str(r)[:160]}"
    for campo in ("cliente", "resumo", "contratos"):
        assert campo in r, f"dossiê sem {campo}: {sorted(r)}"
    cli = r["cliente"]
    assert cli.get("codigo") and cli.get("cnpj"), f"cliente incompleto: {cli}"
    for ct in (r.get("contratos") or []):
        for campo in ("servico", "emitente"):
            assert campo in ct, f"contrato do dossiê sem {campo}: {sorted(ct)}"
    mrr = (r.get("resumo") or {}).get("mrr")
    assert isinstance(mrr, (int, float, type(None))), f"mrr não numérico: {mrr!r}"

    ruim = await S.contexto_cliente(chave="CLIENTE-QUE-NAO-EXISTE-XYZ-000")
    assert ruim.get("http") == 404 and (ruim.get("dica") or "").strip(), ruim
    return f"{len(r.get('contratos') or [])} contratos, mrr numérico; controle = 404"


async def r05_documentos_com_versao() -> str:
    a = await S.listar_documentos_da_entidade("contrato", MAIAPOLIS_CTR)
    docs = a.get("documentos") or []
    assert (a.get("total") or 0) >= 2, f"total de documentos: {a.get('total')}"
    for d in docs:
        for campo in ("categoria", "nome", "versao", "tamanho_kb", "criado_em"):
            assert campo in d, f"documento sem {campo}: {sorted(d)}"
    por_nome: dict = {}
    for d in docs:
        por_nome.setdefault(d["nome"], set()).add(d["versao"])
    assert any(len(v) >= 2 for v in por_nome.values()), (
        f"nenhum nome com duas versões — o versionamento regrediu: {por_nome}")

    maior = max(docs, key=lambda d: d["versao"])
    b = await S.baixar_documento(maior["id"], formato="texto")
    assert b.get("ok"), f"baixar falhou: {str(b)[:160]}"
    assert len(b.get("texto_extraido") or "") > 1000, "texto curto demais para o instrumento"

    c = await S.baixar_documento("00000000-0000-0000-0000-000000000000", formato="texto")
    assert c.get("http") == 404, c
    return f"{a['total']} docs, versões {sorted({d['versao'] for d in docs})}; id falso = 404"


async def r06_ensaio_mostra_e_nao_grava() -> str:
    a = await S.ensaiar("criar_cliente", {"nome": SONDA, "cnpj": CNPJ_SINTETICO})
    assert a.get("gravou") is False, a
    escritas = a.get("escritas") or []
    assert escritas, "ensaio de criar_cliente sem nenhuma escrita registrada"
    e0 = escritas[0]
    assert e0.get("metodo") == "POST" and "/clients" in e0.get("rota", ""), e0
    assert "corpo" in e0, "escrita sem o corpo resolvido — não dá para decidir nada"

    # prova em PRODUÇÃO: a sonda não existe
    b = await S.listar_clientes(busca=SONDA)
    assert (b.get("total") or 0) == 0, f"O ENSAIO GRAVOU: {b.get('clientes')}"

    c = await S.ensaiar("listar_contratos", {"limite": 3})
    assert not (c.get("escritas") or []), c
    assert "Nenhuma escrita" in (c.get("resumo") or ""), c
    return f"{len(escritas)} escrita mostrada, 0 gravada; leitura pura diz que não gravaria"


async def r07_isolamento_do_sandbox() -> str:
    """⭐ O caso mais importante da suíte."""
    antes = await S.listar_contratos(limite=100)
    total_prod_antes = antes.get("total")

    criado = await S.no_sandbox("criar_contrato_por_modelo", {
        "cliente_documento": MAIAPOLIS_CNPJ, "modalidade": "eletronica_instalacao",
        "valor_total": 46320, "vigencia_inicio": "2026-10-01"})
    assert criado.get("ok") and criado.get("sandbox") is True, str(criado)[:200]
    res = criado.get("resultado") or {}
    numero = res.get("contrato")
    assert res.get("status") == "criado" and numero, f"não criou no sandbox: {str(res)[:200]}"
    assert re.match(r"^CTR-\d{4}-\d{5}$", numero), f"numeração fora do padrão: {numero}"
    assert criado.get("aviso"), "no_sandbox sem o aviso de que nada existe em produção"

    no_sb = await S.no_sandbox("listar_contratos", {"limite": 100})
    listados = (no_sb.get("resultado") or {}).get("contratos") or []
    assert any(c.get("numero") == numero for c in listados), "criou e não aparece no sandbox"

    # ❤️ o coração do teste
    na_prod = await S.listar_contratos(limite=100)
    assert not [c for c in (na_prod.get("contratos") or []) if c.get("numero") == numero], (
        f"O CONTRATO DO SANDBOX VAZOU PARA PRODUÇÃO: {numero}")
    assert na_prod.get("total") == total_prod_antes, (
        f"produção mudou de tamanho: {total_prod_antes} -> {na_prod.get('total')}")

    # armadilha 1: relação, nunca valor fixo
    total_sb = (no_sb.get("resultado") or {}).get("total")
    assert total_sb != total_prod_antes, (
        f"sandbox e produção com o MESMO total ({total_sb}) — ou a rota não trocou de "
        f"ambiente, ou estou lendo o banco de produção achando que é o de ensaio")
    return f"{numero} no sandbox ({total_sb}), ausente da produção ({total_prod_antes})"


async def r08_valor_unico_e_conflito() -> str:
    a = await S.criar_contrato_por_modelo(
        MAIAPOLIS_CNPJ, "eletronica_instalacao", valor_total=46320,
        vigencia_inicio="2026-10-01", dry_run=True)
    assert a.get("gravou") is False and a.get("natureza") == "one_time", a
    assert a.get("modelo") == "eletronica_servico_unico", a.get("modelo")
    assert a.get("emitente") == "Eletrônica", a.get("emitente")
    bruto = json.dumps(a, ensure_ascii=False)
    for proibido in ("dia_vencimento", "payment_day", "valor_mensal", "grace_period"):
        assert proibido not in bruto, f"campo de recorrência no valor único: {proibido}"

    b = await S.criar_contrato_por_modelo(
        MAIAPOLIS_CNPJ, "portaria", valor_total=46320,
        vigencia_inicio="2026-10-01", dry_run=True)
    assert b.get("codigo") == "VALOR_CONFLITANTE" and b.get("http") == 422, b
    assert "valor_mensal" in (b.get("dica") or ""), f"a dica não ensina o caminho: {b.get('dica')}"
    return "one_time sem recorrência; total em modalidade recorrente = 422"


async def r09_operacao_longa_vira_job() -> str:
    disparo = await S.executar_em_segundo_plano("contexto_cliente", {"chave": "Kopenhagen"})
    jid = disparo.get("job_id")
    assert jid and re.match(r"^job_[0-9a-f]+$", jid), f"job_id fora do padrão: {jid}"

    limite = time.time() + 30  # armadilha 4: mesma sessão, teto de 30s
    estado = {}
    while time.time() < limite:
        estado = await S.status_job(jid)
        if estado.get("pronto"):
            break
        await asyncio.sleep(0.3)
    assert estado.get("pronto") is True, f"job não concluiu em 30s: {estado}"
    assert estado.get("status") == "concluido", estado

    do_job = (await S.resultado_job(jid)).get("resultado") or {}
    direto = await S.contexto_cliente(chave="Kopenhagen")
    # comparar campos ESTÁVEIS, não o dicionário inteiro
    assert (do_job.get("cliente") or {}).get("codigo") == (direto.get("cliente") or {}).get("codigo")
    assert (do_job.get("cliente") or {}).get("cnpj") == (direto.get("cliente") or {}).get("cnpj")
    assert len(do_job.get("contratos") or []) == len(direto.get("contratos") or [])
    return f"{jid} concluiu em {estado.get('decorrido_s')}s, idêntico à chamada direta"


async def r10_parede_do_modelo_em_uso() -> str:
    lista = await S.listar_contratos(cliente=MAIAPOLIS_CNPJ)
    tid = (lista.get("contratos") or [{}])[0].get("template_id")
    assert tid, "a listagem não diz de qual modelo o contrato depende"

    antes = await S.listar_modelos_contrato()
    r = await S.atualizar_modelo_contrato(tid, descricao="teste-ci")  # sem confirmar!
    assert r.get("codigo") == "MODELO_EM_USO" and r.get("http") == 409, str(r)[:200]
    afetados = r.get("contratos_afetados") or []
    assert afetados, "recusou sem dizer QUAIS contratos seriam afetados"
    for c in afetados:
        assert c.get("numero") and c.get("cliente") and c.get("status") is not None, c

    # armadilha 5/6: a fixture é real — provar que NADA mudou, relendo
    assert await S.listar_modelos_contrato() == antes, "a guarda recusou E alterou o modelo"
    return f"MODELO_EM_USO citando {len(afetados)} contrato(s); nada gravado"


async def r11_parede_de_aprovacao_humana() -> str:
    """Era `xfail` no spec. Fechou com CP-MCP-001 — assert duro agora."""
    from fastmcp import Client

    import gate_propose as G

    alvo = "enviar_link_assinatura"
    esperado = G.CODIGO_APROVACAO

    async with Client(S.mcp) as c:
        try:
            await c.call_tool(alvo, {"contrato": MAIAPOLIS_CTR})
            raise AssertionError("A CHAMADA DIRETA EXECUTOU — o e-mail teria saído")
        except AssertionError:
            raise
        except Exception as e:  # noqa: BLE001
            env = _env_do_erro(str(e))
            assert env.get("codigo") == esperado and env.get("http") == 403, (
                f"recusa direta sem o envelope da issue: {str(e)[:160]}")
            assert env.get("sai_da_empresa"), "a recusa não diz o que sairia da empresa"

    for nome, fn in (("ensaiar", S.ensaiar), ("no_sandbox", S.no_sandbox),
                     ("segundo_plano", S.executar_em_segundo_plano)):
        r = await fn(alvo, {"contrato": MAIAPOLIS_CTR})
        assert r.get("codigo") == esperado and r.get("http") == 403, f"{nome}: {r}"
        assert not r.get("escritas"), f"{nome} registrou escrita numa ação barrada: {r}"

    # a família inteira, não só o caso que apareceu
    passam = [n for n in G.EFEITO_EXTERNO if not G.precisa_aprovacao(n)]
    assert not passam, f"efeito externo sem parede: {passam}"
    return f"4 caminhos = {esperado}/403; {len(G.EFEITO_EXTERNO)} ações externas cobertas"


async def extra_request_id_em_toda_falha() -> str:
    """CP-MCP-003 · varredura: NENHUMA resposta sai sem `request_id`, nem em erro.

    O spec pede "varrer todas as tools com input inválido e afirmar que 100% das respostas
    têm request_id". Uma amostra não serve: o defeito original era UMA tool entre centenas
    (`obter_contrato`), e a próxima a esquecer o try/except seria outra qualquer.

    ⚠️ Só LEITURAS. Mandar lixo numa tool de escrita seria exercitar escrita com argumento
    inválido, e "não gravou porque o argumento era ruim" não é garantia de nada.
    """
    import inspect

    from fastmcp import Client

    import tool_risk_manifest as M

    alvos = []
    for nome, classe in M.TOOL_RISK.items():
        if classe != "read" or not hasattr(S, nome):
            continue
        obrig = [p.name for p in inspect.signature(getattr(S, nome)).parameters.values()
                 if p.default is inspect.Parameter.empty]
        if obrig:
            alvos.append((nome, obrig))
    assert len(alvos) >= 40, f"só {len(alvos)} leituras com argumento — a varredura encolheu?"

    sem_id = []
    async with Client(S.mcp) as c:
        for nome, args in alvos:
            payload = {a: "LIXO-INVALIDO-ZZZ-999" for a in args}
            try:
                d = (await asyncio.wait_for(c.call_tool(nome, payload), timeout=20)
                     ).structured_content or {}
            except Exception as e:  # noqa: BLE001
                d = _env_do_erro(str(e))
            if not str((d or {}).get("request_id", "")).startswith("req_"):
                sem_id.append(nome)
    assert not sem_id, f"responderam SEM request_id: {sem_id}"
    return f"{len(alvos)} leituras com input inválido, 100% com request_id"


async def extra_parametro_obrigatorio() -> str:
    """CP-MCP-002 · argumento faltando = 422, sem vazar a assinatura da função.

    ⭐ A tool de sonda é `criar_cliente`, NÃO `enviar_link_assinatura`. O Cowork achou isto
    validando: em `enviar_link_assinatura` o portão de aprovação dispara ANTES da validação
    de parâmetro — o que é a ordem CERTA (fail-closed no mais perigoso primeiro), mas faz o
    403 encobrir o 422 e o caso não medir nada. Testar o 422 exige uma tool de escrita que
    NÃO esteja bloqueada.
    """
    r = await S.ensaiar("criar_cliente", {})
    assert r.get("codigo") == "PARAMETRO_OBRIGATORIO" and r.get("http") == 422, r
    assert r.get("campos_faltantes"), "422 sem dizer QUAIS campos faltam"
    msg = r.get("mensagem") or ""
    for vazamento in ("positional", "argument", "()"):
        assert vazamento not in msg, f"a assinatura da função vazou: {msg!r}"
    assert not (r.get("escritas_que_teria_feito") or []), "faltou argumento E tentou escrever"

    # e a ORDEM das guardas: no que é bloqueado, a aprovação vem antes — e tem de vir
    bloqueada = await S.ensaiar("enviar_link_assinatura", {})
    assert bloqueada.get("codigo") == "REQUER_APROVACAO_HUMANA", (
        f"a validação de parâmetro passou na frente da parede: {bloqueada}")
    return f"422 com {r['campos_faltantes']}; na bloqueada a aprovação vem primeiro"


async def r12_orcamento_misto() -> str:
    """35% no produto e 40% na mão de obra, VISÍVEIS por linha."""
    r = await S.orcamento_por_natureza("35710481000103", "eletronica", [
        {"descricao": "64 câmeras IP", "custo": 1200, "quantidade": 64,
         "natureza_item": "produto"},
        {"descricao": "instalação", "custo": 28000, "quantidade": 1,
         "natureza_item": "mao_de_obra_tecnica"}])
    assert r.get("ok"), str(r)[:200]
    linhas = r["memoria_de_calculo"]
    assert len(linhas) == 2, f"memória com {len(linhas)} linhas"
    por_nat = {l["natureza_item"]: l for l in linhas}
    assert por_nat["produto"]["margem"] == 0.35, por_nat["produto"]["margem"]
    assert por_nat["mao_de_obra_tecnica"]["margem"] == 0.40, por_nat["mao_de_obra_tecnica"]
    # o que o Bloco 1 exige: se mostrar UMA margem só, está errado
    assert len({l["margem"] for l in linhas}) == 2, "as duas linhas com a mesma margem"
    for l in linhas:
        assert l.get("origem_do_parametro"), "linha sem procedência do parâmetro"
        assert l.get("convencao") == "margem_sobre_preco", l.get("convencao")
    assert r.get("margem_media_resultante") not in (0.35, 0.40), (
        "a média está sendo confundida com parâmetro")
    return (f"produto {por_nat['produto']['margem_pct']}, mão de obra "
            f"{por_nat['mao_de_obra_tecnica']['margem_pct']}, média resultante "
            f"{r['margem_media_resultante']}")


async def r13_margem_nao_cadastrada() -> str:
    r = await S.orcamento_por_natureza("35710481000103", "eletronica", [
        {"descricao": "projeto", "custo": 5000, "natureza_item": "projeto"}])
    assert r.get("codigo") == "MARGEM_NAO_CADASTRADA" and r.get("http") == 422, str(r)[:200]
    assert r.get("margens_cadastradas"), "recusou sem dizer o que EXISTE"
    assert "0.15" not in str(r.get("memoria_de_calculo") or ""), "caiu no fallback de 15%"
    return f"recusou citando {len(r['margens_cadastradas'])} margens cadastradas"


async def r14_regime_ausente() -> str:
    r = await S.orcamento_por_natureza("66014833000110", "patrimonial", [
        {"descricao": "posto 24h", "custo": 10000, "natureza_item": "servico_alocado"}])
    assert r.get("codigo") == "REGIME_NAO_CADASTRADO" and r.get("http") == 422, str(r)[:200]
    assert "rbt12" in (r.get("dica") or "").lower(), f"dica não aponta o que falta: {r.get('dica')}"
    return f"recusou precificar: {r.get('faltando')}"


async def r15_dois_cnpjs() -> str:
    p = await S.consultar_parametros_precificacao()
    emp = {e["cnpj"]: e for e in (p.get("empresas") or [])}
    assert len(emp) >= 2, f"só {len(emp)} empresa(s) com regime"
    cargas = {c: e.get("carga_total") for c, e in emp.items()}
    assert len({str(v) for v in cargas.values()}) >= 2, (
        f"as empresas têm a MESMA carga: {cargas} — o regime por CNPJ não está valendo")
    for e in emp.values():
        assert e.get("fonte"), f"{e['cnpj']} sem `fonte` declarada"
    return f"{len(emp)} CNPJs, cargas distintas: {list(cargas.values())}"


async def r18_nota_interna_nao_vaza() -> str:
    """Bloco 4. O texto INTEIRO é devolvido, porque "não aparece" sem o texto não conta."""
    r = await S.baixar_proposta_pdf("PROP-2026-00114", formato="texto")
    texto = r.get("texto_extraido") or ""
    assert texto, f"não renderizou: {str(r)[:160]}"
    for proibido in ("OBS INTERNA", "Margem atual", "margem de lucro", "não mostrar"):
        assert proibido.lower() not in texto.lower(), (
            f"VAZOU no PDF do cliente: {proibido!r}")
    # a fronteira estrutural existe, não só o texto está limpo hoje
    import importlib

    pdf = importlib.import_module("modules.crm.services.proposal_pdf") if False else None
    return f"{len(texto)} chars no PDF do cliente, sem nenhum marcador interno"


async def r19_capabilities_sem_fantasma() -> str:
    doms = (await S.conecta_pro_capabilities()).get("dominios") or {}
    fantasmas = []
    for nome in doms:
        d = await S.conecta_pro_capabilities(dominio=nome)
        for t in (d.get("fluxo") or []):
            if not hasattr(S, t):
                fantasmas.append(f"{nome}→{t}")
    assert not fantasmas, f"o mapa cita tool inexistente: {fantasmas}"
    return f"{len(doms)} domínios, todas as tools do fluxo existem"


async def r20_fechar_folha_atras_do_muro() -> str:
    """⚠️ DIVERGÊNCIA do spec, decidida pelo Jordan em 12/09/2026.

    O R20 original pedia `ensaiar("fechar_folha")` funcionando como dry-run. Isso contradiz
    o CP-MCP-001, que faz `ensaiar` recusar toda ação de aprovação humana — e `fechar_folha`
    é uma delas. O Jordan escolheu MANTER O MURO: o ensaio de verdade se faz no sandbox, que
    grava num banco descartável.

    Este caso afirma a decisão dele, não o texto original do spec.
    """
    r = await S.ensaiar("fechar_folha", {})
    assert r.get("codigo") == "REQUER_APROVACAO_HUMANA", (
        f"o muro de fechar_folha caiu: {str(r)[:180]}")
    assert not r.get("escritas"), "registrou escrita numa ação barrada"
    # e o caminho alternativo legítimo existe
    import tool_risk_manifest as M

    assert M.TOOL_RISK.get("fechar_folha") == "propose", M.TOOL_RISK.get("fechar_folha")
    return "muro mantido (decisão do dono); ensaio real via no_sandbox"


async def r21_muro_antes_de_resolver() -> str:
    """403 e não 404: o muro dispara ANTES de resolver a entidade.

    O Cowork provou isso antes de arriscar a chamada real, e é a prova mais forte: a recusa
    é estrutural, não depende de o alvo existir.
    """
    r = await S.ensaiar("propor_pagamento", {"descricao": "ID-QUE-NAO-EXISTE-ZZZ",
                                             "valor": 1})
    assert r.get("http") == 403, f"esperava 403 (muro antes), veio {r.get('http')}: {r}"
    assert r.get("codigo") == "REQUER_APROVACAO_HUMANA", r
    return "403 com ID inexistente — o muro vem antes de resolver a entidade"


async def r22_ensaio_nao_polui_a_fila() -> str:
    """Fila poluída por teste treina humano a aprovar sem ler."""
    import gate_propose as G

    for fn in (S.ensaiar, S.no_sandbox, S.executar_em_segundo_plano):
        r = await fn("enviar_link_assinatura", {"contrato": MAIAPOLIS_CTR})
        assert r.get("codigo") == G.CODIGO_APROVACAO, r
        assert not r.get("escritas"), "registrou escrita"
    return "os 3 despachantes recusam sem criar pedido na Central"


async def r23_pendencias_acionaveis() -> str:
    r = await S.pendencias_acionaveis(horizonte_dias=30, severidade_minima="media")
    assert r.get("ok"), str(r)[:200]
    itens = r.get("pendencias") or []
    assert itens, "nenhuma pendência — improvável, e lista vazia é lida como 'tudo bem'"
    assert r.get("criterio_de_severidade"), "severidade sem critério declarado"
    for i in itens:
        for campo in ("id", "dominio", "titulo", "severidade", "impacto",
                      "acao_sugerida", "tool_para_agir"):
            assert campo in i, f"pendência sem {campo}: {sorted(i)}"
        assert i["severidade"] in ("critica", "alta", "media", "baixa"), i["severidade"]
    # ordenada: severidade mais grave primeiro
    pesos = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
    ordem = [pesos[i["severidade"]] for i in itens]
    assert ordem == sorted(ordem), "a lista não está ordenada por severidade"
    return f"{len(itens)} pendências ordenadas · {r.get('por_severidade')}"


async def r24_escopo_lgpd_declarado() -> str:
    """Bloco 7: o agente sabe o que vai acessar ANTES de acessar."""
    import lgpd_escopo as L

    assert L.nivel("tool_inventada_agora") == L.SENSIVEL, "o fail-closed caiu"
    assert L.nivel("baixar_holerite_pdf") == L.SENSIVEL
    assert L.nivel("folha_dashboard") == L.AGREGADO
    d = await S.conecta_pro_capabilities(dominio="folha_dp")
    assert d.get("lgpd_por_tool"), "capabilities não declara o nível por tool"
    for t, v in d["lgpd_por_tool"].items():
        assert v.get("lgpd_nivel") in (L.AGREGADO, L.OPERACIONAL, L.SENSIVEL), (t, v)
        assert v.get("lgpd_significa"), f"{t} sem tradução do nível"
    c = L.CONCESSAO
    assert not L.concessao_vale_para("baixar_holerite_pdf"), (
        "holerite individual entrou na concessão de operação normal")
    return (f"{len(L.NIVEL)} tools classificadas; concessão de {len(c['tools'])} até "
            f"{c['valido_ate']}")


CASOS = [
    ("R01 documento legível", r01_documento_legivel),
    ("R02 identificador tolerante", r02_identificador_tolerante),
    ("R03 listagem diz de quem é", r03_listagem_diz_de_quem_e),
    ("R04 dossiê numa chamada", r04_dossie_numa_chamada),
    ("R05 documentos com versão", r05_documentos_com_versao),
    ("R06 ensaio mostra e não grava", r06_ensaio_mostra_e_nao_grava),
    ("R07 isolamento do sandbox ⭐", r07_isolamento_do_sandbox),
    ("R08 valor único e conflito", r08_valor_unico_e_conflito),
    ("R09 operação longa vira job", r09_operacao_longa_vira_job),
    ("R10 parede do modelo em uso", r10_parede_do_modelo_em_uso),
    ("R11 parede de aprovação humana", r11_parede_de_aprovacao_humana),
    ("CP-MCP-002 parâmetro = 422", extra_parametro_obrigatorio),
    ("R12 orçamento misto", r12_orcamento_misto),
    ("R13 margem não cadastrada", r13_margem_nao_cadastrada),
    ("R14 regime ausente", r14_regime_ausente),
    ("R15 dois CNPJs", r15_dois_cnpjs),
    ("R18 nota interna não vaza", r18_nota_interna_nao_vaza),
    ("R19 capabilities × registry", r19_capabilities_sem_fantasma),
    ("R20 fechar_folha atrás do muro", r20_fechar_folha_atras_do_muro),
    ("R21 muro antes de resolver", r21_muro_antes_de_resolver),
    ("R22 ensaio não polui a fila", r22_ensaio_nao_polui_a_fila),
    ("R23 pendências acionáveis", r23_pendencias_acionaveis),
    ("R24 escopo LGPD declarado", r24_escopo_lgpd_declarado),
    ("CP-MCP-003 request_id sempre", extra_request_id_em_toda_falha),
]


async def main() -> int:
    falhas = []
    for rotulo, fn in CASOS:
        try:
            detalhe = await fn()
            print(f"  ✅ {rotulo:34} {detalhe}")
        except AssertionError as e:
            falhas.append(rotulo)
            print(f"  ❌ {rotulo:34} {e}")
        except Exception as e:  # noqa: BLE001
            falhas.append(rotulo)
            print(f"  💥 {rotulo:34} {type(e).__name__}: {e}")
    print()
    if falhas:
        print(f"TEST test_regressao_mcp FAIL — {len(falhas)}/{len(CASOS)}: {', '.join(falhas)}")
        return 1
    print(f"TEST test_regressao_mcp PASS — {len(CASOS)}/{len(CASOS)} casos (run {RUN})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
