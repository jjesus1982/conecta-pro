# FRENTE 10 — Uniforme/EPI com grade, frota com `Restam` e vistoria pareada, avaliação por ambiente

**Branch:** `frente/10-uniforme-frota-totem` · **Sessão:** tmux-agente-10 · **Módulo:** operacional
**Data:** 12–13/09/2026 · **Onde foi testado:** staging (`conecta_pro_staging`) pelo **modo efêmero**
(container descartável `teste-frente-10` com a worktree em `/app:ro`, porta 127.0.0.1:**8210**).
`/app` do `conecta-pro-backend-staging` é bind **somente-leitura** da árvore principal — `docker cp`
para lá falha ("Read-only file system"), então nada de hot-copy nesta frente.

> **Receita do efêmero que funcionou** (duas armadilhas custaram tempo e valem para as outras frentes):
> `-e ENVIRONMENT=staging` é obrigatório — com o `--env-file /opt/conecta-pro/.env` puro vem
> `ENVIRONMENT=production`, o loguru tenta abrir `/app/logs/app.log` dentro do bind `:ro` e o app
> morre no startup **sem nunca responder ao `/health`** (parece travamento, é `Errno 30`).
> E o upload da foto da vistoria precisa de diretório gravável **por cima** do `:ro`
> (`-v "$WT/backend/uploads_teste:/app/uploads"`) — `--tmpfs` não serve, não se cria mountpoint
> dentro de bind somente-leitura.
>
> ```bash
> docker run --rm -d --name teste-frente-10 --network conecta-staging-network \
>   -p 127.0.0.1:8210:8080 -v "$WT/backend:/app:ro" -v "$WT/backend/uploads_teste:/app/uploads" \
>   -e ENVIRONMENT=staging -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
>   --env-file /opt/conecta-pro/.env $ENVS -e PORT=8080 conecta-pro-backend:latest
> ```

---

## 1. Estado ANTES, medido

### 1.1 O que existia no staging (o terreno)

| Assunto | Tabela | Linhas | O que tinha |
|---|---|---|---|
| EPI — entregas legadas | `gp_epi_deliveries` | **220** | nome do item em **texto livre** (`epi_nome`), 13 nomes distintos, **sem tamanho, sem mínimo, sem máximo** |
| EPI — catálogo | `health_epi_catalog` | **5** | nome, CA, categoria — **sem grade de tamanho** |
| EPI — estoque | `health_epi_inventory` | **0** | tem `quantidade_minima`/`quantidade_maxima`, nunca alimentada |
| EPI — entregas novas | `health_epi_deliveries` | 0 | vazia |
| EPI — ficha assinada | `sst_fichas_epi` | 1 | itens em jsonb, para a ficha em PDF |
| **Frota / veículo / vistoria / abastecimento / multa** | — | — | **nenhuma tabela existia.** `pg_stat_user_tables` não tem nada que case com `veic\|vehic\|frota\|fleet\|vistoria\|multa` |
| Avaliação | — | — | não existe avaliação por ambiente. O **NPS** existe (`crm_followups` com `template='nps'`, **0 respostas** no staging) e é pesquisa de **cliente por WhatsApp**: sem ambiente, sem turno, sem item |
| Ronda (reuso da foto) | `inspection_rounds` 83 · `inspection_checkpoints` 15 | — | padrão de upload que a frente copiou |

Uniforme, no sentido do benchmark (grade P/M/G/GG/EXG com Mínimo·Máximo·Pendente·Atual por SKU),
**não existia em lugar nenhum** — havia entrega de EPI por nome livre, que é exatamente o terreno
onde "Blazer Feminino M" e "BLAZER FEMININO - M" viram dois itens.

### 1.2 Os oráculos, VERMELHOS (saída colada)

```
=== ORACULO SKU (antes)
FALHOU: tabela sst_uniforme_grade não existe — não há grade de tamanho nem mínimo/máximo por SKU
VERMELHO: mecanismo de grade ausente
exit=1

=== ORACULO VISTORIA (antes)
FALHOU: tabela frota_vistorias não existe — vistoria de saída não tem com que comparar
VERMELHO: mecanismo de vistoria ausente
exit=1

=== CACADOR (antes)
tabela frota_veiculos ausente — DDL da frente 10 não aplicado
TOTAL veículos sem KM no período: ? (sem tabela)
FAIL checar_frota_sem_km
exit=1
```

