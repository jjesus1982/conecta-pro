# DGX F2 — CCT como DADO: Sindicato → Funções → Eventos/Benefícios por função → Municípios (24/09/2026)

**Branch:** `dgx/f2-cct-como-dado` (base `c7077dbb6`) · **Módulo:** folha (serviço) + telas do DP · **Sessão:** agent-f2
**Paralelo cego.** Nada aqui muda holerite, `calculo_service.py`, `employees` ou `rubricas_folha`. Produção só leitura.

## 1. Estado antes (medido no sandbox = cópia de produção, 24/09)

- Sindicato: **texto** em `cct_convencoes.sindicato_trabalhadores` ("SINDECOMPRESTS", CNPJ 00.444.514/0001-36,
  AM000613/2025, 01/01/2026–31/12/2026, Manaus/AM). Sem entidade, sem vínculo por id.
- Funções: `cct_cargos` = **51** cargos com piso e `adicional_tipo` (3 `periculosidade_30`, 4 `insalubridade_10`,
  1 `adicional_10`, 43 sem). Nenhuma tabela dizia **quais rubricas** cada função recebe nem **quais benefícios**.
- Regras por função em Python: `calculo_service.py` (0015 periculosidade, 0016 insalubridade, 0018 ronda 15%,
  0020 noturno pela escala, 0021 hora reduzida, 0030/0031 intrajornada, 0090 DSR só sobre HE) e
  `modules/cct/models/schedule.AdicionaisCCT` (20 / 50 / 100 / 15 / 30 / 10 %). Adicionais são **por funcionário**
  (`employees.periculosidade_percentual`, `insalubridade_percentual`, `adicional_ronda_percentual`), não por cargo.
- Benefícios: `cct_beneficios` = 8 linhas (6 obrigatórios), sem vínculo a função.
- Municípios: `cct_convencoes.municipio = 'Manaus'` (um campo texto). Sem tabela.
- Telas do DP: `cct-conformidade` (só salário × piso), `beneficios-cct`, `novo-beneficio-cct`. MCP `tabela_salarial_cct`/
  `beneficios_cct` leem `cct_cargos`/`cct_beneficios` via `cct_service.py` (continuam valendo — não mudei a fonte deles).
- Ativos CLT (sem homologação/PJ): **50**; **5 sem `cct_cargo_id`** (fora de toda conferência — §7).
- Holerite **09/2026: 0 visíveis** (51 em `draft`, fonte conecta). Última competência visível: **07/2026** (48 publicados, 45 de ativos com função).

Oráculo VERMELHO (sandbox, antes de qualquer código):
```
$ python3 /app/scripts/orq/test_oraculo_cct_como_dado.py
FALHOU: CCT ainda não é dado — faltam tabelas ['cct_sindicatos', 'cct_funcao_eventos', 'cct_funcao_beneficios', 'cct_municipios'] e a coluna cct_convencoes.sindicato_id
TOTAL cct_como_dado: 1 vermelho
exit=1
```

## 2. O que o DGX tem (docs/dgx/01 e 09)

`Sindicatos` (Nome, NomeReduzido, Endereço, Contato, Telefone, Tipo LABORAL/PATRONAL) e a árvore por API:
`sindicatoFuncoes`, `SindicatoFuncaoEventos` (função → evento com razão/razão noturna), `SindicatoFuncaoBeneficios`,
`sindicatoMunicipios` — tudo `filtro` (POST) e `{id}`. A função carrega SEUS eventos e SEUS benefícios; o município
diz onde vale. É essa árvore que virou tabela aqui.

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/folha/services/cct_como_dado.py` (novo) | DDL idempotente + seed (`ensure(db)`), de-para `HOLERITE_PARA_RUBRICA`, `funcoes_sem_evento(db)` para a conformidade. |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_f2_cct.py` (novo) | 5 telas + 1 form + 7 ações `POST /api/v1/redesign/action/cct-…`; aviso na `cct-conformidade`. |
| `backend/scripts/orq/test_oraculo_cct_como_dado.py` (novo) | Oráculo (a)(b)(c)(d) — §4. |
| `backend/scripts/orq/_f2_ensure.py` (novo) | Aplica DDL/seed sem abrir tela (o que o 1º acesso ao DP faz). |
| `_dp_grupos.py` | Grupo novo **g-cct «Sindicato & CCT»** em `GRUPOS` + `MENU` (6 abas). |
| `departamento_pessoal.py` | 2+1 linhas `# dgx f2` (router + `telas(db, out)` ANTES de `montar_grupos`) e item `g-cct` em `EXTRA_MENU` (porta no menu sem tocar `frontend/`). |

