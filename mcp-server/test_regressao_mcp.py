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
