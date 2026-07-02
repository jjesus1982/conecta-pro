# Censo das Integrações Telegram — Conecta PRO

- **Data:** 2026-05-31
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Escopo:** Read-only. Tokens mascarados. Validação de token feita via `getMe` (não envia mensagem ao chat). **Nenhuma mensagem de teste enviada.**
- **Veredito geral:** 🔴 **O monitoramento Telegram NÃO alerta de crises de recurso.** Ele falhou em avisar da crise de 20–30/mai — e continua falhando hoje.

---

## 1. Inventário de Bots / Tokens

Foram encontrados **3 tokens distintos** (2 válidos, 1 morto) — todos apontando para o mesmo chat `5536961034` (Jordan):

| # | Bot (username) | Token (mascarado) | Válido? (getMe) | Chat ID | Onde é usado | Propósito |
|---|----------------|-------------------|-----------------|---------|--------------|-----------|
| 1 | **@conecta_pro_monitor_bot** | `8562364686...SuBQ` (`MONITOR_BOT_TOKEN`) | ✅ **válido** | 5536961034 | cron (orchestrator_unificado rapido/completo/heartbeat/escaladas), `relatorio_matinal/semanal.py`, `proatividade`, `backup_database.sh`, pm2 `cto-monitor-bot` (monitor_bot.py), `skills_agent.py` | Monitor + comandos interativos (/status etc) + relatórios |
| 2 | **@conectapro_alertas_bot** | `8343886201...DVOQ` (`TELEGRAM_BOT_TOKEN` no `.env`) | ✅ **válido** | 5536961034 | pm2 `telegram-assistant` (telegram_assistant.py, polling `getUpdates`); referenciado pelo caminho Alertmanager→OpenClaw | Assistente IA interativo + (teoricamente) alertas |
| 3 | *(sem nome)* | `8147216585...EvIc` | 🔴 **INVÁLIDO** (`ok:false`) | **vazio** (`""`, "CONFIGURAR") | `/root/check-conectado-health.sh` | Órfão — monitora só o gateway OpenClaw (Claude), nunca envia |

**Processos de bot ativos (pm2, há 24 dias):**
- `cto-monitor-bot` → `monitor_bot.py` (bot 1) — online.
- `telegram-assistant` → `telegram_assistant.py` (bot 2) — online (60 MB).

**Bots redundantes / tokens órfãos:**
- **Bot 3 (`8147...EvIc`) é órfão e morto:** token revogado/inválido **e** `chat_id` nunca configurado. O script só verifica a RAM do processo `openclaw-gateway` (componente do Claude Code), não recursos do ERP. Candidato a remoção.
- **Bots 1 e 2 são parcialmente redundantes:** dois bots diferentes para o mesmo chat, um para "monitor/relatórios" e outro para "assistente/alertas".

---

## 2. O que cada um envia, quando — e se ALERTA de recurso

| Job (cron) | Frequência | Token | O que envia | Alerta de recurso? |
|------------|-----------|-------|-------------|--------------------|
| `orchestrator_unificado.py rapido` | */5 min | bot 1 | Score/checks (SE obtiver login ERP) | ❌ código de RAM/load existe mas **nunca executa** (ver §4) |
| `orchestrator_unificado.py completo` | */30 min | bot 1 | Relatório completo | ❌ mesmo gate |
| `orchestrator_unificado.py heartbeat` | a cada 6h | bot 1 | "💚 HEARTBEAT" com CPU/RAM/Disco/uptime (indicador 🔴≥90%) | ⚠️ **só dispara se o login ERP funcionar** — não funciona |
| `orchestrator_unificado.py escaladas` | */5 min | bot 1 | Escaladas do CTOBrain | ❌ não é recurso |
| `relatorio_matinal.py` | 10h diário | bot 1 | Relatório matinal | ❌ relatório periódico |
| `relatorio_semanal.py` | seg 11h | bot 1 | Relatório semanal | ❌ relatório periódico |
| `proatividade` | a cada 4h | bot 1 | Propostas do CTO | ❌ não é recurso |
| `backup_database.sh` | 3h diário | bot 1 | Sucesso/falha do backup (via `curl -sf`, **não depende de login ERP**) | ❌ só status de backup — mas **prova que o bot 1 entrega** |
| `check-conectado-health.sh` | */15 min | bot 3 | Alerta de gateway OpenClaw | ❌ **chat_id vazio → nunca envia** |
| Prometheus → Alertmanager | contínuo | (webhook) | `HighMemoryUsage`, `HighLoadAverage`, `DiskSpaceCritical`, `PostgresDown`, etc. | ✅ **existe** — mas entrega quebrada (ver §4) |

