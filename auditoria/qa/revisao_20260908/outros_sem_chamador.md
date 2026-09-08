# demais módulos — 315 rotas sem chamador (08/09/2026)

Medição: `checar_cobertura_rotas.py` T0 → bucket `nenhum` fora de people-management.

| Veredito | Qtde | O que foi feito |
|---|---|---|
| MORTA | 126 | apagadas via `podar.py`. Lista: `morta_outros_20260908.tsv` (138 = 126 + 11 campo/os + 1 users) |
| campo/os | 11 | `ordens_servico` = 0 → decisão: apagar junto |
| LIGAR | 26 | tela/ação no redesign (lote LIGAR deste dia) |
| INTERNA | restante | ficam (MCP, orquestrador, oráculos, tasks) — `podar.py` recusa handler importado fora do controller |

LIGAR (26): cashflow summary/trends/breakdowns; payables process-recurring + installments; liminares PUT status; dre-consolidado; precificacao simulador; inventory/real; ged-integration contracheques; signatures empresa/assinar-lote; portal operacao assiduidade/escalas; portal financeiro resumo; avisos nao-lidas; diarias resumo-gerencial; webhooks inter configurar/status; whatsapp agent/dashboard.

Constantes de módulo engolidas pela poda (ROBOT_URL do det, `_CATEGORIAS_FISCAIS` onvio, `_AGENDAMENTO_PADRAO` ged config, `_STATUS_MAP/_TIPO_DESC` esocial) foram restauradas de HEAD via `restaurar_const.py` + ruff F821 = 0.
