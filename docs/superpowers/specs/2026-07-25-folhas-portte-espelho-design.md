# Espelhar folhas Portte (Jan–Jun 2026) no nosso sistema — Design/Plano

Aprovado por Jordan 25/07. Missão: nossas 6 competências (Jan–Jun/2026) em `hr_payslips` espelhando fielmente as folhas oficiais que a Portte gerou (120+ PDFs no Drive). Loop autônomo; forma delegada; **folha=dado legal, nunca inventar** ([[feedback_dado_real_vs_simulado]], [[folha-cct]]).

## Fonte (Drive `1K7TEggSu1miMfI6UX_PU3bS_76-X_Jzq`)
6 subpastas (Janeiro…Junho). Por mês: por **condomínio (Serviço)** um par **"Folha MM.2026_<Cond>"** (EXTRATO MENSAL detalhado) + **"Recibo Folha MM.2026_<Cond>"** (holerite derivado), mais o **consolidado "Conecta Mais - Geral"**. Algumas folhas foram **alteradas para correção** (2 versões → usar a corrigida).

### Estrutura da Folha Portte (aprendida — Michelangelo 01/2026)
- Cabeçalho: Empresa 25 CONECTA MAIS (CNPJ1 35.710.481/0001-03), Competência, Emissão.
- Serviço = condomínio (nome + CNPJ próprio, ex. Michelangelo 04.911.208/0001-13).
- Por empregado: matrícula, nome, **CPF**, admissão, cargo+CBO, salário, e **rubricas** (código, nome, referência, valor, **P/D**). Totais: Proventos, Descontos, Informativa, Líquido, Base/Valor INSS-FGTS-IRRF.
- Resumo por Serviço + Geral (soma) + Situações (headcount).

## Alvo — `hr_payslips` (quase 1:1)
`condominio_id`, `employee_id`, `reference_year/month`, `base_salary`, `total_earnings`, `total_deductions`, `net_salary`, **`earnings`/`deductions`/`informative` (jsonb=rubricas)**, `inss_base/value`, `irrf_base/value`, `fgts_base/value`, `payslip_type`, `status`, `source_system='portte'`, `external_id`, `import_batch_id` (1 por mês → idempotente/rastreável), `empresa_id` (CNPJ1). Relacionadas: `rubricas_folha`, `payroll_events`.
Estado atual: 03/2026=51, 06/2026=56 payslips (origem a reconciliar); faltam 01,02,04,05.

## Pipeline (loop, 1 mês por ciclo)
1. **Extrair** — ler cada "Folha MM_<Cond>" (Drive `read_file_content`) → JSON estruturado em `auditoria/folhas_portte/extracao/<mes>/<cond>.json` (por empregado+rubricas+totais+bases). Raw NÃO fica no contexto principal (escreve em disco). Subagente por mês se o acesso ao Drive propagar; senão sequencial.
2. **Reconciliar** — casar empregado por **CPF**→`employees`; condomínio por **CNPJ/nome**→`condominios/clients`. **Cross-check: Geral == soma dos serviços** (por rubrica e líquido). Correções: 2 versões do mesmo (competência,cond) → usar a de `modifiedTime` maior. Gera `reconciliacao/<mes>.md` com toda não-conformidade.
3. **Carregar** — `pg_dump` backup antes; upsert `hr_payslips` por (employee_id,condominio_id,ref_year,ref_month) marcado `source_system='portte'`+`import_batch_id`. 03/06 já existem → **comparar vs Portte, reportar diff, Portte vence** (com log do que mudou).
4. **Verificar (oráculo)** — nosso `hr_payslips` == PDF: líquido/proventos/descontos por empregado, totais por serviço e mês, Geral==soma. Só "ok" com prova (query vs valor do PDF).

## Descobertas da Fase 3 (carga) — 25/07
- **`hr_payslips` SEM trigger** → INSERT não auto-posta no razão; `ledger_auto` é passo SEPARADO e idempotente. Carga da folha é segura/isolada; postar no razão é decisão/etapa própria depois.
- **Paisagem existente (define ação por mês):** 06/2026 já `source='portte'` (56) → **verificar vs extração, não recriar**; 03/2026 `source='dominio_sistemas'` (51) → **reconciliar rumo à Portte**; **01,02,04,05 faltam** → importar.
- **Mapeamento rubrica→jsonb (confirmado num payslip real):** `earnings=[{code,value,reference,description}]`, `deductions=[{code,value,description}]`, `informative` idem. tipo P→earnings, D→deductions, informativa→informative. Extração `{codigo,nome,referencia,valor,tipo}` → code=codigo, value=Decimal(valor), reference=referencia, description=nome. Campos diretos: base_salary, total_earnings/deductions, net_salary, inss/irrf/fgts base+value, payslip_type='monthly', status (a definir: 'published' espelha o existente).
- **Atenção June:** payslip existente usa rubrica "DIAS NORMAIS"(8781); Janeiro-PDF usa "HORAS NORMAIS"(1) — pode ser formato de export diferente OU competência diferente. Comparar a extração de Jun vs o import existente antes de tocar.

