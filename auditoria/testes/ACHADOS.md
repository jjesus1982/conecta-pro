# Bateria E2E como usuário final — 13/09/2026
Ambiente: PRODUÇÃO (erp.conectamais.pro) · escrita liberada pelo Jordan (inclusive irreversível)
Navegador: Playwright MCP · usuário jjesus@conectamais.pro (admin)

## Livro-caixa de atos gravados em produção
| # | Quando | Módulo | Ato | Reversível? | Como desfazer |
|---|--------|--------|-----|-------------|----------------|
| 1 | 14/09 01:00 | Operacional | Escala 10/2026 Prime Arena gerada, submetida, aprovada e PUBLICADA (62 turnos, 4 pessoas) | Sim | É a escala real de outubro do posto; se não servir, o supervisor redesenha em Escalas & Turnos. id `4cfecb51-2aae-48fd-a56f-ffe753318e4e` |
| 2 | 14/09 01:05 | Operacional | Diária ABIDIAS 14/09 Michelangelo R$ 90 lançada **e excluída** | Sim | Já desfeito. VT/VR gerado ficou `cancelado`. |
| 3 | 14/09 01:09 | Operacional | Ocorrência OCO-2026-00005 (Prime Arena, leve) criada **e resolvida** | Sim | Fica no histórico como resolvida. Para sumir: `is_active=false` em `occurrences`. |
| 4 | 14/09 01:13 | Operacional | Comunicado «QA 14/09» criado e PUBLICADO (destinatários: todos) | Sim | Hoje não chega a ninguém (A1-16). Depois do bake, chega. Para tirar: `is_active=false` em `communication_announcements` id `9b001c42-9c92-4a1d-8829-840e27791cbe`. |
| 5 | 14/09 01:2x | CRM | Lead «QA Bateria E2E 14/09» criado | Sim | Descartar em CRM › Definir lead (destino: lost, motivo: teste). |
| 6 | 14/09 01:40 | DP | **Folha 09/2026 MICHELANGELO gerada** — 2 holerites em rascunho, líquido R$ 1.800,22 | Sim | É folha real e faltante de setembro. Rascunho, não paga. Regerar substitui. |
| 7 | 14/09 01:47 | Fiscal | **NFS-e AUTORIZADA** Eletrônica→Patrimonial R$ 9,50 (DPS-2026-1789350431) | — | Ambiente de **homologação** do nacional: não é documento fiscal válido, não precisa cancelar. |
| 8 | 14/09 01:44–47 | Fiscal | 3 DPS rejeitadas pelo governo (E0310 código inválido, E0202 prestador=tomador) | — | Rejeitadas: nada foi gerado. |
| 9 | 14/09 01:5x | Financeiro | PIX de R$ 0,01 tentado | — | **Recusado no gate** (falta conta de origem). Nenhum dinheiro saiu. |
| 10 | 14/09 02:1x | CRM | **Proposta PROP-2026-00123** criada (Patrimonial, R$ 9,50, emitente Eletrônica) | Sim | Rascunho. Excluir em CRM › Excluir proposta, ou deixar como registro do teste. |

## Achados

---
## MÓDULO 1 — OPERACIONAL

### A1-01 · GRAVE · Alocações não dizem ONDE a pessoa está alocada
**Tela:** Operacional › Escalas & Turnos › Alocações
**Sintoma:** a coluna «Cliente / Posto» sai `—` em TODAS as 73 linhas. A alocação diz
"Ativa" mas não diz onde — que é a única informação que uma alocação precisa dar.
**Provado em dois níveis:** não é render do frontend. O payload do
`GET /api/v1/redesign/data/operacional` já traz `{"v": "—"}` nas 73 linhas.
**Causa raiz (medida no banco de produção):**
```
employee_alocacoes: 73 linhas, 73 com condominio_id preenchido
JOIN clients      → 0 casam
JOIN posts        → 0 casam
JOIN condominios  → casam (215a124b = IDEAL FLORES, 21929c3d = PRIME ARENA, ...)
```
A coluna se chama `condominio_id` e o builder fazia `LEFT JOIN clients c ON c.id=al.condominio_id`.
Tabela errada. É a "convenção codificada" da casa: alguém assumiu que condomínio = cliente.
**Corrigido em:** `redesign_data_controller.py:~327` — join passa a ser em `condominios`.
**Estado:** corrigido no fonte, **aguardando bake** (hot-copy não recarrega Python).

### A1-02 · ATENÇÃO · Posto ativo com zero vigilantes
**Tela:** Operacional › Postos & Presença › Postos
**Sintoma:** «Condomínio Gelain» está `Ativo`, turno `diurno`, **0 vigilantes**.
Bate com a Cobertura em risco, que mostra Conecta Base 0% e Green Hills 25% como `Crítico`.
**Não é defeito de software:** é estado real da operação aparecendo corretamente.
Fica registrado como pendência de operação, não de sistema.

### A1-03 · GRAVE · Rescisão concluída não encerra a alocação — a cobertura mente PARA MELHOR
**Medido no banco:** 4 pessoas com `status` demitido/inativo continuam com `employee_alocacoes.ativo = true`:
DANIEL SOUZA DOS SANTOS (IDEAL FLORES), FERNANDO MIGUEL GOMES DA SILVA (MICHELANGELO),
JONATHAN DO NASCIMENTO MENDES (LARANJEIRAS), KEYSON DA SILVA PINTO (PRIME ARENA — rescisão
CONCLUÍDA em 14/08/2026).
**Efeito:** a coluna «Vigilantes» do Postos conta gente que não trabalha mais ali. Prime Arena
mostra 6; um deles saiu há um mês. A Cobertura em risco usa esse número — ou seja, o alarme
mais importante do módulo está calibrado para otimista.
**Onde corrigir:** concluir rescisão deve encerrar `employee_alocacoes` da pessoa.
**Estado:** NÃO corrigido — mexe no fluxo de rescisão do DP, será testado no módulo 3.

### A1-04 · FALSO ALARME (registrado para não repetir)
Acusei o botão «Gerar» de não disparar nada. Era o meu seletor: `has-text("Gerar")` casa com a
ABA «Gerar escala» antes do botão. Com seletor exato: `POST /operacional/scales/generate → 201`.
Lição: em tela cheia de abas com nome parecido, seletor por texto exato, sempre.

### A1-05 · MÉDIO · Escala gerada nasce sem nome
`POST /operacional/scales/generate` grava `scales.name = ''`. A lista «Escalas em rascunho»
mostra «—» na coluna ESCALA e não dá para distinguir uma escala da outra.
Dá para conviver (as outras telas rotulam por posto+competência), mas é ruído no lugar errado.