**Conclusão do §2:** as regras de alerta de recurso **existem** em dois lugares (heartbeat do orchestrator e Prometheus), mas **nenhuma entrega de fato** — uma por bug de gate, outra por dependência circular. Os relatórios periódicos (matinal/semanal) não alertam de crise.

---

## 3. Ainda funcionam? (estado dos envios)

- **Tokens Telegram:** bots 1 e 2 **válidos** (`getMe ok:true`); bot 3 **inválido**.
- **Entrega real do bot 1:** o `backup_database.sh` (envio direto, sem login ERP) roda e o backup de **31/05 03:00 concluiu OK** → o canal Telegram em si **funciona** para quem não depende do login.
- **Orchestrator (rapido/completo/heartbeat):** 🔴 **100% de falha**. Contagem de `"Falhou após todas as tentativas"` nos logs `monitor_rapido` (maio): **0 sucessos / 1.000+ falhas** em todos os arquivos diários. Mesmo padrão em `monitor_completo` e `monitor_heartbeat`.
- **`relatorio_matinal.log` (31/05):** `Telegram erro: HTTP Error 400: Bad Request` seguido de `✅ Relatório enviado` — entrega instável (erro 400 de formatação) e log de sucesso possivelmente enganoso.
- **Gateway OpenClaw:** 🔴 **parado AGORA** — `conectado-health.log` registra "🔴 CRÍTICO: Gateway OpenClaw está parado!" a cada 15 min (mas sem enviar, chat_id vazio). Como o Alertmanager entrega via OpenClaw, esse caminho de alerta está fora do ar.

---

## 4. TESTE DE FOGO — o Telegram teria avisado da crise de 20–30/mai? **NÃO.**

### Evidência A — o monitor de recursos aborta antes de checar RAM/load
Em `orchestrator_unificado.py`, `main()` (linhas 897–900):
```python
token = obter_token_compartilhado()      # login no ERP: 127.0.0.1:8080/auth/login
if not token:
    telegram("🔴 Monitor Unificado: falha ao obter token JWT")
    sys.exit(1)                           # <<< ABORTA aqui
```
O login usa `jjesus@conectamais.pro / Jordan0612` e **falha sempre** (credenciais e/ou rate-limit de login 5/min, agravado por ~4 jobs logando juntos). O rótulo enganoso **"[TOKEN] Rate limit — aguardando 65/130/195s → Falhou após todas as tentativas"** é sobre **esse login do ERP, não sobre o Telegram**. Como o token nunca é obtido, o código de avaliação de RAM/CPU/disco (`ciclo_rapido`/`ciclo_heartbeat`, ex. linha 857 `RAM: {ram_pct}%` com indicador 🔴≥90%) **nunca roda**. Resultado: **é impossível gerar um alerta de RAM/load** — o programa sai antes.

### Evidência B — logs da crise mostram blackout
`monitor_rapido.log.12.gz` (≈20/mai) e `.10.gz` (≈22/mai): todas as execuções terminam em "Falhou após todas as tentativas", **zero envio de recurso**. Em **21/05 01:01** aparece `"/bin/sh: 1: Cannot fork"` — o próprio servidor (load 127 / processos esgotados) impediu o monitor de rodar. Ou seja, no auge da crise o monitor **nem executava**.

