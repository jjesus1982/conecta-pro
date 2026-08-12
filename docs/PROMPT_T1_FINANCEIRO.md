# Prompt para o T1 — fechar o FINANCEIRO (v2, calibrado pelas suas respostas)

> Cole o bloco abaixo inteiro numa sessão nova do T1, em `/opt/conecta-pro`.
> Sessão nova importa: as skills não carregam na sessão que as criou.
>
> **v2** substitui a v1: suas respostas em `docs/QUESTIONARIO_T1_FINANCEIRO_RESPOSTAS.md`
> mudaram metade do plano. O que você já fechou saiu daqui; o que você apontou entrou.

---

Você é o T1 e o **financeiro é seu território**. Vai fechá-lo por inteiro, em loop, com
autonomia total. Não peça permissão para agir. Pergunte só quando a resposta mudar o que você
faria — e mesmo aí, faça primeiro tudo que não depende dela.

## Primeiro: as três ferramentas que você não sabia que existiam

Você respondeu *"não usei nenhuma das três travas — não sabia que existiam"*. Isso é falha do
Arsenal, não sua. Elas rodam em segundos e trabalham em cima do que você já está fazendo:

```bash
python3 backend/scripts/qa/checar_repositorio.py      # financial: 19 chamadas a método que não existe
python3 backend/scripts/qa/checar_rotas_frontend.py   # frontend pedindo rota que o backend não tem
docker exec conecta-pro-backend python3 /app/scripts/qa/cacar_fabricacao.py       # valor inventado quando a fonte falha
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_vocabulario.py  # lista literal que a coluna não tem
python3 backend/scripts/qa/checar_regressao.py        # tudo contra a linha de base; roda sozinho à 00:00
```

O roteiro completo está em `docs/ARSENAL_SKILLS.md` (11 skills, 7 travas). Leia também
`auditoria/qa/MVP_servicos_fechamento.md` — as 5 barreiras descritas lá reaparecem aqui.

Skills: `conecta-pro-skills:plano-conecta`, `:raio-de-impacto`, `:oraculo-conecta`,
`:entregue-de-verdade`, `:fecha-modulo`.

## Território — mudou desde a v1

| | |
|---|---|
| **Seu** | todo o backend `financial/`, o razão, a escrituração, os oráculos que você criar |
| **De outra sessão** | `backend/scripts/qa/`, `docs/ARSENAL_SKILLS.md`, `frontend/src/lib` — não desfaça |
| ⚠️ **De NINGUÉM** | `frontend/src/app/modulos/financeiro/{banking,contabilidade,dashboard}/page.tsx` |

Os três arquivos do frontend têm **95 linhas modificadas e não commitadas**, sobre um commit
de 15/07. Você disse que não são seus; não são meus. **É WIP órfão de uma terceira sessão.**
Pela regra da parede: **não edite, não commite, não descarte.** Se o financeiro precisar
deles, pergunte ao Jordan primeiro — descartar trabalho alheio é o único erro que não dá para
desfazer.

```bash
git log --since="1 day ago" --oneline -- <arquivos>
git status --short -- <arquivos>
git check-ignore -v <arquivos>     # silêncio do status: livre ou INVISÍVEL?
```

A última linha não é firula: 73 arquivos de código do frontend estavam invisíveis ao git pela
regra `lib/`. **Onde o git é cego, a parede não existe.** Commite por pathspec
(`git commit -m "..." -- <arquivos>`), nunca `git add -A` com `--amend`/`reset` amplo.

## O que você já fechou (confirmei, não estou pedindo de novo)

- **Trigger do período fechado**: verifiquei em produção. `2026-03-15` →
  *"periodo contabil fechado… anterior ao corte de 01/08/2026"*; `2026-08-11` passa. As três
  portas por fora (`conciliacao_liquido`, `estoque_real`, `accounting_seed`) estão cobertas
  pelo banco, que é o lugar certo — remendo por serviço não cobre o próximo escritor.
- **Backups `backup_*_20260811/12`**: marcados como intocáveis. Ninguém encosta.

⚠️ Uma correção ao seu relatório: **`caixa_divergente` não é oráculo** — é *regra proativa*
em `modules/notifications/proativo/regras.py`. Ela vigia de verdade, mas por outro mecanismo:
**não entra na varredura das 00:00** e não aparece na contagem de oráculos. Vigilância aqui
tem dois sistemas, e vale saber em qual você está pendurando cada coisa.

## As 4 frentes, na ordem que eu faria

### 1. Backend — 19 chamadas a método inexistente, todas num arquivo só

`backend/modules/financial/costing/controllers/costing_controller.py`
(`get_multi`, `get`, `soft_delete`, `get_statistics`, …).

Costuma ser renomeação, mas **confira também a forma**: a trava tem dois olhos, e o segundo
pega método anotado `-> Schema` que devolve o dict cru do repositório. Em `serviços` ela
dizia verde com o dashboard ainda em 500. E **rastreie o módulo inteiro, não a pasta** — lá o
sintoma eram 4 rotas e a família era 78.

### 2. O EXTRATO — sua própria resposta 17, e concordo

Você disse: *"sem ele nada mais é verdade"*, e ele quebrou em silêncio **três vezes num dia**
(880 linhas duplicadas, sinal invertido em 94 registros, ponte recriando duplicata por
deduplicar via texto). A regra proativa cobre divergência de saldo — **ela não cobre as três
falhas acima**.

Escreva o oráculo do extrato em `backend/scripts/orq/test_oraculo_extrato.py`, afirmando
**invariantes**, não números:
- nenhuma duplicata por `(conta, data, valor, id_externo)`;
- sinal coerente com o tipo do lançamento (nenhum "RECEBIMENTO" com valor negativo);
- soma mês a mês do nosso extrato == saldo do próprio banco, dentro da tolerância.

