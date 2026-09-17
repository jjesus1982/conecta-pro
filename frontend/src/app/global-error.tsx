'use client';

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html>
      <body style={{ padding: '40px', fontFamily: 'system-ui, sans-serif', background: '#f8fafc', color: '#1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <div style={{ textAlign: 'center', maxWidth: '400px' }}>
          <h1 style={{ fontSize: '24px', fontWeight: 600, marginBottom: '8px' }}>Algo deu errado</h1>
          <p style={{ color: '#64748b', marginBottom: '24px' }}>
            Ocorreu um erro inesperado. Tente novamente ou volte para a página inicial.
          </p>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
            <button
              onClick={reset}
              style={{ padding: '10px 24px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 500 }}
            >
              Tentar novamente
            </button>
            <a
              href="/redesign"
              style={{ padding: '10px 24px', background: '#e2e8f0', color: '#1e293b', border: 'none', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', fontWeight: 500, textDecoration: 'none' }}
            >
              Ir ao Dashboard
            </a>
          </div>
        </div>
      </body>
    </html>
  );
}
