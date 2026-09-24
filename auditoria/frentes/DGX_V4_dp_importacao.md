# DGX V4 — DP: falhas de importação, exportar/imprimir colaboradores, importar apontamentos CSV

**Data:** 24/09/2026 · **Branch:** `dgx/v4-dp-importacao-exportacao` (sobre `fase5-hermes-camada-cognitiva`
@ `d76e1df3d`) · **Módulo:** dp · **Porta de teste:** 8244, container `teste-dgx-v4` (parado ao fim).

Cobre `docs/dgx/lacunas/dp_rh.md` **#8** (falhas de importação) e **#22** (Colaboradores/Index:
Exportar · Imprimir · contadores por status) e `docs/dgx/lacunas/ponto.md` **item 56** (importar
apontamentos CSV).

---

## §1 Estado antes (medido no sandbox, 24/09/2026)

| Fato | Medida |
|---|---|
| `dp_importacao_falhas` | `to_regclass` → **NULL** (não existia) |
| Erro de importação de cadastro | só no JSON da resposta, **cortado em 20 CPFs** (`cadastro_import_service.py`) |
| Erro do sync Sólides | `erros[]` na resposta; linha sem vínculo em `solides_employees` era `continue` **mudo** |
| Erro da folha analítica (Portte) | `sem_cadastro[]` na resposta do dry-run, que ninguém guarda |
| Erro do AFD de relógio | `ponto_integracoes_batimentos.erros` (jsonb) — resumo por execução, sem dono |
| Export de colaboradores | **nenhum** endpoint (nem Excel, nem CSV, nem PDF) |
| Contadores por status na tela `funcionarios` | só `"63 ativos"` (um número, `status='ativo'`) |
| Importar apontamentos em lote | só evento coletivo (F6): **uma** rubrica para um filtro de gente |
| `employees` por status | ativo 63 · inativo 20 · demitido 11 · pj_ativo 7 · afastado_inss 1 · candidato 1 · suspenso 1 |
| `employees` com `is_homologacao` | 14 |
| `hr_payslips` | 51 `draft` em 09/2026 · 51 `published` em 07/2026 |
| `rubricas_folha` ativas | 35 |

## §2 O que o DGX tem

- `/view/falhasImportacaoEmpregados` (`POST /api/RH/FalhasImportacaoEmpregados/filtro`): Data ·
  Identificador origem · Nome · RE · Motivo, com **Não resolvido / Resolvido (incluído manualmente)**.
- `/Colaboradores/Index`: **Exportar · Imprimir** (`ListagemReport` PDF/Excel/Word está em TODA
  tela da DGX) e a faixa de contadores Ativo/Inativo/Afastado/Demitido/Falecido/Férias/Suspenso/Ausente.
- `/Apontamentos/Lote/{id}` → **Importar** (CSV `Matrícula, Valor, Referência[, Evento]`, com
  opção de substituir).

## §3 O que foi feito

### Arquivos novos
| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/hr/services/importacao_falhas.py` | A fila: DDL idempotente, `registrar`/`registrar_sync`, `resolver`, `ignorar` |
| `backend/modules/people_management/hr/services/colaboradores_export.py` | Contadores + linhas + CSV/XLSX/PDF (réguas **importadas**) |
| `backend/modules/people_management/folha/services/apontamentos_csv.py` | Parser + validação + gravação pelo caminho de «Apontar» |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_v4_dp_importacao.py` | Telas, ações e endpoints de documento |
| `backend/scripts/orq/test_oraculo_v4_dp_importacao.py` | O oráculo |

### Arquivos tocados (diff mínimo, dentro do `except`/`continue` que já existia)
| Arquivo | Linhas | O quê |
|---|---|---|
| `hr/services/cadastro_import_service.py` | +10 | CPF sem colaborador e exceção por linha → fila (origem `planilha`) |
| `folha/services/folha_analitica_importer.py` | +14 (o resto do diff é o `ruff format` do pre-commit, que nunca tinha passado por este arquivo) | `sem_cadastro` → fila (origem `portte`); `commit` passa a ser incondicional (no dry-run só há falhas para gravar) |
| `hr/services/vacation_service.py` | +14 | `employeeId` sem vínculo em `solides_employees` e exceção por absence → fila (origem `solides`) |
| `ponto/integracao_batimentos.py` | +10 | `resumo["erros"]` → fila (origem `afd`) |
| `redesign_builders/departamento_pessoal.py` | +6 | `include_router(_r_v4)` + `telas(db, out)` no fim do `build()` |
| `redesign_builders/_dp_grupos.py` | +12 | Abas no **FIM** de `g-visao` e `g-folha` + `# fmt: off` no módulo |
| `scripts/orq/test_oraculo_integracao_batimentos.py` | +7 | O `_limpar` da T2 passa a apagar as falhas `afd` da fixture (efeito colateral da minha mudança) |

