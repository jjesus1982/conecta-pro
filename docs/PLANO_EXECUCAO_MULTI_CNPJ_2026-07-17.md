# PLANO DE EXECUÇÃO — Multi-CNPJ Grupo Conecta Mais

**Versão:** 1.0 · **Data:** 2026-07-17 · **Status:** AGUARDANDO "PODE EXECUTAR" do Jordan
**Docs-irmãos:** `PREMORTEM_MULTI_CNPJ_2026-07-17.md` · `PRD_MULTI_CNPJ_2026-07-17.md` · `PLANO_MULTI_CNPJ_GRUPO_CONECTA_2026-07-17.md` (diagnóstico com arquivo:linha de cada ponto)

**Papéis:** `[C]` Claude t1 (executor técnico) · `[J]` Jordan (destravas externas/decisões) · `[P]` Portte (transição trabalhista, folha oficial) · t2/t3 = outros terminais (território próprio, fora deste plano).

**Ritual obrigatório de toda frente com migration:** drift-check ORM → snapshot rotulado do banco → staging → migration ADITIVA com backfill=CNPJ1 (nunca NOT NULL na 1ª leva) → suítes release → blue-green → suítes release de novo. Sem exceção (pré-mortem F12/F15).

---

## FASE 0 — Destravas externas [J] — INICIAR IMEDIATAMENTE (rodam em paralelo a tudo)

| # | Item | Dono | Limite | Bloqueia |
|---|---|---|---|---|
| D1 | ~~Credencial produção Cora~~ **FEITO 17/07** (client-id + cert/key no Drive). RESTA: credencial de STAGE + contas de teste (suporteapi@cora.com.br) | [J] | 19/07 | E4 (sandbox) |
| D2 | Resposta da Portte: data/competência OFICIAL da sucessão + classTrib do CNPJ2 | [J]+[P] | 21/07 | E3 (fronteira) |
| D3 | ~~Dados cadastrais~~ **FEITO 17/07** (Drive: cartão CNPJ 66.014.833/0001-10, IM 721042001, contrato social, alvará, cert A1 .pfx). RESTA: comprovante de opção do Simples (p/ alíquotas/DAS) + credencial NFS-e Nacional/Manaus da Patrimonial | [J] | 21/07 | E1 ok; E5 aguarda |
| D7 | Desativar aprovação in-app p/ pagamentos via API no Cora (como feito no Inter) OU confirmação do suporte de que não existe | [J] | 24/07 | E4 (modo `api` vs `app`) |
| D4 | Procurações gov do CNPJ2 (eSocial p/ eventos SST nossos; e-CAC) | [J] | 24/07 | E3 (SST) |
| D5 | Aditivos assinados pelos 7 condomínios da Patrimonial | [J] | 30/07 | Virada jurídica |
| D6 | Verificar cadastro da empregadora na plataforma Sólides pós-transição | [J] | 28/07 | robôs GED/cadastro |

Checkpoint diário 18h [C]+[J]: status das frentes + externas; item externo parado 2 dias = escalar.

## ETAPA E1 — Fundação da identidade (18–19/07) [C]

1. Drift-check + snapshot rotulado (`pre_multicnpj_e1`).
2. Completar registro `conecta_patrimonial` em `empresas` (CNPJ, IM, cert path/senha, nfse_ambiente, status ativa) — dados de D3. Corrigir FK `condominiums`×`condominios` se o drift-check acusar.
3. Carregar cert2 no `CertificateStore` (chaveado por CNPJ); teste: assinar XML com cada cert.
4. Decisão `tenants`×`empresas` (proposta: `tenants` congelada, `empresas` = fonte única) + helper único `get_empresa()` substituindo `EMPRESA_PRINCIPAL_ID` triplicado.
5. Reconciliar `.env` raiz × `backend/.env` (inventário já feito); criar placeholders `CORA_*`; verificação lendo env DE DENTRO do container.
**Gate E1:** RF-01 verde; suítes release verdes; nada de comportamento novo (tudo dormante).
**Rollback:** restore do snapshot; registro da Patrimonial volta a `em_abertura`.

## ETAPA E2 — Contratos + identidade documental (19–22/07) [C]

1. Migration `contracts.empresa_id` (backfill CNPJ1) + trilha de auditoria.
2. Classificação canônica: 7 condomínios→Patrimonial; Parise/Gelain/Green Hills→Eletrônica; ESCRITÓRIO→Eletrônica (interno). Conferência com [J] antes do UPDATE.
3. Migrador consertado: UUID, persiste `empresa_id`, grava `ContractAddendum` tipo novo `transferencia_titularidade`; gerar aditivos p/ D5.
4. `pdf_branding` → `branding(empresa, competencia)`: fonte única lendo `empresas`; **fronteira histórica** (data de D2) em config versionada; 28 geradores herdando automaticamente; eliminar a 2ª fonte (`nfe_provider._EMITENTE`) e os hardcodes documentais mapeados.
**Gate E2:** RF-02, RF-03 (holerite 06/2026 byte-idêntico!), diff-zero de contrato/proposta do CNPJ1.
**Rollback:** `empresa_id` é aditiva — reverter é UPDATE p/ CNPJ1 + branding constante de volta (commit revert).