### A1-06 · GRAVE · O contador de turnos da escala MENTE — 23 de 34 escalas
**Medido:** `scales.total_shifts` diverge de `count(shifts)` em **23 das 34 escalas (68%)**.
Exemplos: contador 153 × 143 turnos reais; contador 157 × 396; contador 129 × 330.
A escala que acabei de gerar tem 62 turnos no banco e `total_shifts = 0`.
**Efeito:** «Escalas do mês» mostrava «0 turnos» em escala publicada e CHEIA. O «Editor visual»
mostrava «153/153» (parece fechada) numa escala de 143 turnos. O manual que escrevi ensinava
a confiar nessa coluna — ensinava a confiar num número errado.
**Corrigido (3 pontos):**
- `operacional.py:~1034` «Escalas do mês» → conta de `shifts`
- `operacional.py:~1791` «Editor visual» → conta turnos e preenchidos de `shifts`
- `operacional.py:~251` evento de publicação → usa o `n_turnos` já contado, não o contador
**Estado:** corrigido no fonte, aguardando bake.

### A1-07 · MÉDIO · N+1 no carregamento de qualquer tela do operacional
Toda navegação dispara **27 GETs** separados de `/api/v1/clients/{id}/condominiums`, um por
cliente. São 27 viagens de rede para montar um seletor. Não quebra nada; pesa em 4G.

### T1 · FLUXO DA ESCALA — PASSOU
Gerar → submeter → aprovar → publicar, pela tela, como usuário:
```
POST /operacional/scales/generate        → 201   (62 turnos, 01–31/10, 4 pessoas, 12x36)
POST /redesign/action/escala-submeter    → 200
POST /redesign/action/escala-aprovar     → 200
POST /redesign/action/escala-publicar    → 200
```
Banco confirma: status `published`, `approved_by`/`approved_at`/`published_by`/`published_at`
preenchidos. A trava «escala sem turnos — gere os turnos antes de publicar» existe e conta
`shifts` de verdade (não o contador furado). Bom desenho.
**Ressalva de UX:** nenhuma confirmação visível na tela após cada ação. O `okMsg` existe no
contrato da tela mas não apareceu no texto da página em 8 s de espera.

### A1-08 · MÉDIO · Excluir diária não mostra de QUEM é a diária
**Tela:** Operacional › Diaristas › Excluir diária
O seletor rotula `POSTO · FUNÇÃO · DATA` — sem o nome da pessoa. Duas diárias do mesmo posto,
mesma função e mesmo dia ficam indistinguíveis. Numa tela cuja única ação é apagar, isso é
convite a apagar a diária errada. Sugestão: incluir o nome no rótulo.

### A1-09 · NÃO É DEFEITO (medi errado primeiro, fica o registro)
Acusei o VT/VR de virar pagável órfão após excluir a diária. Contei `count(*)=1` e concluí que
tinha sobrado. Olhando o STATUS: o registro foi para `cancelado`, não apagado — a exclusão
cascateia certo e ainda preserva o rastro de auditoria. Desenho correto.
Lição: contar linha não é medir estado. Ver o status antes de acusar.

### T1-b · FLUXO DA DIÁRIA (lançar → atravessar → excluir) — PASSOU
```
POST /redesign/action/diaria          → 200   diaria_lancamentos #623, R$ 90,00
                                              (valor derivado da tabela por função/turno — não digitado)
   ↳ gera na hora  financial_pagamentos_diaristas  vt_vr R$ 32,00 origem 'diarias_dia'
POST /redesign/action/diaria-excluir  → 200   #623 removida, VT/VR → 'cancelado'
```
**Travessia Operacional → Financeiro: CONFIRMADA.** O VT/VR do dia nasce junto com a diária e
aparece em Financeiro › Pessoas & Folha na data certa.
**O valor de R$ 90 NÃO vira pagável sozinho** — espera a ação «Programar diárias do mês»
(origem `diarias`, tipo `diaria_mensal`). É desenho, não defeito: o card «Total pendente»
mostra «Diária mensal» separado do VT/VR. Mas quem olha só o dia vê R$ 256 e pode achar que
é tudo o que o dia deve.

### T1-c · FLUXO DA OCORRÊNCIA — PASSOU, com travessia confirmada
```
POST /redesign/action/occurrence          → 200   OCO-2026-00005 criada
POST /redesign/action/occurrence-resolve  → 200   status 'resolvida'
```
Banco confirma o ciclo inteiro: `corrective_action`, `resolution_notes`, `resolved_by_id`,
`resolved_at`. A trava de descrição mínima (10 caracteres) existe e funciona.
**Travessia Operacional → Área do Cliente: CONFIRMADA**, na aba **Chamados**
(«Ocorrências e chamados»: CÓDIGO, TÍTULO, TIPO, SEVERIDADE, STATUS, QUANDO).
**Correção do manual 01:** eu escrevi que a ocorrência aparece na Área do Cliente — aparece,
mas em **Chamados**, não em «Operação». A aba Operação do síndico lista só rondas.

### A1-11 · GRAVE · Fuso misturado dentro da MESMA ocorrência
**Medido:** OCO-2026-00005 gravou `occurred_at = 2026-09-13 21:09:17` e
`reported_at = 2026-09-14 01:09:17`. Mesmo instante, quatro horas de diferença — e dias
diferentes. Nas 5 ocorrências da base: 2 com exatamente 4h de diferença, 1 em dias distintos.
**Causa raiz — duas linhas vizinhas** em `occurrence_repository.py:72-73`:
```python
occurred_at=data.occurred_at or datetime.now(),   # hora LOCAL do container
reported_at=datetime.utcnow(),                    # UTC
```
Ambas as colunas são `timestamp without time zone` e a convenção da casa é UTC
(o `created_at` do Postgres bate com `reported_at`, não com `occurred_at`).
**Efeito:** o KPI «ocorrências (7d)» compara `occurred_at >= now()-interval '7 days'` — uma
ponta em hora de Manaus contra outra em UTC. Erra na virada do dia, que é justamente quando
a operação de segurança mais registra.
**Corrigido:** `occurred_at` passa a usar `datetime.utcnow()`. Aguardando bake.

### A1-12 · MÉDIO · Ocorrência nasce sem empresa
As 5 ocorrências da base têm `empresa_id` NULL. Num grupo de dois CNPJs, ocorrência sem
empresa não pode ser filtrada por empresa nem entra em relatório por CNPJ.

### T1-d · FLUXO DO COMUNICADO — PASSOU no gravar, FALHOU no atravessar
```
POST /redesign/action/comunicado-criar     → 200
POST /redesign/action/comunicado-publicar  → 200   status real devolvido: 'published'
```

### A1-13 · MÉDIO · A MESMA coluna de status tem três grafias
`communication_announcements.status`: **`publicado` (10 linhas), `cancelled` (2), `published` (1)**.
A de 'published' é a que a ação de publicar grava HOJE. O leitor da lista pintava de verde só
quem tivesse 'publicado' — ou seja, todo comunicado publicado de agora em diante aparece cinza,
como se não tivesse sido publicado.
**Corrigido:** os dois leitores (lista de Comunicados e Comunicados—leituras) aceitam as duas
grafias. **NÃO normalizei as 10 linhas antigas** — reescrever status em produção é migração,
e é decisão sua. Sugestão: `UPDATE ... SET status='publicado' WHERE status='published'`.