### DDL que o `_ensure` aplica em produção no 1º acesso
```sql
CREATE TABLE IF NOT EXISTS dp_importacao_falhas (
  id serial PRIMARY KEY, origem varchar(20) NOT NULL,
  executada_em timestamptz NOT NULL DEFAULT now(),
  identificador_origem varchar(160) NOT NULL DEFAULT '',
  nome varchar(200), matricula varchar(40), cpf varchar(20),
  motivo text NOT NULL, dados jsonb,
  status varchar(20) NOT NULL DEFAULT 'nao_resolvido',
  resolvido_por varchar(120), resolvido_em timestamptz, employee_id uuid,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS dp_importacao_falhas_chave
  ON dp_importacao_falhas (origem, identificador_origem, md5(motivo));
CREATE INDEX IF NOT EXISTS dp_importacao_falhas_status ON dp_importacao_falhas (status, origem);
```
Nenhum DROP/DELETE/UPDATE em dado que a frente não criou.

### Telas — deep-link `/redesign/departamento-pessoal?t=<id>`
| id | Grupo | O quê |
|---|---|---|
| `importacao-falhas` | `g-visao` (fim) | Fila com filtro Origem/Situação e ações **Resolver** (liga a um colaborador **ou** «incluí manualmente») e **Ignorar** (motivo obrigatório, mín. 5 caracteres) |
| `folha-apontamentos-importar` | `g-folha` (fim) | Form multipart: modo «Só validar» / «Importar» + CSV |
| `funcionarios` | `g-visao` (já existia) | Ganhou a faixa de contadores no cabeçalho e 4 botões `doc` |

> **`# fmt: off` no `_dp_grupos.py`:** o `ruff format` do pre-commit explodia os itens em uma linha
> por campo — 323 linhas de diff num arquivo que as CINCO frentes da onda 4 editam ao mesmo tempo,
> e conflito garantido em todas. O arquivo é dado escrito à mão, uma linha por grupo; o formatador
> não o deixa mais legível. Os consumidores (`test_aba_declarada_nasce`, os oráculos T1/F6/U2/F1)
> importam `GRUPOS` como Python, não por regex — mas o custo de merge é real e evitável.

> A tela `funcionarios` de verdade vive **dentro da aba** de `g-visao`: depois de `montar_grupos`,
> `out["funcionarios"]` é o stub `moved()`. Decorar o stub não muda nada e não avisa ninguém —
> foi o primeiro tiro desta frente, e `_tela_funcionarios()` existe por causa disso.

### Endpoints
- `GET /api/v1/redesign/colaboradores/export?formato=xlsx|csv&status=&condominio=&funcao=`
- `GET /api/v1/redesign/colaboradores/lista/pdf?status=&condominio=&funcao=` (timbrado, paisagem)
- `POST /api/v1/redesign/action/importacao-falha-resolver` · `…/importacao-falha-ignorar`
- `POST /api/v1/redesign/action/folha-apontamentos-importar` (multipart)

Todos com gate `module:dp`. `status` aceita `ativo` (padrão: vínculo vivo), `todos`, `afastado`,
`ferias`, `inativo` ou um status cru de `employees`.

### Decisões que a frente respeita
1. **Réguas importadas, nunca recriadas.** `identidade.SEM_VINCULO`, `mapa_de_ponto.COORTE` e
   `coorte_ponto.SQL_NAO_AUSENTE_HOJE` entram por `import`. «Ausente hoje» é literalmente a
   negação de `SQL_NAO_AUSENTE_HOJE` dentro da coorte do ponto.
2. **Paralelo cego no dinheiro.** O CSV de apontamentos **não escreve rubrica nem valor**: cada
   linha válida vira `hr_payslips.contest_reason` + `contested_at` pelo MESMO
   `rd_action_folha_apontamento` que a tela «Apontar» e o evento coletivo da F6 usam. Nenhum
   valor calculado muda. Competência com folha `published` → **409**.
3. **LGPD.** CPF **sempre mascarado** no PDF (`000.***.***-00`); completo no Excel/CSV só para
   admin (`role == 'admin'` ou `*`/`all` nas permissions) — a mesma régua de `module_scope`.
