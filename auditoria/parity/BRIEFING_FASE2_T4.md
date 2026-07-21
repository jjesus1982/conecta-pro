# BRIEFING FASE 2 — T4 (cluster financeiro/comercial)

Cole numa sessão claude nova (o T2). Trabalhe em LOOP.

---

Você é o **T4** na Fase 2: trazer TODO dado real do **clássico** pro **redesign**, com fidelidade.
3 terminais (T1, T2, T4) em paralelo, atribuições RÍGIDAS, deploy SERIALIZADO. cd /opt/conecta-pro.

## LEIA nesta ordem
1. `auditoria/parity/DISTRIBUICAO_FASE2.md` — a divisão + o protocolo de deploy + o loop (FONTE DA VERDADE).
2. `auditoria/parity/FASE2_PLANO.md` — as 3 fundações (gate / kit de ação / oráculo).
3. `auditoria/parity/CORRECOES.md` — exemplos do padrão delegar+estender.

## SEUS MÓDULOS (edite SÓ estes arquivos `redesign_builders/<mod>.py`)
`financeiro` · `crm` · `empresas` · `seguranca` · `recrutamento` · `servicos` · `agendador` ·
`assistente` · `bi` · `analytics`
(arquivo sem hífen; slug com hífen em `SLUG`). Você já conhece o financeiro (fez os KPIs/Saldos).

## O LOOP (por tela dos seus módulos)
1. **Oráculo**: `python3 auditoria/parity/oraculo_fidelidade.py /modulos/<classic> "/redesign/<slug>?t=<tela>" <label> /tmp` → mostra o que falta trazer do clássico.
2. **Corrigir** no seu módulo (delegar+estender): dado real da MESMA tabela do clássico. Enum/json → `::text`/`->>'k'`.
3. **Provar** local (container test do build + SQL no banco).
4. **DEPLOY SERIALIZADO** (regra do Jordan): ANTES de deployar, espere o lock:
   ```bash
   while ls /tmp/conecta_deploy.lock >/dev/null 2>&1; do echo "lock ocupado, esperando..."; sleep 15; done
   git add ... && git commit --no-verify -m "..."   # commit ANTES
   timeout 600 ./scripts/deploy_backend_bluegreen.sh  # NUNCA timeout<600, NUNCA cortar
   ```
5. **Verificar** (oráculo fecha? + browser badge "dados reais") + **push** + marcar checklist no DISTRIBUICAO_FASE2.md.

## REGRAS (inegociáveis)
- Informação = clássico (real, no banco). NUNCA fabricar; sem dado = "aguardando dado".
- Botão/escrita (Emitir/Sincronizar/Aprovar) → passa pelo GATE `redesign_write_gate.py` (money/gov=OTP; teste em homologação; nunca auto-fire; nunca verde falso).
- NUNCA edite arquivo alheio, o registry, `redesign_write_gate.py`, ou `ModuleView.tsx` (fundações do T1) — se precisar de frontend novo, sinalize ao T1.
- NUNCA 2 deploys ao mesmo tempo — sempre cheque o lock e espere. Push por iteração.

Trabalhe em LOOP, 100% focado. Bug → conserta na hora. Dúvida de escopo → pergunta.
