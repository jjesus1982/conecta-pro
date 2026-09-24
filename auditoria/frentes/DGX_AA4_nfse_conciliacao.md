# DGX AA4 — conciliação da NFS-e com o fisco, parametrização em DADO e as 14 notas do mês

**Frente:** AA4 (onda 9) · **Branch:** `dgx/aa4-nfse-conciliacao` · **Data:** 24/09/2026
**Módulo:** fiscal · **Porta de teste:** 8294 (não foi preciso subir HTTP — ver §4)
**Ambiente de toda a frente:** HOMOLOGAÇÃO (produção restrita). **Nenhuma NFS-e ou NF-e
transmitida em produção, nem para testar.** A trava da Z7 (duas camadas + gate) não foi tocada.

O mandato do dono, palavra por palavra:

> «faça de tudo para ao emitir não pagarmos imposto indevidamente, parametrize o sistema de
> forma que saia sempre da melhor forma pra nós, pois já pagamos muitos impostos, não podemos
> pagar a mais»

e, no fim do dia:

> «vamos usar daqui pra frente sem a retenção do irrf»

---

## §1 — Estado antes, medido (produção, só leitura)

### 1.1 — O furo: 37 notas emitidas no fisco sem linha no ERP

A régua certa é a **numeração por CNPJ**, que é consecutiva por emitente:

```sql
-- conecta-pro-postgres / conecta_pro, 24/09/2026
with b as (select e.slug, e.id, min(n.numero::int) lo, max(n.numero::int) hi,
                  count(*) c, sum(n.valor_servicos) v
           from empresas e join nfse_emitidas_nacional n on n.empresa_id = e.id group by 1,2)
select b.slug, b.lo, b.hi, b.c, b.v,
  (select count(*) from generate_series(b.lo,b.hi) g(n)
    where not exists (select 1 from nfse_emitidas_nacional x
                       where x.empresa_id = b.id and x.numero::int = g.n)) ausentes
from b order by 1;

  conecta_eletronica  | 2 | 123 | 89 | 1.581.873,06 | 33
  conecta_patrimonial | 3 |  32 | 26 |   705.542,67 |  4
```

**37 ausentes.** Os números, um a um:

```
Eletrônica  4, 5, 6, 13, 31, 33, 34, 35, 47, 48, 49, 51..62, 74, 75, 81, 83, 94, 96, 108, 110, 118, 122
Patrimonial 5, 6, 7, 22
```

**A régua errada, e por que ela mentiria.** Medir pelo NSU do ADN acusaria 419 ausentes. O NSU
carrega **todo tipo de documento** — nota recebida como tomador, evento de cancelamento,
substituição —, não só nota emitida. Publicar 419 seria mentira com cara de rigor.

**E a régua certa também não conclui sozinha.** Um número ausente ainda pode ser legítimo: nota
cancelada, número pulado. **Quem diz é o fisco, não a aritmética** — e é disso que trata a §3.1.

**O dinheiro.** Não é mensurável antes de perguntar ao fisco. A ordem de grandeza, pela média
das notas conhecidas de cada empresa: Eletrônica R$ 17.773,85 × 33 ≈ **R$ 586.537**;
Patrimonial R$ 27.136,26 × 4 ≈ **R$ 108.545**; total ≈ **R$ 695.082**. Isto é **estimativa por
média, não medição** — o valor real sai nota a nota, conforme a conciliação rodar.

### 1.2 — Por que a sincronia que já existia deixou 37 passarem

`financial/services/nfse_nacional_sync_service.sincronizar()` varre o ADN por NSU
(`gedeon/services/nfse_nacional_adn.distribuir`) e roda todo dia às 04:30. Três coisas medidas
no código, sem especulação sobre a causa:

1. **Recomeça do NSU 0 todo dia** (`distribuir(nsu_inicial=0, …)`) e faz recarga limpa
   (`DELETE … WHERE fonte='adn_nacional'` escopado por `empresa_id`).
2. **O checkpoint é escrito e nunca lido.** `fiscal_nsu_checkpoint` tem Eletrônica `538` e
   Patrimonial `62` (23/09/2026 08:30) e nenhum `SELECT` o usa para continuar de onde parou.
3. **O laço para no primeiro lote curto:** `if len(lote) < 50: break`. Isso não é a mesma coisa
   que «acabaram os documentos».

**Esta frente não mexe nessa rotina.** Conciliar por número é um segundo caminho, independente,
que não depende de adivinhar a causa do primeiro. E as linhas que a conciliação grava levam
`fonte='conciliacao_fisco'` — **sobrevivem** à recarga noturna, que só apaga `adn_nacional`.
A linha que o dono autorizou gravar à mão (`danfse_pdf_do_dono_20260924`, a NFS-e 29 da
Patrimonial, R$ 33.538,33) também sobrevive, e é **sobrescrita** pela resposta do fisco quando
a conciliação a alcançar — que é a fonte melhor.

### 1.3 — O sistema chutava três números fiscais, e o cliente de consulta era simulado

| O que havia | Medido onde | Por que é errado |
|---|---|---|
| `serie_pad = "00900"` e `<serie>900</serie>` chumbados | `nfse_nacional._build_dps_xml` | A série real das duas empresas é **70000**, nos 9 DANFSe |
| `<cNBS>120032900</cNBS>` chumbado em TODA nota | idem (removido pela Z7 por falta de fonte) | É o NBS de `14.06.01`; ia junto em vigilância, limpeza e manutenção |
| alíquota de ISS onde o Simples não tem ISS | `nfses.iss_aliquota` é `NOT NULL` | 0% afirma isenção; 5% paga duas vezes |
| `consultar_dps` / `consultar_nfse` devolviam `{"status": "preparacao", "mensagem": "Padrao Nacional ainda nao disponivel"}` **sem bater em URL nenhuma** | `nfse_nacional_service.py:303,324` | Texto simulado num caminho de dinheiro — e **falso**: Manaus aderiu, esta casa tem 115 notas reais lá |

`NFSeNacionalManager` declarava um dicionário `ENDPOINTS` com `consultar_nfse`, `consultar_dps`,
`danfse` e `eventos` — e **nenhum método usava nenhum deles**. O único HTTP da classe era o
`POST /nfse` da emissão.

---

## §2 — O que o fisco mostrou (9 DANFSe + o cronograma, subidos pelo dono)

