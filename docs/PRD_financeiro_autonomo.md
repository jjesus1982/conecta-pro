# PRD — Financeiro Autônomo Conecta PRO ("CFO digital + banco + contabilidade + fisco nativos")

**Autor:** T1 (financeiro) · **Data:** 2026-07-26 · **Para alinhamento com:** T2 (DP/folha), T3 (agentes)
**Status:** proposta para coordenação (dividir território ANTES de construir)

## 1. Visão
Transformar o módulo Financeiro num sistema autônomo e nativo que substitui 4-5 fornecedores externos
(escritório contábil Portte, Power BI, tesouraria/pagamento, analista financeiro): um **cockpit que se
dirige sozinho** + um **CFO de IA proativo** + um **banco dentro do ERP** + **contabilidade e fisco
próprios** — para os 2 CNPJs (Eletrônica/Lucro Real + Patrimonial/Simples), cada um no seu regime.

## 2. Princípio-chave (evita "dois sistemas num só")
UM dado, UMA fonte, UMA interface entre módulos. A **folha** (motor de cálculo) é do **DP (T2)**; o
**razão e o fisco** (posting, SPED, guias, apuração) são do **Financeiro (T1)**. A ponte entre os dois é
UMA tabela/interface bem definida (`hr_payslips` → `accounting_entries` via `ledger_auto`). Nenhum módulo
reimplementa o do outro.

## 3. O que JÁ EXISTE (investigado 2026-07-26 — não reconstruir)
- **UI:** export universal ✅; drill-down, tendências (RdChart line/area) e filtros (`filterCol`) têm
  INFRA pronta — só falta emitir o campo nos builders. Gráficos (7 telas) já no ar.
- **Agentes:** CFO com LLM real (`cfo_service.py`) VIVO, no Hermes, no chat de consultores, lê dado real.
  Proativo 5.3 LIVE (2 regras financeiras no sino: caixa baixo/CNPJ, aging). Propor→aprovar 5.4 LIVE
  (cobrar 🟡, pagar-lote 🔴 execução humana). 16 skills cirúrgicas no disco + `skill_loader` funcional.
- **Banco:** Cora+Inter, todos os pagamentos gated OTP (folha CLT/PJ, diaristas, boleto/PIX/TED/DARF/GPS),
  saldo consolidado, arsenal de captura, conciliação por líquido.
- **Contábil/fisco:** razão `accounting_entries` populado+reconciliado (folha jan-jun); Balanço, DRE
  (competência/caixa/AV), Liquidez, Apuração IRPJ/CSLL, DAS 2 CNPJ, provisões (gated), tributos mensais.
  Geradores ECD e EFD-ICMS/IPI existem; EFD-Reinf R-1000 real; eSocial SST real; NFS-e nacional real.
- **Motor de folha nativo** (DP): calcula bruto→líquido de ponto/CCT (INSS certificado, adicionais,
  rescisão/TRCT, férias/13º). Hoje em FALLBACK (Portte é a verdade). Proporcionalização de mês parcial
  já iniciada (proventos/descontos = mapa de completude feito).

## 4. Os gaps reais (ligar, não construir)
### Frente A — UI topo de linha (T1, financeiro redesign)
- A1 **Drill-down**: emitir `to` nos KPIs → renderer já navega.
- A2 **Tendências**: alimentar `charts:[{type:'line'}]` das queries mensais que já rodam (orçado×real 12m,
  conciliação por mês, faturamento por mês).
- A3 **Filtros globais**: ligar `filterCol` (período) no financeiro + seletor CNPJ + estado compartilhado.
- A4 **Cockpit executivo**: consolidar as abas do `g-visao` numa landing única (KPI+gráfico+alerta+CFO).
- A5 **Export de gráfico** (só tabela hoje).

### Frente B — CFO agente proativo + skills (T1 financeiro + T3 agentes)
- B1 **Skills→cérebro** 🎯: `cfo_service.consultar` fazer `SkillLoader.load_multiple()` por lente → cola o
  `.md` cirúrgico no prompt que já vai pro Hermes. (Hoje: agentes que injetam skills não chamam LLM; o CFO
  que chama LLM não injeta skills.) Maior alavanca.
- B2 **CFO proativo**: regra 5.3 que, num achado financeiro, pede ao CFO um mini-diagnóstico (não só template).
- B3 **Mais regras no sino**: vencimento por cliente, margem/DRE fora de meta, tributo a vencer, concentração
  de pagáveis.
- B4 **Mais ações 5.4**: propor_provisionar, propor_baixa/quitação, propor_acordo de inadimplência (gated).
- B5 **Consolidar 2 gerações** de agentes (gedeon novo vs orchestrator legado).

### Frente C — Contabilidade + fisco próprios (DEMITIR PORTTE) — **ZONA COMPARTILHADA T1×T2**
- C1 **Folha autoritativa** [**T2**]: certificar IRRF, persistir nativa (`source='conecta'`), unificar
  motores, completude (mês parcial/descontos), conciliar centavo-a-centavo vs Portte, recibos férias/13º.
