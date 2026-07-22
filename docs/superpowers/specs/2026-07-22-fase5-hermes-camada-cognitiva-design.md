# Fase 5 — Hermes Agent como camada cognitiva do Conecta PRO (Design/Spec)

**Data:** 2026-07-22 · **Autor:** Jordan + Claude (brainstorming) · **Status:** design aprovado, aguardando plano de implementação
**Antecede:** Fases −1→4 (identidade dos consultores, dedup de notificação, grafo de entidades, loop de feedback) — todas no ar e provadas.
**Referências:** [[project_hermes_agent_estudo]] (`docs/estudo_hermes_agent_2026-07-21.md`), [[project_consultores_ia_hermes]], [[project_paridade_t4_financeiro_comercial]].

---

## Objetivo (uma frase)
Plugar o **Hermes Agent (NousResearch)** como o motor autônomo por trás dos 8 consultores do ERP — orquestrando-os, agindo proativamente por evento e sob demanda, aprendendo com o uso — **sem nunca poder mover dinheiro sozinho** e **sem substituir nenhuma superfície existente**.

## Arquitetura (2 frases)
O Hermes roda **headless** num container ao lado do backend (cérebro = OpenAI, sem GPU) e conecta ao ERP **como cliente MCP** do nosso conector, que só expõe tools classificadas por risco. As superfícies continuam sendo as nossas — proativo cai no **sino** (Fase 0), on-demand no **chat dos consultores** — e dinheiro/legal só se movem pelo **gate OTP humano** que já existe.

## Tech Stack
Hermes v0.19.0 (headless, API Server OpenAI-compatible) · OpenAI `gpt-5-chat-latest` (+ fallback gpt-5→gpt-4.1→gpt-4o) · FastMCP (conector, 228 tools) · FastAPI backend (`main_production`) · PostgreSQL (`consultor_memorias`, `notification_queue`) · GPEventBus · Docker Compose · volume nomeado p/ memória aprendida.

## Global Constraints (inegociáveis — valem em toda tarefa)
- **Dinheiro que SAI = SEMPRE gate OTP humano.** O Hermes só *propõe*; nunca *executa*. Tools de money-out ficam **fora do conector**.
- **Operacional (postos/escalas) e dossiê Jurídico = READ-ONLY.** Nenhum caminho de escrita externa.
- **Nunca fabricar dado.** Vazio real = "aguardando dado".
- **Jordan = fonte da verdade** organizacional.
- **PII contida no ERP.** Memória do Hermes na nossa infra; retrato de entidade gated a CEO.
- **Deploy:** backend blue-green (`scripts/deploy_backend_bluegreen.sh`); baked na imagem (docker cp = volátil). `.env` na raiz `/opt/conecta-pro/.env`.
- **Degradação graciosa:** Hermes é aditivo; se cair, os consultores respondem direto pelo `consultor_hub`.

---

## As 6 decisões que travam o design
1. **Alvo:** Hermes real no ar, fim a fim (não blueprint, não só ponte).
2. **Acionamento:** on-demand (você chama) **+** proativo por evento (GPEventBus). Sem cron por ora.
3. **Canal:** dentro do ERP — proativo no **sino**, on-demand no **chat dos consultores**. Hermes headless por trás.
4. **Raio de ação:** ler + propor + **auto de baixo risco**; dinheiro/legal/operacional = gate + OTP.
5. **Abertura:** os **8 consultores** desde o dia 1.
6. **Aprendizado:** os **dois cérebros aprendem juntos** (Hermes + Fase 4 do ERP), com guarda LGPD.

---

## Bloco 1 — Arquitetura de alto nível

O Hermes é o motor; o ERP é a casa. Nunca aparece "de fora".

