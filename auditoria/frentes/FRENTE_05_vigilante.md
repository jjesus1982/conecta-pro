# FRENTE 05 — Conformidade de vigilante: reciclagem com validade, CNV, nome de guerra, armamento/colete como CONTROLE

**Data:** 12/09/2026 (noite) · **Branch:** `frente/05-vigilante` (worktree `agent-af51e343d68aa21ab`, criada a partir de `30be528a3`)
**Módulo:** `hr` (`backend/modules/people_management/hr/**`) + `_frente_05.py` do redesign · **Sessão:** `tmux-agente-05`
**Commits:** `84ef4f65b` (oráculo + régua, vermelho), `e941e1afb` (rotas, models, telas, caçador), + este relatório.

---

## 1. Estado ANTES — medido

Produção (SELECT apenas, para o vermelho inicial — nada escrito) e staging (`conecta_pro_staging`, cópia) dizem a mesma coisa:

| Medida | Valor |
|---|---|
| Funcionários ativos | 65 |
| Com cargo contendo "vigil" | **0** (cargos: AGENTE DE PORTARIA, AGENTE DE SERVIÇOS GERAIS, ARTÍFICE, JARDINEIRO, LÍDER DE PORTARIA) |
| Com `cnv` / `cnv_validade` preenchidos | 0 / 0 |
| Com `curso_vigilante` / `curso_vigilante_validade` | 0 / 0 |
| Com `porte_arma` | 0 · postos `requires_armed`: 0 de 17 |
| Escalados hoje (turno ativo, não folga, `scheduled`, coorte da casa) | **28** |
| Tabelas `vigilante_cursos` / `equipamentos_controlados` | não existiam |
| Coluna `employees.nome_de_guerra` | não existia |
| Coluna `employees.cnv_validade` | **JÁ EXISTIA** (model + banco, `sprint33_employees_operational`) — o briefing dizia que não. Não foi recriada. |

**Oráculo no nascimento** (`test_oraculo_vigilante_apto.py`, staging, DDL recém-aplicado com tabelas vazias, antes de qualquer rota/tela) — VERMELHO, exit 1:

```
escalados hoje: 28 · sujeitos à régua: 28 (chave de funções ausente → todos) · aptos: 0 · inaptos: 28 (sem dado: 28) · armas sem controle: 0
FALHOU: ADEMIR SALUSTIANO DE SOUZA FILHO (AGENTE DE SERVIÇOS GERAIS · Condomínio Villa dos Pássaros): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: AILTON CÉSAR VASCONCELOS (AGENTE DE PORTARIA · Condomínio Mirante das Flores): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: ANGELA LOPES MACEDO (AGENTE DE SERVIÇOS GERAIS · Condomínio Villa Dei Fiori): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: ANILSON JOSE SEIXAS NEVES (AGENTE DE PORTARIA · Residencial Laranjeiras Village): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: ANTONIO CARLOS VIEIRA (ARTÍFICE · Condomínio Michelangelo): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: ANTONIO WALCICLEY PEREIRA DA SILVA (LÍDER DE PORTARIA · Condomínio Ideal Flores da Cidade): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: BIANCA HELEM DA SILVA MEIRA (AGENTE DE PORTARIA · Residencial Laranjeiras Village): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: CELIANE GARCIA DE SOUSA (AGENTE DE SERVIÇOS GERAIS · Condomínio Ideal Flores da Cidade): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: EDILENE SALES SOUSA (AGENTE DE SERVIÇOS GERAIS · Condomínio Ideal Flores da Cidade): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: EDIWILSON CORREA MARQUES (LÍDER DE PORTARIA · Condomínio Mirante das Flores): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: EDWARD JOSÉ ATENCIO DOMINGUEZ (AGENTE DE PORTARIA · Condomínio Villa dos Pássaros): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: EIDY CULIER DE CASTRO (AGENTE DE PORTARIA · Condomínio Villa Dei Fiori): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: EULER FELIPE FERNANDES DA COSTA (AGENTE DE PORTARIA · Residencial Laranjeiras Village): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: FRANCISCO RAMON FARIAS DE SOUZA (AGENTE DE PORTARIA · Residencial Laranjeiras Village): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: GEILSON RODRIGUES DE ANDRADE (JARDINEIRO · Condomínio Ideal Flores da Cidade): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: GERNANES BINDA APARICIO (AGENTE DE PORTARIA · Condomínio Villa Dei Fiori): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: GRACIENE PEREIRA DE CASTRO (AGENTE DE SERVIÇOS GERAIS · Condomínio Prime Arena): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: JAQUELINE CARLOS DOS SANTOS (AGENTE DE SERVIÇOS GERAIS · Condomínio Villa Dei Fiori): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: JEOVANE DO NASCIMENTO (AGENTE DE PORTARIA · Condomínio Villa dos Pássaros): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: JONILSON MARTINS DE SOUZA (AGENTE DE PORTARIA · Condomínio Ideal Flores da Cidade): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: KALEL SILVA DE JESUS (ARTÍFICE · Condomínio Michelangelo): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: LIVIA CARISE PEREIRA CONSENTINE (AGENTE DE PORTARIA · Condomínio Ideal Flores da Cidade): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: MAIARA MUNIZ DE SANTOS (AGENTE DE PORTARIA · Condomínio Ideal Flores da Cidade): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: MALAQUIAS PEREIRA FERREIRA (AGENTE DE SERVIÇOS GERAIS · Condomínio Prime Arena): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: MAURICIO ALVES CHAGAS (AGENTE DE PORTARIA · Condomínio Green Hills): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: OSCAR SOARES DA COSTA FILHO (AGENTE DE SERVIÇOS GERAIS · Condomínio Villa dos Pássaros): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: TELMA MARIA LAGES MEIRA (AGENTE DE SERVIÇOS GERAIS · Condomínio Mirante das Flores): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
FALHOU: VANDERLICE SANTOS DA SILVA (AGENTE DE SERVIÇOS GERAIS · Condomínio Mirante das Flores): CNV sem validade cadastrada; sem curso/reciclagem cadastrado
28 desvio(s): vigilante escalado sem aptidão provada ou arma sem controle. [...]
exit=1
```