## Não-conformidades (haverá muitas) — regra
Relatório por mês. Empregado Portte sem match (CPF) / condomínio não mapeado / rubrica desconhecida / Geral≠soma / diff vs dado existente. **Surfaço, nunca fabrico nem descarto.** Decisão de negócio (criar empregado inexistente, mapear condomínio novo) → **PARO e mostro ao Jordan**; resto sigo sozinho. [[feedback_jordan_fonte_da_verdade]]

## Segurança
Backup por mês antes da carga. Nada de dinheiro/pagamento (só registro de folha). Verificação antes de avançar. Idempotente por `import_batch_id`. Reversível (DELETE por batch).

## Ordem de execução
Mês a mês. Provável começar por um mês **novo e simples** (menos condomínios) p/ validar o pipeline ponta-a-ponta, depois escalar. Progresso medido por competências verificadas (0/6 → 6/6).

## Coordenação com T1 (sessão paralela — financeiro) — 25/07
- **Minha folha alimenta o razão do T1:** `hr_payslips` → `accounting_entries` via `ledger_auto`. Ao popular Jan–Jun, o Balanço/IRPJ-CSLL/DRE/Orçado×Realizado/Provisões do T1 refletem sozinhos. ⚠️ **Efeito contábil downstream** → na Fase 3 (carga): investigar se INSERT em `hr_payslips` auto-posta no razão (trigger vs processo) e garantir **idempotência** (import_batch_id) p/ re-runs NÃO duplicarem lançamentos. Verificar antes de carregar em massa.
- **T1 tem tela de Provisões que LÊ `hr_payslips`** (férias 1/9 + 13º 1/12), nunca escreve. Não colide.
- **Deploy acoplado (blue-green bakeia a árvore inteira):** commitar ANTES de deployar; `git add` só dos MEUS arquivos (DP/hr/people-management). **NÃO tocar** nos arquivos do T1: `redesign_builders/_fin_*.py`, `redesign_builders/financeiro.py`, `financial/services/{conciliacao_liquido,regua_cobranca,apuracao_lucro_real}_service.py`, `integrations/inter`, `integrations/banking`.
- Checar deploy rodando com bracket-trick: `ps -eo args | grep "[d]eploy_backend_bluegreen.sh"`.

## RESULTADO (25/07) — 5/6 espelhados+verificados; Março pendente decisão
Pipeline completo executado. Estado em `hr_payslips` (source='portte'), verificado banco==Portte Geral (nº folhas E líquido) por mês:
| Mês | Folhas | Líquido | Status |
|---|---|---|---|
| 01/2026 | 50 | R$ 68.594,81 | ✅ espelhado+verificado |
| 02/2026 | 53 | R$ 62.776,42 | ✅ (5 de Villa Passaros do Geral; EDWARD por nome) |
| 03/2026 | 51 (dominio) | R$ 66.677,59 | ⚠️ **PENDENTE JORDAN**: Portte=R$66.860,57 (dif R$182,98); o Domínio existente tem `payroll_payments` (pagamentos reais) vinculados → não sobrescrevi. Decisão: reconciliar pagamentos vs Portte. |
| 04/2026 | 52 | R$ 71.941,65 | ✅ (SILVANA criada, R$418,62) |
| 05/2026 | 52 | R$ 73.561,44 | ✅ |
| 06/2026 | 56 | R$ 73.075,36 | ✅ (já era portte, verificado) |
Total 5 meses portte: 263 folhas. **5 empregados criados** (dados Portte, status demitido, CNPJ1): SILVANA + 4 demitidos R$0 (regra Jordan "manter cadastro Portte"). **1 exceção documentada:** SADRAC (Jan, R$0, demitido) — posto sem PDF individual em NENHUM mês → sem condomínio mapeável → não carregado (R$0, total exato sem ele). Backups: `backups/postgresql/hr_payslips_PRE_portte_*.dump` + `employees_PRE_portte_*.dump`. Reversível por batch (source='portte'+competência) ou restore. `hr_payslips` alimenta razão do T1 (ledger_auto, passo separado — não postado ainda).

## Artefatos
`auditoria/folhas_portte/extracao/<mes>/*.json` · `reconciliacao/<mes>.md` · `INVENTARIO.json` (todos os arquivos Drive) · relatório final `RESULTADO.md`.
