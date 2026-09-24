# DGX V3 — Frota como no APP Frotas do DGX: manutenção, multa→conta/recurso, itens de vistoria, grupos

**Data:** 24/09/2026 · **Branch:** `dgx/v3-frota-app` · **Módulos:** `equipamentos` + `suprimentos`
**Sessão:** agent-v3 · **Sandbox:** `conecta_pro_staging` (container efêmero `teste-dgx-v3`, porta 8243 — parado ao fim)
**Lacunas atacadas:** #6 (itens de vistoria), #7 (manutenção), #8 (multa → conta/recurso), #9 (grupos)

## 1. Estado antes (medido no sandbox, 24/09 08:50)

| O que | Medido |
|---|---|
| `frota_manutencoes` | **não existia** — manutenção de veículo não era entidade |
| `manutencoes` (tela do builder `equipamentos`) | lia só `equipment_maintenances` (patrimônio); veículo não aparecia |
| `frota_multas.payable_id` / `cabe_recurso` / `recurso_*` | **não existiam** — multa nunca virava título e não tinha ciclo de recurso |
| PDF de multa | **não existia** (o DGX tem «PDF detalhes» na tela de multas) |
| Vistoria | 8 campos fixos + 5 áreas fixas em `_frente_10._AREAS`, em código — nada configurável |
| `frota_vistoria_itens` / `frota_vistoria_respostas` | **não existiam**; nada bloqueava a saída de um carro reprovado |
| `sup_grupos` | **não existia**; `nfe_compras_estoque.grupo` = lista fixa de 6 códigos no código da F9 |
| `nfe_compras_estoque` | 147 materiais, **grupo NULO em todos os 147** |
| `sst_uniforme_kits.grupo` | não existia |
| Oráculo `test_oraculo_v3_frota_app.py` | **VERMELHO** — `builder _dgx_v3_frota_app não importa` |

## 2. O que o DGX tem (lacunas #6–#9, trial de 24/09)

- **`/VeiculoManutencoes`**: fornecedor, KM, previsão/liberação, itens tipo peça/serviço com valor, centro de
  custo; **Aprovar**, **Gerar Conta**, **Solicitar Materiais**, e «Gerar troca de óleo» que cria a troca sozinha.
- **Multas**: Gerar Contas (boleto, vencimento), Cabe recurso, Recurso lançado, PDF de detalhes, resultado.
- **APP Frotas → Itens de Vistoria**: texto, ordem, tipo de dado, foto obrigatória, texto obrigatório,
  **impede locomoção**, «não se aplica», grupo de checklist, tipo de veículo.
- **`/GruposAlmoxarifado`**: código, descrição, **grupo pai** — compartilhado por materiais e uniformes.

## 3. O que foi feito

**Arquivos novos**
- `backend/modules/operacional/controllers/redesign_builders/_dgx_v3_frota_app.py` — 6 telas + 10 ações + 1 GET (PDF) + `_ensure`.
- `backend/modules/operacional/services/frota_multa_pdf.py` — PDF padrão-ouro da multa (com `demo()` que roda sozinho).
- `backend/scripts/orq/test_oraculo_v3_frota_app.py` — oráculo.

**Arquivos tocados (enxuto, comentário `# dgx v3` em cada linha)**
- `_dgx_f10_frotas.py`: 5 `ALTER TABLE frota_multas` no DDL; a tela `frota-multas` ganha as ações do V3 e o
  botão de PDF por linha; `frota_saida` consulta `v3.bloqueio_locomocao` antes de aceitar a saída.
- `_dgx_f9_suprimentos.py`: grupo de material deixa de ser lista fixa e vem de `sup_grupos` (select, rótulo e
  filtro, em `materiais` e `estoque`); `material`/`material-editar` passam a **criar** o grupo digitado à mão em
  vez de recusar o material; `sst_uniforme_kits` ganha `grupo` (coluna, select no kit novo, coluna na tela).
- `equipamentos.py` / `suprimentos.py`: plug (router incluído UMA vez, em `equipamentos.py`).