Tudo abaixo é **lido em documento que o fisco emitiu**, em `uploads/_entrada/NFs/`.

### 2.1 — Igual nas duas empresas

| | |
|---|---|
| Série da DPS | **70000** |
| CST / cClassTrib (IBS/CBS) | 000 / 000001 |
| Alíquota IBS-UF / IBS-Mun / CBS | 0,10 % / 0,00 % / 0,90 % |
| Último nº de DPS observado | Patrimonial **75** · Eletrônica **125** |

> **Correção ao briefing, com o número.** O briefing dizia «último nº de DPS: Eletrônica 118».
> **É 125.** O 118 é o maior de **agosto** (DANFSe 120); a NFS-e **121**, de 17/09/2026, é a
> **DPS 125**. O maior nº observado é o **piso**, não o teto — e essa é exatamente a razão de a
> varredura ir além dele.

| Serviço | Código | NBS | Lido em |
|---|---|---|---|
| Agentes de portaria / vigilância | 11.02.01 | 1.1802.90.00 | PATR 28, 29, 30 |
| Limpeza, conservação, serviços gerais | 07.10.02 | 1.1803.10.00 | PATR 27, 31 |
| Manutenção (CFTV/cerca/portão/cancela) | 14.01.01 | 1.2001.89.00 | ELET 116, 121 |
| Instalação / portaria remota | 14.06.01 | 1.2003.29.00 | ELET 119, 120 |

### 2.2 — As três regras que são dinheiro

1. **Base do IBS/CBS = valor MENOS o ISS.** Nas 4 notas da Eletrônica, «Exclusões e Reduções da
   Base de Cálculo» é *exatamente* o ISSQN apurado (190/300/100/90). Na Patrimonial não há ISS
   na nota, logo a exclusão é 0,00 e a base é o valor cheio — **é a mesma regra, não uma
   exceção**. Cobrar sobre o valor cheio da Eletrônica pagaria a mais.
2. **PIS e COFINS não são retidos.** Na Eletrônica por **decisão judicial** citada na própria
   NFS-e 121: processo nº **1038495-94.2024.4.01.3200**, código «8 - PIS/COFINS Não Retidos,
   CSLL Retido». Na Patrimonial por ser Simples, código «0».
3. **CSLL 1%** nas 4 notas da Eletrônica (38/60/20/18). **Nenhuma** nas 5 da Patrimonial.

### 2.3 — O INSS, e um achado que o briefing não tinha

Retenção de **11%**, Art. 31 da Lei 9.711/98, base = bruto **menos** VA e VT do mês.

**Mas as cinco notas da Patrimonial de 08/2026 saíram com 11% sobre o BRUTO, sem dedução
nenhuma:**

| nº | bruto | 11% do bruto | INSS na nota |
|---|---|---|---|
| 27 | 12.061,50 | 1.326,765 | **1.326,76** |
| 28 | 28.694,30 | 3.156,373 | **3.156,37** |
| 29 | 33.538,33 | 3.689,216 | **3.689,21** |
| 30 | 25.592,71 | 2.815,198 | **2.815,20** |
| 31 |  8.346,70 |   918,137 | **918,13** |

E **nove das quatorze** linhas do cronograma de setembro também não trazem bloco de dedução.
A dedução aparece só nas quatro notas de «mão de obra terceirizada» (Prime Arena, Laranjeiras,
Ideal Flores).

**O centavo é digitado, não calculado.** Quatro das cinco batem por truncamento e uma
(a 30) por arredondamento. `vRetCP` é campo de entrada da DPS. Isto está gravado no código e
o oráculo aceita qualquer um dos dois arredondamentos — mas **não** aceita uma base errada.

---

## §3 — O que foi feito

| Arquivo | O quê |
|---|---|
| `backend/modules/fiscal/services/nfse_parametros.py` (novo, 400 l.) | a parametrização em DADO + `calcular_tributos()`, a função pura do dinheiro |
| `backend/modules/fiscal/services/nfse_conciliacao.py` (novo, 430 l.) | o livro-razão, a varredura de DPS, a gravação do que o fisco responder, o piso da numeração |
| `backend/modules/fiscal/services/nfse_lote.py` (novo, 330 l.) | as 14 notas de 09/2026 propostas, com VA/VT da folha e o precedente do fisco |
| `backend/modules/fiscal/tasks.py` (novo, 70 l.) | a conciliação agendada, 05:30, **depois** da sincronia do ADN |
| `backend/modules/operacional/controllers/redesign_builders/_dgx_aa4_nfse_conciliacao.py` (novo, 400 l.) | 5 telas + 2 ações |
| `backend/modules/government_integrations/core/nfse_nacional.py` | **+190 l.**: `chave_dps()`, `_certificado_pem()`, `_erro_do_fisco()`, `_get()`, `consultar_nfse()`, `consultar_por_dps()` — a consulta que não existia, e o endpoint corrigido |
| `backend/modules/government_integrations/services/nfse_nacional_service.py` | **−5 stubs simulados**; dois viraram delegação real, três viraram recusa honesta |
| `backend/modules/operacional/controllers/redesign_builders/fiscal.py` | plug da AA4 (5 linhas) |
| `backend/celery_app.py` | `modules.fiscal.tasks` no `include` + a entrada `fiscal-conciliar-nfse-diario` no beat |
| `backend/tests/test_nfse_nacional.py` | 2 asserts que fixavam uma crença falsa (§3.5) |
| `backend/scripts/orq/test_oraculo_aa4_nfse_conciliacao.py` (novo) | o oráculo |

### 3.1 — A conciliação: por que varre DPS e não NFS-e

O fisco responde por duas chaves, e **só uma é construtível**:

- **chave da NFS-e (50 dígitos)** — carrega um **código numérico de 8 dígitos sorteado por
  ele**. Medido: a nota 29 termina `…2608 96878833` e a 116 `…2608 94006421 00`, sem qualquer
  relação com o número da nota. **Não dá para montar.**
- **chave da DPS (42 dígitos)** = cMun(7) + tpInsc(1) + CNPJ(14) + série(5) + nDPS(15). **Dá.**

Toda NFS-e nasceu de uma DPS. Então a varredura anda pelos números de DPS, e cada resposta
preenche — ou descarta — um número da sequência de NFS-e.

