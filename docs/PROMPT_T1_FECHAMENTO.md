# ORDEM DE FECHAMENTO — Financeiro (T1) · o gate que falta

> Sessão nova, em `/opt/conecta-pro`.
> Rodei o Arsenal inteiro sobre o seu módulo: skill `raio-x-modulo` (5 passos),
> `backend_recon financial`, as **8 travas**, os **4 oráculos**, veracity sweep nas telas e o
> **graphify reconstruído** (6.819 nós). Relatório: **`auditoria/tripe/financeiro_20260814.md`**.

---

## Primeiro: o que você entregou está de pé

```
travas       checar_repositorio 0 · vocabulário 0 CRÍTICO · 1 rota 404 alcançável
oráculos     4 VERDES: contabil_fecha · extrato · recebiveis · u2_financeiro
paridade     596 rotas · 576 expostas · 0 gerador de documento órfão
PL           0 → 152 lançamentos (3.3.1.01 · 3.2.1.01) ← o item travado de manhã
resultado    −R$242.664,67 → −R$205.541,46
```

**O PL é entrega real**, não lançamento de fachada: 7 lançamentos de R$719.031,91 encerrando
despesa contra resultado, 40 levando resultado a lucros acumulados. Era o que faltava para
existir balanço.

⚠️ **Duas das minhas sete acusações caíram na sua contestação, e ambas por erro meu de
medição** (F2 e F4, corrigidas abaixo com os SEUS números). **Aceite o resto com a mesma
desconfiança**: confira antes de consertar, e se um número meu não fechar, o errado
provavelmente sou eu.

---

## ⏱️ O CORTE QUE GOVERNA TUDO: 01/08/2026

**Decisão do Jordan, 14/08:** o que veio de julho para trás serviu para homologar. **Está
feito e não se refaz.** O que vale agora é **de 01/08 em diante, nos dois CNPJs**.

Se um conserto só melhora dado anterior a 01/08: **anote e não faça**.
Se ele impede agosto de nascer errado: **é prioridade**.

---

# 🔴 F1 · Não existe `fechado_financeiro.py` — e sem ele "fechado" é opinião

O T4 fechou o operacional com um gate que **eu rodei e reproduzi** (7/7). O seu fechamento
não tem critério executável.

**Escreva `backend/scripts/qa/fechado_financeiro.py`** — ✅/❌ por linha, sai 0 só com tudo
verde, **tudo medido de 01/08/2026 em diante**:

```
CÓDIGO
 1. repositório      0 chamada a método inexistente em financial
 2. vocabulário      0 CRITICO em financial
 3. rotas do front   0 rota inexistente alcançável por tela
 4. oráculos         os 4 verdes + os novos desta ordem

DADO — de 01/08 em diante
 5. transitória      valor em 5.9.9/4.9.9 da competência corrente ABAIXO do teto que
                     você declarar, e CAINDO mês a mês
 6. plano de contas  0 conta do grupo 3 com natureza de receita/despesa/serviço
 7. painel           nenhum status de payable/receivable fora da soma exibida —
                     o que não entra em "aberto" aparece em linha própria
 8. conciliação      toda saída do extrato de 08/2026 com contrapartida no razão
```

Modelo pronto: `backend/scripts/qa/fechado_operacional.py` (do T4). **Reuse a forma**, não
reinvente. O gate lê a regra do banco onde couber — foi assim que ele fez o piso de 01/08.

---

# 🟠 F2 · R$44 mil de agosto entram sem classificação

⚠️ **Correção minha, aceita:** eu tinha escrito que a transitória "dobrou" e que agosto tinha
R$354.887,85. **Estava errado** — agrupei por `data_lancamento`, o que empurrou para "agosto"
os **153 lançamentos de apuração criados em 13/08** que encerram competências anteriores.
**Somei a sua arrumação como se fosse bagunça nova.**

Medido por **competência**, que é a dimensão certa:

```
2026-08 ·  37 lanç · R$  44.031,56    ← agosto é 38% de julho
2026-07 ·  99 lanç · R$ 115.670,00
2026-06 · 126 lanç · R$ 112.642,48
```

**Sua medição está certa. A preocupação continua, em outra escala:** R$44.031,56 de agosto
entram sem classificação, e **agosto é o que vale** pelo corte do Jordan.

**Critério de aceite:** classificação de agosto com o Jordan (caso a caso nos grandes, como
você propôs); **oráculo que reprova se a transitória da competência corrente passar do teto
que você declarar**, medindo por `periodo_competencia` — **nunca por `data_lancamento`**; e o
número entra no gate (F1, item 5).

