#!/bin/bash
# Painel de monitoramento do José Luís — o que ENTRA e o que SAI, e onde falhou.
# Criado 24/09/2026 a pedido do Jordan: "este terminal vai monitorar tudo que entra e sai".
# READ-ONLY. Roda em segundos; feito para ser executado em ciclo.
J=${1:-20}   # janela em minutos
echo "═══ JOSÉ LUÍS · últimos ${J}min · $(date -u -d '-4 hours' +%H:%M) Manaus ═══"

echo "── ENTRANDO (grupos) ──"
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -t -A -F' | ' -c "
SELECT g.nome, coalesce(m.autor_nome,'⚠️ SEM AUTOR'), m.classificacao, left(replace(m.conteudo,chr(10),' '),46)
  FROM wa_grupo_mensagens m JOIN wa_grupos g ON g.jid=m.grupo_jid
 WHERE m.criado_em > now() - interval '${J} minutes' ORDER BY m.criado_em DESC LIMIT 8;" 2>/dev/null

echo "── SAINDO (o que ele publicou) ──"
docker exec chatwoot-fazerai-postgres psql -U chatwoot -d chatwoot_fazerai -t -A -F' | ' -c "
SELECT ct.name, CASE WHEN m.private THEN '⚠️ NOTA (não saiu)' ELSE '✅ enviado' END,
       left(replace(m.content,chr(10),' '),58)
  FROM messages m JOIN conversations c ON c.id=m.conversation_id JOIN contacts ct ON ct.id=c.contact_id
 WHERE m.message_type=1 AND m.created_at > now() - interval '${J} minutes' ORDER BY m.id DESC LIMIT 6;" 2>/dev/null

echo "── FALHAS no caminho do agente ──"
docker logs conecta-pro-celery-integrations --since ${J}m 2>&1 | grep -ioE "resposta VAZIA|reasoning_content|tool desconhecida|no teto de|parede falhou|autor NÃO identificado|não consegui|Trace" | sort | uniq -c | sed 's/^/  /'
docker logs conecta-pro-backend --since ${J}m 2>&1 | grep -icE "grupos: autor NÃO identificado" | sed 's/^/  autor não identificado (webhook): /'

echo "── PENDÊNCIAS que ele registrou ──"
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -t -A -F' | ' -c "
SELECT tipo, gate, left(titulo,58) FROM agent_drafts WHERE status='rascunho' ORDER BY created_at DESC LIMIT 5;" 2>/dev/null

echo "── ROTINA DE TURNO (véspera 18:00 · lembrete 04-07 · cobertura 08:30, Manaus) ──"
docker exec conecta-pro-postgres psql -U postgres -d conecta_pro -t -A -F' | ' -c "
SELECT coalesce(count(*)::text,'0')||' confirmações · '||
       coalesce(sum(CASE WHEN status='confirmado' THEN 1 ELSE 0 END)::text,'0')||' confirmadas · '||
       coalesce(sum(CASE WHEN status='nao_avisado' THEN 1 ELSE 0 END)::text,'0')||' NÃO avisadas'
  FROM troca_turno_confirmacoes WHERE data >= current_date;" 2>/dev/null