## ETAPA E3 — Espelhamento trabalhista + SST (20–26/07) [C][P]

1. Migrations `employees.empresa_id` + `hr_payslips.empresa_id` (backfill CNPJ1).
2. Espelhamento das datas oficiais da Portte (D2): script de virada com trilha; NADA muda até D2 chegar.
3. Trava SST: evento só transmite se empregador==empresa vigente do funcionário na data; seleção de cert por empresa; dry-run diário em produção-restrita.
4. Holerite/espelho de ponto: empregador por competência (consome E2.4). Patronal por regime (28% fixo → função por `regime_tributario`) e `ENCARGOS_PCT` por regime na precificação (valores novos validados com [P]).
5. Compliance CCT/risco trabalhista passam a filtrar por empresa (o `empresa_id` órfão dos schemas ganha origem).
**Gate E3:** RF-04, RF-05; conciliação sistema×Portte 100%; suítes release verdes.
**Degradação planejada:** se D2 atrasar, TUDO fica pronto e dormante; a virada dos funcionários é um script de 1 comando quando a data chegar.

## ETAPA E4 — Banco Cora + partição financeira (20–29/07) [C]

1. (20–22) `CoraAdapter` no contrato dos adapters (auth mTLS+OAuth2, saldo, extrato, invoice/PIX-cobrança, DARF/GPS, webhooks) — desenvolvido contra o **stage**; conta Cora registrada em `bank_accounts`.
2. (22–25) Partição por conta: `bank_account_id` nas tabelas bancárias; tetos/saldo-mínimo/caches Redis com namespace por conta; conciliação reescrita (morre `ILIKE '%inter%' LIMIT 1` e o `condominio_id` chumbado); beats em loop por conta ativa.
3. (25–27) Roteamento por empresa dona: `executar_lote` diaristas, cobrança recorrente, agenda de beneficiários (ganha dados bancários completos — exigência Cora), régua de cobrança IA, kit de fatura, telas de cobrança, portal do cliente (boletos dos 2 bancos).
4. (27–29) Produção: credencial real (D1), carga retroativa do extrato desde a abertura, webhook registrado, ensaio R$0,01 (cobrança e pagamento com aprovação no app).
**Gate E4:** RF-08, RF-09, RF-10; extrato Inter do CNPJ1 sem NENHUMA mudança; recebimento real do Mirante visível e conciliado.
**Degradação planejada:** se D1 atrasar, Cora opera em modo "pago/recebido pelo app + conciliação manual" com painéis "aguardando integração" — a virada NÃO trava.

## ETAPA E5 — Fiscal por empresa (22–27/07) [C]

1. `empresa_context` por `empresa_id` (morre `LIMIT 1`+cache); serviços NFS-e lendo config da tabela `empresas`; `optante_simples`/ISS derivados do regime (proibido default).
2. Migrations `nfse`/`nfe` + checkpoint NSU por empresa; matriz obrigação×regime explícita (CNPJ2: DAS; sem SPED-LR).
3. Importar NFS-e já emitidas da Patrimonial (pull pela credencial D3) — RF-07.
4. Homologação: emissão de teste das DUAS empresas; conferência campo-a-campo da nota CNPJ2 contra o
   **GABARITO REAL (NFS-e 10 e 11 do Mirante, no Drive)**: via NFS-e Nacional/DPS série 70000;
   códigos de tributação nacional **11.02.01** (portaria) e **07.10.02** (limpeza/jardinagem);
   "Optante Simples ME/EPP, apuração pelo SN"; ISSQN não retido/sem destaque; **INSS 11% retido na
   fonte pelo tomador (cessão de mão de obra)** → recebimento LÍQUIDO = bruto − 11% (conciliação E4
   deve casar líquido×nota bruta); notas substitutas encadeadas (importação trata `NFSe Subst`).
**Gate E5:** RF-06, RF-07; **diff-zero do XML do CNPJ1**; fixtures parametrizadas (E7.1) verdes.
**Degradação planejada:** se a credencial NFS-e do CNPJ2 atrasar, emissão da Patrimonial segue manual (como o Mirante) com importação posterior — documentado, sem improviso.

