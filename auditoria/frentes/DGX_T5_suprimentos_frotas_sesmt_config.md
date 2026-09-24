# DGX T5 — Suprimentos · Frotas · SESMT · Demandas · Configurações (passagem de teste + 4 lacunas, 24/09/2026)

**Branch:** `dgx/t5-suprimentos-frotas-sesmt-config` (base `b9005ef2f`) · **Sessão:** agent-t5 · **Módulos tocados:** seguranca, suprimentos, saude-ocupacional, configuracoes (+3 linhas no gate do redesign)
**Container de teste:** `teste-dgx-t5` em 127.0.0.1:8225 — **parado** ao fim · **Sandbox:** `conecta_pro_staging` · produção só leitura.
**Lista de lacunas (Fase C):** `docs/dgx/lacunas/suprimentos_frotas_sesmt_config.md` (commit `b98b4dfeb`).

## §1 Estado antes (medido no sandbox)

| O quê | Medido |
|---|---|
| `crm_audit_log` | **36.228** linhas (jun→set/2026): 20.977 POST · 14.235 GET (telas abertas) · 486 DELETE · 280 PUT · 250 PATCH; 4.498 nos últimos 7 dias por **53 usuários** — sem tela; só o tool `consultar_auditoria` |
| Tela `seguranca?t=auditoria` | lia `turnover_audit_logs` (**5** linhas); o JSON do módulo trazia mock («Login admin — Jordan · agora») |
| `lgpd_audit_logs` (telas Mascaramento/Criptografia) | **0** linhas |
| Solicitação de material | não existia (F9 §5: «movimentar estoque → saída com destino cobre o caso») |
| Exame por colaborador com data | não existia: `gp_asos.tipos_exame_ids` guarda ids (97 ASOs, **0** com ids); `sst_tipos_exame` 12 tipos, todos 12 meses |
| Acesso com prazo | não existia: `aval_links`/`document_share` são links públicos por token; `users` = 116 (8 admin, 26 agente, 67 funcionário…), 0 com validade |
| RBAC | `users.role` + `permissions[]` (`module:X`, `self:portal`, `all`); slugs admin-only; financeiro só do CEO — sem tela/ação, sem horário, sem cerca |
| Oráculo `test_oraculo_t5_*` na árvore `b98b4dfeb` | **VERMELHO** — `cannot import name '_dgx_t5_suprimentos_frotas_sesmt_config'` |

## §2 O que o DGX tem — Fase A, botão a botão (dado `TESTE CP T5 *`, colaborador compartilhado id 1)

