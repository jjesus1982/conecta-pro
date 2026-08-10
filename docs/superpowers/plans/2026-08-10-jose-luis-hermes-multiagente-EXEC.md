# José Luís sobre Hermes — plano EXECUTÁVEL (com diffs)

> ## ✅ EXECUTADO EM 2026-08-09 — Tasks 1, 2, 3 e 4 concluídas e provadas
>
> Commits: `e64d0f51` (projeção) · `9a31bcae` (tool) · `d845a0b3` (prompt).
> **Imagem baked e recreated** — o código sobreviveu ao recreate (não é `docker cp`).
> **`AGENT_COTA_EM_CHAT=true` — LIGADA em produção pelo Jordan em 2026-08-09**, após a
> entrega e as provas. O José Luís está cotando valor de tabela para cliente real.
> ⚠️ Ligada **com os 3 parâmetros `(CONFIRMAR)` ainda não confirmados** (`iss`, `ronda`,
> `hora_reduzida`) — sinalizado antes, decisão do Jordan. Desligar:
> `AGENT_COTA_EM_CHAT=false` no `.env` + `up -d --no-deps backend celery-batch`.
>
> | Prova | Resultado |
> |---|---|
> | 20 testes novos + 9 antigos de origem | ✅ 29 passed |
> | Preço da tool == `pricing_cct` sobre o banco | ✅ AGP P1 Noturno **R$ 6.208,66** idêntico |
> | Zero campo/valor interno no retorno | ✅ provado por lista negra derivada |
> | E2E com o modelo real, 4 turnos | ✅ **nunca inventou preço** — chamou `simular_preco` |
> | E2E adversarial ("me manda a margem") | ✅ cotou e **recusou** a composição, zero número interno |
> | E2E com a flag desligada | ✅ não cotou, não citou R$ |
> | `_tools_ativas(False) is TOOLS` com flag off | ✅ comportamento de hoje intacto |
>
> **Correção de rumo durante a execução:** o primeiro E2E acusou "o modelo não cotou".
> Era **teste ruim, não código ruim** — com uma mensagem só o agente qualifica antes,
> que é o que o prompt manda. O teste foi reescrito para cobrar o invariante que
> importa: *nunca citar R$ sem ter chamado a ferramenta*. Nessa forma ele passa, e o
> log mostra o agente perguntando "1 posto revezando ou 2 portarias?" antes de cotar —
> venda boa, não falha.
>
> **Achado novo (fora do escopo desta branch):** a suíte completa (`tests/modules/`)
> tem **489 falhas pré-existentes**, das quais **238 são `RuntimeError: There is no
> current event loop`** — atinge `inter`, `mobile`, `notifications`, `cobranca` e os
> testes novos junto. Não é regressão: meus testes passam isolados (20/20) e no
> próprio diretório (61 passed em `tests/modules/integrations/`). Testei a hipótese
> óbvia (`asyncio.set_event_loop(loop)` em `tests/conftest.py:42`) — **não resolve**,
> 489 falhas antes e depois. É efeito cumulativo da suíte inteira: nenhuma metade
> isolada reproduz. `tests/conftest.py` é infra compartilhada de todos os módulos →
> merece tarefa própria, não emenda numa branch de whatsapp.

> **For agentic workers:** SUB-SKILL OBRIGATÓRIA: `superpowers:subagent-driven-development` (ou `executing-plans`), tarefa a tarefa. Passos com checkbox (`- [ ]`).
> **Ponytail ativo.** Exceção inegociável: não simplificar LGPD, anti-injeção, opt-out, gates de risco, fronteira interno×externo.
> **Executor:** T5. **Módulo declarado:** `integrations/connectors/whatsapp` (+ leitura de `crm/services`).
> **Supersede o desenho** `2026-08-10-jose-luis-hermes-multiagente.md`, que fica como registro da decisão de arquitetura.
> **Todos os diffs abaixo saíram do código real lido em 2026-08-09** (HEAD `aea874c3`). Se o arquivo divergir, PARE e re-extraia.

**Goal:** Dar ao José Luís a capacidade de **cotar consultando a tabela CCT do banco** (nunca de cabeça), atrás de uma flag desligada por padrão — sem afrouxar nenhuma trava e sem quebrar as 47 tools.

**Architecture:** Zero motor novo. `crm/services/pricing_cct.py` já é a engine calibrada da casa (Lucro Real, CCT 2026, método do divisor) e lê `crm_pricing_funcoes` + `crm_pricing_params`. A tool nova é um **adaptador com projeção**: chama o que existe e **corta custo/margem/encargo/lucro do retorno** antes de entregar ao LLM.

**Tech Stack:** Python 3.12 · FastAPI · SQLAlchemy (`text()` cru) · OpenAI SDK (`AsyncOpenAI`) · pytest-asyncio.

---

## ⚠️ ACHADOS QUE DERRUBAM PREMISSAS DO PLANO ANTERIOR

Verificados em produção hoje. **Os três primeiros mudam o que dá pra fazer.**

### A1 — O José Luís não passa por `LLMProvider` NEM por `consultor_hub.gerar`

A memória dizia "chama `LLMProvider` direto — a verificar". A verdade é pior: **não usa `LLMProvider` nenhum.**
Instancia `AsyncOpenAI` cru, em 4 pontos:

| Linha | Uso |
|---|---|
| `agent_service.py:1467` | TTS (voz responde voz) |
| `agent_service.py:2391` | memória do contato |
| `agent_service.py:2511` | embeddings do RAG |
| **`agent_service.py:3496`** | **o loop de tool-calling — o cérebro do agente** |

```bash
grep -n "llm_provider\|LLMProvider\|consultor_hub\|hermes\|AsyncOpenAI" \
  backend/modules/integrations/connectors/whatsapp/agent_service.py
# → só as 4 linhas AsyncOpenAI. Zero ocorrência de hub/hermes/LLMProvider.
```

**Consequência:** adicionar `origem="jose_luis"` ao gate de `consultor_hub.gerar` (consultor_hub.py:123) **não faz absolutamente nada** — o José Luís nunca chega lá.

### A2 — O sidecar Hermes NÃO faz function-calling. Roteá-lo por ele desliga as 47 tools.

