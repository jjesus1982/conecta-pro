# Prompt para o T1 — fechar o FINANCEIRO com o Arsenal

> Cole o bloco abaixo inteiro numa sessão nova do terminal T1, dentro de `/opt/conecta-pro`.
> Sessão nova importa: as skills não carregam na sessão que as criou.

---

Você é o T1 e o **financeiro é seu território**. Vai fechá-lo por inteiro, sem pendências,
trabalhando em loop com autonomia total. Não pergunte permissão para agir; pergunte só
quando a resposta mudar o que você faria — e mesmo aí, faça primeiro tudo que não depende
dela.

## Como trabalhar

Use o **Arsenal**: `docs/ARSENAL_SKILLS.md`. Leia antes de começar. São 11 skills e 7 travas,
e o roteiro copiar-colar está na seção 5. Ele foi construído fechando o módulo `serviços`
(relatório em `auditoria/qa/MVP_servicos_fechamento.md`) — leia esse relatório também: as 5
barreiras que ele descreve reaparecem no financeiro.

Invoque as skills pelo nome (`conecta-pro-skills:plano-conecta`, `:raio-de-impacto`,
`:oraculo-conecta`, `:entregue-de-verdade`, `:fecha-modulo`). Trabalhe em loop ultrathink:
medir → consertar → provar → medir de novo, até a trava ficar em zero.

## Território e parede — leia antes da primeira linha

O financeiro é seu. **Outro terminal fechou `serviços` e mexeu em `backend/scripts/qa/`,
`docs/ARSENAL_SKILLS.md` e `frontend/src/lib`** — não desfaça nada disso.

Antes de tocar qualquer arquivo:

```bash
git log --since="1 day ago" --oneline -- <arquivos>
git status --short -- <arquivos>
git check-ignore -v <arquivos>     # silêncio do status: livre ou INVISÍVEL?
```

⚠️ A última linha não é firula. Em 12/08 apareceram **73 arquivos de código do frontend**
(`frontend/src/lib`) engolidos pela regra `lib/` do `.gitignore` — `git status` calado, sem
histórico, sem revisão. **Onde o git é cego, a parede não existe.** Já corrigido para
`frontend/src/lib`; pode haver outros cantos.

Commite **por pathspec** (`git commit -m "..." -- <arquivos>`), nunca `git add -A` com
`--amend` ou `reset` amplo: o índice e o HEAD são compartilhados entre as sessões.

## Regras que não se negociam

1. 💰 **Dinheiro que SAI nunca é testado por happy-path.** PIX, pagamentos, transferências:
   verifique por leitura de código e por registro no banco. Jamais acione. O gate de OTP
   humano existe e não se contorna nem "só para testar".
2. 🏛️ **Governo é somente leitura.** eSocial, SPED, NFS-e: transmitir em QA gera evento real.
3. 🚫 **Nunca fabricar dado.** Fonte falhou → "aguardando dado", nunca um número estimado.
   Vazio real é resposta honesta; número inventado é o pior defeito desta casa.
4. 📅 **Período contábil fechado não se reescreve.** `CORTE_CONTABIL = 2026-08-01` é decisão
   do Jordan. Já houve 184 lançamentos reclassificados por cima dele — e desfeitos.
5. 🔔 Notificação é o **sino interno** (`communication_notifications`). Telegram é banido.
6. **Operacional é curado à mão pelo Jordan e READ-ONLY.** Divergência vira relatório.

## O que já está MEDIDO (12/08/2026) — comece por aqui, não do zero

### Backend: 19 chamadas para método que o repositório não tem

**Todas no mesmo arquivo**: `backend/modules/financial/costing/controllers/costing_controller.py`
(`get_multi`, `get`, `soft_delete`, `get_statistics`, …).

```bash
python3 backend/scripts/qa/checar_repositorio.py     # financial: 19
```

Isto costuma ser **renomeação** (o método existe com outro nome), mas confira também a
**forma**: a trava tem dois olhos, e o segundo pega método anotado `-> Schema` que devolve o
dict cru do repositório. Em `serviços`, a trava dizia verde com o dashboard ainda em 500.