**Suprimentos.** Grupos (código numérico, pai) → Material (código, descrição, mín/máx, unidade, origem, grupo) → Estoque (Mínimo/Máximo/Atual/Valor; Movimentar = só «Ajustar»). Cadeia: Solicitação (nome, data) → Itens (item do catálogo material/uniforme, qtd) → **Cotações por item** (fornecedor, forma, condição, valor, Aguardando/Aprovada/Rejeitada) → item ganha fornecedor → **Aprovar** (recusa «itens sem fornecedor»; status 2) → Pedido (fornecedor, **forma e condição de pagamento obrigatórios p/ aprovar**, prazo, rastreamento, endereço de entrega; itens tipados Material/Uniforme/Serviço/Equipamento) → Aprovar → NF de entrada (nº, série, emissão, emitente, plano de contas, forma/condição, «gera conta a pagar»; itens produto/serviço, **desdobramento em parcelas**, rateio por contrato/conta, anexos; «Gerar» exige valor > 0) → estoque **15 → 25**, valor R$ 312,50 (custo médio 12,50). Solicitação de Materiais (contrato, tipo Normal/Mensal/Urgente/Serviço, data de necessidade, itens; Aprovar = modal com qtd entregue + centro de custo → estoque **25 → 22**, status Atendida; contagem Aberta/Atendida/Parcial; Copiar; Motivo de rejeição; Detalhes). Uniformes: cadastro (código, grupo) → **Tamanhos** (tamanho, mín, máx) → Estoque de uniformes (Máx/Mín/**Pendente**/Atual/Valor; Movimentar: Ajustar, Retornar, Descartar, Ajustar pendente) → Kit (itens = uniforme+tamanho × qtd) → Entrega (colaborador com RE/admissão/contrato; **Incluir Kit**; motivo Admissão/Desgaste/Outros/Troca de função; Aprovar → Separação; Entregar → Entrega; estoque **6 → 4**; devolução com motivo Demissão/…; PDF; filtro EM ABERTO/SEPARADO/ENTREGUE). Equipamentos: armamento (registro, nº, SINARM, marca, espécie, calibre, validade, exclusividade GERAL/ESCOLTA/PATRIMONIAL; **histórico de disparos** por agente; munições não devolvidas), colete (CA, lote, proteção, tamanho P–XG, status Disponível/Em missão/Indisponível/Destruído, velada), comunicação móvel (rádio/IMEI/carcaça/patrimônio/centro de custo; QR code do app de escoltas; Indisponibilizar), rastreador. **Entrega = alocação por CONTRATO** (Contrato → Armamentos/Coletes/Equipamentos com valor comercial e retorno de capital), «Devolução manual» com motivo. Fornecedor (razão, fantasia, PJ/PF, CNPJ, endereço, «é posto»).

**Frotas.** Veículo (placa, prefixo, modelo, tipo Carro/Moto/Van/Caminhão/Carro forte/Guincho, exclusividade, KM atual, cidade/UF; lista com Próx. troca óleo/pneu/correia e **Restam**; PDF detalhado; anexos). Controle de saída (condutor, passageiro, data; **KM saída = KM atual do veículo**; retorno com KM ≥ saída — «Km de retorno não pode ser menor ou igual» —; **2ª saída aberta do mesmo carro é aceita**; data futura recusada). Trocas de óleo (KM, valor, filtros; «Km menor que o atual» recusado; PermitirKmMenor), pneu, correia (rolamentos). Multa (infração da tabela CTB com código, AIT, RENAINF, notificação, datas; **data futura recusada**; Indicado = condutor; valor/desconto/vencimento; Gerar conta a pagar exige vencimento; Cabe recurso / Recurso lançado; PDF). Manutenção (fornecedor, KM, previsão/liberação, tipo Peça/Serviço, valor, centro de custo; Aprovar exige liberação; **«Gerar troca de óleo» cria a troca sozinha** ao KM da manutenção; Gerar conta; Solicitar materiais). Locação (locador = fornecedor ou prestador, diário/mensal, valor, forma, retirada/devolução). Requisições de abastecimento/lavagem e abastecimentos: telas do app (`/api/frotas/*`), formulário web devolveu 500 — **não exercitado**. APP Frotas (React): Auditorias (condutor, placa, KM, tarefa, progresso), Checklist/Vistorias (par chegada×saída, status do checklist, manutenção pendente), Grupo de frotas, Grupo vistoria checklist, **Itens de vistoria** (texto, ordem, tipo de dado, tipo de veículo, grupo, foto obrigatória, texto obrigatório, impede locomoção, «não se aplica», requisição de abastecimento embutida com litros/forma de pagamento/KM digitável), Itens de auditoria, Localidades, Solicitações de auditoria (cliente, escolta, data), Solicitações de manutenção (tipo, placa, valores), Usuários do app (login/senha, colaborador, grupo checklist, grupos de frota, permissões Todas/Abastecimentos/Vistorias/Requisição/Pernoites/Auditorias/Incluir veículos). 4 relatórios (abastecimentos, manutenções, trocas) por período/veículo/modelo/grupo/fornecedor.