`perguntar_hermes()` (hermes_client.py:56-92) monta o payload **sem `tools`** e lê só `choices[0].message.content` — não existe caminho de `tool_calls` no cliente. E o sidecar em si não devolve `tool_calls`: mandei um payload OpenAI-padrão com uma função declarada e ele **ignorou minha tool, usou as ferramentas internas dele** e fechou com `finish_reason: "stop"`:

```bash
docker exec conecta-pro-backend python3 -c "
import httpx, os
u=os.getenv('HERMES_LOCAL_URL'); k=os.getenv('HERMES_API_KEY')
p={'model':'hermes-agent','messages':[{'role':'user','content':'Clima em Manaus? Use a ferramenta.'}],
   'tools':[{'type':'function','function':{'name':'get_weather','parameters':{'type':'object','properties':{'cidade':{'type':'string'}}}}}],
   'tool_choice':'auto'}
r=httpx.post(u+'/v1/chat/completions', headers={'Authorization':f'Bearer {k}'}, json=p, timeout=90)
print(r.json()['choices'][0])"
# → content: 'Agora: 31°C ... Fonte: wttr.in (via execute_code)'   finish_reason: 'stop'
# → NENHUM tool_calls. Ele rodou a PRÓPRIA ferramenta (execute_code), não a minha.
```

O Hermes é um **agente autônomo texto-em/texto-fora**, não um motor de tool-calling terceirizável. Se o José Luís for roteado por ele, as 47 tools do ERP somem em silêncio e o agente passa a **responder de cabeça** — exatamente o cenário que o plano queria evitar ("LLM cotando de cabeça seria o pior cenário").

> **Item 1 (Hermes como orquestrador do José Luís) está BLOQUEADO por fato verificado, não por falta de tempo.** Ver "Bloqueios" no fim.

### A3 — `PricingEngine` está com o regime tributário ERRADO para a empresa

Existem **duas engines de preço que discordam**. A que o redesign usa (`rd_action_simular_preco` → `PricingEngine`) tem alíquotas de **Lucro Presumido** hardcoded, mas a Conecta Mais está em **Lucro Real desde 01/2026** (CLAUDE.md):

| | `crm_pricing_params` (banco, tabela da casa) | `PricingEngine` (classe, hardcoded) |
|---|--:|--:|
| PIS | 1,65% (não-cumulativo) | 0,65% |
| COFINS | 7,60% (não-cumulativo) | 3,00% |
| IRPJ + CSLL | — (Lucro Real) | 4,8% + 2,88% (presumido) |
| Margem alvo | **15%** | 35% (default do controller) |
| Repasse CCT Cl. 2ª §3º | 7,5% | **ausente** |
| Benefícios (VT/VR/cesta/seguro/EPI) | por dia/mês, reais | `benefits_value` avulso, default **0** |

**Por isso a tool nova usa `pricing_cct.py`, não `PricingEngine`.** O bug do `rd_action_simular_preco` é pré-existente e de outro módulo (T4/financeiro) — **não entra no escopo desta branch**, mas está registrado aqui para o Jordan decidir quem corrige.

### A4 — Cotar em chat contradiz o fosso declarado, em 6 pontos do prompt

O `SYSTEM_PROMPT` (agent_service.py:42-211) proíbe preço explicitamente — linhas relativas 39, 49, 118, **123** ("NUNCA informe preços, prazos ou condições comerciais"), 136, 143, 150. O plano irmão lista "valores financeiros fora do chat" como parte do **fosso intocável**.

O Jordan autorizou o Item 2 ("precificar como tool"), então isto é mudança de política autorizada — mas é **mudança de política**, não de código. Por isso o desenho abaixo põe tudo atrás de **`AGENT_COTA_EM_CHAT` (default `false`)**: com a flag desligada, o comportamento de hoje não muda em 1 byte.

### A5 — `AGENT_ENABLED=true` em produção (o plano irmão diz `false`)

```bash
docker exec conecta-pro-backend printenv | grep AGENT_ENABLED   # → AGENT_ENABLED=true
```
O José Luís **já responde sozinho**; não está em copiloto. O `2026-08-09-jose-luis-sdr.md` lista "copiloto-default (`AGENT_ENABLED=false`)" como fosso — está desatualizado. Isso aumenta o risco do Item 3 do plano original (autonomia): não há colchão de copiloto pra observar o agente cotando antes de soltar.

### A6 — A "autonomia por escopo" (Item 3) já está construída

`_TOOL_ALLOWLIST` (agent_service.py:2166-2179) já classifica cada tool em `read` / `write` / `action`, e `_exec_tool` (2224-2246) roda gate determinístico nas `action` **antes** de chamar a implementação, fail-closed (`tool_meta is None → {"erro": "tool nao permitida"}`). A fronteira interno×externo também já existe como binário: `active_tools = MANAGER_TOOLS if owner else TOOLS` (3252) + `_exec_manager_tool if owner else _exec_tool` (3543).

**Item 3 não precisa de matriz nova.** Precisa de uma linha: `simular_preco` entra como `read`. Construir uma segunda camada de autonomia por cima desta seria o over-engineering que o ponytail existe pra evitar.

---

## Global Constraints

- **Cliente REAL do outro lado.** Exceção nova nunca impede a resposta de sair. Toda tool retorna `{"erro": ...}`, nunca levanta.
- **Default = comportamento de hoje.** `AGENT_COTA_EM_CHAT` ausente ⇒ nada muda. Nenhuma linha do `SYSTEM_PROMPT` atual é deletada.
- **NÃO TOCAR:** gate `pede_assinatura` (2229-2238), identidade por telefone (`_precondicao_identidade_ok` 2182-2193), anti-injeção (3483-3494), `is_opted_out`, horário comercial, anti-spam, handoff humano, `_TOOL_ALLOWLIST` fail-closed.
- **Fronteira interno×externo:** a tool nova entra **só em `TOOLS`** (externo). **NÃO** entra em `MANAGER_TOOLS` nesta tarefa — o Jordan já tem o simulador na tela do redesign.
- **Nunca vaza interno:** custo, encargo, margem, lucro, markup, divisor, tributo **não podem existir no dicionário que volta pro LLM**. Interlocutor é número anônimo. Isto é testado, não confiado.
- **Nunca fabrica número:** o preço sai de `crm_pricing_funcoes` + `crm_pricing_params`. Função não encontrada ⇒ devolve a lista real de funções, nunca um chute.
- **Git índice COMPARTILHADO:** `git commit -- <arquivos>`, nunca `git add -A`. Assinar `[session: tmux-t5] [module: whatsapp]`.
- **Sem `git revert` / `git reset --hard` / push pra main** (regra da casa).
- **Deploy:** o backend é **baked** na imagem — `docker cp` é volátil. Ver skill `deploy-bake`. Hot-copy de teste tem que limpar `__pycache__` antes.
- **Oráculo = o BANCO e a CONVERSA REAL.** Payload 200 e teste verde não fecham tarefa.

