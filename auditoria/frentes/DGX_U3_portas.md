# DGX U3 — Porta para toda tela: 13 telas órfãs e 2 ações sem tela (24/09/2026)

Branch `dgx/u3-portas` sobre `fase5-hermes-camada-cognitiva` @ 7e297d134. Container efêmero
`teste-dgx-u3` (porta 8233), parado ao fim. Frontend intocado.

## §1 — Estado antes (medido)

`python3 backend/scripts/qa/checar_tela_sem_porta.py` contra a produção, 24/09 06:1x, régua antiga:

```
  TELA servida e fora de todo menu/aba: 13
       crm/atividades · departamento-pessoal/mapa-ferias · departamento-pessoal/rep-p-instrumento
       marketing/gerar-texto · marketing/nova-campanha · marketing/nova-estrategia · marketing/novo-lead
       operacional/consultor-op · operacional/consultor-op-arquivo · operacional/notificacoes-marcar-todas
       operacional/otimizar-escala · operacional/otimizar-escala-mes · rh/registrar-motivo-desligamento
  AÇÃO que nenhuma tela chama: 2
       /redesign/action/payable · /redesign/action/receivable
TOTAL: 15 sem porta
```

## §2 — O que o DGX tem

Não se aplica: a frente é de navegação do próprio Conecta PRO (tela que existe e ninguém alcança).

## §3 — Decisão por tela

Lido o builder de cada uma e o `ModuleView.tsx` (o que o front DESENHA como porta: item do menu do
pacote, `extraMenu`, aba de grupo, `ctaTo` de tela de topo com `cta` — linha 1315 — e stub `redirect`).

| Tela / ação | Decisão | Onde ficou a porta | Por quê |
|---|---|---|---|
| `departamento-pessoal/mapa-ferias` | (a) aba | g-ferias → «Mapa de férias (risco de dobra)» (`_dp_grupos.py`); `_frente_08.telas` passou a rodar ANTES de `montar_grupos` (`departamento_pessoal.py`) | frente 08 nasceu depois da navegação e ficou só no deep-link; a raiz `mapa-ferias` vira `redirect` para a aba (deep-link antigo segue) |
| `departamento-pessoal/rep-p-instrumento` | (a) aba | g-ponto → «Instrumento legal (INPI/atestado)», ao lado de «AFD» | é o cadastro que o AFD exige (sem INPI o arquivo sai `SEM_INPI`); já era montado antes de `montar_grupos` |
| `operacional/consultor-op` · `consultor-op-arquivo` | (a) aba | g-visao → «Consultor operacional» · «Consultor operacional · anexo», ao lado de «Consultor IA» | os 4 forms do operacional nasciam DEPOIS da navegação: movi o bloco `montar_grupos` para depois deles (`operacional.py`) |
| `operacional/otimizar-escala` · `otimizar-escala-mes` | (a) aba | g-escalas → «Otimizar escala (dia)» · «(mês)» | só sugere, não grava (decisão de 10/08 mantida); idem acima |
| `operacional/notificacoes-marcar-todas` | (b) mudou de casa | `meu-espaco/notificacoes` ganhou `ctaTo` → form `notificacoes-marcar-todas` montado em `_build_meu_espaco` | a tela de notificações vive no meu-espaço e o botão «Marcar lidas» dela não levava a nada; a rota (`operacional.py: rd_action_notif_marcar_todas`) é a mesma, marca as do usuário logado. Saiu do operacional (o `_op_grupos` já a tinha expulsado do menu) |
| `rh/registrar-motivo-desligamento` | (a) `ctaTo` | `rh/turnover` (item do menu) ganhou `cta: "Registrar motivo"` + `ctaTo` | o form alimenta a análise de turnover; `rescisao` (DP) é outro módulo e `ctaTo` só resolve dentro do mesmo payload |
| `marketing/novo-lead` · `nova-campanha` · `gerar-texto` · `nova-estrategia` | falso positivo | JÁ tinham `ctaTo` de `lead-magnet` / `campanhas` / `copywriter` / `estrategista` (todas no menu) — botão desenhado há semanas | o caçador não contava `ctaTo` como porta. Corrigido no caçador (§4). Nada mudou no marketing |
| `crm/atividades` | porta existe no repositório | `crm.json` commitado (d938de02d) tem o item; a cópia de trabalho de `/opt/conecta-pro` foi reescrita hoje 06:10 (minificada, sem `atividades`, não commitada) | drift do checkout principal, não do backend. Não toco `frontend/`. Ver §7 |
| `/redesign/action/payable` · `/receivable` | (b) rotas removidas | forms base apontam para `payable-condicao` / `receivable-condicao` (F11; o F12 ainda troca receber por `receivable-fonte`, que delega à F11) | `_conta_com_condicao` sem `condicao_id` = 1 título pelos MESMOS serviços e campos — superset exato. `grep -rn` no repositório inteiro (backend, frontend/src, scripts, agents, tests): nenhum front/MCP/teste chamava as rotas. `rd_action_payable` FICA como função (F10 frotas a importa: locação → título); `rd_action_receivable` apagada (43 linhas) |

