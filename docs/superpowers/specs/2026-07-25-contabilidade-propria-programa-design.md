# Programa "Contabilidade Própria Conecta PRO" — Master Spec

**Data:** 2026-07-25 · **Autor:** T1 · **Aprovado por:** Jordan (magnitude + ordem livre)

## Objetivo estratégico
O Conecta PRO passa a **gerar tudo nativo** (folha, eSocial, guias, contabilidade, SPED) para
os 2 CNPJs, eliminando a dependência do escritório Portte e do portal Onvio. "Tudo no sistema,
sem precisar de ninguém." Corte só após rodar em **paralelo** e bater centavo-a-centavo.

## Caveats travados (não são software — Jordan ciente e de acordo)
1. **Contador com CRC** continua necessário como responsável técnico (assina ECD/ECF) — pode ser
   funcionário ou contrato de revisão/assinatura, não o serviço completo da Portte.
2. **Rodar em paralelo** com a Portte por N meses; corte só com reconciliação centavo-a-centavo.
   Nunca cortar às cegas (erro fiscal = multa).
3. **Manutenção contínua** das tabelas legais (IRRF/INSS/anexos Simples) conforme muda a lei.

## Linha de base VERIFICADA (o que já é real — evidência dos 3 laudos 2026-07-25)
- **Folha (cálculo):** motor nativo forte (INSS certificado, IRRF codado, adicionais, HE, DSR,
  rescisão/TRCT, férias, 13º). Em **fallback** (não persiste; Portte é a verdade).
- **eSocial (motor):** transmissão REAL (SOAP+mTLS+cert A1), multi-CNPJ, espelho de conferência.
  S-1000/SST reais; S-2200/2299 prontos mas não-acionados. **S-1200/1210/1299 = casca.**
- **Guias:** DAS/FGTS/DARF **calculam** da folha real; **código de barras/PIX simulados ou None**.
- **Fiscal:** ECD gera Bloco I do razão; EFD-Reinf real; apuração IRPJ/CSLL calculada.
- **Contabilidade:** razão honesto no que registra, mas **duas contabilidades desconectadas** e
  longe de certificável (sem plano referencial, saldos de abertura, blocos J, encerramento).

## Insight de sequência (caminho crítico)
A **DCTFWeb é montada pela Receita a partir do S-1200 + EFD-Reinf que NÓS transmitirmos.**
Logo o pino-mestre é a folha autoritativa → S-1200 nativo. Ordem: **folha real → eSocial folha
→ guias/DCTFWeb → fiscal**. A contabilidade certificável (D) é trilha pesada paralela.

## Decomposição em 6 sub-projetos (cada um: spec própria → plano → executa → concilia)
| # | Sub-projeto | Tamanho | Depende | Entregável |
|---|---|---|---|---|
| **A** | **Folha autoritativa** | 🟡 Médio | — | folha nativa persiste, certificada, concilia com Portte |
| **B** | **eSocial folha nativo** | 🔴 Grande | A | S-1200/1210/1299 fiéis + wire S-2200/2299/2206 + cert Patrimonial, transmitindo |
| **C** | **Guias reais** | 🔴 Grande | A, B | DAS (PGDAS-D), FGTS Digital (Caixa), DARF (barcode SERPRO/Sicalc), GPS/ISSQN |
| **D** | **Contabilidade certificável** | 🔴🔴 Máx | — (paralela) | unifica os 2 mundos, plano referencial, saldos abertura, blocos J, encerramento, fatos ausentes |
| **E** | **Geradores fiscais** | 🔴 Grande | D | ECD completa, ECF (novo), EFD-Contribuições (novo), DEFIS, PGDAS-D declaração |
| **F** | **Corte** | 🟡 Processo | A–E | paralelo→reconcilia→CRC assina→demite Portte |

**Ordem de execução:** A → B → C (trilha folha/gov) · D em paralelo → E (trilha contábil/fiscal) → F.

---

## Sub-projeto A — Folha autoritativa (primeiro; detalhado)

### Propósito
Inverter a folha nativa de fallback para **fonte primária confiável**: certificar as tabelas,
persistir os holerites calculados, unificar os dois motores, e provar por conciliação cega
centavo-a-centavo contra a Portte antes de qualquer uso legal.

### Componentes (evidência do laudo folha)
1. **Certificar IRRF 2026** — o redutor da reforma (Lei 15.270) está codado em
   `clt_calculator.py:97-142` mas `IRRF_CERTIFICADA_2026=False`. Validar com casos-teste reais
   vs Portte; virar a flag só quando bater. (INSS já é `INSS_CERTIFICADA_2026=True`.)
2. **Persistir a folha nativa** — hoje `calcular_folha_colaborador` só retorna dict; `fechar_folha`
   não grava. Gravar em `hr_payslips` com `source_system='conecta'` (isolado do `'portte'`, sem
   sobrescrever o espelho). Idempotente por (employee_id, competência, source).
3. **Unificar os 2 motores** — `calculo_service.py` (CCT, plugado) NÃO desconta faltas nem lê
   `EmployeeBenefit` real (usa odonto/taxa hardcoded); `payroll_service.py` (CLT) sim. Convergir
   num motor único que aplique faltas + benefícios reais.
4. **Conciliação cega nativo × Portte** — endpoint `/conferencia` já existe; rodar nos ~56 CLT ×
   2 CNPJs por várias competências; relatório de divergência por rubrica; meta = 0 divergência.
5. **Recibos faltantes** — gerar PDF de recibo de **férias** e de **13º** (hoje só TRCT/holerite/VT-VR).
6. **Saldo FGTS real** — `calcular_rescisao` recebe `saldo_fgts` externo (default 0); alimentar do
   acumulado real (FGTS Digital / extrato) pra a multa 40% sair correta.

### Isolamento e segurança
- Nativo grava `source_system='conecta'`; NÃO toca as linhas `'portte'`. O guard atual
  (`calcular_folha_batch_com_guard`) continua priorizando Portte até a conciliação provar o nativo.
- Nada legal com selo de estimativa vai pra frente: o holerite nativo mantém
  `certificacao_tabela_legal` honesto até certificar.
- Multi-CNPJ escopado por `empresa_id` (Eletrônica/Patrimonial).

### Critério de sucesso (A)
- Folha nativa persistida e recuperável por competência/CNPJ (`source='conecta'`).
- IRRF certificado (flag true) com casos-teste documentados.
- Conciliação cega: 0 divergência de líquido e rubricas vs Portte em ≥3 competências.
- Recibos de férias e 13º gerando PDF.
- Zero mistura com o espelho Portte; guard só inverte quando a conciliação passa.

### Fora de escopo (A)
- Transmitir eSocial (é B). Gerar guias (é C). Contabilizar a folha no razão certificável (é D).
  A só torna a folha **autoritativa e persistida** — a matéria-prima de todo o resto.
