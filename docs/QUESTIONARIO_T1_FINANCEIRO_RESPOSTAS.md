# Respostas ao questionário do T1 — financeiro

Respondido em 12/08/2026. Onde eu medi, o número está aqui. Onde não sei, digo que não sei.

---

## A. O que está em curso

**1-2.** Os três arquivos (`banking/page.tsx`, `contabilidade/page.tsx`, `dashboard/page.tsx`)
**não são meus** — não toquei em frontend nesta sessão. Trabalhei só em backend + banco.
Quem estiver com eles precisa responder; eu não sei o estado nem o prazo.

**3. Intocável até eu terminar:** nada de arquivo. Mas duas coisas de DADO:

- `accounting_entries` do período **≥ 01/08/2026** — o razão bate com o extrato ao centavo
  (Δ R$0,00) e qualquer escrita fora de `extrato_para_razao` quebra isso em silêncio.
- As tabelas `backup_*_20260811` e `backup_*_20260812` — são o desfazer de 8 correções
  materiais feitas hoje (duplicatas, transferência do grupo, cartões, memo, empréstimo).
  Não apague.

## B. Decisões que viraram código

**4. `bc2c7fde9` não é meu** — é da sessão que mexeu em `contrapartida_entrada` em 11/08
21:45. Não posso resumir a regra dela sem chutar. O que sei da minha metade: a função
passou a aceitar `categoria` além da descrição, e a ordem de teste é GRUPO → cliente →
transitória.

**5. Só Cora.** O memo é a justificativa que o Jordan escreve **no app do Cora** na hora de
pagar, e ela volta no extrato. Medido: 67% das saídas do Cora em agosto (74% do valor) têm
memo. O Inter tem campo de descrição na API (140 chars) mas **ainda não confirmei se ela
volta no extrato** — as descrições do Inter que vejo são todas do formato do banco
(`PIX ENVIADO - Cp :`). Se não voltar, o caminho é guardar a descrição no envio.

A regra tem duas metades com precedência OPOSTA, e isso é o que a faz funcionar:
- **natureza** (Uber, café, material) VENCE o cadastro — café é café mesmo pago a um PJ;
- **relação** (salário, adiantamento) PERDE para o cadastro — ele escreve "Salario" ao pagar
  a Pyetra, que é PJ; a palavra é coloquial, o vínculo é fato.

Quebra se: alguém inverter essa ordem, ou se o prefixo `[CORA]` mudar (`_memo()` o remove).

**6. Sim, três, e um já virou código hoje:**
- ✅ **cartão pessoal usado para compra da empresa** → `reembolso` (5.1.1.08). Itaú R$4.706,54
  + Nubank R$2.000. ⚠️ Pendente: as notas dos materiais. Sem elas é indistinguível de
  distribuição disfarçada.
- ⬜ **adiantamento de salário** → mapeado para 2.1.1.01 (abate o passivo da folha), mas
  NÃO validado com o Jordan.
- ⬜ **aporte de sócio** — não existe caso registrado ainda; a conta 2.1.5.01 hoje só tem
  saída (R$27.900).

**7. Duas listas, em `plano_contas_caixa.py`:**
```python
_GRUPO = ("CONECTA MAIS", "CONECTAMAIS", ..., "JORDAN SANTOS DE JESUS LTDA")
CNPJS_DO_GRUPO = ("35710481000103", "66014833000110")
```
O **CNPJ é o que decide** — o nome é rede de segurança. Motivo: o Cora devolve no favorecido
a razão social ANTIGA da Eletrônica ("JORDAN SANTOS DE JESUS LTDA"), e por isso R$13.800 de
transferência Patrimonial→Eletrônica estavam lançados como **retirada de sócio de um lado e
recebimento de cliente do outro** — a mesma transferência inflando as duas pontas.

Fragilidade conhecida: lista fixa. CNPJ novo no grupo tem que entrar à mão.

**8. SIM, e é furo meu — obrigado pela pergunta.** Três serviços escrevem em
`accounting_entries` e **nenhum respeita o corte**:

