# A noite de 23→24/09/2026 — o DGX dentro do Conecta PRO

**Pedido do Jordan, 23/09 à noite:** *"cria um plano geral para implementar tudo o que ele já tem e
funciona no conecta pro, todos os módulos, multi agentes, em várias frentes, loop autônomo, vou
dormir agora, amanhã de manhã eu vejo, você tem total autonomia."*

**Este documento é o que você lê primeiro.** Ordem: uma linha, o que mudou de arquitetura, o que
testar (10 minutos), o que só você decide, e depois o detalhe por frente.

Plano vivo: `docs/dgx/PLANO_IMPLEMENTACAO.md`. Contrato dos agentes: `docs/dgx/CONTRATO_AGENTE.md`.
Relatórios por frente: `auditoria/frentes/DGX_F1..F12_*.md` (cada um com §6 «como testar» e §7
«decisões do dono»).

---

## 1. Em uma linha

**12 frentes planejadas, 12 mescladas e no ar** (F1–F7, F10, F11 no bake 16 às 00:35; F8, F9, F12 no
bake seguinte, 01:05 — os dois sem drift). **16 oráculos novos rodados no container de produção,
todos verdes.** Tudo foi provado num container efêmero contra uma cópia de produção antes de subir, e a
árvore mesclada foi provada de novo antes do bake (35 módulos do redesign abertos, 0 falhas).

Três bugs achados de passagem e corrigidos: o webhook da Cora nunca conseguia marcar transação
como efetivada/cancelada; a ativação de candidato em 12x36 estourava em mês de 31 dias; o
validador de CPF da consulta à Receita reprovava CPF válido.

## 2. O que mudou de arquitetura (é isto que o DGX tinha e nós não)