**Prove em vermelho contra o código anterior** — oráculo que nunca viu vermelho não vale. E
respeite a sua própria lição nº 1: **fora da janela de cobertura da fonte, ausência não é
prova** (o `/extrato` do Inter só devolve de 07/02 em diante).

### 3. O resultado, que você mesmo não confia

Prejuízo de R$97.066,72 com **R$384.580,79 na transitória lançados como despesa** e os dois
CNPJs misturados. Enquanto isso não se resolver, **qualquer DRE é ficção plausível** — e
DRE é o tipo de número que sobe para o Jordan e vira decisão.

Duas coisas travam aqui, e a segunda é pré-requisito da primeira:
- as contas **3.x estão corrompidas** (`3.1.1 Portaria`, `3.1.2 Vigilância` dentro de
  *Capital Social*; `3.2.1 ISS 5%` dentro de *Lucros Acumulados*);
- **não existe lançamento em 3.x** — sem PL não há balanço, o resultado nunca encerra, e
  distribuição isenta não tem base escritural.

Refazer o grupo 3 é do seu escopo. ⚠️ **Mexer em plano de contas altera número que o Jordan
lê.** Use `_mutacao.Mutacao` (ensaio por padrão, `--aplicar` explícito, teto), e leve a
decisão de nomenclatura ao Jordan antes de aplicar — ele é a fonte da verdade organizacional.

### 4. Dinheiro que sai — o número que muda a conversa

Você mediu: **só o Inter transmite** (26 pagamentos, R$35.813,99), o Cora **não tem PIX de
saída na API**, e **89% do dinheiro sai pelo Cora** (R$136.426,78 de R$153.259 em agosto).
Ou seja: "pagar tudo pelo sistema" alcança **11%** hoje, e isso é limite de API do banco, não
defeito nosso.

**Escreva isso no relatório com essas palavras.** É a diferença entre "o módulo está
incompleto" e "o Cora não oferece o serviço" — e só a segunda é verdade.

As 6 rotas 404 em telas de pagamento (`banking`, `inter` ×2, `pagamentos-diaristas`,
`pagamentos-pj`) você não conhece. **Consertar ali é repontar a URL ou remover a chamada —
nunca exercitar o fluxo.** Confirme cada uma por `curl` com token antes de agir: a trava dá
pista, o HTTP dá prova. E lembre que três dessas telas são o WIP órfão: mapeie, não edite.

## Regras que não se negociam

1. 💰 **Dinheiro que SAI nunca é happy-path.** Verifique por leitura de código e por registro
   no banco. O gate de OTP não se contorna nem "só para testar".
2. 🏛️ **Governo é somente leitura.** Transmitir em QA gera evento real.
3. 🚫 **Nunca fabricar.** Fonte falhou → "aguardando dado". Vazio real é honesto; número
   estimado é o pior defeito desta casa.
4. 📅 **Período fechado não se reescreve.** Agora o banco recusa — mas `UPDATE` segue livre
   de propósito, então o cuidado continua sendo seu.
5. 🔔 Notificação é o **sino** (`communication_notifications`). Telegram é banido.
6. **Operacional é READ-ONLY para agentes.**

## Definição de ENTREGUE — três portões

1. **Servido pela rota real depois do bake.** `docker cp` é volátil e não recarrega módulo já
   importado. Deploy só por `scripts/deploy_backend_bluegreen.sh` (~15 min, rode em
   background). **Nunca reinicie o backend de produção para testar.**
2. **Oráculo que pega**, em `backend/scripts/orq/test_*.py` — a varredura da 00:00 acha
   sozinha. Afirme a **regra**, nunca a fotografia. Escreva a consulta de verdade de forma
   **independente**: copiar a query que você audita só prova que você sabe copiar.
3. **Nenhuma superfície nova sem vigia.**

Faltando um, é "feito" — não é "entregue".

## Suas três lições valem para mim também — e passaram a valer para todos

Entraram no Arsenal com o seu nome no motivo:

- **Fora da janela de cobertura de uma fonte, ausência não é prova.** (169 transações reais
  apagadas porque a API do Inter só retorna de 07/02 em diante.)
- **Antes de concluir "está velho", confirme que alguém escreve naquele campo.**
  (`last_sync_at` é coluna morta; quem grava é `last_balance_update`.)
- **Alarme que toca sempre é alarme que ninguém lê — o corte temporal é o que o mantém
  crível.** (Escrituração às 05:20 contra extrato que chega 08:00.)

O padrão que você mesmo nomeou é a regra mais valiosa das três: *"eu estava confiante e
errado, e o que me pegou foi sempre uma medição contra algo de fora, nunca uma releitura do
meu próprio código."*

## O loop

```
1. raio-x: rotas montadas × telas × tabelas com dado
2. travas (as 5 acima) — anote o número ANTES
3. conserte a FAMÍLIA, não o caso
4. oráculo por lógica não-trivial, provado em vermelho
5. bake · confira pela rota real com token · compare com o banco
6. checar_regressao — a base cai sozinha; subir exige --gravar e commit
7. volte ao 1 até as travas zerarem no financeiro
```

## Ao terminar

`auditoria/qa/financeiro_<AAAAMMDD>.md`, com veredito por lente (DADO / TELA / CÓDIGO), o que
ficou **NÃO COBERTO** e por quê, e os números antes → depois.

**"NÃO VERIFICADO" é resultado válido; "passou" sem evidência não é.** E separe as duas
coisas ao dizer que fechou: *dimensão de contrato fechada* ≠ *módulo pronto*. Em `serviços` o
contrato fechou e o produto continua casca — dizer só a primeira metade seria mentira.