### A1-14 · MÉDIO · Comunicado publicado nasce com 0 destinatários
Publiquei com `destinatarios_tipo = 'all'` e ficou `total_destinatarios = 0`,
`total_visualizacoes = 0`. Os comunicados antigos mostram 44 destinatários.
É o mesmo mal do A1-06: contador denormalizado que ninguém atualiza na hora de publicar.
Efeito prático: a tela «Leituras» divide por um total zero — não dá para saber quem falta ler.

### A1-15 · GRAVE · Fuso misturado também no comunicado
`data_publicacao = 2026-09-13 21:13:59` (Manaus) contra `created_at = 2026-09-14 01:13:32` (UTC),
no mesmo registro. É o A1-11 numa segunda tabela — o padrão se repete: quem escreve usa
`datetime.now()`, quem audita usa `utcnow()`. Vale uma varredura por `datetime.now()` no
backend inteiro (fica como recomendação, não fiz).

### A1-16 · CRÍTICO · Comunicado publicado hoje é INVISÍVEL para o colaborador
**O teste:** publiquei um comunicado pelo Operacional (200 OK, aparece na lista de Comunicados
e em Comunicados—leituras). Abri o Portal do Colaborador › Comunicados: **não está lá.**
Os 10 comunicados antigos aparecem; o recém-publicado, não.
**Causa raiz** — `portal_do_funcionario.py:294`:
```sql
WHERE coalesce(a.is_active,true) AND a.status='publicado'
```
A ação de publicar grava `published`. O portal filtra `publicado`. Nenhum comunicado publicado
a partir de hoje chega a um único colaborador — e ninguém percebe, porque a tela de origem
mostra o comunicado publicado normalmente.
**Impacto de negócio:** comunicado é o canal formal com a equipe. Convocação, mudança de
escala e norma de segurança publicadas hoje não chegam a ninguém, e a empresa acha que
comunicou. Em discussão trabalhista, «foi comunicado» sem leitura registrada não se sustenta.
**Corrigido:** o portal aceita as duas grafias. Aguardando bake.
**Nota:** o seletor de «Publicar comunicado» (operacional.py:1990) já tratava as duas grafias.
Era só o portal e os dois selos.

### A1-17 · INFORMATIVO · 314 usos de `datetime.now()` no backend
Contados em `backend/modules` (fora de testes). É a superfície do problema de fuso dos
A1-11 e A1-15. Não varri os 314 — muitos podem ser inofensivos. Fica a recomendação de uma
varredura dirigida a tudo que grava coluna `timestamp` de evento.

## MÓDULO 1 — VEREDITO
**O esqueleto funciona.** Escala nasce, é submetida, aprovada e publicada; diária lança,
atravessa para o Financeiro e some quando excluída; ocorrência nasce, resolve e chega ao
portal do cliente. As travas de negócio existem e são boas (escala sem turno não publica;
descrição de ocorrência tem mínimo; exclusão de diária cancela em vez de apagar).

**O que impede liberar hoje:** 1 crítico (A1-16, comunicado não chega a ninguém) e 3 graves
(A1-01 alocação sem posto, A1-06 contador de turnos mentindo em 68% das escalas, A1-11 fuso
misturado). Os quatro estão **corrigidos no fonte e presos até o bake**.

**O que é da operação, não do sistema:** posto ativo sem vigilante (A1-02) e 4 alocações
ativas de gente demitida (A1-03) — esta última faz a cobertura mentir para melhor e será
reaberta no módulo 3, onde a rescisão é testada.

---
## MÓDULO 2 — PONTO (Gestão de Pessoas + DP)

### T2-a · PRESENÇA E FUSO — PASSOU
A tela «Presença hoje» diz explicitamente «(Manaus)» e, medida às **01:18 UTC / 21:18 Manaus**,
continuava no dia 13 — não virou o dia junto com o UTC. É a tela tratando o fuso certo.
Batidas gravadas em `gp_clock_punches` estão em hora de Manaus (19:02 = turno das 19h).

### A2-01 · NÃO É DEFEITO (falso alarme meu, o segundo)
Acusei a aba «Ajustar batida» de abrir vazia. Ela tem 7 campos — eu medi com 8 s de espera e
ela precisava de mais. Medindo direito: **2,8 s até renderizar**. Dentro do aceitável.

### A1-07 (revisado) · MÉDIO · O N+1 custa metade do tempo de tela
Medido: 33 chamadas por tela do financeiro, **27 delas** `/clients/{id}/condominiums`, ocupando
**2,0 s dos 2,8 s** até a tela ficar usável. O backend responde o módulo inteiro em 0,2–2,4 s
(operacional 0,69 · DP 1,04 · financeiro 2,43 · GED 0,23). O gargalo é o N+1 do frontend,
não o servidor. Trocar por uma chamada única corta quase metade do tempo de abertura.

### A2-02 · GRAVE · A confirmação pergunta sempre a mesma coisa, e a coisa errada
**Tela:** DP › Ponto & Jornada › Espelho: calcular/fechar.
Escolhendo «Só calcular (mostra anomalias)» — ação inofensiva — a confirmação diz
«**Fechar** o espelho do mês para todos os colaboradores ativos. Confirma?».
Escolhendo «Calcular e FECHAR» — ação destrutiva — a frase é **idêntica**.
O texto é estático no contrato da tela, e o renderizador não sabe o que foi escolhido.
Uma confirmação que diz sempre a mesma coisa não confirma nada: ou treina a ignorar, ou
assusta na ação inofensiva.
**Corrigido:** texto passa a cobrir os dois caminhos com honestidade.

### A2-03 · GRAVE · Fechar o mês era o comportamento PADRÃO
`FecharMesRequest.fechar: bool = True`. O select «Ação» tem opção vazia; deixando em
«Selecione…», o campo não vai no corpo e o backend **fecha o mês por omissão**.
Junto com o A2-02 (a confirmação sempre diz «Fechar»), o caminho do acidente estava aberto.
*Mitigação que já existia e é boa:* só fecha espelho **sem anomalia aberta**; os demais voltam
em `bloqueados`. Isso limitou o estrago.
**Corrigido:** `fechar: bool = False`. Fechar o mês passa a exigir escolha explícita.

### A2-04 · CRÍTICO · O cálculo do espelho da Portaria 671 estava MORTO (HTTP 500)
```
POST /api/v1/people-management/hr/ponto/fechar-mes  {"mes":9,"ano":2026,"fechar":false}
→ HTTP 500 em 0,087 s
```
**Causa raiz, do traceback:**
```
psycopg2.errors.UndefinedFunction: operator does not exist: character varying = uuid
... FROM time_sheets WHERE ... AND employee_id NOT IN (SELECT id FROM employees ...)
```
`time_sheets.employee_id` é **varchar**; `employees.id` é **uuid**. O filtro de isolamento de
homologação foi aplicado sem CAST nessa metade do UNION. A metade de cima não quebra porque
`gp_clock_punches.employee_id` já é uuid.
**Alcance:** o endpoint devolvia 500 em QUALQUER competência — calcular e fechar o espelho do
ponto não funcionava para ninguém. É a função mais exigida legalmente do módulo.
**Varri o resto:** 11 tabelas têm `employee_id` varchar; verifiquei os 10 outros pontos com o
mesmo filtro — todos rodam sobre `gp_clock_punches` (uuid). Só este estava quebrado.
**Corrigido** com `CAST(id AS TEXT)`. Validado no banco: a consulta agora roda e devolve
**51 colaboradores** na competência 09/2026.