### DDL que `ensure()` aplica em produção no 1º acesso ao DP (tudo `IF NOT EXISTS` / `ON CONFLICT DO NOTHING`)
- `cct_sindicatos` (nome UNIQUE, sigla, cnpj, uf, data_base, categoria, site, contato, tipo, ativo, origem_regra)
- `ALTER TABLE cct_convencoes ADD COLUMN IF NOT EXISTS sindicato_id uuid` + `UPDATE … WHERE sindicato_id IS NULL` casando pelo nome (FK lógica; só preenche vazio)
- `cct_funcao_eventos` (cct_cargo_id, rubrica_codigo → `rubricas_folha.codigo`, razao, razao_noturna, obrigatorio, observacao, origem_regra, ativo; UNIQUE por função×rubrica)
- `cct_funcao_beneficios` (cct_cargo_id, cct_beneficio_id, valor, desconto_percentual, obrigatorio, observacao, origem_regra, ativo; UNIQUE)
- `cct_municipios` (convencao_id, municipio, uf, ibge, origem_regra; UNIQUE)

### Seed (medido no sandbox): 1 sindicato · 1 município (Manaus/AM, IBGE 1302603) · **459 eventos** (51 funções × 9 rubricas; 7 obrigatórios) · **408 benefícios** (51 × 8)
Toda linha tem `origem_regra` dizendo de onde veio. Regras do seed (decididas, não reabertas):
- `cct_cargos.adicional_tipo` → evento **OBRIGATÓRIO** com a razão da própria linha: `periculosidade_30` → 0051 (30%) em
  ELETRICISTA ALTA/BAIXA TENSÃO e TÉCNICO EM MÁQUINAS; `insalubridade_10` → 0050 (10%) nos 3 CONTROLE DE PRAGAS e PISCINEIRO.
- Para **toda** função, eventos **opcionais** (dependem do funcionário/turno/ponto, exatamente como `calculo_service` faz):
  0020 noturno 20% · 0021 hora noturna reduzida · 0010 HE 50% · 0011 HE 100% · 0030 intrajornada (50) · 0090 DSR sobre HE ·
  0051 periculosidade 30 · 0050 insalubridade 10 · 0040 ronda 15 (CCT cl. 23ª).
- `adicional_10` (CARPINTEIROS E PEDREIROS) **não** virou evento: não há rubrica para ele em `rubricas_folha`. Não inventei código.
- Benefícios: os 8 de `cct_beneficios` para toda função, `obrigatorio`/valor/desconto copiados da linha da CCT.

### Telas (grupo g-cct · deep-link `/redesign/departamento-pessoal?t=g-cct`)
| id | Tipo | O que faz |
|---|---|---|
| `cct-sindicato` | table + Editar por linha | Ficha do sindicato; painel «Convenção vigente» (MTE, vigência, data-base, vínculo `sindicato_id`, patronal). |
| `cct-funcoes` | table (filtro com/sem ativos) | Função, piso, adicional do cargo, nº eventos, benefícios obrig./total, ativos, municípios. Ações por linha **Eventos** e **Benefícios** (form modal que inclui na função). |
| `cct-funcao-eventos` | table (filtro por função) | Rubrica, razão, razão noturna, obrigatório/opcional, origem. Ação **Remover**. |
| `cct-funcao-beneficios` | table (filtro por função) | Benefício, valor, desconto, obrigatório, origem. Ação **Remover**. |
| `cct-municipios` | table + CTA | Município/UF/IBGE/origem. Ação **Remover**; CTA → `cct-municipio-novo`. |
| `cct-municipio-novo` | form | Município, UF, IBGE → convenção vigente. |
| `cct-conformidade` (existente) | + sub e 2 painéis | «Ativos cuja função NÃO tem evento configurado» e «Ativos sem função da CCT» (nominal). |