**Reuso (não copiado)** — é o coração desta frente:
`f10.frota_troca` (a troca tipada com `proxima_km` e o `km_proxima_troca_*` do veículo) · `fr10.frota_leitura`
(o KM da liberação sem troca) · `fr10.frota_vistoria` (par chegada×saída, fotos, veredito) · `fr10._form`/`_opts`/
`_int`/`_dec`/`_quem`/`_AREAS`/`_MIME_EXT`/`_FOTOS_DIR` · `rd_action_payable` → `PayableService.create_account`
(título, NUNCA pagamento) · `PayableService.reject_account` (cancelar) · `t5.sup_solicitacao_material` (a
solicitação de material da T5, mesma numeração e mesma fila) · `pdf_branding` + `holerite_pdf._cell/_titulo/_fmt_cpf`.

**DDL que `_ensure` aplica em produção no 1º acesso (idempotente)**
```
CREATE TABLE IF NOT EXISTS frota_manutencoes (veiculo_id, tipo, fornecedor_id, km, previsao_entrada,
   previsao_saida, liberacao, itens jsonb, valor_total, centro_custo, status, aprovado_por/em,
   payable_id, solicitacao_material_id, km_conclusao, concluida_em, observacao, created_at/by)
CREATE INDEX IF NOT EXISTS ix_frota_manutencoes_veiculo
CREATE TABLE IF NOT EXISTS frota_vistoria_itens (codigo UNIQUE, grupo, ordem, texto, tipo_dado,
   foto_obrigatoria, texto_obrigatorio, impede_locomocao, nao_se_aplica, tipo_veiculo, ativo)
CREATE TABLE IF NOT EXISTS frota_vistoria_respostas (vistoria_id, item_id, valor, reprovado, UNIQUE(vistoria,item))
CREATE INDEX IF NOT EXISTS ix_frota_vist_resp_bloqueio ... WHERE reprovado
CREATE TABLE IF NOT EXISTS sup_grupos (codigo UNIQUE, descricao, pai_id → sup_grupos, tipo, ativo)
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS payable_id uuid
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS cabe_recurso boolean NOT NULL DEFAULT false
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS recurso_lancado_em timestamptz
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS recurso_resultado varchar(12) CHECK (... pendente|deferido|parcial|indeferido)
ALTER TABLE frota_multas ADD COLUMN IF NOT EXISTS recurso_observacao text
ALTER TABLE sst_uniforme_kits ADD COLUMN IF NOT EXISTS grupo varchar(20)     -- no DDL da F9 (tabela dela)
SEED frota_vistoria_itens: as 5 áreas da frente 10 (dianteira, traseira, lateral_direita,
   lateral_esquerda, interior), grupo 'Áreas', tipo_dado 'nota' — ON CONFLICT DO NOTHING
SEED sup_grupos: os 6 grupos que a F9 usava (uniforme, epi, material, equipamento, limpeza,
   escritorio) + SELECT DISTINCT de nfe_compras_estoque.grupo — ON CONFLICT DO NOTHING
```

**Telas**

| id | módulo · grupo | o quê |
|---|---|---|
| `frota-manutencoes` | equipamentos | fila com itens, valor, conta e SM; ações **Aprovar** (gated) · **Concluir** · **Gerar conta** (gated) · **Solicitar materiais** · **Cancelar** |
| `frota-manutencao-nova` | equipamentos | veículo, tipo, fornecedor, KM, centro de custo, previsões, itens `tipo \| descrição \| valor` |
| `frota-vistoria-itens` | equipamentos | a tabela que monta a vistoria; editar item na linha |
| `frota-vistoria-item-novo` | equipamentos | novo item (código = chave do campo) |
| `frota-vistoria-nova` | equipamentos | **substituída**: montada pela tabela; vazia = a da frente 10, idêntica |
| `manutencoes` | equipamentos | **substituída**: patrimônio + frota na mesma fila, coluna «Origem» (nada migrado) |
| `frota-multas` | equipamentos | **estendida**: ações Gerar conta / Lançar recurso / Resultado + PDF por linha |
| `sup-grupos` | suprimentos · Materiais & estoque | hierarquia, contagem de materiais, editar na linha |
| `sup-grupo-novo` | suprimentos · Materiais & estoque | código, descrição, pai, tipo |