- C2 **eSocial folha** [**T2**]: S-1200/1210/1299 fiéis + wire S-2200/2299 (o motor de transmissão é real).
- C3 **Postar folha→razão** [**T1**]: `ledger_auto` consome a folha autoritativa do T2 (interface hr_payslips).
- C4 **Guias reais** [**T1**]: DAS/DARF/GPS/FGTS com código de barras/PIX válido (hoje simulado).
- C5 **Geradores SPED** [**T1**]: ECF (novo), EFD-Contribuições (novo), DEFIS, PGDAS-D; ECD completa
  (plano referencial I051, saldos de abertura, blocos J, encerramento). Fonte = Domínio/Onvio ou razão próprio.
- C6 **Multi-CNPJ**: cada regime no seu; consolidado com eliminação intercompany.

## 5. Divisão de território (o coração deste PRD — evita conflito e retrabalho)
| Domínio | Dono | Arquivos-chave |
|---|---|---|
| Motor de folha (cálculo bruto→líquido, rescisão, férias/13º) | **T2** | `people_management/folha/services/calculo_service.py`, `hr/services/payroll_service.py`, `common/utils/clt_calculator.py` |
| eSocial (todos os eventos, transmissão) | **T2** | `government_integrations/**esocial**`, `people_management/hr/**esocial**` |
| DP redesign / CRUD / fluxo/aprovação (não-money-out) | **T2** | `redesign_builders/departamento_pessoal.py` |
| Razão / posting / ledger_auto | **T1** | `financial/services/ledger_auto_service.py`, `accounting_entries` |
| SPED (ECD/ECF/EFD/Reinf), guias, DAS/apuração/tributos | **T1** | `government_integrations/**sped**/**dctfweb**/**reinf**`, `financial/agents/tax_calculator.py` |
| Banco / money-out (pagar tudo, gated OTP) | **T1** | `redesign_builders/financeiro.py`, `integrations/banking`, `integrations/inter` |
| Financeiro redesign / cockpit / gráficos / CFO agente | **T1** | `redesign_builders/_fin_*.py`, `RdChart.tsx`, `financial/cfo_service.py`, `financial/agents/**` |
| Agentes / Hermes / propor→aprovar / proativo / skills | **T3+T1** | `ai/**`, `notifications/proativo`, `skills/financeiro` |

**Interface única folha↔razão:** T2 entrega a folha autoritativa em `hr_payslips` (`source='conecta'`); T1
posta no razão via `ledger_auto` e gera o SPED. **Ninguém cruza a fronteira sem combinar.**

**RESOLVIDO (2026-07-26, T2 confirmou a Seção 5):** `calculo_service.py`/`clt_calculator.py`/
`payroll_service.py` = **T2** (C1). T2 aceita, mas AINDA NÃO começou C1/C2 (sessão atual dele = 100% DP
redesign CRUD). **T1 PARA de mexer no motor de folha.** Minha proporcionalização de mês parcial já commitada
= **ref `8eeec51c`** — entregue ao T2 pra ele incorporar/revisar quando entrar na C1 (Fase 4). Até lá, o
motor fica como está.

## 6. Guardrails inegociáveis
- **Oráculo**: todo número exibido == banco; nunca fabricar; vazio-real = "aguardando dado".
- **Money-out**: SEMPRE gate OTP humano, FORA dos agentes. Nunca testar caminho feliz.
- **Agentes**: veem e sugerem; humano decide+OTP. Propor→aprovar (5.4), propositor≠aprovador.
- **Legal/fiscal**: não se inventa; contador CRC = responsável técnico (pessoa, não software).
- **Corte da Portte**: só após rodar em paralelo e bater centavo a centavo. Nunca às cegas.
- **Deploy**: blue-green backend; frontend via `docker-compose.yml` (NÃO prod.yml); árvore compartilhada.

## 7. Fases sugeridas (superpowers: spec→plano→build→verifica por fase)
1. **Quick wins UI** (A1 drill-down + A2 tendências) — barato, alta visibilidade, reusa gráficos.
2. **B1 skills→cérebro** — acende as 16 skills no CFO. Maior alavanca de IA.
3. **A3/A4 filtros + cockpit** + B2/B3 (CFO proativo + regras no sino).
4. **C1/C2 folha+eSocial autoritativos** [T2] ∥ **C3 posting** [T1] — trilha demitir-Portte, coordenada.
5. **C4/C5 guias + SPED (ECF/EFD-Contrib/DEFIS)** [T1] + B4 ações gated.
6. **Corte Portte** (paralelo→reconcilia→CRC assina) + B5 consolidação.

## 8. Sucesso
- Toda capacidade do backend financeiro tem superfície funcional no redesign (0 órfão acionável).
- CFO agente avisa+propõe sozinho no sino, com skills, gated.
- Os 2 CNPJs geram suas obrigações no ERP, prontas pro PVA/portal (assinadas), sem depender do software da Portte.
- Nenhuma duplicação T1×T2: uma folha (T2), um razão (T1), uma interface entre eles.