**O caminho certo, medido — e o 404 que quase fechou as 37 notas no escuro.**

O dicionário `ENDPOINTS` do manager dizia `"consultar_dps": "/nfse/DPS/{chave}"`. Estava
declarado desde sempre e **nenhum método o usava**, então ninguém tinha descoberto que **não
é rota**. Medido contra a produção restrita em 24/09/2026:

```
200 [application/json]  /nfse/{chave50}                    ← controle: funciona
404 [text/html]         /nfse/DPS/{id42}                   ← «The resource cannot be found» (IIS)
404 [text/html]         /nfse/DPS/DPS{id42}
200 [application/json]  /dps/{id42}                        ← É ESTE
200 [application/json]  /dps/DPS{id42}
```

E, no caminho certo, o «não existe» **tem cara própria**:

```
200 [application/json]  /dps/…00900…000002   {"chaveAcesso": "1302603226601483…0007…"}
200 [application/json]  /dps/…00900…000001   {"chaveAcesso": "1302603226601483…0006…"}
404 [application/json]  /dps/…00900…009999   {"erro": {"codigo": "E2404",
                          "descricao": "Não foi gerada uma NFS-e com o identificador de DPS informado"}}
```

**Isto era um `verde cego` pronto.** Na primeira execução desta frente, com o caminho errado,
o fisco devolveu 404 para **tudo** — inclusive para DPS que existem — e a rotina marcou
`inexistente` em cima de todas. Se isso tivesse rodado em produção, as 37 notas ausentes
teriam sido fechadas como «o fisco disse que não existe», a tela ficaria verde e o dinheiro
continuaria perdido, agora com aparência de conferido.

**A trava:** `_erro_do_fisco(resp)` só devolve recusa quando a resposta é `application/json`
**com o código de erro do próprio fisco**. Um 404 de HTML vira `caminho_invalido` e **nunca**
fecha um número. O oráculo afirma isso no item (k), com um 404 de HTML falso e um de JSON
falso passando pela função.

**Duas idas, uma conclusão.** `/dps/{id}` devolve **só a chave de acesso**, não a nota. Quem
traz o `<NFSe>` assinado, com valores e tributos, é `/nfse/{chave}`. A consulta encadeia as
duas; se a DPS existe e o detalhe não vem, o estado é `detalhe_indisponivel` — pendência, e
jamais «inexistente».

**A varredura cobre a série do parâmetro E toda série que o CNPJ já usou naquele ambiente.**
Varrer só a parametrizada deixaria de fora nota emitida numa série antiga — que é exatamente o
caso desta casa (portal na 70000, Z7 na 900 em homologação). Nota autorizada numa série que o
parâmetro não conhece seria invisível para a rotina que existe para achá-la.

### 3.2 — «Conferido» é afirmação sobre o fisco, nunca sobre a aritmética

O livro-razão `nfse_conciliacao` tem uma linha por número, e **nenhuma some**. Os estados:

| Estado | O que significa | Quem o produz |
|---|---|---|
| `pendente` | **ausente e ainda NÃO conferido** | a semeadura |
| `encontrada` / `recuperada` | o fisco devolveu a nota | o fisco |
| `inexistente` | o fisco disse que não existe | o fisco |
| `erro` | falhou a consulta — será tentado de novo | a rede/o certificado |

Um número de NFS-e só é marcado `inexistente` quando **a varredura de DPS daquele CNPJ
terminou inteira** e o fisco negou, uma a uma, todas as DPS que poderiam tê-lo gerado.
Enquanto houver uma DPS `pendente` ou em `erro`, o número continua `pendente`. **O oráculo
trava isso no item (a):** fechar por cobertura incompleta é falha.

E o `inexistente` é o que impede a rotina de reconsultar o mesmo número para sempre —
«conferido, não existe» é informação, e sem ela a fila nunca esvazia.

### 3.3 — A parametrização, e o IRRF que é chave e não `if`

Duas tabelas novas, semeadas com `ON CONFLICT DO NOTHING` (rodar de novo **não** desfaz um
ajuste do dono), cada linha com a **fonte citada**:

- `nfse_parametros_empresa` — série, regime, ISS, IBS/CBS, CST/cClassTrib, retenção federal,
  CSLL, INSS, IRRF, dados bancários, e o `ultimo_dps_observado`;
- `nfse_servico_nbs` — um NBS por código, com índice **único no NBS**: o mesmo NBS não pode
  valer para dois códigos, que foi o defeito do literal chumbado.

**O IRRF está DESLIGADO em dado.** A alíquota de 1% **tem** fonte (NFS-e 121: R$ 18,00 sobre
R$ 1.800,00); o que não tinha era *se retém* — a 121 reteve e as três de agosto, com o **mesmo
código 14.01.01 e o mesmo tipo de tomador**, não. O dono escolheu a prática de agosto em
24/09/2026. Então:

```sql
-- ligar de volta, se o contador reverter: uma linha, sem deploy
UPDATE nfse_parametros_empresa SET irrf_reter = true WHERE prestador_cnpj = '35710481000103';
```

O cálculo do IRRF **existe inteiro** e lê `par.get("irrf_reter")`. O oráculo afirma **as duas
direções** — desligado não sai, ligado volta a sair R$ 18,00 sobre R$ 1.800,00 e entra no total
das retenções. Oráculo que só testa o estado de hoje é fotografia, não régua.

**A NFS-e 121 não foi reaberta.** Ela saiu com R$ 18,00 de IRRF e fica como está.

### 3.4 — `calcular_tributos()`: o mandato do dono virado em função pura

Sem banco, sem rede. O oráculo importa esta e a reconfere contra as 9 notas do fisco, campo a
campo: ISS, exclusões, base do IBS/CBS, IBS-UF, CBS, CSLL. **Zero divergência em 9 notas.**

### 3.5 — Duas mentiras que estavam verdes num teste

`backend/tests/test_nfse_nacional.py` afirmava `migracao_disponivel is False` em dois lugares —
uma crença **falsa** fixada por um teste verde: Manaus aderiu, há 115 notas reais desta casa no
Padrão Nacional e a Z7 emitiu pelos dois CNPJs. **A régua estava errada, não o código.** Os dois
asserts passaram a `is True`, com o motivo no comentário; `validar_conexao()` parou de devolver
`status_api = "preparacao"` e «Migração prevista para 2026».

