# Questionário para o T2 — Departamento Pessoal

Investiguei o módulo antes de perguntar. **Tudo que dá para medir está medido** — 596 rotas,
163 telas, 7.806 batidas, 822 holerites, 9 oráculos e 11 regras proativas. O que está aqui é
só o que o código não responde: decisão, intenção e julgamento.

Responda curto — uma linha serve. **"Não sei" é resposta válida e útil.**

---

## A. O que está em curso (para eu não atropelar)

1. Você está com dois arquivos modificados e um novo, não commitados:
   `employee_portal/controllers/painel_ponto_controller.py`,
   `employee_portal/controllers/primeiro_acesso_controller.py` e
   `ponto/coorte_ponto.py` (novo). **O que está em curso?**
2. `coorte_ponto.py` é peça nova de arquitetura ou script de apoio?
3. Tem alguma tabela ou rotina do DP que outra sessão **não pode** tocar até você terminar?

## B. Dois mundos paralelos — os três que achei e não sei explicar

4. **`/api/v1/people-management/hr` (221 rotas) × `/human-resources` (134 rotas).** São
   camadas diferentes, ou uma é resíduo da reorganização 35→9? Qual está viva?
5. **Ponto: `gp_clock_punches` tem 7.806 batidas (a última é de hoje); `time_entries` tem 0.**
   Duas engrenagens para a mesma coisa? Qual é a verdade do ponto?
6. **`overtime_records` = 0 e `time_justifications` = 0**, mas existem 168 espelhos em
   `time_sheets`. Hora extra e justificativa vivem em outro lugar, ou ainda não são usadas?
7. **`ged_documents` = 0**, e o GED tem 28 rotas e 19 telas (11 com conteúdo). De onde vem o
   conteúdo dessas telas? O GED guarda documento em outra tabela?

## C. A fronteira do DP com dinheiro e com o governo

8. **Folha é dinheiro que sai.** Qual é hoje o gate humano entre "folha calculada" e
   "pagamento efetuado"? Tem algum caminho que paga sem passar por ele?
9. `hr_payslips` tem **822 holerites — 457 `conecta` e 365 `portte`**. Qual das duas fontes
   manda hoje, e em que competência a nossa passou a ser autoritativa?
10. **`eventos_esocial` está com 0 registros e 0 recibos.** Isso significa que nada foi
    transmitido, ou que a transmissão é registrada noutro lugar? (Memória do projeto diz que
    o SST S-2230 chegou a rodar em produção.)
11. Quais eventos do eSocial **são nossos** e quais são da Portte, hoje, na prática?
12. Holerite no portal é o dado mais sensível do módulo (LGPD). Você confia no escopo
    self-only hoje — um funcionário consegue ver o holerite de outro por alguma rota?

## D. Qualidade do que já existe

13. **`payslip_portal_service.py` tem 9 chamadas para métodos que o repositório não tem** —
    é a maior concentração do DP, e é justamente o holerite do portal. Essas rotas estão em
    uso, ou o portal usa outro caminho?
14. Das 163 telas do DP, **21 estão vazias**. 8 são do portal (que precisa de usuário no
    contexto) e 8 são do GED (0 documentos). **As outras 5 são vazio honesto ou tela morta?**
15. Qual parte do DP você **não confia** hoje, mesmo que a tela mostre número?
16. Tem número exibido em alguma tela do DP que você sabe estar errado ou defasado?

## E. O que é "fechado" para você

17. Se o DP estivesse **pronto, sem pendências**, o que estaria funcionando que hoje não
    está? Liste 3 a 5 coisas concretas.
18. O DP é o módulo **mais vigiado** do sistema: 9 oráculos e 11 regras proativas
    (`dp_aviso_previo_vencendo`, `dp_ferias_limite_gozo`, `dp_folha_devida`,
    `dp_ponto_a_fechar`, …). **Alguma delas dá alarme falso ou você já aprendeu a ignorar?**
    Alarme que ninguém lê é pior que alarme nenhum.
19. Se uma coisa do DP quebrasse **em silêncio** e ninguém percebesse por um mês, qual doeria
    mais caro?

## F. Sobre o Arsenal (para eu consertar a ferramenta, não só o módulo)

20. Você já usou as travas de `backend/scripts/qa/`? Alguma te deu **achado falso**?
21. O que o roteiro de fechamento **não cobre** e você teve que fazer na mão no DP?

---

**Bônus, se sobrar paciência:** conte um erro que você cometeu no DP e como percebeu. As
regras mais valiosas do Arsenal hoje vieram de erros medidos, não de boas práticas — o T1
contribuiu com três ("fora da janela da fonte, ausência não é prova"; "confirme que alguém
escreve naquele campo antes de dizer que está velho"; "filtro por texto não é contagem").