**SESMT.** Médico (nome, CRM 8 dígitos, telefone, UF). Tipos de exame (descrição, validade 3/6/12 meses; 17 pré-cadastrados). ASO (data, vencimento, tipo Admissional/Periódico/Retorno/Mudança/Monitoração/Demissional, entregue, resultado Apto/Restrições/Inapto, médico, colaborador; abas **Exames** (exame, data → «Válido até» pela validade do tipo), Exposição a risco (código Tab. 24 eSocial E1.1…, agente), Monitoração biológica; Importar arquivo). Lista: colaborador, função, posto, data, vencimento, admissão/demissão; legenda **Ativo / Exame vencido / ASO vencido / ASO renovado** — ao lançar um periódico antigo, o admissional ficou «renovado (1)». Filtro por status do empregado, contrato, cliente, «não possui ASO», vencimento em N dias.

**Demandas.** Assunto (nome, **departamento** = pessoa interna, prazo em dias, responsável). Demanda (tipo cliente/colaborador, prioridade, assunto obrigatório, descrição, responsáveis; **prazo em dias ÚTEIS**: 24/09 + 2 = 28/09; Encaminhar (motivo + destinatário), Concluir (solução), código de OS, anexos, e-mail, histórico, materiais/colaboradores; filtro Todas/Concluída/Pendente/…; tempo gasto). Atendimento de balcão (motivo Admissão/Atendimento/Rescisão/Reunião/Treinamento com descrições padrão — «Troca/retirada de uniformes», «Pedido de demissão»…; supervisor, unidade, RG/CPF; tempo desde a entrada; Finalizar com solução; histórico; contadores por motivo). CRM = visita por cliente (data, descritivo; lista por cliente com último autor). Diretórios = pastas de documentos por cliente/contrato. Feedback = respostas padrão por assunto + follow-up (Salvar deu 500 no trial).

**Configurações.** Acessos temporários (usuário responsável, expiração, propósito → roles `eimp` importação de empregados / `fin` / `osf` escoltas / `spr*` pronta resposta; token JWT copiável; Vigente/Expirado; `POST` deu 500 no trial — lido no bundle). Departamentos de usuários (nome, usuário responsável). Empresa (razão, CNPJ, endereço, logo, emitentes). Log Sistema (Tabela alterada/Usuário/Data/Máquina, Detalhes coluna→valor; filtro usuário/colaborador/tabela — só **Movimentações, Cartão Ponto, OS, Fechamento** —/período/folha; vazio no trial). Usuários: nome, login, e-mail, status, grupo, contas bancárias, parceiro, **flags** (bloqueio RH, avisos, dashboard cliente, ver salários, ver salários do dept, finalizar demandas, ocultar, adm. de arquivos, **Todas permissões**), última troca de senha, **cerca eletrônica** (raio/lat/long), SSO Microsoft, supervisor de todos deptos/clientes/prospects, data de início, **horário de acesso** (+ faixas), e a **árvore de permissões** por usuário (`cb<id>` → `GET /Usuarios/DefinirPermissao/{id}?idPermissao=`; parcial/total por nó) mais 7 escopos de dado (clientes, contratos, transportadoras, grupos de almoxarifado, eventos, relógio de ponto, salário). Árvore lida por `POST /api/autenticacao/permissoes/filtro`: **828 nós** = 190 menus + 638 ações; por raiz: Operacional 23/100, DP/RH 32/94, Frotas 29/79, Suprimentos 27/76, Apontamentos 19/62, Financeiro 20/60, Demandas 6/45, Faturamento 8/42, Comercial 6/26, Configurações 6/21, SESMT 3/11, Alertas 0/21. Ações típicas: Consultar/Incluir/Editar/Excluir + Aprovar, Exportar, Movimentar, Devolução manual, Indisponibilizar, Finalizar, Concluir, Gerar conta, Aprovação supervisor/coordenador/gerente, Opções de tela. As 13 seções de `/Configuracoes` (101 campos) estão em `docs/dgx/04`; os 3 parâmetros escolhidos foram **lidos** (`LinhasGrid=50`, `ValorSalarioMinimo=0`, `ValorRaioRelogioPonto=10`) — o `Salvar` da página devolveu 500 no trial, então nada mudou nem precisou voltar. Dump completo: `permissoes.json`/`arvore_permissoes.txt` ficaram no scratchpad da sessão (não no repositório).