### Evidência C — o caminho de alerta "correto" tem dependência circular
As regras Prometheus (`HighMemoryUsage`, `HighLoadAverage`, `DiskSpaceCritical`, `PostgresDown`…) existem desde 01/abr, mas o Alertmanager (`alertmanager.yml`) **não envia ao Telegram diretamente** — faz POST para:
```
http://conecta-pro-backend:8080/api/v1/ai/openclaw/alert-webhook
```
Isto é, **a entrega do alerta depende do backend (8080) estar saudável** — justamente o componente que satura/cai numa crise de RAM/load/dockerd hang. Quando o servidor trava, o webhook não chega → nenhum alerta sai. (E hoje o gateway OpenClaw está parado, §3.)

### Evidência D — caminhos independentes também não alertam
- `system_monitor.sh` (*/15min): mede recursos mas **não envia Telegram** (0 referências).
- `check-conectado-health.sh` (*/15min): `chat_id` vazio + token inválido → **nunca envia**; e mede só o gateway OpenClaw, não o ERP.

### Por que o Telegram não te avisou da crise de 20–30/mai
> Porque o único monitor que olha RAM/load (o `orchestrator_unificado`) **encerra com `sys.exit(1)` antes de checar qualquer recurso**, sempre que o login na API do ERP falha — e ele falha 100% das vezes (credencial/rate-limit). O canal Telegram em si funciona (o backup de 31/05 enviou), mas o código nunca chega na linha que mandaria o alerta de recurso. O caminho alternativo (Prometheus → Alertmanager) só entrega **através do próprio backend**, que estava sobrecarregado/travado na crise. E os scripts shell independentes ou não enviam Telegram, ou estão com chat_id/token inválidos. Resultado: **silêncio total de recursos** — nem "tudo ok", nem alerta. Falso negativo por design.

---

## 5. Veredito por integração

| Integração | Estado |
|------------|--------|
| @conecta_pro_monitor_bot — entrega do canal | 🟢 funciona (backup envia) |
| @conecta_pro_monitor_bot — monitor de recursos (orchestrator) | 🔴 quebrado (aborta no login ERP, nunca checa RAM/load) |
| @conectapro_alertas_bot — assistente | 🟡 online, mas é interativo, não alerta proativo |
| Prometheus → Alertmanager → OpenClaw → Telegram | 🔴 dependência circular do backend + gateway OpenClaw parado |
| check-conectado-health.sh (bot órfão) | 🔴 morto (token inválido + chat_id vazio) |
| Relatórios matinal/semanal | 🟡 periódicos, **não alertam de crise** (e com erro 400 intermitente) |

**Classificação final do monitoramento Telegram de crises: 🔴 QUEBRADO/SILENCIOSO.**
Para crises de recurso ele é um **falso negativo**: não alerta e não avisa que parou de alertar.

---

## 6. Recomendações (propostas — nada executado)
1. **Desacoplar o alerta de recurso do login do ERP:** mover a checagem de RAM/CPU/disco/containers para ANTES (e independente) de `obter_token_compartilhado()`, enviando alerta mesmo sem JWT. Hoje um login que falha mata todo o monitoramento.
2. **Corrigir a credencial de login** do monitor (`jjesus@conectamais.pro` parece incorreta; o admin conhecido é `admin@conectapro.com.br`) e/ou reduzir a concorrência de jobs que estouram o rate-limit de login (rapido+escaladas+completo simultâneos).
3. **Quebrar a dependência circular do Alertmanager:** adicionar um receiver Telegram **direto** no Alertmanager (bot 2, sem passar pelo backend) para alertas críticos de recurso — assim o alerta sai mesmo com o backend caído.
4. **Remover o bot órfão** (`8147...EvIc`) e configurar/aposentar o `check-conectado-health.sh`.
5. **Heartbeat de "dead-man's switch":** se o chat parar de receber heartbeat por >X horas, isso por si só deveria sinalizar problema (hoje a ausência de heartbeat é silenciosa).
6. **Reduzir a sobreposição de jobs** (rapido a cada 5min, mas cada execução leva ~6,5min em backoff) — está empilhando processos e contribuiu para o `Cannot fork` da crise.

---
*Read-only. Tokens mascarados. Validação por `getMe` (sem envio ao chat). Nenhuma config/serviço alterado.*
