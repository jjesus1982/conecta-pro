# Chesterton — recepção de ÁUDIO no agente WhatsApp (STT) — READ-ONLY

- **Data:** 2026-06-10 (gerado 2026-06-11)
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Token:** STEP-0-AUDIO-RO
- **Modo:** 100% READ-ONLY — nada escrito/buildado; nenhuma chamada de API.

---

## a) O áudio CHEGA no webhook? Em que formato? Há registro real?
- **O webhook NÃO lê áudio hoje.** `controller.py:229` `chatwoot_webhook` extrai só `content = data.get("content")` (l.263) e `message_type` (l.264, usado **só p/ direção** in/out — não é tipo de mídia). **Nunca lê `data["attachments"]`** (grep `attachment|data_url|file_type|audio|voice` no connector inteiro = **zero**).
- **Não quebra:** numa mensagem de áudio o Chatwoot manda `content` vazio + o áudio em `attachments[].data_url`. O webhook loga `content=None` (coluna nullable) → **sem crash** (STEP g), mas o áudio é **silenciosamente descartado**.
- **Registros reais:** `cwi_message_log` tem **16 entradas**, **2 sem texto** (msg_id 53 e 55, phone `9284393279`, 2026-06-09) — **candidatos a áudio/mídia**, mas o attachment **não foi capturado** (só sabemos que `content` ficou vazio). **Não dá pra ver o formato bruto pelo nosso log.**
- 🔴 **GATE:** precisamos de **um áudio real de teste** (Jordan manda um áudio pro 0800) para capturar o `attachments` exato (URL? auth? .oga/opus?). O log atual não preserva isso.

## b) Onde engatar o STT no fluxo
- **Fluxo atual:** webhook → loga em `cwi_message_log` → (se `direction=in` e agente on) agenda `agent_service.processar_incoming(conv_id, phone)` (BackgroundTask, roda **no backend**, não celery).
- `processar_incoming` (l.654) → `gerar_resposta(conv_id)` → `_log_draft` + `_post_private_note`.
- `gerar_resposta` (l.470) **lê o histórico do PRÓPRIO `cwi_message_log`** (l.486-489):
  ```sql
  SELECT direction, content FROM cwi_message_log
  WHERE chatwoot_conversation_id=:c AND direction IN ('in','out')
    AND content IS NOT NULL AND content <> ''   -- <- FILTRA vazios (exclui áudio!)
  ```
  → o áudio (content vazio) é **excluído duas vezes**: webhook não extrai + query filtra `content<>''`.
- **🎯 Melhor ponto de inserção (menor risco) = no WEBHOOK** (`controller.py`, antes do INSERT): se `data.get("attachments")` tiver item de áudio → baixar `data_url` → Whisper → **gravar a transcrição em `content`**. Aí o fluxo do agente **fica intocado** (ele já lê `content` do log). O texto do agente que já funciona não é tocado.
- Alternativa (agent_service): mais invasiva (o agente lê do log, não do Chatwoot) — **não recomendada**.

## c) cwi_message_log tem onde guardar transcrição + referência ao áudio?
- Colunas: `id, direction, phone_canonical, chatwoot_conversation_id, chatwoot_message_id, content (text), client_id, lead_id, status, created_at`. **Sem coluna de mídia/attachment/media_url/message_type.**
- **Transcrição cabe em `content`** (text) → suficiente p/ o agente entender (MVP, **sem migration**).
- **Para preservar referência ao áudio original + marcar "é áudio"** → precisaria coluna(s) nova(s) (`media_url`, `message_type`/`is_audio`) → **migration sprint95** (com a disciplina: backup, rev id ≤32 chars, dry-run). **Opcional** — não bloqueia o MVP.

## d) STT — Whisper viável?
- **openai SDK 2.38.0** no container → `client.audio.transcriptions.create` **existe** (confirmado `Transcriptions.create`). ✅ Mesmo SDK do chat (`from openai import AsyncOpenAI`, `gerar_resposta` l.506).
- **`OPENAI_API_KEY` = SET (164 chars)** no backend → serve p/ Whisper (mesma chave). ✅
- **ffmpeg = AUSENTE** no container. WhatsApp manda voice **ogg/opus** — **a Whisper API aceita `ogg` direto** (formatos: mp3/mp4/mpeg/mpga/m4a/wav/webm/**ogg**/flac). → **ffmpeg provavelmente NÃO é necessário** (enviar o .oga/ogg direto). Se o container vier `.oga` com codec problemático, aí sim precisaria ffmpeg — **confirmar no teste real**.

## e) Como baixar o áudio (URL Chatwoot + auth)?
- Cliente HTTP do agente = **`aiohttp`** (`_post_private_note` l.619-633), header **`api_access_token: <token>`**, base `CHATWOOT_BASE_URL` (default `http://chatwoot-fazerai:3000`), account `CHATWOOT_ACCOUNT_ID` (1). **Reusável** p/ baixar o `data_url`.
- O `data_url` do Chatwoot normalmente é interno (`/rails/active_storage/...` ou `http://chatwoot-fazerai:3000/...`) → pode exigir o `api_access_token`. **Confirmar no teste real.**