Os três nascem vermelhos por **ausência do mecanismo**, que é o estado honesto: o que não existe
não pode estar limpo. Os dois oráculos também **sabem ficar vermelhos com o mecanismo presente** —
prova na seção 3.3.

---

## 2. O que foi feito, arquivo por arquivo

### `backend/modules/operacional/controllers/redesign_builders/_frente_10.py` (novo, 813 linhas)
Tudo da frente num arquivo só: 15 telas, 11 ações, 1 rota de foto, 2 rotas públicas, e a constante
`DDL` com o texto exato das tabelas.

**Uniforme/EPI**
- `sku_norm(item, tamanho)` normaliza **na escrita**. Réplica declarada da régua do Hermes
  (`modules/gedeon/agents/hermes.py:408 _normalize` — NFKD, maiúsculas, sem marca de acento) mais
  colapso de separadores. A unicidade é do **banco** (`UNIQUE (sku_norm)`), não de um `if` em Python.
- Tela `uniforme-grade`: SKU · Tamanho · **Mínimo · Máximo · Pendente · Atual · Valor · Situação**.
  `atual = NULL` aparece como **"sem contagem"**, nunca 0. `Pendente` é contado do banco
  (solicitado + separado). Ação por linha "Contar" registra contagem física.
- Tela `uniforme-grade-novo` (FORM): tamanho aceita `PP|P|M|G|GG|XG|EXG|XGG` ou número de 2 dígitos;
  mínimo e máximo **obrigatórios** (a frente inteira existe para conferir mínimo).
- Tela `uniforme-entrega-lote` (FORM): entrega **individual e em lote** — escolhe um posto (todos os
  alocados ativos) e/ou cola CPFs, um por linha. CPF que não casar com colaborador ativo **único**
  aborta o lote inteiro (nada de `LIMIT 1` sobre chave que repete).
- Tela `uniforme-entregas` + ação de estado: **solicitação → separação → entrega → devolução**, um
  passo por vez (pular etapa é 409). A baixa de estoque acontece só em "entregue" e **bloqueia** se
  o SKU estiver sem contagem ou com saldo insuficiente — sensível é o default.

**Frota** (tabelas novas; nada existia)
- Tela `frota-painel`: KM atual, próxima troca de **óleo/pneu/correia** e `Restam`. `Restam` só sai
  para veículo com **leitura dentro de `PERIODO_KM_DIAS` (30)**; os outros aparecem **"sem dado"**
  cinza — nunca vencidos. Negativo = vermelho (`bad`).
- Telas `frota-leitura` / `frota-abastecimentos`: KM e abastecimento com valor/litro e **média km/l**
  (KM rodado desde o abastecimento anterior ÷ litros, via `LAG`). Sem abastecimento anterior é
  **"sem dado"**, não 0. KM que anda para trás é 409.
- Telas `frota-vistoria-nova` / `frota-vistorias`: **chegada × saída**. A saída só pareia com chegada
  do **mesmo veículo, mesma `os_ref`, mesmo condutor**, dentro de `JANELA_VISTORIA_HORAS` (168h) e
  ainda não pareada. Sem par → **`aguardando_checklist`**. Com par → `sem_diferencas` /
  `houve_diferencas`, derivado da comparação por área (bom→ruim) e do checklist (ok→avariado).
  **Foto por área** (dianteira, traseira, lateral D/E, interior) reaproveitando o padrão da ronda:
  MIME validado, teto de 10MB, arquivo em disco + ponteiro em `jsonb`, download com guarda de path
  traversal e sob autenticação.

**Avaliação por ambiente**
- Telas `avaliacao-ambiente-novo` / `avaliacao-ambientes`: ambientes **por contrato**, com itens
  (ex.: Portaria → Assento, Mesa, Piso).
- Telas `avaliacao-link-novo` / `avaliacao-links`: link compartilhável por contrato, **com e sem
  identificação obrigatória**, e ação de desativar.
- **Página pública** `GET|POST /api/v1/redesign/publico/avaliacao/{token}`: HTML autocontido com
  carinha **N/A · ótimo · bom · regular · ruim** por item. Sem totem físico: é uma página por token,
  **sem login**, sob o router do redesign que já está montado. Exige **ambiente + turno**; é anônima
  quanto à **pessoa** (não grava IP nem usuário) e nunca quanto ao posto. Link desativado responde
  "link encerrado".