---
## MÓDULO 4 — COMERCIAL (CRM)

### T4-a · LEAD — PASSOU
`POST /redesign/action/lead → 200`. Lead «QA Bateria E2E 14/09» criado com origem, valor
estimado e observação.

### A4-01 · GRAVE · O funil tem um degrau que não existe: não há como criar CLIENTE pela tela
**O teste:** criei o lead pela tela. Abri «Nova proposta». O campo Cliente* é um select de 27
clientes existentes — e o lead recém-criado **não está lá**. Lead não é cliente.
**Procurei a porta:** varri os 6 módulos onde faria sentido (CRM, Financeiro, Área do Cliente,
Configurações, Empresas, Operacional) atrás de um formulário que faça POST em `/clients`.
**Não existe nenhum.**
O CRM tem CTA para criar lead, proposta, contrato, comissão, atividade, produto, aditivo,
modelo de contrato, item de proposta e até **condomínio** — a tela «Clientes» é a única
lista relevante **sem** botão de criar.
**O que «Definir lead» faz:** qualifica e, opcionalmente, abre OPORTUNIDADE (`INSERT INTO
opportunities`). Não cria cliente. Existe `converter_lead_para_crm` no marketing_controller e
`_link_lead_client` no pipeline_sync, mas nenhuma tela os chama.
**Consequência prática:** um lead novo nunca vira proposta sem alguém criar o cliente por fora
(API, banco ou tool do conector). O funil «lead → proposta → contrato» que o manual descreve
está interrompido no primeiro salto para todo cliente novo.
**NÃO corrigi:** criar tela de cadastro de cliente é feature, não conserto — e cliente tem
CNPJ, endereço, contato e vínculo com condomínio. É decisão sua como deve ser o formulário.

### A4-02 · CRÍTICO · Criar proposta pela tela estava impossível (HTTP 500)
```
POST /redesign/action/proposal → 500
asyncpg.exceptions.NotNullViolationError:
  null value in column "empresa_id" of relation "proposal_items" violates not-null constraint
```
**Causa raiz e a ironia dela:** o repositório `proposal_repository.py:226` já tinha o comentário
> «NOT NULL no banco: quem chega aqui sem empresa já foi recusado antes, com mensagem.
>  Repassar `None` daria erro de integridade sem explicação.»

A suposição estava errada. A ação `/action/proposal` do redesign **não recusava nada**: montava
`ProposalItemCreate(name=…, quantity=1, unit_price=…)` sem empresa, mandava `None` para o banco,
e o erro de integridade virava exatamente o 500 sem explicação que o comentário temia.
**Detalhe que explica o desenho:** a tabela `proposals` **não tem** `empresa_id`. Quem carrega a
empresa é o ITEM. O pai não sabe de qual CNPJ sai a proposta; o filho exige saber.
E `users` não tem vínculo com empresa — então não dava para inferir. Os 175 itens existentes se
dividem entre `conecta_eletronica` (160) e `conecta_patrimonial` (15): as duas emitem de verdade.
**Corrigido em três pontos** (sem chutar um padrão, porque a escolha é de negócio):
1. campo **«Empresa emissora*»** no formulário, carregado de `empresas` (ordenado por principal);
2. guarda na ação: sem empresa, **400 com mensagem** em vez de 500 mudo;
3. a empresa escolhida é repassada ao `ProposalItemCreate` (o schema já aceitava o campo).
**Alcance:** enquanto isso durou, nenhuma proposta podia ser criada pela tela. As 10 propostas
existentes são anteriores à restrição NOT NULL.

### T2-b · ESPELHO DA PORTARIA 671 — PASSOU depois do bake
```
POST /people-management/hr/ponto/fechar-mes {"mes":9,"ano":2026,"fechar":false}
→ HTTP 200 em 1,22 s   (antes: 500 em 0,08 s)
```
Resposta: 51 processados · **0 fechados · 43 bloqueados · 0 erros** · `pode_fechar_todos: false`
com o aviso «Existem espelhos com anomalia ABERTA — corrija/justifique antes do fechamento».
**O motor está certo e é bom:** recusa fechar mês com anomalia, e a anomalia vem nomeada, datada
e descrita em português, com o id da batida. Exemplo real:
> «Entrada às 18:00 sem saída correspondente (próxima batida é outra entrada às 18:26).»

### A2-05 · OPERAÇÃO (não é software) · 182 anomalias de ponto abertas em 09/2026
Medido na resposta do próprio motor: **43 dos 51 colaboradores** têm anomalia aberta.
| Tipo | Qtd |
|---|---|
| `par_incompleto` (entrada sem saída) | 68 |
| `saida_sem_entrada` | 68 |
| `dia_sem_batida` | 46 |
| **total** | **182** |

Dias piores: 09/09 (21) · 11/09 (17) · 02/09 (17) · 08/09 (16) · 05/09 (16).
Pessoas com mais: ANTONIO CARLOS VIEIRA (16) · ANILSON JOSE SEIXAS NEVES (10) ·
NAILSON GARCIA GOMES (10) · CELIANE GARCIA DE SOUSA (10) · ADAILSON SERRA ALVES (9).
**Leitura:** o mês de setembro NÃO pode ser fechado hoje, e portanto a folha de 09/2026 não tem
base. O padrão «entrada às 18:00 e outra entrada às 18:26» aparece muito — é a marca da
tentativa repetida no reconhecimento facial, o mesmo sintoma das falhas medidas em 11/09.
Isto é fila de trabalho do DP, não defeito de código — mas é o que separa o sistema de fechar
o mês.

---
## VERIFICAÇÃO PÓS-BAKE (a prova de que as correções pegaram)
Bake blue/green concluído às 21:33. Reabri cada tela pelo navegador:

| Achado | Antes | Depois (medido na tela) |
|---|---|---|
| A1-01 Alocações sem posto | `—` nas 73 linhas | `LARANJEIRAS`, `IDEAL FLORES`, … |
| A1-06 Contador de turnos | escala nova com `0` turnos | `62` e `62/62`; a de 09/2026, `97/97` |
| A1-16 Comunicado invisível | portal mostrava 10, sem o novo | portal mostra **11**, com o novo |
| A2-04 Espelho morto | `HTTP 500` em 0,08 s | `HTTP 200` em 1,22 s, 51 processados |

*(A2-02 e A2-03, texto de confirmação e padrão seguro do fechar-mês, também entraram no bake.
A1-11 fuso da ocorrência idem — só aparece na próxima ocorrência criada.)*

---
## MÓDULO 3 — DEPARTAMENTO PESSOAL