```
VOCÊ ──on-demand──▶ chat dos 8 consultores (UI existe) ──▶ BACKEND ──ponte HTTP──▶ HERMES
VOCÊ ◀──proativo──── SINO / notification_queue (Fase 0) ◀── enqueue_alert ◀────────── HERMES
                                                                    ▲
BACKEND: GPEventBus (Item −1) ──evento──▶ ponte Hermes ────────────┘

HERMES (container headless, OpenAI, memória em volume, .hermes.md, approvals.deny)
   └─ é CLIENTE MCP ─▶ CONECTOR MCP (só tools classificadas 🟢🔵🟡)
                          └─▶ consultor_hub.py + dados reais (grafo de entidades, Fase 4)

dinheiro/legal proposto ──▶ pendente ──▶ gate OTP ──▶ VOCÊ aperta
```

Pontos-chave: reaproveita sino (Fase 0), GPEventBus (Item −1), grafo+feedback (Fase 4), conector MCP. Duas portas pro Hermes (chat + evento), mesma engine. O conector é a fronteira de segurança. Container headless na nossa infra = 1ª camada da guarda LGPD.

---

## Bloco 2 — Taxonomia de risco das tools (coração da segurança)

**A fronteira perigosa é estática e humana, não um palpite de IA em tempo real.**

### 4 classes (toda tool nasce carimbada; sem carimbo = 🔴 = não exposta — fail-closed)
| Classe | O que é | Hermes pode? | Exemplos |
|---|---|---|---|
| 🟢 READ | consulta/análise, zero mudança de estado | auto | `consultor_*`, aging, `contexto_entidade` |
| 🔵 WRITE-baixo | interno, reversível, sem efeito externo em dinheiro/gente | auto | criar nota, marcar tarefa, rascunhar doc, `registrar_feedback` |
| 🟡 PROPOR | cria **pendente** que só humano executa c/ OTP | propõe, não executa | `propor_pagamento`, `propor_comunicado` |
| 🔴 EXECUTAR dinheiro/legal/operacional | move dinheiro / ato externo irreversível / altera escala | **não existe no conector** | mandar PIX, protocolar, editar alocação |

### 4 paredes de defesa em profundidade
0. **Exposição** — 🔴 simplesmente não está no conector. Não se chama o que não existe.
1. **Carimbo + allowlist** — `risk_class` no metadata; ponte só entrega 🟢🔵🟡 (`tools.include`). Sem classe = 🔴.
2. **approvals.deny do Hermes** — nega 🟡 de auto-disparar → força proposta→humano.
3. **Gate OTP downstream (não-bypassável)** — 🟡 só cria pendente; dinheiro só se move com seu OTP. Nenhuma camada de software do Hermes atravessa.

### Mata a preocupação com o classificador
A lista 🔴/🟡 é escrita à mão, versionada. O smart-approval (IA de risco do Hermes) é camada **extra** (Parede 2), nunca a principal — se errar, a Parede 3 (OTP) segura, ou ele pergunta à toa (falha pro lado seguro). Um `tool_risk_manifest` + lint de CI quebra o build se tool nascer sem classe.

---

## Bloco 3 — Os 8 consultores como tools MCP

Risco concentrado numa família pequena e explícita, não espalhado por 8×N tools.

### Família A — Consulta (🟢, uma por consultor)
`consultor_ceo` (executivo; único que puxa retrato de entidade, gated) · `consultor_cfo` (financeiro) · `consultor_juridico` (**READ-ONLY**) · `consultor_dp` (RH/folha/ponto/CCT) · `consultor_fiscal` (notas/guias/regime) · `consultor_comercial` (CRM/funil) · `consultor_operacional` (**READ-ONLY**) · `consultor_ged` (documentos/kits/Sophia).

Cada uma roteia pro `consultor_hub` com a origem certa + contexto de entidade.