## ETAPA E6 — GED/GEDEON multi-CNPJ (22–27/07 — P1 pelo kit de 28/07) [C]

1. Certidões: coluna `cnpj` em `ged_certidoes`; sync CND/CRF/CNDT em loop pelas 2 empresas; painel duplo (RF-11).
2. Kit híbrido: resolução POR DOCUMENTO (NFS-e pela nota; guias pela competência/empresa; CNDs dos 2 conjuntos; comprovantes pelo banco de origem); classificador `is_matriz` reconhece as 2; nível de empresa no Drive.
3. Comprovante generator: empresa+banco do pagamento real (Inter OU Cora), não constantes.
**Gate E6:** RF-12 (kit de teste híbrido do Ideal Flores conferido por [J]).
**Checkpoint D-4 (24/07):** "GED pronto p/ kit de 28/07?" NÃO → pausar beat `montar_kits_mensais` e montar julho manualmente (decisão explícita, pré-mortem F11).

## ETAPA E7 — Rede de proteção (transversal, 18–29/07) [C]

1. (18–20) Parametrizar as 22 fixtures CNPJ1 → viram gate diff-zero. 2. Guard-lint anti-CNPJ-hardcode (molde `test_money_guardrail`). 3. Testes novos: identidade por competência, roteamento bancário, kit híbrido. 4. Specs Playwright multi-CNPJ (scaffolds existentes) preenchidos. 5. Suítes release após cada deploy.

## ETAPA E8 — Frontend + consultores + relatórios (24–30/07, P2) [C]

1. Filtro/seletor de empresa (visão, não tenancy); 7 telas com CNPJ chumbado; módulo `empresas` do front ligado à API real.
2. `estrutura_grupo()` (lendo `empresas`, como o jurídico já faz) injetado nos 8 consultores + rótulo "Grupo consolidado"; correção dos prompts com fatos velhos; PIX da régua de cobrança pela empresa do contrato (já em E4.3).
3. DRE/fluxo por empresa + consolidado (RF-15); MCP: parâmetro `empresa` nas ~40 tools (padrão `*_grupo` existente); tool do `financial_mcp_server` corrigida.
**Degradação planejada:** E8 inteira pode escorregar p/ 01–05/08 sem quebrar a virada (rótulo honesto entra ANTES, é 1 dia).

## ENSAIO E VIRADA

**29–30/07 — Ensaio geral em staging:** virada completa simulada (classificação, fronteira, kit híbrido, emissões homologação, Cora stage, suítes+E2E). Correções. Re-ensaio do que falhou.
**31/07 — GO-LIVE:** backup manual rotulado (`pre_golive_multicnpj`) → deploy final blue-green → runbook: conferir 10 contratos, fronteira ativa, certidões duplas, beats por empresa, painéis honestos → suítes release + E2E → monitoramento intensivo.
**01/08 —** vigência dos aditivos [J]; sucessão eSocial executada pela [P]; script de espelhamento dos funcionários rodado com as datas oficiais [C]; SST passa a sair pelo CNPJ2.
**02–05/08 —** primeira emissão NFS-e automática da Patrimonial; kit híbrido de julho entregue; conciliação Cora ativa; retrospectiva rápida + ajustes.

## WS9 — CAPACIDADE DE FOLHA ORGÂNICA (ago→out, pós-virada) [C][P][J]

*Regra-mãe: Portte é permanente; nada vira oficial sem o Jordan declarar o ponto de confiança; funcionário nunca vê número do motor paralelo.*
- **Ago (comp. 08):** motor próprio calcula em paralelo; relatório de convergência por rubrica×funcionário contra a Portte; corrigir: médias de variáveis, afastamentos INSS, pensão na base IRRF, IRRF certificado.
- **Set (comp. 09):** eSocial-folha em produção-restrita: S-1005/1010/1020 do CNPJ2 + ponte folha→S-1200/S-1210/S-1299 (transporte real já existe); DAS com Fator R alimentado pela folha; convergência de novo.
- **Out (comp. 10):** se convergência 100% por 3 competências e [J] aprovar → discutir oficialização com a [P] (que permanece como validação). Skills/agentes: "fechar-folha-mensal", conferidor (oráculo triplo: gov aceita + guia bate + Portte bate), "obrigações-do-mês" por empresa.

## Prioridade e degradação (resumo — pré-mortem F17)

| Prioridade | Etapas | Se atrasar |
|---|---|---|
| **P0** | E1, E2, E3, E6, E7.1 | NÃO degradam — são a virada |
| **P1** | E4, E5 | Degradam p/ modo manual documentado (app Cora + emissão manual + importação) |
| **P2** | E8 | Escorrega até 05/08 sem quebrar nada |
| Pós | WS9 | Ritmo próprio, gated por convergência |