### T3-a · GERAR FOLHA — PASSOU, e é a melhor tela que vi até agora
```
POST /redesign/action/folha-gerar → 200
"Folha 09/2026 — MICHELANGELO GERADA no Conecta PRO: 2 holerite(s), líquido R$ 1.800,22,
 FGTS R$ 306,68. Status rascunho — gerar não paga; o pagamento segue no Financeiro com OTP."
```
A confirmação é **específica**: «Isto calcula e GRAVA a folha de todos os CLT ativos da
competência (rascunho). Regerar substitui a geração anterior. Confirmar?» — diz o que faz e
avisa que regerar substitui. É o oposto do A2-02. E a resposta diz o que NÃO faz: gerar não paga.
Abriu o PDF da folha em nova aba. Banco confirma 2 holerites `draft`.

### A3-02 · MÉDIO · Folha gera sobre mês de ponto ABERTO, sem aviso
O espelho de 09/2026 está `calculado` (51), **não `fechado`** — são 182 anomalias abertas.
A folha gerou assim mesmo. Pior: **ANTONIO CARLOS VIEIRA**, que tem **16 anomalias**, saiu com
holerite de R$ 953,94 como se o mês dele estivesse limpo.
**Ressalva honesta:** gerar RASCUNHO sobre mês aberto é defensável — o sistema diz «rascunho» e
diz que não paga. O que não pode é FECHAR ou PAGAR assim. A trava certa é no pagamento, e isso
será testado no módulo 5.
**Sugestão (não implementei, é regra de negócio):** a tela avisar «este mês tem N anomalias
abertas» antes de gerar. O dado já existe e sai do mesmo motor.

### A3-01 · MÉDIO · 94 holerites de meses FUTUROS poluindo o pareamento
`hr_payslips` tem 47 holerites de **11/2026** e 47 de **12/2026** — criados em **03/08/2026**.
Hoje é 13/09. Os meses reais que faltam (09 e 10) não existiam até este teste.
**Não são 13º:** conferi as rubricas — não têm nenhuma.
**Efeito:** a tela «Conecta × Portte» abre na competência mais recente, que é **12/2026**, e
mostra divergências «só Conecta» para 47 pessoas de um mês que não aconteceu. A tela de
divergência mais importante do DP abre cheia de ruído.
**Sugestão:** desativar/apagar os 94 holerites de 11 e 12/2026. É decisão sua — não mexi.

### A3-03 · MÉDIO · Holerite sem rubrica em todos os meses, menos março
`hr_payslip_items` tem 560 linhas, **todas de 03/2026** (51 holerites). Julho (102 holerites) e
agosto (66) têm valor líquido e **zero rubricas**.
O `folha_pdf_parser.py` popula essa tabela a partir do PDF da Domínio — rodou uma vez, em março.
**Efeito:** o detalhamento do contracheque no Portal do Colaborador (`PayslipItem[]`) fica vazio
para todo mês que não seja março. A pessoa vê o líquido e não vê de onde ele vem.
*(A folha em si não depende disso: base, INSS, FGTS, descontos e líquido estão em colunas de
`hr_payslips`. É o detalhamento que falta.)*

### A3-04 · MENOR · Dois seletores de mês, dois formatos
«Espelho: calcular/fechar» usa `01`…`12`. «Gerar folha» usa `Janeiro`…`Dezembro`.
Mesma competência, mesmo módulo, duas linguagens.

---
## MÓDULO 6 — FISCAL (NFS-e)

### T6-a · EMISSÃO DE NFS-e — PASSOU, e é real
Conforme você pediu, notas cruzadas entre os dois CNPJs, abaixo de R$ 10,00.
```
POST /government/nfse-nacional/emitir  (dry_run=false)
  Eletrônica → Patrimonial · R$ 9,50 · código 110201
→ 201  {"status":"autorizada","id_dps":"DPS-2026-1789350431"}
```
**É emissão de verdade, não simulação.** O log mostra o caminho inteiro:
certificado A1 carregado (`JORDAN SANTOS DE JESUS LTDA:35710481000103`, válido até 13/01/2027)
→ XML assinado (1.443 bytes) → transmitido ao **SEFIN Nacional** → resposta do governo.
ISS calculado certo: R$ 0,475 sobre R$ 9,50 (5%).
**Ambiente:** `homologacao` (`sefin.producaorestrita.nfse.gov.br`) nas duas empresas — então a
nota **não é documento fiscal válido**, é o ambiente de testes oficial. Isso torna o seu pedido
seguro, e é bom saber: **o sistema nunca emitiu nota em produção.**

### A6-01 · MÉDIO · A tela pede JSON cru
«Tomador (JSON)» e «Serviço (JSON)» são textareas de JSON. Vêm com modelo pré-preenchido, o que
ajuda, mas ninguém do fiscal vai editar JSON à mão. É tela de desenvolvedor.

### A6-02 · GRAVE · O valor PADRÃO do formulário é um código que o governo rejeita
O campo Serviço vem com `"codigo_tributacao_nacional": "1.1701.10.00"`. Usei como veio:
```
E0310 — O código de tributação nacional informado não existe conforme a lista de serviços
        nacional do Sistema Nacional NFS-e
```
O formato aceito tem **6 dígitos** (`110201`, que é o que as 112 notas reais usam).
Quem confiar no modelo da tela toma rejeição na primeira tentativa.
**Agrava:** a tabela `codigos_servico` existe e está **VAZIA** — não há catálogo para escolher.
O usuário precisa saber o código de cabeça.

### A6-03 · GRAVE · O erro do governo era jogado fora e virava «Erro interno»
O controller tem um caminho que levanta **422 com a rejeição exata do governo** — e logo abaixo
um `except Exception` que capturava a própria HTTPException e devolvia
`500 {"detail":"Erro interno ao preparar DPS"}`.
A causa (`E0310`, com descrição) ficava só no log. Quem podia corrigir lia «erro interno».
**Corrigido:** `except HTTPException: raise` antes do genérico.

### A6-04 · GRAVE · A Patrimonial NÃO consegue emitir nota
Testei o sentido inverso (Patrimonial → Eletrônica, R$ 8,75) passando `prestador` na requisição.
Rejeitado:
```
E0202 — Na emissão da NFS-e não é permitido que o prestador seja igual ao tomador
```
E o `idDPS` devolvido pelo governo contém **35710481000103** — o CNPJ da **Eletrônica** — mesmo
eu tendo informado o da Patrimonial.
**Causa raiz** (`nfse_nacional_service.py:_get_manager`): o manager é construído com
`self.cert_path` e `self.cnpj` — configuração fixa da instância, **cacheada** — e não com o
prestador recebido em `emitir_dps`. O serviço monta o objeto `PrestadorNacional` com o CNPJ
informado, mas **assina com o certificado da outra empresa**, e o nacional rejeita a divergência.
**E o certificado existe:** `empresas.certificado_a1_path` tem `patrimonial.pfx`, válido até
06/07/2027. O certificado está lá; o código não o escolhe.
**Consequência:** num grupo de dois CNPJs, só a Eletrônica emite. E a **Patrimonial é justamente
a que faz vigilância, portaria e limpeza** — os serviços que mais faturam.
**NÃO corrigi de propósito:** escolher certificado por prestador é caminho fiscal. Emitir nota
assinada pela empresa errada é pior que não emitir. O conserto é claro (selecionar cert e CNPJ
pelo prestador, e não cachear um manager único), mas quero seu aval antes de mexer nisso.