É o vermelho honesto do pré-mortem: o sistema não sabe quem é vigilante, nem quando a reciclagem vence, nem onde está arma nenhuma.

### Decisão tomada que NÃO estava no briefing (registrada, não reaberta)

A Conecta Mais é de **portaria** (CCT SINDECOMPRESTS): 0 vigilantes por cargo em produção. Cobrar CNV de agente de serviços gerais e jardineiro é trava que se aprende a ignorar — o mesmo modo de falha que o oráculo do ponto teve com a Cintia afastada. Então **quem está sujeito à régua vem do banco**, não do código: `system_configs.vigilante.funcoes_exigem_credencial` (lista JSON de trechos casados contra `employees.cargo` e `posts.post_type`, ex.: `["vigilante","escolta"]`).

- **Chave ausente = TODO MUNDO sujeito** (conservador; é o estado de hoje em produção e no staging → 28 sem dado).
- Posto `requires_armed`, CNV preenchida ou curso cadastrado põem a pessoa na régua mesmo com a chave preenchida.
- O DP decide a lista; enquanto não decidir, o oráculo fica vermelho — de propósito.

---

## 2. O que foi feito — arquivo por arquivo

| Arquivo | O quê |
|---|---|
| `backend/modules/people_management/hr/services/conformidade_vigilante.py` (novo) | **Régua única.** `SQL_ESCALADOS_HOJE` (mesma régua do lembrete de ponto + `coorte_ponto.SQL_NAO_AUSENTE_HOJE` importada), `avaliar()` pura (ausência = motivo, vencido = motivo), `aptidao()`, `vencimentos()` (30/60/90, vencidos, SEM DADO separado), `posse_equipamentos()`, `cursos()`, escritas `cadastrar_curso` (vence_em = conclusão + meses; meses de `system_configs` se não informado; conclusão no futuro → erro), `cadastrar_equipamento` (série obrigatória, UNIQUE), `entregar` (**armamento só para APTO pela régua inteira**; 2ª posse → erro pelo índice único parcial), `devolver`, `definir_nome_de_guerra`, e `armas_sem_controle()` para o caçador. |
| `backend/scripts/orq/test_oraculo_vigilante_apto.py` (novo) | Oráculo: (1) regra pura com datas fixas (7 casos), (2) DDL aplicado, (3) ninguém escalado hoje sujeito à régua está inapto/sem dado, (4) nenhuma arma sem controle. Importa a régua, não a copia. |
| `backend/modules/people_management/hr/models/vigilante.py` (novo) + `models/__init__.py` (+4 linhas) | `VigilanteCurso`, `EquipamentoControlado`, `EquipamentoControladoAlocacao` — para o alembic enxergar (env.py já importa o pacote `hr.models`). |
| `backend/modules/people_management/hr/schemas/vigilante.py` (novo) | `CursoCreate`, `EquipamentoCreate`, `EntregaCreate`, `DevolucaoCreate`, `NomeDeGuerraUpdate` (usados pelo controller E pelas ações do redesign — uma validação só). |
| `backend/modules/people_management/hr/controllers/vigilante_controller.py` (novo) | Sub-router `/vigilante` com `CurrentActiveUser` como os vizinhos. |
| `backend/modules/people_management/hr/aggregator.py` (+8 linhas, `# frente 05`) | `router.include_router(vigilante_router)` — o aggregator já está montado em `/api/v1/people-management/hr`. |
| `backend/modules/operacional/controllers/redesign_builders/_frente_05.py` (novo) | `MENU` (5 itens), `telas(db)` (painel de aptidão, por pessoa, armamento/colete, 2 FORMs), `router` com 5 ações `/action/vigilante-*`. Se o DDL não existir no banco, cai em "aguardando dado" sem derrubar o módulo. |
| `backend/modules/operacional/controllers/redesign_builders/gestao_de_pessoas.py` (+6 linhas, `# frente 05`) | 2 linhas no fim do `build()` + 3 no nível do módulo (menu, router). Foi o caminho indicado pelo integrador (o registry ignora `_*.py`). |
| `backend/scripts/qa/checar_arma_sem_serie.py` (novo) | Caçador → `TOTAL armas sem série/responsável: N`. |
| `auditoria/frentes/FRENTE_05_vigilante.md` | Este relatório. |