| serviço | alcançável hoje | lançamentos |
|---|---|---|
| `conciliacao_liquido_service` | **SIM** — botão `/action/conciliar-liquido` | 65 `baixa_recebimento` |
| `estoque_real_service` | via `inventory_controller` | 1 `baixa_estoque` |
| `accounting_seed_service` | seed | 97 `nfse_emitida` + 85 `tributo_iss` + 188 `banco_inter` |

Ou seja: o corte que eu construí tinha **três portas por fora**, e a mais aberta era
justamente a que um humano alcança clicando.

✅ **FECHADO (migration `e5f6a7b8c9d0`, 12/08).** Não remendei serviço por serviço — a regra
desceu para o BANCO, porque remendo não cobre o próximo escritor que aparecer. Trigger
`trg_bloqueia_periodo_fechado` em `BEFORE INSERT ON accounting_entries`.

Só INSERT. **UPDATE segue livre de propósito**: corrigir lançamento errado do passado é
legítimo (foi o que se fez hoje com a transferência entre CNPJs); o que não pode é
lançamento NOVO nascer em período fechado. Provado nos três casos: INSERT em 15/03
recusado com mensagem clara, INSERT em 11/08 passa, UPDATE em lançamento antigo permitido.

⚠️ A data está no trigger E em `periodo_contabil.CORTE_CONTABIL` — mudar o corte exige os
dois. Ler de tabela de config custaria mais máquina do que a regra vale com um corte só.

## C. Dinheiro que sai

**9. VIVO: só o Inter.** 26 pagamentos confirmados, R$35.813,99, entre 03/07 e 11/08
(`inter_payments`). **Cora é casca para PIX** — e não por falta de código: o Cora **não tem
PIX de saída** na API, nem por chave nem copia-e-cola. Só TED por dados bancários completos,
e a TED sai como `INITIATED` (aprova no app). `CoraAdapter.initiate_payment` levanta
`NotImplementedError` de propósito.

Isso importa mais do que parece: **89% do dinheiro sai pelo Cora** (R$136.426,78 de
R$153.259 em agosto). O caminho "pagar tudo pelo sistema" alcança 11% hoje.

**10. Não sei responder com prova.** Não auditei os caminhos de OTP — não é meu escopo
(fronteira money-out: analisar/aprovar é meu, pagar é T1). Trate como NÃO VERIFICADO.

**11-12. Não sei.** Não toquei nessas telas nem nessas rotas. O que posso afirmar do lado
do backend: `/api/v1/financial/*` responde (usei `relatorios/balancete` hoje) e
`/api/v1/redesign/data/{slug}` é o dispatcher vivo. Se a tela chama
`/api/v1/banking/payment` e dá 404, ou a rota nunca existiu ou foi renomeada antes de mim.

**13. Inter transmite; Cora não.**
- Inter → **CONECTAMAIS ELETRONICA** (35.710.481/0001-03)
- Cora → **CONECTAMAIS PATRIMONIAL** (66.014.833/0001-10), só leitura de extrato + saldo

## D. O que é "fechado"

**14. Cinco coisas concretas que faltam:**
1. **Patrimônio Líquido** — zero lançamento em 3.x. Sem PL não há balanço patrimonial
   (é 501 honesto), o resultado nunca é encerrado (2027 somaria em cima de 2026), e
   distribuição de lucro isenta não tem base escritural.
2. **Saldo de abertura de PASSIVOS/ATIVOS no corte.** Provei o do caixa (R$18.663,83, dois
   caminhos independentes) e **não registrei mais nada**. A empresa devia R$12.000 à Denise
   em 31/07 e o razão não sabe — a conta 2.1.6.01 está com saldo DEVEDOR de R$12.300.
3. **Pagamento nascer no sistema.** Hoje 41 de 175 saídas do período aberto (23,4% por
   linha, 49,1% por valor) têm pagável vinculado. O resto foi pago e explicado depois.
4. **Nota fiscal de PJ.** 9 prestadores, zero NFS-e numa base de 135 notas (2022–2026), e
   10 dos 11 pagamentos de agosto foram para CPF. Só 2 dos 9 têm CNPJ cadastrado.