---
## MÓDULO 5 — FINANCEIRO

### T5-a · O GATE DO DINHEIRO — PASSOU, e é o melhor desenho do sistema
Tentei um PIX de R$ 0,01. A tela pediu confirmação específica:
> «Isto vai ENVIAR um PIX via Inter. Gerar o código OTP para o Jordan confirmar?»

e o rodapé avisa: «Ação protegida por OTP humano — ao enviar, um código vai ao e-mail do Jordan».
O boleto vai além e nomeia o risco de CNPJ:
> «Isto vai PAGAR um boleto. Confira a conta escolhida — **Cora é a Patrimonial, Inter é a
> Eletrônica, são CNPJs diferentes**»

**E o backend recusou o pagamento:**
```
400 "Escolha de qual conta sai o pagamento: Cora (Patrimonial) ou Inter (Eletrônica).
     São CNPJs diferentes e o sistema não escolhe por você."
```
Uma recusa a adivinhar sobre dinheiro entre duas pessoas jurídicas. É exatamente o que se quer.
Contraste com o A2-02 (confirmação estática do espelho): aqui o texto é específico da ação.
**Nenhum centavo saiu neste teste.**

### A5-01 · GRAVE · A tela de PIX é impossível de usar
O backend exige a conta de origem; **o formulário do PIX não tem esse campo**. Toda tentativa
morre no mesmo 400, e não há onde escolher a conta.
**Causa raiz:** o contrato da tela usa a flag `"originField": true` para o renderizador desenhar
o seletor «Conta de origem». Conferi as cinco telas de saída de dinheiro:
| Tela | originField |
|---|---|
| pagar-boleto | **True** |
| pagar-darf | **True** |
| pagar-gps | **True** |
| transferir-ted | **True** |
| **enviar-pix** | **ausente** |
O PIX é o único fora do padrão — e é o meio mais usado.
**Corrigido:** `"originField": True` em `enviar-pix`. Aguardando bake.

---
## MÓDULOS 7 a 13 — VARREDURA

### T7 · GED / KITS — PASSOU
Visão geral coerente com o banco: 4.641 arquivos, 926 assinados, 3.715 pendentes.
«Entrega dos kits» lista um condomínio por linha, com canal e destinatário, fonte declarada
(`ged_document_kits`). «Kits de documentos» mostra completude, status e os quatro botões do
caminho (Gerar PDFs · Solicitar assinaturas · Anexar NFS-e · Enviar).

### A7-01 · MÉDIO · Dá para enviar kit incompleto ao cliente, de dentro da Área do Cliente
Na Área do Cliente › Documentos, um kit em **40% «Em montagem»** exibe os botões
**«Montar no Drive»** e **«Enviar»**, sem nenhum aviso de que falta peça.
Enviar kit incompleto é o erro que o síndico percebe antes de nós. A completude já está na
mesma linha — bastaria a tela impedir, ou ao menos perguntar.

### T9 · PORTAL DO COLABORADOR — PASSOU, e é honesto
«Bater ponto» responde: «Seu usuário não está vinculado a um colaborador — nada a registrar.»
Em vez de mostrar zero e parecer defeito, nomeia o motivo. É o comportamento certo.
**Achado operacional:** «Assinaturas pendentes» mostra o contrato **CTR-2026-00022**
(Associação de Proprietários) esperando a **sua** assinatura desde **11/09**, com validade até
**11/10**. Passou despercebido até esta varredura.

### A12-01 · GRAVE · Medida disciplinar pedia o UUID do colaborador digitado à mão
**Tela:** RH › Nova medida disciplinar.
Campos: «Colaborador (id)*» (texto), «Nome do colaborador*» (texto), «CPF*» (texto), «Cargo».
O usuário digitava o **UUID**, o nome e o CPF — dados que o sistema já tem. Todo o resto do
sistema usa seletor.
**Por que importa:** é o documento que vai para a pasta funcional e pode virar justa causa.
Id ou CPF digitado errado é medida aplicada à pessoa errada.
**Corrigido:** «Colaborador*» virou **select** dos ativos, rotulado «NOME — CPF», para o id
nunca mais ser digitado. *(Nome e CPF continuam campos separados; preenchê-los sozinho exigiria
mexer no renderizador — fica registrado como pendência menor.)*

### T13 · EQUIPAMENTOS — confirmado vazio, como o manual 12 já dizia
Nenhuma tela de cadastro; «Patrimônio» segue em «Nenhum registro ainda». Sem novidade.

### T1-e · A ESCALA 12x36 GERADA É LEGALMENTE CORRETA — passou com folga
Auditei no banco a escala que gerei (Prime Arena, 10/2026, 62 turnos, 4 pessoas):
| Colaborador | Dias seguidos | Intervalos de 2 dias |
|---|---|---|
| ANTONIO DINIZ ASSIS DOS SANTOS | **0** | 14 |
| CARLOS EDUARDO DA SILVA FAÇANHA | **0** | 15 |
| MALAQUIAS PEREIRA FERREIRA | **0** | 15 |
| RILEM FERREIRA DE SOUZA | **0** | 14 |

**Zero** dias consecutivos para qualquer pessoa; **todos** os intervalos são de exatamente
dois dias — as 36 horas de descanso da 12x36. Turnos gravados como 07:00–19:00 e 19:00–07:00,
12 horas cada. Duas pessoas por dia, 31 dias, 62 turnos.
O gerador não só funciona: ele respeita a regra na letra.

### A7-02 · MENOR · Contracheque não chega sozinho ao GED
`hr_payslips` tem 66 holerites em 08/2026; `ged_contracheques` tem **1**. Em 06/2026 são 49.
A ação «Contracheques em lote» precisa ser rodada — não é automática ao gerar a folha.
É desenho, mas cria a pegadinha: folha gerada ≠ contracheque disponível ao colaborador.

---
## MÓDULO 10 — SAÚDE OCUPACIONAL

### A10-01 · GRAVE · Três telas do mesmo módulo, três números para «ASO vencido»
| Tela | Diz | O que realmente conta |
|---|---|---|
| Visão geral › ASO por status | **44** | linhas com `status='vencido'` |
| Alertas SST | **88** | **todo** ASO vencido da história |
| *(o número acionável)* | **25** | pessoas **ativas** cujo **último** ASO venceu |

**Por que 88 é o pior dos três:** conta papel, não pessoa. Alguém com três exames antigos
aparece três vezes. A tela que deveria ser a fila de trabalho do SST inflava a urgência em
**3,5×** — e uma fila que exagera é uma fila que ninguém trata.
**O sistema já sabia o número certo:** a aba «Exames», no mesmo arquivo, usa a lógica correta
(último ASO por colaborador ativo) e tem até um comentário dizendo «números batem (25)».
**Corrigido:** Alertas passa a contar pessoa ativa com último ASO vencido — **25** — e o rótulo
agora diz «colaborador(es) ativo(s) com ASO vencido», não «ASOs vencidos».

