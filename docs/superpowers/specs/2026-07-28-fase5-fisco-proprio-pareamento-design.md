# Fase 5 — Fisco Próprio + Pareamento Portte (design)

**Data:** 2026-07-28 · **Autor:** T1 · **Aprovado por:** Jordan (arranca a Fase 5)

## Reframe estratégico (decisão do Jordan)
A Portte NÃO é demitida agora — só em **~6 meses**. Até lá, o ERP roda **em paralelo** e o Jordan
faz o **pareamento mês a mês** (nosso × Portte) até ter confiança de que temos maturidade para andar
com as próprias pernas. Logo:

- **A peça CENTRAL da Fase 5 é o PAREAMENTO** (nosso × Portte por competência), não os geradores.
  O pareamento é o "medidor de maturidade": quando bater centavo a centavo por N meses, corta-se a Portte.
- Os geradores (guias, SPED) **alimentam** o pareamento — mas o valor imediato é a COMPARAÇÃO.
- Nada de dizer "transmitido/pago" sem transmissão real (oráculo). Guias/arquivos ficam prontos +
  validados; a entrega real segue humana (PVA/portal) até o corte.

## Objetivo
Construir a capacidade fiscal própria (guias reais + SPED) E o pareamento contínuo nosso×Portte,
para os 2 CNPJs (Eletrônica Lucro Real + Patrimonial Simples), de forma que ao fim de ~6 meses de
paralelo o Jordan possa cortar a Portte com segurança.

## O que JÁ existe (não reconstruir)
- **Cálculo:** `tax_calculator` (DAS Simples, Lucro Real), apuração IRPJ/CSLL, DAS Patrimonial/tributos
  Eletrônica já expostos. Razão `accounting_entries` populado+reconciliado.
- **Guias (cálculo):** DAS, FGTS, DARF/DCTFWeb calculam — mas barcode/PIX/linha digitável SIMULADOS.
- **SPED:** ECD gera Bloco I; EFD-ICMS/IPI gera; EFD-Reinf R-1000 real. ECF ausente, EFD-Contrib stub.
- **Padrão de pareamento:** a conciliação de folha (nativo×Portte, `auditoria/conciliacao_folha_*`) já
  provou o padrão — reusar para guias/tributos.
- **Fonte Portte:** Onvio (login + pull de docs funcionam) tem as guias/comprovantes PDF; hr_payslips
  tem a folha Portte. É a "verdade Portte" para comparar.

## Sub-projetos (ordem: pareamento primeiro, geradores alimentam)
### C-PAR — Pareamento mensal nosso × Portte (PRIMEIRO — a espinha)
- Serviço `pareamento_fiscal_service.comparar(competencia)`: para cada competência, monta lado a lado
  NOSSO (tax_calculator/razão/folha nativa) × PORTTE (hr_payslips, guias Onvio, DAS pago) por rubrica:
  DAS, tributos federais, ISS, INSS/FGTS, folha líquida. Retorna divergências por linha + % batido.
- Tela redesign "Pareamento Portte" (g-fiscal): semáforo por competência (verde=bate, amarelo=diverge),
  drill nas divergências. O "medidor de maturidade" (quantos meses seguidos bateram).
- Oráculo: cada valor NOSSO e PORTTE vem de query real; divergência = diferença real, nunca fabricada.

### C4 — Guias reais (documento pagável)
- DAS (PGDAS-D), DARF (barcode SERPRO/Sicalc), GPS, FGTS Digital — gerar código de barras/linha
  digitável/PIX VÁLIDOS (checksum). Cada guia: gera doc + valida. Entrega real fica humana até o corte.
- Alimenta o pareamento (nosso valor de guia × guia Portte).

### C5 — Geradores SPED (arquivo oficial)
- ECD completa (plano referencial I051, saldos abertura, blocos J, encerramento).
- ECF (novo), EFD-Contribuições (novo), DEFIS, PGDAS-D declaração.
- Validam (0 erros PVA). Entrega offline (PVA) humana até o corte.

### C3 — Postar folha→razão (quando T2 entregar a folha autoritativa)
- `ledger_auto` posta a folha `source='conecta'` com encargos completos. Coordenado com T2.

## Guardrails
- Oráculo (nunca fabricar; divergência real). Legal/fiscal não se inventa.
- Nada "transmitido/pago" sem transmissão real → status honesto até o corte.
- Contador CRC = responsável técnico até (e depois) o corte.
- Paralelo antes do corte: o pareamento tem que bater N meses seguidos.
- Coordenação: folha/eSocial = T2; razão/SPED/guias = T1.

## Sucesso
- Pareamento mensal nosso×Portte no ar, com semáforo e medidor de maturidade.
- Guias com barcode/PIX válidos; SPED validando no PVA.
- Ao fim de ~6 meses de paralelo batendo, o corte da Portte é uma decisão informada, não um salto.