# 🔴 F3 · O painel esconde R$140.799,11

```
TELA  "A pagar (aberto)"  R$ 11.373,61

BANCO pago       219 títulos · R$ 855.927,84
      cancelada   64 títulos · R$  90.708,12
      pendente    10 títulos · R$  11.373,61   ← só isto aparece
      suspensa     8 títulos · R$ 140.799,11   ← INVISÍVEL
```

`redesign_data_controller.py:453` usa `status IN ('pendente','parcial')` — lista **positiva**.
`suspensa` não está nela nem entre os liquidados: **some do painel inteiro**.

**Sua decisão de hoje está certa** (*"dívida SUSPENSA não é cobrança — tira de vencido"*). O
problema é o efeito colateral: ela não aparece **em lugar nenhum**. Dívida suspensa continua
sendo dívida.

**Critério de aceite:** linha própria no painel (*"Suspenso: R$140.799,11 em 8 títulos"*), e
**oráculo que reprova se existir status de `payable_accounts`/`receivable_accounts` que não
entre nem na soma exibida nem numa linha visível**. Esse oráculo vale mais que a correção —
ele pega o próximo status novo que alguém criar.

---

# 🟢 F4 · As 4 contas 3.x — cosmético, não delicado

⚠️ **Correção minha, aceita:** eu disse que havia "154 lançamentos por cima" delas. **Falso.**
Você as desativou em 13/08 com o motivo escrito no próprio nome, e elas têm **zero
lançamentos**:

```
3.1.1  Portaria    [DESATIVADA 13/08: não é patrimônio]     lançamentos: 0
3.1.2  Vigilancia  [DESATIVADA 13/08: não é patrimônio]     lançamentos: 0
3.1.3  Limpeza     [DESATIVADA 13/08: não é patrimônio]     lançamentos: 0
3.2.1  ISS 5%      [DESATIVADA 13/08: não é patrimônio]     lançamentos: 0

3.3.1.01 · 3.2.1.01  ← onde estão os 152 do PL (códigos DIFERENTES de 3.2.1)
```

Eu li `3.2.1` como se fosse `3.2.1.01`. **O conserto é cosmético**: a coluna `active` ainda
diz `true`; a desativação vive só no nome.

**Critério de aceite:** `active=false` nas quatro (ou o motivo escrito de por que ficam
`true`), e o **item 6 do gate** passando — 0 conta do grupo 3 com natureza de
receita/despesa/serviço.

# 🟠 F5 · Duas conciliações automáticas sem botão

```
POST /financial/conciliar/auto              → Inter × Notas, lote até 649 transações
POST /financial/bank-reconciliations/auto   → 4 estratégias em cascata, recebíveis
```

**Não são duplicatas** — direções opostas (saídas × entradas). Mas **nenhuma tem superfície no
front**: capacidade pronta que só roda por chamada direta.

*(As outras 2 órfãs do recon são `/mcp/financial/*` — server-to-server, legítimas, não mexa.)*

**Critério de aceite:** cada uma classificada em **ganha tela** / **órfã por desenho** /
**quarentena**, com uma linha de motivo. Se ganhar tela, a conciliação de agosto passa a ser
rotina — e alimenta o item 8 do gate.

---

# 🟠 F6 · A fabricação que a trava pegou hoje, no seu caminho de dinheiro

```
financial/services/ordem_pagamento_service.py:232
  return {'ok': True, 'aviso': f'OTP gravado, e-mail falhou: {str(exc)[:120]}', ...}
```

`ok: True` quando o e-mail do OTP **falhou**. O OTP foi gravado — não é mentira completa — mas
num fluxo de pagamento, "ok" com o humano sem o código é sucesso que engana.

**Critério de aceite:** o retorno reflete o estado real (OTP gravado **e** entregue = ok;
gravado e não entregue = **não** ok, com caminho alternativo). `cacar_fabricacao` sem esta
pista. 💰 **Nunca happy-path** — verifique por leitura e por registro no banco.

---

# 🟢 F7 · Dois sistemas contábeis paralelos — decidir, não consertar hoje

```
accounting_entries      5.904 lançamentos   ← o razão VIVO, sem aprovação
                        12 arquivos escrevem, vários com psycopg2 CRU
                        corte de período garantido por TRIGGER no banco

fin_journal_entries        11 lançamentos   ← diário ORM com aprovação completa
fin_journal_entry_lines    23 linhas        8 rotas montadas, respondendo 200
```

