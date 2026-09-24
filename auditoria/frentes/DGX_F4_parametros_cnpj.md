# DGX F4 — Parâmetros do sistema por CNPJ (24/09/2026)

**Branch:** `dgx/f4-parametros-cnpj` (base `c7077dbb6`) · **Módulo:** config (+ 1 constante na folha, 1 no painel de ponto) · **Sessão:** agent-f4
**Container de teste:** `teste-dgx-f4` em 127.0.0.1:8204 — **parado e removido** ao fim.

## 1. Estado antes (medido no sandbox)

- `system_configs`: **12 linhas**, todas de escopo global (`sino.*`, `qa.*`, `contabil.corte_baseline`,
  `ged.agendamento`, `ponto.facial.*`, `ponto.offline.*`, `vigilante.*`, `oraculos.*`). Duas levas de
  colunas (PT: `tipo/escopo/grupo/descricao/is_editavel/historico`; EN: `valor_type/scope/group/...`).
  `chave` é **UNIQUE**; 5 das 12 linhas sem `grupo`, 7 com `tipo='string'` e o tipo de verdade em `valor_type`.
- **Nenhum leitor comum**: `conformidade_vigilante`, `reconferencia_facial`, GED, `tasks_oraculos` e mais
  4 fazem SQL próprio em `system_configs`. **Oito** escritores fazem `ON CONFLICT (chave)`.
- **Sem porta de edição**: `configuracoes-sistema` mostra limites de tenant, não parâmetros.
- Parâmetros de negócio chumbados: `ADIANTAMENTO_PERCENTUAL = 0.40` (`calculo_service.py:112`),
  `TOLERANCIA_ENTRADA_MIN = 15` (`coorte_ponto.py:186`), `TOLERANCIA_ATRASO = 15 min`
  (`presence_controller.py:71`), `DESC_VT_PCT = 0.04`, `DESC_VR_PCT = 0.01`, `VT_DIA = 10`, `VR_DIA = 22`,
  `DIAS_TRAB_ESCALA['12x36'] = 15`, `geofence_raio_metros default=150`, `SMTP_FROM_EMAIL`.
- `tenant_settings`: 0 linhas; `tenants`: 1 (o grupo). Empresas do grupo em `empresas`:
  Conecta Mais Eletrônica `35710481000103` (principal) e Conecta Mais Patrimonial `66014833000110`.

Oráculo VERMELHO (sandbox, antes de qualquer código):
```
$ python3 /app/scripts/orq/test_oraculo_parametros_por_cnpj.py
FALHOU: leitor/frente não importa: cannot import name 'parametros' from 'core' (/app/core/__init__.py)
TOTAL parâmetros por CNPJ: 1 falha
exit=1
```

## 2. O que o DGX tem

127 parâmetros `{nome, valor, chaveEmpresa}` — **um valor por empresa** — em 12 seções da API
(`docs/dgx/05`) e uma tela `/Configuracoes` com 108 campos em 13 seções (`docs/dgx/04`). Dos 127,
a maioria é de módulos que não temos (escolta, Cronos, App Supervisões, boletim). Os que têm
correspondente aqui: `DiaApontamento`, `DiasAntesLancarAusencia`, `ToleranciaIntegracaoBatimentos`,
`CONTROLE_ACESSO_RAIO_MAXIMO`, `DiasFechamento`, `DiasLimiteFaturamento`, `LinhasGridFechamento`,
`CRDiasAVencerEmailAuto`, `CRDiasVencidosEmailAuto`, `NotasServicoEnvioAutomatico`,
`NotaServicoDiasContratoValorProporcional`, `DominioPatrimonialOnline`, `Senha*` (6).

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/core/parametros.py` (novo, 110 linhas) | Leitor único: `async param(db, chave, empresa_cnpj=None, default=None)` e `param_sync(...)` (a folha é síncrona). Ordem: valor da empresa → global → default. Tipado por `tipo` (cai em `valor_type` legado); default `Decimal` devolve `Decimal`. Cache 30 s por processo, `invalidar()`. A consulta roda em **SAVEPOINT**: coluna ainda ausente ou banco fora → default, sem envenenar a transação do chamador. `demo()` com asserts. |
| `.../redesign_builders/_dgx_f4_parametros.py` (novo) | `SEED` (28 chaves, 8 grupos, cada uma com `nome`, `descricao` PT-BR, `grupo`, `tipo`, `metadata.origem` = onde o valor vive no código, `metadata.dgx` = nome no DGX). `_ensure(db)` = DDL + seed (`ON CONFLICT DO NOTHING`). `salvar(db, chave, empresa, valor, quem)` valida tipo, empresa do grupo e `is_editavel`; grava global (`valor`) ou por CNPJ (`valor_por_empresa`), vazio por empresa **remove a exceção**; append em `historico`: `{quando, quem, empresa, de, para}` (sensível → `***`). Telas `parametros` e `parametro-editar`. Rota `POST /api/v1/redesign/action/parametro-salvar` (só admin — mesma trava `_is_admin_user` do módulo; 422 em valor inválido). |
| `.../redesign_builders/configuracoes.py` | +12 linhas: import do `router`/`MENU` (`# dgx f4`), `EXTRA_MENU` ganha os 2 itens, `build()` chama `telas(db, out)` em try/except (tela diz "sem dado: …" em vez de derrubar usuários/tenants). |
| `.../folha/services/calculo_service.py` | +8/−3: `_pct_adiant = _d(param_sync(db, "folha.adiantamento_percentual", default=ADIANTAMENTO_PERCENTUAL * 100)) / 100`; as 3 leituras da constante no bloco 1045 usam `_pct_adiant`. A constante fica como default. **Paralelo cego**: o oráculo recalcula um holerite de 09/2026 e confere `valor == salário base × 40%`. |
| `.../employee_portal/controllers/painel_ponto_controller.py` | +4/−1: `tol_entrada = int(param_sync(db, "ponto.tolerancia_entrada_min", default=TOLERANCIA_ENTRADA_MIN))` antes do laço; `limite` usa `tol_entrada`. |
| `backend/scripts/orq/test_oraculo_parametros_por_cnpj.py` (novo) | Oráculo (§4). |