**Nada** foi escrito em produção, no checkout principal `/opt/conecta-pro`, em `main_production.py`, `alembic/versions/`, `checar_regressao.py`, `celery_app.py` ou `_modules/*.json`.

---

## 3. Estado DEPOIS — medido

### 3.1 Como foi testado (modo efêmero, não hot-copy)

O `/app` do `conecta-pro-backend-staging` é bind **só-leitura** do checkout principal — `docker cp` falha. Testei em **modo efêmero**: cópia do backend da worktree dentro do container (`/tmp/f05`) + `uvicorn` efêmero na porta 8082 (interna ao container, derrubado ao final), e depois o comando do integrador (`docker run --rm -v <worktree>/backend:/app:ro … conecta-pro-backend:latest`) para oráculo e caçador. Os dois apontam para `conecta_pro_staging`. Mesmo resultado nos dois.

### 3.2 Rotas montadas (`app.routes`, código da branch, staging)

```
GET   /api/v1/people-management/hr/vigilante/aptidao
GET   /api/v1/people-management/hr/vigilante/vencimentos
GET   /api/v1/people-management/hr/vigilante/cursos
POST  /api/v1/people-management/hr/vigilante/cursos
GET   /api/v1/people-management/hr/vigilante/equipamentos
POST  /api/v1/people-management/hr/vigilante/equipamentos
POST  /api/v1/people-management/hr/vigilante/equipamentos/{equipamento_id}/entregar
POST  /api/v1/people-management/hr/vigilante/equipamentos/{equipamento_id}/devolver
PATCH /api/v1/people-management/hr/vigilante/employees/{employee_id}/nome-de-guerra
POST  /api/v1/redesign/action/vigilante-curso
POST  /api/v1/redesign/action/vigilante-equipamento
POST  /api/v1/redesign/action/vigilante-entregar
POST  /api/v1/redesign/action/vigilante-devolver
POST  /api/v1/redesign/action/vigilante-nome-de-guerra
menu gestao-de-pessoas: ['vigilante-aptidao', 'vigilante-pessoas', 'vigilante-equipamentos', 'vigilante-curso-novo', 'vigilante-equipamento-novo']
```

### 3.3 Caso de teste no staging (2 fictícios, cargo VIGILANTE, escalados hoje)