Deep-links: `/redesign/equipamentos?t=frota-manutencoes` · `?t=frota-vistoria-itens` · `?t=manutencoes` ·
`/redesign/suprimentos?t=sup-grupos`. PDF: `GET /api/v1/redesign/frota/multas/{id}/pdf`.

**Provado por HTTP no sandbox (porta 8243, fixtures `FIXTURE DGX V3` apagadas ao fim)**
- veículo VVV3A33 → manutenção #1 preventiva, itens `servico | Troca de oleo 5W30 | 180,00` e
  `peca | Filtro de oleo | 65,00` → *"total R$ 245,00. Ao concluir, gera a troca de oleo, filtro."*
- **Concluir sem aprovar → 409** («só se conclui o que foi aprovado»). Aprovar → concluir a 10.100 km →
  `frota_leituras` #7 `troca_oleo` 10100 → 20100 e #8 `troca_filtro` 10100 → 20100 (**uma por tipo**), e
  `frota_veiculos.km_proxima_troca_oleo` virou 20100 — o painel «Restam» da frente 10 lê o mesmo número.
- **Gerar conta** → `payable_accounts` R$ 245,00 venc. 10/10/2026 **pendente**; **clicado de novo → mesmo id**,
  1 linha no banco. **Nada pago.**
- **Solicitar materiais** sem material que case → *404 «Material «Filtro de oleo» não encontrado»* (honesto).
  Depois de cadastrar `V3-FILTRO` com grupo digitado à mão `pecas_frota` (que **nasceu** em `sup_grupos`) →
  `SM-202609-0001` aberta com 1 peça; 2ª vez → 409.
- Multa #6 R$ 195,23 (desconto 156,18, venc. 20/10) → **Gerar conta** = R$ 156,18 «com desconto» (antes do
  vencimento); 2ª vez = mesmo id. **Resultado antes de lançar o recurso → 409.** Lançar recurso → deferido →
  título `cancelada` via `PayableService.reject_account`. Multa #7 (sem desconto) → conta R$ 88,38 «valor
  cheio» → recurso → deferido → *"Título 5808d4ca… cancelado no Financeiro"*, `status = cancelada` no banco.
- PDF `GET /frota/multas/6/pdf` → **200, 38.844 bytes, `%PDF-1.4`**.
- Item novo `freio_servico` (sim/não, **impede locomoção**) → vistoria com `aval_freio_servico=nao` →
  *"BLOQUEADO para saída"* → **`frota-saida` 409 nomeando «Freio de servico»**; vistoria nova com `sim` →
  saída #10 aceita. 6 itens respondidos, gravados em `frota_vistoria_respostas`.

## 4. Oráculo

`backend/scripts/orq/test_oraculo_v3_frota_app.py` — afirma (1) manutenção concluída com troca tem
**exatamente uma** `frota_leituras` daquele tipo no KM da conclusão, com `proxima_km > km`; (2) nenhum
`payable_id` aparece em duas origens (manutenção/multa); (3) recurso deferido não deixa título PENDENTE
pendurado nem toca em título PAGO; (4) o formulário de vistoria com a tabela VAZIA é idêntico ao da frente 10
e **cada uma das 5 áreas semeadas rende o mesmo par de campos** (a tabela pode ganhar itens novos — é para
isso que existe); (5) item que impede locomoção reprovado → `frota_saida` recusa com 409 **nomeando o item**
(exercitado de verdade, com fixture, e desfeito); (6) nenhum `sup_grupos.pai_id` órfão, nenhum ciclo, e todo
`nfe_compras_estoque.grupo` não vazio tem grupo.

