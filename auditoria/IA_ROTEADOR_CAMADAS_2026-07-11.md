# IA — Migração OpenAI-first + Roteador por camadas — 2026-07-11

## Contexto
Crédito Anthropic zerou; consultores já usavam OpenAI. Decisão do Jordan: toda a
IA no melhor modelo OpenAI (gpt-5), Anthropic vira fallback opcional; e o sistema
deve ESCOLHER o modelo pela situação (avançado quando necessário, básico quando
serve) para economizar sem perder qualidade.

## Fundação — core/llm_cascade.py
- Cascata: OpenAI → Anthropic (só se ANTHROPIC_API_KEY) → None (call site aplica
  fallback honesto: regex/dense/frases prontas). NUNCA fabrica.
- Roteador route/aroute (+_ex): escolhe modelo por TIER de complexidade e ESCALA
  sozinho quando o menor falha/vazio/reprova validação.
  - leve=gpt-5-nano (classificar/resumir) · media=gpt-5-mini (conversa/extração)
    · pesada=gpt-5 (jurídico/licitações/risco). Sobrescrevíveis por LLM_TIER_*.
  - Heurística: entrada grande sobe o tier de PARTIDA (>6k→media, >16k→pesada).
  - valida_json pronto (escala se o JSON vier inválido).
  - gpt-5*/o*: max_completion_tokens (piso 2000) e sem temperature (a API rejeita).

## Call sites por tier (7 arquivos)
| módulo | função | tier | fallback honesto |
|---|---|---|---|
| SOPHIA (gedeon) | embeddings 3-large/1536 + síntese | leve | dense 1536 |
| José Luís (portal WhatsApp) | atendimento | media | frases prontas |
| Parser de currículos (RH) | extração JSON | media (escala p/ JSON) | regex |
| Jurídico — parecer | parecer | pesada | "IA indisponível" |
| Jurídico — análise contrato | análise | pesada | "IA indisponível" |
| Licitações — analyst | análise de edital | pesada | ValueError claro |

## Provas E2E (imagem final)
- Roteador: nano na trivial resolvida no leve; heurística 20k→pesada;
  escalonamento por validação percorre os 3 tiers (leve→media→pesada) até None.
- Call sites: parser=gpt-5-mini ✓, José Luís respondeu (não-fallback) ✓,
  SOPHIA síntese citando holerites reais (motor sophia_v2_openai) ✓,
  jurídico parecer+análise=gpt-5 com JSON ✓, analyst objeto+confiança 88 ✓.
- Degradação honesta (sem chaves): parser→regex, José Luís→frase pronta,
  jurídico→None, SOPHIA→dense. Nada inventado.
- Acervo SOPHIA reindexado 662/662 no espaço OpenAI (3-large/1536).

## Correções de percurso
- Analyst DocumentoNecessario: validator tolerante a chaves EN (name/type...).
- Jurídico: orçamento 8192 (gpt-5 consumia a saída pensando e voltava vazio).
- Embedding 3-large nativo=3072 → dimensions=1536 nas 2 chamadas (índice compat).

## Economia esperada
gpt-5-mini ~5× e nano ~25× mais barato que gpt-5. Na mistura real (muita
conversa/extração, pouca análise pesada), conta ~60-80% menor — pesado só entra
no risco/dinheiro ou quando o barato reprova. Recarregar Anthropic é OPCIONAL
(redundância), não mais necessário para operar.
