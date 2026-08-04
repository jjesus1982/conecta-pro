# Folha — paridade com a Portte (5 frentes) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps usam checkbox.
> **ponytail OBRIGATÓRIO.** Oráculo = `auditoria/COMPARACAO_PORTTE_x_CONECTA_julho2026.md`.

**Goal:** Fechar as 5 divergências medidas contra a Portte em julho/2026 (Σ|Δ| R$10.664 em 51 pessoas),
reusando o que já existe. A Portte é a fonte da verdade nos próximos 6 meses.

**Descoberta que organiza o plano:** os itens 3 e 4 têm **causa raiz única** — `horas_reais_ponto`
pareia por `punch_type`, e as batidas do noturno vêm quase todas tipadas `entrada`. Uma correção
resolve os dois.

## Global Constraints
- **Nunca fabricar.** Sem ponto = 0 + aviso, nunca estimativa. Foi assim que o C1 evitou o bug do +5,5k.
- **Reusar, não duplicar.** 6 arquivos tocam horas de ponto; a técnica correta (pareamento por
  alternância) já existe em `redesign_builders/departamento_pessoal.py`. Ela deve MIGRAR para
  `horas_service.py` (o compartilhado), não ser copiada.
- **Espelho supersede cálculo.** Onde `folha_verba_espelho` tem linha, o motor não recomputa (senão
  dobra). Todo fix precisa respeitar `tem_espelho`.
- Money-out é T1. Nada aqui paga.

---

### Task 1: Código de rubrica 0020 duplicado (trava o eSocial)

**Files:** Modify `modules/people_management/folha/services/calculo_service.py`

**Problema medido:** `0020` é emitido por DUAS rubricas — "Adicional Noturno" (1.806,92) e
"Salário Família" (1.080,64). `codRubr` é chave no S-1010/S-1200; naturezas opostas (noturno incide
INSS, salário-família não) sob o mesmo código = evento rejeitado ou aceito errado.

- [ ] **Step 1:** `grep -n '"0020"' calculo_service.py` — confirmar os 2 pontos de emissão.
- [ ] **Step 2:** Trocar o código do **salário-família** para `0095` (faixa livre; 0090 é DSR).
      Conferir contra `rubricas_folha` que 0095 não está em uso.
- [ ] **Step 3:** Verificar no banco que nenhuma rubrica fica com código repetido:
      `SELECT v->>'codigo', count(DISTINCT v->>'descricao') FROM ... GROUP BY 1 HAVING count(DISTINCT ...) > 1`
      → deve voltar vazio.
- [ ] **Step 4:** Reprocessar julho e confirmar totais inalterados (só o código muda).
- [ ] **Step 5:** Commit.

### Task 2: Pagamento a MAIOR — salário-família e DSR

**Files:** Modify `calculo_service.py`

**Medido:** salário-família nosso 1.080,64 × Portte 763,20 (**+317,44 com MENOS pessoas**);
DSR s/ variáveis nosso 489,35 × Portte 33,19 (**+456,16**).

- [ ] **Step 1: Diagnosticar salário-família ANTES de mexer.** Comparar pessoa a pessoa nossa cota
      × a da Portte. Hipóteses a testar: (a) cota unitária errada, (b) teto de renda não aplicado,
      (c) dependentes a mais. **Medir qual é — não presumir.**
- [ ] **Step 2:** Corrigir só a causa medida.
- [ ] **Step 3: DSR — decisão do Jordan, não minha.** A Portte praticamente não paga DSR sobre
      variáveis (só R$33 de reflexo de HE). Ou ela não paga o devido, ou nós inventamos reflexo.
      **NÃO alterar sem definição** — levar o número e perguntar.
- [ ] **Step 4:** Reprocessar julho, medir o Δ cair, commit.

### Task 3+4: Noturno subcalculado e intrajornada ausente (CAUSA RAIZ ÚNICA)

**Files:** Modify `modules/people_management/ponto/services/horas_service.py`

