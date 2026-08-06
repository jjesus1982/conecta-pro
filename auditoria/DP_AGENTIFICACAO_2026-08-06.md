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

---

# Rodada 2 — os pontos levantados pelo T3

## F4 · A saga está VIVA — e o risco que ele apontou era real

Ele insistiu que *bake concluído ≠ vivo*, porque o `try/except` do registro **engole exceção**.
Estava certo, e o furo era concreto: às 12h de hoje o código estava no container e **o processo
em execução nunca havia registrado nada** — container de 10:33, commit da saga de 12:26, log
sem "Saga DP". Casca silenciosa clássica.

Fechado com as **duas** provas que ele exigiu:

**1 · registro no processo novo**
```
14:26:04  Saga DP→Financeiro: subscriber de folha_fechada ativo
14:26:04  Saga DP→Operacional: subscribers de admissão/demissão ativos
14:26:04  Saga DP: subscribers financeiro/operacional ativos
```

**2 · evento real atravessando o worker** — publiquei um `dp.folha.fechada` no Redis Stream,
**sem chamar o handler direto**:
```
publicado no Redis Stream: True
>>> RASCUNHO CRIADO PELO WORKER após 1,5s
    tipo=pagar_folha_lote   gate=🔴   requires_otp=True   status=rascunho
```

Também confirmei que `_dispatch` lê `self._handlers` **em tempo de entrega** — então a ordem
(consumer inicia na linha 98, subscribers na 126) não é problema.

## F5.3 · E2E propor→aprovar→executar

Cobaia: `registrar_afastamento` (🟡 reversível, percorre o caminho completo). A asserção que
mais importa é a quinta: **ação 🔴 de dinheiro não tem executor registrado** — pagar segue no
T1 com OTP na tela, sem caminho de execução automática. A parede está de pé.

## F5.1 · A mesa da Pyetra

Descobri que os prazos **não vivem em `agent_drafts`** — vêm dos watchers, em
`proativo_alert_state`. A Central mostrava só "o que o agente propôs" e deixava de fora "o que
está vencendo", que é justamente a coluna do quadro dela.

Nova tela **Prazos**, ordenada por urgência e agrupada por **área** — Férias, Términos de
contrato, Aviso prévio, Migração, Admissões — porque é assim que ela pensa, não por nome
técnico de regra. **16 prazos vivos** hoje.

## Término de experiência · o `tipo_contrato` era red herring

Eu havia deferido por `tipo_contrato` ser NULL em 50 de 52 ativos. **O campo nunca foi
necessário**: as datas saem de `data_admissao` com a convenção 30+60.

Conferi contra o quadro manuscrito e bate **ao dia**:

| quadro da Pyetra | watcher |
|---|---|
| "17/08 Meri, Jeovane" | MEIRE 17/08 · JEOVANE 17/08 |
| "18/08 Alexandre, Kelly, Nailson" | os três em 18/08 |

Validar o vigia contra a realidade dela — exibido == realidade — foi o que deu confiança na
derivação.

## Digest · existia e ninguém chamava

O T3 acertou: `montar_digest` era casca. **Não criei um segundo agendamento** — já havia
`proativo.digest_diario` às 07:00. Descobri que ele consolida *alertas de regra*, enquanto os
cartões da Central são outra coisa. Complementares, então liguei o meu **dentro** da task
existente, com dedup próprio. `EMAIL_FROM` está vazio, então entrega no **sino**; o e-mail liga
quando setarem a variável.

## O reframe que o Jordan provocou

Eu tinha escrito os alertas como se "não está no sistema" fosse falha de registro do DP. **Não
é** — o Conecta PRO está em construção, o dado vem da Portte e do eSocial, e o fluxo nativo vai
sendo assumido módulo a módulo.

Reescrevi: *"Desligamento a migrar para o fluxo nativo"*, explicando por que vale trazer. Isso
não é redação: um alerta que soa como cobrança faz a Pyetra parar de olhar o vigia, e aí ele
volta a ser inútil — que era o problema original.

Pelo mesmo motivo, **não alerto sobre "admissão sem processo"**.

---

## Estado final

| fase | |
|---|---|
| F0 higiene · F1 captura · F1.2 afastamento + admissão | ✅ |
| F2 vigília — **6 watchers, 16 prazos vivos** | ✅ |
| F3.1 rotineiras de ponto | ✅ |
| **F4 saga — VIVA, provada com evento real pelo worker** | ✅ |
| F5.1 mesa · F5.2 digest · F5.3 E2E | ✅ |

**28 provas, zero resíduo.** Motor intocado: `calculo_service`, espelho da Portte,
`folha-gerar`, períodos aquisitivos, a paridade de R$29,80 de julho.

## O único item deliberadamente fora

O **ritmo mensal do quadro** — VT/VR nos dias 12-14, kit 18-21, pagamento dia 20.

Não é esquecimento: é **calendário recorrente dela**, não prazo derivado de dado. Hardcodar as
datas seria fabricar agenda, e quebraria no primeiro mês em que a rotina mudasse.

O caminho honesto: a Pyetra cadastra a recorrência uma vez, aí vira dado e o watcher passa a
ser legítimo.

## O território do motor ficou intocado

`calculo_service`, `folha_verba_espelho`, a tela `folha-gerar`, a pipeline da Portte, os
períodos aquisitivos e a paridade de R$29,80 de julho: nenhum arquivo tocado. O gate de IRRF
não certificado não foi encostado.

O único arquivo compartilhado que editei foi `main_production.py` — 12 linhas de registro de
subscriber, no padrão exato dos vizinhos, com commit imediato para minimizar a janela com
outras sessões.
