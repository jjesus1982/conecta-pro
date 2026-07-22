# Conecta PRO — Plataforma Agêntica (Fase 5.2+): Visão de Plataforma
**Data:** 2026-07-22 · Síntese de 3 frentes de pesquisa (inventário de capacidades · catálogo de casos de uso · arquitetura SOTA). Base: Hermes (NousResearch, MIT) sobre a superfície MCP + 4 paredes já deployadas (Fase 5.1).

---

## 1. A oportunidade (fundamentada, não hype)
O homework revelou que o Conecta PRO **já tem a parte cara pronta**:
- **~230 "verbos de ação"** mapeados no backend (endpoints/serviços que EXECUTAM algo), + ~130 leituras. Distribuição de risco: **~70 🔴** (dinheiro/legal-externo/escala), **~55 🟡** (propor-pendente), **~105 🔵** (interno reversível).
- **239 tools MCP** já expostas + 8 consultores C-level (hoje só conversam).
- **Event bus central já emitindo eventos** (`ConectaEventBus`/GPEventBus, Redis Streams): DP/folha/ponto/operacional/financeiro/SST/GED/fiscal/gov/CRM/CCT — o GEDEON já reage a ~30 eventos. É a fundação do modo proativo, **pronta**.
- **100+ casos de uso de alto valor** catalogados por papel (operacional, DP, CFO, jurídico, fiscal, comercial, dono).

**Tradução:** o dado e os "verbos" existem. O que falta é o **cérebro** (orquestração + tool-calling encadeado + proativo por evento + memória + multi-agente) e a **camada de garantia** que separa "brinquedo de demo" de "plataforma de grande player".

## 2. A realidade em 3 camadas
| Camada | Estado | O que é |
|---|---|---|
| **Dado** (ler) | ✅ **Pronto** (com poucos gaps de plumbing) | aging, caixa Inter ao vivo, folha-CCT, processos, escala, notas, kits… |
| **Verbos** (agir) | ✅ **Pronto** (~230 funções) | pagar (Inter+OTP), emitir NFS-e/CND, fechar folha, escalar substituto, enviar proposta… |
| **Cérebro + Garantia** | ❌ **A construir** | orquestração multi-agente, propor→aprovar, proativo por evento, memória curada, **evals/groundedness, observabilidade, guardrails** |

**Gaps de plumbing a fechar incrementalmente (por caso de uso):** `shifts` turno-a-turno não é lido pelo panorama COO (o "escala do posto hoje"); custo de diaristas isolado do CFO; **faltam famílias de evento** `juridico.*`, `licitacao.*`, `recruitment.*`, `financeiro.aging.*` (sem elas o Hermes consulta mas não *reage* a prazo/inadimplência).

## 3. Arquitetura de referência (o "monstro", classe mundial)
Padrão consolidado 2026 (Anthropic multi-agent, OpenAI Agents SDK, LangGraph): **hierárquico + blackboard.**

```
ORQUESTRADOR DE TOPO (Hermes)  — roteia por intenção/módulo · teto de iteração · budget por tarefa
        │ (hierárquico)                          │ (blackboard = GPEventBus)
   Sub-supervisores por ÁREA              eventos do ERP → o cérebro REAGE
   Fin · Fiscal · DP · Op · Com                  (nota emitida, folha fechada, posto descoberto)
        │
   ┌────┴─────────────┬───────────────────┐
 Leitores          Executores          Consultores C-level
 (read-only,       (write GATED,        (8 lentes, read + propõe)
  proveniência)     OTP p/ dinheiro,
                    idempotency key)
   ────────────────────────────────────────────
   Tools: NATIVAS (core, alta freq) + MCP (conector 228, externos)
          dinheiro-que-sai FORA do MCP · least-privilege por agente
   ────────────────────────────────────────────
   CAMADA DE GARANTIA (o que faz "grande player"):
   evals+groundedness como GATE de deploy · OTel-GenAI → Langfuse ·
   roteamento de modelo por complexidade (llm_cascade) + budget ·
   auditoria append-only · memória curada (Curator + human-gate legal)
```

**Regra de ouro (anti-multi-agente prematuro):** começar como **1 orquestrador + tools**; só fatiar em sub-agentes quando o prompt ficar ambíguo, as tools passarem de ~15-20, ou a permissão exigir. A plataforma é multi-agente-**ready** desde o dia 1, mas não se super-fragmenta cedo.