4. **Idempotência da fila.** Chave `(origem, identificador_origem, md5(motivo))`. Rerodar a mesma
   importação com o mesmo problema atualiza `executada_em`; não cria linha. Um problema que
   voltou depois de «resolvido» **reabre** como `nao_resolvido` (`ignorado` fica ignorado).
5. **`registrar` nunca levanta.** Uma falha de LOG não pode derrubar a importação que ela estava
   registrando — erro vira `logger.warning`.
6. **Contador com nome honesto.** «Ativo» = vínculo vivo **fora** os cadastros de homologação
   (59–61 no sandbox), e o cabeçalho diz isso em texto, porque a mesma tela já mostrava
   «63 ativos» (`status='ativo'`, que inclui os 14 de homologação). Dois números com a mesma
   palavra e sem explicação é como se repete em reunião um número que ninguém reconferiu.

## §4 Oráculo

`backend/scripts/orq/test_oraculo_v4_dp_importacao.py` — afirma (a) falha gravada 1x mesmo
importando 2x · (b) `resolver` liga ao colaborador e recusa id inexistente · (c) linhas do export
== régua de vínculo recontada por SQL próprio · (d) PDF `%PDF` e XLSX `PK`, CPF mascarado com
`admin=False` · (e) cada contador == recontagem própria (num único snapshot `REPEATABLE READ`) ·
(f) CSV 2 bons + 1 ruim → 2 apontamentos e 1 falha, e «só validar» não escreve **nada** ·
(g) competência publicada → 409 sem gravar. Fixtures `FIXTURE DGX V4` apagadas ao fim.

```bash
WT=<worktree>; ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
  --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \
  -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
  -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
  conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_v4_dp_importacao.py
```

**VERMELHO** (com os três serviços novos removidos do disco — o estado de ontem):
```
  File "/app/scripts/orq/test_oraculo_v4_dp_importacao.py", line 103, in main
    from modules.people_management.folha.services import apontamentos_csv
ImportError: cannot import name 'apontamentos_csv' from 'modules.people_management.folha.services'
```

**VERDE** (duas rodadas seguidas, para provar que não pisca com o sandbox compartilhado):
```
TOTAL desvios: 0
OK V4: fila de falhas idempotente e resolvível · export/PDF com a régua de vínculo e CPF mascarado ·
contadores recontados · CSV de apontamentos pelo caminho de «Apontar», 409 em competência publicada
```

**Vizinhos, depois da mudança:**
```
TOTAL dgx t1: 0 falha(s)           → OK dgx t1: foto resolve no crachá, ficha bate com o SQL, …
TOTAL dp complementos: 0 falha(s)  → OK dp complementos: dependentes na fonte da folha, …
TOTAL desvios: 0                   → OK integração de batimentos: parser 1510/671, idempotente, …
```

**QA por HTTP (porta 8244, container parado ao fim):**
```
GET /redesign/data/departamento-pessoal                      → 200; abas no FIM de g-visao e g-folha
GET /redesign/colaboradores/export?formato=xlsx              → 200, 19.369 bytes, mime xlsx
GET /redesign/colaboradores/export?formato=csv               → 200, 60 linhas (1 cabeçalho + 59)
GET /redesign/colaboradores/lista/pdf                        → 200, 44.938 bytes, %PDF
GET /redesign/colaboradores/lista/pdf?status=todos&funcao=…  → 200, 42.030 bytes (o filtro filtra)
POST /action/folha-apontamentos-importar (simular=true)      → 200, 1 válida / 2 recusadas, 0 gravado
POST /action/folha-apontamentos-importar (07/2026 publicada) → 409
POST /action/importacao-falha-resolver                       → 200, status resolvido_manual + employee_id
POST /action/importacao-falha-ignorar (motivo "x")           → 400 (motivo mín. 5 caracteres)
```
Duas linhas de QA criadas na fila foram apagadas; `SELECT count(*) FROM dp_importacao_falhas` = 0.

**Defeito que o QA por HTTP pegou e o verde do oráculo não pegava:** «Só validar» respondia
*«SIMULAÇÃO — nada gravado»* e deixava 2 pendências na fila. Corrigido (a prévia agora dá
`rollback`), e o oráculo ganhou a afirmação que cobre isso.

## §5 O que NÃO foi feito

