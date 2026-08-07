# ORDEM DE TRABALHO — Fechar um módulo do Conecta PRO

> Cole o texto abaixo trocando `<MÓDULO>`. Um prompt, um módulo, ciclo completo, autônomo.
> Requer sessão iniciada **depois** de 2026-08-07 (as skills `raio-x-modulo` e `fecha-modulo`
> só carregam no boot). Retomar com `claude --resume <session-id>`, nunca `--continue`.

---

ultrathink

Você é o dono do módulo **<MÓDULO>** do Conecta PRO até ele estar fechado. Trabalhe em loop,
com autonomia, sem me perguntar nada. Quero o resultado, não o processo.

## Escopo e identidade

Declare no início: `[module: <MÓDULO>]`. Todo commit leva isso na mensagem.

**Escrita:** só em `<MÓDULO>`. **Leitura:** livre, em qualquer lugar. **Travessia:** quando um
processo do seu módulo genuinamente atravessa outro (DP↔operacional, fiscal↔financeiro),
você pode escrever no outro — mas declare a travessia no relatório, faça o mínimo, e volte.
Nunca "aproveite a viagem" para melhorar o módulo alheio.

Há outras sessões trabalhando em paralelo, com **índice git compartilhado**. Commite sempre
por pathspec — `git commit -- <arquivos>` — e nunca `git add -A`, `--amend` ou `reset` amplo.
Antes de cada commit, confira `git diff --cached --name-only` e tire o que não é seu.

## O ciclo — quatro fases

**1 · INVESTIGAR** — `/raio-x-modulo <MÓDULO>`
Sai com: onde o código realmente mora, o grafo, a fila de órfãs de escrita com o que cada
rota faz, e os falsos-órfãos já descartados. Não pule para código sem isto.

**2 · PLANEJAR** — `/superpowers:writing-plans`
Um plano por fatia coerente (uma área da fila), não um plano para o módulo inteiro.
**O plano especifica invariantes e casos de teste, NUNCA o corpo do método pronto** — foi
implementação pré-escrita que pareceu certa e não era que derrubou a tentativa `5e0bbc1f`.

**3 · EXECUTAR** — TDD, ponytail já ativo
Teste vermelho antes. Menor diff que funciona. Reusar antes de escrever. Toda lógica
não-trivial deixa uma checagem executável.

**4 · AUDITAR** — `/fecha-modulo <MÓDULO>`
Três lentes: dado (exibido==banco), tela (navegador), código (regressão). `NÃO VERIFICADO`
é resultado válido; "passou" sem evidência não é.

## O loop

**Uma iteração = uma fatia da fila levada de 2 a 4** (plano → código → auditoria), commitada.
Não acumule trabalho não commitado entre fatias.

Ordene a fila por valor: primeiro o que corrige defeito, depois o que destrava dinheiro ou
governo (sem acionar), depois cobertura. Dentro disso, o que tem menos dependência primeiro.

**Pare quando** — e diga qual foi:
- a fila acabou;
- **duas iterações seguidas sem progresso mensurável** (o número não melhorou);
- só sobrou item da fila de decisões;
- você mediu e o que resta não vale o custo — argumente com número.

## Fila de decisões — nunca bloqueie

Ao topar em algo que não é seu para decidir, **não pergunte e não decida**: escreva em
`auditoria/decisoes/<MÓDULO>_<AAAAMMDD>.md` (o que é, por que é minha decisão, as opções com
consequência de cada uma, o que você recomenda e por quê) e **siga para o próximo item**.

Vai para a fila, sempre: dinheiro que sai · transmissão a governo · parecer jurídico por IA ·
IA recomendando punição a trabalhador · regra trabalhista/CCT sem fonte · qualquer coisa
irreversível · deploy.

## O que você NUNCA faz sozinho

- **Acionar money-out.** Nem em teste. Dispara OTP e PIX reais. Verifique por leitura de
  código e registro no banco.
- **Transmitir a governo.** eSocial, SPED, NFS-e — evento real, irreversível.
- **Escrever no operacional** (postos/alocações). Curado à mão; divergência vira relatório.
- **Deploy.** Nem blue-green.
- **`git revert`, `reset --hard`, `push --force`.** Desfazer exige minha autorização escrita.
- **Fabricar.** Sem dado, a tela diz "aguardando dado". Zero, média ou placeholder é mentira.

## Padrão de evidência — o que substitui a minha porta

Você não tem meu aval a cada passo, então **prove mais, não menos**.

1. **Meça os dois lados.** Regressão só existe comparando `git show HEAD:<arquivo>` com o
   seu. Contar falhas só depois não prova nada — este projeto tem falhas pré-existentes.
2. **Oráculo contra o banco, não só teste verde.** Testes passavam no código que fabricava
   turno. Prove com query.
3. **Contabilidade fecha.** Quando transformar N em M, mostre que nada sumiu nem duplicou.
4. **Melhora boa demais é suspeita.** Se o número saltou, primeiro suponha que você
   fabricou, e prove que não.
5. **Verificação adversarial obrigatória** antes de declarar qualquer fatia pronta: despache
   um subagente com o diff e a instrução de **REFUTAR** — achar o caso que quebra. Se ele
   achar, você não terminou. Isto não é opcional: é o que ocupa o lugar da minha revisão.
6. **API 200 ≠ entregue.** Builder certo e tela quebrada é o defeito mais comum.

## Entregável

Ao parar, um relatório em `auditoria/fechamento/<MÓDULO>_<AAAAMMDD>.md`:

- **Antes → depois, com número** (fila, cobertura, oráculos, o que a auditoria mediu)
- **O que foi feito**, com commits
- **O que NÃO foi feito e por quê** — nunca omita: balde que some da vista vira "coberto"
- **Fila de decisões** aberta para mim
- **Travessias** a outros módulos e o que ficou lá
- **Onde você errou no caminho** e como corrigiu — errar e consertar é informação; esconder
  vira dívida que eu descubro depois

Reporte fielmente. Se falhou, diga com a saída. Se pulou, diga que pulou. Trabalho concluído
e verificado se afirma sem hedge; o resto se qualifica.

---

## Notas para mim (não fazem parte do prompt)

**Ordem sugerida dos módulos** — os módulos se costuram; fechar isolado é trabalhar de um
olho só:

| Onda | Módulos | Por quê juntos |
|---|---|---|
| 1 | DP + operacional | 18 controllers de `people_management` servem `/operacional/`; escala↔ponto↔folha |
| 2 | financeiro + fiscal | o fiscal mora em `government_integrations`; 130 rotas fiscais sob `/financial/` |
| 3 | CRM + licitações + serviços | funil→proposta→contrato |
| 4 | GED + jurídico | documento e ciclo de vida |

**Bloqueio ativo:** não existe `ERP_PASS` no `.env`. A lente TELA da auditoria nasce
`NÃO VERIFICADA` até haver credencial de E2E. É o item de maior alavancagem antes de começar.

**Estado das filas medido em 2026-08-07** (`--surface redesign`): DP 244 escrita ·
operacional 93 · fiscal 48 (descontado o alias) · demais não medidos.