## 4. Os 4 pilares que separam "grande player" de "brinquedo" (e que o Hermes NÃO traz prontos)
1. **Evals + groundedness como gate de deploy** — golden set (~30 casos) rodando <5min no blue-green; todo número exibido rastreável a uma linha do banco (`exibido==banco` automático); "aguardando dado" testado como resposta correta (nunca inventar). **É o antídoto arquitetural contra alucinação.** É a maior lacuna a construir.
2. **Observabilidade OTel-GenAI → Langfuse** — span por passo (LLM/tool/retrieval), custo por token (input≠output), trajetória auditável. Sem isso não se depura nem se otimiza.
3. **HITL calibrado por reversibilidade** — 3 tiers: 🟢 auto (read) · 🔵 aprova-e-lembra (write reversível) · 🔴 **sempre-gate+OTP** (dinheiro/legal, nunca aprendível). O agente prepara tudo e para no último milímetro; humano aprova ato pronto e conferível.
4. **Memória curada + confiabilidade** — memória de 2 tiers (auto-curada operacional vs human-gated legal/financeiro), com `as_of` e "cache≠verificado"; idempotency key em toda ação (anti PIX-dobro); fallback de provider; degradação honesta (falha > invenção).

## 5. Roadmap faseado (sem retalho — cada fase é software que roda e se prova)
- **5.2 — Fundação viva + quick wins (interno):** sobe o Hermes headless (OpenAI, sem GPU), plugado no conector MCP; **orquestrador + os consultores como tools**; roteamento de modelo (llm_cascade); **camada de garantia mínima já embutida** (groundedness gate + OTel spans + auditoria); degradação graciosa. Entrega **os primeiros quick-wins on-demand** (ex.: briefing executivo, "posso contratar 3 porteiros?" multi-domínio, runway ao vivo). Prova o loop com risco contido.
- **5.3 — Proativo por evento:** liga o GPEventBus ao cérebro (blackboard); as regras de gatilho por domínio; fecha os **gaps de evento** (juridico/aging/recruitment) e o plumbing crítico (shifts→COO). Entrega os **alertas proativos** (posto descoberto + 3 substitutos, inadimplência, prazo/certidão vencendo, obrigação fiscal).
- **5.4 — Ações propor→aprovar em escala:** expande os verbos 🟡/🔴 como tools gated (cobrança, lote de pagamento, substituição, faturamento de kit, proposta comercial, eSocial) com o guardrail de saída determinístico e a idempotência. Aqui o José Luís é **promovido** a agente cliente-facing (allowlist mínimo, anti-injeção).
- **5.5 — Memória que aprende + evals contínuos:** write-back curado (Curator + human-gate legal), golden set como gate de deploy, monitoramento em produção (amostra + rollback canário).
- **5.6 — Moonshots:** Torre de Controle Operacional Autônoma · CFO Autônomo (fechamento de mês orquestrado) · Radar de Churn preditivo · Copiloto de Licitações · Compliance Trabalhista Blindado.

## 6. Casos de uso — os 15 quick-wins e os 5 moonshots (do catálogo)
**Quick wins (dado/verbo já existem, Hermes só encadeia):** posto descoberto+3 substitutos · briefing executivo matinal · follow-up comercial que nunca esquece · aging→lote de cobrança · alerta obrigação fiscal · alerta contrato/certidão vencendo · runway ao vivo · "posso contratar 3 porteiros?" (multi-agente) · simulação de holerite CCT · José Luís envia proposta completa · férias vencendo · custo de diaristas vs orçado · margem por condomínio · ronda vencida · eSocial pendente.

**Moonshots (nível grande player):** Torre de Controle Operacional Autônoma (prevê buraco de posto e pré-negocia substituto) · CFO Autônomo (fecha o mês) · Radar de Churn preditivo cross-domínio · Copiloto de Licitações fim-a-fim · Compliance Trabalhista Blindado (aponta passivo antes da reclamatória).

## 7. Decisões grandes (a shapar com o Jordan)
1. **Ambição do 5.2:** fundação + garantia + quick-wins on-demand (recomendado) vs ir direto a um moonshot.
2. **Quanto da "camada de garantia" já no 5.2:** evals/groundedness + observabilidade desde o início (recomendado — é o "sem retalho") vs adicionar depois.
3. **Multi-agente:** plataforma multi-agente-ready mas operando como orquestrador+tools primeiro (recomendado) vs N agentes já.
4. **José Luís/WhatsApp:** interno primeiro; José Luís promovido a agente cliente-facing na 5.4 com allowlist mínimo (recomendado) vs migrar já.
5. **Custo/modelo:** llm_cascade (nano/mini/gpt-5 por complexidade, dinheiro/legal sempre gpt-5) + budget por tarefa — uma OPENAI_API_KEY.

## Resumo de 1 linha
O dado e os ~230 verbos já existem; a Fase 5.2+ constrói o **cérebro orquestrador + a camada de garantia (evals/groundedness/observabilidade/HITL)** sobre o Hermes — faseado (fundação→proativo→ações→aprende→moonshots), respeitando as 4 paredes, pra levar o Conecta PRO ao nível dos grandes players sem retalho.