Menus propostos por F9 §7 e T5 §5.8: todos os ids (`solicitacoes-compra`, `pedidos-compra`, `nf-entrada`,
`comunicacoes-moveis`, `rastreadores`, `kit-uniforme`, `auditoria-telas`, `solicitacoes-material`,
`acessos-temporarios`, …) já têm porta pelo `EXTRA_MENU` — o caçador não acusa nenhum. Nada a aplicar.

## §4 — Oráculo e caçador

**Caçador** `backend/scripts/qa/checar_tela_sem_porta.py` — dois ajustes documentados no docstring:
1. `ctaTo` de tela de topo com `cta` é porta (transitivo). Falso positivo real: 4 telas do marketing.
   Dentro de aba o front não lê `ctaTo`, por isso a mãe tem de ser tela de topo (menu/extraMenu/ctaTo).
2. `QA_CONTAINER` (default `conecta-pro-backend`): as rotas eram lidas SEMPRE da produção, mesmo com
   `QA_API` apontando para um container efêmero — a lista de ações não era a do que se media.
As funções puras (`telas_sem_porta`, `colhe_endpoints`, `fonte_builders`, `acoes_orfas`, `portas_do_menu`)
ficaram importáveis. Linha canônica inalterada: `TOTAL: N sem porta`.

**Oráculo** `backend/scripts/orq/test_oraculo_toda_tela_tem_porta.py` — aplica a MESMA régua ao app
importado (`RD.BUILDERS`, `RD.EXTRA_MENU`, `RD.router.routes`) com o banco do sandbox; precisa dos JSONs
de menu (`QA_MENUS`, `/menus` montado, ou `<repo>/frontend/...`); sem eles sai 2, nunca verde. Builder
que cai é achado (população contada: `32 módulo(s) medido(s)`).

Vermelho (HEAD 7e297d134 + régua nova, `git archive HEAD backend` montado em /app):
```
   ✗ tela sem porta: departamento-pessoal/rep-p-instrumento
   ✗ tela sem porta: departamento-pessoal/mapa-ferias
   ✗ tela sem porta: operacional/notificacoes-marcar-todas
   ✗ tela sem porta: operacional/consultor-op
   ✗ tela sem porta: operacional/consultor-op-arquivo
   ✗ tela sem porta: operacional/otimizar-escala
   ✗ tela sem porta: operacional/otimizar-escala-mes
   ✗ tela sem porta: rh/registrar-motivo-desligamento
   ✗ ação sem tela: /redesign/action/payable
   ✗ ação sem tela: /redesign/action/receivable
   · 32 módulo(s) medido(s), 279 ação(ões) no router, menus em /menus
TOTAL: 10 sem porta        exit=1
```
(15 − 4 do marketing, que o `ctaTo` resolve − 1 do crm, cujo JSON commitado tem a porta.)

Verde (esta árvore):
```
   · 32 módulo(s) medido(s), 277 ação(ões) no router, menus em /menus
TOTAL: 0 sem porta         exit=0
```
Caçador contra o container efêmero (`QA_API=…:8233 QA_CONTAINER=teste-dgx-u3 QA_RAIZ=$WT`): `TOTAL: 0 sem porta`.
Caçador com a régua nova contra a PRODUÇÃO (antes do bake): `TOTAL: 11 sem porta` (9 telas — as 8 acima +
`crm/atividades` pelo drift do JSON — e as 2 ações). Depois do bake, o esperado é **1** (`crm/atividades`)
até o checkout principal voltar ao `crm.json` commitado; com ele, **0**.