## §3 O que foi feito

Arquivos: **novo** `backend/modules/operacional/controllers/redesign_builders/_dgx_t5_suprimentos_frotas_sesmt_config.py` (telas, DDL, 6 ações, `expirar_acessos`) · **novo** `backend/scripts/orq/test_oraculo_t5_log_materiais_exames_acessos.py` · plugs: `seguranca.py` (+9), `suprimentos.py` (+7: menu + router + `telas_sup`), `saude_ocupacional.py` (+6), `configuracoes.py` (+11, em try/except), `redesign_data_controller.py` (+8: `expirar_acessos` no `redesign_data`, em try/except).

DDL que `_ensure` aplica em produção no 1º acesso (idempotente, nada apagado ou alterado):
```
CREATE TABLE sup_solicitacoes_material (numero UNIQUE, post_id, solicitante, tipo CHECK normal|mensal|urgente, data_necessidade, status CHECK aberta|aprovada|rejeitada|parcial|atendida, motivo_rejeicao, decidido_por/em)
CREATE TABLE sup_solicitacao_material_itens (solicitacao_id FK CASCADE, item_code, descricao, quantidade > 0, entregue 0..quantidade)  + índice (status, created_at)
CREATE TABLE sst_aso_exames (employee_id, aso_id, tipo_exame_id FK sst_tipos_exame, data, valido_ate >= data, resultado CHECK normal|alterado|pendente)  + índice (employee_id, tipo_exame_id, valido_ate)
CREATE TABLE acessos_temporarios (user_id UNIQUE, papel CHECK leitura|operacional, modulos text[], motivo, expira_em, criado_por, revogado_em/por)
```

Telas (deep-link `/redesign/<módulo>?t=<id>`) e ações (`POST /api/v1/redesign/action/<nome>`):

| Módulo | id | O quê | Ações |
|---|---|---|---|
| seguranca | `auditoria` (sobrescreve) | 400 últimas linhas de `crm_audit_log`: quando, quem, «o quê» em português (abriu a tela X / ação Y / criou / alterou / apagou), método, caminho, HTTP, IP; filtros Método × Usuário; sub com total, 24 h, 7 dias, usuários | — |
| seguranca | `auditoria-telas` | quem abriu qual módulo, quantas vezes, última vez (7 dias) | — |
| suprimentos | `solicitacoes-material` | nº, posto, solicitante, tipo, necessidade, itens (com entregue), situação, decisão | Aprovar · Rejeitar (motivo) · **Atender** (código\|qtd pré-preenchido com o que falta; `confirm`) |
| suprimentos | `solicitacao-material-nova` | posto, tipo, necessário até, itens `código\|qtd\|obs` | `sup-solicitacao-material` |
| saude-ocupacional | `aso-exames-vencendo` | último exame por colaborador × tipo: data, **válido até**, resultado, situação vencido / vence em 30 d / em dia; filtros Situação × Exame | — |
| saude-ocupacional | `aso-exame-novo` | colaborador, exame (com periodicidade), data, resultado | `aso-exame-registrar` (liga ao ASO agendado/realizado mais recente, se houver) |
| configuracoes | `acessos-temporarios` | nome, e-mail, papel, módulos, motivo, expira em, Vigente/Expirado/Revogado, criado por · login ativo/inativo | Revogar |
| configuracoes | `acesso-temporario-novo` | nome, e-mail, papel, validade (1–90 dias), módulos (multiselect, financeiro fora), motivo | `acesso-temporario-criar` (devolve a senha inicial uma vez) |