### Família B — Ação (compartilhada)
| Tool | Classe | Efeito |
|---|---|---|
| `criar_nota` | 🔵 | nota interna reversível |
| `marcar_tarefa` | 🔵 | tarefa/lembrete interno |
| `rascunhar_documento` | 🔵 | rascunho (nunca envia) |
| `registrar_feedback` | 🔵 | correção → memória permanente (**realimenta Fase 4**) |
| `propor_pagamento` | 🟡 | PIX pendente → OTP |
| `propor_comunicado` | 🟡 | comunicado/holerite pronto → aprovação p/ enviar |

### 🔴 fora do conector
`mandar_pix`/executar pagamento (só OTP) · `editar_alocacao`/escala (operacional é curado à mão) · `protocolar_peticao` (humano protocola; Hermes no máximo rascunha 🔵).

Isso honra operacional e dossiê jurídico read-only sem exceção. Superfície de risco = ~6 tools de ação, auditável num olhar.

---

## Bloco 4 — Os dois fluxos + o propose→approve→OTP

### Fluxo on-demand
chat → ponte (HTTP) → Hermes escolhe tools 🟢 (cruza no grafo) → se sugerir agir, `propor_*` 🟡 cria pendente (não executa) → resposta streaming no chat. Mesmo no pull, dinheiro para em "pendente".

### Fluxo proativo
GPEventBus emite evento → **regras de gatilho** filtram (threshold curado) → ponte chama Hermes → investiga com tools 🟢 → (a) acionável: `enqueue_alert` (Fase 0, idempotente) → sino, com proposta 🟡 anexa opcional; (b) não: silencia + loga.

### Reuso do gate (sem tela nova)
`propor_pagamento` → pendente na tela de **pagamentos** → OTP (fluxo atual). `propor_comunicado` → rascunho na tela de **comunicados** → aprovar. O Hermes só *alimenta* as filas que você já revisa.

### 4 travas do proativo
1. **Regras de gatilho curadas** — nos **8 domínios** desde o dia 1, cada uma com threshold (não é todo evento).
2. **Dedup por `correlation_id`** — Fase 0 garante idempotência.
3. **Teto de vazão (rate-limit + debounce)** — tempestade de eventos não spamma o sino nem queima token.
4. **Anti-loop** — ação do próprio Hermes não re-emite evento no GPEventBus; eventos de origem Hermes são marcados e nunca realimentados.

---

## Bloco 5 — Aprendizado, memória, guarda LGPD

### Dois cérebros
- **Memória do ERP (Fase 4, existe):** `consultor_memorias` (Postgres); correção → memória permanente lida pelos 8 consultores via `contexto_compartilhado`.
- **Memória do Hermes (nova):** MEMORY.md / USER.md + skills, **em volume nosso**; aprende teu jeito, fatos da org, workflows.

### Join (uma correção, dois lugares)
Você corrige no chat → Hermes chama `registrar_feedback` 🔵 (grava em `consultor_memorias` → os 8 consultores sabem) **e** persiste em USER.md/skill dele. Sem esforço seu — é só conversar.

### Constituição re-injetada
`.hermes.md` (baked) injetado no tier estável a **cada** sessão, com os inegociáveis (OTP, read-only, não fabricar, fonte da verdade, 2 CNPJs, CCT, raias). O Hermes não consegue "esquecer" as regras — voltam sempre.

### 5 travas LGPD da memória do Hermes
1. **Contenção física** — arquivos na nossa infra, nunca saem.
2. **Redação na persistência** — memória durável guarda padrão/preferência, não PII crua (strip CPF/CNPJ/valores/nomes na gravação; sessão pode segurar de passagem).
3. **Retrato de entidade gated a CEO** — cruzamento dinheiro+legal+gente só na origem `ceo` (Fase 4).
4. **Inferência sem treino** — OpenAI só infere; zero-retention; acervo local.
5. **Expiração** — Curator nativo (staleness/arquiva) + purge manual (direito ao esquecimento).

---

## Bloco 6 — Infra, deploy, modelo

