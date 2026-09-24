# DGX U5 — Entrega de benefício em lote com período de apuração (24/09/2026)

Branch: `dgx/u5-entrega-beneficio` (worktree movida para a ponta de `fase5-hermes-camada-cognitiva` @ 7e297d134
antes de qualquer linha). Módulo: `dp` (folha/people_management + builder do DP). Testado SÓ no sandbox
staging, em modo efêmero (imagem `conecta-pro-backend:latest`, worktree montada em `/app:ro`, banco
`conecta_pro_staging`, container `teste-dgx-u5` na porta 8235 — parado e removido ao fim).
**Produção não foi tocada.** Paralelo cego: nada escreve em folha/holerite/pagamento.

---

## 1. Estado ANTES (medido 24/09/2026, staging = cópia de produção)

- O motor da frente 03 (`beneficio_ponto.calcular_competencia`) calcula VT/VR por COMPETÊNCIA (mês civil) e
  grava em `folha_beneficio_conferencia` (08/2026: 108 linhas · R$ 20.922 · 09/2026: 102 · R$ 22.228).
  `mapa_frequencia` só aceitava (ano, mês); `_horas_por_dia` lê o mês com margem de 1 dia.
- Não existia a entidade "entrega": nenhuma tabela dizia «a entrega X do benefício Y, referência MM/AAAA, foi
  apurada de A a B, tem N pessoas, total R$ T, foi aprovada por Q, gerou o arquivo F e o título P».
- Fechamento do ponto: nenhum mês fechado no staging (`time_sheets` 08 e 09/2026 só `calculado`;
  `gp_monthly_closings` vazio para 2026 ≥ 08) → toda apuração por apontamento é, hoje, provisória.
- `beneficio_tipos` (F3) com VT #1 e VR #2 ativos; `cct_benefit_configs`: VR SOLIDES R$ 22/dia, VT SINETRAM e
  SOLIDES R$ 10/dia. Coorte do motor: 50 ativos (+3 desligados dentro do período).
- Oráculo ANTES do código (vermelho):
  ```
  $ test_oraculo_u5_entrega_beneficio.py   (código-base, sem a frente)
  FALHOU: serviço folha/services/beneficio_entregas.py não importa: cannot import name 'beneficio_entregas' …
  TOTAL u5 entrega beneficio: 1                                                                    exit=1
  ```

## 2. O que o DGX tem (`docs/dgx/01`, "Entregas de Benefícios (lote)"; `DGX_T1_dp_rh.md` § Benefícios)

`/EntregasBeneficios` → `Salvar`: `idBeneficio`, `Referencia` (ex. `10/2026`), `PrevisaoInicio`/`PrevisaoFim`,
`idEntregaAnterior` / `idEntregaAnterior2`, `idApontamento` (Manual ou um apontamento) + `ApuracaoInicio`/
`ApuracaoFim`, `Status`. O T1 gravou a entrega 1 com "Funcionários 0" (colaborador sem contrato/alocação);
depois `GerarArquivoExportacao` (leiaute SPTrans) e a conta.

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/folha/services/beneficio_entregas.py` (novo, ~500 l.) | DDL idempotente (`_ensure`), `criar` (validação: tipo ATIVO VT/VR, `MM/AAAA`, janelas, anteriores do mesmo benefício, apontamento não termina no futuro), `apurar` (motor por janela; apaga e regrava os itens; `EntregaTravadaError` se aprovada), `editar_item` (apuração manual pessoa a pessoa), `aprovar`, `gerar_arquivo` (reusa `montar_arquivo_operador` da F03; grava em `UPLOADS_DIR/beneficio_entregas/`; status → `enviada`), `gerar_conta` (PayableService, idempotente por `payable_id`, NÃO paga). `__main__` = auto-checagem das réguas puras. |
| `backend/modules/people_management/folha/services/beneficio_ponto.py` (+40/−8) | `mapa_frequencia(..., periodo=(ini, fim))`: janela arbitrária que pode cruzar meses (`_meses`, horas lidas mês a mês e recortadas; 12x36 sem escala lançada = `dias_vt_vr` proporcional aos dias do mês na janela). **Sem `periodo` nada muda** — o oráculo da F3 (Σ\|Δ\| = 0 em 208 linhas) continua verde. `_dias_do_mes` apagado (ficou sem uso). |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_u5_entrega_beneficio.py` (novo, ~400 l.) | 3 telas + 6 ações (abaixo). |
| `departamento_pessoal.py` (+6) | plug `# dgx u5`: `router` no topo, `telas(db, out)` depois da F3 (abas no FIM de g-beneficios). |
| `_dp_grupos.py` (+3) | as 3 abas listadas no FIM de `g-beneficios` (só documentação da composição; g-ferias intocado). |
| `backend/scripts/orq/test_oraculo_u5_entrega_beneficio.py` (novo) | §4. |

