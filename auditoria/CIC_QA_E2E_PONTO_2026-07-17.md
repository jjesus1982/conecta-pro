# QA E2E — CIC — MÓDULO PONTO · Validação pós-lapidação

> Cole no CIC. O módulo passou por lapidação focada na missão de 01/08 (todos batendo
> ponto pelo Conecta PRO, tempo real). Correção-raiz: convenção única de fuso na coluna
> de batidas (era o que deslocava o espelho em +4h e zerava presença à noite).
> Pré-validado pelo dev: 13/13 browser + 4/4 pytest. Sua função: carimbo independente.

## CONTEXTO
- URL: https://erp.conectamais.pro/modulos/gestao-pessoas/ponto → perfil Jordan/Pyetra.
- **Hard refresh (Ctrl+Shift+R)** em cada tela — houve deploy novo.
- Fonte atual das batidas: sync do Tangerino/Sólides, que só expõe a APURAÇÃO (D-1).
  Por isso "Presentes hoje: 0" durante o dia é status HONESTO até 01/08 — não é bug.

## 🚨 SEGURANÇA (produção)
- NÃO conclua "Fechamento Mensal" (fechar mês é ação real de DP). Pode navegar e
  conferir status.
- Pode REGISTRAR 1 batida de teste na tela Bater Ponto (o dev remove depois — sinalize
  o horário). NÃO aprove/rejeite justificativas reais.

## PARTE A — Itens corrigidos

### A1. Espelho de Ponto — ERA: horários deslocados +4h (07:00 aparecia 11:00)
- [ ] Abra o espelho de um colaborador 44h (ex.: administrativo) em JULHO: as entradas
      devem ser de MANHÃ (06:00–08:00) e o padrão do dia ~07:00→16:00 com almoço —
      NUNCA blocos 11:00→20:00.
- [ ] Um colaborador 12x36 (portaria): entradas ~07:00 ou ~19:00 (troca de turno real).

### A2. Atrasos e Faltas — ERA: coluna Colaborador toda "--"
- [ ] A tabela mostra o NOME do colaborador em cada linha (ex.: MAIARA MUNIZ...).
- [ ] Filtros por tipo funcionam.

### A3. Justificativas — ERA: 422 em toda carga (tela vazia com erro)
- [ ] A tela carrega SEM erro 422 no console; filtros + botão Nova Justificativa
      presentes. "Nenhuma justificativa encontrada" = vazio-real (tabela vazia mesmo).

### A4. Bater Ponto — ERA: geolocalização bloqueada por Permissions-Policy
- [ ] A tela renderiza (relógio ao vivo + botão) e o navegador PEDE permissão de
      localização (não é mais bloqueado silenciosamente pela policy).
- [ ] Registre 1 batida de teste → deve confirmar na hora com o TIPO detectado
      automaticamente e o horário LOCAL correto (confira com seu relógio).
- [ ] TEMPO REAL: volte ao Dashboard Ponto → "Presentes hoje" deve refletir a batida
      IMEDIATAMENTE (sem esperar sync).

### A5. Dashboard — coerência
- [ ] KPIs carregam (colaboradores, inconsistências, banco de horas, Sync Sólides OK).
- [ ] Fechamento Mensal: Junho FECHADO/0 pendências · Julho ABERTO com pendências
      (as pendências de julho são reais — pontos em aberto do período).

## PARTE B — Sweep
- [ ] 7 telas (Dashboard, Bater Ponto, Espelho, Justificativas, Atrasos, Banco de
      Horas, Fechamento): zero "Algo deu errado", zero 500/422 no console.
- [ ] Banco de Horas: saldos negativos altos são esperados NESTE momento (defasagem
      D-1 da fonte + faltas reais) — não conta como bug de tela; o dado normaliza com
      o ponto próprio em agosto.

## RELATÓRIO FINAL
1. A1–A5: PASS/FAIL com print nos FAIL (no A4, informe o horário da batida de teste
   para o dev remover).
2. Sweep: OK/observações.
3. **VEREDITO: APROVADO / APROVADO COM RESSALVA / REPROVADO** — considerando que
   "Presentes 0 via Tangerino durante o dia" e "banco de horas negativo" são estados
   honestos da fonte atual (D-1), documentados, que se resolvem com o ponto próprio
   em 01/08.