### Frontend: 6 rotas que não existem, em páginas REAIS de dinheiro

```
app/modulos/financeiro/banking/page.tsx              /api/v1/banking/payment
                                                     /api/v1/integrations/banking
app/modulos/financeiro/inter/page.tsx                /api/v1/financeiro/inter
app/modulos/financeiro/inter/pagamentos/page.tsx     /api/v1/financeiro/inter
app/modulos/financeiro/pagamentos-diaristas/page.tsx /api/v1/financial/pagamentos-diaristas
app/modulos/financeiro/pagamentos-pj/page.tsx        /api/v1/financial/pagamentos-pj
```

```bash
python3 backend/scripts/qa/checar_rotas_frontend.py
```

⚠️ **Estas são telas de pagamento.** Consertar aqui é **repontar a URL ou remover a chamada**
— não é exercitar o fluxo. Confirme cada uma por `curl` com token antes de agir (404 = não
existe mesmo); a trava dá pista, o HTTP dá prova.

### Vigilância: o financeiro está quase descoberto

Só 3 oráculos encostam nele: `test_oraculo_contabil_fecha.py`, `test_u2_financeiro.py`,
`test_acao_bancohoras_aprovar_redesign.py`. **Contas a pagar/receber, extrato, conciliação,
DRE e guias não têm vigia nenhum.**

## Definição de ENTREGUE — três portões, sem exceção

1. **Servido pela rota real depois do bake.** `docker cp` é volátil e não recarrega módulo já
   importado. Deploy só por `scripts/deploy_backend_bluegreen.sh` (~15 min, rode em
   background). **Nunca reinicie o backend de produção para testar** — foi erro registrado.
2. **Oráculo que pega.** Um por lógica não-trivial, em `backend/scripts/orq/test_*.py`. A
   varredura da 00:00 pega sozinha. Regras: afirme a **regra**, nunca a fotografia; escreva a
   consulta de verdade de forma **independente** (copiar a query que você audita só prova que
   você sabe copiar); e **prove o oráculo em vermelho** contra o código anterior — oráculo que
   nunca viu vermelho não vale.
3. **Nenhuma superfície nova sem vigia.**

Faltando um, é "feito" — não é "entregue".

## Três regras de método, compradas com erro caro

- **Prove o arreio antes de acusar o código.** Um construtor chamado errado produz
  `AttributeError` que parece defeito do sistema. Um `tsc` isolado acusou 7 erros num arquivo
  meu e **48** num arquivo intocado.
- **Falso positivo mata a confiança mais rápido que achado nenhum.** Confira uma amostra por
  HTTP/psql antes de reportar qualquer número grande.
- **Conserte a família, não o caso.** O sintoma de `serviços` eram 4 rotas em 500; a família
  era 78 no módulo e 139 no sistema. **Rastreie o módulo inteiro, não a pasta onde o defeito
  apareceu.** Depois de todo conserto, procure a assinatura no repositório inteiro.

## O loop

```
1. raio-x do módulo: rotas montadas × telas × tabelas com dado
2. travas: checar_repositorio · checar_rotas_frontend · cacar_fabricacao · checar_vocabulario
3. conserte a FAMÍLIA (não o caso), medindo antes e depois
4. oráculo para cada lógica não-trivial, provado em vermelho
5. bake · confira pela rota real com token · compare com o banco
6. checar_regressao (linha de base cai sozinha; subir exige --gravar e commit)
7. volte ao 1 até as travas zerarem no financeiro
```

## Ao terminar

Relatório em `auditoria/qa/financeiro_<AAAAMMDD>.md`, com **veredito por lente**
(DADO / TELA / CÓDIGO), o que ficou **NÃO COBERTO** e por quê, e os números antes → depois.

**"NÃO VERIFICADO" é resultado válido. "Passou" sem evidência não é.** E separe sempre as
duas coisas na hora de dizer que fechou: *dimensão de contrato fechada* ≠ *módulo pronto*.
Em `serviços` o contrato fechou e o produto continua casca — dizer só a primeira metade
seria mentira.
