# Departamento Pessoal — relatório geral

**Período:** 06/08/2026 (início da agentificação) → 07/08/2026 12:30
**Escopo:** módulo DP inteiro e suas ramificações (folha, ponto, férias, SST, eSocial, Central de Aprovações, infraestrutura de deploy)
**Autor:** T2

---

## 1. O ponto de partida

A pergunta que abriu tudo foi sua: *"olhando exclusivamente pro Departamento Pessoal, verifique se tem algum agente de IA neste módulo, o que ele faz? como ele faz? ele está fazendo o que foi criado para fazer?"*

A resposta medida foi: **existia uma camada de IA no DP e ela era casca.** Classes instanciadas, prompts escritos, nenhum caminho de execução. Ela foi removida (`e2eb4695`, "remove a camada morta de IA do DP") antes de construir qualquer coisa nova — não faz sentido empilhar em cima de código que finge funcionar.

O norte veio do grafo de conhecimento do DP e da sua descrição da rotina da Pyetra: **um quadro branco de prazos**. Aviso prévio que vence, experiência que fecha, ASO que expira, férias que passam do limite. Nada disso estava no sistema; vivia na cabeça e na parede dela.

O objetivo passou a ser: transformar esse quadro numa **caixa de decisões** — o agente prepara o trabalho rotineiro, ela aprova.

---

## 2. A camada de inteligência

### 2.1 Vigília — 9 watchers que olham o que ninguém olhava

Rodam no celery a cada 15 minutos, derivando prazo de dado real. Nenhum inventa data.

| Watcher | O que vigia | Alertas vivos hoje |
|---|---|--:|
| `dp_desligamento_sem_processo` | saiu da folha, não tem processo nativo | 9 |
| `dp_termino_experiencia` | 30+60 dias a partir da admissão | 5 |
| `dp_admissao_em_curso` | admissão começada e não concluída | 1 |
| `dp_aso_vencendo` | ASO fora da validade (NR-7) | 1 |
| `dp_ferias_limite_gozo` | período aquisitivo perto do art. 134 | 1 |
| `dp_ponto_a_fechar` | competência aberta perto do fechamento | 1 |
| `dp_aviso_previo_vencendo` | prazo do aviso correndo | silêncio |
| `dp_retorno_ferias` | quem volta e precisa reativar | silêncio |
| `dp_folha_devida` | competência sem folha gerada | silêncio |
| | **TOTAL** | **18 prazos** |

Os três em silêncio não têm achado hoje — silêncio honesto, não watcher quebrado.

**Achado que vale registrar:** o `dp_termino_experiencia`, derivando só de `data_admissao`, **reproduz o quadro manuscrito da Pyetra ao dia** — MEIRE e JEOVANE em 17/08, ALEXANDRE, KELLY e NAILSON em 18/08. O que ela mantinha à mão o sistema agora deriva sozinho.

**Correção de rumo sua:** os alertas primeiro diziam "desligamento sem processo", o que soava como negligência do DP. Você apontou que o sistema está EM MIGRAÇÃO — o dado vem da Portte e do eSocial. Reescrevi para *"Desligamento a migrar para o fluxo nativo"*. Alerta que acusa a pessoa errada é pior que alerta nenhum.

### 2.2 Ações — 12 propostas, o humano decide

Toda ação do DP no chat **propõe**, nunca executa. O LLM cria um rascunho inerte; quem aprova é gente.

```
solicitar_ferias · calcular_folha · fechar_folha · concluir_admissao
registrar_desligamento · registrar_afastamento · fechar_ponto · justificar_ponto
gerar_holerites_lote · renovar_aso · programar_ferias · registrar_ferias
```

Quatro têm **executor registrado** — aprovar dispara o serviço oficial de verdade:
`registrar_ferias`, `registrar_afastamento`, `fechar_ponto`, `justificar_ponto`.

O resto propõe e para. E **dinheiro não tem executor nenhum**: `pagar_folha_lote` não está em `EXECUTORES`, então não existe caminho de execução automática. Aprovar um 🔴 só marca `aprovado` e devolve `needsOtp`, empurrando para a tela de pagamento com OTP.

### 2.3 Saga — o DP conversa com os outros módulos

Evento `dp.folha.fechada` no Redis Stream → subscribers em financeiro e operacional criam rascunho no módulo deles. Provado **vivo**: evento real publicado, rascunho nascido pelo worker em 1,5 segundo.

### 2.4 A mesa — Central e Prazos

- **Central de Aprovações** (`/redesign/aprovacoes`): os cartões esperando decisão, agrupados por área (Folha, Ponto, SST, Férias), com selo de risco 🔵/🟡/🔴.
- **Prazos**: os 18 itens da vigília, que é o quadro branco dela em forma de tela.
- **Digest diário 07:00** (America/Manaus): "bom dia, N itens te esperam". Entregando de verdade — **7 destinatários, 4 dias seguidos**. Silêncio honesto quando não há item: ninguém recebe e-mail dizendo "0 itens".

### 2.5 Portas manuais

