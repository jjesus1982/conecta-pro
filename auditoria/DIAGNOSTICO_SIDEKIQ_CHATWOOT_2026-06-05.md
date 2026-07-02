# Diagnóstico — Sidekiq do Chatwoot (READ-ONLY)

- **Data:** 2026-06-05 ~15:32 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Escopo:** Investigação read-only do container `chatwoot-fazerai-sidekiq` (Exit 137). Nenhuma alteração feita.
- **Veredito:** 🔴 **O Sidekiq do Chatwoot ativo está PARADO há ~6 dias.** A UI funciona, mas todo o processamento em background está parado e silencioso desde 29/mai.

---

## 1. Como e quando morreu

```
docker inspect chatwoot-fazerai-sidekiq:
OOMKilled = false
ExitCode  = 137
Started   = 2026-05-26 15:11:43 UTC
Finished  = 2026-05-29 20:33:25 UTC
```

- **Não foi OOM do kernel** (`OOMKilled=false`). O `137` (=128+9, SIGKILL) veio do **restart em massa de 29/mai**: o `docker stop` matou o Sidekiq no timeout e o container **nunca foi reerguido**. Os demais containers do stack voltaram às ~20:36 do mesmo dia; o Sidekiq ficou para trás.
- O log do container está **vazio** (`docker logs` sem saída) — sem stack trace adicional; consistente com kill externo, não crash interno.

---

## 2. Está processando? NÃO

Inspeção direta do Redis do Chatwoot (`chatwoot-fazerai-redis`, banco **db3**, onde estão as 69 chaves do Sidekiq):

| Métrica | Valor | Leitura |
|---------|-------|---------|
| `stat:processed:2026-05-29` | **4135** | último dia com processamento |
| `stat:processed:2026-05-30` … `2026-06-05` | **vazio** | **0 jobs processados desde 29/mai** |
| `queue:default / low / high / mailers / active_storage` | **0** | sem consumo e sem enfileiramento (o agendador sidekiq-cron mora dentro do worker morto) |
| `retry` / `schedule` / `dead` | 0 / 1 / **198** | 198 jobs mortos acumulados |
| `stat:processed` (total) | 35.322 | histórico |
| `stat:failed` (total) | 977 | histórico |
| `processes` (set) | 1 membro **órfão** | `4c87b1c42692:1:43552d7213c5` — mas `hget info`/`hget beat` **vazios** → sem heartbeat, registro fantasma, não é processo vivo |
| Sidekiq dentro da web (`ps` em `chatwoot-fazerai`) | **nenhum** | não há worker embarcado |

**Conclusão:** o único membro em `processes` é um resíduo sem heartbeat; não existe Sidekiq vivo em lugar nenhum. Zero processamento há 6 dias.

---

## 3. O que ainda funciona

- **Redis** (`chatwoot-fazerai-redis`): 🟢 responde `PONG`, saudável. A dependência do Sidekiq está OK — o problema é só o worker ausente.
- **Web** (`chatwoot-fazerai`, `127.0.0.1:3003`): 🟢 `running / healthy / RestartCount=0`. Servida pelo nginx em `chat.conectamais.pro` (`proxy_pass 127.0.0.1:3003`, HTTPS Let's Encrypt). **Abre a tela normalmente.**

> ⚠️ Falso "tudo certo": quem olha a UI acha que o atendimento está no ar, mas o backstage não processa nada.

---

## 4. Impacto funcional (silencioso desde 29/mai)

Com o Sidekiq morto, **todo o trabalho assíncrono do Chatwoot está parado**:
- Envio/recebimento de mensagens via jobs e **webhooks** (Evolution/Baileys ↔ Chatwoot);
- **Automações** e regras;
- **Mensagens agendadas** (scheduled messages);
- **IMAP** de caixas de e-mail;
- **Notificações**, auto-resolução de conversas, imports de contatos;
- Jobs periódicos do `sidekiq-cron` (estão registrados como `cron_job:*:enqueued`, mas não disparam — o agendador está dentro do worker morto).

As filas vazias **não** indicam vazão saudável: indicam que, sem o worker, **nada é enfileirado nem consumido**.

---

## 5. Recomendações (PROPOSTAS — nada executado)

1. **Religar o `chatwoot-fazerai-sidekiq`** (subir o container e garantir `restart: unless-stopped` + dependência correta no compose) — é a correção óbvia que restabelece o processamento. *Ação de mudança → deixada como proposta.*
2. **⚠️ Antes de subir, revisar o que o `sidekiq-cron` reenfileiraria:** ao religar, jobs periódicos atrasados de ~6 dias (auto-resolve, **scheduled messages**, IMAP) podem disparar de uma vez — risco de **enviar mensagens antigas a clientes**. Recomenda-se revisar/limpar agendamentos vencidos antes de iniciar.
3. **Investigar os 198 jobs em `dead`** para entender o que falhou de forma definitiva antes da parada.
4. **Limpeza:** a stack antiga `chatwoot` / `chatwoot-sidekiq` (Exited 137, abandonada) continua candidata a remoção.
5. **Causa-raiz preventiva:** o restart de 29/mai deixou um serviço para trás sem ninguém perceber por 6 dias — reforça a necessidade de um alerta de "container crítico parado" (ligado ao tema do Censo Telegram: o monitoramento não avisou).

---
*Read-only. Inspeção via `docker inspect` e `redis-cli` (somente leitura). Nenhum container, fila ou configuração foi alterado.*
