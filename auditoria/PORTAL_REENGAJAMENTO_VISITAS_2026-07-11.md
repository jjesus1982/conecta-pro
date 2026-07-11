# Portal do Cliente — Frentes 1 (Reengajamento) e 2 (Visitas de gestão) — 2026-07-11

Contexto: raio-x do portal mostrou infra boa mas SEM produtores de notificação
(caixa parada em avisos antigos, último login de cliente em 30/06) e nenhuma
visibilidade das visitas de gestão recém-construídas.

## Frente 1 — Reengajamento (construído + provado)
- notificar() ganhou email_override (teste admin) — envio externo agora LIGADO:
  PORTAL_NOTIFY_ENABLED=true no .env (SMTP Hostinger já existia).
- PRODUTORES novos:
  1. Kit 'enviado' (GED) → aviso na caixa do portal com link (best-effort).
  2. Resumo mensal automático: task portal.resumo_mensal_clientes — beat dia 1º
     09:00 SP (08:00 Manaus), fila gov.batch. Por cliente: kit da competência,
     assiduidade real (serviço existente), ocorrências sanitizadas e visitas de
     gestão do mês. Seção sem dado = "sem registros" (nunca inventa).
  3. Gatilho admin POST /portal/access-management/resumo-mensal/disparar
     (client_id/competencia/enviar_email/email_override).
- PROVA: disparo p/ MIRANTE (2026-07) → caixa "Resumo de julho — MIRANTE" +
  E-MAIL REAL entregue a jordansjesus@gmail.com (email: true). 

## Frente 2 — Visitas de gestão no portal (construído + provado)
- GET /portal/operacao/visitas: rondas de inspeção do condomínio do cliente,
  SANITIZADAS — allowlist de tipos (check-in/out, reunião, verificação de posto,
  observação geral), exclui checkpoints com ocorrência/medida/verificação de
  funcionário; NUNCA expõe descrição interna. Horas UTC→Manaus.
- Fotos servidas por cadeia validada cliente→posto→ronda→checkpoint→arquivo
  (path-safe) em rota autenticada do portal.
- Frontend: seção "Visitas da gestão" no Raio-X (data, responsável,
  chegada→saída, duração, chips de atividades, fotos com lightbox) + card
  "Última visita da gestão" no dashboard. FotoVisita = blob autenticado.
- PROVAS E2E (visita real criada no Mirante e revertida):
  | síndico Mirante vê a visita c/ 1 foto (bytes idênticos) | ✅ |
  | nota interna do supervisor ("SENSÍVEL") não vazou | ✅ |
  | síndico Michelangelo: 0 visitas e foto → 404 (isolamento) | ✅ |
  | telas renderizadas via preview-token no navegador, console limpo | ✅ |

## Percalços reais da trilha
- Bake concorrente de outro terminal recriou o backend no meio do 1º E2E
  (respostas vazias) — reexecutado após o lock; a imagem nova já continha o
  código do portal (buildada da árvore). Beat pegou snapshot sem o agendamento
  (edição concorrente ao build) → docker cp + bake final consolidou.
- preview-token devolve preview_url (não campo token) — extração corrigida.

## Limpeza
Visita de teste do Mirante (ronda+checkpoints+foto) e aviso de teste da caixa
removidos — 0 rondas ativas, 0 resumos de teste. Estado vazio honesto provado.

## Segurança/observações
- E-mails dos clientes: maioria são aliases internos @conectamais.pro; PRIME e
  LARANJEIRAS têm Gmail REAL do cliente — o resumo mensal do dia 1º vai para
  eles quando rodar (comportamento desejado da frente 1; avisar os síndicos).
- Próximos (backlog do raio-x): José Luís com LLM (depende do crédito
  Anthropic), boletos Inter no portal, token do portal em cookie httpOnly.
