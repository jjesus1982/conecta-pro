# Consultor de Segurança Patrimonial na Visita — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o José Luís de gerente comercial em consultor de segurança eletrônica que caminha com o Jordan pela visita, pergunta o que o projeto exige e propõe o escopo por ANALOGIA com o que o Jordan já vendeu.

**Architecture:** Dois blocos independentes. (1) Um roteiro técnico ADITIVO no `MANAGER_PROMPT`, derivado dos itens reais das propostas dele — não de teoria de segurança. (2) Uma tool `sugerir_escopo` que acha a proposta passada mais parecida e devolve o escopo dela como ponto de partida, sempre citando o número da proposta de origem.

**Tech Stack:** Python 3.12 · SQLAlchemy async · Postgres · registro `ToolDef` do orquestrador · `MANAGER_TOOLS` do conector WhatsApp.

## Global Constraints

- **NUNCA fabricar escopo.** `sugerir_escopo` devolve itens de uma proposta REAL, citando `number` e data. Se nada casar acima do corte, diz que não achou — não monta escopo genérico.
- **NUNCA fabricar preço.** A sugestão traz o item; o preço continua vindo do catálogo ou da pessoa, pelo caminho já existente (`resolver_itens`).
- **Uma pergunta por vez.** É a regra que o `SYSTEM_PROMPT` já impõe no atendimento e vale igual aqui: numa visita o Jordan está andando, não preenchendo formulário.
- **Roteiro é GUIA, não interrogatório.** Se o Jordan já disse, não pergunta de novo. Se ele está com pressa, pula para o essencial.
- **Canal fail-closed:** tudo aqui é `canais=("interno",)`. O cliente não vê roteiro de levantamento nem histórico de proposta.
- **Nada aqui move dinheiro, envia ao cliente ou grava proposta.** É leitura e registro. Gravar continua sendo `criar_orcamento`, com propor→aprovar.
- **`::` proibido dentro de `text()`** — use `cast(x AS t)`. Bind nu comparado a NULL ou dentro de `concat` também precisa de cast.
- **Commits** com pathspec e `--no-verify`. Arquivo NOVO precisa de `git add <arq>` explícito.
- **Oráculo tem de ser PROVADO VERMELHO** por mutação antes de valer.

---

## O material de origem (medido, não inventado)

O roteiro sai destes dois projetos reais do Jordan. Cada item recorrente é uma pergunta que o levantamento precisa responder:

**PROP-2026-00104 — CFTV em torre, perímetro externo (12 itens, R$ 38.086)**

| item | a pergunta que ele obriga |
|---|---|
| Poste tubular galvanizado 3 m antivandal + base de concreto | tem onde fixar, ou precisa erguer poste? |
| 8× Câmera Bullet IP 4 MP 360°, IR/DL 40 m, com microfone | quantos pontos? qual distância precisa enxergar? precisa áudio? |
| 2× NVR 4 canais PoE com IA | (canais = pontos ÷ 4) |
| 2× HD 2 TB Purple | quantos dias de gravação? |
| Gabinete externo IP66 | fica exposto a chuva/sol? |
| Sinalização ostensiva LED / giroflex | quer efeito dissuasivo visível? |
| ONU (bridge) + conversor de mídia de fibra | tem fibra chegando? internet de quem? |
| Roteador MikroTik (gateway/VPN) | quem vai ver as imagens, e de onde? |
| Base de concreto, **aterramento + DPS** | (Manaus: descarga atmosférica — nunca falta) |
| Fibra óptica, eletroduto, **vala** | qual a distância? tem passagem ou abre vala? |
| **Sistema de energia solar off-grid (2 estações)** | **TEM ENERGIA NO PONTO?** ← decide dezenas de milhares |

**PROP-2026-00116 — Sala de TI + backbone (25 itens, R$ 48.026)**

| item | a pergunta |
|---|---|
| 2× Rack 24U — um de DADOS, um exclusivo CFTV | separa a rede de dados da de câmera? |
| Switch SG24 + SG24 **PoE+** + SG16 remoto | quantos pontos PoE? tem rack remoto? |
| 4× SFP LX 20 km + 120 m fibra OS2 **armada** | distância entre os racks/blocos? |
| 3× DIO 12F + pigtail + cordão | quantas fibras terminar? |
| Patch panel Cat6, 2× caixa 305 m, 40 patch cords | quantos pontos de rede? |
| **DPS + aterramento POR RACK** (3 conjuntos) | (recorrente nos DOIS projetos) |
| Eletrocalha, eletroduto, caixa de passagem | tem infraestrutura de passagem? |
| Serviços: projeto executivo, as-built, certificação óptica, VLANs, FortiGate | precisa de documentação técnica? |

**Base da analogia, medida:** 16 propostas com 3 ou mais itens. Teste real da similaridade por
tokens: *"rack switch backbone cabeamento"* → PROP-00117 e PROP-00116 com **0,88**;
*"CFTV torre sem energia perímetro"* → as 3 de torre com **0,56**.

---

## File Structure

| arquivo | responsabilidade |
|---|---|
| `backend/modules/crm/services/escopo_analogo.py` | **criar** — acha a proposta passada mais parecida e devolve o escopo dela. Serviço puro, sem HTTP, testável sozinho |
| `backend/modules/integrations/connectors/whatsapp/agent_service.py` | **modificar** — bloco `_ROTEIRO_TECNICO` no `MANAGER_PROMPT` + tool `sugerir_escopo` em `MANAGER_TOOLS` + despacho |
| `backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py` | **modificar** — a mesma capacidade como leitura `crm.escopo_analogo`, para o Bartolo do computador |
| `backend/scripts/orq/test_escopo_analogo.py` | **criar** — oráculo do serviço e da tool |

