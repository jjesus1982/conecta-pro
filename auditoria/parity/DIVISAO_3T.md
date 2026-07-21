# DIVISÃO 3 TERMINAIS — Paridade Redesign (fonte da verdade)

> Documento OFICIAL de coordenação. Orquestrador = **T1**. Duas análises independentes
> (T1 e T3) convergiram na mesma arquitetura → desenho travado. Atualizado 2026-07-21.

## Objetivo da FASE 1
Ligar (wire) ao DADO REAL do clássico as **161 telas não-wired** do redesign, em 3 terminais
**sem conflito**. Cobertura atual: **128 wired / 258 no menu (≈37%)**. Ação legal/dinheiro
(transmitir eSocial, pagar, OTP) fica SEMPRE **GATED** — nunca disparada em teste.
Fase 2 (reconstrução das ~611 capacidades de escrita) vem depois, com outro placar.

## Identidades (TRAVADAS — não confundir) — atualizado 2026-07-21
| Terminal | Papel | tmux |
|---|---|---|
| **T1** | Orquestrador + fundação (feita) + seus módulos | (sessão que fez telas 1-24) |
| ~~T2~~ | **Realocado p/ outra missão crítica** — seus módulos foram p/ T4 | — |
| **T3** | Trabalhador — cluster pessoas | já com diagnóstico na mão |
| **T4** | Trabalhador — cluster financeiro/comercial (assumiu o do T2) | sessão nova |
| **T5** | Monitor (NÃO codifica) — observa T1/T3/T4 | sessão nova |

## Divisão por módulo (cada módulo pertence a EXATAMENTE um terminal)
| Terminal | Módulos (gap = telas não-wired) | ~telas |
|---|---|---|
| **T1** | operacional(28) · saude-ocupacional(3) · fiscal(6) · juridico(8) · integracoes(5) · campo(2) · documentos(2) · relatorios(1) · meu-espaco(0) · suprimentos(1) · homologacao(1) | **~57** |
| **T4** | financeiro(21) · gestao-de-pessoas(9) · crm(3) · empresas(4) · seguranca(5) · recrutamento(1) · servicos(2) · agendador(3) · assistente(2) · bi(0) · analytics(0) | **~50** |
| **T3** | departamento-pessoal(10) · rh(10) · marketing(7) · area-do-cliente(6) · portal-do-funcionario(5) · licitacoes(3) · configuracoes(6) · equipamentos(4) · automacoes(3) | **~54** |

Denominador = **telas wireable** (não P0 cru: P0 mede o buraco total, inclui escrita GATED que
ninguém faz em paralelo agora).

## As 4 REGRAS INVIOLÁVEIS (quebrou = conflito / perda de trabalho)
1. **Propriedade de arquivo.** Cada terminal edita SÓ `backend/modules/operacional/controllers/redesign_builders/<seu_módulo>.py`. NUNCA o registry (`redesign_data_controller.py`), NUNCA `_shared.py`, NUNCA módulo alheio.
2. **Commit antes de deploy.** O blue-green assa a árvore git inteira → commite seu arquivo antes de subir. Arquivos disjuntos → `git pull --rebase` nunca conflita → deploy de um carrega o commitado de todos (aditivo).
3. **Deploy serializa pelo lock** `/tmp/conecta_deploy.lock`. Use retry-loop se ocupado. 1 imagem por vez; builds ~2-3 min enfileiram.
4. **Checklist ao vivo.** Marque a tela que pegou aqui embaixo ANTES de começar (evita 2 pegarem a mesma).

## Padrão de cada tela (ver CORRECOES.md p/ exemplos)
1. Achar menu-id não-wired no `_modules/<slug>.json`.
2. No SEU `redesign_builders/<mod>.py`: `await safe("<id>", tbl(...))` lendo a MESMA tabela do clássico.
3. Coluna enum/json → `::text` / `->>'k'` no coalesce (senão `safe()` engole a tela e ela some).
4. Deploy blue-green → grep container → `curl /redesign/data/<slug>` prova dado real → commit atômico + linha no CORRECOES.md.
5. Ação de escrita legal (transmitir/pagar) = form GATED, NUNCA dispara.