**Regra do acerto** (a do motor, trocando "portal do mês anterior" por "entregas anteriores"):
`planejado` = dias previstos na janela de PREVISÃO (escala + regra do tipo: remover férias/afastados) ·
`trabalhado` = dias T/E na janela de APURAÇÃO (só apontamento) · `direito` = trabalhado ·
`recebido_anterior` = Σ `quantidade` da pessoa nas entregas anteriores 1 e 2 · `ajuste_ponto` = direito − recebido ·
`quantidade` = max(0, planejado + ajuste) · `total` = quantidade × unitário (R$/dia de `cct_benefit_configs`).
O acerto só é feito quando a janela de apuração tem o MESMO nº de dias que a soma das previsões das anteriores;
senão o item fica `janela_divergente` com a previsão pura (estado, nunca zero inventado). Sem anterior →
`sem_anterior`; janela sem ponto → `anterior_sem_ponto`; faltas > limite do tipo → `cortado_faltas`; manual →
`manual` (previsão pura, o DP corrige com o botão **Quantidade**). `sem_modalidade` / `sem_parametro` /
`sem_escala` / `sem_regra` ficam sem valor e fora do arquivo e da conta.
**Apuração definitiva × provisória**: por apontamento, `competencia_fechada` de cada pessoa em cada mês da janela;
alguém com mês aberto → `apuracao_definitiva = false` e o item diz «apuração provisória — mês aberto: 08/2026».

**DDL que `_ensure` aplica em produção no 1º acesso** (tela, cada ação e o oráculo chamam):
```sql
CREATE TABLE IF NOT EXISTS beneficio_entregas (id bigserial PK, beneficio_tipo_id bigint NOT NULL, referencia varchar(7) NOT NULL,
  previsao_inicio date NOT NULL, previsao_fim date NOT NULL, apuracao_modo varchar(12) CHECK (manual|apontamento) DEFAULT 'manual',
  apuracao_inicio date, apuracao_fim date, entrega_anterior_id bigint, entrega_anterior2_id bigint,
  status varchar(10) CHECK (rascunho|apurada|aprovada|enviada|paga) DEFAULT 'rascunho', apuracao_definitiva boolean,
  total numeric(12,2), quantidade_pessoas integer, arquivo_operador_path text, payable_id uuid, observacao text,
  criado_por varchar(120), aprovado_por varchar(120), aprovado_em timestamptz, apurado_em timestamptz, created_at, updated_at);
CREATE TABLE IF NOT EXISTS beneficio_entrega_itens (id bigserial PK, entrega_id bigint NOT NULL REFERENCES beneficio_entregas ON DELETE CASCADE,
  employee_id uuid NOT NULL, operadora varchar(20), planejado int, trabalhado int, recebido_anterior int, direito int, ajuste_ponto int,
  quantidade int, unitario numeric(12,2), total numeric(12,2), estado varchar(24) NOT NULL, observacao text, UNIQUE (entrega_id, employee_id));
CREATE INDEX IF NOT EXISTS ix_beneficio_entregas_tipo_ref ON beneficio_entregas (beneficio_tipo_id, referencia);
```
Sem seed. Nenhuma tabela existente alterada.