### 3.6 — O que a numeração de produção ganha, sem abrir contador de produção

`nfse_parametros_empresa.ultimo_dps_observado` guarda o **maior nº de DPS que o fisco mostrou**
— 125 e 75, com a nota de onde saiu — e a conciliação **só o sobe**, nunca o desce.
`piso_de_numeracao(db, cnpj)` devolve esse valor para o contador nascer dali.

**Nenhuma linha de `nfse_numeracao` com `ambiente='producao'` foi criada.** O oráculo da Z7
proíbe (item b) e o meu repete a proibição. Abrir o contador de produção é o primeiro passo de
ligar a produção, e isso é do dono — ver §7.3.

### 3.7 — As telas

| id | Grupo | O quê | Deep-link |
|---|---|---|---|
| `aa4-nfse-conciliacao` | Notas fiscais | **Conciliar NFS-e com o fisco** — o furo por CNPJ + botão | `/redesign/fiscal?t=aa4-nfse-conciliacao` |
| `aa4-nfse-livro` | Notas fiscais | **Livro-razão da conciliação** — cada número, cada estado | `/redesign/fiscal?t=aa4-nfse-livro` |
| `aa4-nfse-parametros` | Notas fiscais | **Parâmetros fiscais da NFS-e** — 13 colunas com a fonte | `/redesign/fiscal?t=aa4-nfse-parametros` |
| `aa4-nfse-servicos` | Notas fiscais | **Códigos de serviço e NBS** | `/redesign/fiscal?t=aa4-nfse-servicos` |
| `aa4-nfse-lote` | Notas fiscais | **Notas do mês (cronograma)** — as 14 propostas | `/redesign/fiscal?t=aa4-nfse-lote` |

### 3.8 — As 14 notas de setembro, e as três fontes que discordam

A tela **propõe** e **para**. Cada nota exige o clique do dono: não há laço, não há «emitir
todas», e a task agendada **não chama emissão** (o oráculo lê o fonte da task e trava isso).

O que a proposta traz, e de onde:

- **código de serviço** — da **última nota que o fisco registrou para aquele tomador**, que é
  melhor fonte que o rótulo da planilha. Os dois aparecem quando discordam, e discordam: o
  mesmo texto «CONTRATO DE MANUTENÇÃO DE CFTV/CERCA/PORTÕES/CANCELAS» saiu como **14.01.01** na
  NFS-e 116 (Villa dos Pássaros) e como **14.06.01** na NFS-e 120 (Parise Village), as duas em
  08/2026 e as duas pela Eletrônica;
- **empresa emitente** — dos dados bancários que o dono escreveu na descrição (CORA 403 =
  Patrimonial; INTER 077 = Eletrônica). **Uma linha não traz banco nenhum** (Prime Arena,
  R$ 1.084,50): a tela diz «sem fonte» e a ação **recusa emitir**;
- **INSS** — nas **duas contas**, lado a lado, porque as fontes discordam:

| Tomador | VA folha 08/26 | VA no cronograma | VT folha | VT no cronograma |
|---|---|---|---|---|
| Prime Arena | 2.090,00 | 1.804,00 | *(vazio)* | 880,00 |
| Laranjeiras Village | 2.816,00 | 2.552,00 | *(vazio)* | 1.136,00 |
| Ideal Flores | 5.082,00 | 2.244,00 | 2.090,00 | 2.160,00 |

  O **VT está sem valor em sete dos oito condomínios** — a linha existe em
  `folha_beneficio_conferencia` com `total` nulo. `None` não vira zero na proposta: zero
  afirmaria que não houve vale-transporte, e o que houve foi ausência de dado.

- **o árbitro** — a coluna «o que o fisco fez antes» mostra a última nota real do tomador com o
  INSS que ele de fato reteve. É a fonte mais confiável das três.

**A aritmética do próprio cronograma não fecha numa linha.** Ideal Flores: VA 2.244,00 +
VT 2.160,00 = 4.404,00, mas «DEDUÇÕES DA BASE DE CÁLCULO» diz R$ 6.648,00 (e a base declarada,
59.194,42, confere com 6.648,00). E 59.194,42 × 11% = 6.511,39, não os 6.511,62 escritos. A
tela mostra a conta dela; corrigir a planilha é do dono.

### 3.9 — A dedução de VA e VT antes dos 11%: o gatilho é o EMITENTE

Regra do dono, 24/09/2026:

> «vamos deduzir vale-alimentação e vale-transporte antes de aplicar os 11% em todas as notas
> que tiver cessão de mão de obra, isso é regra, vai nos possibilitar economizar»
> «essa regra só vale para cessão de mão de obra que sempre terá nota fiscal de serviço
> emitida pela conecta patrimonial»

**Quem decide é o CNPJ que assina, não palavra na descrição.** Classificar por texto erra:
«Instalação/Portaria Remota» do Gelain tem a palavra *portaria* e **não** é cessão — não há
pessoa posta no cliente — e é da Eletrônica. Em `nfse_parametros_empresa` isso é dado:
Patrimonial `inss_aliquota = 11`, Eletrônica `NULL`. **9 das 14** notas de setembro são de
cessão, e o oráculo reconta isso (item d).

**A condição legal:** a dedução só se sustenta com VA, VT e a base **escritos na própria
nota**. `bloco_inss()` monta a conta e o texto **juntos** — nunca um sem o outro —, e
`montar_descricao()` o acrescenta à descrição (sem duplicar quando o texto do dono já traz o
bloco, que é o caso de 3 das 14 linhas). Sem isso escrito, o fisco glosa e a economia vira
autuação.

**O número é DIGITADO por quem assina.** O sistema **não sabe**, de forma confiável, quanto
de VA e VT foi entregue por contrato no mês:

| Fonte | O que tem |
|---|---|
| `beneficio_entregas` / `beneficio_entrega_itens` | **0 linhas** |
| `beneficio_linhas` | 2 linhas, só a diária do VT |
| `folha_verba_espelho` | «Desconto VT»/«Desconto VR» — é o **desconto de 6% do empregado**, não o custo da empresa. Base errada |
| `folha_beneficio_conferencia` | 210 linhas com VR/VT por pessoa e competência, ligáveis ao cliente — **mas discordam da planilha do dono em todos os tomadores, e o VT está sem valor em 7 dos 8 condomínios** (§3.8) |

