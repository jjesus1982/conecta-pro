"""Oráculo — o DONO alcança o próprio motor de precificação (28/08/2026).

O motor da CCT existia completo: 10 funções, 24 parâmetros, DOZE deles marcados
"CONFIRMADO Jordan 2026-08-10". E o único que não o alcançava era o Jordan — `simular_preco`
e `montar_proposta` viviam só em `_PAPEIS["sdr"]`, o papel do número ANÔNIMO. Um
desconhecido no WhatsApp cotava um posto; o dono, não. `pricing_simulations`: 0 linhas.

O que este oráculo defende, e por que cada item existe:

  1. O SERVIDOR enxerga — no grafo real de import, não no que o teste montou. Foi assim que
     a etapa 1 passou 8/8 morta hoje de manhã.
  2. O DONO ganha E O CLIENTE NÃO PERDE. Dar capacidade a um lado tirando do outro é o
     defeito silencioso: ninguém reclama do que sumiu de um número anônimo.
  3. CAMINHO FELIZ COM NÚMERO: `simular_preco("AGP P1 Noturno")` tem de devolver preço e
     composição, não "a tool existe". Testar só a presença prova que a porta existe, não
     que ela abre.
  4. A REDAÇÃO DO CLIENTE CONTINUA REDIGINDO. A projeção pública não pode ganhar custo,
     encargo, margem nem lucro — é o mesmo motor servindo dois leitores.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

FALHAS: list[str] = []
INTERNOS = ("custo", "encargo", "margem", "lucro", "salario", "repasse", "tributo",
            "composicao", "beneficio")


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        FALHAS.append(titulo)


async def main() -> int:
    import main_production  # noqa: F401,PLC0415  — o grafo do SERVIDOR, não o meu

    from modules.integrations.connectors.whatsapp import agent_service as A

    def nomes(schemas):
        return {(s.get("function") or {}).get("name") for s in schemas}

    dono, cliente = nomes(A._tools_ativas(owner=True)), nomes(A._tools_ativas(owner=False))

    for t in ("simular_preco", "montar_proposta"):
        checar(t in dono, f"o DONO enxerga {t}")
    # o cliente não perde: as duas continuam onde estavam
    for t in ("simular_preco", "montar_proposta"):
        checar(t in cliente, f"o CLIENTE não perdeu {t}",
               "" if t in cliente else "regressão — capacidade some do lado anônimo")
    checar(len(cliente) >= 14, "o conjunto do CLIENTE não encolheu", f"{len(cliente)} tools")

    # ── caminho feliz: número de verdade, não presença ────────────────────────
    r = await A._tool_simular_preco({"funcao": "AGP P1 Noturno", "postos": 2}, dono=True)
    preco = float(r.get("preco_posto_mes") or 0)
    checar(r.get("ok") and preco > 0,
           "simular_preco devolve NÚMERO para o dono", f"R$ {preco:,.2f}/posto·mês")

    comp = r.get("composicao") or {}
    faltam = [k for k in ("CUSTO_TOTAL", "encargos", "beneficios_vt_vr", "margem_pct",
                          "salario_base") if not comp.get(k) and comp.get(k) != 0]
    checar(not faltam, "a COMPOSIÇÃO vem inteira (custo antes do preço)",
           f"faltam: {faltam}" if faltam else
           f"custo R$ {comp.get('CUSTO_TOTAL')} · margem {comp.get('margem_pct')}")
    checar(float(comp.get("CUSTO_TOTAL") or 0) < preco,
           "o custo é MENOR que o preço (a margem existe e é positiva)")

    # ── margem: existia na engine e a tool não expunha ────────────────────────
    # 28/08/2026 — sem isto o Jordan perguntou "e com 10%?" e começou a fazer a conta À MÃO.
    m10 = await A._tool_simular_preco({"funcao": "AGP P1 Noturno", "margem": 0.10}, dono=True)
    p10 = float(m10.get("preco_posto_mes") or 0)
    checar(0 < p10 < preco, "margem MENOR devolve preço MENOR",
           f"15% = R$ {preco:,.2f} → 10% = R$ {p10:,.2f}")
    checar(float((m10.get("composicao") or {}).get("margem_pct") or 0) == 0.10,
           "a margem pedida é a margem aplicada")
    m10b = await A._tool_simular_preco({"funcao": "AGP P1 Noturno", "margem": 10}, dono=True)
    checar(float(m10b.get("preco_posto_mes") or 0) == p10,
           "aceita '10' e '0.10' como a mesma coisa")
    # o CUSTO não muda com a margem — se mudar, a engine está errada em algum lugar
    checar((m10.get("composicao") or {}).get("CUSTO_TOTAL") == comp.get("CUSTO_TOTAL"),
           "mudar a margem NÃO mexe no custo")

    # ⚠️ margem é decisão comercial: o CLIENTE não pode escolher a dele.
    cli_m = await A._tool_simular_preco({"funcao": "AGP P1 Noturno", "margem": 0.01})
    checar(float(cli_m.get("preco_posto_mes") or 0) == preco,
           "o CLIENTE não consegue baixar a própria margem",
           f"pediu 1%, recebeu R$ {float(cli_m.get('preco_posto_mes') or 0):,.2f}")

    # ── a redação do cliente continua redigindo ───────────────────────────────
    pub = await A._tool_simular_preco({"funcao": "AGP P1 Noturno", "postos": 2})
    vazou = [k for k in pub if any(i in k.lower() for i in INTERNOS)]
    texto = str(pub.get("instrucao") or "")
    checar(not vazou, "a projeção do CLIENTE não ganhou campo interno",
           f"vazaram: {vazou}" if vazou else "")
    checar(float(pub.get("preco_posto_mes") or 0) == preco,
           "os dois leem o MESMO motor (mesmo preço, redação diferente)")
    checar("NUNCA cite" in texto, "a instrução do cliente segue proibindo custo/margem")

    print()
    if FALHAS:
        print(f"  ❌ {len(FALHAS)} FALHA(S): {', '.join(FALHAS)}")
        return 1
    print("  ✅ o dono alcança o próprio motor, e o cliente continua com o que tinha.")
    return 0


sys.exit(asyncio.run(main()))
