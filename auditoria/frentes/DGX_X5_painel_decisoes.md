# DGX X5 — Painel do dono: as decisões pendentes com número ao vivo (24/09/2026)

## 1. Estado antes (medido)

Em dois dias, 20 frentes produziram **51 decisões que só o Jordan pode tomar**. Elas moram em:

| Onde | Quantas |
|---|---|
| `auditoria/RELATORIO_NOITE_2026-09-24.md` §4, §12, §15, §19 | as mesmas, ecoadas |
| §7 de cada `auditoria/frentes/DGX_*.md` (35 relatórios) | 51 |
| Em tela, onde ele decide | **0** |

Medido no sandbox em 24/09: `SELECT to_regclass('dono_decisoes')` → `NULL`. Não havia tabela,
serviço, tela nem rota. **Decisão em markdown morre**: quando ele abre o arquivo, o número é o
de quando a frente mediu, e não há onde registrar a resposta.

## 2. O que o DGX tem

O benchmark não tem «fila de decisão do dono» — é um instrumento desta casa, nascido do formato
`§7 — Decisões que só o dono pode tomar` que o contrato de frente obriga. O que o DGX ensina e
foi copiado aqui é a forma: **número ao lado da pergunta**, filtro por área, e a régua dita na
própria tela.

## 3. O que foi feito

### 3.1 Arquivos

