# PROMPT DE RETOMADA — cole isto na sessão nova

---

Continue a paridade da folha com a Portte. **Não re-descubra nada** — a investigação está feita.

**Leia nesta ordem antes de agir:**
1. `MEMORY.md` → `project_prontidao_desligar_portte.md`
2. `auditoria/COMPARACAO_PORTTE_x_CONECTA_julho2026.md` — a comparação completa (1ª passada PDF + 2ª passada banco). **É o oráculo.**
3. `docs/superpowers/plans/2026-08-04-folha-paridade-portte.md` — o plano, já cirúrgico

**Metodologia (inegociável, foi ela que fez isso dar certo):**
- `/superpowers:executing-plans` para tocar o plano tarefa a tarefa
- `/ponytail:ponytail` SEMPRE — reusar antes de escrever; o menor diff que funciona
- `/conecta-pro-skills:folha-cct` ao mexer em verba (a CCT SINDECOMPRESTS é a base)
- `/conecta-pro-skills:veracity-sweep` antes de dar qualquer coisa como pronta
- **Medir antes de concluir.** Esta frente inteira nasceu de eu ter diagnosticado de memória e errado. Nada de "acho que é" — rode a query.

**Métrica única:** Σ|Δ| contra a Portte caindo. Hoje **R$10.664,27** em 51 pessoas (julho/2026).
O Δ agregado (−5,4%) engana: 29 pessoas abaixo, 17 acima, erros se compensando.

---

## Estado: Task 1 ✅ FEITA

Rubrica `0020` estava duplicada (Adicional Noturno + Salário Família). Salário-família virou `0095`.
Verificado: zero códigos duplicados, totais preservados. **Falta bake** (commitado, volátil).

## Task 3+4 — CAUSA RAIZ JÁ ISOLADA (não reinvestigar)

`ponto/services/horas_service.py::horas_reais_ponto` pareia `entrada`→`saida` **confiando no
`punch_type`**. As batidas do noturno vêm quase todas tipadas `entrada`
(RENE: `21:01 entrada` → `09:01 entrada`) → o loop sobrescreve a entrada, **nunca forma par**,
devolve 0 horas → 0 noturno → 0 intrajornada. **É isso que produz os 29%.**

**A correção já existe provada:** pareamento por **alternância** (1ª→2ª, 3ª→4ª batida), que usei em
`redesign_builders/departamento_pessoal.py` — furos de ponto caíram de 840 para 29.
**MIGRAR a técnica para `horas_service.py`** (compartilhado por 6 arquivos). **Não duplicar.**

Bônus a corrigir junto: o filtro `EXTRACT(MONTH) = :m` quebra a jornada que começa 31/07 22:00 e
termina 01/08 07:00. Atribuir o par ao mês da ENTRADA.

⚠️ `calculo_service.py:318` tem `intrajornada_valor = Decimal("0")` **fixo**. O C1 removeu a
estimativa **de propósito** (fabricava intervalo não registrado, bug do +5,5k). Só religar se o
ponto pareado der base REAL. **Sem base = 0 + aviso. Nunca estimar.**

## Task 2 — PAGAMENTO A MAIOR (dinheiro saindo hoje)

| | Nosso | Portte | Δ |
|---|--:|--:|--:|
| Salário-família | 1.080,64 | 763,20 | **+317** (com MENOS pessoas) |
| DSR s/ variáveis | 489,35 | 33,19 | **+456** |

Salário-família: **medir pessoa a pessoa** qual é a causa (cota errada / teto de renda não aplicado /
dependente a mais). Não presumir.

🛑 **DSR precisa de decisão do Jordan, não sua.** A Portte praticamente não paga reflexo sobre
variáveis. Ou ela deixa de pagar o devido, ou nós inventamos. **Levar o número e perguntar.**

## Task 5 — Férias (maior massa, e onde pagamos A MAIS)

13 rubricas ausentes; **+R$2.203,85 a mais** por ignorar o adiantamento (R$3.940,73).
Michelangelo ficou +R$808 mais caro que a Portte só por isso.

Reusar `clt_calculator.calcular_ferias` + `hr_vacation_requests` (fonte única eleita em 04/08).
⚠️ `calcular_ferias` é **base-only** (sem média de variáveis, art. 142). A Portte paga médias
(806/807/8189/8190). Implementar a média OU declarar a limitação — não fingir.

## Task 6 — GOVERNANÇA (fazer cedo, senão tudo envelhece)

**Três scripts diferentes geraram a folha de julho no mesmo dia, com resultados diferentes.**
Um deles perdeu a ELEN (afastada INSS) e 3 desligados — R$893,85 + proporcionais.
**Eleger UM script oficial** e documentar. O `folha_fase_e_persistir.py` passa `historico=True` e
inclui não-ativos com vínculo na competência (é o candidato certo).

---

## Regras operacionais desta base

- **Deploy:** `scripts/deploy_backend_bluegreen.sh`. **Antes, cheque `pgrep -f "deploy_backend_blue[g]reen"`** — há 3 sessões claude paralelas e o lock é compartilhado. **Muitas vezes o bake nem é preciso**: o deploy da outra sessão builda do git e carrega seus commits. **Teste antes de bakear.**
- **Git índice compartilhado:** commitar por pathspec `git commit -- <arquivos>`. NUNCA `git add -A`.
- **Ao gerar relatório, mandar o `scp` na ÚLTIMA LINHA** da resposta (o Jordan lê no Mac).
- Portte/Onvio são intocáveis. `source_system='portte'` é a verdade; nunca sobrescrever.
- Money-out é T1 com gate OTP. Publicar ≠ pagar.

## Rodando em background (não mexer)

Cron horário `scripts/cron_esocial_s1010.sh` tentando capturar os S-1010 no eSocial (os códigos
legais das rubricas — gargalo do S-1200). Tem sonda de saúde: só julga a resposta quando o
governo está respondendo. **Avisa no sino do Conecta PRO** quando capturar ou quando der veredito
de permissão. Governo degradado desde 03/08.

## Contexto maior

Objetivo: desligar a Portte em ~6 meses. Medido: **reconciliar ~95%, substituir ~35%**.
Julho/2026 foi a **primeira folha calculada nativamente** (a Portte não tinha fechado o mês) e a
primeira publicada ponta a ponta. Agora existe oráculo para ela — é o que torna esta frente possível.