- Tela `avaliacao-dashboard`: % ótimo/bom e contagem de "ruim" por **contrato · ambiente · turno**.

### `.../redesign_builders/equipamentos.py` (+8 linhas, marcadas `# frente 10`)
Anexa as telas de frota e avaliação antes do `return out`, e inclui **uma vez só** o `router` das
ações e o `MENU_EQUIPAMENTOS`.

### `.../redesign_builders/gestao_de_pessoas.py` (+8 linhas, marcadas `# frente 10`)
Anexa as telas de uniforme e o `MENU_GESTAO`. **As linhas da frente 5 foram preservadas** — as
minhas entram logo antes do `return out`, com comentário `# frente 10`.

### `backend/scripts/orq/test_oraculo_sku_unico.py` (novo)
Afirma: (1) nenhum par da grade normaliza para o mesmo SKU **e** o `sku_norm` gravado é o que a
régua produz — escrita que passe por fora do normalizador aparece; (2) toda linha ativa tem tamanho,
mínimo e máximo, com mínimo ≤ máximo; (3) **todo item ativo do catálogo tem ao menos uma linha de
grade** — item sem grade é item cujo mínimo ninguém confere.

### `backend/scripts/orq/test_oraculo_vistoria_par.py` (novo)
Afirma: saída com par aponta para **chegada** do mesmo veículo/OS/condutor, anterior e dentro da
janela; saída sem par tem status `aguardando_checklist` e **nunca** veredito; saída com par tem
veredito; nenhuma chegada é par de duas saídas.

### `backend/scripts/qa/checar_frota_sem_km.py` (novo)
Caçador de dívida: veículo ativo sem leitura no período. Linha canônica
`TOTAL veículos sem KM no período: N`. Sem tabela = vermelho.

Os três **importam** `sku_norm` / `JANELA_VISTORIA_HORAS` / `PERIODO_KM_DIAS` de `_frente_10` em vez
de copiar: duas cópias divergem e a que diverge cala.

---

## 3. Estado DEPOIS, medido

### 3.1 Rotas montadas (lidas de `app.routes` no efêmero 8210)

```
/api/v1/redesign/action/uniforme-grade
/api/v1/redesign/action/uniforme-estoque
/api/v1/redesign/action/uniforme-entrega-lote
/api/v1/redesign/action/uniforme-entrega-status
/api/v1/redesign/action/frota-veiculo
/api/v1/redesign/action/frota-leitura
/api/v1/redesign/action/frota-vistoria
/api/v1/redesign/frota/vistorias/{vistoria_id}/fotos/{area}
/api/v1/redesign/action/avaliacao-ambiente
/api/v1/redesign/action/avaliacao-link
/api/v1/redesign/action/avaliacao-link-desativar
/api/v1/redesign/publico/avaliacao/{token}      (GET e POST)
```

15 telas servidas: 4 em `/redesign/data/gestao-de-pessoas` (uniforme) e 11 em
`/redesign/data/equipamentos` (frota + avaliação), todas no `extraMenu` do módulo.

### 3.2 Oráculos VERDES (saída colada)

```
=== SKU
grade: 11 SKU(s) ativo(s) · 11 distintos pela régua · catálogo sem grade: 0
OK sku_unico: nenhum SKU duplicado pela régua e todo item tem tamanho, mínimo e máximo
exit=0

=== VISTORIA
vistorias de saída: 3 · com par: 2 · aguardando checklist: 1
OK vistoria_par: toda saída compara com a chegada certa ou espera o checklist
exit=0

=== CACADOR (conta dívida; N>0 é o trabalho dele)
🚗 PMW7C88 · Renault Kangoo 2019 · última leitura: nunca
TOTAL veículos sem KM no período: 1 (de 2 ativo(s), período 30d)
FAIL checar_frota_sem_km
```

### 3.3 Prova de que os oráculos SABEM ficar vermelhos com o mecanismo presente

Injetei no staging uma escrita que passou **por fora** do normalizador e um par de OS trocada,
rodei, e desfiz:

```
--- INSERT sst_uniforme_grade (sku_norm gravado à mão como 'BLAZER FEMININO - M')
grade: 12 SKU(s) ativo(s) · 11 distintos pela régua · catálogo sem grade: 0
FALHOU: grade #13 'BLAZER FEMININO - M': sku_norm gravado 'BLAZER FEMININO - M' ≠ régua 'BLAZER FEMININO M'
FALHOU: grade #13 'BLAZER FEMININO - M' duplica #11 (mesmo SKU 'BLAZER FEMININO M')
VERMELHO: 2 desvio(s) na grade de uniforme/EPI

--- UPDATE frota_vistorias SET par_id=1 WHERE id=3  (par de OUTRA OS)
vistorias de saída: 3 · com par: 2 · aguardando checklist: 0
FALHOU: saída #3: par #1 é de outro carro/OS/condutor (1,OS-2026-0912,…) ≠ (1,OS-SEM-CHEGADA,…)
FALHOU: chegada #1 é par de duas saídas (#2 e #3)
VERMELHO: 2 desvio(s) no par chegada×saída
```

### 3.4 E2E contra o efêmero 8210 (tudo pela HTTP, com token real)

```
== 1. Grade
[200] SKU 'BOTINA DE SEGURANCA MARLUVAS M' cadastrado.        (…10 SKUs do catálogo…)
[200] SKU 'BLAZER FEMININO M' cadastrado.
[409] DUPLICATA 'BLAZER FEMININO - M': Este SKU já existe: 'BLAZER FEMININO M'. Não vai duplicar.
[400] mínimo>máximo: Mínimo maior que máximo.
[400] sem mínimo: Mínimo e máximo são obrigatórios — sem eles o estoque não é conferido.

== 2. Entrega em lote
[200] lote do posto: Lote L20260913-5E74: 13 solicitação(ões) criada(s).
[400] CPF inexistente: CPF sem colaborador ativo único: 00000000000.
[409] pular separação: De 'solicitado' só se vai para 'separado'.
[200] solicitado → separado → entregue → devolvido   (estoque do SKU: 6 → 5)
[409] entregar sem estoque: Estoque de 'Blazer Feminino M' não cobre: atual 0 < 1.

== 3. Frota
[200] veículo JXK4B12 · [409] placa repetida · [200] veículo PMW7C88
[200] leitura km 41200 · [200] abastecimento 41680 · [200] abastecimento 42310
[409] KM 100 menor que a última leitura (42310). Hodômetro não anda para trás.
[400] Abastecimento pede litros e valor maiores que zero.

== 4. Vistoria chegada × saída
[200] Vistoria #1: Chegada registrada.                          (OS-2026-0912, foto dianteira)
[200] Vistoria #2: Houve diferenças.                            (saída da MESMA OS, dianteira bom→ruim)
[200] Vistoria #3: Aguardando checklist (sem chegada da mesma OS/condutor).
[200] Vistoria #4: Chegada registrada.                          (OS-2026-0913)
[200] Vistoria #5: Sem diferenças.

== 5. Avaliação
[200] Ambiente 'Portaria' com 3 item(ns). · [409] repetido · [200] 'Banheiro Térreo'
[200] link anônimo · [200] link com identificação
[200] página pública SEM token de login: 3045 bytes, tem formulário = True
[200] resposta anônima gravada = True
[200] item faltando é recusado = True
[200] link com identificação recusa anônimo = True
[200] resposta identificada gravada = True
[200] link desativado responde 'encerrado' = True

== 6. Banco: grade 11 · entregas 13 · veículos 2 · leituras 3 · vistorias 5 · ambientes 2 · respostas 2
   1 chegada OS-2026-0912 par=-  | 2 saida OS-2026-0912 par=1 houve_diferencas
   3 saida OS-SEM-CHEGADA par=- aguardando_checklist
   4 chegada OS-2026-0913 par=-  | 5 saida OS-2026-0913 par=4 sem_diferencas
```

Segurança da foto: `200 image/png 67b` com token; **401** sem token; **404** em
`..%2f..%2f..%2fetc%2fpasswd`.

### 3.5 O que a tela mostra (dado real, lido de `/redesign/data/...`)