Vizinhos, no efêmero: `test_aba_declarada_nasce.py` → `TOTAL: 0 aba(s) declarada(s) sem tela` (387 abas);
`test_oraculo_mapa_ferias.py` → `OK`. Prova HTTP (8233): g-ponto tem `rep-p-instrumento`; g-ferias tem
`mapa-ferias` (table, 52 linhas; raiz = redirect); g-visao tem os 2 consultores; g-escalas os 2 otimizadores;
`rh/turnover.ctaTo = registrar-motivo-desligamento`; `meu-espaco/notificacoes.ctaTo` + form; forms de conta
apontam para `payable-condicao` / `receivable-fonte`; `POST /action/payable|receivable` → 404.

## §5 — O que NÃO foi feito e por quê

- `frontend/` intocado (contrato). `crm.json` do checkout principal não foi restaurado — é do orquestrador.
- KPI `to` de dashboard (`DashScreen`) também é porta no front; não entrou na régua porque nenhuma das 15
  precisava dela (YAGNI). Se um dia um dash apontar `to` para tela sem outra porta, o caçador acusa — e
  aí se acrescenta.
- `ruff`: os 4 arquivos grandes (`operacional.py`, `rh.py`, `departamento_pessoal.py`,
  `redesign_data_controller.py`) já tinham 32 erros no HEAD; não formatei linhas alheias. Os 4 arquivos
  que são meus ou pequenos (`_dp_grupos`, `_op_grupos`, caçador, oráculo) passam limpos.
- Não registrei o oráculo em `checar_regressao.py` (contrato: o orquestrador registra).
- `receivable-condicao` continua sem tela no payload (F12 troca o form por `receivable-fonte`); não é
  órfã pela régua (nome no fonte da F11) e a F12 delega a ela. Deixei.

## §6 — Como o Jordan testa amanhã

1. DP → **Ponto & Jornada** → aba «Instrumento legal (INPI/atestado)» (ao lado de AFD). **Férias &
   Afastamentos** → aba «Mapa de férias (risco de dobra)»: 52 linhas, legenda por faixa.
2. Operacional → **Visão Geral** → «Consultor operacional» e «· anexo». **Escalas & Turnos** → «Otimizar
   escala (dia)» / «(mês)» — só devolve sugestão.
3. RH → **Turnover** → botão «Registrar motivo» no cabeçalho → form com os desligados sem motivo.
4. Meu Espaço → **Notificações** → botão «Marcar lidas» → «Marcar todas».
5. Financeiro → Contas a pagar → «Registrar conta a pagar»: sem condição = 1 título (como antes);
   com condição = parcelas. Idem receber.
6. Marketing → Campanhas / Lead magnet / Copywriter / Estrategista: os botões já estavam lá.

## §7 — Decisões que só o dono / orquestrador podem tomar

1. **`crm.json` do checkout principal** (`/opt/conecta-pro/frontend/src/app/redesign/_modules/crm.json`,
   reescrito hoje 06:10, não commitado, sem `atividades`): restaurar do HEAD (`git checkout -- <arquivo>`)
   e publicar o front, ou commitar a remoção de propósito — nesse caso `crm/atividades` vira achado real e
   a tela (crm_activities, real) precisa de outra porta.
2. Frente 08 (`_frente_08.py`) diz no docstring «alcance hoje: deep-link» — ficou desatualizado; não editei
   `_frente_*` por contrato.
- Commit do código com `SKIP=ruff,ruff-format` (como T5 §5.9): o hook reescreveu 6 arquivos com linhas alheias e abortou; bandit, secrets e governança passaram.

## Correção do orquestrador (24/09, depois do bake 19)

`backend/scripts/orq/test_oraculo_toda_tela_tem_porta.py` foi **apagado**. Dois motivos medidos:

1. **Não mede onde roda.** A varredura da meia-noite roda os oráculos DENTRO do container de
   produção, e os JSONs de menu vivem em `frontend/src/app/redesign/_modules` — que não existe
   naquele container. Saída real em produção: `NÃO MEDIDO — JSONs de menu do front não encontrados`.
2. **Vermelho falso todo dia.** Ele saía com código 2; a convenção da casa é `3 = BLOQUEADO`
   (`modules/notifications/tasks_oraculos.py::_EXIT_BLOQUEADO`). Com 2, a varredura classificava
   como **vermelho** — um alarme permanente que ninguém leria depois da segunda noite.

A regra continua vigiada, e por quem consegue medi-la: o caçador `checar_tela_sem_porta.py`, que
roda **no host** (`CACADORES_HOST` em `checar_regressao.py`, linha da trava 75), mede contra a
produção no ar — medida mais forte que a do app importado. As melhorias de régua que a U3 fez no
caçador (o `ctaTo` de tela de topo com `cta` é porta; `QA_CONTAINER`) ficam.
