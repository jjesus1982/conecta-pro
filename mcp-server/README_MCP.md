# Conector MCP do Conecta PRO

Servidor MCP (starter) que expõe a API do Conecta PRO como ferramentas para o Claude.

## O que está pronto (testado)
- Container `conecta-pro-mcp` (porta interna 127.0.0.1:8788), na rede `conecta-pro_conecta-pro-network`.
- 11 ferramentas: `consultar_pipeline`, `consultar_forecast`, `criar_proposta`, `listar_propostas`,
  `criar_lead`, `listar_leads`, `listar_clientes`, `listar_contratos`, `listar_sequencias`,
  `inscrever_lead_em_sequencia`, `resumo_comercial`.
- Auth de entrada: **Bearer token** (`MCP_AUTH_TOKEN` em `.env`).
- Auth de saída p/ o ERP: conta de serviço (login JWT cacheado). **Hoje usa o admin — trocar por usuário escopado.**

## Subir / atualizar / logs
```bash
cd /opt/conecta-pro/mcp-server
docker compose -f docker-compose.mcp.yml up -d --build   # sobe/atualiza
docker logs conecta-pro-mcp --tail 30                     # logs
curl http://127.0.0.1:8788/healthz                        # health
```

## Publicar em https://mcp.conectamais.pro (passo a passo)
1. **DNS** (Hostinger): criar registro **A** `mcp` → `82.25.75.74`.
2. **vhost nginx**:
   ```bash
   sudo cp /opt/conecta-pro/mcp-server/nginx-mcp.conectamais.pro.conf /etc/nginx/sites-available/mcp.conectamais.pro
   sudo ln -s /etc/nginx/sites-available/mcp.conectamais.pro /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
3. **TLS** (após o DNS propagar):
   ```bash
   sudo certbot --nginx -d mcp.conectamais.pro
   ```
   O certbot adiciona o bloco 443/SSL e o redirect sozinho.

## Adicionar no Claude
**O endpoint MCP é:** `https://mcp.conectamais.pro/mcp`
**Header de auth:** `Authorization: Bearer <MCP_AUTH_TOKEN>` (o token está em `.env` / `.mcp_token_full.txt`).

- **Claude Code (CLI):**
  ```bash
  claude mcp add --transport http conecta-pro https://mcp.conectamais.pro/mcp \
    --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
  ```
- **App Claude (conector personalizado, OAuth):** ver "Modo OAuth (Google)" abaixo.

## Modo OAuth (Google) — para o app oficial do Claude
O servidor já suporta OAuth 2.1 delegado ao Google (env `AUTH_MODE=google`). O app do Claude faz
Dynamic Client Registration + login; o usuário autentica na conta Google; o MCP valida.
Já testado: em modo google o servidor publica `/.well-known/oauth-authorization-server` com
`registration_endpoint` (/register) e `authorize`/`token`.

REUSA o OAuth client do ERP (mesmo client_id/secret do login Google) — já pré-preenchido no `.env`.
Para ativar (precisa do domínio HTTPS público no ar):
1. **Google Cloud Console** → no OAuth client EXISTENTE (576020339239-...apps.googleusercontent.com) →
   Authorized redirect URIs → **ADICIONAR** `https://mcp.conectamais.pro/auth/callback`. (Não cria client novo.)
2. No `.env`: trocar `AUTH_MODE=google` (client_id/secret já estão lá, copiados do ERP).
3. `docker compose -f docker-compose.mcp.yml up -d` (recarrega o .env).
4. No app do Claude: Configurações → Conectores → Adicionar personalizado → URL
   `https://mcp.conectamais.pro/mcp` → o Claude inicia o fluxo OAuth e abre o login do Google.

> Bearer e Google são alternativos: `AUTH_MODE=bearer` (default, Claude Code) ou `=google` (app Claude).

## Segurança (feito + recomendado)
- ✅ **Usuário de serviço escopado** criado: `mcp-service@conectamais.pro` (role `operator`, NÃO admin) —
  já em uso no `.env` (senha em `.svc_pw.txt`). Bloqueado em endpoints que exigem `require_roles("admin")`.
- Rotacionar `MCP_AUTH_TOKEN` e a senha do serviço periodicamente.
- `.env`, `.mcp_token_full.txt`, `.svc_pw.txt` têm permissão 600 e NÃO vão para o git (`.gitignore`).