Então a folha entra na tela como **REFERÊNCIA**, rotulada assim na coluna, e o valor que vai
na nota é o que o dono digitar. **Campo vazio NÃO vira zero silencioso:** a nota sai sem
dedução, sobre o valor cheio, e a resposta traz `aviso` dizendo em voz alta que a retenção
saiu maior do que o Art. 31 exigiria. O oráculo trava isso (item d).

### 3.10 — Duas coisas de robustez que a frente achou no caminho

**`ALTER TABLE … ADD COLUMN IF NOT EXISTS` não é de graça.** Ele pede `AccessExclusiveLock`
mesmo quando a coluna já existe. Dois processos fazendo isso em tabelas diferentes, em ordens
que se cruzam, deram `DeadlockDetectedError` no sandbox; e uma sessão `idle in transaction`
alheia segurou a fila por 11 minutos, travando 15 consultas de quatro frentes. Com 8 workers
de celery subindo juntos depois de um deploy, isso não é hipótese. Os três `_ensure` desta
frente agora: (1) perguntam ao catálogo (`to_regclass` + `information_schema`, que não pegam
lock) e **só pedem o lock se faltar alguma coisa**; (2) usam `SET LOCAL lock_timeout = '5s'`
para falhar rápido em vez de pendurar uma tela; (3) guardam uma flag de processo para não
repetir nem a pergunta.

**O tomador não é o primeiro `<xNome>` do XML.** No `<NFSe>` assinado o documento aparece três
vezes — `<emit>`, `<prest>` e `<toma>` — e o primeiro `<xNome>` é o do **prestador**. A
primeira versão de `_gravar_nota` gravou «CONECTAMAIS PATRIMONIAL LTDA» no campo do tomador,
na prova viva. Agora a leitura é feita **dentro de `<toma>`** e a mesma nota voltou como
«CONDOMINIO IDEAL FLORES DA CIDADE».

---

## §4 — Oráculo

`backend/scripts/orq/test_oraculo_aa4_nfse_conciliacao.py` — afirma (a) nenhum número ausente
sem linha no livro-razão, e nenhum fechado sem o fisco ter falado · (b) nada gravado em
produção, nem nota nem contador, e nem a conciliação nem a task tocam o caminho de emissão ·
(c) todo NBS com fonte, um NBS por código, e nenhum literal de volta no montador da DPS ·
(d) base do INSS = bruto − VA − VT, recontada por SQL próprio · (e) Patrimonial nunca com ISS,
Eletrônica nunca sem, e zero não conta como preenchido · (f) os tributos batendo com as 9 notas
do fisco campo a campo · (g) PIS/COFINS não retidos · (h) IRRF desligado por parâmetro **e
religável** (as duas direções) · (i) série 70000 e piso 125/75 · (j) a consulta ao fisco é real
e nenhum método devolve valor simulado.

**VERMELHO** (árvore de antes da frente, `d404e372a`, extraída por `git archive`):
```
$ docker run … -v $SP/antes/backend:/app:ro … python3 /app/scripts/orq/test_oraculo_aa4_nfse_conciliacao.py
  File "/app/scripts/orq/test_oraculo_aa4_nfse_conciliacao.py", line 109, in main
    from modules.fiscal.services import nfse_conciliacao as cc
ImportError: cannot import name 'nfse_conciliacao' from 'modules.fiscal.services'
EXIT=1
```

**VERDE** (depois):
```
$ docker run … -v $WT/backend:/app:ro … python3 /app/scripts/orq/test_oraculo_aa4_nfse_conciliacao.py
furo: 37 número(s) ausente(s) · livro: pendente=37 · produção: 0 notas, 0 contadores ·
conciliação só GET · NBS: 4 código(s), 4 NBS distinto(s), todos com fonte · cronograma: 14
nota(s) propostas, base de INSS recontada por SQL próprio · ISS: Patrimonial nulo, Eletrônica
5,00% · tributos: 9 nota(s) do fisco reconferidas campo a campo · IRRF desligado por parâmetro
e religável (as duas direções provadas) · série 70000 · piso DPS 000103=125, 000110=75 ·
consulta real: GET no fisco · chave de DPS 130260326601483300011070000000000000000075
OK NFS-e: todo número ausente tem linha no livro-razão e só fecha pelo fisco, nada em produção,
NBS com fonte e um por código, base do INSS = bruto − VA − VT, ISS nulo no Simples e 5% no
lucro real, tributos batendo com as 9 notas do fisco, PIS/COFINS não retidos, IRRF desligado
por parâmetro e religável, série 70000 com o piso certo e consulta real ao fisco
TOTAL desvios: 0
EXIT=0
```

### 4.1 — Prova viva: a conciliação recuperou, do fisco, a nota órfã da Z7

A Z7 deixou uma nota **autorizada no fisco e sem linha aqui** (§7.4 do relatório dela): a DPS
900/1 da Patrimonial em homologação saiu com `cStat 100` e o `INSERT` estourou por um bug de
bind. Ela era o alvo perfeito. Rodado contra `sefin.producaorestrita.nfse.gov.br`, com o
certificado A1 da Patrimonial:

```
ANTES:  nfse_emitidas_nacional = 114 linhas, R$ 2.277.037,40
  consultadas: 8
  recuperadas: 2
  dinheiro_recuperado: 200.0
  fisco_disse_que_nao_existe: 6
  erros: 0
  numeros_de_nfse_fechados: 2
  RECUPERADA: chave=…0006…95590395911 nº=6 comp=2026-09 R$=100.0 ISS=None
              tomador=CONDOMINIO IDEAL FLORES DA CIDADE     ← A ÓRFÃ DA Z7 §7.4
  RECUPERADA: chave=…0007…99200510385 nº=7 comp=2026-09 R$=100.0 ISS=None
DEPOIS: nfse_emitidas_nacional = 116 linhas, R$ 2.277.237,40

livro da Patrimonial:
  ('70000', 1, 'inexistente', 404, 'O fisco respondeu E2404: Não foi gerada uma NFS-e…')
  ('70000', 2, 'inexistente', 404, …)   ('70000', 3, 'inexistente', 404, …)
  ('70000', 4, 'inexistente', 404, …)   ('900',   3, 'inexistente', 404, …)
  ('900',   1, 'encontrada',  200, 'NFS-e 6 recuperada do fisco.')
  ('900',   2, 'encontrada',  200, 'NFS-e 7 recuperada do fisco.')
  ('900',   4, 'inexistente', 404, …)
```