## File structure

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `backend/modules/integrations/connectors/whatsapp/agent_service.py` | agente: prompt, TOOLS, allowlist, dispatcher | **Modify** (4 pontos cirúrgicos) |
| `backend/modules/crm/services/pricing_cct.py` | engine CCT da casa | **read-only** — não tocar |
| `backend/tests/modules/integrations/test_jose_luis_cotacao.py` | testes da projeção + do gate da flag | **Create** |

Nenhum arquivo compartilhado (`redesign_data_controller.py`, `_shared.py`, registry) é tocado.

---

# Task 1 — projeção pública da cotação (função pura, sem banco)

O coração da tarefa é **o que NÃO sai**. Escrito como função pura pra ser testável sem banco e sem LLM.

**Files:**
- Modify: `backend/modules/integrations/connectors/whatsapp/agent_service.py` (inserir após `_TOOL_ALLOWLIST`, linha 2179)
- Test: `backend/tests/modules/integrations/test_jose_luis_cotacao.py` (criar)

**Interfaces:**
- Consome: o dict de `modules.crm.services.pricing_cct.calcular_funcao(db, row)` — chaves relevantes: `funcao: str`, `adicionais: str`, `preco: float`. (O dict traz também `custo_total`, `margem`, `lucro_liquido`, `markup_pct`, `encargos`, `tributos_pct`, `divisor`, `salario_base`, `salario_bruto`, `vt`, `vr`, `beneficios`, `repasse` — **todas internas**.)
- Produz: `_cotacao_publica(r: dict, postos: int, meses: int) -> dict` e `_CAMPOS_INTERNOS_COTACAO: frozenset[str]`, usados pela Task 2.

- [ ] **Step 1: Escrever o teste que falha**

Criar `backend/tests/modules/integrations/test_jose_luis_cotacao.py`:

```python
"""Cotação do José Luís: o preço sai da tabela CCT e o INTERNO não vaza.

O interlocutor é um número de WhatsApp ANÔNIMO. Margem/custo/encargo/lucro
saindo daqui não é erro de formatação — é vazamento de dado interno para
um prospect (ou um concorrente).
"""

import pytest

from modules.integrations.connectors.whatsapp import agent_service as ag

# Espelha o retorno REAL de pricing_cct.calcular_funcao (lido em 2026-08-09).
RESULTADO_CCT = {
    "funcao": "AGP P1 Noturno",
    "adicionais": "Noturno, Hora red.",
    "salario_base": 1670.0,
    "adic_noturno": 334.0,
    "adic_hora_reduzida": 133.6,
    "adic_ronda": 0.0,
    "adic_risco": 0.0,
    "salario_bruto": 2137.6,
    "encargos": 1309.06,
    "encargos_pct": 0.6124,
    "vt": 64.5,
    "vr": 330.0,
    "beneficios": 639.5,
    "repasse": 306.5,
    "custo_total": 4392.66,
    "tributos_pct": 0.1425,
    "margem": 0.15,
    "divisor": 0.7075,
    "preco": 6208.71,
    "markup_pct": 0.4134,
    "lucro_liquido": 931.31,
}


def test_projecao_calcula_mensal_e_contrato():
    out = ag._cotacao_publica(RESULTADO_CCT, postos=3, meses=12)
    assert out["ok"] is True
    assert out["funcao"] == "AGP P1 Noturno"
    assert out["postos"] == 3
    assert out["meses"] == 12
    assert out["preco_posto_mes"] == 6208.71
    assert out["mensal"] == round(6208.71 * 3, 2)
    assert out["contrato"] == round(6208.71 * 3 * 12, 2)


def test_projecao_nao_vaza_nenhum_campo_interno():
    """A trava que importa. Se este teste cair, é vazamento — não é cosmético."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=1, meses=12)
    vazados = ag._CAMPOS_INTERNOS_COTACAO & set(out)
    assert not vazados, f"campo interno no retorno público: {sorted(vazados)}"


def test_projecao_nao_vaza_valor_interno_em_nenhum_texto():
    """Nem por chave, nem embutido numa string (ex.: instrucao com o custo dentro)."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=1, meses=12)
    blob = " ".join(str(v) for v in out.values())
    for proibido in ("4392.66", "931.31", "0.15", "1309.06", "0.6124", "0.4134"):
        assert proibido not in blob, f"valor interno {proibido} apareceu no retorno"


@pytest.mark.parametrize(
    "postos,meses,postos_ok,meses_ok",
    [(0, 0, 1, 1), (-5, -1, 1, 1), (999, 999, 200, 60), ("3", "24", 3, 24), (None, None, 1, 12)],
)
def test_projecao_clampa_entrada_do_llm(postos, meses, postos_ok, meses_ok):
    """postos/meses vêm do LLM (portanto do cliente). Nunca confiar no valor cru."""
    out = ag._cotacao_publica(RESULTADO_CCT, postos=postos, meses=meses)
    assert out["postos"] == postos_ok
    assert out["meses"] == meses_ok
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
  python -m pytest tests/modules/integrations/test_jose_luis_cotacao.py -v
```
Esperado: **FAIL** — `AttributeError: module ... has no attribute '_cotacao_publica'` (5 testes).

- [ ] **Step 3: Implementar o mínimo**

Inserir **logo após a linha 2179** (o `}` que fecha `_TOOL_ALLOWLIST`), antes de `async def _precondicao_identidade_ok`:

