# DGX F12 — SESMT (tipos de exame, médicos) · Demandas (assuntos, atendimentos, feedbacks, diretórios) · Comercial (fontes pagadoras, regiões, postos por cliente)

**Data:** 24/09/2026 · **Branch:** `dgx/f12-sesmt-demandas-comercial` · **Sandbox:** `conecta_pro_staging` (cópia de produção de 23/09)
**Arquivo:** `backend/modules/operacional/controllers/redesign_builders/_dgx_f12_sesmt_demandas_comercial.py`
**Oráculo:** `backend/scripts/orq/test_oraculo_sesmt_demandas_comercial.py` — VERDE (TOTAL falhas: 0)

## §1 Estado antes (medido no sandbox)

### O mapa das duas tabelas de ASO — e quem escreve em cada uma

| Tabela | Linhas | Model | Quem ESCREVE | Quem LÊ | Veredito |
|---|---|---|---|---|---|
| `gp_asos` | 97 (52 admissional realizado · 44 periódico vencido · 1 demissional agendado) | `people_management/sst/models/aso.py` (`ASOModel`) | `sst_controller` POST `/sst/aso` (agendar), POST `/sst/aso/retroativo`, PUT resultado; `_dgx_f6_dp`; `operacional/tasks.py` | aba Exames, Alertas, «ASOs vencendo», esteira PCMSO, calendário legal, `sst_alerts_tasks`, tools do Hermes (`asos_vencendo`, `funcionarios_sem_aso`), `esocial_service` (S-2220), kronos/gedeon | **VIVA** |
| `health_asos` | 97 (espelho de 16/03/2026; `updated_at` idêntico ao de `gp_asos`) | `health_occupational/models/pcmso.py` (`ASO`) | só `health_occupational/services/pcmso_service.py::emitir_aso` — **Session síncrona, sem rota montada**; testes unitários | `module_integrator` (anti-procrastinação) por nome; `sst_alerts_tasks` a abandonou em 07/09 («família morta») | **MORTA** — cópia de março que ninguém atualiza |

Tudo nesta frente lê e grava `gp_asos`. `health_medical_exams` (1 linha, agendamento de 03/2026) é da mesma família morta.

### O resto
- Médico do ASO era texto: `medico='Dr. Carlos Mendes'`, `crm='CRM-AM 4521'` em 96/97 linhas; 1 linha com `clinica='Clínica a confirmar pelo DP (teste do fluxo 07/09/2026)'`.
- `sst_pcmso` (1 linha, OCR de 08/07/2026): coordenador **DR. POJUCAN MANOEL MORAES, CRM/AM 467**, vigência 05/2026–04/2027, `exames_por_funcao` com 3 grupos (PORTARIA → AGP, LIDER; MANUTENCAO → ARTIFICE; CONSERVACAO_E_LIMPEZA → ASG, JARDINEIRO) e códigos da Tabela 27 (4 exames sem código: espirometria, RX tórax, ECG, EEG — «NÃO verificados» no próprio OCR).
- `gp_asos.exames` só cita «Avaliação clínica ocupacional» (0295) em 96 linhas.
- Não existiam: tipos de exame, médicos, assuntos, atendimentos, fontes pagadoras, regiões.
- Demandas: `ouvidoria_manifestacoes` 4 (todas «aberta», de 07/2026, texto de teste); `client_portal_tickets` 5 (seed de 01/2026); `feedback_insights` 0; NPS (`crm_followups.template='nps'`) 0 respostas; `cwi_message_log` 4.448 mensagens (a conversa, não o atendimento).
- Diretório: `crm_contacts` 20 (Síndico 4, Síndica 2, Contato principal 11, Presidente 1, Vice 1, Representante legal 1); `clients.financial_contact_*`/`technical_contact_*` todos NULL nos 29; `posts.emergency_contact` NULL nos 17.
- Comercial: `clients` 29 (todos `active`, `regiao` inexistente), `posts` 17 (`required_headcount` = contratado), `allocations` 67 ativas (a fonte de `grade_do_posto`); `employee_alocacoes` (F5) 51 ativas com `posto_id` NULL em 51/51 (aponta `condominios`, não `posts`).
- Ativos sem ASO válido (último ASO vencido ou sem ASO realizado): **57 de 63** — AGENTE DE PORTARIA 34+1, ASG 12, ARTÍFICE 4, JARDINEIRO 3, LÍDER 3.