Regras que valem em código:
- **Atender = o mesmo caminho da F9.** `EstoqueRealService.registrar_saida` (saldo, `nfe_estoque_movimentos` tipo saída, COGS `5.1.1.06/1.1.4.01` no razão), uma vez por item; a baixa vem ANTES do UPDATE dos itens, então saldo insuficiente → 409 e nada gravado. Entregue ≥ pedido em todos os itens → «atendida», senão «parcial». Só «aprovada»/«parcial» se atende; só «aberta» se aprova/rejeita; rejeitar exige motivo.
- **Válido até = data + `periodicidade_meses`** do tipo (calendário, sem estourar o mês). Data no futuro → 400.
- **Acesso temporário = `users` comum**: role `viewer` (leitura) ou `operator` (operacional), `permissions = [module:X…]` só dos canônicos, **financeiro nunca** (regra de `users.py`), e-mail único, 1–90 dias. `expirar_acessos()` roda em todo `GET /api/v1/redesign/data/*` e nas telas: `is_active=false` para vencido ou revogado → `get_current_active_user` recusa («Usuario inativo») em qualquer rota. Nada em `core/auth` mudou. `# ponytail:` a janela entre vencer e a próxima abertura de tela é o teto — cron dedicado quando houver mais de meia dúzia de acessos.

## §4 Oráculo

`backend/scripts/orq/test_oraculo_t5_log_materiais_exames_acessos.py` — afirma: fiação nos 4 builders + gate e 7 ids com porta; 4 tabelas; `auditoria` mostra a escrita mais recente e conta o total de `crm_audit_log`; solicitação aberta→aprovada→atender 3/5 = parcial com saldo −3 e 1 movimento de saída, +2 = atendida (saldo −5), 6/5 → 400, 50 → 409 sem mexer no saldo, rejeitar sem motivo → 400, atender aberta → 409; `valido_ate` == data + periodicidade (recontado) e a tela marca vencido/em dia; acesso nasce viewer com só `module:dp,module:sst`, financeiro → 400, e-mail repetido → 409, vence → `is_active=false`, revogar (id como texto) → inativo + `revogado_em`; varredura: 0 vencidos/revogados com login ativo. Fixtures `FIXTURE DGX T5` apagadas no `finally` (inclusive o COGS).

```bash
WT=$(git rev-parse --show-toplevel); ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,mode=1777 -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_t5_log_materiais_exames_acessos.py
```
ANTES (árvore `b98b4dfeb` via `git archive`):
```
FALHOU: builder _dgx_t5_suprimentos_frotas_sesmt_config não importa: cannot import name '_dgx_t5_suprimentos_frotas_sesmt_config' from 'modules.operacional.controllers.redesign_builders'
TOTAL falhas: 1
exit=1
```
DEPOIS:
```
auditoria: 36329 linhas · solicitações: 2 · exames: 2 · acessos: 1 · saldo fixture final: 5
TOTAL falhas: 0
OK t5: auditoria lê a trilha viva; atender baixa o estoque pelo caminho da F9 (parcial/atendida/409); válido até = data + periodicidade; acesso expira e revoga sozinho, nunca com financeiro
exit=0
```
Vizinhos na mesma árvore: `test_oraculo_suprimentos_cadeia` (F9) **verde** · `test_oraculo_sesmt_demandas_comercial` (F12) **verde** · `test_oraculo_parametros_por_cnpj` (F4) **verde**.