### T10 · O QUE PASSOU NO SST
- **Estabilidade** funciona e é precisa: CINTIA BEZERRA OLIVEIRA, acidente de trajeto,
  garantia até **21/05/2027**. É a consulta que evita demitir quem não pode ser demitido.
- **Riscos jurídicos** (módulo 11): exposição estimada **R$ 339.057,57** em 65 de 65
  colaboradores, quebrada por verba, com o aviso «estimativa, não provisão» na própria tela.

---
## VERIFICAÇÃO PÓS-BAKE 2

| Achado | Antes | Depois (medido na tela) |
|---|---|---|
| A4-02 Proposta com 500 | `NotNullViolationError` | **PROP-2026-00123 criada** · item R$ 9,50 com `empresa_do_item = CONECTAMAIS ELETRONICA LTDA` |
| A5-01 PIX sem conta | formulário sem o campo | campo **«Conta de origem — de qual empresa»** presente |
| A6-03 erro engolido | `500 "Erro interno"` | 422 com o código do governo *(entra no próximo teste de rejeição)* |
| A12-01 UUID digitado | campo de texto | **select** «Colaborador*» com «NOME — CPF» |

*(A sessão do navegador caiu durante o bake — os containers foram recriados. Refiz o login e
revalidei. Vale como lembrete: bake derruba sessão de quem está usando o sistema.)*

---
## MÓDULO 8 — ÁREA DO CLIENTE · O TESTE DE VAZAMENTO (que eu tinha dado como impossível)

Eu havia registrado que não daria para testar o portal como síndico por falta de credencial.
Estava errado: existe `POST /portal/access-management/{client_id}/preview-token`, que gera um
token de 15 min para ver o portal **como o cliente**. Usei e testei de verdade.

**Montagem:** token do **CONDOMÍNIO IDEAL FLORES DA CIDADE** (JWT com
`sub = 4db583b6-…`, `type: portal`, `preview: true`, expira em 30 min).

| Tentativa | Resultado | Veredito |
|---|---|---|
| Listar meus kits | **17 kits**, todos com `client_id` do Ideal Flores | ✅ |
| Existem no sistema | **137 kits** de 21 clientes | — |
| Abrir kit do **Prime Arena** pelo id | **404** «Kit documental nao encontrado» | ✅ |
| Listar documentos desse kit alheio | **404** | ✅ |
| Listar chamados | 0 itens, nenhum `client_id` de terceiro | ✅ |

**A parede segura.** E segura do jeito certo: devolve **404**, não 403 — não confirma sequer
que o recurso existe, que é a prática correta para não vazar a existência de um cliente.
Dos 137 kits do sistema, o síndico enxerga os 17 que são dele.

**Achado lateral (A8-01 · MENOR):** há **duas tabelas de cliente** — `clients` (26 linhas) e
`ged_clients` (21). O portal usa `ged_clients`; o CRM e o Financeiro usam `clients`. Levei um
404 de «cliente não encontrado» só por usar o id da tabela errada. É a mesma família de
confusão do A1-01 (`condominios` × `clients`): três tabelas para o conceito de cliente.
Não quebra nada hoje, mas é onde o próximo join vai errar.

---
## O QUE NÃO CONSEGUI TESTAR, e por quê

Registro honesto do que ficou de fora, para você não achar que está coberto:

| O que | Por quê |
|---|---|
| **Portal do Colaborador como colaborador** | O usuário admin não tem cadastro de colaborador vinculado. Vi as telas e a mensagem honesta que elas dão, mas não vi holerite, escala nem ponto de uma pessoa real. Para testar de verdade: vincular um usuário de teste a um colaborador. |
| ~~**Área do Cliente como síndico**~~ | **TESTADO depois** — achei o `preview-token`. O escopo segura: 17 kits de 137, e 404 ao tentar o kit de outro condomínio. Ver módulo 8. |
| **Bater ponto com reconhecimento facial** | Exige celular com câmera e um colaborador real. A batida offline e a reconferência no servidor ficaram sem prova. |
| **Pagamento efetivo com OTP** | Parei no gate de propósito: o passo 2 exige o código que chega no seu e-mail. Provei que a trava existe e recusa; não provei que o pagamento completa. |
| **Assinatura de contrato com ICP-Brasil** | Não assinei o CTR-2026-00022 que está esperando você. Assinar contrato de cliente real é ato jurídico seu, não meu. |
| **CAT (acidente de trabalho)** | Não abri uma. CAT de acidente que não aconteceu é documento oficial falso. Vi o formulário e a validação. |
| **Fechar o mês do ponto** | Não fechei 09/2026: o mês não acabou e tem 182 anomalias abertas. Fechar seria congelar um mês incompleto como base da folha. |
| **Transmitir eSocial** | Não transmiti evento nenhum. Evento no governo em nome de um colaborador é ato com efeito legal sobre terceiro. |

---
## LIÇÕES DE MÉTODO (as três vezes que eu errei antes de acertar)

Registro porque elas valem mais que os achados — são o que evita o próximo falso alarme.

**1. Seletor por texto parcial acusa o inocente.**
`has-text("Gerar")` casou com a ABA «Gerar escala» antes do BOTÃO «Gerar». Concluí que o botão
não disparava nada. Com texto exato: `POST → 201`. Em tela cheia de abas com nome parecido,
texto exato, sempre.

**2. Contar linha não é medir estado.**
Acusei o VT/VR de virar pagável órfão depois de excluir a diária, porque `count(*)` devolveu 1.
Olhando o STATUS: `cancelado`. O sistema tinha feito a coisa certa — cancelar preservando o
rastro — e eu quase reportei o oposto.

**3. `pgrep -f` casa com o próprio comando.**
Duas vezes nesta sessão: achei que um deploy estava rodando porque o meu próprio comando de
monitoramento continha a palavra do processo que eu procurava. Já tinha caído nessa com a
varredura de oráculos. Filtrar por PID ou por nome do executável, não por linha de comando.

**E uma quarta, sobre escrever manual:**
Escrevi as primeiras notas do manual deduzindo pelo NOME da aba. «Mapa» não é mapa — é a tabela
de quais postos têm coordenada. «Editor visual» não arrasta nada — é a lista de preenchimento.
«Escalas do mês» não é grade dia a dia — é lista de escalas por posto. Manual escrito por
dedução ensina o sistema errado. Refiz olhando print por print.

### A4-03 · GRAVE · Proposta RECUSADA podia virar contrato; proposta nova, não
O seletor de «Gerar contrato a partir da proposta» oferecia **PROP-2026-00114** e
**PROP-2026-00093** — as duas com status **`rejected`**. Proposta recusada é proposta que o
cliente disse não. Não havia **nenhum** filtro de status.
**Corrigido:** exclui `rejected`, `recusada`, `lost`, `perdida`, `cancelled`, `cancelada`.