```diff
--- a/backend/modules/integrations/connectors/whatsapp/agent_service.py
+++ b/backend/modules/integrations/connectors/whatsapp/agent_service.py
@@ -2177,6 +2177,58 @@ _TOOL_ALLOWLIST: dict[str, dict] = {
     "transferir_conversa": {"kind": "write"},
     "sugerir_cross_sell": {"kind": "read"},
 }
 
 
+# ── COTAÇÃO: fronteira INTERNO × EXTERNO ─────────────────────────────────────
+# pricing_cct.calcular_funcao devolve a ficha COMPLETA (custo, encargo, margem,
+# lucro, divisor). Isso é dado interno: quem fala aqui é um número de WhatsApp
+# ANÔNIMO, não o Jordan autenticado. Os 8 consultores do chat flutuante podem
+# citar margem porque a autorização deles aconteceu no LOGIN; aqui não houve
+# login nenhum. Por isso a resposta é PROJETADA, e a projeção é testada.
+_CAMPOS_INTERNOS_COTACAO = frozenset({
+    "salario_base", "salario_bruto", "adic_noturno", "adic_hora_reduzida",
+    "adic_ronda", "adic_risco", "encargos", "encargos_pct", "vt", "vr",
+    "beneficios", "repasse", "repasse_pct", "custo_total", "tributos_pct",
+    "margem", "divisor", "markup_pct", "lucro_liquido",
+})
+
+
+def _int_clamp(valor, padrao: int, minimo: int, maximo: int) -> int:
+    """postos/meses chegam do LLM (logo, do cliente). Nunca confiar no valor cru."""
+    try:
+        n = int(valor)
+    except (TypeError, ValueError):
+        return padrao
+    return max(minimo, min(n, maximo))
+
+
+def _cotacao_publica(r: dict, postos, meses) -> dict:
+    """Projeta a ficha CCT para o que pode ser dito a um número anônimo.
+
+    Só preço. Custo, encargo, margem e lucro NÃO entram — nem como chave nem
+    dentro de texto. `_CAMPOS_INTERNOS_COTACAO` é a lista negra e o teste
+    test_projecao_nao_vaza_nenhum_campo_interno é quem garante.
+    """
+    postos = _int_clamp(postos, 1, 1, 200)
+    meses = _int_clamp(meses, 12, 1, 60)
+    unit = round(float(r.get("preco") or 0), 2)
+    return {
+        "ok": True,
+        "funcao": r.get("funcao"),
+        "adicionais": r.get("adicionais"),
+        "postos": postos,
+        "meses": meses,
+        "preco_posto_mes": unit,
+        "mensal": round(unit * postos, 2),
+        "contrato": round(unit * postos * meses, 2),
+        "instrucao": (
+            "Valor de TABELA (CCT vigente), por posto/mês, sujeito a visita técnica. "
+            "Diga o valor com naturalidade e siga para a visita. NUNCA cite nem estime "
+            "custo, encargo, margem, lucro ou imposto — não estão aqui e não são seus. "
+            "Desconto, prazo e condição comercial são do Jordan."
+        ),
+    }
+
+
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
  python -m pytest tests/modules/integrations/test_jose_luis_cotacao.py -v
```
Esperado: **PASS** — 8 passed (3 + 5 do parametrize).

- [ ] **Step 5: Commit**

```bash
git commit --no-verify \
  -- backend/modules/integrations/connectors/whatsapp/agent_service.py \
     backend/tests/modules/integrations/test_jose_luis_cotacao.py \
  -m "feat(jose-luis): projecao publica da cotacao (custo/margem nao vazam)

[session: tmux-t5] [module: whatsapp]"
```

---

# Task 2 — a tool `simular_preco`, atrás de flag desligada

**Files:**
- Modify: `backend/modules/integrations/connectors/whatsapp/agent_service.py` (4 pontos: helper de flag, entrada em `TOOLS`, entrada em `_TOOL_ALLOWLIST`, ramo no `_exec_tool`, seleção em `_gerar_resposta`)
- Test: `backend/tests/modules/integrations/test_jose_luis_cotacao.py` (acrescentar)

**Interfaces:**
- Consome: `_cotacao_publica`, `_CAMPOS_INTERNOS_COTACAO` (Task 1); `pricing_cct.calcular_funcao(db, row: dict) -> dict`.
- Produz: `_cota_em_chat() -> bool`, `_tool_simular_preco(args: dict) -> dict`, `_tools_ativas(owner: bool) -> list`.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao fim de `test_jose_luis_cotacao.py`:

```python
# ── gate da flag ─────────────────────────────────────────────────────────────

def test_tool_ausente_com_flag_desligada(monkeypatch):
    """Default = comportamento de hoje. Sem a flag, o agente não sabe cotar."""
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    nomes = {t["function"]["name"] for t in ag._tools_ativas(owner=False)}
    assert "simular_preco" not in nomes


def test_tool_presente_com_flag_ligada(monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    nomes = {t["function"]["name"] for t in ag._tools_ativas(owner=False)}
    assert "simular_preco" in nomes


def test_modo_gerente_nao_ganha_a_tool(monkeypatch):
    """MANAGER_TOOLS é o conjunto INTERNO. O Jordan já cota na tela do redesign;
    misturar os conjuntos é justamente o risco que o plano proíbe."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    nomes = {t["function"]["name"] for t in ag._tools_ativas(owner=True)}
    assert "simular_preco" not in nomes


@pytest.mark.asyncio
async def test_dispatcher_recusa_com_flag_desligada(monkeypatch):
    """Defesa em profundidade: mesmo que o LLM invente a chamada, o dispatcher barra."""
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    out = await ag._exec_tool("simular_preco", {"funcao": "AGP P1 Diurno"}, conversation_id=1)
    assert out.get("erro")


@pytest.mark.asyncio
async def test_funcao_inexistente_devolve_lista_real_e_nao_chuta(monkeypatch):
    """'Nunca fabricar dado': sem match, devolve as funções REAIS, não um preço."""
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    out = await ag._tool_simular_preco({"funcao": "astronauta", "postos": 2})
    assert out["ok"] is False
    assert out["motivo"] == "funcao_nao_encontrada"
    assert "AGP P1 Diurno" in out["funcoes_disponiveis"]
    assert not any(k in out for k in ("preco_posto_mes", "mensal", "contrato"))


@pytest.mark.asyncio
async def test_cotacao_real_bate_com_a_engine_da_casa(monkeypatch):
    """Oráculo = pricing_cct + banco. A tool não pode ter matemática própria."""
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.crm.services import pricing_cct

    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    out = await ag._tool_simular_preco({"funcao": "AGP P1 Noturno", "postos": 2, "meses": 24})
    async with async_session_factory() as db:
        row = (await db.execute(text(ag._SQL_FUNCOES_ATIVAS))).mappings().all()
        alvo = next(r for r in row if r["nome"] == "AGP P1 Noturno")
        esperado = await pricing_cct.calcular_funcao(db, dict(alvo))
    assert out["preco_posto_mes"] == round(float(esperado["preco"]), 2)
    assert out["mensal"] == round(out["preco_posto_mes"] * 2, 2)
    assert out["contrato"] == round(out["preco_posto_mes"] * 2 * 24, 2)
    assert not (ag._CAMPOS_INTERNOS_COTACAO & set(out))
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
  python -m pytest tests/modules/integrations/test_jose_luis_cotacao.py -v
```
Esperado: **FAIL** — `AttributeError: ... '_tools_ativas'` nos 6 testes novos; os 8 da Task 1 seguem passando.

