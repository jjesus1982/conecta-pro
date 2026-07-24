'use client';
// RdBell — sino REAL do redesign (peça 4 da camada cognitiva).
// Substitui o badge hardcoded "3" por dado vivo: useUnreadCount (poll 30s) para o
// contador e useNotifications (lazy, só ao abrir) para o painel. Reusa os hooks do
// clássico (src/hooks/useNotifications.ts → /api/v1/operacional/comunicacao/*), cujo
// api-client já injeta o Bearer do localStorage access_token.
import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { useNotifications, useUnreadCount } from '@/hooks/useNotifications';

function tempoRelativo(iso: string | null | undefined): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return 'agora';
  if (s < 3600) return `${Math.floor(s / 60)}min`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export default function RdBell() {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const { total, refresh: refreshCount } = useUnreadCount(30000);
  const {
    notifications, isLoading, refresh, markAsRead, markAllAsRead,
  } = useNotifications({ autoLoad: false, initialPageSize: 12, initialFilters: { is_read: false } });

  // carrega a lista só na primeira abertura (lazy — não pesa navegação)
  useEffect(() => {
    if (open && !loaded) { refresh(); setLoaded(true); }
  }, [open, loaded, refresh]);

  // fecha ao clicar fora / Esc
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open]);

  async function lerUma(id: string) {
    const ok = await markAsRead(id);
    if (ok) { refresh(); refreshCount(); }
  }
  async function lerTodas() {
    const ok = await markAllAsRead();
    if (ok) { refresh(); refreshCount(); }
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative' }}>
      <button
        type="button"
        className="rd-icon-btn"
        aria-label={total > 0 ? `Notificações: ${total} não lidas` : 'Notificações'}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <Bell size={18} />
        {total > 0 && <span className="rd-dot-badge">{total > 99 ? '99+' : total}</span>}
      </button>

      {open && (
        <div
          className="rd-card"
          role="menu"
          style={{
            position: 'absolute', right: 0, top: 'calc(100% + 8px)', width: 340, maxWidth: '86vw',
            zIndex: 60, padding: 0, overflow: 'hidden',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>Notificações</span>
            {total > 0 && (
              <button type="button" className="rd-btn rd-btn-ghost" style={{ fontSize: 11, padding: '4px 8px' }} onClick={lerTodas}>
                Marcar todas como lidas
              </button>
            )}
          </div>

          <div style={{ maxHeight: 380, overflowY: 'auto' }}>
            {isLoading && <div style={{ padding: 16, fontSize: 12, color: 'var(--ink-weak)' }}>Carregando…</div>}
            {!isLoading && notifications.length === 0 && (
              <div style={{ padding: 18, fontSize: 12, color: 'var(--ink-weak)', textAlign: 'center' }}>
                Nenhuma notificação não lida.
              </div>
            )}
            {notifications.map((n) => (
              <div
                key={n.id}
                style={{ display: 'flex', gap: 10, padding: '11px 14px', borderBottom: '1px solid var(--border)', alignItems: 'flex-start' }}
              >
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--orange)', marginTop: 5, flex: 'none' }} />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{n.title}</div>
                  {n.body && <div style={{ fontSize: 11.5, color: 'var(--ink-weak)', marginTop: 2, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{n.body}</div>}
                  <div style={{ fontSize: 10.5, color: 'var(--placeholder)', marginTop: 4 }}>{tempoRelativo(n.created_at)}</div>
                </div>
                <button
                  type="button"
                  className="rd-btn rd-btn-ghost"
                  style={{ fontSize: 10.5, padding: '3px 7px', flex: 'none' }}
                  onClick={() => lerUma(n.id)}
                  aria-label="Marcar como lida"
                >
                  Lida
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
