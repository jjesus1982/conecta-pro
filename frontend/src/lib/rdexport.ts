// Exportação client-side de listas do REDESIGN (Excel / PDF / CSV) — sem rota backend:
// os dados já estão na tela (scr.cols + scr.rows). Espelha o <ExportButton> do clássico
// (xlsx + jspdf-autotable, ambos já instalados). Libs carregadas sob demanda (dynamic import)
// para não pesar o bundle. Usado pelo <ExportMenu>.
export type ExportFmt = 'xlsx' | 'csv' | 'pdf';

function baixarBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function nomeArquivo(nome: string, ext: string): string {
  const safe = (nome || 'export').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\w-]+/g, '_').replace(/^_+|_+$/g, '');
  return `${safe || 'export'}.${ext}`;
}

export async function exportarTabela(
  cols: string[], rows: string[][], nome: string, fmt: ExportFmt, titulo?: string,
): Promise<void> {
  if (fmt === 'csv') {
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const csv = [cols.map(esc).join(','), ...rows.map((r) => r.map(esc).join(','))].join('\r\n');
    baixarBlob(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }), nomeArquivo(nome, 'csv'));
    return;
  }
  if (fmt === 'xlsx') {
    const XLSX = await import('xlsx');
    const ws = XLSX.utils.aoa_to_sheet([cols, ...rows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Dados');
    const buf = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
    baixarBlob(
      new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
      nomeArquivo(nome, 'xlsx'),
    );
    return;
  }
  // pdf — jspdf + autotable (mesmo padrão do clássico)
  const [{ default: jsPDF }, { default: autoTable }] = await Promise.all([
    import('jspdf'),
    import('jspdf-autotable'),
  ]);
  const doc = new jsPDF({ orientation: cols.length > 5 ? 'landscape' : 'portrait', unit: 'pt', format: 'a4' });
  let startY = 40;
  if (titulo) {
    doc.setFontSize(13); doc.setTextColor(22, 39, 125); doc.text(titulo, 40, 30); startY = 46;
  }
  autoTable(doc, {
    head: [cols], body: rows, startY,
    styles: { fontSize: 8, cellPadding: 3 },
    headStyles: { fillColor: [22, 39, 125], textColor: 255 },
    alternateRowStyles: { fillColor: [244, 247, 252] },
    margin: { left: 40, right: 40 },
  });
  baixarBlob(doc.output('blob'), nomeArquivo(nome, 'pdf'));
}