## §2 O que o DGX tem
- **SESMT:** ASO (`/SaudeOcupacional`: data, vencimento, tipo (6), entregue, resultado apto/restrições/inapto, `idMedico`), Médicos (`/Medicos`: nome, CRM (8), telefone, UF), Tipos de Exames (`/Exames`: descrição, validade 3/6/12 meses).
- **Demandas:** Assuntos (`/AssuntosOcorrencias`), Atendimentos (`/Atendimentos`), Demandas (`/OcorrenciasAssuntoFixo`), Diretórios (`/DiretoriosCliente`), Feedbacks (`/Feedback`), CRM (`/Visitas`).
- **Comercial:** Clientes, Fontes Pagadoras (`/FontesPagadoras`: razão social, nome fantasia, PJ/PF, inscrição nacional), Postos (`/PessoaPostos`: código/remota, endereço, lat/long/raio), Contratos, Regiões (`/view/regioes`, SPA).

## §3 O que foi feito

### DDL que `_ensure` aplica em produção no 1º acesso (idempotente)
```
CREATE TABLE sst_tipos_exame (id, nome UNIQUE, codigo_esocial, periodicidade_meses, obrigatorio_admissional/periodico/demissional/retorno/mudanca_funcao, por_funcao jsonb, custo_ref, ativo)
CREATE TABLE sst_medicos (id, nome, crm, uf, especialidade, clinica, telefone, responsavel_pcmso, ativo, UNIQUE(crm, uf))
ALTER TABLE gp_asos ADD medico_id int, tipos_exame_ids jsonb
CREATE TABLE dem_assuntos (id, nome UNIQUE, area, sla_horas, responsavel_padrao, ativo)
CREATE TABLE dem_atendimentos (id, numero, assunto_id FK, origem, cliente_id, employee_id, externo_nome/telefone, descricao, status CHECK, atribuido_a, aberto_em, resolvido_em CHECK (>= aberto_em), resolucao, satisfacao CHECK 1-5, ref_tipo, ref_id, aberto_por) + índice (status, aberto_em)
CREATE TABLE crm_fontes_pagadoras (id, cliente_id, razao_social, cnpj char(14), endereco_cobranca, email_nf, condicao_id → fin_condicoes_pagamento, dia_vencimento, ativo, UNIQUE(cliente_id, cnpj))
CREATE TABLE crm_regioes (id, nome UNIQUE, uf, municipios jsonb, supervisor_employee_id, cor, ativo)
ALTER TABLE clients ADD regiao_id int · ALTER TABLE posts ADD regiao_id int · ALTER TABLE receivable_accounts ADD fonte_pagadora_id int
```
**Seed (ON CONFLICT DO NOTHING):** 11 tipos de exame lidos de `sst_pcmso.exames_por_funcao` (com código Tab. 27 e funções → cargos de `employees`) + o 0295 dos ASOs (deduplicado por código); 2 médicos (Pojucan CRM/AM 467 = coordenador PCMSO; Carlos Mendes CRM/AM 4521, dos ASOs); 7 assuntos com SLA; 1 região «Manaus/AM» (sem supervisor — acusada de propósito).

### Telas (deep-link `/redesign/<modulo>?t=<id>`)
| Módulo | id | O quê |
|---|---|---|
| saude-ocupacional | `tipos-exame` · `tipo-exame-novo` | tabela com Editar/Inativar; form |
| saude-ocupacional | `medicos` · `medico-novo` | idem; «Coordenador» do PCMSO único |
| saude-ocupacional | `exames-por-funcao` | matriz função × exame obrigatório × vencidos (34 linhas), filtro por função, nomes de quem está vencido |
| saude-ocupacional | `aso-agendar` | form de ASO com select de médico e ids de exames dos cadastros |
| departamento-pessoal | `renovar-aso` (g-saude) | o form existente **trocado** pelo mesmo de cima (endpoint `aso-agendar` → chama `sst_controller.agendar_aso` e completa médico/CRM/clínica/exames em `gp_asos`) |
| crm · «Demandas & atendimentos» | `atendimentos` · `atendimento-novo` · `demandas-assuntos` · `demanda-assunto-novo` · `feedbacks` | atendimentos com **SLA vencido em vermelho**, filtro Abertos/Encerrados, ações Assumir/Resolver (resolução + satisfação 1–5); ouvidoria (4) e portal (5) LIDOS como atendimentos; feedbacks = NPS + satisfação + insights por cliente/mês |
| crm · «Clientes & contatos» | `diretorios-cliente` · `diretorio-contato-novo` · `postos-por-cliente` | 23 contatos por papel (síndico/zelador/administradora/financeiro/emergência); form reusa POST `/crm/contacts/`; 15 postos ativos com contratado × alocado hoje e diferença |
| crm · «Fontes pagadoras & regiões» | `fontes-pagadoras` · `fonte-pagadora-nova` · `regioes` · `regiao-nova` | CNPJ validado por `validar_cnpj`; condição de pagamento da F11; região com Editar + «Vincular» cliente/posto; sem supervisor ativo = badge vermelho |
| financeiro | `registrar-conta-receber` (g-receber) | ganha select «Fonte pagadora»; envio passa por `receivable-fonte` → `_conta_com_condicao` (F11) → grava `fonte_pagadora_id` |