- **Serviço `conecta-pro-hermes`** — headless (só API Server OpenAI-compat, chamado pela rede interna), persistente (listener + memória), `mem_limit 2g` (cérebro externo = leve; cap por OOM).
- **Baked vs volume:** semente (`.hermes.md`, skills iniciais, config) **baked na imagem**; memória **aprendida** em **volume nomeado** (sobrevive a rebuild). `docker cp` = volátil.
- **Cérebro:** OpenAI, sem GPU. `gpt-5-chat-latest` + fallback. Chave + token MCP na **raiz `.env`**. Zero-retention.
- **Fiação MCP:** `config.yaml` → `mcp_servers.conecta_pro.url = http://conecta-pro-mcp:8788/mcp` + `tools.include` só 🟢🔵🟡 (Parede 1 na prática).
- **Degradação graciosa:** hoje os 8 consultores já respondem via `consultor_hub` direto; a ponte tem health-check e cai pro direto se o Hermes morrer. Hermes é **aditivo, não SPOF**.
- **Recurso:** `mem_limit` + earlyoom/guardian (OOM v2). Hermes reinicia sozinho sem tocar no backend.

---

## Bloco 7 — Rollout (risk-first, cada fase testável sozinha)

- **5.0 Fundação:** `tool_risk_manifest` classifica as 228 + novas; lint fail-closed; confirma 🔴 ausente. *Sem Hermes.* ✔ lint passa, toda tool classificada.
- **5.1 Tools MCP (2 famílias) — sem Hermes:** 8 `consultor_*` 🟢 + ~6 ações 🔵🟡; 🟡 escrevem nas filas de pendente existentes. ✔ cliente MCP burro: 🟢 lê, 🟡 cria pendente visível na tela de aprovação, 🔴 não existe. *Parte perigosa validada em isolado.*
- **5.2 Hermes headless + MCP + degradação:** sobe container; ponte + health + fallback. ✔ on-demand passa pelo Hermes; mata Hermes → chat ainda responde. *"Real no ar" no pull.*
- **5.3 Proativo + 4 travas:** subscriber GPEventBus (8 domínios); anti-loop + dedup + rate-limit. ✔ evento sintético → sino ou silêncio; duplicado → sem dobro; origem-Hermes → sem loop.
- **5.4 Aprendizado + LGPD:** liga memória (volume) + join → Fase 4; scrubber + purge + Curator. ✔ correção cai nos dois cérebros; memória durável sem PII crua.
- **5.5 Endurecimento + E2E:** passe adversarial (disparar dinheiro sem OTP, vazar PII, loop, drift); E2E pela **rota da tela**; blue-green, baked. ✔ nenhum ataque passa; verde na rota real.

**Ordem:** superfície perigosa provada sem IA (5.1) → pull antes do push → aprendizado por último (memória acumula) → endurecimento como fase própria (padrão antídoto).

---

## Testabilidade / oráculos
- Verificar **pela rota da tela** (grep `fetch(` na página → HTTP naquela rota com payload do form). Rota in-process com dict-cru dá falso PASS.
- Oráculo do dado real: exibido == banco (curl vs query). Nunca fabricar.
- Produção roda `main_production:app` (prefixos diferem de `main.py`).

## Fora de escopo (Fase 5)
- Cron/briefings agendados (acionamento 3 não escolhido).
- GPU / raciocínio 100% local (cérebro é OpenAI).
- Canal de mensagem externo (WhatsApp/Telegram) — tudo dentro do ERP.
- Auto-execução de dinheiro/legal/operacional — permanentemente 🔴.

## Riscos abertos / a decidir no plano
- Conteúdo exato das **regras de gatilho** por domínio (thresholds) — a curar com Jordan na 5.3.
- Formato do `tool_risk_manifest` (arquivo declarativo vs decorator na tool).
- Detalhe do scrubber de PII (regex CPF/CNPJ/valores + lista de nomes) na 5.4.