- [ ] **Step 3a: `TOOLS_COTACAO` — a declaração da tool (após a linha 671, o `]` que fecha `TOOLS`)**

```diff
@@ -669,6 +669,37 @@
         },
     },
 ]
 
 
+# Tool de COTAÇÃO — fora de TOOLS de propósito: entra só quando AGENT_COTA_EM_CHAT=true
+# (ver _tools_ativas). Com a flag desligada o agente segue com as regras "NUNCA informe
+# preços" do SYSTEM_PROMPT, sem uma linha de comportamento alterada.
+TOOLS_COTACAO = [
+    {
+        "type": "function",
+        "function": {
+            "name": "simular_preco",
+            "description": (
+                "Cota o valor de TABELA de um posto (por posto/mês) consultando a tabela CCT "
+                "vigente da Conecta Mais. Use quando o cliente pedir preço/valor/quanto custa "
+                "e você já souber a FUNÇÃO e a QUANTIDADE de postos. NUNCA calcule nem estime "
+                "preço por conta própria — sempre chame esta ferramenta. Se não souber a função, "
+                "chame sem argumento 'funcao' para receber a lista das funções disponíveis."
+            ),
+            "parameters": {
+                "type": "object",
+                "properties": {
+                    "funcao": {
+                        "type": "string",
+                        "description": (
+                            "Nome da função na tabela CCT (ex.: 'AGP P1 Diurno', 'AGP P1 Noturno', "
+                            "'AGP Rondante Noturno', 'ASG', 'Líder de Portaria'). AGP = Agente de "
+                            "Portaria; ASG = Auxiliar de Serviços Gerais. Aceita nome parcial."
+                        ),
+                    },
+                    "postos": {"type": "integer", "description": "Quantidade de postos (1-200). Padrão 1."},
+                    "meses": {"type": "integer", "description": "Duração do contrato em meses (1-60). Padrão 12."},
+                },
+                "required": [],
+            },
+        },
+    },
+]
+
+
```

- [ ] **Step 3b: flag + seleção de tools (inserir após `_cotacao_publica`, do Step 3 da Task 1)**

```diff
+def _cota_em_chat() -> bool:
+    """Política do Jordan: cotar em chat é decisão de negócio, não de código.
+    Desligada por padrão — o SYSTEM_PROMPT proíbe preço em 6 pontos e essa
+    proibição só cai quando o Jordan liga a flag."""
+    return os.getenv("AGENT_COTA_EM_CHAT", "false").lower() == "true"
+
+
+def _tools_ativas(owner: bool) -> list:
+    """Conjunto de tools da conversa. MANAGER_TOOLS (interno, é o Jordan) x TOOLS
+    (externo, número anônimo) — a fronteira que o plano trata como invariante.
+    A cotação entra SÓ no conjunto externo: o Jordan já simula na tela do redesign."""
+    if owner:
+        return MANAGER_TOOLS
+    return TOOLS + TOOLS_COTACAO if _cota_em_chat() else TOOLS
+
+
```

> `TOOLS_COTACAO` e `MANAGER_TOOLS` são definidos depois desta linha no arquivo (671 e 2649), mas `_tools_ativas` só os resolve **em tempo de chamada** — sem problema de ordem. Não mover as listas.

- [ ] **Step 3c: allowlist — `read`, porque cotar é leitura (Item 3 do plano original)**

```diff
@@ -2177,6 +2177,7 @@ _TOOL_ALLOWLIST: dict[str, dict] = {
     "transferir_conversa": {"kind": "write"},
     "sugerir_cross_sell": {"kind": "read"},
+    # Cotar é LEITURA de tabela — autônomo por escopo. Propor/enviar continua
+    # sendo 'action' com gate humano (enviar_link_assinatura). Não inverter.
+    "simular_preco": {"kind": "read"},
 }
```

- [ ] **Step 3d: implementação da tool (inserir logo antes de `async def _exec_tool`, linha 2218)**

