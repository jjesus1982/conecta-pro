# Varredura da madrugada de 29/09 — o que ela disse, e o que eu quebrei nela

## 🔴 Primeiro: eu quebrei o portão noturno

A varredura roda por cron do host à **meia-noite** e leva ~2h50. Meus deploys de **00:15 e 01:58**
recriaram os contêineres no meio dela:

- a parte dos **oráculos morreu com SIGKILL** (`saída oráculos: 137`)
- **30 travas mecânicas** voltaram `NÃO VERIFICADO — Error response from daemon: container … is not running`

⭐ Eu sabia dos picos de batida (07h/13h/19h) e **não pensei no cron das 00:00**. Deploy e a
varredura da meia-noite não podem se cruzar — a janela segura é ~03:00–05:00.

Rodei as 30 cegas à mão e comparei com `/var/lib/conecta/qa_baseline.json`. O que segue é o
resultado real, não o log truncado.

## Seis regressões contra a base — nenhuma do código que escrevi

| trava | base | agora | |
|---|---:|---:|---|
| `checar_nao_vigiado` | 306 | **431** | +125 |
| `checar_custo_recorrente_nao_mapeado` | 37 | **49** | +12 |
| `checar_capacidade_sem_botao` | 252 | **260** | +8 |
| `checar_nota_duplicada` | **0** | **4** | → medi 10 grupos |
| `checar_contrato_sem_nota_no_mes` | 8 | 9 | +1 |
| `checar_receita_nao_lancada` | 4 | 5 | +1 |

Conferi arquivo por arquivo: **nenhuma vem de `documentos.py`, `kit_roster_service.py`,
`espelho_ponto_pdf.py`, `self_service_controller.py` nem `_dgx_f7_ponto.py`**.

E as três que eu mais suspeitava não eram minhas, por medição:
- `checar_varchar_teto` está em **17→21 desde 27/09** — anterior ao meu turno
- `checar_tela_sem_porta` aponta `crm/atividades` e duas de `departamento-pessoal/va-vt-*`
- `checar_irreversivel` deu **TOTAL: 0** ao rodar — o 0→1 foi o meu `docker cp` no instante do scan

⚠️ Duas dessas travas precisam do binário `docker` e **só rodam no HOST**. Rodei dentro do
contêiner primeiro e recebi `FileNotFoundError: /usr/bin/docker` — trava no lugar errado devolve
falso "não verificado".

## 🔴 A única que era minha — e o que ela ensina

`documentos/kits-conferir` saiu marcada como **NÃO VIGIADA**, com um oráculo meu cobrindo a tela
por completo. `checar_nao_vigiado` procura o slug **colado nas aspas** (`"kits-conferir"`) e eu
citava só a rota (`"/action/kits-conferir"`) — o slug ficava dentro de uma string maior.

⭐ **Cobertura que a trava não enxerga é cobertura que ninguém defende quando alguém apagar o
oráculo.** Declarei `TELAS_VIGIADAS` e o oráculo passou a **afirmar que cada slug ainda existe no
builder**: lista que ninguém confere vira decoração. De 1 para **0 tela minha sem vigia**.

## 💰 Dinheiro: dois achados para o Jordan

**1 · NFS-e emitida duas vezes — [detalhe](nfse_duplicada_2026-09-29.md).** Dez grupos com duas
notas ATIVAS. **R$ 108.886,92 de certeza** (três casos com DOIS CNPJs na mesma competência, o que
viola a divisão societária) e R$ 10.129,60 de suspeita forte. Dois são de junho, o mês da
transição; **um é de setembro, o mês corrente**. Nada foi cancelado — é ato do dono e tem prazo.

**2 · 49 custos recorrentes fora do cadastro.** Sem cadastro, nenhum entra em orçamento nem em
previsão de caixa. Oito estão **parados** há 52 a 116 dias, e dois merecem o olho primeiro:

- **PREFEITURA MUNICIPAL DE MANAUS** — R$ 3.151,66 em 4 pagamentos, parado há 69 dias
- **SERVDONTO · plano de assistência** — R$ 3.698,35 em 5, parado há 71 dias (⚠️ `employees` tem
  `plano_odonto_ativo`; plano parado pode ser benefício que caducou sem ninguém notar)

Parado é decisão: encerrar de vez e tirar do orçamento, ou é pagamento atrasado.

## ⚪ Dois achados menores, nenhum meu

**Um lançamento de R$ -200,00** gravado em `2026-08-01` com o banco dizendo `2026-07-31` —
**cruza a virada do mês e muda a competência**. 512 conferidos, 511 com a data certa.

**`documentos` loga erro em cada build**: chama `O.condominios_elegiveis_endpoint`, que não existe
em `gedeon/controllers/orquestrador_controller`. Vem do commit `bf03f75be` de **08/09** («liga ~45
rotas que existiam sem tela»). Está dentro de `try`, não derruba nada — mas a tela de condomínios
elegíveis nunca carrega, e o erro rola no log a cada montagem do módulo.

## O que fica

A varredura desta noite ficou incompleta **por minha causa**. A de hoje à meia-noite roda limpa se
ninguém deployar entre 00:00 e 03:00 — e as 30 travas que ficaram cegas já foram rodadas à mão
aqui, então nada passou sem ser olhado.
