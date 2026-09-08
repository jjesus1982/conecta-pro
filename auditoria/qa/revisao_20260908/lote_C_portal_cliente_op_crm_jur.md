# Lote C — 84 rotas restantes de client_portal / operacional / clients / crm / juridico (08/09/2026)

Vereditos: INTERNA-ESCONDIDA 48 · REDUNDANTE 19 · LIGAR 16 · MORTA 1 · EXTERNO 0.

Por que o medidor não via (todos ensinados ao `checar_cobertura_rotas.py` no mesmo dia):
1. Área do cliente monta a URL com `${API_BASE}` e passa por `services/portal/portalApi.ts` (fora dos globs).
2. f-strings com prefixo curto (`/crm/leads/{id}`, `/clients/{id}/activate`) — limiar de 12 chars descartava.
3. Handler passado por referência (`chamar(K.listar_playbook, …)`) — índice exigia `alias.fn(`.
4. `RdBell.tsx` importa `src/hooks/useNotifications.ts` (classificado como clássico).
5. Concatenação implícita de literais em `agents/modules/dp_agentes.py`.

Aplicado: 9 handlers apagados (`apagar_C.tsv` + performance-overview e ws/status à mão — decorators `ai_router`/`websocket_router`);
7 ficaram por import do orquestrador; alias `/operacional/assinaturas/documento/{id}` ficou (mesmo handler do path people-management).
LIGAR construídos (lotes 3 e 4): diaristas editar/inativar, gerar escala, salvar template, passagem lida, comunicados leituras,
placar dos consultores, indicadores de rondas, assinaturas das medidas, leads mudar status, clientes editar (PUT), DET e processo por
arquivo (multipart), área do cliente: assiduidade, escalas, badge de avisos não lidos, resumo financeiro.
