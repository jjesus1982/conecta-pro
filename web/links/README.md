# Página de bio — https://conectamais.pro/links/

Substitui o Linktree, que foi abandonado por dois motivos concretos:

1. **Acesso perdido.** A conta do Linktree ficou com um ex-prestador. A bio do
   Instagram — porta de entrada de todo lead orgânico — estava refém de conta de
   terceiro.
2. **Ele apaga a atribuição.** O link da bio carregava `utm_source=ig&
   utm_medium=social&utm_content=link_in_bio`, e o Linktree **não repassa UTM**
   para o botão de destino. O lead chegava sem saber de onde veio.

Cada botão embute `[c:<slug>]` no `?text=` do wa.me. O
`_atribuicao_do_texto` (whatsapp/agent_service.py) lê o marcador e grava
`leads.utm_campaign` — o denominador do CAC. Sem marcador, o sistema **não
inventa** campanha: `utm_campaign` fica nulo, honestamente.

| botão | slug | source derivado |
|---|---|---|
| Falar no WhatsApp | `bio_cotacao` | `instagram_linktree` |
| Portaria remota | `bio_portaria` | `landing_portaria_remota` |
| Agentes de portaria | `bio_agentes` | `landing_agentes_portaria` |
| Monitoramento 24h | `bio_monitoramento` | `landing_monitoramento` |

**Armadilha ao editar os textos:** a origem sai da PRIMEIRA palavra-chave
encontrada, nesta ordem — *portaria remota*, *agentes de portaria*,
*monitoramento*, *instagram* (`_ORIGEM_MARCADORES`). Escrever "portaria remota"
no botão genérico faria o lead do Instagram ser contado como landing.

## Deploy

Servida pelo nginx do host, direto do disco, sem container e sem build:

    cp index.html logo.webp /var/www/web.conectamais.pro/links/

O `server` de `conectamais.pro` usa `try_files $uri $uri/ /index.html`, então o
diretório `/links/` é servido sozinho — **nenhuma alteração de nginx.conf**.
Esta cópia existe para a página não viver só fora do versionamento.
