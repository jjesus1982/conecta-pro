# DP — o padrão que se repete em todos os atos (2026-08-04)

> Medido três vezes, em três atos independentes, sempre com o mesmo resultado.
> A folha paga (reconciliada Δ=0 contra a Portte) é o oráculo em todos os casos.

## O número

| Ato | O DP registra | A realidade (folha) | Cobertura |
|---|--:|--:|--:|
| Afastamento | 7 pessoas | **29** | **24%** |
| Férias | 5 pessoas | **27** | **18%** |
| Admissão | **0** concluídas | 3 admitidos em 19/07 | **0%** |

Férias: 22 pessoas receberam R$27.959 de férias **sem nenhuma solicitação registrada**.
Afastamento: 22 pessoas receberam afastamento **sem nenhum registro**.
Admissão: 3 pessoas entraram na folha de julho **sem passar pelo módulo de admissão**.

## O que isso é — e o que não é

**Não é bug.** Os módulos funcionam: têm endpoint, cálculo real, documento legal, e as telas
foram religadas com ação por linha (testadas por curl e browser). O código faz o que promete.

**É adoção.** O fluxo real de RH acontece **fora do sistema** — atestado no papel, aviso de férias
combinado no WhatsApp, admissão fechada direto com a contabilidade. O sistema é preenchido
depois, parcialmente, ou não é.

## Por que isso é o bloqueio real dos 6 meses

Hoje isso não dói, porque a **Portte é a rede de segurança**: o que não entra no nosso sistema
entra no dela, e a folha sai certa mesmo assim.

Quando ela sair, essa rede some. Aí:

- Férias não registrada = saldo errado no TRCT (já provado: a rescisão pagaria período gozado)
- Afastamento não registrado = folha sem o desconto/afastamento correto e S-2230 não transmitido
- Admissão fora do fluxo = sem contrato, sem ficha de registro, sem S-2200

**Nenhum desses problemas se resolve escrevendo código.** O cálculo já está certo — validado
centavo a centavo contra a Portte. O que falta é o dado entrar.

## Tabelas de férias: qual é a viva

| Tabela | Linhas | Última atividade | Veredito |
|---|--:|---|---|
| `hr_vacation_requests` | 19 | **16/07/2026** | ✅ **é a viva** — usar esta |
| `employee_vacation_periods` | 67 | 28/03/2026 | congelada desde março |
| `hr_vacation_periods` | 67 | 28/03/2026 | congelada, duplica a anterior |
| `employee_vacation_requests` | 15 | 01/04/2026 | morta |
| `vacation_requests` | 10 | 01/04/2026 | morta |

As duas tabelas de **períodos** (que guardam o saldo aquisitivo) estão paradas desde março com
`days_used = 0` em 100% dos 67 registros — é delas que sai o "saldo de férias" das telas. Ou seja,
**o saldo exibido hoje não desconta nada do que já foi gozado**.

## Recomendação

O trabalho de código que faz diferença agora é pequeno; o que decide é processo:

1. **Definir `hr_vacation_requests` como fonte única** e aposentar as 4 outras (2 mortas, 2 duplicadas).
2. **Fazer o registro ser o caminho, não o espelho** — enquanto der para admitir/afastar/tirar férias
   sem passar pelo sistema, a cobertura não sobe. Isso é decisão de operação, não de engenharia.
3. Só depois disso vale construir cálculo de afastamento, recibo de férias e o resto — porque
   cálculo sobre registro de 20% de cobertura não serve para nada.

## O que já está protegido

A rescisão **não** paga férias em duplicidade em silêncio: implementei o alerta que lê a evidência
na folha e avisa quem homologa. É mitigação, não solução — a solução é o registro existir.

---

## FONTE ÚNICA DE FÉRIAS — decidida e aplicada (2026-08-04)

Escolhi pelos **consumidores reais**, não por preferência. E são DUAS escolhas, porque
*solicitação* e *período aquisitivo* são coisas diferentes — não são tabelas duplicadas.

| Papel | **Fonte única** | Por quê |
|---|---|---|
| Período aquisitivo (saldo) | **`employee_vacation_periods`** | lida pelo portal do funcionário, pela tela de saldo do redesign e **pela rescisão** (`termination_service`) |
| Solicitação de férias | **`hr_vacation_requests`** | única viva (ativa até 16/07); é a que a tela `ferias` usa e onde religuei o "Aprovar" |

**Não canônicas:** `hr_vacation_periods` (só o contexto jurídico lê), `employee_vacation_requests`
e `vacation_requests` (paradas desde abril).

### Não derrubei as tabelas — de propósito

Elas têm consumidores reais em portal, redesign e controllers. Dropar agora quebra tela em
produção. Aposentar exige migrar cada leitor primeiro; é trabalho de refatoração, não de decisão.
O que resolvia o dano **imediato** era o saldo mentiroso, e isso foi corrigido.

### Correção aplicada no saldo

`days_used` estava **0 em 100% dos 67 períodos** — o saldo exibido não descontava nada do que
já havia sido gozado. Atualizei a partir das solicitações **APROVADAS** (evidência dura):

| Colaborador | Direito | Usados | Saldo |
|---|--:|--:|--:|
| ADAILSON SERRA ALVES | 30 | 30 | 0 |
| ANTONIO CARLOS VIEIRA | 30 | 30 | 0 |
| EDIWILSON CORREA MARQUES | 30 | 19 | 11 |
| FRANCISCO RAMON FARIAS DE SOUZA | 30 | 30 | 0 |

**Usei só as APROVADAS**, não as 14 `SUBMITTED`. Prova de que está certo: ADAILSON tem
solicitação submetida para julho, mas bateu ponto **116 vezes** em julho — não tirou. Contar
pedido não aprovado como gozado zeraria o saldo de quem ainda tem direito.

Backup: `auditoria/employee_vacation_periods_pre_fonte_unica_2026-08-04.json`.

### O que continua errado (e por que não forcei)

**22 pessoas gozaram férias segundo a folha e não têm solicitação nenhuma** — para essas, o
saldo segue mostrando 30 dias. Não dá para derivar os dias com honestidade: a folha traz
**horas** (`96:00`, `84:00`), e converter hora→dia exige presumir jornada. Em saldo de férias
isso vira dinheiro errado no TRCT.

Essas 22 precisam de lançamento manual do DP — é o mesmo problema de adoção descrito acima,
não um gap de cálculo.
