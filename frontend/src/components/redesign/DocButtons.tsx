'use client';

// DocButtons — fundação de documentos do REDESIGN. Renderiza, para cada documento declarado
// pela tela (scr.docs) ou pela linha (row.docs), um chip com "Abrir" (HTML/nova aba) e "Baixar".
// Documentos indisponíveis (stub/placeholder/sem transmissão real) aparecem desabilitados com
// tooltip honesto — NUNCA um botão que abre lixo. Ver src/lib/docsource.ts.
import { Download, Eye, FileText, FileSpreadsheet, FileArchive, FileCode } from 'lucide-react';
import { abrirDoc, baixarDoc, isAbrivel, type DocRef } from '@/lib/docsource';

function IcoFor({ fmt, size = 13 }: { fmt?: string; size?: number }) {
  const C = fmt === 'xlsx' || fmt === 'csv' ? FileSpreadsheet
    : fmt === 'zip' ? FileArchive
      : fmt === 'xml' ? FileCode
        : FileText;
  return <C size={size} style={{ flex: 'none', opacity: 0.85 }} />;
}

const chipBase: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 8px',
  border: '1px solid var(--line, #E2E8F0)', borderRadius: 8, background: 'var(--fill, #F8FAFC)',
  fontSize: 12, color: 'var(--ink, #0F1B3A)', lineHeight: 1.4,
};
// minHeight 32px: medido em 14/08 no navegador, estes botões tinham 22px de altura e
// aparecem 102 vezes numa tela só (Rondas). Apple recomenda 44 e Material 48, mas
// empilhar 102 botões de 44px mudaria o desenho da tabela — 32 tira do risco de errar
// o toque sem redesenhar a tela.
const actBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 3,
  padding: '4px 8px', minHeight: 32, borderRadius: 6,
  border: '1px solid transparent', background: 'transparent', cursor: 'pointer',
  color: 'var(--navy, #16277D)', fontSize: 12, fontWeight: 600,
};

export function DocButtons({ docs, compact = false }: { docs: DocRef[]; compact?: boolean }) {
  if (!Array.isArray(docs) || docs.length === 0) return null;
  return (
    <div className="rd-docs" style={{ display: 'flex', flexWrap: 'wrap', gap: compact ? 6 : 8, alignItems: 'center' }}>
      {docs.map((doc, i) => {
        if (doc.disabled) {
          return (
            <span key={i} className="rd-doc-chip rd-doc-off" title={doc.motivo || 'Documento indisponível'}
              style={{ ...chipBase, opacity: 0.55, cursor: 'not-allowed', background: 'transparent' }}>
              <IcoFor fmt={doc.fmt} /> <span>{doc.label}</span>
            </span>
          );
        }
        return (
          <span key={i} className="rd-doc-chip" style={chipBase} title={doc.gate ? `Acesso: ${doc.gate}` : doc.label}>
            <IcoFor fmt={doc.fmt} />
            {/* Em linha de tabela o label do doc some (é longo), mas "Abrir"/"Baixar" NUNCA:
                 sem verbo a coluna vira dois ícones mudos e ninguém acha o download. */}
            {!compact && <span style={{ fontWeight: 600 }}>{doc.label}</span>}
            {isAbrivel(doc.fmt) && (
              <button type="button" className="rd-doc-act" onClick={() => abrirDoc(doc)}
                title={`Abrir ${doc.label}`} style={actBtn}>
                <Eye size={13} /><span>Abrir</span>
              </button>
            )}
            <button type="button" className="rd-doc-act" onClick={() => baixarDoc(doc)}
              title={`Baixar ${doc.label}`} style={actBtn}>
              <Download size={13} /><span>Baixar</span>
            </button>
          </span>
        );
      })}
    </div>
  );
}