Ações: `cct-sindicato-editar`, `cct-funcao-evento` (upsert; recusa rubrica fora de `rubricas_folha`), `cct-funcao-evento-remover`,
`cct-funcao-beneficio`, `cct-funcao-beneficio-remover`, `cct-municipio`, `cct-municipio-remover`. Linha criada pela tela ganha
`origem_regra = 'tela DP · <email> · <data>'`. Remover é DELETE **só nas tabelas desta frente**.

## 4. Oráculo — comandos e saídas

Rodado em container efêmero contra o sandbox (receita do contrato; `ensure()` aplicado por `_f2_ensure.py` = o que o 1º acesso ao DP faz):
```bash
WT=$(git rev-parse --show-toplevel)
ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\n' ' ')
docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env $ENVS conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_cct_como_dado.py
```
(Para o servidor HTTP efêmero, a imagem precisa de `--tmpfs /app/logs:mode=1777 --tmpfs /app/uploads:mode=1777` e as pastas
`backend/logs`/`backend/uploads` existindo na worktree — `/app` montado RO derruba o startup em `logs/app.log`. Vale para as outras frentes.)

VERMELHO (antes, §1) → `FALHOU: … faltam tabelas […] e a coluna cct_convencoes.sindicato_id · TOTAL cct_como_dado: 1 vermelho · exit=1`.

Primeira rodada com código teve **10 vermelhos em (c)** — `hr_payslips.base_salary` é a base PROPORCIONAL («16 dias (admissão/desligamento)»,
R$ 929,34 para piso R$ 1.742,52). Não era piso furado; era a régua lendo o campo errado. O oráculo passou a normalizar por «N dias».