5. **Transitória vazia.** R$384.580,79 em 5.9.9.01/4.9.9.01.

**15. O que eu NÃO confio hoje:** o **resultado**. O razão acusa prejuízo de R$97.066,72 no
acumulado, e esse número não presta: tem R$458 mil na transitória lançados como DESPESA
inflando o prejuízo, e os dois CNPJs estão misturados. Qualquer DRE hoje é ficção plausível.

**16. Sim:** as contas 3.x do plano estão **corrompidas** — `3.1.1 Portaria`, `3.1.2
Vigilância`, `3.1.3 Limpeza` dentro de *Capital Social* e `3.2.1 ISS 5%` dentro de *Lucros
Acumulados*. É linha de serviço e alíquota no lugar de patrimônio. Não mexi porque refazer
o grupo 3 é parte do trabalho de PL.

**17. O EXTRATO.** Sem ele nada mais é verdade — contas a pagar, conciliação, DRE e guias
todos derivam dele. E ele já quebrou em silêncio três vezes só hoje: 880 linhas duplicadas
(R$563.979,07), sinal invertido em 94 registros (R$785 mil, "RECEBIMENTO" virando saída), e
a ponte recriando duplicata todo dia porque deduplicava por texto de descrição.

Ele é o único desses cinco que **tem** oráculo agora: `caixa_divergente` compara razão ×
extrato com tolerância de R$1,00, e o extrato foi provado contra o saldo do próprio banco
(`/banking/v2/saldo?dataSaldo=`) mês a mês.

## E. Arsenal

**18. Não usei nenhuma das três travas.** Não sabia que existiam. Zero achado, falso ou
verdadeiro — não posso opinar.

**19. O que fiz na mão** (e que um roteiro cobriria):
- puxar o extrato do banco e comparar com o nosso, mês a mês, por multiset (data, valor);
- provar saldo de abertura por dois caminhos independentes;
- verificar drift de worker **depois** de um deploy que se declarou OK.

**20. A ferramenta que eu queria:** um **`checar_oraculo_externo`** — dado um número que a
tela mostra, ele diz *contra qual fonte de fora do sistema esse número foi provado, e
quando*. Todo erro caro de hoje passou por um número que parecia certo e que ninguém tinha
confrontado com o mundo. Não é teste (o teste prova o código contra si mesmo); é a pergunta
"quem, fora daqui, confirma isso?".

---

## Bônus — três erros meus, medidos

**1. Apaguei 169 transações reais (R$12.117,13).** Comparei nosso extrato contra a API do
Inter e tratei "a API não tem linha nesta data" como "isto é duplicata". Mas o `/extrato` do
Inter só retorna de **07/02** em diante (retenção) — as datas de 1 a 6 de fevereiro voltavam
vazias porque estão FORA DA JANELA, não porque as linhas eram falsas. Percebi porque as
somas mensais contra o saldo do próprio banco pioraram em fevereiro em vez de melhorar.
Restaurei do backup. **Lição: fora da janela de cobertura de uma fonte, ausência não é
prova.**

**2. Achei que `current_balance` estava parado desde abril e disse isso ao Jordan.** Eu lia
`last_sync_at`, que é coluna **morta** em `bank_accounts` — ninguém escreve nela. Quem grava
é `last_balance_update`, e estava fresco. Cheguei a desenhar um alarme inteiro em cima dessa
premissa falsa. **Lição: antes de concluir "está velho", confirme que alguém escreve naquele
campo.**

**3. Deixei um alarme que tocaria 21 horas por dia.** Agendei a escrituração às 05:20, mas
os extratos chegam 08:00 e 08:10 — toda movimentação esperaria ~24h para virar lançamento, e
o alarme (que roda a cada 15 min contando movimentação sem lançamento) acusaria a defasagem
normal como defeito. Percebi ao reconciliar o Cora. **Lição: alarme que toca sempre é alarme
que ninguém lê — o corte temporal é o que o mantém crível.**

O padrão dos três: **eu estava confiante e errado**, e o que me pegou foi sempre uma medição
contra algo de fora, nunca uma releitura do meu próprio código.