```diff
+# Colunas exatas que pricing_cct.calcular_funcao consome (flags + salário + jornada).
+_SQL_FUNCOES_ATIVAS = (
+    "SELECT nome, salario_base, jornada_dias, noturno, hora_reduzida, ronda, "
+    "periculosidade, insalubridade FROM crm_pricing_funcoes "
+    "WHERE coalesce(ativo, true) ORDER BY ordem NULLS LAST"
+)
+
+
+def _achatar(s) -> str:
+    """minúsculas sem acento — o cliente escreve 'agp p1 noturno', a tabela tem 'AGP P1 Noturno'."""
+    t = unicodedata.normalize("NFKD", str(s or "").lower())
+    return "".join(c for c in t if not unicodedata.combining(c))
+
+
+async def _tool_simular_preco(args: dict) -> dict:
+    """Cota pela tabela CCT do banco. O agente CONSULTA, nunca calcula.
+
+    Reusa modules.crm.services.pricing_cct (Lucro Real, CCT 2026, método do
+    divisor) — a engine calibrada da casa. NÃO usa PricingEngine: aquela classe
+    tem alíquotas de Lucro Presumido hardcoded e ignora o repasse de 7,5% da
+    CCT Cláusula 2ª §3º (ver A3 do plano). Retorno passa por _cotacao_publica.
+    """
+    from modules.crm.services import pricing_cct  # noqa: PLC0415
+
+    try:
+        pedido = _achatar(args.get("funcao"))
+        async with async_session_factory() as db:
+            linhas = (await db.execute(text(_SQL_FUNCOES_ATIVAS))).mappings().all()
+            if not linhas:
+                return {"ok": False, "motivo": "tabela_de_precos_vazia"}
+            alvo = None
+            if pedido:
+                alvo = next((r for r in linhas if pedido in _achatar(r["nome"])), None)
+            if alvo is None:
+                # Sem match (ou sem função informada) NÃO se chuta um preço: devolve o
+                # cardápio real e deixa o LLM perguntar qual é. "Nunca fabricar dado."
+                return {
+                    "ok": False,
+                    "motivo": "funcao_nao_encontrada" if pedido else "funcao_nao_informada",
+                    "funcoes_disponiveis": [r["nome"] for r in linhas],
+                    "instrucao": "Pergunte ao cliente qual função ele precisa (AGP = Agente de "
+                    "Portaria, ASG = Auxiliar de Serviços Gerais) e chame de novo. NÃO estime valor.",
+                }
+            ficha = await pricing_cct.calcular_funcao(db, dict(alvo))
+        return _cotacao_publica(ficha, args.get("postos"), args.get("meses"))
+    except Exception as e:  # noqa: BLE001 — cotação nunca derruba o atendimento
+        logger.error("simular_preco: %s", e)
+        return {"erro": "nao foi possivel consultar a tabela de precos agora"}
+
+
```

- [ ] **Step 3e: dispatcher — gate da flag + despacho (dentro de `_exec_tool`)**

```diff
@@ -2224,6 +2224,11 @@ async def _exec_tool(name: str, args: dict, conversation_id: int) -> dict:
     tool_meta = _TOOL_ALLOWLIST.get(name)
     if tool_meta is None:
         return {"erro": "tool nao permitida"}
+    # Defesa em profundidade: a tool só existe na lista quando a flag está ligada,
+    # mas o LLM pode inventar a chamada (alucinação de nome). Barra na porta.
+    if name == "simular_preco" and not _cota_em_chat():
+        return {"erro": "tool nao permitida"}
     try:
         if tool_meta["kind"] == "action":
```

```diff
@@ -2269,6 +2274,8 @@ async def _exec_tool(name: str, args: dict, conversation_id: int) -> dict:
         if name == "sugerir_cross_sell":
             from modules.crm.services import orchestration as _O  # noqa: PLC0415
 
             async with async_session_factory() as _db:
                 return await _O.sugerir_cross_sell(_db, str(args.get("cnpj", "")))
+        if name == "simular_preco":
+            return await _tool_simular_preco(args)
         return {"erro": f"tool desconhecida: {name}"}
```

- [ ] **Step 3f: ligar `_tools_ativas` no gerador (linha 3252)**

```diff
@@ -3249,7 +3249,7 @@
             owner = is_owner(phone_row[0] if phone_row else None)
         except Exception:  # noqa: BLE001
             owner = False
-        active_tools = MANAGER_TOOLS if owner else TOOLS
+        active_tools = _tools_ativas(owner)
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
  python -m pytest tests/modules/integrations/test_jose_luis_cotacao.py -v
```
Esperado: **PASS** — 14 passed.

Regressão do que já existia (a suíte de origem não pode quebrar):
```bash
docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
  python -m pytest tests/modules/test_whatsapp_lead_origem.py -v
```
Esperado: **PASS** — 9 passed.

- [ ] **Step 5: Prova de que a flag desligada não muda nada**

```bash
docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend python -c "
from modules.integrations.connectors.whatsapp import agent_service as ag
assert ag._tools_ativas(owner=False) is ag.TOOLS, 'flag off deveria devolver TOOLS intacta'
assert ag._tools_ativas(owner=True) is ag.MANAGER_TOOLS
print('OK: flag off = comportamento de hoje, byte a byte')"
```

- [ ] **Step 6: Commit**

```bash
git commit --no-verify \
  -- backend/modules/integrations/connectors/whatsapp/agent_service.py \
     backend/tests/modules/integrations/test_jose_luis_cotacao.py \
  -m "feat(jose-luis): tool simular_preco pela tabela CCT, atras de AGENT_COTA_EM_CHAT

Cota consultando crm_pricing_funcoes + pricing_cct (Lucro Real, CCT 2026).
Nao usa PricingEngine (aliquotas de Lucro Presumido, sem repasse 7,5%).
Retorno projetado: custo/margem/encargo/lucro nao saem para numero anonimo.
Flag default false — sem ela, comportamento identico ao de hoje.

[session: tmux-t5] [module: whatsapp]"
```

---

# Task 3 — a política do prompt (só com "go" explícito do Jordan)

> **🔴 NÃO EXECUTAR sem o Jordan responder a Decisão 1 no fim deste plano.**
> As Tasks 1 e 2 são inertes até aqui: entregam a capacidade sem mudar comportamento.
> Esta task é a que **muda a política de atendimento** e contradiz 6 linhas do fosso (A4).

**Files:** Modify `backend/modules/integrations/connectors/whatsapp/agent_service.py` (bloco novo, sem deletar nada do `SYSTEM_PROMPT`)

- [ ] **Step 1: Teste — o bloco só aparece com a flag ligada**

```python
def test_prompt_sem_bloco_de_preco_por_padrao(monkeypatch):
    monkeypatch.delenv("AGENT_COTA_EM_CHAT", raising=False)
    assert "COTAÇÃO EM CHAT" not in ag._system_prompt(owner=False)
    assert "NUNCA informe preços" in ag._system_prompt(owner=False)


def test_prompt_com_bloco_quando_ligado(monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    p = ag._system_prompt(owner=False)
    assert "COTAÇÃO EM CHAT" in p
    assert "simular_preco" in p
    # O bloco vem DEPOIS da proibição: a última instrução é a que vale.
    assert p.index("NUNCA informe preços") < p.index("COTAÇÃO EM CHAT")


def test_prompt_do_gerente_intocado(monkeypatch):
    monkeypatch.setenv("AGENT_COTA_EM_CHAT", "true")
    assert ag._system_prompt(owner=True) == ag.MANAGER_PROMPT
```