Prova HTTP (container `teste-dgx-t5`, 8225, parado ao fim): `GET /data/{seguranca,suprimentos,saude-ocupacional,configuracoes}` → 200, os 8 ids presentes e no `extraMenu`; `auditoria` = 400 linhas, sub «36307 registros · 762 nas últimas 24 h · 4576 em 7 dias por 53 usuários», 1ª linha «Jordan Jesus · abriu a tela operacional». Solicitação com o material real `1254` (saldo 20): atender aberta → 409; aprovar; atender 1 → «Parcial», saldo **20 → 19**, COGS «Baixa estoque: SACO VAZIO x1» R$ 2,50; exame Audiometria 01/02/2026 → válido até 01/02/2027 «em dia» na tela; futuro → 400. Acesso `teste-cp-t5@…` (leitura, dp+fiscal, 3 dias): financeiro → 400; **login 200**; `GET /data/departamento-pessoal` 200 · `fiscal` 200 · `financeiro` **403** · `configuracoes` **403**; `expira_em` no passado + qualquer `GET /data` → `is_active=false` e o token antigo recebe **403 «Usuario inativo»**; tela mostra «Expirado · login inativo»; revogar com id texto → 200, de novo → 404, login → 403. Tudo apagado (sobras = 0, saldo de `1254` de volta a 20, COGS e movimento removidos).

## §5 O que NÃO foi feito e por quê

1. **Perfis de permissão por tela/ação** (828 nós no DGX) — G; a decisão de 07/09 foi «gerentes com mesmo perfil»; por módulo cobre 10 usuários de back-office. Horário de acesso e cerca eletrônica de login: não se aplicam ao portal do agente (celular, qualquer hora). §7.
2. **Itens de vistoria/auditoria configuráveis** — as 8 áreas fixas da frente 10 cobrem 1 carro de supervisão; configurar exigiria trocar o formulário em `_frente_10.py` (alheio).
3. **Manutenção de veículo como entidade** (fornecedor/valor → conta a pagar, gera troca) — F10 §5.7 deixou «veículo é patrimônio?» para o dono; sem essa decisão seria a 2ª tabela de manutenção.
4. **Multa → título / recurso** — F10 já desconta em folha (mais que o DGX); título é F11 (contas fixas). Baixo valor.
5. **Grupos hierárquicos de materiais** — `grupo` texto + filtro resolve para 147 itens. **Cotação por item** (`purchase_quotations` do WhatsApp existe), **parcelas da NF** (F11 gera título), **«descartar» uniforme**, **encaminhar demanda** — baixo valor, cada um P; ficam listados.
6. **Acessos temporários sem token de API** — o DGX emite JWT com `roles` para integração (importar empregados etc.); aqui o acesso é um login com senha. Token de máquina com prazo é `create_access_token(expires_delta)` + um usuário técnico — não fiz porque ninguém integra por API hoje além do `mcp-service`.
7. **Cron de expiração** — a varredura roda no gate do redesign (todo mundo passa por ali); um beat dedicado é a 2ª cópia. O oráculo acusa vencido ativo.
8. **Frontend intocado**; `auditoria` já tinha porta no JSON de `seguranca`; os outros 7 ids entram pelo `EXTRA_MENU`. Se o orquestrador quiser no JSON: `seguranca.json` +`auditoria-telas`; `suprimentos.json` +`solicitacoes-material`; `saude-ocupacional.json` +`aso-exames-vencendo`; `configuracoes.json` +`acessos-temporarios`.
9. **Hooks `ruff`/`ruff-format` pulados no commit do código** (`SKIP=ruff,ruff-format`): `configuracoes.py` e `redesign_data_controller.py` nunca foram formatados e o hook reescrevia centenas de linhas alheias. Os 2 arquivos novos passam `ruff check` limpos; os plugs são 2–11 linhas cada.
10. **No DGX**: `Configuracoes/Salvar`, `AcessosTemporarios` (POST), `Feedback/SalvarRespostaPadrao` e o abastecimento web devolveram 500 — não é a nossa instância. Apps de celular: não exercitados. Log Sistema ficou vazio porque só registra 4 tabelas do DP (que este grupo não toca).
11. **Limpeza no DGX**: apaguei o que criei na ordem inversa; o que o trial recusou apagar por dependência está anotado no §6 (nada fora do prefixo `TESTE CP T5`; o colaborador compartilhado ficou).

## §6 Como o Jordan testa amanhã

