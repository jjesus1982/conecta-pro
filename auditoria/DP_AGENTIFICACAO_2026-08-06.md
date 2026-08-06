# DP — Agentificação · o que foi construído · 06/08/2026

> Loop autônomo, dono ausente. Plano: `docs/superpowers/plans/2026-08-06-dp-agentificacao.md`.
> Ledger: `.superpowers/sdd/progress-dp.md`. 5 commits, tudo provado em bancada, 0 resíduo.

---

## O que a Pyetra ganha, em uma frase

O quadro branco de prazos dela deixou de viver só na parede: **quatro vigias contam os dias
sozinhos**, e o que eles encontram vira cartão na Central para ela aprovar.

## O achado que justifica a frente inteira

O primeiro watcher que rodou contra o banco real encontrou:

> **9 pessoas com data de desligamento no cadastro e SEM processo de rescisão.**

É o caso Keyson quantificado. Sem processo não existe aviso prévio para vigiar, não nasce TRCT
e o eSocial S-2299 não é gerado. O prazo que estourou não foi esquecido — ele **nunca entrou
no sistema**.

Por isso a regra `dp_desligamento_sem_processo` é o **vigia do próprio vigia**. Sem ela, o
silêncio do watcher de prazo seria lido como "está tudo em ordem", que é exatamente a falha
original.

---

## F0 · A camada morta saiu

Removidos `hr/skills/{payroll,benefits,compliance,documenter}_skill.py` e
`integration/skills/orchestrator_skill.py`. Zero importador vivo, nada montado no boot.

O grafo do DP mostrava **`BaseAgent` como god node nº2, com 76 arestas** — sendo código que
ninguém chama. Três dos dez nós mais conectados do módulo eram cascas. A dívida não era inerte:
distorcia a leitura da arquitetura.

**O landmine do plano era real e foi desarmado:** `orchestrator_skill` importava
`compliance_skill`. Mas os imports são *lazy* (dentro de funções) e o próprio orchestrator só
era referenciado por **um teste tautológico** que apenas provava que a classe importa. Removi a
cadeia inteira — deixar o orchestrator sem o compliance quebraria em tempo de chamada, pior que
a casca.

Prova: `from main_production import app` → **4174 rotas antes e depois**.

## F1 · Captura — o dado que nasce fora do sistema

`agir_dp("registrar_desligamento")` propõe abrir o processo de quem já tem desligamento no
cadastro. O executor chama `TerminationService.create_termination` — **o mesmo serviço da
tela**. Zero terceiro escritor.

**Honestidade do não-derivável:** o tipo da rescisão não sai do cadastro. O rascunho nasce com
o campo em aberto e diz *"CONFIRME antes de aprovar: tipo da rescisão — não é derivável e eu
não chuto"*, em vez de assumir `sem_justa_causa` em silêncio.

**Corrigi um invariante que eu mesmo errei.** Meu primeiro teste punha um *boom* em
`create_termination`, assumindo que a proposta não podia criar nada. Errado: o helper `propor`
**cria a entidade inerte** — é o padrão do módulo (`solicitar_ferias` nasce `SUBMITTED`). O
invariante certo é que a **conclusão** nunca dispare. Testar o invariante errado dá falsa
segurança, então o teste passou a botar boom em `complete_termination`/`calculate_*` e a
verificar `status='initiated'`.

## F2 · Vigília — quatro watchers de prazo

| regra | severidade | achados hoje |
|---|---|--:|
| `dp_aviso_previo_vencendo` | crítico | 0 |
| `dp_ferias_limite_gozo` | crítico | 1 |
| `dp_desligamento_sem_processo` | atenção | **9** |
| `dp_retorno_ferias` | atenção | 0 |

**Um falso positivo foi caçado e morto na bancada.** ORLAILSON aparecia como 🔴 art. 137. Ele é
PJ — foi desligado como CLT com férias **indenizadas** (verba 0062, rescisão) e recontratado
como PJ. Se eu não tivesse conferido, o primeiro alerta que a Pyetra visse já seria mentira.

O alerta separa **risco real** de **falta de registro**, e pula contrato suspenso (o caso
ARYELTON: rescisão indireta em curso, o aquisitivo não corre).

## F4 · Saga — assinar, não reviver

Confirmei no código o que estava em disputa: o `dp.*` **já estava vivo**, com 11 publishers
reais e chamados. Só o GEDEON escutava. Financeiro e operacional **publicam e não assinavam
nada do DP** — a cadeia nunca teve a metade que reage.

```
dp.folha.fechada        → financeiro PROPÕE o lote de pagamento   (🔴 + OTP)
dp.funcionario.admitido → operacional PROPÕE alocar em posto      (🟡)
dp.funcionario.demitido → operacional PROPÕE baixar alocação      (🟡)
```

A baixa importa: sem ela o posto aparece coberto por quem já saiu, e a escala segue lançando
plantão — um dos defeitos que a paridade da folha expôs em julho.

**Prova decomposta**, porque o bus é Redis Streams e o E2E completo exigiria o worker:
(a) inscrição — 1 handler em cada um dos 3 tipos; (b) comportamento — handler direto cria
**1** rascunho, idempotente em 2 chamadas, gate 🔴 + OTP no de dinheiro, e evento sem
competência **não cria nada**.

## F5.2 · Digest diário

`montar_digest` monta o corpo; quem despacha é o canal existente — assim dá para testar sem
mandar e-mail. **Silêncio honesto:** sem item aberto devolve `None`. E-mail vazio todo dia
treina a pessoa a ignorar o canal.

---

## Regressão final — tudo verde

```
tools_acao_dp   6/6 PASS      captura   5/5 PASS      digest  1/1 PASS
watchers        4 registradas  saga      3 handlers    boot    4174 rotas
```

**Um resíduo meu, achado e limpo:** 2 funcionários `BANCADA_*` sobraram de execuções que
falharam **antes** de alcançar o `finally`. Descobri porque o watcher subiu de 9 para 10 e fui
conferir o décimo. O vigia acabou servindo de sentinela do meu próprio teste. Cleanup em
`finally` não cobre falha no setup.

## O que ficou de fora, e por quê

Nada bloqueado por decisão sua — ficou por orçamento de contexto desta sessão:

- **F1.2** captura de admissão/afastamento (mesmo molde de F1.1, direto)
- **F3.1** rotineiras extras no `agir_dp` — holerites em lote, fechar/justificar ponto, renovar
  ASO, programação de férias. *`calcular_folha` e `fechar_folha` já existiam e já propõem.*
- **F5.1** a mesa visual da Pyetra no /redesign. A Central já está no ar e **recebe tudo que
  foi construído**; falta o agrupamento por tipo e o calendário de prazos.
- **F5.3** E2E aprovar→executar. Cada peça está provada isolada; falta o encadeamento.
- **Watcher de término de experiência** — `tipo_contrato` é NULL em 78 de 90 cadastros.
  Nasceria cego. Espera a captura preencher o campo.

## O território do motor ficou intocado

`calculo_service`, `folha_verba_espelho`, a tela `folha-gerar`, a pipeline da Portte, os
períodos aquisitivos e a paridade de R$29,80 de julho: nenhum arquivo tocado. O gate de IRRF
não certificado não foi encostado.

O único arquivo compartilhado que editei foi `main_production.py` — 12 linhas de registro de
subscriber, no padrão exato dos vizinhos, com commit imediato para minimizar a janela com
outras sessões.
