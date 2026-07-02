# Teste de fumaça — core/mailer: ENTREGA CONFIRMADA ✅

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Provar que o backend ENTREGA e-mail de verdade (caminho da F-VISITA.2).
- **Veredito:** ✅ **FUNCIONAL.** `send_email` → `True` e **entrega confirmada por Jordan** (recebeu o e-mail).
- **Nada alterado pelo backend:** sem código novo, sem commit, sem tocar `.env`/`mailer`, sem rebuild. O ajuste foi a senha no painel do Hostinger (feito pelo Jordan).

---

## 1. Diagnóstico inicial (1ª tentativa) — FALHOU no auth
- `send_email('jjesus@conectamais.pro', ...)` retornou **`False`**.
- Erro exato (`core.mailer:47`): **`535 5.7.8 Error: authentication failed`**.
- Causa: o par `noreply@conectamais.pro` + senha do `.env` foi **recusado** pelo Hostinger (a senha gravada no `.env` estava correta — 12 chars, sem aspas — mas **não batia com a senha real da caixa** no painel).

## 2. Correção (Jordan)
- A senha da caixa **`noreply@conectamais.pro`** foi **alinhada no painel Hostinger** para a mesma do `.env`.
- **`.env` não foi alterado** (já continha a senha correta); só o lado do servidor foi ajustado.

## 3. 2ª tentativa — SUCESSO
- `send_email('jjesus@conectamais.pro', ...)` retornou **`True`** (login + envio sem erro SMTP).
- **Entrega confirmada por Jordan** — recebeu o corpo da mensagem de teste.

## 4. Config SMTP validada
| Var | Valor |
|-----|-------|
| SMTP_HOST | `smtp.hostinger.com` |
| SMTP_PORT | `465` (SSL implícito) |
| SMTP_USE_TLS | `false` → mailer usa `SMTP_SSL` (correto p/ 465) |
| SMTP_USERNAME / FROM_EMAIL | `noreply@conectamais.pro` |
| SMTP_FROM_NAME | `Conecta PRO` |

`core/mailer.send_email(to_email, subject, html_body) -> bool` — assíncrona, conecta via SSL, `login()`, `sendmail()`, retorna `True`/`False` (captura exceção).

## 5. Implicação
- A **confirmação de visita por e-mail (F-VISITA.2)** agora tem caminho de entrega funcional.
- Lembrete: o "SMTP do Chatwoot quebrado" é **outro** SMTP independente — não confundir.

---

## Resumo
- 1ª tentativa: `False` / `535 auth failed` (senha desalinhada no Hostinger). ⛔
- Após Jordan alinhar a senha do `noreply@` no painel: 2ª tentativa `True` + **recebimento confirmado**. ✅
- `core/mailer` **validado e funcional** (`noreply@conectamais.pro` → destinatário, via Hostinger:465 SSL). Nada alterado no backend.

*Smoke test concluído com sucesso. Nada modificado/commitado.*