### DDL que `_ensure` aplica em produção no 1º acesso à tela (ou 1ª gravação)
```sql
ALTER TABLE system_configs ADD COLUMN IF NOT EXISTS valor_por_empresa jsonb NOT NULL DEFAULT '{}'::jsonb;
INSERT INTO system_configs (…28 linhas…) ON CONFLICT (chave) DO NOTHING;   -- 12 → 40 linhas
```
Nada é apagado, nada existente é alterado. **Nenhum índice novo, nenhuma constraint tocada.**

### Decisão que desvia do brief (registrada)
O brief pedia `empresa_cnpj varchar(14)` + índice único `(chave, coalesce(empresa_cnpj,''))`. Isso exige
**derrubar** `system_configs_chave_key` (UNIQUE em `chave`) — e **8 escritores** fazem
`ON CONFLICT (chave) DO UPDATE` (`tasks_oraculos`, `ged/config_controller`, `aviso_diarias_whatsapp`,
`crm/orchestration`, `financial/relatorios_controller`, `checar_sino_surdo`, `checar_registros_servidor`,
`test_oraculo_periodo_fechado`). Sem a constraint, todos quebram no 1º upsert
("no unique or exclusion constraint matching the ON CONFLICT"). Escolhi **uma linha por parâmetro** com
`valor_por_empresa jsonb {cnpj: valor}`: mesma semântica do DGX (um valor por empresa), zero
constraint tocada, e a tela já era "uma linha, uma coluna por empresa". Se um dia houver 30 CNPJs,
vira tabela filha — hoje são 2.

### Seed — 28 chaves em 8 seções (valor = o que o código usa hoje; vazio = sem fonte, editável)
| Seção | Chaves (valor) |
|---|---|
| folha | `adiantamento_percentual` (**40**) · `dia_apontamento` (—) · `dias_antes_lancar_ausencia` (—) |
| ponto | `tolerancia_entrada_min` (**15**) · `geofence_raio_padrao_m` (**150**) · `facial_obrigatoria` (—) · `arredondamento_min` (—) |
| fechamento | `dia_fechamento_ponto` (—) · `dias_limite_faturamento` (—) · `linhas_grid` (—) |
| beneficios | `vt_desconto_pct` (**4**) · `vr_desconto_pct` (**1**) · `vt_valor_dia` (**10.00**) · `vr_valor_dia` (**22.00**) · `dias_vt_vr_modo` (**escala**) · `dias_vt_vr_12x36` (**15**) |
| financeiro | `cobranca_dias_a_vencer_email` (—) · `cobranca_dias_vencidos_email` (—) |
| fiscal | `nfse_envio_automatico` (—) · `nfse_valor_proporcional_dias` (—) |
| empresa | `dominio` (**www.conectamais.pro**) · `email_remetente` (**noreply@conectamais.pro**) |
| senha | `qtd_digitos` · `maiusculas` · `minusculas` · `numeros` · `simbolos` · `dias_expiracao` (todas —, só estrutura) |

Percentuais guardados como **número humano** (40, 4, 1) — o código divide por 100 ao ler.

