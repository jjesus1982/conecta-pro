# DISTRIBUIÇÃO FASE 2 — trazer TODO dado real do Clássico → Redesign (T1 · T2 · T4)

> Fonte da verdade. T3 fora (missão grande). Missão: **fidelidade total de dados** — cada tela
> do redesign mostra o dado REAL que o clássico mostra. 3 terminais em LOOP, atribuições RÍGIDAS,
> deploy SERIALIZADO. Fundações prontas (gate / kit de ação / oráculo) — ver [[FASE2_PLANO]].

## 1. DIVISÃO RÍGIDA POR MÓDULO (cada módulo = EXATAMENTE 1 dono. NÃO invadir o alheio)

### T1 (eu) — operacional + fiscal/legal (11)
`operacional` · `saude-ocupacional` · `fiscal` · `juridico` · `integracoes` · `campo` ·
`documentos` · `homologacao` · `suprimentos` · `relatorios` · `meu-espaco`

### T2 — pessoas / RH / DP / gestão (10)
`departamento-pessoal` · `rh` · `gestao-de-pessoas` · `marketing` · `area-do-cliente` ·
`portal-do-funcionario` · `licitacoes` · `configuracoes` · `equipamentos` · `automacoes`

### T4 — financeiro / comercial (10)
`financeiro` · `crm` · `empresas` · `seguranca` · `recrutamento` · `servicos` · `agendador` ·
`assistente` · `bi` · `analytics`

**Arquivo por módulo:** cada terminal edita SÓ `backend/modules/operacional/controllers/redesign_builders/<seu_modulo>.py`.
Nome do arquivo SEM hífen (ex.: `departamento_pessoal.py`), slug com hífen em `SLUG`.

## 2. PROTOCOLO DE DEPLOY — SERIALIZADO (regra do Jordan, INEGOCIÁVEL)
**Um terminal SEMPRE checa se outro está deployando e ESPERA.** Nunca 2 deploys ao mesmo tempo.

```bash
# ANTES de deployar — esperar o lock liberar (poll 15s), sem forçar:
while ls /tmp/conecta_deploy.lock >/dev/null 2>&1; do
  echo "[deploy] lock ocupado ($(cat /tmp/conecta_deploy.lock/owner 2>/dev/null)) — esperando..."; sleep 15
done
# só então:
git add <seus arquivos> && git commit --no-verify -m "..."   # COMMIT ANTES (blue-green assa a árvore)
timeout 600 ./scripts/deploy_backend_bluegreen.sh              # timeout >=600 — NUNCA cortar no meio
```
- **NUNCA** rodar deploy com lock ocupado. **NUNCA** timeout < 600s (cortar deixa produção no green stale).
- Lock stale (sem processo + backend saudável + antigo): **NÃO limpe sozinho** — sinalize ao Jordan/T1.
- Pós-deploy: `grep` no container + **oráculo/curl no DOMÍNIO PÚBLICO** (não só localhost). Se pegar race (deploy concorrente), **re-curl** antes de concluir.
- Deploy de FRONTEND (se precisar) serializa igual + purga `.next/static` (drift de chunk).

## 3. O LOOP DE CADA TERMINAL — ACUMULAR 2-3 TELAS POR DEPLOY (regra do Jordan)
**NÃO deploye 1 tela por vez** — com 3 terminais isso sufoca o lock. Acumule **2-3 telas
(cada uma commitada + provada local) e faça UM deploy** pro lote. Reduz a frequência ~3×.

Por tela:
1. **ORÁCULO** — `python3 auditoria/parity/oraculo_fidelidade.py <classic_path> <redesign_path> <label> <out>`
   → SÓ no clássico (fidelidade pede trazer) / SÓ no redesign (divergência).
2. **CORRIGIR** no seu `redesign_builders/<mod>.py` (delegar+estender): dado real da MESMA
   tabela/serviço do clássico. Enum/json → `::text` / `->>'k'`.