`ZZ_TESTE_F05_VALIDO` (CNV válida; curso válido cadastrado **pela rota**) e `ZZ_TESTE_F05_VENCIDO` (CNV válida; reciclagem concluída em 13/03/2024, 24 meses → venceu em 13/03/2026).

**Curl (servidor efêmero, token do contrato):**
```
== POST /hr/vigilante/cursos (curso VÁLIDO para ZZ_TESTE_F05_VALIDO)
{"id":"1a3ee092-…","vence_em":"2028-06-01"}          ← conclusão 01/06/2026 + 24 meses (parâmetro do banco)
== POST curso com conclusão no FUTURO → HTTP 422
== GET /hr/vigilante/aptidao?escalados_hoje=true
{'hoje': '2026-09-12', 'funcoes_exigem_credencial': None, 'total': 30, 'sujeitos': 30, 'aptos': 1, 'inaptos': 29, 'sem_dado': 28}
  ZZ_TESTE_F05_VALIDO  apto= True  []                                   curso_vence_em= 2028-06-01
  ZZ_TESTE_F05_VENCIDO apto= False ['reciclagem vencida em 13/03/2026'] curso_vence_em= 2026-03-13
== GET /hr/vigilante/vencimentos → {'vencendo': 0, 'vencidos': 1, 'sem_dado': 104}
== equipamento
sem serie: HTTP 422
cadastro: {"id":"a226f26a-…"}                          (armamento F05-TESTE-0001, Taurus RT 838 .38)
{"detail":"ZZ_TESTE_F05_VENCIDO está INAPTO para armamento: reciclagem vencida em 13/03/2026"}  → entregar a INAPTO: HTTP 422
{"id":"55aefee4-…","entregue_em":"2026-09-13T03:13:29Z"}                                         → entregar a APTO: HTTP 200
{"detail":"F05-TESTE-0001 já está em posse de alguém — registre a devolução antes"}              → entregar de novo: HTTP 422
GET /equipamentos: armamento F05-TESTE-0001 ativo responsavel= ZZ_TESTE_F05_VALIDO entregue_em= 2026-09-13T03:13:29Z
devolver: HTTP 200
== PATCH nome-de-guerra → {"ok":true,"nome_de_guerra":"FALCÃO"} · ação redesign → {"ok":true} · ação curso sem tipo → HTTP 422
== GET /redesign/data/gestao-de-pessoas
telas: ['vigilante-aptidao', 'vigilante-pessoas', 'vigilante-equipamentos', 'vigilante-curso-novo', 'vigilante-equipamento-novo']
kpis: [('Escalados hoje (sujeitos)', '30'), ('Aptos', '1'), ('Vencidos', '1'), ('SEM DADO', '28')]
painéis: SEM DADO — escalados hoje (28) · VENCIDOS — escalados hoje (1) · Vence em até 30 / 31–60 / 61–90 dias · Régua em vigor
pessoas rows: 54 · ZZ_TESTE_F05_VALIDO … 'Apto' actions: ['Curso','Nome de guerra'] · ZZ_TESTE_F05_VENCIDO … 'Inapto'
equip rows: 1 [('F05-TESTE-0001', ['Entregar'])] · forms: vigilante-curso-novo → /action/vigilante-curso (6 campos), vigilante-equipamento-novo → /action/vigilante-equipamento (4 campos)
== sem token → HTTP 401
```

**Oráculo depois — continua VERMELHO (correto: falta dado real), mas distingue válido de vencido:**

Chave de funções ausente (estado atual = produção):
```
escalados hoje: 30 · sujeitos à régua: 30 (chave de funções ausente → todos) · aptos: 1 · inaptos: 29 (sem dado: 28) · armas sem controle: 0
FALHOU: ZZ_TESTE_F05_VENCIDO (VIGILANTE · Condomínio Ideal Flores da Cidade): reciclagem vencida em 13/03/2026
[+28 "sem dado" iguais aos da seção 1]
29 desvio(s) … exit=1
```
Chave = `["vigilante","escolta","rondante armado"]` (só para provar o escopo; depois removida do staging):
```
escalados hoje: 30 · sujeitos à régua: 2 (funções: vigilante, escolta, rondante armado) · aptos: 1 · inaptos: 1 (sem dado: 0) · armas sem controle: 0
FALHOU: ZZ_TESTE_F05_VENCIDO (VIGILANTE · Condomínio Ideal Flores da Cidade): reciclagem vencida em 13/03/2026
1 desvio(s) … exit=1
```
`ZZ_TESTE_F05_VALIDO` não aparece em nenhuma das duas: o oráculo distingue.

