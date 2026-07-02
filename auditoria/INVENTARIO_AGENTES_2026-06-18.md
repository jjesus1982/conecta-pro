# Inventário do sistema de agentes (`agents/modules/`) — Conecta PRO

**Data:** 2026-06-18 · **Tipo:** READ-ONLY. **Objetivo:** mapear os orquestradores e agentes (a estrutura "80 agentes / 13 orquestradores" do CLAUDE.md é real?).

---

## RESPOSTA DIRETA
**Sim — a estrutura é exatamente "80 agentes em 13 orquestradores".** O CLAUDE.md está **estruturalmente correto** nesse número (o que diverge é a *execução* via cron — ver nota final).

- `agents/modules/` = **17 arquivos .py**: **13 orquestradores** (`orch_*.py`, pequenos) + **4 arquivos de definição de agentes** (`*_agentes.py`, grandes) + `__pycache__`.
- **80 classes `AgenteXxx(BaseAgent)`** + **13 classes `OrchestratorClass(BaseOrchestrator)`**.

> ⚠️ **Nota sobre o comando original:** `grep "class.*Agent" | grep -v "BaseAgent"` retornou **vazio** porque toda classe é `class AgenteX(BaseAgent):` — o `-v BaseAgent` removeu as 80 (BaseAgent está nos parênteses de herança). O grep correto é `^class Agente`.

---

## O QUE É CADA AGENTE (padrão real)
Não há docstring. Cada agente é um **agente de monitoria/auditoria** de um submódulo, com atributos estruturados:
```python
class AgenteColaboradores(BaseAgent):
    MODULO = "departamento_pessoal"
    SUBMODULO = "colaboradores"
    ENDPOINTS = ['/api/v1/people-management/hr/employees', ...]
    CONHECE_BUGS = [{'descricao': '...', 'corrigido': True, 'auto_corrigivel': False}, ...]
```
→ Cada agente conhece **os endpoints do seu submódulo** e **os bugs conhecidos** dele. É um framework de **vigilância por submódulo**, não agentes de IA generativa.

---

## OS 13 ORQUESTRADORES (1 por módulo)
| Arquivo | Módulo |
|---|---|
| `orch_dp.py` | departamento_pessoal |
| `orch_rh.py` | recursos_humanos |
| `orch_ponto.py` | ponto_eletronico |
| `orch_financeiro.py` | financeiro |
| `orch_fiscal.py` | fiscal_contabil |
| `orch_operacional.py` | operacional |
| `orch_ged.py` | ged |
| `orch_inteligencia.py` | inteligencia |
| `orch_negocios.py` | negocios |
| `orch_saude_ocupacional.py` | saude_ocupacional |
| `orch_portais.py` | portais |
| `orch_equipamentos.py` | equipamentos |
| `orch_administrativo.py` | administrativo |

## OS 80 AGENTES (nome = função) por arquivo de definição

### `dp_agentes.py` — 25 agentes (DP + Ponto + RH)
AgenteColaboradores · AgenteAdmissao · AgenteRescisao · AgenteContratos · AgenteFolhaSalarial · AgentePontoEletronico · AgenteBancoHoras · AgenteFeriasDP · AgenteBeneficios · AgenteLicencas · AgenteReembolsos · AgenteESocialDP · AgenteDocumentosDP · AgenteDisciplina · AgenteCCT · AgenteCarreira · AgenteClima · AgenteTurnover · AgenteTimeTracking · AgentePayroll · AgenteDashboardPonto · AgenteJustificativas · AgenteFechamentoMensal · AgenteSST · AgenteCommandCenter

### `op_ged_agentes.py` — 20 agentes (Operacional + GED)
AgentePostos · AgenteEscalas · AgenteAlocacoes · AgenteSubstituicoes · AgenteOcorrencias · AgenteProcessosDisciplinares · AgenteRondas · AgenteDiaristas · AgenteComunicados · AgenteCheckInOut · AgenteMonitoramentoCampo · AgenteKPITendencias · AgenteAICommandCenter · AgenteDashboardGED · AgenteClientesCondominios · AgenteKitsDocumentais · AgenteDocumentosGED · AgenteCertidoesEmpresa · AgenteEnviosGED · AgenteAssinaturasGED

### `fin_fiscal_agentes.py` — 19 agentes (Financeiro + Fiscal)
AgenteDashboardFinanceiro · AgenteContratos · AgenteContasPagar · AgenteContasReceber · AgenteFluxoCaixa · AgenteConciliacaoBancaria · AgenteBoletos · AgenteFornecedores · AgenteContabilidade · AgenteFaturamento · AgentePrecificacao · AgenteRelatoriosFinanceiros · AgenteNFe · AgenteNFSe · AgenteCertidoes · AgenteESocialFiscal · AgenteSPED · AgenteDCTFWeb · AgenteEFDReinf

### `extra_agentes.py` — 16 agentes (IA + CRM + Saúde + Portais + Equip. + Admin)
AgenteAIBartolo · AgenteAIModulos · AgenteAIAprendizado · AgenteCRMLeads · AgenteCRMOportunidades · AgenteCRMContratos · AgenteSaudeOcupacional · AgentePCMSO · AgentePortalClientes · AgenteGovESocial · AgenteCCTPortal · AgenteEquipamentos · AgenteEquipamentosManutencao · AgenteReembolsos · AgenteNotificacoesAdmin · AgenteCCTAdmin

**Total: 25 + 20 + 19 + 16 = 80 agentes.**

---

## CRUZAMENTO COM O RECON (estrutura × execução)
- **Estrutura (código): real e intacta** — 80 agentes / 13 orquestradores, definidos em `agents/modules/` (datados 2026-04-06).
- **Execução (cron): parcial** — conforme `RECON_CLAUDEMD_V2_2026-06-18.md`: o `orchestrator_unificado.py rapido` (*/5) + `dashboard`/`context_builder`/`heartbeat`/`predicao` rodam e produzem `reports/monitor` hoje; mas o **ciclo `completo` */30 está quarentenado** (`# [LIMPEZA 20260531]`), junto com proatividade/auto_evolucao/semanal/turno.
- **Conclusão para o v2:** manter "80 agentes / 13 orquestradores" como **arquitetura existente**, mas corrigir a narrativa de execução — **não** é "ciclo 30min ativo, score 10/10"; é **monitor leve ativo + ciclo pesado quarentenado**. Cada agente é vigia de submódulo (endpoints + bugs conhecidos), não IA generativa (essa é a frente separada do agente WhatsApp "José Luís", no `git log`).

---

## NÚMEROS (para o v2)
| Item | Valor |
|---|---|
| Arquivos em `agents/modules/` | 17 (13 orch + 4 def + cache) |
| Orquestradores | **13** (1 por módulo) |
| Agentes (`class Agente*`) | **80** |
| Distribuição | dp 25 · op_ged 20 · fin_fiscal 19 · extra 16 |
| Padrão do agente | MODULO + SUBMODULO + ENDPOINTS + CONHECE_BUGS (vigia, não generativo) |
| Execução real | monitor leve ativo · ciclo pesado quarentenado |