3. **PROVAR local** — container test do `build()` (docker cp + rodar), SQL no banco.
4. **COMMIT** (atômico, por tela — commit sempre, deploy não).
5. Voltar ao passo 1 pra próxima tela. **Ao juntar 2-3 telas commitadas:**
6. **ESPERAR LOCK + DEPLOY** o lote (protocolo §2) → **VERIFICAR** as 2-3 (oráculo + browser)
   → **push** → **marcar** no checklist (§5). Recomeça o loop.

## 4. REGRAS DE SEGURANÇA (inegociáveis)
- **Informação = clássico** (dado real, ancorado no banco). **Nunca fabricar.** Sem dado real = "aguardando dado" honesto.
- **Escrita/botão** (Emitir/Sincronizar/Pagar/Transmitir) → passa pelo **GATE** (`redesign_write_gate.py`): money/gov exige OTP; teste só em **homologação**; nunca auto-fire; nunca "verde" sem retorno real.
- **NUNCA editar** arquivo alheio, o registry (`redesign_data_controller.py`), `redesign_write_gate.py`, ou `ModuleView.tsx` (fundações — se precisar de frontend novo, sinalize ao T1). Só o SEU módulo.
- Operacional (postos/alocações/escala) = READ-ONLY p/ agente; nunca escreve.
- **Push por iteração** (não acumular commits). `--no-verify`, `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## 5. CHECKLIST AO VIVO (marque `[x] <T> <modulo>/<tela>` ao fechar)
<!-- ex.: - [x] T1 fiscal/certidoes — trouxe abas de filtro + rótulo "Vencendo" (oráculo fecha) commit abc -->
- [x] T1 juridico/riscos — trouxe Exposição trabalhista (53 colab, R$242k) reusando riscos_service; oráculo fecha (números batem clássico).
- [x] T4 financeiro/pagamentos-pj — trouxe a tela que faltava (clássico tinha, redesign não): lista financial_pagamentos_pj (9 reais: competência/beneficiário/empresa/valor/NF/status) via EXTRA_MENU. Money-out (pagar) fica no fluxo gated OTP do clássico. Oráculo de menu fecha; curl público 9 rows. commit b9ff4184
- [x] T2 departamento-pessoal/funcionarios — trouxe completude do cadastro eSocial (% + campos faltantes, mesma fórmula 15 campos S-2200); override no builder, dado real. Provado no público (ADAILSON 60%, ADEILSON 47%, ANGELA 40% batem com o clássico). commit f8ac6328, blue-green OK.
- [~] T1 juridico/riscos — trabalhista (53 colab) FIEL (oráculo fecha as linhas). FALTA seção Tributário (riscos_tributario: Simples×Lucro Real + retenções + 3 riscos) + agregação por tipo de verba → próximo passo (dash multi-painel).
- FERRAMENTA: oráculo agora normaliza texto (ignora pontuação/acento) → só flaga gap REAL, sem ruído. Vale p/ T2/T4.
- [x] T4 financeiro/dashboard — fidelidade: painel ADITIVO "Faturamento NFS-e (12m)" (Bruto 1.615.707,19 · Líquido 1.451.894,06 · ISS 76.805,71 · Ticket 19.234,61) que o clássico exibe e o redesign não tinha. Mantém os KPIs de caixa. curl público confirma. commit 79359a58
- [x] T2 departamento-pessoal/folha — trouxe breakdown INSS/FGTS 8%/Descontos/Líquido por colaborador (hr_payslips), override no builder; redesign só tinha base+líquido. Provado no público (ADAILSON INSS 79,82/FGTS 208,71 batem com o clássico). commit (folha), blue-green OK.
- [x] T4 bi — fidelidade: NOVO bi.py com "Receita × Despesa (6m)" (bank_transactions, 6 meses reais) + "DRE do mês" (pivot, 'Outros custos' fecha com resultado). Clássico /financial/bi/overview mostrava; redesign só tinha 4 KPIs. curl público confirma. commit 72a23117
- [x] T2 departamento-pessoal/ferias — status traduzido p/ PT (Aprovado/Pendente/Cancelado, derivado igual clássico) + coluna "Solicitado em" (data convertida p/ Manaus). Provado no público (ADAILSON 01/06 Aprovado 13:19 bate com o clássico). blue-green OK.
- [x] T4 crm/leads — oráculo pegou: clássico mostra Origem (source) por lead; base do redesign não. Override + coluna Origem (whatsapp/website/…). curl público confirma. Nota: crm/dashboard clássico=404 (redesign tem a mais, sem gap). commit 975b1ad5
- [x] T2 departamento-pessoal/beneficios — trouxe operadora + valores (empresa/desconto) + vigência (employee_benefits), status active→Ativo; redesign só tinha tipo/plano/status. Provado no público (ADAILSON Plano Odont. CCT 2026 R$9/R$9). blue-green OK.
- [x] T2 rh/treinamentos — trouxe local/instrutor/vagas (0/20) + status traduzido (Agendado/Concluído); trainings. Provado (Uso EPI · Sala Conecta Mais · Amanda Reis · 0/20). blue-green OK.
- [x] T4 crm/oportunidades + crm/propostas — oráculo: clássico mostra KPIs de resumo (opp: Total/Em Negociação/Propostas/Pipeline; prop: Total/Rascunho/Enviadas/Aprovadas). Trazidos no subtítulo (tela table não tem KPI-card; não toco ModuleView). curl público confirma. commit 11ecc1be
- [x] T2 rh/candidaturas — trouxe coluna Candidato (LEFT JOIN candidates); redesign só tinha etapa/status. Provado no público (MARCOS OLIVEIRA SILVA · triagem). blue-green OK.
- [x] T2 departamento-pessoal/rescisao — base lia employees demitido (fonte errada, sem valores); sobrescrito p/ termination_processes (mesma fonte do clássico /terminations): Tipo/Status/Valor Total, labels espelham tipoConfig/statusConfig. Provado no público (JÚLIO CÉSAR · Involuntária · Concluída · 02/03 · R$ 0,00). blue-green OK.
- [x] T4 crm/contatos — oráculo: clássico mostra Email + "Contato principal"; base só tinha Contato/Cliente/Cargo/Telefone. Override + Email + badge Principal (crm_contacts). curl público confirma. crm/atividades=0 gaps (fiel). commit 06b242b5
- [~] T4 empresas/rentabilidade — clássico mostra margem por contrato SEM tabela de custo real (financial_contract_costs=0; /bi/profitability é agregado). Régua "nunca fabricar" → redesign mantém rentabilidade por cliente com dado real. Não é gap fechável sem fonte de custo. seguranca/auditoria e recrutamento/candidatos = sem gap (vazio real / fora do menu).
- [x] T4 varredura oráculo (fidelidade confirmada, sem gap acionável): crm/atividades=0 gaps; seguranca/auditoria+consentimento=vazio real (redesign até mais rico c/ candidate_consents); recrutamento/vagas+candidatos+entrevistas+servicos/ordens=fora do menu; empresas/demonstrativos=só cabeçalhos. Cluster T4 com gaps claros fechados (6 fixes) — restante fiel ou divergência de estrutura que precisa de frontend (sinalizado ao T1).
- [x] T2 departamento-pessoal/admissao — coluna CPF (formatada) + status traduzido p/ PT (Documentos Pendentes/Cancelada/…, espelha statusConfig do clássico); _badge_status deixava o enum cru. Provado público (AUDIT_Fulano 111.444.777-35 · Cancelada). blue-green OK.
- [x] T2 rh/onboarding — status traduzido p/ PT (mesma fonte admission_processes). Provado público (Cancelada/Documentos Pendentes). Nota: fonte progresso/etapas (/onboarding/dashboard) do clássico é passo mais profundo p/ depois. blue-green OK.
- [x] T4 financeiro/contratos — oráculo: clássico mostra Cliente (nome/CNPJ) + Retenções (ISS/INSS/CSLL ou Nenhuma) por contrato; base só tinha Nº/Contrato/Mensal/Status/Início. Override + Cliente + Retenções. curl público confirma. contas-pagar/faturamento: só formatação/resumo (sem coluna faltando). commit c379d681
- [x] T2 departamento-pessoal/contratos — Tipo traduzido p/ PT (clt_indeterminate→CLT Indeterminado, espelha contractTypeLabels); antes enum cru. Provado público. blue-green OK.
- [x] T2 departamento-pessoal/documentos — status normalizado (ativo/active→Ativo, espelha statusConfig draft/valid/expired/…); _badge_status deixava 'active' cru. Provado público. blue-green OK.
- [x] T4 financeiro/clientes + financeiro/fornecedores — oráculo: clássico mostra CNPJ; base não. Override + coluna CNPJ formatada (clients.document_number / suppliers.cpf_cnpj). curl público confirma. contas-receber: descrição detalhada mas colunas batem. commit e6188e38
- [x] T1 operacional/presenca — QUADRO por posto/condomínio (composite: tabela+resumo) reusando quadro_presenca_hoje; números batem o clássico (Ideal Flores 7/0/2/5 etc). Substituiu o log de batidas. build 0.18s.
- [x] T2 rh/cursos — Categoria traduzida p/ PT (behavioral→Comportamental, espelha categoryLabels do clássico). Provado público. blue-green OK.
- [x] T2 departamento-pessoal/reembolsos — status traduzido (rascunho→Rascunho, espelha statusConfig PT+sinônimos EN); antes minúsculo cru. Provado público. blue-green OK.
- NOTA T2 (fontes divergentes p/ passo dedicado): rh/onboarding (progresso/etapas via /onboarding/dashboard), dp/licencas (sst_afastamentos vs /leaves), rh/turnover (lê log de atividade, não métricas). rh/carreira status 'active' já é fiel (clássico também cai no fallback cru).
- [x] T4 financeiro/nfse-entrada — oráculo: clássico mostra CNPJ do prestador + Empresa (Eletrônica/Patrimonial); redesign não. Override + CNPJ + Empresa (join empresas). curl público confirma. compras (req.=0, redesign mais rico) e estoque (fonte EPI diferente) = sem gap fechável. commit 7317c677
- [x] T1 saude/exames — painel Regularização PCMSO (composite) com lógica EXATA do clássico (último ASO por ativo): ASOs válidos 8 · com ASO vencido 25 (bate o clássico!) · pendentes 45. Antes eu contava 44/88 (errado); achei _get_pcmso_stats do sst_service.
- [x] T2 departamento-pessoal/esocial — coluna Colaborador (nome via join cpf_trabalhador→employees.cpf por dígitos) + CPF formatado; clássico mostra nome, redesign só CPF cru. Espelho não tem status (não fabricado). Provado público (CINTIA BEZERRA · 029.804.042-50). blue-green OK.
- [x] T2 departamento-pessoal/certificacao — status capitalizado (pendente→Pendente, espelha statusBadge). Provado público. blue-green OK.
- [x] T4 empresas/liminares — oráculo: clássico destaca a Descrição/base legal (Não retenção INSS, Não cobrança PIS/COFINS); redesign só tinha Tipo. Override + coluna Descrição. curl público confirma. financeiro/fiscal (redesign mais rico) e custos (categoria já no bi/DRE) = sem gap fechável. commit 0dd2c169
- [x] T1 saude/afastamentos — painel Indicadores (composite) reusando SSTService.get_dashboard: afastados 4 · taxa 7,5% · ajuda-medicamento 3 · custo/mês R$900. Números batem o clássico.
- [x] T4 crm/comissoes — oráculo: clássico mostra KPIs (Total/Valor Total/Pendentes); trazidos no subtítulo (commissions). financeiro/inter+boletos = só cabeçalho/detalhe (sem coluna faltando). curl público confirma. commit 1aef6b0e
- [x] T2 gestao-de-pessoas/ged-kits — status legível (em_montagem→Em montagem/Enviado/Completo); capitalize() deixava underscore. Provado público. blue-green OK.
- [x] T2 departamento-pessoal/licencas — status PT (Ativo/Em Andamento/Encerrado/Cancelado, espelha statusConfig+synonyms EN); fonte = mesma base (clássico /leaves mapeia os mesmos afastamentos). Provado público (CINTIA · Em Andamento). blue-green OK.
- NOTA T2: rh/avaliacoes lê operacional_avaliacoes_equipe (tabela OPERACIONAL, read-only/curada Jordan) vs fonte RH do clássico (colunas Tipo/Status) — divergência de fonte, não mexer sem decisão.
- [x] T4 seguranca/esquecimento — resumo (Total/Pendentes/Concluídas) no subtítulo. commit c4323cd1
- [x] T4 empresas/obrigacoes — oráculo: clássico tem calendário multi-empresa (Eletrônica/Patrimonial + tipo + descrição + vencimento + status). REUSEI o mesmo agente ObligationsMonitorAgent.gerar_calendario_grupo (computação pura 0ms, A5) → 12 obrigações, 10 atrasadas. commit (empresas.py acima)
- [x] T1 operacional/colaboradores — enriquecido p/ bater o clássico: +Email/Matrícula/Departamento/Admissão (7 cols, 83 colab) + painel Total/Ativos/Afastados. GOTCHA: faltava importar _scalar no operacional.py → bloco falhava mudo (except). LIÇÃO: módulo deve importar TODOS os helpers que usa.
- [x] T2 departamento-pessoal/fechamento-ponto — trocada fonte gp_monthly_closings → time_sheets (fonte real do painel_fechamento do clássico); status derivado (Homologado/Aguardando assinatura/Fechado/N anomalia(s)/Calculado) via sig_signature_requests, horas HH:MM, última competência, exclui homologação. Anomalias batem 1:1 com o painel (ADAILSON Calculado, ANTONIO 30, EDIWILSON 11, ERIKA 22). blue-green OK.
- [x] T2 rh/onboarding — trocada fonte admission_processes → employees admitidos há ≤90d ativos (fonte do /onboarding/dashboard do clássico); progresso/etapas não são populados pelo endpoint → não fabricado, mostra Dias na empresa real. blue-green OK.
- [x] T4 financeiro/orcamentos — oráculo: clássico mostra tabela mensal orçado/realizado (projeção); redesign mostrava financial_orcamentos cru (1 chave). Refiz como Orçado(MRR real)×Realizado(receita real do extrato)×Diferença×% mensal — estrutura fiel, dado real, sem replicar crescimento fabricado. cobrancas/candidaturas=sem gap. commit 58b66e8c
- [x] T1 saude/cat — painel Indicadores de acidentes (Total CATs 3 · Colaboradores 53 · Taxa 5,66%), mesma fórmula do clássico (calcular_taxa_acidente).
- [x] T2 departamento-pessoal/ponto — troca 1-linha-por-batida → registro DIÁRIO (Colaborador/Data/Entrada/Saída/Total), batidas de gp_clock_punches pareadas por (colaborador,dia) via min/max, como o clássico /hr/time-records; punch_timestamp Manaus-local; exclui homologação. Provado público. blue-green OK.
- [x] T2 rh/avaliacoes — troca operacional_avaliacoes_equipe → performance_reviews (fonte RH do clássico); Colaborador/Avaliador/Tipo/Score/Status, labels espelhados (annual→Anual, completed→Concluída). Reviewer/employee resolvidos em employees (15/15). Provado público (ADAILSON · ANTONIO WALCICLEY · Anual · 6.3 · Concluída). blue-green OK.
- [x] T4 crm/clientes — oráculo: clássico mostra CNPJ+email+KPIs (Total/Ativos/Condomínios/Bloqueados); override + CNPJ + Email + resumo. banking=só "Posição da Conta" (sem gap). assistente/analytics=sem página no clássico (sem gap); agendador=scheduler vazio (honesto). commit b2b4a8bb
- [x] T1 relatorios/central — hub de cards (Operacional/Financeiro/Comercial/Dashboards Exec.) que o clássico mostra e o redesign tinha vazio. Fecha o último gap dos módulos do T1.
- [x] T4 precificacao (financeiro+crm) — oráculo: clássico mostra custo/preço/margem por função; redesign só tinha config CCT. REUSEI calcular_funcao (pricing_cct, mesmo do clássico) → Função/Piso/Custo/Preço/Margem batendo exato (AGP P1 Diurno 41,34%). cold-start único ~3s (import), warm 0,08s. commit dd41019f
