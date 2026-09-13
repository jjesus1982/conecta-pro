"""Varredura paramétrica do contrato de erro — lixo APENAS no identificador.

Rode dentro da imagem:
    docker exec -w /app conecta-pro-mcp python3 varredura_envelope.py read
    docker exec -w /app conecta-pro-mcp python3 varredura_envelope.py 2a read
    docker exec -w /app conecta-pro-mcp python3 varredura_envelope.py write_low ensaio

⭐ Por que existe, e por que o MÉTODO é a parte que importa (13/09/2026). A validação do
Cowork derrubou minha afirmação "0 leituras com 5xx" com um caso: `espelho_ponto`. A causa
não era a tool — era a minha varredura anterior, que passava lixo em TODOS os argumentos.
Em qualquer tool com parâmetro tipado (`mes: int`), a validação de tipo disparava primeiro,
devolvia um 422 correto, e o caminho do IDENTIFICADOR nunca era exercitado. Eu media o
validador de tipo e chamava de cobertura.

Três passadas, porque há três lugares onde o contrato de erro quebra:
  · `read`            — obrigatório inválido, tipado preenchido com valor VÁLIDO;
  · `2a`              — identificador OPCIONAL inválido, obrigatório válido (foi assim que o
                        Cowork achou `dossie_juridico`, que eu não alcançava);
  · `write_low ensaio`— pelo `no_sandbox`. ⚠️ NÃO pelo `ensaiar`: ele intercepta a escrita
                        ANTES do ERP, então prova que não grava e não mede o erro.

⚠️⚠️ A PASSADA DE ESCRITA DEIXA LIXO NO SANDBOX, e na 1ª execução ela MEDIU O PRÓPRIO
LIXO. `aceitar_estimativa_da_proposta` apareceu como "sucesso falso": o resolvedor havia
casado `LIXO-INVALIDO-ZZZ-999` com uma proposta cujo `client_name` era literalmente
"LIXO-INVALIDO-ZZZ-999" — criada por uma passada anterior desta mesma varredura. O
resolvedor estava CERTO; o defeito era o teste acreditando no resíduo que ele mesmo plantou.

Depois de rodar `write_low`, limpe:

    docker exec conecta-pro-postgres-staging psql -U postgres -d conecta_pro_staging -c \
      "DELETE FROM proposals WHERE cast(proposals AS text) ILIKE '%LIXO%';"

⚠️ NÃO rode `refrescar_sandbox.sh` para isso: o staging carrega DDL de trabalho de outros
terminais que produção não tem (frente 07), e refrescar apagaria o trabalho deles.

⚠️ E distingue IDENTIFICADOR de TEXTO LIVRE. `nome`, `titulo`, `servico` são dado: criar lead
com nome esquisito é legítimo, e marcar isso como defeito me faria consertar tool correta.
"""
import asyncio, inspect, json, logging, sys, typing
sys.path.insert(0, "/app")
import re as _re
import server as S, tool_risk_manifest as M
from fastmcp import Client
logging.disable(logging.WARNING)
LIXO = "LIXO-INVALIDO-ZZZ-999"

def valor_valido(anot, nome):
    """Valor que PASSA a validação de tipo — para o teste chegar no identificador.

    ⚠️ `server.py` tem `from __future__ import annotations`, então TODA anotação chega
    aqui como STRING ('int', 'str | None'). A 1ª versão comparava `base is int` e nunca
    casava: o lixo voltava para o `mes`, a validação de tipo disparava primeiro e o caminho
    do identificador nunca era exercitado — que é exatamente o furo que o Cowork achou no
    `espelho_ponto`. O instrumento de medir tinha o mesmo defeito que ele media.
    """
    t = str(anot).lower().replace("optional[", "").strip("[]'\" ")
    if "int" in t and "print" not in t:
        return 9 if ("mes" in nome or "month" in nome) else 2026
    if "float" in t or "decimal" in t:
        return 1.0
    if "bool" in t:
        return False
    if "list" in t:
        return []
    if "dict" in t:
        return {}
    return None  # str: candidato a lixo

def _ident(nome):
    """É IDENTIFICADOR de algo existente — não texto livre.

    ⚠️ `nome`, `titulo`, `descricao`, `servico`, `emitente` são DADO, não identificador:
    criar lead com nome esquisito é dado legítimo, e marcar isso como "sucesso falso" me
    faria consertar tool correta. A varredura tem de saber a diferença.
    """
    return bool(_re.search(r"(^|_)id$|_id$|identificador|numero|chave|cnpj|cpf|codigo|"
                           r"^ref$|proposta|contrato|deal|posto|employee|proposal", nome, _re.I))


def paylod(fn):
    p = {}
    ids = []
    for par in inspect.signature(fn).parameters.values():
        if par.default is not inspect.Parameter.empty:
            continue
        v = valor_valido(par.annotation, par.name)
        if v is None:
            p[par.name] = LIXO
            if _ident(par.name):
                ids.append(par.name)
        else:
            p[par.name] = v
    return p, ids

def env(t):
    try:
        return json.loads(t[t.index("{"):t.rindex("}") + 1])
    except Exception:
        return {"http": 500, "_raw": t[:70]}

