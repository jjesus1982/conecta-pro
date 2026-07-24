'use client';

// ExportMenu — exporta a lista visível (Excel/PDF/CSV) client-side. Aparece em TODA tela de
// tabela com linhas (paridade com o <ExportButton> do clássico nas telas operacionais). Lê
// scr.cols + scr.rows (valor cru de cada célula), sem rota backend. Ver src/lib/rdexport.ts.
import { useEffect, useRef, useState } from 'react';
import { Download, FileSpreadsheet, FileText, Table } from 'lucide-react';
import { exportarTabela, type ExportFmt } from '@/lib/rdexport';

export function ExportMenu({ cols, rows, nome, titulo }: {
  cols: string[]; rows: string[][]; nome: string; titulo?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  if (!Array.isArray(rows) || rows.length === 0) return null;

  const go = (fmt: ExportFmt) => { setOpen(false); void exportarTabela(cols, rows, nome, fmt, titulo); };

  const item: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '7px 12px',
    background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 12.5,
    color: 'var(--ink, #0F1B3A)', textAlign: 'left',
  };

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button type="button" className="rd-btn rd-btn-outline" onClick={() => setOpen((o) => !o)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12.5, padding: '6px 12px' }}
        title={`Exportar ${rows.length} registro(s)`}>
        <Download size={14} /> Exportar
      </button>
      {open && (
        <div style={{
          position: 'absolute', right: 0, top: 'calc(100% + 4px)', zIndex: 50, minWidth: 150,
          background: 'var(--card, #fff)', border: '1px solid var(--line, #E2E8F0)', borderRadius: 10,
          boxShadow: '0 8px 24px rgba(15,27,58,0.14)', overflow: 'hidden', padding: 4,
        }}>
          <button type="button" style={item} onClick={() => go('xlsx')}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--fill,#F1F5F9)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
            <FileSpreadsheet size={15} color="#16A34A" /> Excel (.xlsx)
          </button>
          <button type="button" style={item} onClick={() => go('pdf')}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--fill,#F1F5F9)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
            <FileText size={15} color="#DC2626" /> PDF
          </button>
          <button type="button" style={item} onClick={() => go('csv')}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--fill,#F1F5F9)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
            <Table size={15} color="#2563EB" /> CSV
          </button>
        </div>
      )}
    </div>
  );
}