Toda operação que o agente propõe tem também a porta manual equivalente, apontando para **o mesmo endpoint**: registrar licença, agendar/renovar ASO, revisar justificativa de ponto, fechar mês, aviso de férias, contracheques em lote.

---

## 3. Folha — paridade com a Portte

Sua regra: *"a Portte é a fonte da verdade, nossa folha precisa espelhar fielmente a dela, com as regras que ela aplica."*

### O que foi decodificado

A chave estava na **coluna REFERÊNCIA** dos espelhos (horas por rubrica). Com 96 observações dava para derivar a fórmula, em vez de adivinhar. Descobertas:

- A Portte paga **adicional noturno por ESCALA, não por ponto** — múltiplos de 8. Você decidiu pagar pela escala, e o motor passou a fazer isso: 7 horas de relógio na janela 22:00–05:00, fator `(1 + 0,20 + ronda) × 1,5`.
- DSR sobre variáveis calculado só sobre horas extras.
- Férias descontadas em mês comercial de 30 dias.
- Escala 12x36 **não gera hora extra** nas telas de RH.

### O resultado medido

| | |
|---|--:|
| Σ\|Δ\| individual (antes) | R$ 10.664 |
| Σ\|Δ\| individual (depois) | **R$ 29,80** |
| Pessoas batendo ao centavo | **43 de 51** |
| Diferença total | **+R$ 28,89** (0,03%) |
| Meses espelhados | 7 (jan–jul) |
| Julho | 370 verbas, 51 pessoas |

Existe pipeline mensal reutilizável (`extrair → reconciliar → carregar` + backfills), não é trabalho manual de uma vez.

---

## 4. Os defeitos encontrados — inclusive os meus

Esta seção existe porque o padrão que ela mostra vale mais que a lista.

### 4.1 O botão Aprovar estava morto desde que nasceu

**O mais grave de todos.** `CurrentActiveUser` é `Annotated["User", Depends(...)]` com `"User"` como string. O `aprovacoes.py` tem `from __future__ import annotations`, então o FastAPI resolve anotações no namespace do módulo — onde `User` não existia. A resolução falhava **em silêncio** e `current_user` virava query param: **todo clique respondia 422**.

Nasceu assim em `062bdf96` (05/08). O banco confirmou: **zero rascunhos decididos** desde então. Ninguém nunca tinha aprovado nada pela Central.

Não era brecha de segurança — com `?current_user=x` dá 500, não aprova. Era porta morta.

### 4.2 Os outros três

| Defeito | Efeito |
|---|---|
| `revisar-justificativa` mandava POST para rota PUT, sem `reviewer_id` | 405, depois 422 |
| Campos constantes com `type:"hidden"`, que o ModuleView não conhece | virariam caixas **editáveis** — dava para trocar "aprovar" por outra coisa |
| `POST /sst/aso`: schema `str`, coluna DATE | **500 para qualquer chamador**; rota nunca usada por front nenhum |

### 4.3 A Central renderizava vazia com 3 rascunhos no banco

`ModuleView` inicializa a tela ativa lendo o menu do pacote JSON. **Eu** esvaziei esse menu para matar abas duplicadas — e aí `active` nascia `''`. `scr` tem fallback; `isReal` não tinha. Resultado: "Aguardando dado" permanente. A lista existia, ninguém via, e o botão estava atrás dela.

### 4.4 Eu apaguei seis meses de espelho

Um backfill com `DELETE ... WHERE ano=:a AND fonte=:f` — que eu li como "por mês" e era **por ano**. Rodar com `MESES=7` apagou jan–jun. Só descobri porque a captura de férias devolveu 0 onde eu esperava 6. Restaurado integralmente a partir de `hr_payslips`: 7 meses, 2.347 verbas, 356 dias. A paridade de julho sobreviveu.

### 4.5 O padrão

> **função ok → HTTP quebrado → HTTP ok → tela quebrada.**

Cada camada que eu não exercitei escondeu um defeito. Meus testes chamavam funções direto e passavam todos; o botão estava morto. Depois passaram por HTTP; a tela estava cega. Declarei "100%" duas vezes antes de as suas auditorias acharem buraco.

A conclusão que fica no processo: **prova de camada não vale para a camada de cima**. Hoje existe teste que bate no HTTP montando o payload **a partir do próprio builder** — se alguém mudar um campo da tela sem mudar a rota, o teste cai.

---

## 5. Infraestrutura — um defeito de plataforma achado pelo DP

Os workers do celery estavam **de pé há 8 a 13 dias** rodando código velho, enquanto o backend era deployado várias vezes por dia. Motivo: `deploy_backend_bluegreen.sh` **não mencionava celery em lugar nenhum**.

Custo concreto: os 9 watchers de DP existiam no backend e **não existiam no worker**. O avaliador rodava a cada 15 minutos sem enxergá-los, e os alertas ficaram **24 horas congelados** sem ninguém perceber — porque container "healthy" não diz nada sobre o código que ele carrega.