```
frota-painel
  JXK4B12 · Fiat Strada 2024 · 42.310 · 13/09/2026 03:38 · -310 km · 17.690 km · -4.310 km
  PMW7C88 · Renault Kangoo 2019 · sem dado · — · sem dado · sem dado · sem dado
frota-abastecimentos
  JXK4B12 · 42.310 · 40.0 L · R$ 252,00 · R$/L 6.30 · média 15.8 km/l
  JXK4B12 · 41.680 · 42.5 L · R$ 268,60 · R$/L 6.32 · média sem dado   (não há leitura anterior)
uniforme-grade
  Blazer Feminino · M · mín 5 · máx 20 · pendente 12 · atual 6 · ok
avaliacao-dashboard  kpis: 2 respostas · 40% ótimo+bom · 1 ambiente · 2 links
  CTR-2026-00013 · Portaria · Noite  →  67% ótimo/bom · 3 item(ns) · ruim 0
  CTR-2026-00013 · Portaria · Tarde  →  0% ótimo/bom · 2 item(ns) · ruim 2
```

`PMW7C88` é o veículo deixado **de propósito** sem leitura: prova a decisão "sem dado, nunca
vencido" e alimenta o caçador.

---

## 4. Fiação pendente para o integrador

### 4.1 `backend/scripts/qa/checar_regressao.py` — bloco `CACADORES` (roda no container)

```python
    # Veículo ativo sem leitura de KM no período (frente 10, 12/09/2026): `Restam` só vale com
    # quilometragem alimentada; sem leitura o painel mostra "sem dado" e a troca de óleo passa
    # despercebida do mesmo jeito. 1 de 2 na estreia (staging).
    "checar_frota_sem_km.py": lambda s: _n(r"^TOTAL veículos sem KM no período: (\d+)", s, "TOTAL veículos sem KM no período: 0"),
```

### 4.2 DDL de PRODUÇÃO (aplicado só no staging; 8 tabelas + 3 índices)

```sql
CREATE TABLE IF NOT EXISTS sst_uniforme_grade (
  id serial PRIMARY KEY, item varchar(120) NOT NULL, tamanho varchar(10) NOT NULL,
  sku_norm varchar(140) NOT NULL UNIQUE, minimo integer NOT NULL CHECK (minimo >= 0),
  maximo integer NOT NULL CHECK (maximo >= minimo), atual integer CHECK (atual >= 0),
  valor_unitario numeric(12,2), catalog_id uuid, ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS sst_uniforme_entregas (
  id serial PRIMARY KEY, lote varchar(40) NOT NULL, grade_id integer NOT NULL REFERENCES sst_uniforme_grade(id),
  employee_id uuid NOT NULL, quantidade integer NOT NULL CHECK (quantidade > 0), motivo varchar(30) NOT NULL, prazo date,
  status varchar(20) NOT NULL DEFAULT 'solicitado' CHECK (status IN ('solicitado','separado','entregue','devolvido')),
  solicitado_em timestamptz NOT NULL DEFAULT now(), separado_em timestamptz, entregue_em timestamptz, devolvido_em timestamptz,
  created_by varchar(120));
CREATE INDEX IF NOT EXISTS ix_sst_uniforme_entregas_grade ON sst_uniforme_entregas (grade_id, status);
CREATE TABLE IF NOT EXISTS frota_veiculos (
  id serial PRIMARY KEY, placa varchar(10) NOT NULL UNIQUE, modelo varchar(80),
  km_proxima_troca_oleo integer, km_proxima_troca_pneu integer, km_proxima_troca_correia integer,
  ativo boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS frota_leituras (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  tipo varchar(15) NOT NULL CHECK (tipo IN ('km','abastecimento')), km integer NOT NULL CHECK (km >= 0),
  litros numeric(8,2), valor numeric(10,2), condutor_id uuid, lida_em timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE INDEX IF NOT EXISTS ix_frota_leituras_veiculo ON frota_leituras (veiculo_id, lida_em);
CREATE TABLE IF NOT EXISTS frota_vistorias (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  tipo varchar(10) NOT NULL CHECK (tipo IN ('chegada','saida')), os_ref varchar(40) NOT NULL, condutor_id uuid NOT NULL,
  km integer, checklist varchar(10) NOT NULL CHECK (checklist IN ('ok','avariado')), areas jsonb NOT NULL DEFAULT '{}'::jsonb,
  par_id integer REFERENCES frota_vistorias(id),
  status_saida varchar(25) CHECK (status_saida IN ('sem_diferencas','houve_diferencas','aguardando_checklist')),
  criado_em timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE TABLE IF NOT EXISTS aval_ambientes (
  id serial PRIMARY KEY, contract_id uuid NOT NULL, nome varchar(80) NOT NULL, itens jsonb NOT NULL DEFAULT '[]'::jsonb,
  ativo boolean NOT NULL DEFAULT true, criado_em timestamptz NOT NULL DEFAULT now(), UNIQUE (contract_id, nome));
CREATE TABLE IF NOT EXISTS aval_links (
  token varchar(48) PRIMARY KEY, contract_id uuid NOT NULL, exige_identificacao boolean NOT NULL DEFAULT false,
  ativo boolean NOT NULL DEFAULT true, criado_em timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS aval_respostas (
  id serial PRIMARY KEY, token varchar(48) NOT NULL REFERENCES aval_links(token),
  ambiente_id integer NOT NULL REFERENCES aval_ambientes(id), turno varchar(10) NOT NULL CHECK (turno IN ('manha','tarde','noite')),
  identificacao varchar(120), notas jsonb NOT NULL, comentario text, criado_em timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_aval_respostas_amb ON aval_respostas (ambiente_id, criado_em);
```