**Telas** (abas no fim de `g-beneficios`; deep-link `/redesign/departamento-pessoal?t=<id>`):

| id | tipo | o que mostra / faz |
|---|---|---|
| `beneficio-entregas` | table | Entrega (#id · ref) · Benefício · Previsão · Apuração (manual / apontamento DD/MM–DD/MM) · Anteriores · Pessoas · Total · Status · Apuração (definitiva/provisória) · Arquivo · Conta · Por. Filtro por status. Ações por linha conforme o estado: **Apurar** (rascunho/apurada), **Aprovar** (apurada), **Arquivo** (aprovada+; escolhe operadora), **Conta** (aprovada/enviada sem título; `gated`). CTA "Nova entrega". |
| `beneficio-entrega-nova` | form | os campos do `/EntregasBeneficios`: Benefício (só tipos ATIVOS VT/VR), Referência MM/AAAA, previsão início/fim (date), Entrega anterior 1 e 2 (select das entregas existentes), Apuração (manual/apontamento), apuração início/fim, observação → `beneficio-entrega-salvar`. |
| `beneficio-entrega-itens` | table | filtro por entrega (`#id · VR 09/2026 · status`): Colaborador · Oper. · Plan. · Trab. · Receb.ant · Direito · Ajuste (±) · Qtd · Unit. · Total · Estado · Obs. Ação **Quantidade** (só rascunho/apurada, item com unitário). |

**Ações** (`POST /api/v1/redesign/action/…`): `beneficio-entrega-salvar`, `beneficio-entrega-apurar?entrega_id=`,
`beneficio-entrega-aprovar?entrega_id=`, `beneficio-entrega-arquivo?entrega_id=` (payload `operadora`),
`beneficio-entrega-conta?entrega_id=` (gated), `beneficio-entrega-item-editar?item_id=`. `ValueError` → 422,
`EntregaTravadaError` → 409. Medido na porta 8235 (fixtures `FIXTURE DGX U5`, apagadas):
```
GET data/departamento-pessoal → 200 · abas g-beneficios: 18 (… beneficio-entregas, beneficio-entrega-nova, beneficio-entrega-itens)
salvar ref 13/2026 → 422 "Referência no formato MM/AAAA" · salvar A (VR 08/2026 manual) → 200 #7 · apurar A → 53/53 R$ 18.832,00
salvar B (VR 09/2026, apontamento 01/08–31/08, anterior #7) → 200 #8 · aprovar B sem apurar → 409
apurar B → 200: 51/51 R$ 23.056,00 — apuração provisória (mês aberto) {ok: 49, anterior_sem_ponto: 2}
tela entregas: linha #8 … 'apurada' 'provisória' — ações [Ver, Apurar, Aprovar] · tela itens: 51 linhas no filtro "#8 · VR 09/2026 · apurada"
editar item qtd 'abc' → 422 · aprovar B → 200 · reapurar B → 409 · editar item de B → 409
arquivo VR/sinetram → 422 "VR só sai pelo Sólides" · arquivo solides → 200 SOLIDES_entrega8_…_51_ConectaMais.txt (0 avisos)
conta → 200 5cc2b5b4… R$ 23.056,00 "Nada foi pago" · conta 2ª vez → 200 "já existia" mesmo id
linha #8 final: 'enviada' · arquivo preenchido · conta 5cc2b5b4… — ações [Ver, Arquivo]
checar_tela_sem_porta (QA_API=8235): TOTAL 15 sem porta — nenhum de benefício/entrega (os 15 são anteriores)
```

## 4. Oráculo — `backend/scripts/orq/test_oraculo_u5_entrega_beneficio.py`

Afirma (fixtures próprias): (1) serviço/builder importam e `dp.build()` chama `_telas_u5`; tabelas existem.
(2) apurar duas vezes: mesmo nº de itens, nenhum `employee_id` repetido, mesmo total. (3) `total` == Σ itens e
`quantidade_pessoas` == count(total) — por SQL. (4) item a item em `ok`: `recebido_anterior` == quantidade da MESMA
pessoa na entrega anterior (recontado), `ajuste` == direito − recebido, `quantidade` == max(0, planejado + ajuste),
`total` == qtd × unitário; exige ≥ 1 `ok`. (5) contra-prova: `trabalhado` pela janela 01/08–31/08 == `trabalhado_anterior`
que o motor guardou em 09/2026 (VR). (6) aprovada: reapurar → 409, editar item → 409, md5 dos itens idêntico.
(7) dois `gerar_conta` → um `payable_id`, uma linha em `payable_accounts`, `gross_value` == total, status `pendente`.
(8) provisória: SQL próprio em `time_sheets`/`gp_monthly_closings` → `apuracao_definitiva` coerente e itens avisando.
(9) arquivo gerado, caminho guardado, status `enviada`. Fixtures (2 entregas, itens em cascata, 1 título, 1 arquivo) apagadas.
```
ANTES  → FALHOU: serviço … não importa · TOTAL u5 entrega beneficio: 1 · exit=1
DEPOIS → A #3: 53 pessoa(s) com valor / 53 · estados {'manual': 53}
         B #4: 51 / 51 · estados {'ok': 49, 'anterior_sem_ponto': 2} · acerto True · definitiva False
         (4) itens ok conferidos: 49 · (5) pessoas comparadas com o motor por mês: 11
         (8) pessoas com 08/2026 aberto: 51 · definitiva=False · itens provisórios 51
         (7) título 081020c6… 23056.00 status pendente · (9) SOLIDES_entrega4_…_51_ConectaMais.txt: 60 linha(s), 0 aviso(s)
         fixtures restantes: 0 · TOTAL u5 entrega beneficio: 0 · OK … · exit=0
test_oraculo_beneficio_regra_e_dado.py → competências comparadas: 2 · linhas comparadas: 208 · Σ|Δ total|: R$ 0.00 · TOTAL desvios: 0 · exit=0
test_oraculo_beneficio_fecha.py (-v /opt/conecta-pro/uploads:/app/uploads:ro) → casadas no motor: 23 · divergentes: 0 · OK · exit=0
```
Comandos: receita do `CONTRATO_AGENTE.md` (`--tmpfs /app/logs:rw,mode=1777` — sem `mode` o app não escreve
`app.log` porque roda sem root e o container morre com exit 3; e `-e SMTP_*=` vazios).

## 5. O que NÃO foi feito e por quê

- **`calcular_competencia` não ganhou `periodo`** — o motor por mês (e o `_previsao` dentro dele) continua intocado;
  a U5 reimplementa em ~30 linhas o laço por pessoa (mesmos estados) porque o acerto é contra ENTREGAS, não contra o
  portal. Diff no motor limitado a `mapa_frequencia(periodo=)` + `_meses`.
- **Status `paga` não é atingido por nada aqui**: quem paga é o Financeiro (título). Marcar a entrega como paga quando
  o título for baixado é um gancho no `PayableService` — fora do módulo declarado.
- **Uma conta por entrega**, no `COND_EMPRESA`, fornecedor = nome do tipo. VT com SINETRAM + Sólides na mesma entrega
  vira UM título; separar por operadora exige decidir o fornecedor de cada uma (§7).
- **Arquivo**: mesmo gerador da F03 (layout espelho do relatório, "oficial a confirmar"); SINETRAM continua exigindo
  nº de cartão conhecido (vem do último `portal_cartao` importado).
- **Sem excluir entrega** pela tela (rascunho errado fica; apagar é SQL). Sem edição da entrega depois de criada.
- **Sem "Funcionários 0" por alocação**: a coorte é a do motor (vínculo no período), não "alocado em posto".
- **`limite_faltas` usa as faltas da janela de apuração** (não do mês anterior fechado, como no motor por competência) —
  na entrega a janela É o período conferido.
- Sem Telegram, sem `alembic/`, sem `frontend/`, sem `checar_regressao.py`, sem MCP/Hermes, sem produção.

## 6. Como o Jordan testa amanhã (depois do bake)

1. DP → Benefícios & Reembolsos → **Nova entrega**: Vale Refeição, referência `08/2026`, previsão 01/08/2026–31/08/2026,
   apuração **Manual** → "Entrega #N criada". Aba **Entregas (lote)** → linha #N `rascunho` → **Apurar** → `apurada`,
   ~53 pessoas, ~R$ 18.832 (previsão pura). Aba **Itens da entrega** → filtro `#N · VR 08/2026` → **Quantidade** numa
   pessoa → total da entrega refaz.
2. **Nova entrega**: VR, `09/2026`, previsão 01/09–30/09, **Pelo apontamento** 01/08/2026–31/08/2026, Entrega anterior 1 = #N
   → **Apurar** → "apuração provisória (mês aberto)"; itens `ok` com Receb.ant = quantidade de #N, Ajuste = Direito − Receb.ant.
   (Depois de fechar 08/2026 em Ponto & Jornada, reapurar → "definitiva".)
3. **Aprovar** → `aprovada`; **Apurar** some da linha; **Quantidade** some dos itens. **Arquivo** → Sólides → texto no
   resultado, nome na coluna Arquivo, status `enviada`. **Conta** → título no Financeiro → Contas a pagar (pendente);
   clicar de novo → "já existia".
4. Oráculo em produção: `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_u5_entrega_beneficio.py`
   → `TOTAL u5 entrega beneficio: 0` (cria e apaga as próprias fixtures; grava o arquivo num tmp).

## 7. Decisões que só o dono pode tomar (e um achado do motor)

- **ACHADO no motor da F03 (não é da U5, mas a U5 o expõe)**: em `beneficio_ponto._horas_por_dia` o dia do turno é o
  dia da ENTRADA de cada par de batidas. No 12x36 NOTURNO com intervalo (19:00 → 02:00 · 03:00 → 07:00) o plantão vira
  DOIS pares em DOIS dias civis (D 19:00–02:00 e D+1 03:00–07:00), e o D+1 conta como dia trabalhado à parte —
  ADAILSON SERRA ALVES aparece com **31 dias trabalhados em 08/2026** (T 15 + E 16) para 15 plantões. Medido no
  staging: 31 datas distintas com batida, 63 batidas, todas nesse padrão. O motor por mês guarda o mesmo 31 em
  `trabalhado_anterior` (é por isso que o item 5 do oráculo bate). Na entrega por apontamento isso vira
  **ajuste +16 dias** para os noturnos — errado em dinheiro se alguém aprovar. Corrigir (colar o segmento pós-intervalo
  ao plantão que começou na véspera) é regra do motor da F03 e exige re-medir o oráculo da F3, cujas linhas guardadas
  carregam o defeito.
  **Até lá: não aprovar entrega por apontamento de escala noturna.**
- Janela de apuração ≠ soma das previsões anteriores: hoje vira `janela_divergente` (previsão pura). Ratear por dia
  seria inventar; se a Pyetra quiser entregas 16→15, basta criar as entregas com previsão 16→15 e a janela casa.
- Conta a pagar por operadora (SINETRAM boleto × Sólides PIX) ou uma por entrega? Fornecedor cadastrado para cada?
- Vencimento do título = 1º dia da previsão (ou hoje, se já passou): é a data em que o benefício tem de estar na mão.
- Coorte: todo vínculo no período (motor) ou só alocados em posto (DGX "Funcionários 0")?