| Arquivo | O que é |
|---|---|
| `backend/modules/operacional/services/dono_decisoes.py` (novo, 600 linhas) | A regra: DDL idempotente, a semente das 28 decisões com a PERGUNTA copiada do §7 de origem, as 18 consultas `numero_sql`, `medir()` com as três paredes, `listar()`, `decidir()`. |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_x5_decisoes.py` (novo) | As duas telas e as três ações. |
| `backend/modules/operacional/controllers/redesign_builders/bi.py` (+16 linhas úteis) | Plug: 2 itens no `EXTRA_MENU`, `telas(db, out)` no fim do `build()`, `router` no fim do arquivo. |
| `backend/scripts/orq/test_oraculo_x5_decisoes.py` (novo) | O oráculo. |

### 3.2 Onde foi — e por quê

O brief sugeria `orquestrador-executivo` **ou** `bi`. Li os menus:

- **`orquestrador-executivo`** é só uma URL de chat. O tile foi fundido com «Consultor IA» em
  19/09 (`frontend/src/app/redesign/page.tsx` L20-27: as duas URLs chamavam o mesmo
  `POST /consultores/chat/consultar`); o slug **não tem builder nem entrada em `BUILDERS`**.
  Tela nenhuma nasceria ali.
- **`relatorios`** existe, é admin-only e é «KPIs executivos consolidados» — relatório, não fila
  de decisão. Trocaria uma pilha de números por outra.
- **`bi`** está no grupo «Inteligência & Patrimônio», é o módulo que o dono abre para olhar
  número, tem builder próprio (`bi.py`) e hoje só duas abas — sobra porta. **A decisão do dono é
  um painel de número.** Foi para o BI.

### 3.3 DDL que o `ensure()` aplica no 1º acesso

```sql
CREATE TABLE IF NOT EXISTS dono_decisoes (
    id serial PRIMARY KEY, codigo varchar(20) NOT NULL UNIQUE, titulo varchar(200) NOT NULL,
    pergunta text NOT NULL, area varchar(20) NOT NULL, origem varchar(120) NOT NULL,
    impacto varchar(20) NOT NULL, numero_sql text, unidade varchar(20),
    tela_para_agir varchar(200), status varchar(20) NOT NULL DEFAULT 'aberta', decisao text,
    decidida_por varchar(120), decidida_em timestamptz,
    criada_em timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_dono_decisoes_status ON dono_decisoes (status);
-- + 28 INSERT ... ON CONFLICT (codigo) DO NOTHING
```

Nenhum DROP, DELETE ou UPDATE em dado que a frente não criou. **Nada aqui muda folha, preço,
escala ou pagamento** — grava texto de decisão, autor e data.

### 3.4 Telas

- `/redesign/bi?t=decisoes-do-dono` — Área · Decisão · A pergunta · **Número de hoje** · Impacto ·
  Origem · Ir para a tela · Situação. Filtros: Situação (padrão «aberta»), Área, Impacto. Ações
  por linha: **Decidir** e **Descartar** (some quando a linha já foi decidida). O botão genérico
  «Ver» do redesign abre a linha inteira — é por ali que se lê a pergunta completa.
- `/redesign/bi?t=decisao-registrar` — formulário: escolhe a decisão, escolhe decidir/descartar,
  escreve o texto livre.

### 3.5 As três paredes do `numero_sql`

1. **Varredura por palavra-chave** antes de chegar ao banco: INSERT/UPDATE/DELETE/CREATE/DROP/
   ALTER/TRUNCATE/GRANT/REVOKE/COPY/MERGE/VACUUM, com `\b` para não pegar `created_at`/`updated_at`.
2. **SAVEPOINT sempre desfeito**, inclusive quando a consulta dá certo (sentinela `_Desfaz`).
   Read-only de fato, não de intenção.
3. **`statement_timeout = 4000ms`** — consulta lenta não segura o painel.

Uma consulta que falha **não derruba o painel**: a linha mostra «não medido» e o erro vai para o
log. Decisão sem consulta (escolha pura) mostra «sem número, é escolha» — não se inventa número
para caber na coluna.

## 4. A tabela das decisões semeadas e o número que cada uma deu HOJE

Medido no sandbox (cópia de produção) em **24/09/2026**.

| # | Área | Decisão | Origem (§7) | Impacto | **Número hoje** | Tela para agir |
|---|---|---|---|---|---|---|
| D01 | folha | Faltas fora da base do INSS | DGX F1 §7.1 | dinheiro | **R$ 1.558,67** (última competência com espelho) | `?t=rubricas` |
| D02 | folha | Adicionais pagos fora da CCT | DGX F2 §7.1 e §7.2 | dinheiro | **11 pessoas** | `?t=cct-funcoes` |
| D03 | cadastro | Ativos sem cargo da CCT | DGX F2 §7.3 | cadastro | **5 pessoas** | `?t=funcionarios` |
| D04 | ponto | Escalas na paridade errada | DGX W1 §7.3 (caçador `checar_escala_paridade`) | operação | **4 pessoas-mês** | `operacional?t=g-escalas` |
| D05 | ponto | HE sem explicação | DGX W3 §7.1 | dinheiro | **195 itens** | `?t=he-classificar` |
| D06 | operacional | Postos com contrato inexistente | DGX T3 §7.2 | cadastro | **5 itens** | `operacional?t=g-postos` |
| D07 | operacional | Postos sem salário base | DGX T3 §7.3 | dinheiro | **15 itens** | `operacional?t=g-postos` |
| D08 | operacional | Clientes sem visita há + de 30 dias | DGX T3 §7.7 | operação | **19 itens** (de 29 clientes ativos) | `crm?t=visitas-por-cliente` |
| D09 | cadastro | Pessoas sem foto | DGX F6 §7.5 + T1 §7.3 | cadastro | **60 pessoas** (todas) | `?t=funcionarios` |
| D10 | cadastro | Pessoas sem CNH | DGX F10 §7.2 | risco | **60 pessoas** (todas) | `?t=funcionarios` |
| D11 | folha | Dependentes sem data de nascimento | DGX F6 §7.2 | dinheiro | **33 itens** (todos) | `?t=dependentes` |
| D12 | folha | Férias na faixa > 22 meses | FRENTE 08 §5 | risco | **5 pessoas** | `?t=mapa-ferias` |
| D13 | financeiro | Pensão sem beneficiário | DGX F11 §4.7 | risco | **0 pessoas** | `financeiro?t=pensionistas` |
| D14 | fiscal | NF-e só em resumo | DGX F9 §7.3 | dinheiro | **33 itens** | `suprimentos?t=nfe-entradas` |
| D15 | folha | Rubricas ativas nunca emitidas | DGX F1 §7.5 | cadastro | **15 itens** | `?t=rubricas` |
| D16 | cadastro | Colaboradores com dois logins | DGX F8 §7.3 | operação | **21 pessoas** | `configuracoes?t=usuarios` |
| D17 | cadastro | Demitidos sem data de demissão | DGX T1 §7.2 | cadastro | **15 pessoas** | `?t=funcionarios` |
| D18 | operacional | Alertas «lead sem contato» | DGX T3 §7.6 | operação | **295 itens** | `operacional?t=alertas` |
| D19 | folha | Folga trabalhada: HE ou compensatória? | DGX F8 §7.1 | dinheiro | *sem número, é escolha* | `?t=he-classificar` |
| D20 | operacional | Veículo é patrimônio? | DGX F10 §7.3 | cadastro | *sem número, é escolha* | `equipamentos` |
| D21 | operacional | Que itens de vistoria bloqueiam a saída | DGX V3 §7.5 | risco | *sem número, é escolha* | `operacional?t=frota-vistoria` |
| D22 | financeiro | Cobrança por e-mail sem clique | DGX T4 §7.1 | risco | *sem número, é escolha* | `financeiro?t=g-receber` |
| D23 | financeiro | A fatura substitui ou soma? | DGX W2 §7.1 | operação | *sem número, é escolha* | `financeiro?t=faturas` |
| D24 | financeiro | Fatura ou `gerar_recebiveis`? | DGX W2 §7.2 | dinheiro | *sem número, é escolha* | `financeiro?t=faturas` |
| D25 | fiscal | `tpAdmissao` 10 ou 11 na transferência | DGX W4 §7.1 | risco | *sem número, é escolha* | `?t=esocial` |
| D26 | fiscal | Ligar NBS/CST/cClassTrib na NFS-e | DGX V5 §7.1 | risco | *sem número, é escolha* | `fiscal?t=nfse` |
| D27 | operacional | Quem recebe o pânico sem alerta configurado | DGX U4 §7.1 | risco | *sem número, é escolha* | `operacional?t=g-ocorrencias` |
| D28 | folha | CSV de apontamento LANÇA na folha? | DGX V4 §7.1 | dinheiro | *sem número, é escolha* | `?t=importar-apontamento` |

**Confere com o relatório da frente de origem** em D03 (5), D04 (4 — a linha canônica do caçador
é «TOTAL escalas na paridade errada: 4»), D05 (195), D06 (5), D08 (19 de 29), D11 (33), D12 (5),
D16 (21), D17 (15), D18 (295). D14 dá 33 e o F9 §7.3 dizia 32 — chegou mais uma NF-e em resumo
desde a medição daquela frente; é exatamente o ponto desta tela.

**D01 merece leitura.** O número do F1 §7.1 (R$ 4.593,86 · 19+12 pessoas em 09/2026) saiu do
MOTOR rodando, não de linha gravada: `hr_payslip_items` de 09/2026 está vazia. O `numero_sql` mede
o que existe gravado — as faltas (1051 + 1053) da última competência com espelho, R$ 1.558,67 em
07/2026. A pergunta na linha cita os dois números, com a fonte de cada um.

## 5. Oráculo

`backend/scripts/orq/test_oraculo_x5_decisoes.py` — afirma: (1) toda decisão semeada tem origem e
pergunta e vocabulário válido de área/impacto; (2) todo `numero_sql` roda e devolve UM escalar, ou
é nulo de propósito; (3) nenhum `numero_sql` escreve — e a contra-prova: 7 SQLs de escrita
inventados no oráculo TÊM de ser recusados, e 2 SELECTs com `created_at`/`updated_at` NÃO podem
ser; (4) decidir grava autor e data e tira da lista de abertas, recusa decisão em branco e código
inexistente; (5) fixture com SQL inválido → a linha aparece como «não medido» e o painel continua
de pé. Fixtures `'FIXTURE DGX X5'` apagadas no fim (conferido: 0 sobraram).

```bash
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_x5_decisoes.py
```

**VERMELHO (antes do código):**
```
  File "/app/scripts/orq/test_oraculo_x5_decisoes.py", line 61, in main
    from modules.operacional.services import dono_decisoes as dd
ImportError: cannot import name 'dono_decisoes' from 'modules.operacional.services'
```

**VERDE (depois):**
```
decisões semeadas: 28 · com número: 18 · sem número (escolha): 10
  · D03: 5     · D09: 60    · D10: 60    · D16: 21    · D17: 15    · D13: 0
  · D14: 33    · D01: 1558.67 · D02: 11  · D11: 33    · D12: 5     · D15: 15
  · D06: 5     · D07: 15    · D08: 19    · D18: 295   · D04: 4     · D05: 195
TOTAL desvios no painel de decisões: 0
OK painel do dono: origem e pergunta em todas, todo numero_sql mede um escalar,
nenhum escreve, decidir grava autor e data, SQL ruim vira «não medido»
```

**HTTP (container `teste-dgx-x5`, porta 8265, já parado):**
`GET /api/v1/redesign/data/bi` → `extraMenu: ['receita-despesa','dre','decisoes-do-dono',
'decisao-registrar']`, `screens` com as duas telas novas, 28 linhas, 10 delas «sem número, é
escolha». Ações testadas de verdade: `decisao-decidir?codigo=D18` e `decisao-registrar` (D20,
descartada) gravaram `decidida_por=jjesus@conectamais.pro` e `decidida_em=2026-09-24`; decisão em
branco devolveu 400 («Escreva a decisão — é ela que fica registrada»). As duas linhas de teste
foram voltadas para `aberta` no sandbox.

`python3 backend/scripts/orq/test_menu_agrupado.py` → os 2 problemas que sobram são do `crm.py`
(grupos «Contratos» e «Reuniões & visitas» em blocos separados), anteriores a esta frente. `bi.py`
passa limpo.

## 6. Como o Jordan testa amanhã

1. `/redesign/bi` → na lateral, duas abas novas: **Decisões do dono** e **Registrar decisão**.
2. Abrir **Decisões do dono**. O filtro «Situação» já vem em «aberta». São 28 linhas.
3. Conferir a coluna **Número de hoje**: 18 linhas com número, 10 com «sem número, é escolha».
   O número é recontado a cada abertura — recarregue e ele continua batendo com o banco.
4. Filtrar **Impacto → dinheiro**: sobram 9. É por onde começar.
5. Numa linha qualquer, clicar **Ver**: abre a pergunta inteira, a origem e a tela para agir.
6. Numa linha, clicar **Decidir**, escrever a decisão e gravar. A linha muda para «decidida
   DD/MM/AAAA» e sai do filtro «aberta». Os botões Decidir/Descartar somem dela.
7. Copiar o endereço da coluna **Ir para a tela** e colar no navegador: vai direto onde a coisa
   se resolve.

## 7. Decisões que só o dono pode tomar

Esta frente não cria decisão nova — ela dá casa às 51 que já existiam. O que sobra para o dono
**sobre a própria fila**:

1. **As 23 decisões que ficaram de fora.** Semeei 28 das 51. As outras 23 precisariam cada uma de
   um SQL próprio (colisões de `codRubr` no eSocial, Σ|Δ| de 07/2026, insalubridade sobre base,
   comissões «auto — proposta», unificação `allocations`×`employee_alocacoes`, mínimos de 147
   materiais, 16 parâmetros vazios…). Um SQL errado no painel do dono é pior que markdown: entra
   como número e ninguém confere. Semear as demais é trabalho de uma frente inteira — ou de quem
   escreveu cada §7, que sabe a régua. **Quer as 23 na tela, ou as 28 bastam por enquanto?**
2. **Quem pode decidir?** Hoje: `admin` / `super_admin` / `administrador` ou permissão `*`/`all`.
   Se os dois gerentes tiverem de registrar decisão da área deles, isso muda.
3. **Decisão decidida some da tela?** Hoje fica, com badge «decidida DD/MM». Se virar poluição,
   o filtro resolve — mas talvez você queira um arquivo morto depois de 90 dias.
4. **«Ir para a tela» é texto, não botão.** O renderizador genérico do redesign (`ModuleView.tsx`)
   não tem célula-link: só texto, badge, foto, e botões de documento (que fazem `fetch` com Bearer,
   não navegação). Não toquei em `frontend/`. Para virar botão, o orquestrador precisa de um tipo
   de célula novo — algo como `{"isLink": true, "v": "Ir para a tela", "href": "..."}` renderizado
   como `<a>` — e aí a coluna vira um clique.

## 8. O que NÃO foi feito e por quê

- **23 das 51 decisões** não foram semeadas — §7.1 acima.
- **Nenhum `numero_sql` cobre 09/2026 para folha** porque `hr_payslip_items` de 09/2026 está vazia
  (a folha do mês ainda não gravou linha). O D01 mede a última competência com espelho e diz isso
  na pergunta.
- **A faixa «> 22 meses» de férias foi recontada por `employee_vacation_periods`** (período aberto
  com `days_remaining > 0` e mais de 22 meses desde `start_date`), não pela âncora do serviço
  `mapa_ferias.py` (admissão ∪ retorno de afastamento > 6 meses). As duas dão **5** hoje. Se o
  serviço e a tabela divergirem, o painel vai seguir a tabela — está escrito no SQL.
- **A ronda de 15% não entra no D02**: `cct_cargos` não tem coluna de ronda por cargo, então não há
  régua para contar «fora da CCT». A pergunta cita os 15 casos que o F2 achou.
- **Não mexi em `frontend/`, `alembic/`, `checar_regressao.py`, produção** nem em nada que execute
  pagamento. Produção foi lida zero vezes por esta frente (só o sandbox).
- **`bi.py` foi reformatado pelo `ruff format`** (o arquivo já estava fora do formato antes de eu
  tocar nele — `ruff check` acusava I001 no HEAD). Conferido depois: `test_menu_agrupado.py`
  continua lendo o `EXTRA_MENU` do `bi.py` sem problema (o regex `_ITEM` é `re.S`).

---

### Anexo — a mina do import circular

O plug natural (`from ._dgx_x5_decisoes import EXTRA_MENU, router, telas` no topo do `bi.py`)
**fecha um ciclo**: `_dgx_x5_decisoes` importa o `redesign_data_controller`, e o
`redesign_data_controller` roda o discovery no fim do próprio módulo, que importa o `bi.py`, que
importa o `_dgx_x5_decisoes` ainda meio carregado. O sintoma é uma linha de log e o módulo inteiro
sumindo do menu:

```
redesign_builders/bi falhou: cannot import name 'EXTRA_MENU' from partially
initialized module '..._dgx_x5_decisoes' (most likely due to a circular import)
```

**Verde e ninguém morre** — o discovery loga e segue; o `bi` simplesmente não existe mais. Só
apareceu porque o oráculo importa o serviço antes do controller, numa ordem diferente do boot.
O conserto: os itens do menu escritos direto no `bi.py`, `telas` importado dentro do `build()`,
`router` importado no FIM do `bi.py`, e o `redesign_data_controller` importado **dentro das
funções** do `_dgx_x5_decisoes`. Vale para qualquer frente futura que se plugue num builder que
o próprio `redesign_data_controller` carrega.