```
# ANTES (24/09 09:04 — mesmo oráculo contra o backend sem o módulo)
FALHOU: builder _dgx_v3_frota_app não importa: cannot import name '_dgx_v3_frota_app' from
        'modules.operacional.controllers.redesign_builders'
TOTAL v3_frota_app: 1
exit=1

# DEPOIS, COM AS FIXTURES VIVAS (24/09 09:13 — as afirmações 1–3 com dado real)
manutenções concluídas: 1 · trocas conferidas: 2 · contas geradas: 3 · recursos deferidos: 2 ·
itens de vistoria: 6 · grupos: 7
FALHOU: 1 fixture(s) 'FIXTURE DGX V3' sobraram no banco      ← o próprio oráculo cobrando a limpeza
TOTAL v3_frota_app: 1

# DEPOIS, FIXTURES APAGADAS (24/09 09:16) — estado em que o sandbox ficou
manutenções concluídas: 0 · trocas conferidas: 0 · contas geradas: 0 · recursos deferidos: 0 ·
itens de vistoria: 5 · grupos: 6
TOTAL v3_frota_app: 0
OK v3_frota_app: uma troca por manutenção, conta idempotente, recurso deferido cancela sem pagar,
vistoria igual à de ontem, item que impede locomoção bloqueia a saída, grupos sem órfão
exit=0

# VIZINHOS (todos verdes, com as fixtures ainda vivas — o pior caso)
OK frota_operacional: saída única, hodômetro não recua, multa desconta do condutor, Restam fecha, ...
   saídas: 1 (abertas 1) · multas em folha: 0 · trocas conferidas: 2 · requisições realizadas: 0
OK vistoria_par: toda saída compara com a chegada certa ou espera o checklist
OK suprimentos: solicitação→pedido→NF fecha, entrada única por chave, status == régua, posse única, kit ...
   materiais conferidos na régua: 150 · kit JARDINEIRO: 2 × 2 = 4
OK t5: auditoria lê a trilha viva; atender baixa o estoque pelo caminho da F9; ... acesso expira sozinho
```
Autoteste do gerador de PDF: `python3 /app/modules/operacional/services/frota_multa_pdf.py` →
`ok frota_multa_pdf 38882 bytes`.

## 5. O que NÃO foi feito, e por quê

1. **`equipment_maintenances` não foi migrada.** A tela `manutencoes` LÊ as duas fontes com coluna «Origem»;
   nenhuma linha mudou de tabela. Unificar exige a decisão «veículo é `equipment`?», pendente desde a frente 10.
2. **O intervalo da próxima troca é uma régua da casa, não do fabricante.** `INTERVALO_KM` (óleo e filtro
   10.000, pastilha 30.000, pneu 40.000, correia 60.000) num dicionário só, declarado no topo do módulo.
   A manutenção que conclui usa ele; quem quiser outro número usa «Frota · Nova troca», que pede o KM.
3. **O tipo de troca é inferido da descrição do item**, na ordem pastilha → correia → filtro → pneu → óleo
   (por isso «filtro de óleo» é FILTRO). Não inventei um campo «tipo de troca» no item: o DGX também lê da
   descrição, e um campo a mais no formulário seria a primeira coisa que ninguém preenche.
4. **«Solicitar materiais» exige que a descrição da peça case com um material do almoxarifado** (código exato
   ou descrição única, pelo `_material` da T5). Sem isso a solicitação nasceria apontando para nada. O 404 diz
   exatamente o que fazer.
5. **Não há upload de nota fiscal da manutenção** nem anexo — `observacao` é texto. A frente 10 já tem o padrão
   multipart; replicá-lo antes de alguém pedir seria a terceira cópia.
6. **Recurso não tem prazo nem instância.** `recurso_lancado_em` + `recurso_resultado` cobrem o ciclo do DGX;
   1ª/2ª instância e prazo do órgão são processo jurídico, não campo de tela.
7. **A árvore de grupos não tem tela de arrastar/soltar** — o pai é um select, e o ciclo é recusado com 409
   (checado por `WITH RECURSIVE`). Para 7 grupos, arrastar seria enfeite.
8. **`tipo_veiculo` do item de vistoria é texto livre** e filtra pelo valor igual; `frota_veiculos` não tem
   coluna de tipo hoje, então o campo fica pronto e sem efeito prático até alguém cadastrar tipos.