O mesmo texto vive na constante `DDL` no fim de `_frente_10.py` — se um dia divergir, a constante é
a cópia, o banco é a verdade.

### 4.3 O que **não** precisa de fiação

- `main_production.py`: **nada**. O `router` entra pelo registry dos builders
  (`_discover_module_builders` → `router.include_router(_m.router)`), sob `/api/v1/redesign`.
- `frontend/src/app/redesign/_modules/*.json`: **nada**. O menu vai por `EXTRA_MENU` e já aparece em
  `extraMenu` na resposta (conferido nas duas telas). Nenhum `.tsx` foi tocado: `tbl`/`dash`/`FORM`
  (inclusive `file` + `multipart`) já são genéricos.
- `celery_app.py`: **nada**. A frente não tem task agendada.

### 4.4 Diretório de fotos

As fotos de vistoria vão para `/app/uploads/frota/<id_da_vistoria>/`, dentro do mesmo volume que a
ronda usa (`bind /opt/conecta-pro/uploads -> /app/uploads rw=true` no backend de produção) —
nenhum volume novo. **Atenção ao deploy blue/green:** o diretório é criado sob demanda na primeira
foto; não precisa pré-criar.

---

## 5. O que NÃO foi feito, e por quê

1. **Gestão de multas — fora de escopo, deliberado.** A decisão é que só se aponta condutor com
   **posse datada** do veículo na data da infração. Não existe tabela de multa nem de posse; criar a
   gestão inteira de multas (AIT, Renainf, notificação, boleto, recurso) para preencher um campo é o
   oposto do que a frente pede, e apontar o **condutor atual** pela multa de três meses atrás é
   acusar o inocente. O que a frente deixa pronto para quando entrar: `frota_vistorias` já registra
   **quem estava com o carro, em que OS e quando** — é a semente do histórico de posse.
2. **Não migrei as 220 linhas de `gp_epi_deliveries` para a grade nova.** O nome do item é texto
   livre e **não tem tamanho**: a migração teria de inventar o tamanho de cada entrega, e vazio real
   é "sem dado", nunca um chute. A grade nasce do catálogo (5 itens × 2 tamanhos, feitos no teste) e
   do que o DP cadastrar. O histórico velho continua onde está, intacto.
3. **Não toquei em `health_epi_inventory`.** Ela tem colunas de mínimo/máximo e **0 linhas**;
   aproveitá-la exigiria um `epi_id` por tamanho, que o catálogo não tem. Tabela nova com `UNIQUE`
   no SKU normalizado é menos código e a trava fica no banco.
4. **QR Code não é gerado.** O link é uma URL; imprimir o QR é um passo de papel. Se o Jordan quiser
   o PNG do QR na tela, é um endpoint pequeno depois — não inventei dependência nova para isso.
5. **Manutenção com valor de mão de obra/peças e "gera manutenções periódicas"** (benchmark 3.6) não
   entrou: `equipment_maintenances` já existe e é onde isso mora; misturar com a frota nova antes de
   o Jordan dizer se veículo é `equipment` seria criar a segunda fonte de verdade.
6. **Nada foi para produção.** Sem bake, sem deploy, sem `docker cp` em container de produção. O DDL
   de produção está na seção 4.2 para o integrador aplicar.

---

## 6. Como o Jordan testa amanhã

