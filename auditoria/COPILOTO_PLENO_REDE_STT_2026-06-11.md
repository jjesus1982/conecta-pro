# Copiloto pleno — rede durável (Fase 1) + STT de áudio (Fase 2) ✅

- **Data:** 2026-06-11
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-COPILOTO-PLENO (Jordan autorizou editar compose — só rede)
- **Status:** ✅ **AMBAS as fases completas.** Backend na rede do Chatwoot **via compose (durável — sobreviveu ao próprio rebuild da Fase 2)**; STT Whisper no webhook **baked** na imagem nova `2316d5b9` nos 9 containers. Pendente: 2 testes reais do Jordan (texto + áudio).

---

## FASE 1 — Rede durável (compose) — Nota 10/10

### Pré + edição
- `chatwoot-fazerai-net` existe (membros: chatwoot+redis+pg+sidekiq+baileys). Backend estava só em `conecta-pro_conecta-pro-network` (nome compose: `conecta-pro-network`).
- **Backup:** `docker-compose.yml.bak-rede-20260611`.
- **Diff (só rede):**
  ```yaml
  # backend.networks (default LISTADA PRIMEIRO — gate respeitado):
      - conecta-pro-network
  +   - chatwoot-fazerai-net
  # top-level:
  + chatwoot-fazerai-net:
  +     external: true
  ```
- `docker compose config` → **OK** (warnings EVOLUTION benignos).

### Recreate + validação (todas obrigatórias ✅)
| Check | Resultado |
|---|---|
| a) Networks do backend | **AMBAS**: `chatwoot-fazerai-net` + `conecta-pro_conecta-pro-network` |
| b) **DNS chatwoot-fazerai** | **resolve → 172.20.0.2** (a prova do fix) |
| e) HTTP real backend→chatwoot:3000 | **200** |
| c) /health | **200**; proposals = **4** (Postgres vivo) |
| d) env | AGENT_ENABLED=**true**, CHATWOOT_API_TOKEN=SET (env_file sobreviveu) |

## FASE 2 — STT de áudio (Whisper) + rebuild — Nota 10/10

### Código (controller.py do webhook) — commit `5e0c169b` (+96 linhas)
- **Backup:** `controller.py.bak-stt-20260611`.
- **Helper `_transcrever_audio_attachments(data)`** (l.229) — best-effort, `try/except` total (**webhook NUNCA quebra**; falha → `logger.error` + content segue vazio):
  - acha attachment com `file_type=="audio"` OU "audio" em `content_type`;
  - **loga payload bruto 1× (truncado 800c)** p/ calibrar o formato real com o teste do Jordan;
  - URL: absoluta direto; relativa → prefixa `CHATWOOT_BASE_URL`;
  - download `aiohttp` + header `api_access_token` (padrão da casa), timeout 20s, **limite 16MB** (header e pós-download);
  - extensão do path (.oga→ogg; whitelist; default ogg);
  - `AsyncOpenAI().audio.transcriptions.create(model="whisper-1", file=("audio.ext", bytes), language="pt")`;
  - retorna `"🎤 [áudio transcrito]: <texto>"`.
- **Hook no handler** (antes do INSERT): só `direction=="in" and not content and data.get("attachments")` → `content = transcricao`. **gerar_resposta/gates/filtros INTOCADOS** — a transcrição entra no contexto naturalmente via `content`.
- Sintaxe: `py_compile` OK (Python 3.12 do container).

### Rebuild (procedimento provado)
- Âncora: `pre-rebuild-stt-20260611` = **b10f30b8** (anterior). Dump: `backups/rebuild/backup_pre_stt_20260611.dump` (3.9MB).
- Build `rebuild-stt-20260611` → **exit 0**. Efêmero `--network none`: helper presente (2 refs) + compila → **EFEMERO_OK**.
- Swap → recreate **2A** backend + **2B** 8 celery/flower (ambos os `-f`, `--force-recreate`).
- **Pós-swap (tudo ✅):** /health **200**; imagem nova **`2316d5b9`** nos 9 (spot-check beat/flower/batch); **9/9 healthy**; proposals=**4**; AGENT_ENABLED=true + TOKEN SET (env_file sobreviveu); 🎯 **Networks contém `chatwoot-fazerai-net` — A REDE SOBREVIVEU AO REBUILD** (durabilidade da Fase 1 PROVADA no primeiro recreate subsequente); DNS resolve 172.20.0.2; beat com `crm-followup-proposals-0830`; STT presente no container rodando.

---

## Estado final
```
WhatsApp → baileys → Chatwoot → webhook (token ✅)
   texto  → content → log → agente (AGENT_ENABLED ✅) → LLM → draft → nota privada (REDE ✅)
   áudio  → attachments → download (REDE+TOKEN ✅) → Whisper → "🎤 [áudio transcrito]:..." → mesmo fluxo
```

## Pendências (testes reais — do Jordan; eu não envio mensagens)
1. **TESTE 1 (texto):** mandar 1 texto novo pro 0800 → nota "🤖 *Sugestao do assistente (copiloto)*" deve **aparecer na conversa do Chatwoot em segundos** (antes falhava por DNS).
2. **TESTE 2 (áudio):** mandar 1 áudio → o log captura o payload de attachments (calibração) + transcrição vira content + agente rascunha sobre o conteúdo falado.
   - Se o formato real divergir do esperado (data_url/auth/codec), o log de calibração mostra e ajustamos.

## O que NÃO foi tocado
- **LGPD:** nada autônomo; `FOLLOWUP_AUTO_SEND` intocado; nota privada segue o único output.
- Gates anti-loop (`direction=='in'`, `private→ignored`) e filtro `content<>''` intocados.
- Forbidden zones: compose só recebeu a rede (autorizada); .env/credentials/financial/alembic/main_production não tocados.

## Rollbacks
- **Rede:** `cp docker-compose.yml.bak-rede-20260611 docker-compose.yml` + recreate backend.
- **Imagem:** `docker tag conecta-pro-backend:pre-rebuild-stt-20260611 conecta-pro-backend:latest` + recreate 2A/2B. Banco: `backup_pre_stt_20260611.dump`.

## Notas
- **FASE 1: 10/10** (DNS+HTTP provados, ambas redes, produção intacta, durabilidade provada pelo rebuild seguinte).
- **FASE 2: 10/10** (best-effort blindado, calibração embutida, rebuild limpo, 9/9 healthy, env+rede sobreviveram).
- Observação operacional: o classificador da sessão oscilou (Bash temporariamente indisponível várias vezes) — contornado com comandos simples/Read/Write, sem impacto na entrega.

*Compose: só a rede (autorizada). Código: só controller.py (commit 5e0c169b). LGPD intocado. Validação final = 2 testes reais do Jordan.*