**Caçador:** `TOTAL armas sem série/responsável: 0` (exit 0). Verde de propósito — 0 flags de porte, 0 postos armados hoje; acusa no dia em que o primeiro flag aparecer sem série atrás, ou posto armado tiver escalado sem arma em posse.

Estado deixado no staging: DDL aplicado; parâmetro `vigilante.reciclagem_validade_meses = 24`; chave de funções **ausente** (conservador); os 2 fictícios `ZZ_TESTE_F05_*`, o curso e o equipamento `F05-TESTE-0001` ficaram para o Jordan ver a distinção na tela. Limpeza (quando quiser): `DELETE FROM equipamentos_controlados_alocacoes WHERE equipamento_id IN (SELECT id FROM equipamentos_controlados WHERE numero_serie='F05-TESTE-0001'); DELETE FROM equipamentos_controlados WHERE numero_serie='F05-TESTE-0001'; DELETE FROM shifts WHERE employee_id IN (SELECT id FROM employees WHERE nome LIKE 'ZZ_TESTE_F05%'); DELETE FROM employees WHERE nome LIKE 'ZZ_TESTE_F05%';` (cursos caem por CASCADE).

---

## 4. Fiação pendente para o integrador — linhas EXATAS

### 4.1 DDL de produção (idempotente; aplicar ANTES do bake — sem ele o painel mostra "aguardando dado" e o oráculo acusa "DDL não aplicado")
```sql
ALTER TABLE employees ADD COLUMN IF NOT EXISTS nome_de_guerra varchar(60);
-- employees.cnv_validade JÁ existe (sprint33) — não recriar.

CREATE TABLE IF NOT EXISTS vigilante_cursos (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id     uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  tipo            varchar(40) NOT NULL CHECK (tipo IN ('formacao','reciclagem_patrimonial','reciclagem_escolta_armada','reciclagem_vspp','outro')),
  data_conclusao  date NOT NULL,
  validade_meses  int  NOT NULL CHECK (validade_meses > 0),
  vence_em        date NOT NULL,
  local           varchar(120),
  certificado_url text,
  created_by      uuid,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_vigilante_cursos_employee ON vigilante_cursos (employee_id, vence_em DESC);

CREATE TABLE IF NOT EXISTS equipamentos_controlados (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tipo         varchar(20) NOT NULL CHECK (tipo IN ('armamento','colete')),
  numero_serie varchar(60) NOT NULL UNIQUE,
  modelo       varchar(80),
  calibre      varchar(20),
  status       varchar(20) NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo','manutencao','baixado')),
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS equipamentos_controlados_alocacoes (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  equipamento_id uuid NOT NULL REFERENCES equipamentos_controlados(id),
  employee_id    uuid NOT NULL REFERENCES employees(id),
  entregue_em    timestamptz NOT NULL DEFAULT now(),
  devolvido_em   timestamptz,
  entregue_por   uuid,
  devolvido_por  uuid,
  observacao     text,
  CHECK (devolvido_em IS NULL OR devolvido_em >= entregue_em)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_equip_aloc_aberta
  ON equipamentos_controlados_alocacoes (equipamento_id) WHERE devolvido_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_equip_aloc_employee ON equipamentos_controlados_alocacoes (employee_id);

INSERT INTO system_configs (id, chave, valor, tipo, escopo, prioridade, descricao, grupo, nome)
VALUES (gen_random_uuid(), 'vigilante.reciclagem_validade_meses', '24', 'string', 'global', 'normal',
        'Validade (meses) da reciclagem de vigilante, contada da conclusão do curso (Lei 7.102/83; PF exige 2 anos)',
        'vigilante', 'vigilante.reciclagem_validade_meses')
ON CONFLICT (chave) DO NOTHING;
```
Diferenças em relação à sugestão do briefing (deliberadas): `status` do equipamento é estado FÍSICO (`ativo|manutencao|baixado`) — "em posse" deriva da alocação aberta, garantida por índice único parcial (uma verdade só); `devolvido_por` e `CHECK` de datas adicionados; `cnv_validade` não recriada.

