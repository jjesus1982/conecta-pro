# O Chatwoot consegue enviar e-mail? — Diagnóstico (READ-ONLY)

- **Data:** 2026-06-05 ~18:47 UTC
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Pergunta:** O Chatwoot (`chatwoot-fazerai`) consegue enviar e-mail (convites de agente, notificações)?
- **Veredito:** 🔴 **NÃO.** A configuração SMTP está incompleta — host e credenciais vazios. Qualquer envio de e-mail falha.

---

## 1. Estado das variáveis SMTP (via `printenv` + comprimento)

| Variável | Estado |
|----------|--------|
| `SMTP_ADDRESS` (servidor SMTP) | 🔴 **VAZIO** |
| `SMTP_USERNAME` | 🔴 **VAZIO** |
| `SMTP_PASSWORD` | 🔴 **VAZIO** |
| `SMTP_PORT` | ✅ 587 |
| `SMTP_DOMAIN` | ✅ `conectamais.pro` |
| `MAILER_SENDER_EMAIL` | ✅ `Conecta Mais <noreply@…>` |
| `SMTP_AUTHENTICATION` | ✅ `login` |
| `SMTP_ENABLE_STARTTLS_AUTO` | ✅ `true` |
| `FRONTEND_URL` | ✅ `https://chat.conectamais.pro` |

> ⚠️ Sem `SMTP_ADDRESS`/`SMTP_USERNAME`/`SMTP_PASSWORD`, o Chatwoot não tem servidor nem credencial para enviar. As demais vars (porta, domínio, remetente) estão prontas, mas não bastam.

## 2. Prova de conectividade
```
TCPSocket(SMTP_ADDRESS:587)  →  host vazio  →  Errno::ECONNREFUSED
```
Não há servidor SMTP para conectar.

## 3. O `dead=199` do Sidekiq NÃO é problema de e-mail
- 198 dos 199 jobs mortos: `ActiveRecord::DatabaseConnectionError` — falhas **históricas** da crise de 29-30/mai (DB/sidekiq indisponíveis), não SMTP.
- Apenas **1** `ActionMailer::MailDeliveryJob` no dead set — e morreu por **erro de banco**, não de SMTP.
- Fila `queue:mailers` atual = **0** (nada preso agora).
- O Sidekiq atual está saudável e processando (IMAP fetch rodando a cada minuto).

## 4. Impacto
- **Convite de agente por e-mail** → não chega.
- **Notificações por e-mail** (novas conversas, atribuições) → não saem.
- **Reset de senha / confirmação de conta** → não funciona.
- O atendimento por **WhatsApp** não é afetado (esse fluxo é via Baileys, independente do SMTP).

---

## 5. Como corrigir (PROPOSTA — nada executado)
Preencher as 3 vars vazias no `.env` do Chatwoot (`/opt/chatwoot-fazerai/.env`, que é `env_file` do compose) com um servidor SMTP real e credenciais, e recriar o `chatwoot-fazerai` + `chatwoot-fazerai-sidekiq`:
```
SMTP_ADDRESS=<host do seu provedor>      # ex.: smtp.gmail.com / smtp.resend.com / smtp do seu hosting
SMTP_USERNAME=<usuário/login SMTP>
SMTP_PASSWORD=<senha/app-password/API key>
# (porta 587, domínio, remetente e STARTTLS já estão ok)
```
Depois:
```
cd /opt/chatwoot-fazerai
docker compose up -d --no-deps --force-recreate chatwoot-fazerai chatwoot-fazerai-sidekiq
```
**Validação pós-fix:** reenviar um convite de agente (ou usar o console do Chatwoot) e confirmar entrega; o teste de `TCPSocket(SMTP_ADDRESS:587)` deve passar a CONECTAR.

> Preciso de você: **qual provedor SMTP** usar (Gmail/Workspace, Resend, Mailgun, SendGrid, ou o SMTP do hosting do domínio `conectamais.pro`) e as credenciais — sem isso não dá para preencher.

---
*Read-only: `printenv` (comprimento, sem expor valores), teste TCP socket, inspeção do dead set do Sidekiq. Nada alterado.*
