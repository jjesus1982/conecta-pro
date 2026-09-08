# Lote A — 130 rotas restantes de people-management / users / reimbursement / recruitment (08/09/2026)

Vereditos do agente (código + count(*) no banco, só SELECT): MORTA 5 · REDUNDANTE 36 · LIGAR 49 · INTERNA-ESCONDIDA 40.

Achados que mudaram a leitura:
- `frontend/src/app/portal-funcionario/*` só redireciona para `/modulos/meu-espaco` — o portal VIVO do funcionário é o meu-espaco
  (1.635 batidas faciais em 30 dias, 41 contingências). Passou a contar como app do redesign no medidor.
- Hermes (`tools_read_dp.py:362-376`) ainda importa `list_positions/list_open_positions` do recruitment; não apagar sem aposentar a tool.
- `agents/` lista URLs mas o orquestrador de agentes não roda (sem cron/pm2).

Aplicado: 30 handlers apagados (`apagar_A.tsv`); 3 ficaram por import do orquestrador (portal/dashboard, my-vacations/balance,
rh/consultor/panorama); `dp/payroll/pay-batch` ficou (decorator fora do padrão; dinheiro — não mexer sem o dono).
Fica intocado por decisão do dono (07/09): `/api/v1/reimbursements/*` (6 rotas).
LIGAR construídos no lote 5: usuários (aprovar/ativar/desativar/permissões), CCT cargos (PUT) e feriados (DELETE), onboarding
pendências, desempenho visão integrada, S-2200 gerar XML, links PJ por empresa, certificações da folha por competência, espelho
solicitar homologação, folha PIX prévia/status, calendário legal SST, esteira PCMSO, prontuário SST, ASO retroativo (PDF), CAT
abrir e transmitir (gated), ficha de EPI gerar, mapear risco, direitos CCT do funcionário, simulador de rescisão, histórico e
execução da coleta GED.