async def main(classe="read", usar_ensaio=False):
    alvos = []
    for n, c in M.TOOL_RISK.items():
        if c != classe or not hasattr(S, n):
            continue
        p, ids = paylod(getattr(S, n))
        if ids:                      # só quem tem identificador para invalidar
            alvos.append((n, p, ids))
    cat = {"envelope": [], "nega_propria": [], "vazio": [], "llm": [], "PROBLEMA": []}
    async with Client(S.mcp) as c:
        for n, p, ids in alvos:
            # ⚠️ `ensaiar` NÃO serve para medir erro de identificador: ele intercepta a
            # escrita ANTES da chamada ao ERP, então o caminho do id inválido nunca roda.
            # Ele prova que não grava. Para o CONTRATO DE ERRO é o `no_sandbox`, que deixa a
            # chamada acontecer de verdade contra o ambiente de teste.
            chamada = ("no_sandbox", {"ferramenta": n, "argumentos": p}) if usar_ensaio else (n, p)
            try:
                d = (await asyncio.wait_for(c.call_tool(*chamada), timeout=25)).structured_content or {}
            except Exception as e:
                d = env(str(e))
            if usar_ensaio:
                if d.get("ok") is False and d.get("codigo"):
                    pass                      # o próprio sandbox recusou: envelope válido
                else:
                    d = d.get("resultado") if isinstance(d.get("resultado"), dict) else d
            if (d.get("http") or 0) >= 500:
                cat["PROBLEMA"].append(f"{n}[{','.join(ids)}]:500"); continue
            if d.get("ok") is False:
                f = [k for k in ("codigo", "http", "mensagem", "dica") if not d.get(k)]
                (cat["PROBLEMA"] if f else cat["envelope"]).append(f"{n}:falta {f}" if f else n); continue
            if d.get("ok") is None:
                cat["PROBLEMA"].append(f"{n}: SEM `ok` — {sorted(k for k in d if k!='request_id')[:5]}"); continue
            if any(k in d and d[k] is False for k in ("existe", "encontrado", "achou")):
                cat["nega_propria"].append(n); continue
            if d.get("total") == 0 or (isinstance(d.get("items"), list) and not d["items"]):
                cat["vazio"].append(n); continue
            r = str(d.get("resposta") or "")
            if r and ("inválid" in r.lower() or "sem pergunta" in r.lower()):
                cat["llm"].append(n); continue
            cat["PROBLEMA"].append(f"{n}:sucesso falso {sorted(k for k in d if k!='request_id')[:5]}")
    print(f"CLASSE {classe} · alvos {len(alvos)}")
    for k, v in cat.items():
        print(f"  {k:12} {len(v):3}")
    for x in cat["PROBLEMA"]:
        print("   🔴", x)




# ── 2ª passada: lixo em identificador OPCIONAL, válido no resto ────────────────────────
# ⭐ Achado do Cowork (13/09): ele chamou `dossie_juridico(tipo="funcionario",
# identificador="LIXO")` — tipo VÁLIDO, id lixo — e recebeu `{"encontrado": false}` sem
# envelope. Minha 1ª passada só preenche obrigatórios, então nunca chegou nesse caminho.
# O valor válido sai do DOCSTRING: quem enumera opções ('panorama' | 'funcionario' | …)
# está declarando o domínio do parâmetro.
import re as _re


def _enum_do_docstring(fn, nome):
    doc = (fn.__doc__ or "")
    m = _re.search(rf"{nome}\s*[:=]?\s*((?:'[a-z_]+'|\"[a-z_]+\"|[a-z_]+)(?:\s*\|\s*"
                   rf"(?:'[a-z_]+'|\"[a-z_]+\"|[a-z_]+))+)", doc, _re.I)
    if m:
        return _re.split(r"\s*\|\s*", m.group(1))[0].strip("'\" ")
    return None


async def segunda_passada(classe="read"):
    alvos = []
    for n, c in M.TOOL_RISK.items():
        if c != classe or not hasattr(S, n):
            continue
        fn = getattr(S, n)
        ps = list(inspect.signature(fn).parameters.values())
        opcionais_str = [p.name for p in ps
                         if p.default is not inspect.Parameter.empty
                         and valor_valido(p.annotation, p.name) is None
                         and _ident(p.name)]
        if not opcionais_str:
            continue
        base = {}
        ok_base = True
        for p in ps:
            if p.default is not inspect.Parameter.empty:
                continue
            v = valor_valido(p.annotation, p.name)
            if v is None:
                v = _enum_do_docstring(fn, p.name)
                if v is None:
                    ok_base = False        # obrigatório que eu não sei preencher: pula
                    break
            base[p.name] = v
        if ok_base:
            alvos.append((n, base, opcionais_str))

    problemas = []
    async with Client(S.mcp) as c:
        for n, base, opcs in alvos:
            for campo in opcs[:3]:
                p = {**base, campo: LIXO}
                try:
                    d = (await asyncio.wait_for(c.call_tool(n, p), timeout=25)
                         ).structured_content or {}
                except Exception as e:
                    d = env(str(e))
                if (d.get("http") or 0) >= 500:
                    problemas.append(f"{n}({campo}=lixo):500")
                elif d.get("ok") is None:
                    problemas.append(f"{n}({campo}=lixo): SEM `ok` — "
                                     f"{sorted(k for k in d if k != 'request_id')[:5]}")
    print(f"2ª PASSADA {classe} · {len(alvos)} tools com id opcional")
    for x in problemas:
        print("   🔴", x)
    if not problemas:
        print("   sem problema")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "read"
    if modo == "2a":
        asyncio.run(segunda_passada(sys.argv[2] if len(sys.argv) > 2 else "read"))
    else:
        asyncio.run(main(modo, len(sys.argv) > 2 and sys.argv[2] == "ensaio"))
