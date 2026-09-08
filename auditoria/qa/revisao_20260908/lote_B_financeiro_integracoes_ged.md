# Lote B — 86 rotas restantes de financial / integrations / ged / gedeon / gdrive / signatures / notifications (08/09/2026)

Vereditos: MORTA 7 · REDUNDANTE 29 · LIGAR 42 (5 já ligados por SQL) · INTERNA-ESCONDIDA 8 · EXTERNO 0.

Notas do agente que importam para o dono:
- Webhook do Inter: não há `webhookUrl` registrado nem tabela `inter_webhook_*` — nenhuma rota é chamada pelo banco hoje.
- `POST /pagamentos-pj/programar/{ano}/{mes}` era o elo que faltava: sem ele `pagar-folha-pj` responde "nenhum item elegível".
- `POST /gdrive/desconectar` (OAuth) e o `drive/disconnect` do GED (renomeia credencial) são mecanismos diferentes.
- `cashflow_entries` (8.370) é espelho do extrato por sync, não lançamento humano: as rotas de CRUD de entries são redundantes.

Aplicado: 29 handlers apagados (`apagar_B.tsv`); 7 ficaram por import (builders/orquestrador/serviços).
LIGAR construídos no lote 4: Inter categorização (tabela + corrigir + stats + auto-processar), Onvio (documentos, execuções,
estatísticas, sessão), Drive desconectar, auditoria de pagamentos Inter, parcelas pendentes, gerar recorrentes, programar folha PJ,
NF do PJ por linha, fluxo de caixa (resumo/tendência/categorias/fornecedores), DRE consolidado, estoque movimentos/resumo,
liminares status, contracheques GED no portal, documentos por kit, solicitar assinaturas do kit, GEDEON (panorama, alinhamento DP,
funcionários, visão por funcionário, VT/VR não assinados), painel do José Luís, certidões (emitir robô / subir PDF / avisar cliente).
NÃO feito: trocar o laço de `assinar-doc-empresa __ALL__` por `assinar_lote_empresa` (fluxo OTP existente; mudar sem o dono é risco).