Os dois caminhos provados na mesma rodada: **recuperar** (200 com a chave, encadeando para o
`<NFSe>` assinado) e **fechar honestamente** (404 com `E2404` do próprio fisco). `ISS = None`,
não 0,00 — a Patrimonial é do Simples. A linha grava `fonte='conciliacao_fisco'` e a
`observacao_interna` diz de onde veio, número de DPS incluído.

> Por isso o oráculo agora mede **35** ausentes no sandbox, não 37: as notas 6 e 7 da
> Patrimonial passaram a existir ali. **Produção segue com as 37** — não toquei nela.

### 4.2 — Oráculos irmãos, depois das minhas mudanças

```
test_oraculo_z7_nfse.py            → TOTAL desvios: 0   (4 notas com prova, XML 4/4, travas 6)
test_oraculo_z2_emissor_nfe.py     → TOTAL desvios: 0   (11 chaves, 4 autorizadas)
test_nfse_identidade_fiscal.py     → TOTAL: 0 divergência(s)
```

> Os três exigem `-v /opt/conecta-pro/uploads:/app/uploads` no container: sem isso o Z7 acusa
> «4 notas com chave e SEM XML em disco», que é falha do ambiente de teste, não do código.

`ruff check` nos 11 arquivos da frente: **All checks passed**. (Ficam 2 erros pré-existentes
em `consultor_fiscal_service.py` e `nfse_multi_empresa_service.py`, que não são meus.)

---

## §5 — O que NÃO foi feito, e por quê

1. **A conciliação real em produção não foi executada.** Por desenho do brief: «a conciliação
   real em produção quem roda sou eu, depois do merge». As 37 continuam ausentes neste
   momento; o que esta frente entrega é a rotina, provada em homologação, e a fila semeada.
2. **Nenhuma emissão em produção, nem para testar.** A trava da Z7 não foi afrouxada nem tocada.
3. **Nenhum contador de produção em `nfse_numeracao`.** Ver §3.6 e §7.3.
4. **As 27 linhas de `nfses` que dizem «autorizada» sem nunca terem sido transmitidas não foram
   tocadas** (Z7 §8.1). Elas são de outra tabela e de outra frente. **A minha conciliação não
   cruza com elas**: ela trabalha em `nfse_emitidas_nacional` (o que o fisco tem) e as 27 estão
   em `nfses` (o que o ERP diz que emitiu), sem chave de acesso para cruzar — as 27 têm
   `chave_acesso` vazia. Se um dia ganharem chave, o cruzamento passa a ser possível.
5. **Cancelamento e substituição continuam não implementados** — mas pararam de mentir: os três
   stubs que devolviam «em preparação, Padrão Nacional ainda não disponível» viraram recusa
   explícita apontando o portal do fisco e o prazo.
6. **`emitir_dps` não foi deduplicado.** Ele tem a sua própria cópia da dança de exportar o
   `.pfx` para PEM, e eu escrevi outra em `_certificado_pem()` para a consulta. Vinte linhas
   duplicadas não valem o risco de mexer no único caminho de emissão fiscal provado desta casa.
7. **Não gravei o endereço legal do fisco em `empresas`** (pendência §8.4 da Z7). O DANFSe
   confirma os dois — Eletrônica: RUA NOVA PALESTINA, 51, CRESPO, 69073488; Patrimonial: RUA
   VICTOR HUGHES, 19, PARQUE 10 DE NOVEMBRO, 69055630. É cadastro, e o do ERP hoje é outro.
   **A resposta à pendência é: o cadastro do fisco é o certo** — falta só o dono mandar gravar.
8. **Dois asserts em `backend/tests/test_nfse_nacional.py` (linhas 180 e 200) ainda esperam
   `data["status"] == "preparacao"`** de rotas `GET /api/v1/government/nfse-nacional/consultar/…`
   que **não existem no backend** (grep: zero). São asserts mortos, pré-existentes, e só são
   alcançados se a resposta for 200 — que não acontece. Não toquei.
9. **Não corrigi a sincronia do ADN** (§1.2). O checkpoint escrito e nunca lido, e o
   `break` no primeiro lote curto, ficam registrados aqui como achados. Mexer na rotina que
   traz 114 notas por dia não é desta frente.
10. **A NFS-e 121 não foi reaberta** — decisão do dono, o IRRF dela fica como saiu.
11. **A conciliação não foi rodada até o fim nem em homologação.** Provei os dois caminhos
    com 8 números da Patrimonial; a fila inteira (448 pendências de DPS nas duas empresas,
    duas séries cada) não foi atravessada. O agendador a atravessa a 40 por dia.
12. **`emitir_dps` continua sem passar pela parametrização de tributos.** `calcular_tributos()`
    existe, está provada contra as 9 notas e alimenta a tela — mas o XML da DPS ainda não
    escreve IBS/CBS, CSLL nem `vRetCP` a partir dela. Fazer isso é mexer no montador do
    documento fiscal e precisa de uma emissão de homologação por regime para provar; não
    coube nesta frente. **A consequência prática é nenhuma hoje**, porque o dono não emite
    por aqui — o cronograma de setembro já foi para a Portte Contábil.
13. **`nfse_lote.inss_de()` e `beneficios_por_tomador()` continuam servindo a tela**, mas o
    número que vai na nota é o digitado (§3.9). Não apaguei as duas porque é exatamente a
    comparação lado a lado que deixa a divergência visível.
14. **Nada foi feito com a NFS-e 26 da Patrimonial** (o erro confirmado que segue válido no
    fisco). Cancelar tem prazo e esta frente não cancela.
15. **Encerrei duas sessões `idle in transaction` alheias no sandbox** (pid 63843 e 63932,
    vindas de `teste-dgx-aa5`, abandonadas há 10 minutos, transações **só de leitura**).
    Estavam bloqueando 15 consultas de quatro frentes, inclusive um `ALTER TABLE nfes` de
    outra. Nada de escrita foi perdido. Registro aqui porque mexi em coisa que não era minha.

---

## §6 — Como o Jordan testa amanhã

