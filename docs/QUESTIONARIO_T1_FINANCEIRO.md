# Questionário para o T1 — o que o código não me conta

Só 20 perguntas, e nenhuma delas é consulta: **tudo que dá para medir eu medi** (493 rotas em
`/financial`, 9 builders de tela, as travas, o banco). O que está aqui é o que só quem
trabalhou no módulo sabe — decisão, intenção e julgamento.

Responda curto. Uma linha por pergunta serve. "Não sei" é resposta válida e útil.

---

## A. O que você está fazendo agora (para eu não atropelar)

1. Você está com três arquivos modificados e não commitados:
   `financeiro/banking/page.tsx`, `financeiro/contabilidade/page.tsx`,
   `financeiro/dashboard/page.tsx`. **O que está em curso neles?**
2. Esse trabalho tem prazo/estado — dá para commitar hoje, ou vai ficar aberto?
3. Tem algo no financeiro que você considera **intocável por outra sessão** até você
   terminar? Quais arquivos ou tabelas?

## B. Decisões que viraram código (e que eu poderia desfazer sem saber)

4. `bc2c7fde9` — "transitórias caem 99%, a classificação já estava no extrato". **Qual é a
   regra em uma frase?** Como sei se ela quebrou?
5. `de8dd9ff3` — "o memo do Cora manda, são as palavras do Jordan, não heurística". Isso vale
   para **todos** os bancos ou só Cora?
6. `f85481fe8` — empréstimo tomado é passivo. Existe outro caso do mesmo tipo já decidido
   (adiantamento, aporte de sócio, cartão) que ainda não virou código?
7. Transferência entre nossos CNPJs não é receita nem retirada. **Como o código identifica
   "nosso CNPJ"** — lista fixa, tabela, heurística?
8. O corte contábil de **01/08/2026**: além de `extrato_para_razao` e `ledger_auto_service`,
   tem outro caminho que escreve no razão e precisa respeitá-lo?

## C. Dinheiro que sai — onde eu não posso nem encostar

9. Quais fluxos de **pagamento estão VIVOS** hoje (mandam PIX/pagamento de verdade) e quais
   são casca?
10. O gate de OTP cobre **todos** eles? Tem algum caminho que paga sem passar pelo gate?
11. `banking/page.tsx` chama `/api/v1/banking/payment` e `/api/v1/integrations/banking` —
    **as duas devolvem 404**. Isso é tela em construção, rota renomeada, ou funcionalidade
    abandonada?
12. Mesma pergunta para `/api/v1/financeiro/inter` (2 páginas),
    `/api/v1/financial/pagamentos-diaristas` e `/api/v1/financial/pagamentos-pj`.
13. Cora e Inter: qual está transmitindo de verdade hoje, e para qual CNPJ?

## D. O que é "fechado" para você

14. Se o financeiro estivesse **pronto, sem pendências**, o que estaria funcionando que hoje
    não está? Liste 3 a 5 coisas concretas.
15. Qual parte do financeiro você **não confia** hoje — mesmo que a tela mostre número?
16. Tem número exibido em alguma tela que você sabe que está errado, ou defasado, e ficou
    para depois?
17. Contas a pagar/receber, extrato, conciliação, DRE e guias **não têm nenhum oráculo**.
    Qual desses erraria mais caro se quebrasse em silêncio?

## E. Sobre o Arsenal (para eu consertar a ferramenta, não só o módulo)

18. Você já usou alguma das travas (`checar_repositorio`, `cacar_fabricacao`,
    `checar_vocabulario`)? Alguma te deu **achado falso**?
19. O que o roteiro de fechamento **não cobre** e você teve que fazer na mão no financeiro?
20. Se você pudesse pedir UMA ferramenta que não existe, qual seria?

---

**Bônus, se sobrar paciência:** aponte um erro que você cometeu no financeiro e como
percebeu. Erro medido vale mais para o Arsenal que acerto narrado — as três regras que ele
tem hoje ("prove o arreio", "falso positivo mata a confiança", "conserte a família") saíram
de erros, não de boas práticas.