Chave opcional, decisão do DP (o padrão sem ela é "todos sujeitos"):
```sql
INSERT INTO system_configs (id, chave, valor, tipo, escopo, prioridade, descricao, grupo, nome)
VALUES (gen_random_uuid(), 'vigilante.funcoes_exigem_credencial', '["vigilante","escolta"]', 'string', 'global', 'normal',
        'Trechos de cargo/tipo de posto que exigem CNV e reciclagem (lista JSON). Ausente = todos sujeitos.',
        'vigilante', 'vigilante.funcoes_exigem_credencial')
ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, ativo = true;
```

### 4.2 `backend/scripts/qa/checar_regressao.py` — no dict `CACADORES` (roda no container)
```python
    # Arma como FLAG (porte_arma) sem série entregue, ou posto armado com escalado sem arma em posse (frente 05, 12/09/2026).
    "checar_arma_sem_serie.py": lambda s: _n(r"^TOTAL armas sem série/responsável: (\d+)", s),
```

### 4.3 `backend/modules/operacional/models/employee.py` — fora do meu módulo, 1 linha após `cnv_validade = Column(Date, nullable=True)`:
```python
    nome_de_guerra = Column(String(60), nullable=True)  # frente 05 — identificação operacional; nome_social é tratamento
```
Sem ela o serviço já grava/lê por SQL (funciona); com ela o `DPEmployeeUpdate`/ficha do DP passam a enxergar o campo (aí acrescentar `nome_de_guerra: str | None = Field(None, max_length=60)` em `hr/schemas/employee.py` classes `DPEmployeeRead` e `DPEmployeeUpdate` — deixei de fora de propósito para não expor campo que o model não tem).

### 4.4 `celery_app.py`, `main_production.py`, `_modules/*.json`
Nada. Sub-router do aggregator do hr (já montado) e menu via `EXTRA_MENU` do builder. `alembic/env.py` já importa o pacote `modules.people_management.hr.models`, que agora exporta os 3 models.

### 4.5 Oráculo
`scripts/orq/test_*.py` é globado sozinho pela varredura da meia-noite. Vai entrar VERMELHO em produção até o DP cadastrar (ou definir a chave de funções). É o esperado — ver §6.

---

## 5. O que NÃO foi feito e por quê

| Item | Motivo |
|---|---|
| Tipo de reciclagem exigido por posto armado (escolta armada vs patrimonial) | Decisão do dono. Hoje qualquer curso válido conta; o campo `tipo` já está gravado para a régua apertar depois. |
| `porte_arma_validade` do cadastro na régua de aptidão | O controle é a posse por série, não o flag. O flag só é acusado pelo caçador. |
| Model `Employee.nome_de_guerra` e schemas do DP | Fora do módulo autorizado (§4.3). |
| Alarme diário (WhatsApp/sino) de vencimento 30/60/90 | O contrato proíbe notificação real; o dado está exposto em `/vigilante/vencimentos` e no painel. Ligar a um lembrete existente é fiação do integrador, se o dono quiser. |
| Pedido de aprovação (`criar_rascunho`) nas escritas | Briefing diz "escrita normal, não é dinheiro". Mantido escrita direta com auth. |
| Menu/tela no frontend clássico | Só redesign, conforme contrato. |
| Registro em `checar_regressao.py` | Arquivo proibido — linha em §4.2. |

---

## 6. Como o Jordan testa amanhã