VERDE (depois, com o código desta frente):
```
convenção vigente: SINDECOMPRESTS → sindicato «SINDECOMPRESTS» · municípios: 1
funções com ativo: 5 · ativos sem função da CCT (fora da conta): 5
AVISO: 0 holerite visível em 09/2026 — contra-prova na última visível: 07/2026
(b) holerites visíveis de ativos com função em 07/2026: 45
AVISO CCT × folha: ARTIFICE NAO ESPECIALIZADO: insalubridade (opcional na função) pago a 2/2 — ANTONIO CARLOS VIEIRA, KALEL SILVA DE JESUS
AVISO CCT × folha: JARDINEIROS: insalubridade (opcional na função) pago a 1/1 — GEILSON RODRIGUES DE ANDRADE
AVISO CCT × folha: LIDER DE PORTARIA: ronda (opcional na função) pago a 2/3 — ANTONIO WALCICLEY PEREIRA DA SILVA, EDIWILSON CORREA MARQUES
AVISO CCT × folha: PORTEIROS AGENTE DE PORTARIA GUARDETE: noturno (opcional na função) pago a 16/27 — ADAILSON SERRA ALVES, ADEILSON DINIZ DEODATO, AILTON CÉSAR VASCONCELOS, ANDREA GONÇALVES DOS SANTOS, ANILSON JOSE SEIXAS NEVES, ANTONIO DINIZ ASSIS DOS SANTOS, EDUARDO OLIVEIRA DE SOUZA, EDWARD JOSÉ ATENCIO DOMINGUEZ, EIDY CULIER DE CASTRO, ELEN XAVIER NUNES, FERNANDO SOUZA SIMPLICIO JUNIOR, JONHATA DINIZ BENAION, JONILSON MARTINS DE SOUZA, MAIARA MUNIZ DE SANTOS, RENE RICARDO CRUZ GONÇALVES, RILEM FERREIRA DE SOUZA
AVISO CCT × folha: PORTEIROS AGENTE DE PORTARIA GUARDETE: ronda (opcional na função) pago a 13/27 — ADAILSON SERRA ALVES, AILTON CÉSAR VASCONCELOS, ANILSON JOSE SEIXAS NEVES, ANTONIO CARLOS CASTRO GAMA, ANTONIO DINIZ ASSIS DOS SANTOS, EDUARDO OLIVEIRA DE SOUZA, EULER FELIPE FERNANDES DA COSTA, FRANCISCO RAMON FARIAS DE SOUZA, JONHATA DINIZ BENAION, JONILSON MARTINS DE SOUZA, MATHEUS HENRIQUE CABRAL DA SILVA, MAURICIO ALVES CHAGAS, RILEM FERREIRA DE SOUZA
AVISO CCT × folha: SERVICOS GERAIS FAXINEIRO: insalubridade (opcional na função) pago a 8/12 — ADEMIR SALUSTIANO DE SOUZA FILHO, ANGELA LOPES MACEDO, DANIEL VIDAL LARROQUE, GRACIENE PEREIRA DE CASTRO, JAQUELINE CARLOS DOS SANTOS, MALAQUIAS PEREIRA FERREIRA, OSCAR SOARES DA COSTA FILHO, PAULO DA SILVA LAMEGO
TOTAL cct_como_dado: 0 vermelho(s) · 6 aviso(s)
OK cct como dado: sindicato ligado, funções com evento/benefício, holerite bate com a função, piso respeitado
TEST oraculo_cct_como_dado PASS
exit=0
```
O que o verde prova: nos 45 holerites publicados de 07/2026, **toda** insalubridade/ronda/noturno paga é evento da função com a
**mesma razão** («10%», «15% CCT»); nenhum evento obrigatório faltou; base cheia ≥ piso em 45/45; 0 linhas sem `origem_regra`.
Rodou de novo depois das ações HTTP (incluir/remover evento, benefício, município; editar sindicato): mesmo resultado.

### Prova por HTTP (container efêmero `teste-dgx-f2`, porta 8202, banco do sandbox — parado e removido ao fim)
```
GET /api/v1/redesign/data/departamento-pessoal → extraMenu: [{id: g-cct, label: Sindicato & CCT}]
g-cct: tabs [cct-sindicato, cct-funcoes, cct-funcao-eventos, cct-funcao-beneficios, cct-municipios, cct-municipio-novo]
cct-sindicato: 1 linha [SINDECOMPRESTS · 00.444.514/0001-36 · AM · 01/01 · laboral] + Editar · painel «Convenção vigente» (5 linhas)
cct-funcoes: 51 linhas · 1ª: PORTEIROS AGENTE DE PORTARIA GUARDETE · R$ 1.670,00 · — · 9 eventos · 6/8 obrig. · 27 ativos · 1 município · ações [Eventos, Benefícios]
cct-funcao-eventos: 459 linhas · cct-funcao-beneficios: 408 · cct-municipios: 1 (Manaus/AM/1302603) · cct-municipio-novo: form
cct-conformidade (aba de g-visao): sub «… · Função sem evento configurado: 0 · Ativos sem função da CCT: 5» + 2 painéis nominais
POST action/cct-funcao-evento {0100, razão 22}        → 200 · aparece na aba com origem «tela DP · jjesus@… · 23/09/2026 23:41» · remover → 200
POST action/cct-funcao-evento {rubrica 9999}          → 400 «Rubrica 9999 não existe em rubricas_folha»
POST action/cct-funcao-beneficio {cesta_basica, 150}  → 200 · aparece «R$ 150,00 · Obrigatório» · restaurado ao seed (170, opcional)
POST action/cct-municipio {Iranduba, am, 1301852}     → 200 · aparece · remover → 200
POST action/cct-sindicato-editar {site}               → 200 · persistiu · limpo ao fim (URL não verificada não fica no sandbox)
POST action/cct-sindicato-editar {sem nome}           → 400
```
Nenhuma fixture ficou no sandbox: as linhas de teste foram removidas pelas próprias ações; DDL e seed ficam (são o que produção vai ter).

