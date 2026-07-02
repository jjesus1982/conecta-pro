# Teste de fumaça — core/mailer (entrega de e-mail) — FALHOU (auth SMTP)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Provar se o backend ENTREGA e-mail de verdade (caminho que a F-VISITA.2 usaria).
- **Veredito:** ⛔ **NÃO entrega.** `send_email` retornou `False` — **535 authentication failed** no `server.login()`. Credenciais SMTP inválidas/recusadas.
- **Nada alterado:** sem código novo, sem commit, sem tocar `.env`/`mailer`, sem rebuild.

---

## 1. Assinatura real (read-only)
`core/mailer.py`:
```python
async def send_email(to_email: str, subject: str, html_body: str) -> bool
```
- Early-return `False` se `settings.SMTP_HOST` vazio.
- Conecta via `smtplib.SMTP` + `starttls()` (se `SMTP_USE_TLS`) ou `SMTP_SSL`; `server.login(SMTP_USERNAME, SMTP_PASSWORD)`; `server.sendmail(...)`.
- **Captura exceção e retorna `False`** (não levanta) → o sinal é o retorno + o log.

## 2. SMTP_* no env (nomes + preenchimento, sem valores)
Todas **setadas**: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_USE_TLS`.

## 3. Disparo real (1 e-mail)
- Destinatário: `jjesus@conectamais.pro` (autorizado).
- Chamada à função **real** do `core/mailer` (não smtplib ad-hoc).
- **Retorno:** `False`.
- **Erro exato** (`core.mailer:send_email:47`):
  ```
  (535, b'5.7.8 Error: authentication failed: (reason unavailable)')
  ```

## 4. Diagnóstico
- A conexão **chegou ao estágio de AUTH** (host/porta/TLS funcionam — senão não chegaria ao 535).
- O **`login()` foi rejeitado** → `SMTP_USERNAME`/`SMTP_PASSWORD` inválidos/recusados pelo servidor.
- **Status: NÃO ENTREGUE.** Não adianta checar caixa de entrada/spam — o e-mail **não saiu** (rejeitado no AUTH antes do envio).

## 5. Implicação e próximo passo
- Recursos que dependem de e-mail (ex.: **confirmação de visita na F-VISITA.2**) **não entregam** até corrigir as credenciais.
- **Tarefa separada (não feita):** corrigir `SMTP_USERNAME`/`SMTP_PASSWORD` no `.env` com credenciais válidas do provedor + recreate do backend, e re-rodar este smoke test (esperado: `send_email` → `True` e Jordan confirma recebimento).
- Lembrete: o "SMTP do Chatwoot quebrado" é **outro** SMTP independente; este é o do `core/mailer` (backend).

---

## Resumo
- `send_email` existe e é chamável; as 7 `SMTP_*` estão setadas. ✅ (configurado)
- Entrega **falha** com **535 auth failed** → credenciais SMTP inválidas. ⛔ (não entrega)
- Nada alterado/commitado. Fix = corrigir credenciais no `.env` (tarefa à parte).

*Teste de fumaça concluído. Nada modificado.*