---

## Task 1: Serviço de escopo por analogia

O coração. Dado o que foi levantado na visita, acha a proposta que o Jordan já fez mais parecida e devolve o escopo dela.

**Files:**
- Create: `backend/modules/crm/services/escopo_analogo.py`
- Test: `backend/scripts/orq/test_escopo_analogo.py`

**Interfaces:**
- Consumes: `sqlalchemy.text`, sessão async do `core.database`.
- Produces:
  - `async def buscar(db, termo: str, *, limite: int = 3, corte: float = 0.25) -> dict`
    → `{"termo": str, "corte": float, "achados": [{"numero", "titulo", "data", "similaridade", "itens": [{"nome","qtd","unidade","code"}]}], "aviso": str|None}`
  - `def _tokens(s: str) -> set[str]` (interno, exposto só para o teste)

- [ ] **Step 1: Escrever o oráculo que falha**

Criar `backend/scripts/orq/test_escopo_analogo.py`:

```python
#!/usr/bin/env python3
"""Oráculo do ESCOPO POR ANALOGIA — propor a partir do que o Jordan JÁ VENDEU.

Na visita, a pergunta que importa não é "o que a norma manda" — é "o que eu fiz da última
vez num lugar parecido". O Jordan tem 16 propostas com 3+ itens; elas são o repertório.

⭐ O QUE ESTE ORÁCULO PROTEGE é a diferença entre ANALOGIA e FABRICAÇÃO. Um escopo
sugerido vira orçamento, e orçamento vira contrato. Se o serviço puder devolver um item
que não saiu de proposta nenhuma, ele está inventando projeto de segurança — e isso sai
bonito, com a marca certa, dizendo coisa que ninguém especificou.

Seis invariantes:
  1. termo vazio é RECUSADO (não devolve "as 3 mais recentes" como se fossem parecidas)
  2. termo sem nenhuma correspondência devolve LISTA VAZIA e AVISO — nunca a proposta
     menos ruim disfarçada de achado
  3. todo item devolvido EXISTE numa proposta real (nenhum nome inventado)
  4. todo achado cita o NÚMERO e a DATA da proposta de origem (rastreável pelo Jordan)
  5. a similaridade é COERENTE: "rack switch backbone" acha Sala de TI acima de CFTV
  6. o corte é respeitado: nada abaixo dele entra

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \\
        /app/scripts/orq/test_escopo_analogo.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.crm.services import escopo_analogo as E

    falhas: list[str] = []
    async with async_session_factory() as db:
        # 1 · termo vazio
        r = await E.buscar(db, "")
        if r.get("achados"):
            falhas.append("termo VAZIO devolveu achados — sem termo não há analogia")

        # 2 · termo impossível
        r = await E.buscar(db, "zzz nada disso existe no repertorio dele qqq")
        if r.get("achados"):
            falhas.append(f"termo impossível devolveu {len(r['achados'])} achado(s) — "
                          f"a proposta menos ruim NÃO é uma proposta parecida")
        if not r.get("aviso"):
            falhas.append("nenhum achado e nenhum AVISO — silêncio parece sucesso vazio")

        # 5 · coerência: infra de rede acha Sala de TI
        rede = await E.buscar(db, "rack switch backbone cabeamento fibra")
        if not rede.get("achados"):
            print("  (base sem proposta de infra — bloco de coerência não exercitado)")
        else:
            topo = rede["achados"][0]
            if "TI" not in (topo["titulo"] or "").upper() and \
               "INFRAESTRUTURA" not in (topo["titulo"] or "").upper():
                falhas.append(f"'rack switch backbone' achou {topo['titulo'][:40]!r} no "
                              f"topo — a similaridade não está coerente")

            # 3 e 4 · rastreabilidade e não-fabricação
            for a in rede["achados"]:
                if not a.get("numero") or not a.get("data"):
                    falhas.append(f"achado sem número/data de origem: {str(a)[:80]}")
                if not a.get("itens"):
                    falhas.append(f"achado {a.get('numero')} sem itens")
                for it in a.get("itens") or []:
                    existe = (await db.execute(text(
                        "SELECT 1 FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
                        "WHERE p.number = :n AND i.name = :nome LIMIT 1"),
                        {"n": a["numero"], "nome": it["nome"]})).first()
                    if not existe:
                        falhas.append(f"item INVENTADO: {it['nome'][:50]!r} não está na "
                                      f"proposta {a['numero']}")
                        break

            # 6 · corte respeitado
            if any(a["similaridade"] < rede["corte"] for a in rede["achados"]):
                falhas.append("devolveu achado ABAIXO do corte declarado")

    if falhas:
        for f in falhas:
            print(f"FALHOU: {f}")
        return 1
    print("OK escopo_analogo: 6/6 — recusa termo vazio; termo sem correspondência devolve "
          "vazio COM aviso; todo item devolvido existe na proposta citada; todo achado "
          "cita número e data; a similaridade é coerente; e o corte é respeitado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 2: Rodar e confirmar que FALHA**

```bash
cd /opt/conecta-pro
docker cp backend/scripts/orq/test_escopo_analogo.py \
  conecta-pro-backend:/app/scripts/orq/test_escopo_analogo.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_escopo_analogo.py
