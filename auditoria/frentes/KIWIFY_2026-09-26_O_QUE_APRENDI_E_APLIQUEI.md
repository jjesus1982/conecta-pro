# Kiwify — o que assisti, o que aprendi, e o que isso achou nos seus números

**Data:** 26/09/2026
**Pedido:** *"assista TODOS OS VÍDEOS, exceto do gideão… aprenda tudo"*

---

## 1. O que foi assistido, de fato

**32 de 32 vídeos transcritos. Zero falhas. 36.138 palavras.**

| curso | vídeos | como chegou |
|---|---|---|
| Gestão Financeira Planilha + Passo a Passo | 19 | API do dashboard |
| Planilha de Precificação | 3 | API do dashboard |
| Planilha de Planejamento Tributário | 1 | API do dashboard |
| FISCO IA | 9 | área de membros (`members.kiwify.com`) |
| Multiplicador de Economia Fiscal | 0 | é o PDF que você já tinha mandado |
| Planilhas empresariais | 0 | só link externo |
| GIDEÃOIA | — | **pulado, conforme seu pedido** |

Mais **23 planilhas** baixadas dos anexos, incluindo a `1- Planejamento-Tributario_4.5.xlsx`,
a `PLANILHA-TRIBUTÁRIA.xlsx` do FISCO IA e a `Ponto_de_Equilibrio_V1.xlsx`.

**Três ressalvas honestas sobre o material:**

- Os módulos 3 a 7 do FISCO IA (Simples Nacional, MEI, Lucro Presumido, Abertura de
  Empresas) **não são aulas** — são links para GPTs customizados no chatgpt.com. Não há
  conteúdo a aprender ali.
- A aba `REAL` da planilha de planejamento tributário usa **PIS 1,65% e COFINS 7,6%**, as
  alíquotas NÃO-cumulativas. Para vigilância e limpeza são 0,65% e 3,00%, cumulativas por
  lei (Lei 10.833 art. 10, XXIV). Quem usasse essa planilha para a Conecta Mais veria o
  Lucro Real **5,6 pontos mais caro do que é**.
- O autor declara: *"Eu não sou contador de formação, sou administrador."*

---

## 2. A lição que valeu a noite

Da aula de indicadores (Macro Bit, "Analisando os Indicadores"):

> *"A lucratividade do meu negócio foi de 86,91%… porém ele só foi lucrativo porque teve uma
> receita NÃO operacional. A minha operação me deu prejuízo de 13,79%. Já vi diversas
> empresas onde o sócio ficava aportando dinheiro para manter a empresa viva. **Não faz
> sentido aportar dinheiro se a tua operação é ruim.**"*

E o diagnóstico que decorre dela:

> *"Se o meu negócio tem uma margem boa, mas o meu resultado operacional é fraco, então o
> custo da minha operação está caro demais."*

Apliquei isso aos seus números, e o resultado é o achado do dia.

### Resultado OPERACIONAL, competência 08/2026

| | receita de serviço | despesa operacional | **resultado operacional** | % |
|---|---|---|---|---|
| Patrimonial | 262.161,56 | 256.542,76 | **+5.618,80** | +2,1% |
| **Eletrônica** | 13.300,00 | 31.454,13 | **−18.154,13** | **−136,5%** |

(despesa financeira fora dos dois lados: juros e financiamento são custo de capital, não da
operação — misturar os dois esconde qual dos dois problemas a empresa tem)

**A Eletrônica gasta 2,4× o que fatura só para existir.** Ela passou os contratos para a
irmã em junho e **a estrutura não encolheu junto com a receita**.

Isso muda a conversa sobre "recuperar a Eletrônica": no patamar de faturamento de hoje, ela
não tem uma operação a recuperar — tem uma estrutura de custo sem receita que a sustente.
Ou a receita volta, ou a estrutura encolhe para caber em R$ 13–25 mil/mês.

---

## 3. O que a aplicação achou, que ninguém tinha visto

### a) A Eletrônica não tem folha desde junho — e paga R$ 11.970/mês de "Vale Refeição"

`hr_payslips` da Eletrônica: **zero holerites** desde 06/2026. Mas a conta
`5.1.1.03 Vale Refeição / Alimentação` recebe R$ 11.970/mês em média (R$ 20.160 em
setembro). Abrindo:

```
15/09  1.120,00  Thiago Da Silva Maquine
17/09    672,00  Andrya Pyetra Sousa De Jesus
17/09    672,00  Francisco Ediney Oliveira De Araujo   ← Técnico Mantenedor
17/09    672,00  Ramon Dos Santos Araujo               ← DEV
17/09    672,00  Sidney Ruan De Souza Pedroza          ← Suporte
```

**São PIX para os PJs que desenvolvem e sustentam o Conecta PRO.** Cruzando com
`employees`, os 7 "ativos" da Eletrônica são: Pedro Rafael (DEV/Suporte), Ramon (DEV),
Sidney Ruan (Suporte), Francisco Ediney e José Rodrigo (Técnicos Mantenedores), um
colaborador de teste, e **você mesmo, cadastrado como "AGENTE DE PORTARIA / candidato"**.

Isto resolve uma pendência que tinha ficado em aberto hoje mais cedo: *"o custo de
desenvolvimento do ERP não é separável no sistema"*. **Ele é — está classificado como
vale-refeição.** E a conta certa, `5.2.1.02 Serviços de TI / ERP`, existe no plano com
**zero lançamentos desde sempre**.

Isso importa para a **Estratégia 9 do Multiplicador (Lei do Bem)**: ela exige controle
contábil segregado do gasto com P&D. O gasto existe, está documentado em PIX com nome e
CPF, e está na conta errada. Reclassificar é barato agora e impossível depois.

### b) O plano de contas não separa receita operacional de não operacional

Todas as receitas estão em `4.1 Receitas Operacionais`. **Não existe grupo de receita não
operacional.** A distinção que a aula ensina a fazer — a que decide se o negócio deve
existir — o sistema ainda não consegue fazer por si.

Hoje isso não distorce o resultado, porque aporte de sócio entra como passivo
(`2.1.5.01`) e não como receita. Mas o dia em que entrar uma venda de bem ou uma
indenização, ela vai somar com faturamento de portaria e ninguém vai perceber.

### c) Quatro contas de despesa numeradas na faixa de receita

`4.1.2 FGTS`, `4.1.3 INSS Patronal`, `4.2.1 Software`, `4.2.2 Infraestrutura` são contas
`EXPENSE` numeradas em 4.x. Estão com **zero movimento** — são linhas órfãs. Não fazem mal
hoje, mas são exatamente o tipo de armadilha que faz alguém ler o plano pelo número.

---

## 4. Vigia novo

`backend/scripts/qa/checar_operacao_que_nao_se_paga.py` — mede receita de serviço menos
despesa operacional (financeiras fora), por empresa, nos 3 últimos meses fechados. **Só
acusa quem está negativo em TODOS eles:** um mês ruim é operação, três seguidos é
estrutura. Hoje devolve **0** — a Eletrônica teve julho positivo (+18,3%), então são 2 de 3
e ele não acusa em cima disso. É o comportamento certo, e por isso ele vale: quando acusar,
vai ser verdade.

---

## 5. O que do material NÃO se aplica aqui

- **Precificação por ficha técnica e por revenda** (7 dos 32 vídeos): é para comércio e
  indústria. A Conecta Mais vende hora-homem sob CCT, com piso definido em convenção.
- **Margem de contribuição sobre custo variável**: numa empresa de portaria o "custo
  variável" é o posto, que é fixo por contrato. O conceito útil aqui é outro — margem por
  contrato, que o sistema já tem.
- **Ponto de equilíbrio por ticket médio**: não há ticket médio; há mensalidade por
  condomínio.

O que se aproveita do material é a **estrutura de leitura** — DRE por competência,
separação operacional × não operacional, e a pergunta "onde está o problema: na margem ou
na estrutura?" — não as planilhas em si.

---

## 6. Onde está tudo

| o quê | onde |
|---|---|
| 32 transcrições com timestamp | `uploads/conhecimento/kiwify/transcricoes/` |
| 23 planilhas dos anexos | `uploads/conhecimento/kiwify/anexos/` |
| inventário de aulas e links | `uploads/conhecimento/kiwify/` |