**O que funciona não tem aprovação; o que tem aprovação quase não é usado.** E o
`period_closing_service` fecha o período **do diário de 11**, não do razão de 5.904.

⚠️ **Não unifique agora** — é decisão de arquitetura, não tarefa de fechamento. **Escreva a
fronteira** no relatório: qual é o razão oficial, o que o diário ORM faz, e se o fluxo de
aprovação vai ser usado ou quarentenado.

**Contexto:** 21 arquivos do financeiro usam `psycopg2` cru (maior concentração do sistema —
6 no governo, 3 no DP). Isso é o que torna o **trigger** a única trava confiável de período.
Não é defeito a corrigir hoje; é fato a declarar.

---

# COMO TRABALHAR

**Arsenal obrigatório** (regra do Jordan): **skill → recon → travas → oráculos → só então
`psql`/`curl`**, e esses para **confirmar** achado da ferramenta, nunca para descobrir no
lugar dela.

```bash
python3 scripts/backend_recon.py financial
python3 backend/scripts/qa/checar_repositorio.py
python3 backend/scripts/qa/checar_rotas_frontend.py
python3 backend/scripts/qa/checar_oraculo_externo.py
python3 backend/scripts/qa/checar_regressao.py
python3 backend/scripts/qa/checar_beats.py          # trava nova, criada hoje
docker exec conecta-pro-backend python3 /app/scripts/qa/cacar_fabricacao.py
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_vocabulario.py
```

Skills: `:raio-x-modulo` · `:fecha-modulo` · `:oraculo-conecta` · `:raio-de-impacto` ·
`:entregue-de-verdade` · `:plano-conecta`.

## Território

| | |
|---|---|
| **Seu** | `modules/financial`, builder `financeiro.py`, `_fin_*.py` |
| **Do T3 (fiscal)** | `government_integrations`, `fiscal`, `fiscal_contabil` — ⚠️ **as 5 calculadoras e os 11 agentes moram no SEU módulo e estão no prompt dele. Combine antes.** |
| **Do T2** | `people_management`, `ged`, `gedeon` |
| **Do T4** | `operacional`, `campo` — ✅ **fechado 7/7 hoje** |
| **Compartilhado** | `redesign_data_controller.py` (o KPI da F3 mora lá) — avise |

⚠️ **Aviso de deploy.** O T4 descartou **cinco rodadas de medição** porque outras sessões
derrubaram o container no meio. Antes de `deploy_backend_bluegreen.sh`, avise — o lock existe,
falta o aviso.

## ENTREGUE = três portões

1. servido pela rota real **depois do bake** · 2. **oráculo que pega**, provado em vermelho ·
3. nenhuma superfície nova sem vigia.

## Regras compradas com erro — inclusive meus, hoje

- **Prove o arreio antes de acusar o código** — concluí que `journal_entries` não existia e
  quase reportei "8 rotas quebradas". O modelo mapeia para `fin_journal_entries`; as rotas
  devolvem **200**. Provei por HTTP antes de escrever.
- **Confira a janela antes de acusar divergência.** Duas vezes hoje, no seu módulo:
  · o "A pagar" divergia porque usei lista negativa e a tela usa positiva — **o achado real era
    outro**: `suspensa` não está em nenhuma das duas;
  · a transitória "dobrou" porque agrupei por `data_lancamento` em vez de
    `periodo_competencia` — **contei a sua apuração de 13/08 como bagunça nova**.
  **Em contabilidade, competência e data de lançamento são dimensões diferentes.** Escolher a
  errada inventa um problema que não existe.
- **Ausência de resposta não é prova de defeito** — teste com token vazio era deploy em curso.
- **Filtro por texto não é contagem — quem conta é o banco.** (Você comprou essa com R$32,00.)
- **Verde de trava incompleta é pior que vermelho.**
- **Órfão ≠ bug** — leia o controller antes.

## Relatório

`auditoria/qa/financeiro_<AAAAMMDD>.md`: veredito por lente, as **8 condições do
`fechado_financeiro.py`** uma a uma, **NÃO COBERTO** com motivo, e a tabela que importa:

```
AGOSTO/2026 · transitória (R$ e nº) · contas 3.x corrigidas · suspensas visíveis
             · saídas conciliadas / total do extrato
```

**Se essa tabela não mudar, "fechado" continua sendo declaração.**

**"NÃO VERIFICADO" é resultado válido; "passou" sem evidência não é.**