### A4-04 · GRAVE · Proposta criada pela tela nunca vira contrato
O filtro do seletor é `coalesce(client_document,'') <> ''`. A ação `/action/proposal` buscava
o **nome** do cliente pelo `client_id` e **não o documento** — então toda proposta criada pela
tela nascia com `client_document` vazio e ficava invisível no passo seguinte do funil.
**Medido:** das 5 propostas mais recentes, **3 estão sem documento** — exatamente as criadas
pela tela (incluindo a minha, PROP-2026-00123). As que têm documento vieram por outro caminho.
**Corrigido:** a ação agora busca `name` **e** `document_number` do cliente e grava os dois.
**Somado ao A4-01 (não há tela para criar cliente) e ao A4-02 (empresa_id faltando), o funil
comercial tinha três bloqueios em sequência.** Dois estão corrigidos; o terceiro (cadastro de
cliente) é decisão sua.

---
## T2-c · AFD DA PORTARIA 671 — PASSOU, e é o trabalho mais bem-feito que auditei

Auditado direto na tabela `afd_records`:

| Verificação | Resultado |
|---|---|
| Registros | 36 (1 do tipo **2** = cabeçalho da empresa + 35 do tipo **7** = marcações) |
| NSR | **1 a 36, sem buraco nenhum** — a sequência contínua que a norma exige |
| Cobertura | 35 batidas no dia 13/09 → **35 marcações**. Não perdeu nenhuma. |
| Origens | 32 `mobile` · 2 `contingencia` · 1 `tangerino` — o AFD unifica as três portas |
| Validade | **36 válidos, 0 inválidos**, 36 com `line_hash` |
| Estabelecimento | 1 CNPJ, numeração por estabelecimento como manda a norma |

**O layout está correto.** Amostra real das três primeiras linhas:
```
000000001 2 2026-09-13T08:31:00-0400 ... 66014833000110
000000002 7 2026-09-13T00:25:00-0400 06144025626 8 ...
000000003 7 2026-09-13T01:01:00-0400 07018816122 8 ...
```
NSR com 9 dígitos, tipo do registro, **timestamp ISO 8601 com o offset `-0400` explícito** —
o fuso de Manaus declarado no arquivo, que é justamente o que o A1-11 e o A1-15 não faziam nas
outras tabelas. Aqui foi feito certo.
O CNPJ do cabeçalho é o **66014833000110 — Conecta Mais Patrimonial**, coerente com ser ela a
empresa de vigilância.

**Observação de contexto:** o AFD começou a gravar em **13/09/2026** (hoje). As 11.041 batidas
históricas são anteriores e não estão nele. Isso é esperado — mas significa que, se a
fiscalização pedir período anterior, o arquivo não cobre. Vale saber.

---
## RESSALVA IMPORTANTE SOBRE O A1-06 (o contador de turnos)

Medido **depois** de todas as correções e dos bakes:
```
escalas com contador errado no banco ......... 23  (das 34)
alocações que casam com `condominios` ........ 73  (eram 0 com `clients`)
comunicados publicados (as duas grafias) ..... 11
pessoas ativas com o último ASO vencido ...... 25
```

**As 23 escalas continuam com `total_shifts` errado no banco.** O que eu corrigi foi o lado do
LEITOR: as telas «Escalas do mês» e «Editor visual» agora **contam de `shifts`** em vez de ler
o contador. Elas mostram a verdade.

Mas o contador em si segue inconsistente — e isso importa: qualquer coisa que leia
`scales.total_shifts` direto (relatório, integração, exportação futura) vai continuar errada.

**Seguir a fonte em vez do contador é o padrão certo** (é a regra da casa: ler a fonte, não
codificar a convenção). O conserto durável é um dos dois, e a escolha é sua:
1. **manter o contador atualizado** na escrita (gerar turno, adicionar, remover) — mais código
   e mais um lugar para desincronizar; ou
2. **apagar as colunas** `total_shifts`/`filled_shifts` e contar sempre de `shifts` — menos
   código, uma verdade só, e exige varrer quem mais as lê.

Eu recomendo a **2**. Mas não mexi: apagar coluna em produção é migração, e é decisão do dono.

---
## O QUE ESTA BATERIA DEIXOU NO ARSENAL

A regra da casa diz que trava nova entra em `checar_regressao.py` ou é declarada órfã com dono.
Esta entra: **`checar_id_tipo_divergente.py`**.

**Por que ela faltava:** o defeito crítico de hoje (A2-04) foi uma comparação entre tipos —
`time_sheets.employee_id` VARCHAR contra `employees.id` UUID. Nenhum dos 48 caçadores pegava
essa classe. O `checar_varchar_teto` é vizinho, mas mede outra coisa (valor no teto do varchar).
Foi preciso **clicar na tela** para descobrir que o espelho da Portaria 671 estava morto.

**O que ela faz:** para cada coluna `*_id` de tabela COM dado, procura a tabela candidata pelo
nome e compara o tipo da coluna com o tipo do `id` dela. Sem lista branca. Coluna sem tabela
candidata é ignorada — não é achado, é nome fora da convenção.

**Estreia acusando 8 — e 7 são minas ainda não pisadas:**
```
gp_cats.employee_id              VARCHAR × employees.id UUID
gp_justifications.employee_id    VARCHAR × employees.id UUID
gp_monthly_closings.employee_id  VARCHAR × employees.id UUID
juridico_processos.employee_id   VARCHAR × employees.id UUID
time_sheets.condominium_id       VARCHAR × condominiums.id UUID
time_sheets.work_schedule_id     VARCHAR × work_schedules.id UUID
time_sheets.employee_id          VARCHAR × employees.id UUID   ← esta já explodiu hoje
```
Cada linha dessas é um HTTP 500 esperando alguém escrever o join. A varredura das 00:00 passa
a acusar se o número **crescer**.

**O que ela NÃO pega, e fica declarado:** tipo divergente **grita** (500 na cara). Tabela errada
**cala** — o A1-01 desta mesma bateria tinha os dois lados UUID, o join simplesmente não casou
nenhuma das 73 linhas, e a tela mostrou «—» para todo mundo sem erro nenhum. Para essa segunda
família ainda não há trava. É o próximo caçador a escrever.

---
## VERIFICAÇÃO PÓS-BAKE 4 — o funil comercial, ponta a ponta

Criei uma segunda proposta pela tela, já com as correções no ar:

| Passo | Antes da bateria | Agora |
|---|---|---|
| Criar proposta | `HTTP 500` (empresa_id nulo) | **PROP-2026-00124**, 200 OK |
| CNPJ do cliente | `(VAZIO)` | **66014833000110** — buscado do cadastro |
| Aparece em «Gerar contrato» | **não** (filtro exige documento) | **sim** |
| Propostas recusadas no seletor | PROP-2026-00114 e 00093 (`rejected`) | **nenhuma** |

Comparação lado a lado das duas propostas da bateria, que mostra a correção no meio:
```
PROP-2026-00124  CONECTAMAIS PATRIMONIAL  66014833000110   ← depois do conserto
PROP-2026-00123  CONECTAMAIS PATRIMONIAL  (VAZIO)          ← antes
```
Dos três bloqueios do funil, **dois estão resolvidos**. O terceiro — não existir tela para
cadastrar cliente — continua de pé e é decisão sua.