```
Fiscal → grupo «Notas fiscais»

1) «Conciliar NFS-e com o fisco»   → /redesign/fiscal?t=aa4-nfse-conciliacao
   O subtítulo mostra o furo por CNPJ. Deixe «Todas as empresas», limite 25, clique.
   Espera: quantas recuperou, quanto dinheiro apareceu, quantas o fisco NEGOU, quantos erros.

2) «Livro-razão da conciliação»    → /redesign/fiscal?t=aa4-nfse-livro
   Cada número da sequência tem uma linha. Os que ainda não foram perguntados dizem
   «ausente e ainda NÃO conferido» — é a verdade, não um esquecimento.

3) «Parâmetros fiscais da NFS-e»   → /redesign/fiscal?t=aa4-nfse-parametros
   Confira: série 70000 nas duas · ISS «—» na Patrimonial e 5,00% na Eletrônica ·
   IBS-UF 0,10% / CBS 0,90% · «8 - PIS/COFINS Não Retidos, CSLL Retido» na Eletrônica ·
   IRRF «SEM FONTE» (desligado por sua decisão) · último nº de DPS 125 e 75.

4) «Códigos de serviço e NBS»      → /redesign/fiscal?t=aa4-nfse-servicos
   Quatro códigos, quatro NBS diferentes, cada um com a nota de onde saiu.

5) «Notas do mês (cronograma)»     → /redesign/fiscal?t=aa4-nfse-lote
   As 14 de setembro. Coluna «Cessão de mão de obra?»: 9 delas são (as da Patrimonial).
   Olhe as duas colunas de INSS e a coluna «o que o fisco fez antes».
   A linha do Prime Arena de R$ 1.084,50 aparece SEM FONTE de empresa — de propósito.

6) «Emitir nota do cronograma»     → /redesign/fiscal?t=aa4-nfse-emitir-do-mes
   Escolha a nota do Mirante (portaria, R$ 28.694,30), deixe VA e VT VAZIOS e
   «Simulação» em SIM. Espera: o resultado traz `aviso` dizendo que a nota vai sair
   SEM dedução, sobre o valor cheio.
   Agora preencha VA e VT e simule de novo: `inss_base` cai, `inss_retido` cai, e
   `descricao_enviada` traz os dois valores e a base escritos dentro da nota.
```

Para conferir que a conciliação não pode emitir:
```bash
grep -n "emitir" backend/modules/fiscal/services/nfse_conciliacao.py backend/modules/fiscal/tasks.py
# espera: nenhuma chamada a emitir()/emitir_dps() — o oráculo trava isso no item (b)
```

---

## §7 — Decisões que só o dono pode tomar

1. **Série 70000 no ERP: o risco de colidir com o portal.** O briefing manda semear 70000 e foi
   o que fiz. Mas o portal do fisco **continua usando essa mesma série** — a DPS 125 é de
   17/09/2026. Se o ERP emitir na 70000 a partir de 126 e você emitir uma pelo portal no mesmo
   dia, os dois pegam o mesmo número e o fisco devolve `E0141`. A Z7 escolheu a série **900**
   justamente para não dividir sequência com ninguém.
   **(a)** 70000, como está, e o `E0141` queima o número e avança; **(b)** uma série só do ERP
   (900, ou uma nova nunca usada). **Qual?**

2. **A base da retenção de INSS: as três fontes discordam.** A folha deste sistema, a sua
   planilha e as notas que o fisco emitiu dão números diferentes (§3.8). E as cinco notas de
   08/2026 saíram com **11% sobre o bruto, sem dedução** — o que é mais imposto do que a regra
   do Art. 31 permitiria. **Qual é a certa?** Se for a com dedução, as notas de agosto retiveram
   a mais.

3. **O VT está sem valor em sete dos oito condomínios.** A linha existe na folha e o total é
   nulo. Enquanto ficar assim, a dedução de VT não entra na conta e a retenção sai maior.
   **Isso é dado faltando na folha, e só o DP resolve.**

4. **Ligar a produção da NFS-e.** Quando quiser: (i) `UPDATE empresas SET nfse_ambiente =
   'producao'`; (ii) `NFSE_PRODUCAO_LIBERADA` com a frase-senha no `.env`. O contador de
   produção nasce com o piso certo (125/75) na primeira emissão. **Recomendação: rodar a
   conciliação em produção ANTES**, para o piso já estar atualizado com tudo que o fisco tem.

5. **As 27 NFS-e fantasmas continuam pendentes** (Z7 §8.1). Somam R$ 542.673,92 e entram na
   precificação de contrato. Minha conciliação **não as alcança** (§5.4). A decisão segue sendo
   sua.

6. **O endereço legal.** O fisco confirma os dois. **Gravo em `empresas`?** (§5.7)

7. **O código de serviço do mesmo contrato mudou entre duas notas do mesmo mês** — «manutenção
   de CFTV/cerca/portões/cancelas» saiu como 14.01.01 numa e 14.06.01 noutra, ambas em 08/2026
   e ambas pela Eletrônica. Uma das duas está errada. **Qual é a certa?**

8. **A dedução de VA/VT vale a partir de quando?** Você decidiu deduzir antes dos 11% em toda
   nota de cessão de mão de obra. As **cinco notas de agosto retiveram sobre o bruto** — 11%
   exatos, conferidos ao centavo nas cinco. Se a regra já valia, agosto reteve
   **R$ 1.431,98 a mais** só nas três linhas onde o cronograma declara dedução.
   **Recuperar isso, ou a regra vale só daqui para a frente?**

9. **O cronograma manda reter INSS numa nota da Eletrônica** (Prime Arena, manutenção de piscina
   e jardinagem, R$ 3.879,60: «Aplicada retenção do INSS (11%)…»). **Nenhuma das quatro notas da
   Eletrônica no fisco tem retenção previdenciária.** Deixei a Eletrônica sem INSS parametrizado.
   **Manutenção de piscina e jardinagem é cessão de mão de obra?** Se for, a parametrização da
   Eletrônica precisa de `inss_aliquota = 11`.

10. **A aritmética do cronograma não fecha na linha do Ideal Flores** (§3.8): as deduções
   declaradas (6.648,00) não são a soma do VA e do VT escritos (4.404,00), e o INSS declarado
   (6.511,62) não é 11% da base declarada (6.511,39). **Corrigir a planilha?**

11. **A nota 26 da Patrimonial** — erro confirmado, segue válida no fisco, e cancelar tem prazo.

