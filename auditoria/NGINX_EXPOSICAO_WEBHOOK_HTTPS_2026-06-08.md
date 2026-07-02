# Nginx — Exposição HTTPS do webhook do backend (análise + decisão) READ-ONLY

- **Data:** 2026-06-08
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Avaliar como expor o backend/webhook via HTTPS (subdomínio `webhook.conectamais.pro` pretendido).
- **Veredito:** 🟢 **O webhook já está público e protegido via HTTPS** (`erp.`/`app.conectamais.pro`). **O subdomínio dedicado é dispensável.** Recomendação: usar a **URL interna** no Chatwoot. Nada foi alterado no nginx.

---

## 1. Estrutura do nginx (read-only)
- **Roda no HOST** (systemd), nginx **1.24.0 (Ubuntu)** — sem container.
- Padrão `sites-available/` + `sites-enabled/` (symlinks). `conf.d/rate-limiting.conf`.
- Sites ativos: `app`, `chat`, `conectamais.pro`, `default`, `erp`, `web`.
- `nginx -t` → **syntax ok / test successful**. Warnings benignos pré-existentes (`protocol options redefined for ...:443` em conectamais.pro/erp/web — `http2` repetido; dívida técnica antiga, não tocada).

## 2. Certificados (certbot) — todos válidos
| Cert | Domínios | Expira |
|------|----------|--------|
| chat.conectamais.pro | chat | 24/ago (77d) |
| conectamais.pro | conectamais.pro, www | 21/jul (43d) |
| erp.conectamais.pro | erp, **app** | 15/ago (67d) |
| web.conectamais.pro | web | 21/jul (43d) |
- **Não há** cert para `webhook.conectamais.pro` (precisaria emitir se fosse criar).

## 3. 🔑 Descoberta: o backend já é público via HTTPS
- `app.conectamais.pro` tem `location /api/ { proxy_pass http://127.0.0.1:8080; }` (usa o cert do `erp.`).
- `erp.conectamais.pro` idem.
- Ou seja, **`/api/v1/...` já está exposto via HTTPS público** nesses dois hosts — independente de criar subdomínio novo.

## 4. Testes do webhook via HTTPS público (`erp.conectamais.pro`)
| Requisição | HTTP | Significado |
|------------|------|-------------|
| `GET` (com/sem token) | **405** | rota é POST-only → método barrado **antes** do token (por isso não é 401) |
| `POST` sem token | **401** | proteção ativa ✅ |
| `POST` token errado | **401** | proteção ativa ✅ |
| `POST` token certo | **200** | funciona ✅ |
- Mesmo comportamento via `app.conectamais.pro`. A validação por token (`?token=`) roda só no POST (o GET nunca chega nela).

## 5. Decisão: subdomínio dedicado NÃO é necessário
- O `webhook.conectamais.pro` daria uma URL mais "limpa", mas **não reduz exposição** — o `/api/` já é público via `erp.`/`app.`. Logo, adicionaria manutenção (mais um cert para renovar + server block) com benefício marginal.
- **Etapa 2 do nginx (criar server block + certbot) NÃO foi executada** — parada conforme o plano de 2 etapas do Jordan.

## 6. Recomendação de URL para o webhook do Chatwoot (em ordem)
1. **🥇 Interna (recomendada):** `http://conecta-pro-backend:8080/api/v1/whatsapp/webhook?token=<SEGREDO>`
   - Chatwoot está na mesma rede Docker → a chamada **não sai para a internet**, sem dependência de nginx/cert. Menor superfície e menos pontos de falha.
2. **🥈 Pública (se um sistema externo precisar chamar):** `https://erp.conectamais.pro/api/v1/whatsapp/webhook?token=<SEGREDO>` (validada, 200).
3. ~~`webhook.conectamais.pro` dedicado~~ — dispensável (ver §5).

> O token (64 chars) está em `/opt/conecta-pro/.env` (`WHATSAPP_WEBHOOK_SECRET`). Para a URL pronta:
> `echo "http://conecta-pro-backend:8080/api/v1/whatsapp/webhook?token=$(grep '^WHATSAPP_WEBHOOK_SECRET=' /opt/conecta-pro/.env | cut -d= -f2-)"`

## 7. Se ainda assim quiser o subdomínio dedicado (Etapa 2, sob aprovação)
1. `sites-available/webhook.conectamais.pro` (modelo do `chat.`), expondo **só** `location = /api/v1/whatsapp/webhook → proxy_pass 127.0.0.1:8080` e `location / { return 404; }`.
2. Bloco HTTP(80) primeiro (acme-challenge + redirect) → symlink → `nginx -t` → `reload`.
3. `certbot certonly --webroot -w /var/www/html -d webhook.conectamais.pro`.
4. Adicionar bloco HTTPS(443) com o cert → `nginx -t` → `reload`.
5. Validar 405/401/200. Backup de qualquer arquivo tocado + `nginx -t` antes de cada reload.

---
*Read-only: leitura de configs, `certbot certificates`, `nginx -t`, e `curl` de teste. Nenhum server block criado, nenhum cert emitido, nenhum reload. Nada alterado no nginx.*