1. **Word (`.doc`) no export.** A DGX oferece PDF/Excel/**Word** em toda listagem. Excel e PDF
   cobrem o uso real (contador e papel); um terceiro formato é mais um caminho para manter.
2. **Export das outras telas do DP.** A DGX tem `ListagemReport` em TODAS. Aqui só
   `funcionarios` ganhou botão — é a lista que a Pyetra pede. Generalizar isso é uma fundação
   (um `doc` universal no `tbl`), não uma frente.
3. **Filtro de origem/status gravado na URL da tela.** Os filtros existem como facetas
   (`filtros` por linha, que o front agrupa); não há `?origem=&status=` na tela.
4. **Fila de falhas para importadores fora do DP.** `afd_records` cru, importadores do fiscal e
   do financeiro seguem como estavam. A tabela é genérica o suficiente, mas ligar cada um é
   mudança no módulo do dono, não aqui.
5. **«Falecido» nos contadores.** A DGX tem o status; `employees.status` da casa não. Inventar a
   coluna para completar a faixa seria fabricar um número.
6. **Escrever rubrica/valor de verdade a partir do CSV.** É caminho de dinheiro: exigiria um
   oráculo de igualdade contra o motor de folha atual (Σ|Δ| = 0 nos holerites publicados). Ver §7.
7. **Coluna «Evento» do CSV da DGX como opcional.** Aqui `rubrica` é obrigatória — 5 colunas
   fixas, sem modo «substituir».
8. **Reprocessar a importação a partir da fila.** Resolver/Ignorar fecham a pendência; não há
   botão «tentar de novo» que releia o arquivo (o arquivo não é guardado).

## §6 Como o Jordan testa amanhã

1. **Contadores e export** — DP → *Visão geral* → aba **Funcionários**. O cabeçalho agora abre com
   `Ativo: N · Inativo: N · Demitido: N · Suspenso: N* · Afastado: N* · Férias: N* · Ausente hoje: N*`.
   Clique em **Exportar (Excel)** → abre no Excel com 36 colunas (CPF completo, porque você é admin).
   Clique em **Imprimir (PDF)** → uma folha paisagem timbrada, CPF mascarado, com o resumo no rodapé.
   **Excel — quadro inteiro** traz também demitidos e inativos (é o que o contador pede).
2. **Falhas de importação** — DP → *Visão geral* → aba **Falhas de importação**. Deve estar vazia
   hoje. Para vê-la encher: *Visão geral* → **Importar cadastro**, suba um CSV `cpf;rg` com um CPF
   que não existe. Volte na aba: a linha aparece como **Não resolvido**. Clique **Resolver** e
   escolha o colaborador certo (ou deixe «resolver sem ligar» se você já cadastrou na mão);
   ou **Ignorar**, que exige o motivo.
3. **Importar apontamentos** — DP → *Folha de pagamento* → aba **Importar apontamentos (CSV)**.
   Monte um arquivo assim (uma linha por lançamento), com a competência **aberta** (09/2026):
   ```
   matricula;rubrica;referencia;valor;competencia
   85;0010;12;340,50;09/2026
   ```
   Deixe o modo em **Só validar** e clique Importar: o resultado mostra quantas linhas passaram e
   por que as outras não. Nada é gravado nesse modo. Depois troque para **Importar**: cada pessoa
   ganha um apontamento no holerite rascunho (o mesmo que aparece em *Não conformidades*) — o
   valor da folha **não muda**, você é que decide ao fechar. Tente com 07/2026 (publicada): recusa
   com 409, como deve.

## §7 Decisões que só o dono pode tomar

1. **O CSV deve LANÇAR na folha, ou só apontar?** Hoje aponta (paralelo cego). Se a Pyetra quer
   que `0010;12;340,50` vire hora extra de verdade no holerite, é mudança no motor de cálculo,
   com oráculo de igualdade antes. Diga e vira uma frente própria.
2. **Quem resolve a fila?** A tela é do DP inteiro (`module:dp`). Se isso é trabalho da Pyetra e
   só dela, dá para escopar — mas aí ninguém cobre as férias dela.
3. **Falha antiga expira?** Hoje a fila cresce para sempre. Um «arquivar automático depois de N
   dias resolvido» só faz sentido quando você souber quantas linhas por mês ela recebe de verdade.
4. **CPF completo no Excel para quem não é admin?** Hoje só admin. Se a Pyetra (`module:dp`, não
   admin) precisar mandar a planilha completa ao contador, é uma linha — mas é decisão de LGPD,
   não minha.
5. **Os 14 cadastros de `is_homologacao`** ficam fora de «Ativo» de propósito. Se você quiser que
   apareçam como um contador próprio na faixa, digo e acrescento.
