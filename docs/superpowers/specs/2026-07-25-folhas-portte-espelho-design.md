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

## Não-conformidades (haverá muitas) — regra
Relatório por mês. Empregado Portte sem match (CPF) / condomínio não mapeado / rubrica desconhecida / Geral≠soma / diff vs dado existente. **Surfaço, nunca fabrico nem descarto.** Decisão de negócio (criar empregado inexistente, mapear condomínio novo) → **PARO e mostro ao Jordan**; resto sigo sozinho. [[feedback_jordan_fonte_da_verdade]]

## Segurança
Backup por mês antes da carga. Nada de dinheiro/pagamento (só registro de folha). Verificação antes de avançar. Idempotente por `import_batch_id`. Reversível (DELETE por batch).

## Ordem de execução
Mês a mês. Provável começar por um mês **novo e simples** (menos condomínios) p/ validar o pipeline ponta-a-ponta, depois escalar. Progresso medido por competências verificadas (0/6 → 6/6).

## Artefatos
`auditoria/folhas_portte/extracao/<mes>/*.json` · `reconciliacao/<mes>.md` · `INVENTARIO.json` (todos os arquivos Drive) · relatório final `RESULTADO.md`.