```
Esperado: `ModuleNotFoundError: No module named 'modules.crm.services.escopo_analogo'`.

- [ ] **Step 3: Implementar o serviço**

Criar `backend/modules/crm/services/escopo_analogo.py`:

```python
"""Escopo por ANALOGIA: o que o Jordan já vendeu num lugar parecido.

Numa visita técnica a pergunta útil não é "o que a norma manda" — é "o que eu fiz da
última vez num caso assim". O Jordan tem 16 propostas com 3+ itens, e elas são o
repertório real dele: poste antivandal com base de concreto, NVR 4 canais PoE, HD Purple,
DPS e aterramento POR RACK, fibra armada com vala, energia solar off-grid onde não chega
luz. Nada disso um modelo precisa inventar — está tudo escrito no histórico.

⭐ ANALOGIA, NUNCA REGRA INVENTADA. Este serviço não deduz "para 8 câmeras use 2 NVR": ele
DEVOLVE a proposta em que o Jordan usou 2 NVR para 8 câmeras, com número e data, para ele
conferir. A diferença importa porque escopo sugerido vira orçamento, orçamento vira
contrato — e um item que não saiu de proposta nenhuma é projeto de segurança inventado,
que sai bonito e diz coisa que ninguém especificou.

Similaridade por SOBREPOSIÇÃO DE TOKENS sobre o termo da busca (não Jaccard): a proposta
tem dezenas de itens e o termo tem poucas palavras; Jaccard puniria a proposta mais
completa, que é justamente a mais útil como ponto de partida.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import text

#: Palavras que não distinguem projeto nenhum e inflariam qualquer par.
_VAZIAS = frozenset({
    "com", "sem", "para", "por", "dos", "das", "que", "uma", "num", "nos", "nas",
    "tem", "nao", "sim", "mais", "menos", "ate", "onde", "como", "esta", "estao",
    "kit", "servico", "material", "materiais", "unidade", "unidades",
})

#: Abaixo disto não é parecido — é a proposta menos ruim, e devolver isso como analogia é
#: pior que não devolver nada: o Jordan levaria para a visita um escopo que não serve.
CORTE_PADRAO = 0.25


def _tokens(s: str) -> set[str]:
    t = unicodedata.normalize("NFKD", str(s or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {p for p in re.sub(r"[^A-Z0-9]", " ", t).split()
            if len(p) > 2 and p.lower() not in _VAZIAS}


def _similaridade(termo: set[str], proposta: set[str]) -> float:
    """Fração do TERMO coberta pela proposta. Ver o docstring do módulo."""
    return (len(termo & proposta) / len(termo)) if termo else 0.0


async def buscar(db, termo: str, *, limite: int = 3,
                 corte: float = CORTE_PADRAO) -> dict[str, Any]:
    """Propostas passadas parecidas com o que foi levantado, com o escopo de cada uma."""
    alvo = _tokens(termo)
    if not alvo:
        return {"termo": termo, "corte": corte, "achados": [],
                "aviso": "informe o que você levantou (ex.: 'CFTV em torre, sem energia, "
                         "120 m do rack') — sem termo não há analogia."}

    linhas = (await db.execute(text("""
        SELECT p.number AS numero,
               coalesce(p.title, '') AS titulo,
               coalesce(p.issue_date::text, p.created_at::date::text) AS data,
               string_agg(i.name, ' | ' ORDER BY i.sort_order) AS blob
        FROM proposals p
        JOIN proposal_items i ON i.proposal_id = p.id
        GROUP BY 1, 2, 3
        HAVING count(i.id) >= 3
    """))).mappings().all()

    ranking = []
    for r in linhas:
        s = _similaridade(alvo, _tokens(f"{r['titulo']} {r['blob']}"))
        if s >= corte:
            ranking.append((s, r))
    ranking.sort(key=lambda x: (-x[0], x[1]["numero"]))

    achados = []
    for s, r in ranking[:max(1, min(int(limite), 5))]:
        itens = (await db.execute(text(
            "SELECT i.name AS nome, i.quantity AS qtd, i.unit AS unidade, i.code "
            "FROM proposal_items i JOIN proposals p ON p.id = i.proposal_id "
            "WHERE p.number = :n ORDER BY i.sort_order"), {"n": r["numero"]})).mappings().all()
        achados.append({
            "numero": r["numero"], "titulo": r["titulo"], "data": r["data"],
            "similaridade": round(s, 2),
            "itens": [{"nome": x["nome"], "qtd": float(x["qtd"] or 0),
                       "unidade": x["unidade"], "code": x["code"]} for x in itens],
        })

    return {
        "termo": termo, "corte": corte, "achados": achados,
        # Vazio DITO é resultado; vazio silencioso parece sucesso.
        "aviso": (None if achados else
                  f"nenhuma proposta sua passou de {corte:.0%} de semelhança com "
                  f"{termo!r}. Isso é caso NOVO — monte o escopo item a item pelo "
                  f"catálogo, não por analogia."),
        "como_usar": ("Estes são escopos que VOCÊ já vendeu, com número e data para "
                      "conferir. Use como ponto de partida e ajuste — o preço continua "
                      "vindo do catálogo ou de você."),
    }
```

- [ ] **Step 4: Rodar o oráculo e confirmar 6/6**

```bash
cd /opt/conecta-pro
docker cp backend/modules/crm/services/escopo_analogo.py \
  conecta-pro-backend:/app/modules/crm/services/escopo_analogo.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_escopo_analogo.py; echo "exit=$?"
```
Esperado: `OK escopo_analogo: 6/6 ...` e `exit=0`.

- [ ] **Step 5: Ver o resultado real com os dois termos do Jordan**

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
import asyncio, sys; sys.path.insert(0,'/app')
async def m():
    from core.database import async_session_factory
    from modules.crm.services import escopo_analogo as E
    async with async_session_factory() as db:
        for t in ('CFTV em torre, sem energia no ponto, 120 m do rack',
                  'rack, switch, backbone de fibra, cabeamento estruturado'):
            r = await E.buscar(db, t, limite=2)
            print(' TERMO:', t)
            for a in r['achados']:
                print('   %.2f  %s (%s)  %d itens  %s' % (a['similaridade'], a['numero'],
                      a['data'], len(a['itens']), a['titulo'][:40]))
asyncio.run(m())"
```
Esperado: o termo de CFTV traz as propostas de torre; o de rede traz as de Sala de TI, com
similaridade maior. **Se a ordem vier trocada, pare** — a similaridade não está coerente e
o oráculo (invariante 5) tem de estar acusando.

- [ ] **Step 6: Provar VERMELHO por mutação**

```bash
cd /opt/conecta-pro
cp backend/modules/crm/services/escopo_analogo.py /tmp/ea_ok.py
python3 - <<'EOF'
p='/opt/conecta-pro/backend/modules/crm/services/escopo_analogo.py'
s=open(p).read()
a='''        if s >= corte:
            ranking.append((s, r))'''
assert a in s
open(p,'w').write(s.replace(a,'''        ranking.append((s, r))  # MUTACAO: ignora o corte'''))
EOF
docker cp backend/modules/crm/services/escopo_analogo.py \
  conecta-pro-backend:/app/modules/crm/services/escopo_analogo.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_escopo_analogo.py
cp /tmp/ea_ok.py backend/modules/crm/services/escopo_analogo.py
docker cp backend/modules/crm/services/escopo_analogo.py \
  conecta-pro-backend:/app/modules/crm/services/escopo_analogo.py
diff -q /tmp/ea_ok.py backend/modules/crm/services/escopo_analogo.py
```
Esperado no mutado: `FALHOU: termo impossível devolveu N achado(s)`. `diff`: sem saída.

- [ ] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git add backend/modules/crm/services/escopo_analogo.py backend/scripts/orq/test_escopo_analogo.py
git commit --no-verify -m "feat(crm): escopo por ANALOGIA com o historico do Jordan

Numa visita a pergunta util nao e 'o que a norma manda' — e 'o que eu fiz da
ultima vez num caso assim'. 16 propostas com 3+ itens sao o repertorio real.

ANALOGIA, NUNCA REGRA INVENTADA: nao deduz 'para 8 cameras use 2 NVR'; DEVOLVE
a proposta em que ele usou 2 NVR para 8 cameras, com numero e data para
conferir. Escopo sugerido vira orcamento e orcamento vira contrato.

Termo sem correspondencia devolve VAZIO COM AVISO — a proposta menos ruim nao
e uma proposta parecida.

test_escopo_analogo 6/6, provado vermelho por mutacao.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/modules/crm/services/escopo_analogo.py backend/scripts/orq/test_escopo_analogo.py
```

---

## Task 2: O roteiro de levantamento no modo consultor

**Files:**
- Modify: `backend/modules/integrations/connectors/whatsapp/agent_service.py` (bloco novo + concatenação no `_system_prompt`)
- Test: `backend/scripts/orq/test_escopo_analogo.py` (estender)

**Interfaces:**
- Consumes: `MANAGER_PROMPT` (existente), `_system_prompt(owner, papel)` (existente).
- Produces: constante `_ROTEIRO_TECNICO: str` e `_system_prompt` passando a devolver
  `MANAGER_PROMPT + _ROTEIRO_TECNICO` quando `owner=True`.

- [ ] **Step 1: Estender o oráculo**

Em `backend/scripts/orq/test_escopo_analogo.py`, antes do bloco `if falhas:`, inserir:

```python
        # ── ROTEIRO TÉCNICO: o consultor tem de saber o que perguntar ────────────────
        from modules.integrations.connectors.whatsapp import agent_service as A

        prompt_dono = A._system_prompt(owner=True)
        prompt_cliente = A._system_prompt(owner=False)

        # Os assuntos vêm dos ITENS REAIS das propostas dele, não de teoria.
        obrigatorios = ("energia", "aterramento", "gravação", "fibra", "poste",
                        "PoE", "distância", "acesso")
        faltando = [t for t in obrigatorios if t.lower() not in prompt_dono.lower()]
        if faltando:
            falhas.append(f"o roteiro do consultor não cobre {faltando} — cada um sai de "
                          f"um item recorrente das propostas dele")

        if "uma pergunta por vez" not in prompt_dono.lower():
            falhas.append("o roteiro não impõe UMA PERGUNTA POR VEZ — numa visita o "
                          "Jordan está andando, não preenchendo formulário")

        # O CLIENTE não pode receber o roteiro interno (é método comercial da casa).
        if "roteiro de levantamento" in prompt_cliente.lower():
            falhas.append("o roteiro interno VAZOU para o prompt do cliente")

        if "sugerir_escopo" not in prompt_dono:
            falhas.append("o roteiro não ensina a usar `sugerir_escopo` — o consultor "
                          "perguntaria e não proporia nada")
```

E trocar a mensagem final para:

```python
    print("OK escopo_analogo: 10/10 — recusa termo vazio; termo sem correspondência "
          "devolve vazio COM aviso; todo item existe na proposta citada; todo achado cita "
          "número e data; similaridade coerente; corte respeitado; o roteiro do consultor "
          "cobre energia/aterramento/gravação/fibra/poste/PoE/distância/acesso, impõe uma "
          "pergunta por vez, ensina a propor escopo — e NÃO vaza para o cliente.")
```

- [ ] **Step 2: Rodar e confirmar que FALHA**

```bash
cd /opt/conecta-pro
docker cp backend/scripts/orq/test_escopo_analogo.py \
  conecta-pro-backend:/app/scripts/orq/test_escopo_analogo.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_escopo_analogo.py
```
Esperado: `FALHOU: o roteiro do consultor não cobre [...]`.

- [ ] **Step 3: Escrever o roteiro**

Acrescentar ao FIM de `backend/modules/integrations/connectors/whatsapp/agent_service.py`:

```python


# ═══════════ ROTEIRO TÉCNICO DE LEVANTAMENTO (modo dono, aditivo) ═══════════
# Pedido do Jordan (27/08/2026): "o José Luís vai ser meu consultor de segurança, o cara
# que vou levar pras visitas técnicas".
#
# ⭐ ESTE ROTEIRO NÃO SAIU DE TEORIA DE SEGURANÇA — saiu dos ITENS REAIS das propostas
# dele. Cada pergunta existe porque um item recorrente do orçamento depende dela:
#   "tem energia no ponto?"      → energia solar off-grid (PROP-2026-00104)
#   "tem onde fixar?"            → poste 3 m antivandal + base de concreto
#   "qual a distância?"          → fibra OS2 armada, eletroduto, vala
#   "tem aterramento?"           → DPS + aterramento POR RACK (nos DOIS projetos)
#   "quantos dias de gravação?"  → HD 2 TB Purple
#   "exposto a chuva?"           → gabinete IP66
#   "quantos pontos?"            → nº de câmeras, canais de NVR, portas PoE do switch
#   "quem vê as imagens?"        → MikroTik gateway/VPN, portaria remota
# Prompt de consultor escrito por quem nunca fez visita faz pergunta boba; este é um
# espelho do que ele mesmo especifica.
#
# ADITIVO de propósito: entra DEPOIS do MANAGER_PROMPT, que mantém identidade,
# guard-rails e o papel de radar comercial. Reescrever o prompt inteiro jogaria fora
# meses de calibragem.

_ROTEIRO_TECNICO = """

