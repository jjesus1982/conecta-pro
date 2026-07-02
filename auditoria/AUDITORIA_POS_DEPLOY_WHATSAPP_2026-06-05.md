# Auditoria pós-deploy da migração WhatsApp + correção de drift

- **Data:** 2026-06-05 ~20:10 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Conferir o que está REALMENTE em produção após a migração Evolution→Chatwoot.
- **Resultado:** ✅ Produção correta nos 9 containers. ⚠️→✅ **Drift encontrado e corrigido** (host estava desatualizado).

---

## 1. O que a auditoria encontrou
- **Container `conecta-pro-backend`** roda o **código novo (Chatwoot)** — confirmado (`/api/v1/accounts/...`, `CHATWOOT_*`, sem `sendText`).
- **DRIFT:** o `service.py` **canônico do host** ainda era o **código antigo (Evolution)** — md5 `00826f…` (host) ≠ `61e8bb…` (container). Causa: no deploy eu fiz `docker cp` do arquivo de revisão (`service.py.chatwoot-new`) para os containers, mas **não promovi** para o `service.py` do host.
- Risco do drift: um rebuild/redeploy a partir do host reverteria a produção para Evolution.

## 2. Correção aplicada
- Promovido o código novo para o `service.py` canônico do host (`cp service.py.chatwoot-new service.py`).
- **Verificado:** host (`61e8bb…`) == container (`61e8bb…`) → **fonte da verdade alinhada**.
- Removido o arquivo de revisão redundante `service.py.chatwoot-new`.
- Backup do original Evolution preservado: `service.py.bak-evolution-20260605_194835`.
- Sintaxe do host validada (`py_compile` OK).

## 3. Consistência em TODOS os containers (9/9)
Código novo (md5 `61e8bb…`) **e** token legível (`/app/.chatwoot_token`) em:
```
conecta-pro-backend            OK(novo) tok-ok
conecta-pro-celery-batch       OK(novo) tok-ok
conecta-pro-celery-beat        OK(novo) tok-ok
conecta-pro-celery-nfse        OK(novo) tok-ok
conecta-pro-celery-sefaz       OK(novo) tok-ok
conecta-pro-celery-integrations OK(novo) tok-ok
conecta-pro-celery-operacional OK(novo) tok-ok
conecta-pro-celery-priority    OK(novo) tok-ok
conecta-pro-flower             OK(novo) tok-ok
```

## 4. Lição / nota de processo
- No padrão "código baked + `docker cp`" deste projeto, **sempre promover a alteração ao arquivo do host também** (não só copiar para o container), senão host e produção divergem silenciosamente. Auditoria de md5 host-vs-container deve fazer parte do checklist de deploy.

## 5. Estado consolidado da migração (inalterado, agora sem drift)
- Backend envia via Chatwoot/Baileys (provado: msg entregue/lida).
- Config persistida no compose + `.env` (enabled=true, `CHATWOOT_*`, rede external).
- Pendências em aberto (separadas): senders duplicados (`diaristas`, `client_portal`) ainda em Evolution; SMTP do Chatwoot quebrado.

---
*Read-only de auditoria + 1 `cp` no host (promoção do código) + remoção do arquivo de revisão. Containers de produção não tocados (já estavam corretos). Token não exposto.*
