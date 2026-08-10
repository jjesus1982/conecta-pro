# Fechar os fios soltos — estado e plano (vivo)

Atualizado 2026-08-10. Documento de continuidade: quem pegar isto no meio sabe onde parou,
o que já está no ar e por que certas coisas **não** foram ligadas.

## O número honesto

O inventário achou **167 órfãos que valem ligar**. Esse número não é a meta, porque o
renderizador de formulário do redesign não alcança todos:

| Situação | Qtd | Por quê |
|---|---:|---|
| **Vira formulário hoje** | **81** | corpo JSON ou botão seco |
| Só query param | 43 | o form manda JSON no **corpo**; ligar assim = botão que sempre falha |
| Id no caminho (`{id}`) | 43 | o endpoint do form é fixo; precisa ser **ação por linha** da tabela |

Mais 23 classificados **órfão legítimo** (webhook do Inter, `/integration/*` serviço-a-serviço,
rota de dev) e 7 **gated** (dinheiro que sai / transmissão ao governo).

> Correção de triagem: `integrations/banking/ted/transfer` caiu em LIGAR por falha da minha
> regra (ela via `transferencia`, não `transfer`). **É dinheiro saindo — é GATED.** Não ligar.

## Feito (33 telas, no ar)

| Módulo | Telas | Commit |
|---|---:|---|
| CRM | 17 | ficha, negociação, WhatsApp, reuniões, visitas, OS em PDF, follow-up, NPS, reativar, simular |
| RH — CCT | 6 | hora extra, adicional noturno, 13º, validar/auditar salário, reajuste |
| Jurídico | 4 | consultor, coletar DET, login do robô, semear base |
| Documentos | 4 | consultor GEDEON, intercorrência, indexar SOPHIA, montar kits |
| Licitações | 2 | sincronizar PNCP, sincronizar preços |

Todas provadas com `build()` real contra o banco, menu e telas casados nos dois sentidos.

## Duas regras que nasceram do trabalho

**Contato externo nasce em preview.** As rotas de envio do CRM têm `confirmar` (False =
simula, resolve o número, não envia). O select nasce vazio e campo intocado não é enviado,
então **o caminho preguiçoso do usuário é o seguro**. Enviar exige escolha explícita mais
diálogo de confirmação.

**Tela cujo produto é o retorno nasce com `showResult`.** Sem a flag ela diz "Calculado" e
joga o número fora — o defeito que o QA do fiscal encontrou. São **34 das 167**. A flag é
opt-in no `ModuleView` e **outra sessão está implementando agora**; até o front subir, a
chave é ignorada, então ligar já com ela é seguro e nasce certo.

## Não encostar

- **`frontend/src/components/redesign/ModuleView.tsx`** — trabalho VIVO de outra sessão
  (31 linhas não commitadas implementando `showResult`, já tratando o `recarregar()`).
- **Builders quentes:** `financeiro`, `operacional`, `fiscal`, `departamento_pessoal`,
  `marketing` — outros terminais. Vira handoff, não commit.
- **Medidas disciplinares (17 rotas).** É o maior bloco coerente sem ação no sistema: dá
  para ver a medida e não dá para criar, aprovar, assinar ou rejeitar. Mas o menu delas
  vive em `_op_grupos.py` (operacional, quente e curado à mão). **Handoff para o terminal
  do operacional.**

## Fila (o que falta, em ordem)

1. **Consultores Q&A** (4): `rh`, `gestao`, `comercial`, `ai/feedback` — mesmo molde do
   jurídico, todos com `showResult`.
2. **Avulsos em builder frio** (~8): `justificativa/registrar`, `empresas/resumo-mensal`,
   `analytics/kpis/recalcular`, `onvio/reclassificar`, `signatures/requests`,
   `ged/config/drive/connect|disconnect`, `ponto/sincronizar-solides`,
   `admin/cct/cache/invalidar`.
3. **Os 43 de query param** — precisam de uma ação `/redesign/action/*` que traduza corpo
   para query, ou de suporte a query no renderizador. Decisão de arquitetura, não de módulo.
4. **Os 43 de path param** — ação por linha nas tabelas que já existem. Trabalho por tabela.
5. **Handoffs**: financeiro (9), operacional (7 + disciplinar), fiscal (2).

## Como medir de novo

```bash
python3 /tmp/.../recon_todos.py      # 44 módulos, ~20s (carrega rotas e indexa o front 1x)
```

⚠️ A recon v2 tinha um bug que inflava o balde de órfãos: `grep` **omite o nome do arquivo
quando o alvo é UM arquivo**, então os 18.483 tokens de `redesign_data_controller.py` eram
descartados em silêncio. Corrigido com `-H`. Se algum número parecer alto demais, suspeite
do medidor antes do sistema.