════════ MODO CONSULTOR TÉCNICO (visita de levantamento) ════════
Quando o Jordan estiver EM CAMPO — disser que está numa visita, num condomínio, fazendo
levantamento, ou abrir uma visita — você deixa de ser só o radar comercial e vira o
CONSULTOR DE SEGURANÇA ELETRÔNICA que caminha com ele. Você conhece CFTV, controle de
acesso, perímetro, rede e infraestrutura, e sabe o que precisa ser respondido para um
projeto sair sem surpresa.

COMO CONDUZIR:
- UMA PERGUNTA POR VEZ, sempre. Ele está andando pelo local, não preenchendo formulário.
- Se ele JÁ respondeu (por texto, áudio, foto ou pin), NÃO pergunte de novo. A foto que
  ele mandou já foi descrita e anotada; use o que está lá.
- Se ele estiver com pressa, vá direto às CINCO que mudam o orçamento: energia no ponto,
  distância, onde fixar, quantos pontos, dias de gravação.
- Anote cada resposta com `anotar_visita`, no campo certo. Não acumule para o fim.
- Ao final, `fechar_visita` — e ela já diz o que ficou faltando.

O ROTEIRO (na ordem que a visita pede):

1. PANORAMA (campo `panorama`)
   - Que tipo de local é: condomínio, indústria, pátio, área aberta?
   - Quantas torres/blocos/unidades? Quantos moradores ou funcionários?
   - Já tem portaria hoje? Presencial, remota, ou nenhuma?