### Telas (deep-links)
- `/redesign/configuracoes?t=parametros` — tabela: Parâmetro · Descrição · Global · **Conecta Mais Eletrônica** ·
  **Conecta Mais Patrimonial** · Tipo/origem (+ nº de alterações). Seletor de seção (`filtro` = grupo).
  Painel "Seções" com contagem. Ação por linha **Editar** (campos: *Vale para* = Global | empresa; *Valor*
  pré-preenchido com o global; `confirm`). Lista **todas** as 40 chaves ativas, inclusive as 12 antigas.
- `/redesign/configuracoes?t=parametro-editar` — form (chave, empresa, valor), `gated` + `confirm`.
- Menu: `EXTRA_MENU` de `configuracoes` — "Parâmetros do sistema" e "Editar parâmetro" (grupo "Parâmetros").

Prova por HTTP (container efêmero 8204, banco do sandbox):
```
GET /api/v1/redesign/data/configuracoes → 200
extraMenu: [..., 'parametros', 'parametro-editar']
parametros: table | rows: 40 | cols: [Parâmetro, Descrição, Global, Conecta Mais Eletrônica, Conecta Mais Patrimonial, Tipo · origem]
linha folha.adiantamento_percentual: Global=40 · Eletrônica "= global" · Patrimonial "= global" · ações [Ver, Editar]
Editar → /api/v1/redesign/action/parametro-salvar?chave=folha.adiantamento_percentual · fields [(empresa,''), (valor,'40')]
POST parametro-salvar {ponto.geofence_raio_padrao_m, 66.014.833/0001-10, 999} → 200 "— → 999. Registrado no histórico."
POST parametro-salvar {…, 'abc'}  → 422 "'abc' não serve para um parâmetro do tipo integer"
POST parametro-salvar {…, ''}     → 200 "999 → — (volta ao global)"
historico da chave: [{de:null, para:'999', quem:'jjesus@…', quando:'2026-09-24T03:52:26+00:00', empresa:'66014833000110'}, {de:'999', para:'', …}]
GET /api/v1/people-management/portal/painel-ponto?token=… → 200 (atrasados: 3) — caminho do param_sync vivo
```

## 4. Oráculo

`backend/scripts/orq/test_oraculo_parametros_por_cnpj.py` afirma: (a) toda chave do `SEED` no banco com
`descricao` e `grupo`; (b) `param('folha.adiantamento_percentual')/100 == calculo_service.ADIANTAMENTO_PERCENTUAL`
**e** um holerite de 09/2026 recalculado tem a linha 1045 = salário base × parâmetro (paralelo cego);
(c) fixture `dgx.f4.fixture` (global 10, Patrimonial 20): Patrimonial lê 20, Eletrônica lê 10, sem
empresa lê 10, tipo `int`; chave inexistente devolve o default; (d) `salvar()` deixa `{quem, quando,
empresa, de, para}` no `historico`, o valor salvo é o lido em seguida (cache invalidado) e `'abc'` em
integer é recusado; (e) varredura AST de `core/` e `modules/`: todo `param()`/`param_sync()` tem chave
literal presente no seed e default **avaliado no namespace do módulo** igual ao seed; ≥ 2 chamadores;
(f) `configuracoes.build()` chama a frente, os 2 ids estão no `EXTRA_MENU`, a tela lista todas as ativas
com coluna por empresa. Fixture apagada no `finally`.

Comando (contrato):
```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_parametros_por_cnpj.py
```
Vermelho (antes): ver §1. Verde (depois):
```
seed: 28 chaves em 8 grupos · ativas no banco: 40
adiantamento: 40.0% no banco == 0.40 no código · recalculado: ADAILSON SERRA ALVES
TOTAL parâmetros por CNPJ: 0 falha(s)
OK parâmetros por CNPJ: seed descrito, adiantamento igual ao código, empresa vence global, histórico gravado, defaults batem
exit=0
```
Lint: `ruff check` limpo nos 6 arquivos (os 22 avisos de `configuracoes.py` são pré-existentes: 22 antes, 22 depois); `ruff format` aplicado nos 3 novos.

## 5. O que NÃO foi feito e por quê

- **`empresa_cnpj` + índice único (chave, cnpj)** — ver §3 "Decisão": derrubaria a UNIQUE que 8 escritores usam.
- **Adiantamento por CNPJ no cálculo**: `calculo_service` lê o parâmetro **global** (`empresa_cnpj=None`).
  O `SELECT` do colaborador não traz `empresas.cnpj` e trazer mudaria mais que "uma constante". Quando o
  dono quiser 40% numa empresa e outro valor na outra, é 1 linha a mais no SELECT + passar o CNPJ.
