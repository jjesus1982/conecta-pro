# QA E2E FINAL — CIC — MÓDULO FINANCEIRO · Decisão de PRODUÇÃO

> Cole no CIC. Esta é a rodada de APROVAÇÃO: QA E2E completo do módulo Financeiro,
> click-level, com veredito final de produção. Todos os itens das rodadas anteriores
> (FIN-01..FIN-10 + REG-01) foram fechados, deployados duráveis e pré-validados pelo
> dev em browser real (11/11). Sua função agora é o carimbo independente.

## CONTEXTO
- URL: https://erp.conectamais.pro → perfil Jordan/Pyetra.
- **Hard refresh (Ctrl+Shift+R) em cada tela** — houve deploys novos (backend blue/green
  + imagem frontend rebuildada). Commits desta série: `62707aaa` → `8582df07` → `aeaa9473`.
- Escopo: módulo Financeiro completo (todas as telas do menu Financeiro).

## 🚨 SEGURANÇA (produção, dinheiro real — inegociável)
- **NUNCA** conclua pagamento, PIX, boleto, transferência, OTP ou emissão fiscal.
  Preparar/pré-visualizar sim; no gate final, PARE e reporte "cheguei no gate".
- Registros de teste: máximo 2, prefixo "TESTE QA", valor R$ 1,00. Como você não
  executa deleção, **sinalize-os no relatório** para o dev remover (não contam como
  falha de dados).

## PARTE A — Confirmação dos itens fechados (uma linha PASS/FAIL cada)

### A1. Fluxo de Caixa (/fluxo-caixa)
- [ ] Lista populada (extrato Inter real) com header de contagem coerente.
- [ ] **Entradas** (ex.: PIX RECEBIDO): valor **positivo/verde** com "+". Saídas: negativo/vermelho.
- [ ] Botões **Todos / Entradas / Saídas** filtram a lista de verdade.
- [ ] Gráfico "Receitas vs Despesas (6 meses)": barras de **Receitas não nulas** nos meses
      com crédito (referência: jan/fev/mar/abr/jul têm; **junho não teve crédito no extrato —
      barra zero em junho é dado real, não bug**).
- [ ] Cards: Entradas ~R$ 190 mil · Saídas ~R$ 267 mil (janela 30d) · Saldo Atual = saldo Inter.
- [ ] Card **"Projeção 30d" == último ponto do gráfico "Projeção de Saldo"** (~R$ 66 mil na
      data desta escrita; o critério é card==gráfico e ordem de grandeza — nunca ±R$ 65/66).

### A2. Relatórios (/relatorios)
- [ ] DRE: Receita ~R$ 1,54M, Lucro ~R$ 480 mil (não zerado).
- [ ] Cards rodapé: **A Receber ~R$ 529 mil** · **A Pagar ~R$ 208,6 mil** — batendo com as
      telas de contas.
- [ ] Console SEM erro 422 (havia um em toda carga desta tela; foi corrigido).

### A3. Contas a Pagar / Contas a Receber
- [ ] Totais somados em R$ (nunca string concatenada), KPIs e filtros de status coerentes
      (filtro "Paga" em Receber = ~13).
- [ ] Coluna **Fornecedor/Cliente preenchida** nas contas existentes.
- [ ] Criar 1 "TESTE QA" em cada (R$ 1,00, com fornecedor/cliente digitado) → após F5, o
      registro persiste COM o nome na coluna.
- [ ] Valor 0 e negativo → erro amigável, NÃO cria.
- [ ] Busca "TESTE QA" antes de criar os seus → zero resíduos de rodadas anteriores.

### A4. Faturamento (/faturamento → aba Histórico)
- [ ] KPI **"Valor Fixo Total" ≈ R$ 270,6 mil** (= soma visível dos base_value das ativas).
- [ ] Contadores: Total Regras 10 / Ativas 10 / Inativas 0. Linhas com valores em R$.

### A5. Consistência de saldo (por TOLERÂNCIA — Inter é live)
- [ ] Banco Inter, Dashboard, Pagamentos, Fluxo de Caixa, Conciliação, Raio-X, Agentes →
      mesmo valor aproximado no mesmo instante (~R$ 67–74 mil conforme o momento).
      Reprovar apenas divergência ESTRUTURAL (ex.: o antigo R$ 54.690 fixo).

## PARTE B — Sweep E2E do módulo (o carimbo)
Percorra TODAS as telas do menu Financeiro (Dashboard, CFO IA, Contratos, Contas a Pagar,
Contas a Receber, Fluxo de Caixa, Conciliação, Boletos, Cobranças, Banco Inter, Pagamentos &
Transferências, Faturamento, Relatórios, Contabilidade, Orçamentos, Raio-X, Agentes, e o que
mais houver no menu). Em cada uma:
- [ ] Carrega sem "Algo deu errado", sem chunk error, sem tela branca.
- [ ] Dados exibidos são plausíveis e consistentes entre telas (nada de R$ 0,00 onde há dado,
      nada de "Invalid Date", nada de soma-string).
- [ ] Console: anote qualquer erro. Referência: na pré-validação do dev o console ficou
      **100% limpo** (nem o React #418 apareceu) — se aparecer algo, é digno de nota.
- [ ] Botões primários respondem (abrir modal, filtrar, buscar) — sem botão morto.

## PARTE C — Fluxos críticos até o gate (NÃO concluir)
- [ ] Pagamentos & Transferências: beneficiário "Saúde Manaus" → autofill → preparar PIX
      R$ 0,01 → **PARAR no OTP** e reportar que o gate apareceu corretamente.
- [ ] Boleto: escanear/colar linha digitável → pré-visualização ok → parar antes de pagar.
- [ ] Lote diaristas junho: soma R$ 12.420,00 → parar no gate.
- [ ] Folha junho: lista ~50+ funcionários com líquidos → não executar pagamento.
- [ ] Comprovante de pagamento já concluído: gera PDF legível.

## ITENS CONHECIDOS (não contam como falha nova)
- Orçamentos "Realizado" vazio · balancete de lançamentos não-postados · contadores
  menores já registrados (Fiscal total×autorizadas, MRR por janela) · React #418 se
  aparecer (P2 aceito; não apareceu na pré-validação).
- Total de Contas a Pagar **cresce diariamente** (o robô fiscal importa NF-e reais) —
  número maior que 70 NÃO é regressão.
- 1 recebível `ZZE2E_ContaReceber_EDIT` **cancelado** (artefato antigo, invisível nas
  telas que filtram canceladas) — já sinalizado, não conta.

## RELATÓRIO FINAL
1. PARTE A: PASS/FAIL por item (A1..A5).
2. PARTE B: lista de telas percorridas com OK/observação; qualquer console error com print.
3. PARTE C: cada fluxo com "cheguei no gate — não executei" ou o problema encontrado.
4. Registros de teste que você criou (para o dev limpar).
5. **VEREDITO DE PRODUÇÃO: APROVADO / APROVADO COM RESSALVA / REPROVADO** — considerando
   que a única etapa restante do plano acordado é a **Fase 4 humana** (1 PIX real R$ 0,01 +
   1 emissão fiscal de homologação, com OTP do Jordan), que ocorre APÓS o seu carimbo e
   não é sua atribuição.