## STATUS DA FUNDAÇÃO — ✅ PRONTA (2026-07-21, commit 941f8ab9)
- [x] T1: registry aditivo `_discover_module_builders()` (override + merge + router). Helpers ficaram no monólito (importados pelos módulos) — mais seguro que mover. Não usei `_shared.py`; os módulos importam de `redesign_data_controller`.
- [x] T1: **128 telas wired IDÊNTICAS** ao `BASELINE_PRE_REFACTOR.json` (0 divergência, 8080 healthy).
- [x] T1: deploy + commit `941f8ab9`.
- **✅ FUNDAÇÃO PRONTA — T2 e T3 podem começar.** Como escrever seu módulo: copie `redesign_builders/_TEMPLATE.py` → `<seu_modulo>.py`, defina `SLUG`, copie o corpo do `_build_<mod>` atual do monólito como ponto de partida e adicione telas.
- [x] T1: **caminho de override PROVADO end-to-end** (teste no container, sem deploy): arquivo de módulo real → sem import circular no boot, `BUILDERS[slug]` vira o override, `EXTRA_MENU` mescla, `build()` roda. O mecanismo está battle-tested; pode confiar.

## GOTCHA DE DEPLOY (aprendido no refactor)
- Deploy blue-green leva **~7 min** (build+green+recria primário). **NÃO use timeout < 600s** — cortar no meio deixa o nginx apontado pro green e pode servir código stale. Se cortar: `sed -i "0,/server 127.0.0.1:80../s//server 127.0.0.1:8080;/" /etc/nginx/sites-available/erp.conectamais.pro && nginx -t && systemctl reload nginx` volta pro primário; depois `docker rm -f conecta-pro-backend-green`.
- SEMPRE `grep container` + curl no domínio público pós-deploy (não só localhost:8080).

## CHECKLIST AO VIVO (marque `[x] <terminal> <tela>` quando fechar)
<!-- ex.: - [x] T1 fiscal/certidoes-cnd (curl 9 CNDs) commit abc123 -->
- [x] T1 juridico: 1º módulo via fundação — contratos·conhecimento·analise·processos-det (+visao/processos/det). escritorio=probe→honesto vazio. build() 7 telas provado no container.
- [x] T3 departamento-pessoal (10/10): admissao(admission_processes 3)·aviso-previo(employees, 0=honesto)·ponto(gp_clock_punches 300)·fechamento-ponto(gp_monthly_closings 50)·licencas(sst_afastamentos 8)·reembolsos(reimbursement_requests 20)·contratos(employment_contracts 43)·documentos(hr_employee_documents 32)·certificacao(hr_certifications 51)·esocial(esocial_eventos_espelho 36). build() estende _build_dp. Deploy blue-green OK + HTTP 200 autenticado provado. commit na branch.
- [x] T1 documentos: kits(58 ged_document_kits) + pastas(8 ged_folders). campo pulado (monitoramento/comunicados sem tabela → honesto vazio).
- [x] T4 financeiro (21/21): fluxo-caixa·conciliacao·boletos·cobrancas·banking·inter·compras·estoque·faturamento·fiscal·nfse-entrada·orcamentos·precificacao·custos·contabilidade·contratos·raio-x·cfo·agentes·relatorios·custeio. `redesign_builders/financeiro.py` estende `_build_financeiro`. HTTP 200 8080+público, rows reais. commit c74072a8. Dinheiro que SAI = gated.
- [x] T4 gestao-de-pessoas (9/9): ged-kits(58)·ged-envios(49)·ged-assinaturas(200)·ponto-banco(0 honesto)·rh(66)·rh-treinamentos(0 honesto)·rh-cargos(51)·saude(96)·consultor(4). commit c74072a8.
- [x] T4 crm (3/3): clientes(20)·growth(6)·consultor(69). commit c74072a8.
- [x] T4 empresas (4/4): demonstrativos(7)·rentabilidade(20)·liminares(3)·migrador(4, só visibilidade). commit c74072a8.
- [x] T4 seguranca/LGPD (5/5): consentimento(5)·esquecimento(1)·mascaramento/criptografia/pia-dpia(0 honesto). só visibilidade. commit c74072a8.
- [x] T4 recrutamento (1/1): candidaturas(10). commit c74072a8.
- [x] T4 servicos (2/2): contratos(12)·agendamentos(0 honesto). commit c74072a8.
- [x] T4 agendador (3/3 NOVO): visao(dash)·tarefas(0)·execucoes(0). commit c74072a8.
- [x] T4 assistente (2/2 NOVO): chat(3)·historico(1). commit c74072a8.
- ⚠️ T4: 50 telas VIVAS no primário via cp (volátil). BAKE pendente — árvore suja com WIP não-commitado de people_management (outro terminal); blue-green assa a árvore inteira. Próximo deploy com árvore limpa torna durável (arquivos já commitados).
