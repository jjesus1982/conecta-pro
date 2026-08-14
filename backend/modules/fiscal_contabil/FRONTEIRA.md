# Onde mora cada coisa do fiscal — a fronteira dos três módulos

**Escrito em 14/08/2026** (ordem de fechamento Fiscal/Contabilidade, item F5).

Existem **três** módulos fiscais no repositório, e até aqui nenhuma regra dizia qual era de
quem. O sintoma: o raio-x de 14/08 mediu `fiscal_contabil` como "12 pastas, 8 vazias",
concluiu que a estrutura prometia dez áreas e entregava duas — e a leitura estava certa. As
oito pastas ocas foram removidas no mesmo dia. Este documento é para o buraco não voltar.

```
modules/fiscal                    8 arquivos ·  1.359 linhas
modules/fiscal_contabil          14 arquivos ·  2.128 linhas
modules/government_integrations 177 arquivos · 69.170 linhas
```

## A regra, em uma linha cada

| módulo | responde por | teste para saber se é aqui |
|---|---|---|
| `government_integrations` | **falar com o governo** — SOAP, mTLS, certificado A1, XML de evento, protocolo, recibo | *tem um órgão do outro lado?* |
| `fiscal_contabil` | **o que a empresa deve e quando** — calendário de obrigações, baixa por guia, notas fiscais | *é prazo ou documento nosso?* |
| `financial` (do T1) | **dinheiro e apuração** — razão, DRE, cálculo de tributo, pagamento | *vira lançamento ou pagamento?* |
| `modules/fiscal` | só **publishers de evento** (`publish_certidao_renovada`, vencimentos) | *é aviso para o resto do sistema?* |

## O que isso decide na prática

- **Consultar CND/CRF** → `government_integrations` fala com o órgão; quem grava o resultado é
  o GED (`ged_certidoes`). O calendário só **lê** para saber se está vencida.
- **Calcular DAS** → `financial` (é apuração). O `fiscal_contabil` não calcula tributo.
- **Dar baixa numa obrigação** → `fiscal_contabil/obrigacoes` — é prazo cumprido, não dinheiro.
- **Transmitir eSocial** → `government_integrations`, sempre, e nunca a folha (S-1200 é
  domínio da Portte enquanto durar o paralelo).
- **Emitir NFS-e** → `fiscal_contabil/notas_fiscais` monta, `government_integrations` transmite.

## Por que `fiscal_contabil` é pequeno, e está certo assim

Ele tem duas áreas com conteúdo (`notas_fiscais` 1.064 linhas, `obrigacoes` 1.002) porque as
outras oito **nunca existiram** — eram pastas com um `__init__.py` de zero byte. A capacidade
real de SPED, demonstrações e impostos mora em `government_integrations` e `financial`, e é lá
que deve continuar. Pasta vazia com nome de capacidade não é arquitetura: é promessa, e ela
custou tempo de leitura a todo mundo que passou por aqui.

**Se for criar pasta nova aqui, crie com o primeiro arquivo dentro.**

## O que continua sem dono declarado

`modules/bidding` (licitações) encosta no fiscal pelas certidões e não está na tabela de
territórios de ninguém. Em 14/08 os cinco `INSERT` dele escreviam numa tabela inexistente e
mataram três tarefas, uma delas o vigia de vencimento de certidão — consertado no mesmo dia,
mas a fronteira segue por declarar.