1. **Oráculo (staging):** `docker exec -e PYTHONPATH=/app conecta-pro-backend-staging python3 /app/scripts/orq/test_oraculo_vigilante_apto.py` — depois do bake/merge. Antes disso, modo efêmero (§3.1). Esperado: VERMELHO com 28 "sem dado" + `ZZ_TESTE_F05_VENCIDO` vencido; `ZZ_TESTE_F05_VALIDO` não aparece.
2. **Tela:** Redesign → **Gestão de Pessoas** → `Vigilante · Aptidão`: KPIs (30 sujeitos · 1 apto · 1 vencido · 28 SEM DADO), painel "SEM DADO — escalados hoje" com os 28 nomes da §1, painel "VENCIDOS" com o fictício, "Régua em vigor" dizendo que a chave de funções está ausente.
3. **Por pessoa:** `Vigilante · Por pessoa` → linha `ZZ_TESTE_F05_VENCIDO` → botão **Curso** → tipo "Reciclagem patrimonial", conclusão `2026-09-01`, validade já vem 24 → salvar → recarregar: vira **Apto**, vence em 01/09/2028. Rode o oráculo de novo: o fictício some da lista.
4. **Armamento:** `Vigilante · Armamento e colete` → linha `F05-TESTE-0001` → **Entregar** → escolha um agente de portaria (sem CNV) → deve recusar com "INAPTO: CNV sem validade cadastrada; sem curso/reciclagem cadastrado". Escolha `ZZ_TESTE_F05_VALIDO` → aceita; a linha mostra o responsável e a data; botão vira **Devolver**.
5. **Nome de guerra:** mesma tabela por pessoa → **Nome de guerra** → salvar → aparece na coluna e entre parênteses no responsável do equipamento. `nome_social` não muda.
6. **Escopo (decisão do DP):** rodar o INSERT da chave `vigilante.funcoes_exigem_credencial` (§4.1) com a lista que o DP decidir → o painel e o oráculo passam a cobrar só essas funções (medido: 30 → 2 sujeitos).
7. **API direta:** `curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8081/api/v1/people-management/hr/vigilante/aptidao?escalados_hoje=true`.

### O que o DP precisa cadastrar (quem está escalado hoje e SEM DADO)
Se a empresa decidir que essas funções exigem credencial — senão, definir a chave de funções e a lista some:
ADEMIR SALUSTIANO DE SOUZA FILHO · AILTON CÉSAR VASCONCELOS · ANGELA LOPES MACEDO · ANILSON JOSE SEIXAS NEVES · ANTONIO CARLOS VIEIRA · ANTONIO WALCICLEY PEREIRA DA SILVA · BIANCA HELEM DA SILVA MEIRA · CELIANE GARCIA DE SOUSA · EDILENE SALES SOUSA · EDIWILSON CORREA MARQUES · EDWARD JOSÉ ATENCIO DOMINGUEZ · EIDY CULIER DE CASTRO · EULER FELIPE FERNANDES DA COSTA · FRANCISCO RAMON FARIAS DE SOUZA · GEILSON RODRIGUES DE ANDRADE · GERNANES BINDA APARICIO · GRACIENE PEREIRA DE CASTRO · JAQUELINE CARLOS DOS SANTOS · JEOVANE DO NASCIMENTO · JONILSON MARTINS DE SOUZA · KALEL SILVA DE JESUS · LIVIA CARISE PEREIRA CONSENTINE · MAIARA MUNIZ DE SANTOS · MALAQUIAS PEREIRA FERREIRA · MAURICIO ALVES CHAGAS · OSCAR SOARES DA COSTA FILHO · TELMA MARIA LAGES MEIRA · VANDERLICE SANTOS DA SILVA — para cada um: validade da CNV (`employees.cnv_validade`, já existe na ficha) + curso/reciclagem com data de CONCLUSÃO.

---

## 7. Riscos residuais (pré-mortem)

- **Data guardada não vigia ninguém (risco 1):** o oráculo roda à meia-noite e o painel mostra 30/60/90, mas ninguém recebe aviso — ver §5. Enquanto o DP não abrir a tela, o vencimento só aparece no relatório da varredura.
- **A data vai vir do papel (risco 2):** o formulário pede explicitamente "Data de CONCLUSÃO do curso" e recusa data futura, mas não tem como validar contra o certificado. `certificado_url` existe para guardar a prova.
- **Escopo em branco (decisão nova):** com a chave ausente, 28 porteiros ficam "sem dado" para sempre — e o oráculo vermelho vira ruído. A trava é: o DP definir a chave ou cadastrar. Nenhum dos dois é código.
- **Bake (PARTE 0.3):** tudo aqui foi provado em modo efêmero contra o staging. Nada está servindo até `checar_bake_pendente = 0`. DDL de produção precisa entrar antes do primeiro request.
- **Sentry vazio (PARTE 0.1):** exceção no `telas()` cai em `logger.exception` e vira "aguardando dado" na tela — invisível fora do log do container.