## 5. O que NÃO foi feito e por quê

- **`calculo_service.py` não lê as tabelas novas.** Paralelo cego (contrato): o holerite continua saindo das constantes e
  dos percentuais por funcionário. Ligar a folha à régua da função é decisão do dono (§7) e exige oráculo Σ|Δ| = 0.
- **`adicional_10`** (CARPINTEIROS E PEDREIROS) sem evento — não existe rubrica em `rubricas_folha`; criar rubrica é da F1.
- **Municípios além de Manaus**: a convenção só declara Manaus (`cct_convencoes.municipio`); a `descricao` não lista outros.
  Quem souber a abrangência real da AM000613/2025 inclui pela aba Municípios.
- **Sindicato patronal (SINDICOND-AM)** não virou linha de `cct_sindicatos`: o brief pedia 1 sindicato; o patronal fica no painel
  da convenção. Incluir é uma linha na tabela quando fizer sentido (tipo `patronal` já existe na coluna).
- **Colisão de códigos holerite × `rubricas_folha`** (0040 = ronda na tabela, HE 50% no holerite; 0050/0051 = insalubridade/
  periculosidade na tabela, AFASTAMENTO no holerite de 07/2026; 0015/0016/0018 do holerite não existem na tabela) — **não
  corrigi**: é chave do eSocial (S-1010) e cabe à F1/dono. O oráculo carrega o de-para à mão e vai discordar se alguém mudar.
- **Menu**: item `g-cct` está no `EXTRA_MENU` do builder (porta real, sem editar `frontend/`). Se o orquestrador levar para
  `frontend/src/app/redesign/_modules/departamento-pessoal.json` (chave `menu`, mesmo dict), **apagar do `EXTRA_MENU`** — senão duplica.
- **Sem sub-router REST** (`/api/rh/sindicatoFuncoes` etc.): as telas do redesign são o entregável; JSON por API entra quando o Hermes pedir.
- **`hr_payslips.base_salary` proporcional** («29 dias (admissão/desligamento)» para 6 pessoas admitidas há mais de um ano —
  ANTONIO DINIZ, GEILSON, JONILSON, OSCAR, VANDERLICE, DANIEL SOUZA — no holerite publicado de 07/2026): não investiguei, é
  `calculo_service`. O oráculo (c) normaliza pela referência «N dias» para não acusar piso por causa disso. Fica registrado.

## 7. Discrepâncias reais CCT × folha e decisões que só o dono pode tomar

Medidas pelo oráculo no holerite **publicado de 07/2026** (09/2026 ainda não tem holerite visível). Nenhuma foi "corrigida".

| Função (CCT) | O que a CCT do cargo diz | O que a folha paga | Quem |
|---|---|---|---|
| SERVIÇOS GERAIS FAXINEIRO | sem adicional de cargo | **insalubridade 10%** a 8 de 12 | ADEMIR SALUSTIANO, ANGELA LOPES, DANIEL VIDAL, GRACIENE PEREIRA, JAQUELINE CARLOS, MALAQUIAS PEREIRA, OSCAR SOARES, PAULO LAMEGO |
| ARTÍFICE NÃO ESPECIALIZADO | sem adicional de cargo | **insalubridade 10%** a 2 de 2 | ANTONIO CARLOS VIEIRA, KALEL SILVA DE JESUS |
| JARDINEIROS | sem adicional de cargo | **insalubridade 10%** a 1 de 1 | GEILSON RODRIGUES DE ANDRADE |
| PORTEIROS / AGENTE DE PORTARIA | sem adicional de cargo | **ronda 15%** a 13 de 27 · **noturno** a 16 de 27 | lista nominal na saída do oráculo (§4) |
| LÍDER DE PORTARIA | sem adicional de cargo | **ronda 15%** a 2 de 3 | ANTONIO WALCICLEY, EDIWILSON CORREA |