Ações (todas em `/api/v1/redesign/action/…`, router incluído por `crm.py`): `tipo-exame-salvar`, `medico-salvar`, `aso-agendar`, `assunto-salvar`, `atendimento-salvar`, `atendimento-assumir`, `atendimento-resolver`, `fonte-pagadora-salvar`, `regiao-salvar`, `regiao-vincular`, `receivable-fonte`.

Plugs: `crm.py` (+20: router, 12 itens de menu com `grupo`, `telas_crm`), `saude_ocupacional.py` (+10: 6 itens no `EXTRA_MENU`, `telas_sst`), `departamento_pessoal.py` (+3: `ligar_aso_form` antes de `montar_grupos`), `financeiro.py` (+3: `telas_fin` depois do F11, antes de `montar_grupos`).

## §4 Oráculo
```
bash: docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" --tmpfs /app/logs --tmpfs /app/uploads -e PYTHONPATH=/app ... conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_sesmt_demandas_comercial.py
```
**ANTES do código (vermelho):**
```
FALHOU: builder _dgx_f12_sesmt_demandas_comercial não importa: cannot import name '_dgx_f12_sesmt_demandas_comercial' from 'modules.operacional.controllers.redesign_builders'
TOTAL falhas: 1
```
**DEPOIS (verde):**
```
OK: tipos de exame/médicos seedados do PCMSO e dos ASOs; matriz por função == SQL; atendimento com CHECK e SLA; ouvidoria lida sem migrar; CNPJ validado; região sem supervisor acusada; postos contratado×alocado == allocations
TOTAL falhas: 0
```
O que afirma: fiação nos 4 builders; 6 tabelas + 3 colunas; médico do PCMSO seedado; vencidos por função == SQL próprio (57 ativos, função a função); CHECK `resolvido_em >= aberto_em` recusa inserção inválida; `sla_vencido` 5h/SLA 4h = True e 1h = False; `resolver_atendimento` grava; lista = dem + 4 ouvidoria + 5 portal, sem migração; CNPJ `11.111.111/1111-11` recusado e `35.710.481/0001-03` gravado só dígitos; região sem supervisor acusada; 17 postos contratado × alocado == `allocations` ativas. Fixtures 'FIXTURE DGX F12' apagadas no início (sobra de rodada quebrada) e no fim.

**Prova HTTP** (container `teste-dgx-f12`, porta 8212, parado ao fim): 4 módulos montados (saude 29 telas, crm 82, DP 108, financeiro 173), 18 ids presentes com porta; 11 ações exercitadas — ASO agendado com Pojucan + 2 exames gravados em `gp_asos` (`medico_id=1`, `tipos_exame_ids=[1,2]`, `exames` com 2 itens); atendimento DEM-2026-0007 aberto → assumido → resolvido (`aberto_em <= resolvido_em`, satisfação 4); CNPJ inválido 400; recebível R$ 100,00 com `fonte_pagadora_id`; região vinculada a cliente e vista na tela. Limpeza: `sobras = 0`.