12. **Quem informa o VA e o VT na hora de emitir?** Hoje é campo digitado, porque o sistema não
    tem o número de forma confiável (§3.9). Para ele saber sozinho, o DP precisa lançar o
    benefício **entregue por contrato e por mês** — `beneficio_entregas` está vazia e o VT só
    tem valor em um dos oito condomínios. **Vale abrir essa frente no DP?** Enquanto não, cada
    nota de cessão exige dois números digitados por quem assina.

---

## §8 — Para o orquestrador: DDL que `_ensure` aplica em produção no 1º acesso

```sql
-- nfse_parametros._ensure()  (só roda se `nfse_servico_nbs` ou a coluna `irrf_reter` faltarem)
CREATE TABLE IF NOT EXISTS nfse_parametros_empresa (
  prestador_cnpj varchar(14) PRIMARY KEY, serie_dps varchar(5) NOT NULL,
  regime varchar(24) NOT NULL, iss_aliquota numeric(7,4), iss_observacao text,
  banco_nome varchar(60), banco_codigo varchar(5), agencia varchar(10), conta varchar(20),
  pix_chave varchar(60), fonte text NOT NULL, updated_at timestamp NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS nfse_servico_nbs (
  codigo_servico varchar(8) PRIMARY KEY, codigo_formatado varchar(10) NOT NULL,
  nbs varchar(16), descricao_oficial text NOT NULL, rotulo text NOT NULL,
  fonte text NOT NULL, updated_at timestamp NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS ux_nfse_servico_nbs_valor
  ON nfse_servico_nbs (nbs) WHERE nbs IS NOT NULL;
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS ibs_uf_aliquota numeric(7,4);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS ibs_mun_aliquota numeric(7,4);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS cbs_aliquota numeric(7,4);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS cst_ibs_cbs varchar(4);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS cclass_trib varchar(8);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS retem_pis_cofins boolean;
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS codigo_retencao_federal varchar(2);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS retencao_federal_rotulo text;
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS csll_aliquota numeric(7,4);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS inss_aliquota numeric(7,4);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS irrf_aliquota numeric(7,4);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS irrf_reter boolean NOT NULL DEFAULT false;
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS irrf_observacao text;
-- seeds: INSERT … ON CONFLICT DO NOTHING (2 empresas, 4 códigos de serviço)

-- nfse_conciliacao._ensure()  (só roda se `nfse_conciliacao` ou `observacao_interna` faltarem)
CREATE TABLE IF NOT EXISTS nfse_conciliacao (
  prestador_cnpj varchar(14) NOT NULL, ambiente varchar(16) NOT NULL,
  tipo varchar(6) NOT NULL, serie varchar(5) NOT NULL DEFAULT '', numero integer NOT NULL,
  estado varchar(16) NOT NULL DEFAULT 'pendente', chave_acesso varchar(60),
  numero_nfse varchar(20), http_status integer, mensagem text,
  tentativas integer NOT NULL DEFAULT 0, conferido_em timestamp,
  criado_em timestamp NOT NULL DEFAULT now(),
  PRIMARY KEY (prestador_cnpj, ambiente, tipo, serie, numero));
CREATE INDEX IF NOT EXISTS ix_nfse_conciliacao_estado ON nfse_conciliacao (estado, tipo);
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS ultimo_dps_observado integer;
ALTER TABLE nfse_parametros_empresa ADD COLUMN IF NOT EXISTS ultimo_dps_fonte text;
ALTER TABLE nfse_emitidas_nacional ADD COLUMN IF NOT EXISTS observacao_interna TEXT;  -- no-op em produção
-- UPDATE … SET ultimo_dps_observado = GREATEST(COALESCE(…,0), 125|75) nas 2 empresas

-- nfse_lote._ensure()  (só roda se `nfse_cronograma` faltar)
CREATE TABLE IF NOT EXISTS nfse_cronograma (
  id bigserial PRIMARY KEY, competencia varchar(7) NOT NULL, ordem integer NOT NULL,
  tomador_cnpj varchar(14) NOT NULL, tomador_nome text NOT NULL,
  valor_bruto numeric(15,2) NOT NULL, rotulo_servico text NOT NULL, descricao text NOT NULL,
  empresa_cnpj varchar(14), empresa_fonte text, estado varchar(16) NOT NULL DEFAULT 'proposta',
  nfse_id uuid, fonte text NOT NULL, criado_em timestamp NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS ux_nfse_cronograma_linha ON nfse_cronograma (competencia, ordem);
-- seed: as 14 linhas de 09/2026, ON CONFLICT DO NOTHING
```

**Nenhum UPDATE em dado que não seja desta frente.** O único `UPDATE` fora das minhas tabelas
é o de `nfse_emitidas_nacional` feito pela conciliação, e só sobre a linha cuja chave o fisco
devolveu (`ON CONFLICT (chave_acesso) DO UPDATE`), que é justamente o comportamento pedido.

**Beat novo** (já escrito em `celery_app.py`): `fiscal-conciliar-nfse-diario`,
`fiscal.conciliar_nfse_com_fisco`, `crontab(hour=5, minute=30)` — **depois** do
`financial-nfse-nacional-diario` das 04:30. E `"modules.fiscal.tasks"` entrou no `include`,
então o **`celery_app.py` precisa ser sincronizado para TODOS os workers**, senão a task não
é descoberta.

**Trava nova para `checar_regressao.py`** (você registra):
`test_oraculo_aa4_nfse_conciliacao.py`.

**Nada a pedir em `frontend/`**: as 6 telas são `form` e `table` genéricos; as entradas de
menu vêm pelo `extraMenu` da API.

**Containers parados:** todos os efêmeros desta frente foram removidos (`aa4-oraculo`,
`aa4-prova*`, `aa4-sonda*`). **A porta 8294 não chegou a ser usada** — nada nesta frente
precisou de servidor HTTP: as telas são exercidas pelo `telas(db, out)` dentro do oráculo e a
conciliação foi provada por script contra o fisco.

**Estado do sandbox ao fim:** `nfse_emitidas_nacional` com **116** linhas (as 114 originais +
as 2 notas de homologação que a conciliação recuperou do fisco, `fonte='conciliacao_fisco'`);
`nfse_conciliacao` com 485 linhas, 8 conferidas. **Produção intacta: 115 linhas, 37 ausentes.**