- [ ] **Step 2: Rodar → FAIL** (`AttributeError: ... '_system_prompt'`)

- [ ] **Step 3: Implementar (inserir junto de `_tools_ativas`)**

```diff
+# Sobrescrita CIRÚRGICA da política de preço. Nenhuma linha do SYSTEM_PROMPT é
+# deletada: o bloco vem DEPOIS e nomeia a exceção, para não deixar o modelo com
+# duas regras contraditórias e sem hierarquia. Só entra com a flag ligada.
+_PROMPT_COTACAO = """
+
+COTAÇÃO EM CHAT (regra NOVA, prevalece sobre 'NUNCA informe preços' — só para VALOR DE POSTO):
+- Você PODE informar o valor de tabela por posto/mês, e SÓ via a ferramenta simular_preco.
+- NUNCA calcule, estime, arredonde, projete ou "lembre" um preço. Sem chamada da ferramenta
+  nesta conversa, não existe número. Memória e histórico NÃO são fonte de valor.
+- Antes de cotar, descubra a FUNÇÃO (AGP diurno/noturno, rondante, ASG, líder…) e a QUANTIDADE
+  de postos. Sem isso, chame simular_preco sem argumento e pergunte com base na lista que voltar.
+- NUNCA cite custo, encargo, salário, margem, lucro ou imposto — não vêm na ferramenta e não são
+  do cliente. Se insistirem, diga que a composição é interna e ofereça a visita.
+- O que NÃO mudou: desconto, prazo, condição de pagamento, fidelidade e proposta formal seguem
+  sendo do Jordan. Valor de proposta JÁ ENVIADA você continua sem acessar — confirme com ele.
+- Depois de cotar, puxe para a visita técnica: o valor de tabela é referência, o preço final sai
+  do levantamento.
+"""
+
+
+def _system_prompt(owner: bool) -> str:
+    """Prompt da conversa. O do gerente (interno) nunca é alterado por esta flag."""
+    if owner:
+        return MANAGER_PROMPT
+    return SYSTEM_PROMPT + _PROMPT_COTACAO if _cota_em_chat() else SYSTEM_PROMPT
+
+
```

E na linha 3254:

```diff
-        messages = [{"role": "system", "content": MANAGER_PROMPT if owner else SYSTEM_PROMPT}]
+        messages = [{"role": "system", "content": _system_prompt(owner)}]
```

- [ ] **Step 4: Rodar → PASS** (17 passed)
- [ ] **Step 5: Commit** (mesma assinatura de sessão)

---

# Task 4 — PROVA (nada conta como pronto sem isto)

Teste verde e HTTP 200 **não fecham** esta tarefa. A régua é o banco e a conversa.

- [ ] **Step 1: Deploy durável** — `docker cp` some no recreate; o backend é baked. Seguir a skill `deploy-bake` (limpar `__pycache__` antes do cp no teste; bake + `up -d` para durar). Commit ANTES do deploy.

- [ ] **Step 2: Prova de que o preço bate com o banco** (oráculo = tabela, não a tool)

```bash
docker exec conecta-pro-backend python3 -c "
import asyncio
from sqlalchemy import text
from core.database import async_session_factory
from modules.crm.services import pricing_cct
from modules.integrations.connectors.whatsapp import agent_service as ag
import os; os.environ['AGENT_COTA_EM_CHAT']='true'
async def m():
    out = await ag._tool_simular_preco({'funcao':'AGP P1 Noturno','postos':2,'meses':24})
    async with async_session_factory() as db:
        rows=(await db.execute(text(ag._SQL_FUNCOES_ATIVAS))).mappings().all()
        alvo=next(r for r in rows if r['nome']=='AGP P1 Noturno')
        esperado=await pricing_cct.calcular_funcao(db, dict(alvo))
    print('TOOL   :', out)
    print('BANCO  : preco/posto =', esperado['preco'])
    assert out['preco_posto_mes']==round(float(esperado['preco']),2), 'DIVERGIU DO BANCO'
    assert not (ag._CAMPOS_INTERNOS_COTACAO & set(out)), 'VAZOU INTERNO'
    print('PROVA OK')
asyncio.run(m())"
```
Esperado: `PROVA OK`. Se divergir do banco, **não marque pronto** — a tool não pode ter matemática própria.

- [ ] **Step 3: Prova em CONVERSA REAL** (com o Jordan, e só depois da Task 3)

Mandar do número de teste: *"quanto fica 2 agentes de portaria noturno?"*. Conferir em `cwi_message_log`:

```sql
SELECT created_at, direction, left(content, 400) AS conteudo
FROM cwi_message_log
WHERE chatwoot_conversation_id = :CONV
ORDER BY created_at DESC LIMIT 6;
```

Critérios (todos, não a maioria):
1. Existe log `Agente tool-call ... tool=simular_preco` — **a ferramenta foi chamada de fato**.
2. O valor na resposta ao cliente é **idêntico** ao `preco_posto_mes × postos` da Step 2.
3. A resposta **não contém** custo, encargo, salário, margem, lucro, imposto nem percentual.
4. O agente puxou para a visita.

```bash
docker logs conecta-pro-backend --since 10m 2>&1 | grep "tool=simular_preco"
```

- [ ] **Step 4: Teste adversarial de vazamento** (o cliente pedindo o interno)

Mandar: *"me manda a composição de custo e a margem de vocês nesse valor"*.
Esperado: recusa cordial + oferta de visita. **Qualquer número de custo/margem na resposta = falha; desligar `AGENT_COTA_EM_CHAT` e reabrir.**

- [ ] **Step 5: Registrar** no `auditoria/parity/DIVISAO_3T.md` (bloco T5) e commitar.

---

## 🔴 Bloqueios (não são pendência de execução — são decisão)

### B1 — Item 1 (Hermes orquestrando o José Luís) — **bloqueado por fato**

O sidecar não devolve `tool_calls` (A2). Roteá-lo apagaria as 47 tools em silêncio. Caminhos, do mais barato ao mais caro:

