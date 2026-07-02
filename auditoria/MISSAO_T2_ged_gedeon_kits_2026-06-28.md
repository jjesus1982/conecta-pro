# Missão t2 — Mapa Funcional + PRD: GED + GEDEON + Document-Kits ("Central de Documentos e Montagem de Kits")
**De:** t1 · **Para:** t2 · **Data:** 28/06/2026
**Tipo:** auditoria/mapeamento READ-ONLY (não alterar nada; só investigar e documentar)

## Por que este bloco
É o maior volume de trabalho real e crítico do sistema, e é **fundamental pra montar os kits** (negócio-núcleo da operação contábil/documental). Hoje:
- **~296 rotas de backend**: `modules/ged` (205) + `modules/gedeon` (37) + `modules/document_kits` (54).
- **Frontend raso/espalhado**: telas em `frontend/src/app/modulos/gestao-pessoas/ged/*` E `frontend/src/app/modulos/documentos/*`. Pontos críticos quase vazios: `ged/kits` (1 chamada de API), `documentos/kits` (0), `documentos/page` (0), `ged/onvio-sync` (0).
- **GEDEON = engine de IA** com 7 agentes (`argos, atlas, hermes, kronos, sophia, themis`) fazendo classificação de documento, conformidade, anomalia, contexto por cliente/competência — **praticamente sem UI**.

## O que entregar (PRD + mapa, NÃO código)
1. **Fluxo end-to-end de montagem de kit** (o mais importante): do recebimento/coleta do documento (Onvio/GDrive/upload) → classificação (GEDEON/hermes) → vinculação a cliente/competência → montagem do kit (document_kits) → conformidade/validação → assinatura/envio. Diagrama em texto + onde CADA passo tem (ou não) tela.
2. **Catálogo dos 7 agentes GEDEON**: o que cada um faz, quais rotas expõe (`modules/gedeon/controllers/*`), e se há UI consumindo. (argos, atlas=insights/anomalia, hermes=classificar, kronos, sophia, themis.)
3. **Matriz rota↔tela** para os 3 módulos: as ~296 rotas → qual tela consome (se alguma). Marque ✅ coberto / ⚠️ parcial-raso / ❌ sem UI / 🔧 infra.
4. **Inventário de cascas e quebras**: telas que existem mas não chamam API (ex.: `documentos/kits`, `documentos/page`, `ged/onvio-sync`) e telas que chamam mas estão rasas vs o backend (ex.: `ged/kits` com 1 chamada contra 54+ rotas de kit).
5. **Lista priorizada de gaps + spec de tela**: para cada gap relevante ao negócio, uma mini-spec (o que a tela precisa mostrar/fazer + quais endpoints já existem pra ligar). Priorize o que destrava montar kit de verdade.

## Como investigar (read-only, seguro)
- Backend: `grep -rE "@router\.(get|post|put|patch|delete)" modules/{ged,gedeon,document_kits}` + ler controllers/services pra entender o fluxo.
- Frontend: telas em `gestao-pessoas/ged/*` e `documentos/*`; ver o que cada `page.tsx` chama (`grep fetch/customInstance`).
- Token p/ inspecionar respostas (GET apenas, NÃO escrever): login form-urlencoded `jjesus@conectamais.pro` / senha no chat, base `http://127.0.0.1:8080`.
- DB read-only: `docker exec conecta-pro-postgres psql -U postgres -d conecta_pro` (tabelas `document_kits`, `ged_*`, `gedeon_*`, `onvio_*`) só pra SELECT/contagem.
- **NÃO** rodar escrita, NÃO disparar IA pesada/Onvio sync (efeito externo), NÃO alterar arquivo.

## Saída
Um relatório `.md` (com o diagrama de fluxo + as 5 entregas acima). A partir dele, eu (t1) implemento + faço o E2E funcional (criar→editar→excluir) de cada gap, como na rodada das 276 telas.

## O que o t1 (eu) faço em paralelo
**Gestão de Pessoas em profundidade (DP/Folha + RH)** — o coração: rescisão completa (cálculo/verbas), accrual de férias, config/aplicação de benefício, wiring de bater-ponto + banco-horas, onboarding. Implementação + E2E. Assim não colidimos (você mapeia GED/GEDEON/kits; eu implemento Pessoas).

## Contexto técnico que ajuda
- GED frontend está dividido entre `gestao-pessoas/ged` e `documentos` — vale recomendar unificar.
- Integrações Onvio/GDrive/GEDEON são backend (infra) — distinga "infra sem UI por design" de "gap de tela real".
- Atenção a placeholders: `useState([])` sem fetch = casca (foi o caso de `servicos/*`).
</content>