Leitura: a CCT trata insalubridade/periculosidade como atributo do **cargo** em 8 funções (pragas, piscineiro, eletricistas,
técnico de máquinas), mas a folha real paga por **pessoa/posto** (NR-15, laudo). Nas funções acima o seed deixou o evento como
**opcional** com a razão da CCT (10 / 15 / 20) — o holerite bate na razão (o oráculo conferiu «10%», «15% CCT»). Decisões:

1. **Quem tem laudo?** Insalubridade 10% em 11 pessoas de Serviços Gerais/Artífice/Jardineiro sem cargo insalubre na CCT precisa
   de LTCAT/laudo por posto. Se houver, marcar o evento como **obrigatório** na função (aba Eventos por função) e o oráculo passa a
   cobrar de todos; se não houver, é pagamento sem base — parar é decisão de gente, não de código.
2. **Ronda 15% em 15 agentes de portaria**: a CCT cl. 23ª paga a quem faz ronda no perímetro. Confirmar posto a posto quem faz.
3. **5 ativos sem função da CCT** (fora de toda conferência de piso/evento): ALAN VIEIRA, ALEXANDRE SOUZA, KELLY PATRICIA
   (AGENTE DE PORTARIA), NAILSON GARCIA (ARTÍFICE), THIAGO MAQUINE (JARDINEIRO) — preencher `cct_cargo_id` no cadastro.
4. **Ligar a folha à régua da função** (ler `cct_funcao_eventos` no `calculo_service`)? Só com oráculo Σ|Δ| = 0 nos holerites
   publicados. Hoje a régua é declaração; a folha é a mesma de ontem.
5. **Códigos de rubrica**: unificar holerite (0015/0016/0018/0040) com `rubricas_folha` (0051/0050/0040/0010) — chave do eSocial, F1.

## 6. Como o Jordan testa amanhã (depois do bake do backend)

1. Departamento Pessoal → menu **«Sindicato & CCT»** (ou `/redesign/departamento-pessoal?t=g-cct`).
2. Aba **Sindicato**: uma linha SINDECOMPRESTS · painel «Convenção vigente» com AM000613/2025 e «Sindicato laboral» em verde.
   Clique **Editar**, preencha Site/Contato, salve, recarregue: o valor fica.
3. Aba **Funções**: 51 linhas, «Eventos» = 9 em todas (nas 7 com adicional de cargo a rubrica do adicional é a mesma, só que
   marcada obrigatória), «Benefícios» = 6 obrig., «Ativos» = 27 em PORTEIROS. Filtro do topo: «com ativos» → 5 linhas.
   Clique **Eventos** numa função, escolha a rubrica 0100, razão 22, Opcional, salve. Na aba **Eventos por função** filtre pela
   função: a linha nova aparece com origem «tela DP · seu e-mail · data». Clique **Remover** nela.
4. Aba **Municípios**: Manaus/AM/1302603. CTA «Adicionar município» → Iranduba/AM → aparece; Remover.
5. **Visão geral → Conformidade CCT**: o subtítulo agora termina com «Função sem evento configurado: 0 · Ativos sem função da CCT: 5»
   e os dois painéis listam nomes. Remova TODOS os eventos de JARDINEIROS na aba Eventos por função e volte: GEILSON e THIAGO
   passam a aparecer em «função sem evento» — recoloque (botão Eventos em Funções) e some.
6. Oráculo (container de produção):
   `docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_cct_como_dado.py`
   Esperado: `TOTAL cct_como_dado: 0 vermelho(s) · N aviso(s)` e `TEST oraculo_cct_como_dado PASS`. Os AVISOS são a lista do §7.
   Quando o holerite de 09/2026 for publicado, o oráculo troca sozinho a competência-alvo (deixa de avisar «0 holerite visível em 09/2026»).