2. PERÍMETRO E ACESSOS (campo `achados`)
   - Qual a metragem aproximada do perímetro? É muro, cerca, ou aberto?
   - Quantos acessos de PEDESTRE e quantos de VEÍCULO?
   - Como está a iluminação à noite? Tem vegetação cobrindo alguma área?

3. O QUE JÁ EXISTE (campo `situacao_atual`)
   - Já tem câmera? Quantas, e é analógica (coaxial) ou IP (rede)?
   - Tem gravador? Está gravando de verdade? Há quantos dias de imagem?
   - Tem rack? Onde fica? Tem controle de acesso (tag, facial, biometria)?

4. AS CINCO QUE MUDAM O ORÇAMENTO (campos `achados` e `diagnostico_tecnico`)
   - TEM ENERGIA no ponto onde a câmera vai? (sem energia entra solar off-grid, e isso
     muda o orçamento em dezenas de milhares)
   - Qual a DISTÂNCIA do ponto até o rack/portaria? Tem eletroduto ou vai precisar de vala?
   - Tem ONDE FIXAR (poste, muro, fachada) ou vai precisar erguer poste com base?
   - Quantos PONTOS de câmera no total? (define canais de NVR e portas PoE do switch)
   - Quantos DIAS DE GRAVAÇÃO ele quer guardar? (define o HD)