## §5 O que NÃO foi feito e por quê
- **Não migrei** `health_asos`/`health_medical_exams` nem apaguei nada: são cópia morta; apagar tabela exige o rito de `feedback_apagar_pacote` (importadores no repositório inteiro + boot de prova). Fica para o dono (§7).
- **`exames` do ASO no form são ids separados por vírgula** (o DSL não tem multi-select). A lista de ids está na tela Tipos de exame. Se o front ganhar `multiselect`, é trocar o `type`.
- **Periodicidade** dos 11 exames seedada em 12 meses (NR-7 permite 24 para <45 anos sem risco; o PCMSO da casa diz anual) — o dono ajusta na tela.
- **Matriz de exames** cruza «vencido» pelo ASO (último ASO da pessoa), não exame a exame: `gp_asos.exames` só registra o clínico, não há dado de audiometria/hemograma por pessoa. Quando os ASOs novos gravarem `tipos_exame_ids`, a matriz pode descer ao exame.
- **Chamados do portal** (`client_portal_tickets`) e ouvidoria são LIDOS, sem ação de assumir/resolver aqui — resposta continua na tela de origem (F8 está com «chamados»; não colidi).
- **Postos por cliente** usa `allocations` (a fonte da grade), não `employee_alocacoes` (F5) — esta não tem `posto_id` preenchido (51/51 NULL). Quando F5 preencher `posto_id`, trocar a subquery é uma linha.
- **NFS-e não muda**: fonte pagadora só existe como coluna em `receivable_accounts` e select no form; a emissão (`nfse_multi_empresa_service`) continua tomando o cliente. Apontar a NFS-e para a fonte é decisão fiscal (§7).
- Não toquei em `frontend/`, `_frente_*`, `_dgx_f*` alheios, `alembic/`, `checar_regressao.py`, `sst_controller`.
- `checar_tela_sem_porta` não rodado por mim (precisa do servidor mesclado); todos os ids estão no `extraMenu`/grupos — provado por HTTP.

## §6 Como o Jordan testa amanhã
1. Saúde Ocupacional → **Tipos de exame**: 11 linhas (5 com código Tab. 27, 4 sem — preencha «Editar» → código). **Médicos**: Pojucan (Coordenador) e Carlos Mendes.
2. Saúde Ocupacional → **Exames por função**: filtre «AGENTE DE PORTARIA» → 6 exames, 35 vencidos em vermelho com os nomes.
3. DP → Saúde & eSocial → **Agendar/renovar ASO**: escolha colaborador, tipo, data, médico = Pojucan, exames «1,2», Agendar → aparece em «ASOs vencendo»/Exames como agendado.
4. CRM → **Demandas & atendimentos → Atendimentos**: 9 linhas (4 ouvidoria + 5 portal). **Novo atendimento** (assunto «Falta / cobertura», origem WhatsApp, cliente) → volta à lista → **Assumir** → **Resolver** com satisfação → some de «Abertos», entra em **Feedbacks** no mês.
5. CRM → **Assuntos**: edite o SLA de «Falta / cobertura no posto» (4h) e veja o efeito no vermelho da lista.
6. CRM → **Clientes & contatos → Diretórios do cliente**: filtre um condomínio; **Incluir no diretório** (papel Zelador) → aparece.
7. CRM → **Postos por cliente**: Ideal Flores 12 × 14 (+2 azul), Green Hills 4 × 1 (−3 vermelho), Prime Arena 6 × 4.
8. CRM → **Fontes pagadoras → Nova**: cliente Michelangelo, razão social da administradora, CNPJ real, condição «30 dias», dia 10 → Financeiro → Contas a receber → **Registrar conta a receber**: o select «Fonte pagadora» lista a nova.
9. CRM → **Regiões**: «Manaus» em vermelho (sem supervisor) → Editar → supervisor → some o vermelho → **Vincular** cliente/posto.

## §7 Decisões que só o dono pode tomar
1. **`health_asos` / `health_medical_exams` / `pcmso_service.emitir_aso`**: apagar a família morta (rito de `feedback_apagar_pacote`) ou deixar como está? Hoje é cópia de março que ninguém lê nem grava.
2. **Códigos Tab. 27 em branco** (espirometria, RX tórax, ECG, EEG): confirmar com a MBS/Pojucan antes de declarar no S-2220.
3. **Periodicidade por exame** (12 vs 24 meses) e **custo de referência** por exame (a clínica cobra quanto?).
4. **NFS-e apontar para a fonte pagadora** (tomador = administradora em vez do condomínio): muda o XML e a retenção — não fiz.
5. **Supervisor da região Manaus** e se regiões fazem sentido com 29 clientes na mesma cidade (talvez por zona: Norte/Centro-Sul/Ponta Negra).
6. **SLAs seedados** (4h falta no posto, 48h holerite/boleto, 72h proposta, 120h ouvidoria) — chute honesto, ajustar na tela.
7. **Ouvidoria de teste**: as 4 manifestações de 07/2026 são texto de teste, todas «aberta» há 2 meses — responder ou expurgar?