9. **A foto de item novo de vistoria é salva, mas não há miniatura na tela de itens** — a lista de fotos por
   linha já existe em `frota-vistorias` (frente 10) e passou a incluir os itens novos pelo mesmo jsonb.
10. **Nada foi para produção.** Sem bake, deploy ou `docker cp`. O DDL de produção é o do §3, aplicado por
    `_ensure` no 1º acesso à tela. O container `teste-dgx-v3` (porta 8243) foi parado.

## 6. Como o Jordan testa amanhã

1. `Equipamentos → Frota · Novo veículo` — cadastrar o carro (se ainda não houver).
2. `Frota · Nova manutenção` — veículo, tipo «Preventiva», KM atual, e nos itens, uma linha por serviço/peça:
   `servico | Troca de óleo 5W30 | 180,00` e `peca | Filtro de óleo | 65,00`. O total sai sozinho.
3. `Frota · Manutenções` → **Aprovar** (pede o código por e-mail — é ação de dinheiro) → **Concluir** com o KM
   da liberação. Confira em `Frota · Trocas` e `Frota · Painel`: a troca de óleo apareceu com a próxima KM.
4. Na mesma linha, **Gerar conta** → `Financeiro → Contas a pagar` tem o título **pendente** (não pago).
   Clique de novo: ele diz «já gerada — nada duplicado».
5. **Solicitar materiais** → `Suprimentos → Solicitações de material` tem a SM com as peças. Se der 404, o
   nome da peça não bate com nenhum material — use o código da tela `Materiais`.
6. `Frota · Multas` → numa multa com vencimento, **Gerar conta** (usa o valor com desconto se ainda dá tempo) →
   **Lançar recurso** → **Resultado = Deferido**: o título volta como **cancelada** no Financeiro. O botão
   «Multa #N (PDF)» na linha abre o papel timbrado para o condutor assinar.
7. `Frota · Itens de vistoria` — a lista já vem com as 5 áreas de sempre. **Novo item**: código `freio_servico`,
   texto «Freio de serviço», tipo «Sim / Não», **Impede locomoção = Sim**.
8. `Frota · Nova vistoria` — o formulário agora tem o item novo. Responda **Não** nele → a mensagem avisa que o
   veículo está BLOQUEADO. Tente `Frota · Nova saída` com esse carro: **recusa nomeando o item**.
9. Faça outra vistoria respondendo **Sim** → a saída passa.
10. `Suprimentos → Grupos de materiais` — crie `limpeza_pesada` com pai «Limpeza». Em `Materiais`, edite um
    item e escolha o grupo novo; o filtro do topo passa a separar por ele.

## 7. Decisões que só o dono pode tomar

1. **Os intervalos de troca** (§5.2) são chute de mercado. Se a Conecta Mais tem manual ou contrato de
   manutenção, os cinco números mudam num dicionário só (`INTERVALO_KM`).
2. **Manutenção aprovada é gated (OTP)** porque libera gasto. Se a frota crescer e isso virar fila, o gate
   pode sair da aprovação e ficar só no «Gerar conta» — é uma linha.
3. **`equipment_maintenances` × `frota_manutencoes`**: seguem separadas com origem na mesma tela. Unificar é a
   mesma decisão pendente desde a frente 10 («veículo é patrimônio?»).
4. **Recurso deferido cancela o título; e se já estiver pago?** Hoje a tela **não toca** e manda acertar no
   Financeiro (estorno é fluxo de dinheiro, não pode nascer aqui). Confirme que é isso que você quer.
5. **Quais itens de vistoria bloqueiam a saída de verdade?** Freio, pneu, farol? Marcar demais transforma a
   vistoria em porteira fechada; marcar de menos a torna decorativa. Os 5 itens de hoje não bloqueiam nada.
6. **Os 147 materiais estão sem grupo.** A hierarquia está pronta e vazia de uso — vale uma tarde classificando,
   ou o grupo continua sendo enfeite.
