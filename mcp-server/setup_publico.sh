#!/usr/bin/env bash
# Publica o conector MCP em https://mcp.conectamais.pro e liga o modo OAuth (Google).
# Pré-requisito: registro DNS A "mcp.conectamais.pro" -> 82.25.75.74 já criado e propagado.
# Uso:  sudo bash /opt/conecta-pro/mcp-server/setup_publico.sh
set -euo pipefail

DOMAIN="mcp.conectamais.pro"
IP_ESPERADO="82.25.75.74"
EMAIL_CERT="jordansjesus@gmail.com"
DIR="/opt/conecta-pro/mcp-server"
VHOST_SRC="$DIR/nginx-mcp.conectamais.pro.conf"

echo "==> 1/5 Checando DNS de $DOMAIN (resolvers públicos) ..."
RESOLVED=$(nslookup "$DOMAIN" 1.1.1.1 2>/dev/null | awk '/^Address: /{print $2}' | tail -1 || true)
[ -z "$RESOLVED" ] && RESOLVED=$(nslookup "$DOMAIN" 8.8.8.8 2>/dev/null | awk '/^Address: /{print $2}' | tail -1 || true)
if [ "$RESOLVED" != "$IP_ESPERADO" ]; then
  echo "ERRO: $DOMAIN resolve para '${RESOLVED:-nada}', esperado $IP_ESPERADO."
  echo "      Crie o registro A no painel da Hostinger e aguarde propagar. Abortando."
  exit 1
fi
echo "    OK: $DOMAIN -> $RESOLVED"

echo "==> 2/5 Instalando vhost nginx ..."
cp "$VHOST_SRC" /etc/nginx/sites-available/$DOMAIN
ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
nginx -t
systemctl reload nginx
echo "    OK: vhost ativo (HTTP)."

echo "==> 3/5 Emitindo certificado TLS (certbot) ..."
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL_CERT" --redirect
echo "    OK: HTTPS emitido."

echo "==> 4/5 Ligando modo OAuth (Google) no MCP ..."
sed -i 's/^AUTH_MODE=.*/AUTH_MODE=google/' "$DIR/.env"
cd "$DIR"
docker compose -f docker-compose.mcp.yml up -d
echo "    OK: MCP em modo google."

echo "==> 5/5 Verificando ..."
sleep 5
echo -n "    /healthz publico: "; curl -s -o /dev/null -w '%{http_code}\n' "https://$DOMAIN/healthz"
echo -n "    OAuth metadata:   "; curl -s -o /dev/null -w '%{http_code}\n' "https://$DOMAIN/.well-known/oauth-authorization-server"
echo
echo "PRONTO. No Claude: Conectores -> Adicionar personalizado -> https://$DOMAIN/mcp"
echo "Login pelo Google (restrito a GOOGLE_ALLOWED_EMAILS no .env)."