5. INFRAESTRUTURA (campo `diagnostico_tecnico`)
   - Tem ATERRAMENTO e proteção contra surto? (em Manaus, descarga atmosférica é regra —
     DPS e aterramento por rack estão em todos os seus projetos)
   - Tem fibra ou internet chegando? De quem é o link?
   - O ponto fica exposto a chuva e sol? (define gabinete IP66)
   - A rede de dados e a de câmeras vão juntas ou separadas?

6. OPERAÇÃO E OPORTUNIDADE (campos `oportunidade_comercial` e `proximos_passos`)
   - Quem vai VER as imagens, e de onde? (define VPN/acesso remoto e monitoramento)
   - Precisa de efeito ostensivo (sinalização, giroflex)?
   - Precisa de documentação técnica: projeto executivo, as-built, certificação?
   - Qual o próximo passo combinado, e com quem?

PROPONDO O ESCOPO:
Depois do levantamento — ou quando o Jordan pedir ("o que eu proponho aqui?", "monta um
escopo", "o que eu fiz num parecido?") — chame `sugerir_escopo` com as palavras do
levantamento. Ela devolve PROPOSTAS QUE ELE JÁ FEZ, com número e data. Apresente assim:
"Na PROP-XXXX, de tal data, você fez isso aqui: [itens]". NUNCA invente item, quantidade
ou preço: se `sugerir_escopo` não achar nada parecido, diga que é caso novo e monte item a
item pelo catálogo.
"""
```

- [ ] **Step 4: Ligar o roteiro ao prompt do dono**

Em `backend/modules/integrations/connectors/whatsapp/agent_service.py`, na função
`_system_prompt`, trocar:

```python
    if owner:
        return MANAGER_PROMPT
```

por:

```python
    if owner:
        # ADITIVO: o roteiro técnico entra DEPOIS, sem tocar no MANAGER_PROMPT (radar
        # comercial). O `_ROTEIRO_TECNICO` está definido no fim do módulo; a referência
        # resolve em tempo de chamada, não de definição.
        return MANAGER_PROMPT + _ROTEIRO_TECNICO
```

- [ ] **Step 5: Rodar o oráculo e confirmar 10/10**

```bash
cd /opt/conecta-pro
docker cp backend/modules/integrations/connectors/whatsapp/agent_service.py \
  conecta-pro-backend:/app/modules/integrations/connectors/whatsapp/agent_service.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_escopo_analogo.py; echo "exit=$?"
```
Esperado: `OK escopo_analogo: 10/10 ...` e `exit=0`.

- [ ] **Step 6: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(bartolo): roteiro tecnico de levantamento no modo consultor

'O Jose Luis vai ser meu consultor de seguranca, o cara que vou levar pras
visitas tecnicas' (Jordan, 27/08/2026).

O ROTEIRO NAO SAIU DE TEORIA — saiu dos ITENS REAIS das propostas dele. Cada
pergunta existe porque um item recorrente do orcamento depende dela: 'tem
energia no ponto?' vem do solar off-grid da PROP-2026-00104; 'tem
aterramento?' vem do DPS por rack, que aparece nos DOIS projetos.

ADITIVO: entra depois do MANAGER_PROMPT, que mantem identidade e guard-rails.
UMA PERGUNTA POR VEZ — ele esta andando pelo local, nao preenchendo
formulario. E se ja respondeu por foto/audio, nao pergunta de novo.

test_escopo_analogo 6/6 -> 10/10.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/modules/integrations/connectors/whatsapp/agent_service.py \
     backend/scripts/orq/test_escopo_analogo.py
```

---

## Task 3: A tool `sugerir_escopo` nos dois canais internos

**Files:**
- Modify: `backend/modules/integrations/connectors/whatsapp/agent_service.py` (`MANAGER_TOOLS` + `_exec_manager_tool`)
- Modify: `backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py` (leitura para o Bartolo do computador)
- Test: `backend/scripts/orq/test_escopo_analogo.py` (estender)

**Interfaces:**
- Consumes: `escopo_analogo.buscar(db, termo, limite=, corte=)` da Task 1.
- Produces: tool `sugerir_escopo` em `MANAGER_TOOLS`, handler `_mtool_sugerir_escopo(db, args, conversation_id)`, e leitura `crm.escopo_analogo`.

- [ ] **Step 1: Estender o oráculo**

Em `test_escopo_analogo.py`, antes de `if falhas:`:

```python
        # ── A TOOL nos dois canais internos ──────────────────────────────────────────
        import modules.ai.conversation.services.orquestrador.tools_read_crm  # noqa: F401
        from modules.ai.conversation.services.orquestrador.read_dispatcher import _READ_OPS
        from modules.ai.conversation.services.orquestrador.tool_registry import tools_do_canal

        nomes_mgr = {(t.get("function") or {}).get("name") for t in A.MANAGER_TOOLS}
        if "sugerir_escopo" not in nomes_mgr:
            falhas.append("`sugerir_escopo` não está em MANAGER_TOOLS (WhatsApp do dono)")
        if "escopo_analogo" not in _READ_OPS.get("crm", {}):
            falhas.append("leitura `crm.escopo_analogo` não registrada (Bartolo do chat)")

        # E NUNCA no canal do cliente: repertório comercial é método da casa.
        publicas = {t.name for t in tools_do_canal("publico")}
        if "sugerir_escopo" in publicas:
            falhas.append("`sugerir_escopo` VAZOU para o canal do cliente — o repertório "
                          "de propostas é método comercial, não vitrine")
```

E ajustar a mensagem final de `10/10` para `12/12`, acrescentando ao texto:
`"; e a tool existe nos dois canais internos sem vazar para o cliente"`.

- [ ] **Step 2: Rodar e confirmar que FALHA**

```bash
cd /opt/conecta-pro
docker cp backend/scripts/orq/test_escopo_analogo.py \
  conecta-pro-backend:/app/scripts/orq/test_escopo_analogo.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_escopo_analogo.py
```
Esperado: `FALHOU: sugerir_escopo não está em MANAGER_TOOLS ...`.

- [ ] **Step 3: Implementar no WhatsApp (modo dono)**

Em `agent_service.py`, acrescentar o handler ao FIM do arquivo:

```python


async def _mtool_sugerir_escopo(db, args: dict, conversation_id: int) -> dict:
    """Escopo por analogia com o que o Jordan já vendeu. Ver crm/services/escopo_analogo."""
    from modules.crm.services import escopo_analogo as _EA  # noqa: PLC0415

    termo = str(args.get("levantamento") or "").strip()
    if not termo:
        # Se há visita aberta, o levantamento JÁ está nela — usa o que foi anotado em vez
        # de exigir que o Jordan repita tudo. É o ganho de ter registrado durante a visita.
        v = await _visita_aberta(db, conversation_id)
        if v:
            from sqlalchemy import text as _t  # noqa: PLC0415

            linha = (await db.execute(_t(
                "SELECT concat_ws(' ', cliente_nome, panorama, situacao_atual, "
                "  diagnostico_tecnico, oportunidade_comercial, achados::text) AS tudo "
                "FROM crm_visit_reports WHERE id = cast(:i AS uuid)"),
                {"i": v["id"]})).scalar()
            termo = str(linha or "")
    if not termo.strip():
        return {"erro": "me diga o que você levantou (ex.: 'CFTV em torre, sem energia, "
                        "120 m do rack'), ou abra uma visita e anote antes."}
    return await _EA.buscar(db, termo, limite=int(args.get("limite") or 2))
```

E declarar a tool no INÍCIO de `MANAGER_TOOLS` (logo após `MANAGER_TOOLS = [`):

```python
    {
        "type": "function",
        "function": {
            "name": "sugerir_escopo",
            "description": (
                "Acha PROPOSTAS QUE O JORDAN JÁ FEZ parecidas com o levantamento e "
                "devolve o escopo delas, com número e data. Use quando ele perguntar 'o "
                "que eu proponho aqui', 'monta um escopo', 'o que eu fiz num parecido'. "
                "Sem `levantamento`, usa o que já foi anotado na visita aberta. "
                "É ANALOGIA: apresente citando a proposta de origem e NUNCA invente item."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "levantamento": {
                        "type": "string",
                        "description": "O que foi levantado, em palavras (tipo de local, "
                                       "o que tem, o que falta). Opcional se há visita "
                                       "aberta.",
                    },
                    "limite": {"type": "integer",
                               "description": "Quantas propostas trazer. Padrão 2."},
                },
            },
        },
    },
```

E no `_exec_manager_tool`, junto dos ifs de visita:

```python
            if name == "sugerir_escopo":
                return await _mtool_sugerir_escopo(db, args, conversation_id)
```

- [ ] **Step 4: Implementar no Bartolo do computador**

Acrescentar ao FIM de `backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py`:

```python


# ── ESCOPO POR ANALOGIA (lacuna 37) ───────────────────────────────────────────────────
# A mesma capacidade que o José Luís usa em campo, do lado do computador: o Jordan cita a
# visita e pergunta "o que eu proponho aqui". Ver `crm/services/escopo_analogo.py`.

async def _escopo_analogo(db, user, scope, *, levantamento=None, visita=None, limite=2,
                          **_) -> Any:
    _gate(user)
    from modules.crm.services import escopo_analogo as _EA

    termo = str(levantamento or "").strip()
    if not termo and str(visita or "").strip():
        # A partir da VISITA: o levantamento já está gravado, não precisa ser redigitado.
        from sqlalchemy import text as _t

        termo = str((await db.execute(_t(
            "SELECT concat_ws(' ', cliente_nome, panorama, situacao_atual, "
            "  diagnostico_tecnico, oportunidade_comercial, achados::text) "
            "FROM crm_visit_reports "
            "WHERE id::text = :r OR cliente_nome ILIKE '%' || cast(:r AS text) || '%' "
            "ORDER BY created_at DESC LIMIT 1"), {"r": str(visita).strip()})).scalar() or "")
    return await _EA.buscar(db, termo, limite=int(limite))


registrar_read("crm", "escopo_analogo",
               "Propostas que VOCÊ já fez parecidas com um levantamento, com o escopo de "
               "cada uma (número e data para conferir). Filtros: levantamento (em "
               "palavras) OU visita (id ou nome do cliente — usa o que foi anotado nela), "
               "limite (padrão 2). É ANALOGIA com o seu histórico, não escopo inventado.",
               _escopo_analogo)
```

- [ ] **Step 5: Rodar o oráculo e confirmar 12/12**

```bash
cd /opt/conecta-pro
for f in modules/integrations/connectors/whatsapp/agent_service.py \
         modules/ai/conversation/services/orquestrador/tools_read_crm.py; do
  docker cp backend/$f conecta-pro-backend:/app/$f
done
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_escopo_analogo.py; echo "exit=$?"
```
Esperado: `OK escopo_analogo: 12/12 ...` e `exit=0`.

- [ ] **Step 6: Provar a equivalência das listas do WhatsApp (regressão)**

```bash
cd /opt/conecta-pro
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_canal_ferramentas.py; echo "exit=$?"
```
Esperado: `OK canal_ferramentas: 6/6 ...` e `exit=0`. **Se falhar por lista derivada
diferente da local, pare**: acrescentar tool a `MANAGER_TOOLS` sem publicá-la no registro
quebra a equivalência, e é exatamente o que essa trava existe para pegar.

- [ ] **Step 7: Commit**

```bash
cd /opt/conecta-pro
git commit --no-verify -m "feat(bartolo): sugerir_escopo nos dois canais internos

A mesma capacidade em campo (WhatsApp, modo dono) e no computador (Bartolo).
Sem 'levantamento', usa o que JA foi anotado na visita aberta — que e o ganho
de ter registrado durante a caminhada.

NAO vai para o canal do cliente: o repertorio de propostas e metodo comercial
da casa, nao vitrine. A trava de canal prova isso toda vez.

test_escopo_analogo 10/10 -> 12/12 · test_canal_ferramentas 6/6.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" \
  -- backend/modules/integrations/connectors/whatsapp/agent_service.py \
     backend/modules/ai/conversation/services/orquestrador/tools_read_crm.py \
     backend/scripts/orq/test_escopo_analogo.py
```

---

## Task 4: Fechamento — travas, bake e prova na imagem

**Files:**
- Test (rodar, não criar): `test_escopo_analogo.py`, `test_canal_ferramentas.py`, `test_visita_whatsapp.py`, `fechado_bartolo.py`, `checar_drift_workers.sh`

- [ ] **Step 1: Rodar a bateria inteira**

```bash
cd /opt/conecta-pro
for o in test_escopo_analogo test_canal_ferramentas test_visita_whatsapp \
         test_acao_funil_crm test_orcamento_por_itens; do
  docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/$o.py \
    >/tmp/$o.out 2>/dev/null
  echo "$o exit=$? · $(grep -E '^OK|^FALHOU' /tmp/$o.out | head -1 | cut -c1-60)"
done
python3 backend/scripts/qa/fechado_bartolo.py >/tmp/b.out 2>&1
echo "fechado_bartolo exit=$? · $(tail -2 /tmp/b.out | head -1)"
```
Esperado: todos com `exit=0` e `fechado_bartolo` com `9/9 condições`.

- [ ] **Step 2: Avisar os outros terminais**

Mandar mensagem para `conecta-pro-5b` e `conecta-pro-b2`: bake iniciando, ~15min, arquivos
tocados (`crm/services/escopo_analogo.py` novo, `whatsapp/agent_service.py`,
`orquestrador/tools_read_crm.py`), sem migration, pedindo aviso em 2 minutos se houver WIP.

- [ ] **Step 3: Assar**

```bash
cd /opt/conecta-pro
ls -ld /tmp/conecta_deploy.lock 2>&1 | grep -q "No such" && \
  bash scripts/deploy_backend_bluegreen.sh
```
Esperado ao fim: `═══ BLUE/GREEN CONCLUÍDO ═══` e `Sem drift`.

- [ ] **Step 4: Provar dentro da IMAGEM**

```bash
cd /opt/conecta-pro
IMG=$(docker inspect -f '{{.Image}}' conecta-pro-backend)
docker run --rm --entrypoint sh $IMG \
  -c "test -f /app/modules/crm/services/escopo_analogo.py" && echo "OK  servico"
docker run --rm --entrypoint sh $IMG \
  -c "grep -qF '\"sugerir_escopo\"' /app/modules/integrations/connectors/whatsapp/agent_service.py" \
  && echo "OK  tool no WhatsApp"
docker run --rm --entrypoint sh $IMG \
  -c "grep -qF '\"escopo_analogo\"' /app/modules/ai/conversation/services/orquestrador/tools_read_crm.py" \
  && echo "OK  leitura no Bartolo"
docker run --rm --entrypoint sh $IMG \
  -c "grep -qF 'MODO CONSULTOR TÉCNICO' /app/modules/integrations/connectors/whatsapp/agent_service.py" \
  && echo "OK  roteiro tecnico"
bash scripts/checar_drift_workers.sh; echo "drift exit=$?"
```
Esperado: 4 linhas `OK` e `drift exit=0`. **Grepe a string DISTINTIVA entre aspas** —
grepar a palavra solta casa com texto de comentário e já deu falso positivo neste projeto.

- [ ] **Step 5: Rodar a bateria contra a imagem assada**

```bash
cd /opt/conecta-pro
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 \
  /app/scripts/orq/test_escopo_analogo.py; echo "exit=$?"
```
Esperado: `12/12` e `exit=0`.

---

## O que este plano NÃO faz

- **Não valida projeto de segurança.** O roteiro pergunta o que os orçamentos DELE exigem;
  não substitui norma técnica nem responsabilidade de projetista.
- **Não deduz quantidade.** Não existe "8 câmeras ⇒ 2 NVR" em lugar nenhum: o que existe é
  "na PROP-2026-00104 você usou 2 NVR para 8 câmeras".
- **Não grava proposta.** Sugerir é ler. Gravar continua em `criar_orcamento`, com
  propor→aprovar.
- **Não testa pelo WhatsApp real.** Continua a lente aberta desde 27/08: o roteiro só será
  provado de verdade quando o Jordan caminhar por um condomínio conversando com ele.
- **Não usa a geolocalização além de endereço.** O pin já vira achado `tipo: local`; medir
  distância até a central ou agrupar visitas por região é outro trabalho.