## f) 🔴 BLOQUEADOR PRÉ-EXISTENTE (precede a tool — e talvez regressão do rebuild de hoje)
- `agent_enabled()` (l.72) = `os.getenv("AGENT_ENABLED","false")=="true"`. **`AGENT_ENABLED` está UNSET** no backend **e** no celery-operacional → **o copiloto NÃO seria agendado hoje** (o `if ... agent_enabled()` no webhook fica False).
- **`CHATWOOT_API_TOKEN` UNSET** no backend (e sem `/app/.chatwoot_token`) → `_post_private_note` aborta ("token ausente") e **não há como baixar o áudio do Chatwoot**.
- **Causa:** `AGENT_ENABLED`, `CHATWOOT_API_TOKEN` e `WHATSAPP_WEBHOOK_SECRET` aparecem **ZERO vezes** em `docker-compose.yml` E `docker-compose.celery.yml`. O backend usa `environment:` **explícito** (não `env_file: .env`) que injeta OPENAI_API_KEY (SET) mas **omite** essas três. O `.env` **tem** todas (AGENT_ENABLED/CHATWOOT_API_TOKEN/CHATWOOT_BASE_URL/WHATSAPP_WEBHOOK_SECRET/OPENAI_API_KEY presentes), mas o compose **não as referencia**.
- **Possível regressão:** os rebuilds de hoje recriaram backend+celery via compose. Se essas vars estavam setadas no container anterior por um mecanismo **fora do compose** (docker run -e, ou compose antigo), o recreate as **dropou**. (A memória registrava "AGENT_ENABLED=true" no rebuild followup.) **Não há mensagens incoming após o rebuild (>20:00) p/ observar o comportamento atual** → não dá pra confirmar só por log.
- ⚠️ **Impacto na missão de áudio:** o áudio senta **em cima** do copiloto, que hoje está **desligado** (AGENT_ENABLED ausente) e **sem token Chatwoot** (não baixa o áudio). **Resolver esse wiring de env é pré-requisito** do STT — e merece verificação (foi sempre assim, ou o rebuild dropou?).
- Nota: o webhook em si **funciona sem o secret** (`if expected:` pula a auth quando vazio) → loga mesmo sem `WHATSAPP_WEBHOOK_SECRET` (entrada aberta — ponto de segurança separado).

## g) Bug pré-existente no caminho?
- Webhook **não quebra** com áudio (content vazio é tratado). O "bug" é **omissão**: attachment ignorado + query filtra vazio → o áudio nunca chega ao agente.
- O bloqueador real é o **(f)**: env do agente/Chatwoot ausente no compose.

---

## DESENHO recomendado (menor risco) — o que reusar vs construir
**Reusar (já existe):**
- Webhook + INSERT em `cwi_message_log` (controller.py).
- Cliente OpenAI (`AsyncOpenAI`, key no env) → `client.audio.transcriptions.create(model="whisper-1", file=...)`.
- Cliente HTTP `aiohttp` + header `api_access_token` (`_post_private_note`) → baixar o `data_url`.
- Fluxo do agente (`gerar_resposta` lê `content` do log) — **intocado** se a transcrição virar `content`.

**Construir (falta):**
1. No webhook: ler `data.get("attachments")`; se `file_type=="audio"` (ou content_type audio) → baixar `data_url` (aiohttp+token) → Whisper → `content = transcrição` (prefixar algo como "🎤 [áudio transcrito]: ..." opcional) antes do INSERT.
2. **(pré-requisito) wiring de env:** garantir `AGENT_ENABLED=true` + `CHATWOOT_API_TOKEN` + `CHATWOOT_BASE_URL` no backend (via compose `environment:` ou `env_file`) — senão nem o copiloto nem o download funcionam.
3. **(opcional) migration sprint95:** colunas `media_url`/`message_type` em `cwi_message_log` p/ rastrear o áudio original (não obrigatório no MVP).
4. ffmpeg: **provavelmente dispensável** (Whisper aceita ogg) — confirmar no teste.

## PRÓXIMO PASSO obrigatório (gate)
- **Teste real controlado:** Jordan manda **um áudio** pro número 0800 → capturamos o `attachments` exato no payload (logar o body bruto do webhook num ponto temporário, ou inspecionar via Chatwoot API) p/ saber: URL (interna/pública), se exige `api_access_token`, e o codec/extensão (.oga/opus). **Sem isso, o formato do áudio é suposição.**
- **Antes disso:** decidir o env-wiring do (f) — confirmar se o copiloto está mesmo off e se foi regressão do rebuild.

## Resumo
- Áudio **chega** no webhook (como `attachments`), mas o código **ignora** (content vazio, sem crash). 2 entradas sem-texto reais existem, mas o formato do áudio **não foi capturado** → **precisa teste real**.
- STT **viável e barato**: openai 2.38.0 (audio.transcriptions ✅) + OPENAI_API_KEY presente; Whisper aceita ogg → ffmpeg dispensável.
- Inserção de menor risco: **no webhook** (transcreve attachment → `content`), agente intocado. `content` (text) guarda a transcrição (sem migration p/ MVP).
- 🔴 **Bloqueador:** `AGENT_ENABLED`/`CHATWOOT_API_TOKEN` ausentes no compose (copiloto off + sem token p/ baixar áudio) — possível regressão do rebuild; **resolver primeiro**.

*Read-only: leitura de controller/agent_service/compose/.env (existência de chaves), \d cwi_message_log, SELECT de contagem, versão openai + ffmpeg no container. Nenhuma escrita/build/chamada de API.*