| Antes | Agora |
|---|---|
| Rubrica = 8 colunas; a regra vive em `calculo_service.py` | **`rubricas_folha` com os atributos do DGX** (período, tipo de dia, crédito, soma ao evento, banco de horas, desconta benefício, exporta, DSR, 13º, razão, base…), 35 rubricas com `origem_regra`, Editar/Inativar na tela. Oráculo: bases INSS/FGTS/IRRF recompostas pelas flags = holerite, Σ\|Δ\| R$ 0,00 em 51 holerites |
| CCT = constantes Python | **Sindicato → 51 funções → 459 eventos → 408 benefícios → municípios**, como dado, no menu «Sindicato & CCT» do DP. Conformidade CCT aponta função sem evento e ativo sem função |
| VT/VR = conta manual | **`beneficio_tipos` carrega a regra** (7 tipos de desconto, limite de faltas, remover férias/afastados, integração com ponto). O motor de benefício da frente 03 LÊ a tabela — paralelo cego, 208 linhas iguais ao motor anterior |
| Parâmetro = constante no código | **`system_configs` por CNPJ** (40 chaves em 8 grupos, valor global + Eletrônica + Patrimonial), tela Configurações → Parâmetros com histórico. Adiantamento 40% e tolerância de ponto já lidos do banco |
| Alocação sem motivo | **Movimentação com tipo, motivo (7 do DGX), origem, coberto, solicitante**; alocar por cima encerra a anterior em D−1 |
| Tolerância/raio de ponto chumbados | **Cascata colaborador > escala > função > posto > condomínio > empresa**; feriado com escopo (nacional/estadual/municipal/**cliente**) lido por uma função só no espelho e na precificação |

Mais: dependentes na fonte que a folha lê, vales, eventos coletivos, crachás em lote (PDF),
demissão em lote (rascunhos), relógios/aparelhos, cartão de ponto em lote (48 espelhos num PDF),
dashboard de ausências, frota completa (saída/retorno, multas com condutor sugerido, trocas,
locações, requisições), condições de pagamento gerando parcelas, contas fixas gerando título,
códigos de serviço/CFOP, recibos numerados, fechamento de comissões, orçado × realizado,
pensionistas.

## 3. O que testar amanhã (10 minutos)

| Tela | Onde | O que você deve ver |
|---|---|---|
| **Sindicato & CCT** | `/redesign/departamento-pessoal?t=g-cct` | 51 funções, botão Eventos/Benefícios por função; Conformidade CCT com «5 ativos sem função da CCT» |
| **Rubricas** | `…departamento-pessoal?t=folha-rubricas` | 35 rubricas, coluna «Uso 09/2026», Editar/Inativar; 4 linhas amarelas = colisão de código (§4.2) |
| **Tipos de benefício** | `…departamento-pessoal?t=beneficio-tipos` | VT «% sobre salário · 4% · rubrica 1010»; mude o limite de faltas do VR para 0 e recalcule: linhas «cortado faltas» sem mexer na folha |
| **Parâmetros do sistema** | `/redesign/configuracoes?t=parametros` | 40 parâmetros, `folha.adiantamento_percentual` = 40; Editar por empresa |
| **Movimentações** | `/redesign/operacional?t=movimentacoes` | 73 linhas com motivo «Alocação de vaga» (retroativas); Nova movimentação encerra a anterior |
| **Configurações de ponto / Feriados** | `…departamento-pessoal?t=ponto-configuracoes` · `?t=feriados` | «Empresa · 15/15/150»; 16 feriados com escopo |
| **Cartão de ponto em lote** | `…departamento-pessoal?t=cartao-ponto-lote` | 08/2026 → PDF com 48 espelhos |
| **Dependentes / Vales / Crachás** | `…departamento-pessoal?t=dependentes` · `?t=vales` · `?t=crachas-lote` | dependentes contando salário-família; vale entra na prévia da folha; crachás 8 por folha (sem foto — ninguém tem) |
| **Frota** | `/redesign/equipamentos?t=frota-saidas` | saída única por veículo, retorno com KM, multa sugere o condutor |
| **Coberturas / Livro do posto / Checklist / Chamados** | `/redesign/operacional?t=coberturas` · `?t=livro-ocorrencias` · `?t=checklist-executar` · `?t=chamados` | cobertura em folga detectada nos turnos; livro do dia em PDF timbrado; checklist com item reprovado gera ocorrência; chamado urgente com SLA 1h em vermelho |
| **Suprimentos** | `/redesign/suprimentos?t=estoque` · `?t=nf-entrada` | 147 materiais com os 6 status; 84 NF-e da SEFAZ com «Conferir recebimento» |
| **Exames por função / Atendimentos / Fontes pagadoras** | `/redesign/saude-ocupacional?t=exames-por-funcao` · `/redesign/crm?t=atendimentos` · `?t=fontes-pagadoras` | 57 de 63 ativos sem ASO válido, por função; 9 atendimentos (4 ouvidoria + 5 portal) com SLA; quem paga ≠ quem contrata |
| **Condições / Contas fixas / Recibos** | `/redesign/financeiro?t=condicoes-pagamento` · `?t=contas-fixas` · `?t=recibos` | 30/60 gera 2 parcelas; gerar mês duas vezes cria uma só; recibo 00001 em PDF |

## 4. O que só você decide — os números estão nos §7 de cada relatório

**Dinheiro/folha (F1, F2, F3):**
1. **Faltas não reduzem a base do INSS no motor** (09/2026: R$ 4.593,86 em 19 pessoas → INSS e
   FGTS a maior, FGTS R$ 367,51). Corrigir é mexer no motor; o cadastro hoje diz a verdade do motor.
2. **Colisão de códigos de rubrica** (chave do eSocial): 0040, 0050/0051, 0060/0061, 0070 e o 1002
   usado para IRRF e INSS Férias. Renumerar no motor ou renomear na tabela — qualquer um mexe no
   caminho do dinheiro.
3. **Insalubridade 10% paga a 11 pessoas** (Serviços Gerais, Artífice, Jardineiro) e **ronda 15% a
   15 agentes de portaria** sem cargo insalubre/ronda na CCT — laudo por posto? Marcar obrigatório
   na função? Parar? Lista nominal em `DGX_F2 §7`.
4. **5 ativos sem função da CCT** (ALAN, ALEXANDRE, KELLY, NAILSON, THIAGO): preencher o cargo.
5. **SINETRAM: 27 × R$ 10 ou 30 × R$ 9?** A linha carrega R$ 10/dia «confirmar com a Pyetra».
6. **Quando a tabela vira fonte da folha** (rubricas, CCT, benefício): sugestão — 2 competências
   com oráculo verde.

**Ponto/operação (F5, F7):**
7. **Unificar `allocations` (89) com `employee_alocacoes` (73)** — duas verdades; a `posto_id` é a ponte.
8. **3 pessoas com alocação ativa que não deviam** (1 demitido, 1 afastado INSS, 1 suspenso).
9. **Ligar os 5 campos guardados de ponto** (fora do raio, facial obrigatória, arredondamento,
   intervalo mínimo, tolerância de saída) aos motores — cada um pede paralelo cego.

**Cadastro (F4, F6, F10, F11):**
10. **16 parâmetros sem valor** (nenhum código lê ainda) — preencher ou deixar.
11. **33 dependentes do backfill Portte sem nome/data** pagam salário-família «sem prova».
12. **Foto de funcionário**: 0 de 63 têm — sem upload, crachá sai com moldura vazia.
13. **CNH dos supervisores**: 0 cadastradas — sem isso a lista de motoristas é todo mundo.
14. **Multa em folha**: parcela única ou parcelada (art. 462 CLT — confirmar com o contador).
15. **As 15 comissões «auto — proposta»** (R$ 5.110,62) são reais ou lixo de teste?
16. **`ItemListaServico` 17.19 fixo no emissor de Manaus vs 11.02 nas notas gravadas** — qual?

**Operação, suprimentos, SESMT (F8, F9, F12):**
17. **Folga trabalhada vira HE ou folga compensatória?** O resumo por pessoa/mês já existe; a folha não lê.
18. **21 colaboradores com 2 logins** em `users` — o «não lidos» do app é por usuário; qual vale?
19. **32 NF-e só em resumo** (R$ 13,4 mil): manifestar ciência para baixar o XML e entrar no estoque?
20. **Mínimo/máximo dos 147 materiais**: todos «Mínimo não informado» — quem preenche.
21. **Unificar fornecedores** (`suppliers` 60 × `financial_fornecedores` 12) e **aposentar `fin_stock_*`/`inventory_items`** (semente sem escritor).
22. **Apagar a família morta `health_asos`/`health_medical_exams`** (só `gp_asos` vive) — rito de apagar pacote.
23. **Códigos Tab. 27 em branco** (espirometria, RX, ECG, EEG) — confirmar com a MBS antes do S-2220.
24. **NFS-e apontar para a fonte pagadora** (tomador = administradora): muda XML e retenção — não feito.
25. **As 4 manifestações de ouvidoria de 07/2026** são texto de teste, abertas há 2 meses — responder ou expurgar?

## 5. O que o sistema passou a vigiar sozinho (13 oráculos novos + 1 caçador)

`rubricas_dizem_a_verdade` · `cct_como_dado` · `beneficio_regra_e_dado` · `parametros_por_cnpj` ·
`movimentacao_com_motivo` · `dp_complementos` · `ponto_configuravel` · `frota_operacional` ·
`financeiro_cadastros` · `operacional_dgx` · `suprimentos_cadeia` · `sesmt_demandas_comercial` · `validar_cpf` (+ os das frentes de 13/09 que continuam verdes: grid × triagem,
mapa 5 estados, benefício fecha, vistoria par). Caçador novo **`checar_parametro_ambiguo`** (trava 76):
o padrão `SET x = :p … CASE WHEN :p` que derrubou o lote Inter e o webhook da Cora não volta calado.
Todos entram na varredura da meia-noite por descoberta automática.

## 6. Estado final das frentes

| # | Frente | Estado | Relatório |
|---|---|---|---|
| F1 | Rubricas como dado | ✅ no ar (bake 16) | `DGX_F1_eventos_rubricas.md` |
| F2 | CCT como dado | ✅ no ar | `DGX_F2_cct_como_dado.md` |
| F3 | Tipos de benefício com regra | ✅ no ar | `DGX_F3_tipos_beneficio.md` |
| F4 | Parâmetros por CNPJ | ✅ no ar | `DGX_F4_parametros_cnpj.md` |
| F5 | Movimentações | ✅ no ar | `DGX_F5_movimentacoes.md` |
| F6 | DP complementos | ✅ no ar | `DGX_F6_dp_complementos.md` |
| F7 | Ponto configurável | ✅ no ar | `DGX_F7_ponto.md` |
| F8 | Operacional (coberturas, livro, checklist, chamados, avisos) | ✅ no ar | `DGX_F8_operacional.md` |
| F9 | Suprimentos (compras, estoque, fornecedores, rádios/rastreadores) | ✅ no ar | `DGX_F9_suprimentos.md` |
| F10 | Frotas | ✅ no ar | `DGX_F10_frotas.md` |
| F11 | Financeiro/Faturamento | ✅ no ar | `DGX_F11_financeiro.md` |
| F12 | SESMT + Demandas + Comercial | ✅ no ar | `DGX_F12_sesmt_demandas_comercial.md` |


## 7. O que NÃO foi feito, de propósito

- **Nenhum valor de folha mudou.** Tudo que toca dinheiro é paralelo cego: cadastro descreve, motor
  continua o mesmo, oráculo prova a igualdade. Ligar o motor ao cadastro é decisão sua (item 6).
- **Nenhum dado de produção foi corrigido** (cadastro sem CCT, alocações indevidas, dependentes sem
  nome, comissões suspeitas): aparecem nas telas; quem decide é gente.
- **Nada de Telegram.** Nenhum `alembic/versions/`, `docker-compose`, `.env`, `main_production.py`.
- **Frontend intocado**: as telas usam a DSL genérica (table/form/panels) e as portas vieram por
  `EXTRA_MENU`/grupos no backend — nenhum deploy de frontend foi necessário.
- **Dívida conhecida que continua:** 15 telas sem porta no menu (pré-existentes, lista em
  `checar_tela_sem_porta`); `payable`/`receivable` antigos ficaram sem tela porque a F11 trocou os
  forms para a versão com condição de pagamento (as rotas seguem vivas para API).

## 8. Como a noite foi conduzida (para a próxima)

12 agentes em worktrees isoladas, cada um testando num container efêmero contra o sandbox
(recopiado de produção às 23:40), commits por pathspec na própria branch, merge só pelo
orquestrador com compilação + ruff + trava de porta + oráculo da frente + oráculos vizinhos,
árvore mesclada provada antes do bake, dois bakes (o segundo saiu pelo deploy de outra sessão que pegou o disco já mesclado — o lock serializou, como deve). Os conflitos de merge foram sempre os mesmos
dois arquivos de plug (`departamento_pessoal.py`, `_dp_grupos.py`) e triviais (ambos os lados
somam). O que custou tempo: o container efêmero morrendo no boot por `/app/logs` (3 vezes) — está
no contrato agora.