**Depois** que o integrador aplicar o DDL (4.2) e o deploy entrar, no ERP:

1. **Grade de uniforme** — Gestão de Pessoas → *Uniforme/EPI · Novo SKU*: cadastre
   `Blazer Feminino` tamanho `M`, mínimo 5, máximo 20. Depois tente cadastrar
   `BLAZER FEMININO -` tamanho `M`: o sistema recusa dizendo *"Este SKU já existe: 'BLAZER FEMININO
   M'. Não vai duplicar."* — é a trava 1 do pré-mortem, na sua frente.
2. **Entrega em lote** — *Uniforme/EPI · Entrega em lote*: escolha o SKU, motivo "Admissão" e um
   **posto**; ele cria uma solicitação para cada alocado. Em *Uniforme/EPI · Entregas*, use os
   botões **Separar → Entregar → Devolver**. Tente "Entregar" sem ter contado o estoque: recusa.
3. **Frota** — Equipamentos → *Frota · Novo veículo* (placa + KM das próximas trocas) →
   *Frota · KM / Abastecimento*. No *Frota · Painel*, o veículo com leitura mostra `Restam` (vermelho
   se negativo) e o **sem leitura mostra "sem dado"**, não vencido.
4. **Vistoria** — *Frota · Nova vistoria*: registre a **chegada** com OS `OS-TESTE` e fotos, depois a
   **saída** da mesma OS e mesmo condutor marcando uma área como "Ruim" → sai **Houve diferenças**.
   Registre uma saída com OS que não teve chegada → **Aguardando checklist**, sem acusar ninguém.
5. **Avaliação** — Equipamentos → *Avaliação · Novo ambiente* (contrato + "Portaria" + itens) →
   *Avaliação · Novo link*. Copie a URL e **abra no celular, deslogado**: aparece a página com as
   carinhas. Responda; o resultado aparece em *Avaliação · Painel* por contrato·ambiente·turno.
   No staging, o link vivo hoje é
   `http://127.0.0.1:8210/api/v1/redesign/publico/avaliacao/YXmPGffhs43nv_MKGwXfAHadyxmm6h7k`.

**Se quiser ver antes do deploy**, no staging:

```bash
# sobe o efêmero da branch (para com `down` ao terminar — memória é compartilhada)
/tmp/.../efemero_f10.sh up          # 127.0.0.1:8210
/tmp/.../efemero_f10.sh oraculo test_oraculo_sku_unico.py
/tmp/.../efemero_f10.sh oraculo test_oraculo_vistoria_par.py
/tmp/.../efemero_f10.sh qa checar_frota_sem_km.py
/tmp/.../efemero_f10.sh down
```

---

## 7. Riscos residuais do pré-mortem que continuam

- **0.1 Sem Sentry.** `SENTRY_DSN=` continua vazio. Um 500 nas rotas desta frente — inclusive na
  **página pública**, que roda no celular de quem avalia — morre no log de um container que ninguém
  lê. A frente reduz a superfície (toda falha prevista vira 400/409 com frase em português), mas não
  substitui monitoramento.
- **0.3 `docker cp` não publica.** Nada desta frente está em produção. Só vale depois do bake, com
  `checar_bake_pendente = 0`.
- **0.5 Módulos mortos.** `equipment_management` e `health_occupational` continuam como estavam: esta
  frente pendurou telas nos builders do redesign, **não** ressuscitou os módulos. A frente 9 é quem
  trata disso.
- **Trava 2 (KM que ninguém atualiza) é social, não técnica.** O `Restam` agora é honesto, mas se
  ninguém registrar KM, o painel fica em "sem dado" para sempre. É por isso que o caçador
  `checar_frota_sem_km` existe e nasce contando **1**.
- **O veredito da vistoria depende de quem preenche.** "Houve diferenças" só sai se a área foi
  avaliada nas duas pontas. Saída avaliada com chegada em branco dá `sem_diferencas` — silêncio, não
  acusação. É o lado conservador de propósito; o custo é um falso negativo, e o falso negativo aqui é
  melhor que acusar o motorista errado.
- **Token do link é o acesso.** Quem tiver a URL responde. É o mesmo modelo do portal de assinatura
  (`/api/v1/signatures/public/`), e deliberado: totem na portaria não tem login. Link vazado se
  resolve desativando na tela — o que já está lá.