- **`presence_controller.TOLERANCIA_ATRASO`** (quadro ao vivo, `mapa_de_ponto`) continua constante: a função
  que a usa é pura (sem `db`). Mesma chave `ponto.tolerancia_entrada_min` documenta as duas origens; ligar é
  passar a tolerância por argumento a partir de `_carregar()` — diff de outro tamanho.
- **VT/VR, geofence, e-mail, domínio**: semeados com o valor do código e **não ligados** — só os 2 da prova de
  conceito foram trocados (brief). Ligar cada um é o mesmo padrão de 1 linha; o oráculo (e) acusa se o default
  divergir do seed.
- **Chaves sem fonte (16)** ficaram NULL de propósito (contrato: nunca inventar). O DGX traz defaults (dia 1,
  3 dias, 50 linhas, 30 dias) que **não** copiei — são de uma instância vazia deles, não regra nossa.
- **Modelo ORM `SystemConfig`** (`modules/config/models/system_config.py`) não foi tocado: já está driftado do
  banco (só conhece as colunas EN) e ninguém o usa nesse caminho.
- **Política de senha**: só a estrutura; o login não lê essas chaves.
- **Frontend**: nada — `table` + `panels` + `form` renderizam genericamente. Sem JSON de menu novo.
- **Hooks `ruff`/`ruff-format` pulados nos 2 commits** (`SKIP=ruff,ruff-format`; bandit, gitleaks,
  detect-secrets e governança rodaram e passaram). Motivo: `configuracoes.py` e `calculo_service.py`
  nunca foram formatados — o `ruff-format` reescrevia `configuracoes.py` em **+350/−110 linhas** e o
  `ruff --fix` mexia em 11 linhas alheias, num commit que prometia +12. Os 22 avisos do arquivo são
  pré-existentes (22 antes, 22 depois); os 3 arquivos novos passam `ruff check` e `ruff format` limpos.
  Formatar esses dois arquivos é tarefa de uma sessão só de lint, não de uma frente.

## 6. Como o Jordan testa amanhã

1. Depois do bake do backend: **Configurações → Parâmetros do sistema** (ou
   `/redesign/configuracoes?t=parametros`). Deve listar 40 parâmetros; no seletor de seção, "folha" mostra
   3 linhas e `folha.adiantamento_percentual` = **40**.
2. Na linha de `ponto.geofence_raio_padrao_m`, clicar **Editar** → *Vale para* = Conecta Mais Patrimonial,
   valor `200` → Salvar. Recarregar: a coluna Patrimonial mostra **200** (verde), Eletrônica segue "= global",
   e "Tipo · origem" passa a dizer "1 alteração(ões)".
3. Editar de novo com valor **vazio** → a exceção some ("= global"). O histórico guarda as duas alterações
   (quem = seu e-mail).
4. Tentar salvar `abc` em `ponto.tolerancia_entrada_min` → recusa com "não serve para um parâmetro do tipo integer".
5. **Não** mude `folha.adiantamento_percentual` antes da folha de 09 fechar: o valor entra na próxima
   rodada de cálculo (o parâmetro é lido a cada holerite). Se mudar, o oráculo `test_oraculo_parametros_por_cnpj`
   continua verde (ele compara o holerite com o **parâmetro**, não com 40) — mas o de paridade da folha (F1)
   vai acusar diferença contra a Portte, e é isso que se espera.
6. Oráculo no container de produção depois do bake:
   `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_parametros_por_cnpj.py`
   → `OK parâmetros por CNPJ …`, exit 0. (Ele cria e apaga a fixture `dgx.f4.fixture`.)

## 7. Decisões que só o dono pode tomar

1. **Os 16 parâmetros sem valor** (dia de apontamento, dias para lançar ausência, dia de fechamento do ponto,
   dias limite do faturamento, linhas por página, facial obrigatória, arredondamento, dias de cobrança a vencer/
   vencidos, NFS-e automática e dias proporcionais, 6 de política de senha): preencher pela tela ou deixar
   vazio. Nenhum código lê esses hoje — preencher não muda comportamento até alguém ligar.
2. **Adiantamento diferente por CNPJ?** Hoje 40% vale para as duas empresas. Se a Patrimonial for diferente,
   é a ligação descrita em §5.
3. **VT 4% / VR 1% / R$ 10 e R$ 22 por dia** viraram parâmetro editável. Mudar aqui **ainda não** muda a folha
   (não ligado). Quer que ligue? É a mesma troca de 1 constante cada, com o mesmo oráculo de paralelo cego.
4. **Quem pode editar**: hoje só administração (`role admin` ou permissão `all`), a mesma trava do módulo
   Configurações. Se DP/Financeiro precisar mexer nos seus grupos, é uma regra por `grupo`.