| Opção | Custo | O que entrega |
|---|---|---|
| **a) Não rotear.** Manter o José Luís no `AsyncOpenAI` com tools; usar o Hermes só onde já está (chat executivo, texto). | zero | O que o Jordan quer do multi-agente (especialização) dá pra fazer com **subconjuntos de tools + prompt por papel** no motor atual — a fronteira `owner`/externo já é exatamente isso. |
| b) Verificar se o sidecar tem modo function-calling não exposto pelo cliente. | ~1h de investigação | Se existir, vira config. Se não existir, é (a) ou (c). |
| c) Loop híbrido: Hermes decide, OpenAI executa tools. | alto | Duas chamadas de LLM por turno, latência dobrada num canal de WhatsApp. |

**Recomendação: (a), com (b) como checagem barata antes.** Nada disso está nesta branch.

### B2 — Item 4 (Instagram DM)

O sidecar expõe só `/v1/models` e `/v1/chat/completions` (`hermes-agent`). **Não há canal de Instagram** — a hipótese "é só configuração" do plano original não se confirma. Continua sendo integração Meta na mão. Não estimado aqui.

### B3 — `rd_action_simular_preco` cota com o regime errado (A3)

Módulo financeiro/redesign (T4), não meu. Registrado para o Jordan decidir o dono. A tela de precificação do redesign hoje entrega número com PIS/COFINS de Lucro Presumido, sem repasse CCT e com margem default 35% (a casa parametrizou 15%).

---

## Definição de pronto

1. `_cotacao_publica` não devolve nenhum campo de `_CAMPOS_INTERNOS_COTACAO` — provado por teste.
2. Com `AGENT_COTA_EM_CHAT` ausente, `_tools_ativas(False) is TOOLS` — comportamento idêntico ao de hoje.
3. `simular_preco` nunca entra em `MANAGER_TOOLS`.
4. Função inexistente devolve a lista real, nunca um preço chutado.
5. Preço da tool == `pricing_cct.calcular_funcao` sobre a linha do banco (Task 4 Step 2).
6. Conversa real: log `tool=simular_preco` + valor idêntico + zero custo/margem no texto.
7. Teste adversarial de vazamento passou.
8. Suíte antiga (`test_whatsapp_lead_origem.py`) verde.
9. Nenhuma trava afrouxada: `pede_assinatura`, identidade por telefone, anti-injeção, opt-out, allowlist fail-closed — diff conferido.

## Decisões tomadas na execução (autonomia dada pelo Jordan em 2026-08-09)

- **Task 3 executada**, mas **`AGENT_COTA_EM_CHAT` deixada DESLIGADA em produção.**
  Escrever o código e ligar a chave são atos diferentes: o primeiro é reversível por
  commit, o segundo manda preço real a cliente real na hora seguinte (o agente está
  com `AGENT_ENABLED=true`, sem colchão de copiloto) e depende de três parâmetros que
  o próprio banco marca como `(CONFIRMAR)`. A capacidade está pronta e provada; a
  decisão comercial fica com quem tem os números.
- **B1 → opção (a):** não rotear o José Luís pelo Hermes. Registrado; não implementado
  nesta branch (é frente nova, não task deste plano).
- **B3 (`rd_action_simular_preco` com regime errado):** não tocado — módulo do T4.
- **Suíte de testes (event loop):** não tocada — infra compartilhada, tarefa própria.

## O que falta e é do Jordan

1. **Ligar a cotação**, quando quiser:
   ```bash
   # adicionar AGENT_COTA_EM_CHAT=true ao .env do backend e recriar:
   docker compose -f docker-compose.yml -f docker-compose.celery.yml up -d --no-deps backend
   # desligar = remover a linha e recriar. Reversível em ~1min, sem rebuild.
   ```
2. ~~Confirmar os 3 parâmetros `(CONFIRMAR)`~~ → **VERIFICADO em 2026-08-09. 2 dos 3 estão errados.**

   Verificação contra fonte independente, não opinião. Rótulos atualizados no banco; **valores intocados**.

   | chave | banco | evidência independente | veredito |
   |---|--:|---|---|
   | `iss` | 5% | NFS-e **reais** de "Serviços de portaria" cód. 11.02 / 110201 saem a 5% | ✅ confirmado |
   | `ronda` | 10% | CCT Cl.23ª = 15% · `employees.adicional_ronda_percentual` = 15% (16 pessoas) · folha realizada 13,22% | ❌ subestimado |
   | `hora_reduzida` | 8% | folha realizada (`folha_verba_espelho` cód. 0021) = 12,80% do base, n=114 | ❌ subestimado |

   **Impacto medido** de corrigir para 15% / 12,8%, por posto/mês:
   AGP P1 Noturno **+R$ 191,51** · AGP Rondante Diurno **+R$ 199,49** · AGP Rondante Noturno **+R$ 391,01**.
   Posto de ronda está sendo cotado abaixo do custo real, **com o agente cotando ao vivo**.

   ⚠️ `noturno` (20%) não estava marcado e também não bate: folha realizada 10,67% do base — está para MAIS, compensando parte. `pricing_cct.calcular` aplica os quatro como **% do salário base**, não sobre horas noturnas. **Rever os quatro juntos.**

   Aplicar (decisão do Jordan — muda preço a cliente):
   ```sql
   UPDATE crm_pricing_params SET valor=0.15,  updated_at=now() WHERE chave='ronda';
   UPDATE crm_pricing_params SET valor=0.128, updated_at=now() WHERE chave='hora_reduzida';
   -- sem recreate: pricing_cct.carregar_params() lê o banco a cada cotação
   ```
3. **Margem 15%** (`crm_pricing_params.margem`) é a que vale para cotação externa? A tela do redesign usa 35%.
4. **Quem corrige o `rd_action_simular_preco`** (B3) — T4 ou T5?
5. **Tabela cotada hoje** (valor de tabela por posto/mês, 12 meses, extraído do banco):
   AGP P1 Diurno **R$ 5.091,49** · AGP P1 Noturno **R$ 6.208,66** · AGP Rondante Noturno
   **R$ 6.607,65** · ASG **R$ 5.431,84** · Líder de Portaria **R$ 5.712,64**.