**Causa raiz:** `horas_reais_ponto` pareia `entrada`→`saida` por `punch_type`. Nas batidas do
noturno o tipo vem errado (RENE: `21:01 entrada` → `09:01 entrada`), então o loop sobrescreve a
entrada e **nunca forma par** → 0 horas → 0 noturno → 0 intrajornada. Explica os 29%.

**Reuso:** a técnica correta (parear batidas ALTERNADAS, atravessando meia-noite) já está provada em
`redesign_builders/departamento_pessoal.py` (furos caíram de 840 → 29). Migrar para cá.

- [ ] **Step 1:** Medir hoje: para os 23 com noturno, quantos formam par por `punch_type` vs por
      alternância. Guardar o número (é o oráculo do fix).
- [ ] **Step 2:** Em `horas_reais_ponto`, parear por **alternância** (1ª→2ª, 3ª→4ª batida) em vez de
      confiar no `punch_type`. Manter os guards existentes (`0 < dur < 24h`).
- [ ] **Step 3:** Corrigir o filtro de mês: hoje `EXTRACT(MONTH) = :m` quebra a jornada que começa
      31/07 22:00 e termina 01/08 07:00. Buscar a janela com margem e atribuir o par ao mês da ENTRADA.
- [ ] **Step 4:** Rodar o motor para julho e comparar noturno com a Portte (alvo: sair de 29%).
- [ ] **Step 5: Intrajornada** — `calculo_service.py:318` tem `intrajornada_valor = Decimal("0")`
      fixo. O C1 removeu a estimativa **de propósito** (fabricava intervalo não registrado).
      Só religar se o ponto pareado der base real; **se não der, manter 0 e avisar** — nunca estimar.
- [ ] **Step 6:** Commit + bake.

### Task 5: Bloco de férias (maior massa, e onde pagamos A MAIS)

**Files:** Modify `calculo_service.py`; reusar `clt_calculator.calcular_ferias` e `hr_vacation_requests`

**Medido:** 13 rubricas ausentes. **Pagamos +R$2.203,85 a mais** por ignorar o adiantamento
(R$3.940,73). Michelangelo ficou +R$808 mais caro que a Portte por isso.

- [ ] **Step 1:** Reusar `clt_calculator.calcular_ferias` (já existe, base-only) + `hr_vacation_requests`
      (fonte única eleita em 04/08). **Não recriar cálculo de férias.**
- [ ] **Step 2:** Emitir as verbas de férias e — o mais importante — **o desconto do adiantamento**,
      que é onde o dinheiro sai errado hoje.
- [ ] **Step 3:** ⚠️ `calcular_ferias` é **base-only** (sem média de variáveis, art. 142 CLT). A Portte
      paga médias (806/807/8189/8190). Implementar a média OU declarar a limitação — não fingir.
- [ ] **Step 4:** Validar contra os 3 casos reais de julho (EDIWILSON, ANTONIO VIEIRA, FRANCISCO).
- [ ] **Step 5:** Commit + bake.

### Task 6: Não perder o afastado / não-ativo

**Medido:** ELEN XAVIER (afastada INSS) e 3 desligados em 22/07 sumiram da folha de julho quando
ela foi regravada às 13:45. Custo: R$893,85 + proporcionais.

- [ ] **Step 1:** Descobrir **qual processo** gerou a folha às 13:45 (não foi o
      `folha_fase_e_persistir.py`, que passa `historico=True`). Três scripts diferentes já geraram
      julho hoje com resultados diferentes.
- [ ] **Step 2:** **Eleger UM script oficial** e documentar. Enquanto houver três, qualquer
      comparação envelhece em horas.
- [ ] **Step 3:** Garantir que o oficial inclui não-ativos com vínculo na competência.

## Ordem e métrica
1 (trava eSocial) → 2 (dinheiro saindo) → 3+4 (causa única) → 5 (maior massa) → 6 (governança).
**Métrica única: Σ|Δ| contra a Portte caindo** — hoje R$10.664 em 51 pessoas.