**Corrigido:** o deploy ganhou o passo 7/7, que recria os 8 containers (7 celery + flower) um por vez, esperando cada um ficar healthy, com `celery-beat` por último. Não-fatal: registra o que falhou sem desfazer um deploy de backend que deu certo. `SKIP_CELERY=1` pula quando nenhuma task mudou.

Isso valia para **qualquer módulo**, não só o DP. Qualquer task, watcher ou `beat_schedule` mexido nas últimas semanas — de qualquer terminal — só passou a valer depois disso.

Custo: deploy foi de ~4 para ~15 minutos. O trecho zero-downtime continua nos mesmos ~6.

---

## 6. Organização visual

O DP tinha **24 entradas soltas** no menu contra 7 grupos do financeiro. Passou a usar a mesma fundação (`_dp_grupos.py`, espelho de `_fin_grupos.py`): **8 grupos com abas**, na ordem do ciclo de vida do colaborador — que é como a Pyetra pensa o trabalho, não ordem alfabética nem de tela.

| Grupo | Abas |
|---|--:|
| Visão geral | 4 |
| Admissão & Cadastro | 9 |
| Ponto & Jornada | 4 |
| Folha de pagamento | 10 |
| Férias & Afastamentos | 8 |
| Benefícios & Reembolsos | 6 |
| Saúde & eSocial | 3 |
| Desligamento | 4 |

49 telas → 48 abas, **zero órfã**. Deep-link antigo preservado por redirect.

No caminho apareceram duas coisas: uma **duplicata que eu mesmo criei** (`registrar-licenca` e `nova-licenca` postavam no mesmo endpoint com os mesmos campos), e uma **terceira fonte de menu** — o módulo declarava menu em três lugares e o front soma os três.

---

## 7. Estado medido hoje

| | |
|---|--:|
| Ações que propõem | 12 |
| Executores (aprovar executa de verdade) | 4 |
| Watchers ativos | 9 · **18 prazos vivos** |
| Telas / grupos | 49 / 8 · 48 abas |
| Arquivos de prova | 7 · **30 PASS** |
| Resíduo de bancada | **0** |
| Digest | 7 destinatários/dia, 4 dias |
| Paridade folha julho | **+R$ 28,89** (0,03%) |
| Saga cross-módulo | provada viva (1,5s) |

**Verificado no navegador, ponta a ponta:** clique em Aprovar → modal → HTTP → auth → executor → serviço oficial → linha real em `sst_afastamentos`, rascunho `executado` com o aprovador correto, lista caindo de 3 para 2. Primeira vez que essa cadeia inteira roda neste sistema.

Como efeito colateral do teste, o **RBAC ficou provado sem eu ter planejado**: uma sessão real de `gerente_operacional` no navegador mostrou a Central com 0 rascunhos, corretamente filtrada.

---

## 8. Decisões suas registradas

- **Adicional noturno pela ESCALA**, como a Portte, não pelo ponto.
- **Pyetra vê tudo na Central; quem aprova dinheiro é você.** Avaliado restringir `roles_aprovador` dos cartões do financeiro e **recusado** — não funcionaria (o curto-circuito `_is_admin` ignora o campo) e a regra da casa já diz que Financeiro = Jordan + Pyetra.
- **ARYELTON suspenso** — fora da folha; alerta de férias deve pular suspenso.
- Caminho oficial da folha é a tela `folha-gerar`.

---

## 9. O que fica aberto

**Fora de escopo por decisão, não por esquecimento:**
- O **ritmo mensal** do quadro da Pyetra (VT/VR dias 12–14, kit 18–21, pagamento dia 20) é calendário recorrente dela, não prazo derivado de dado. Codificar as datas seria fabricar agenda.

**Precisam de você:**
- Teto do salário-família 2026 (Portaria MPS/MF nº 13/2026).
- Média do art. 142 pede 12 meses de histórico; temos 7.

**Conhecido e anotado:**
- `celery-beat` segue com código anterior ao último bake — só agenda, e nenhum agendamento mudou.
- `EMAIL_FROM` vazio: o digest entrega pelo sino, não por e-mail.
- Terceiro pareador de batidas em `reports_repository.py` — território operacional, parado.
- `gedeon.risk_monitor` (financeiro) falha ao publicar evento: tenta `localhost:6379`. O bus conecta normalmente quando chamado direto, então é o caminho daquela task. **Não é do DP** — é do terminal do financeiro.

---

## 10. Leitura final

O DP saiu de "tem uma IA que não faz nada" para uma mesa de decisões que prepara trabalho sozinha, vigia 18 prazos a cada 15 minutos e executa de verdade quando alguém aprova — com dinheiro sempre parando num gate humano.

Mas a parte mais útil deste relatório talvez seja a seção 4. Três dos quatro defeitos mais graves eram **meus**, e nenhum deles apareceu em teste — apareceram quando alguém (você, ou eu forçado a subir uma camada) foi olhar onde eu não tinha olhado. O sistema hoje está mais confiável não porque construí mais, mas porque **a distância entre "meu teste passou" e "a Pyetra consegue clicar" finalmente foi percorrida inteira**.