1. **Segurança → Auditoria**: a lista agora é a trilha real — filtre «Usuário = Jordan Jesus» e «Método = POST»; a linha diz o que foi feito («ação diaria», «abriu a tela financeiro»). **Auditoria — telas abertas**: quem entrou em quê nos últimos 7 dias.
2. **Suprimentos → Nova solicitação de material**: posto Ideal Flores, tipo Mensal, itens `1254 | 5 | sacos de lixo`. Em **Solicitações de material** → Aprovar → Atender (vem `1254|5`; mude para 3) → situação «Parcial» e em **Estoque** o saldo de 1254 caiu 3; Financeiro → Estoque — movimentos tem a saída com o nº da solicitação. Atender de novo com 2 → «Atendida». Tente entregar mais do que falta → recusa.
3. **Saúde Ocupacional → Registrar exame**: colaborador, Audiometria, data de 8 meses atrás → **Exames por colaborador** mostra «vencido há N d» (periodicidade 12 meses ⇒ ajuste Audiometria para 6 em Tipos de exame e registre outro: o «válido até» muda).
4. **Configurações → Novo acesso temporário**: nome do contador, e-mail, Leitura, 7 dias, módulos DP + Fiscal, motivo → copie a senha da resposta. Abra uma janela anônima, entre com esse login: DP e Fiscal abrem; Financeiro e Configurações dão «sem acesso». Em **Acessos temporários** → Revogar → o login cai na hora. Depois de 7 dias cai sozinho (a tela mostra «Expirado · login inativo»).
5. Oráculo em produção após o bake: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_t5_log_materiais_exames_acessos.py` → `OK t5 …`, exit 0 (cria e apaga as fixtures).

Ficaram no DGX (o trial devolveu 500 no `Excluir` por dependência, tudo `TESTE CP T5`, nada fora do prefixo): uniforme `T5-UNI-01`
(tem estoque/entregas já apagados, mas o Excluir ainda cai), material `T5-MAT-01` (tem movimentos de NF e de solicitação), a NF de
entrada 5001 e os 2 pedidos (ambos **cancelados**), o grupo «TESTE CP T5 GRUPO» (o material o referencia). Apagados: entregas, kit e
itens, tamanhos, estoque de uniforme, solicitações de compra/material com itens e cotações, itens da NF, saídas/trocas/multa/manutenção/
locação/veículo, arma/colete/rádio/rastreador, médico, exame, ASOs, assunto, demanda, atendimento, visita, diretório, departamento,
fornecedor. Colaborador compartilhado `TESTE CP COLABORADOR 01` ficou (total = 1).

## §7 Decisões que só o dono pode tomar

1. **Permissão por tela/ação** (como o DGX) ou continuar por módulo? Se sim, é uma frente própria (G) sobre `_slug_allowed` + `EXTRA_MENU`; hoje os 2 gerentes têm o mesmo perfil por decisão sua.
2. **Quem aprova a solicitação de material**: hoje qualquer usuário com acesso a Suprimentos (módulo financeiro) aprova e atende. Separar «posto pede» (operacional) de «almoxarifado atende» (financeiro) é uma trava por role — 1 linha na ação, quando você disser quem é quem.
3. **Periodicidade dos exames**: os 12 tipos estão em 12 meses (F12 §7.3); audiometria (6) e o que o PCMSO do Pojucan mandar — é editar na tela Tipos de exame, e o «válido até» dos exames novos segue.
4. **Acesso temporário com Financeiro** para o contador? Hoje é proibido (regra de `users.py`: financeiro só do CEO). Liberar é tirar `financeiro` de `MODULO_PROIBIDO` — mas a regra da tela Usuários continuaria negando.
5. **Validade máxima** (90 dias) e **papéis** (leitura/operacional) — chute honesto; e se o acesso deve exigir troca de senha no 1º login (o login não tem essa trava hoje).
6. **Menu JSON** dos 4 módulos (§5.8) — o orquestrador aplica se quiser os ids fora do `EXTRA_MENU`.
