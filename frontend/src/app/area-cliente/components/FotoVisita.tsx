'use client';

/**
 * Foto de visita da gestão — imagem servida por rota AUTENTICADA do portal.
 * Baixa o arquivo via fetch com Bearer (portal_token) e exibe via objectURL.
 * NUNCA usar <img src> direto na rota (o navegador não envia o token).
 */
import { useEffect, useState } from 'react';
import { ImageOff } from 'lucide-react';

interface FotoVisitaProps {
  /** Caminho relativo retornado pela API (ex.: /api/v1/portal/operacao/visitas/...) */
  url: string;
  alt?: string;
  className?: string;
  onClick?: () => void;
}

export default function FotoVisita({ url, alt = 'Foto da visita', className = '', onClick }: FotoVisitaProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    let criado: string | null = null;
    setObjectUrl(null);
    setErro(false);
    (async () => {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}${url}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        if (!ativo) return;
        criado = URL.createObjectURL(blob);
        setObjectUrl(criado);
      } catch {
        if (ativo) setErro(true);
      }
    })();
    return () => {
      ativo = false;
      if (criado) URL.revokeObjectURL(criado);
    };
  }, [url]);

  if (erro) {
    return (
      <div
        className={`${className} min-w-[64px] min-h-[64px] bg-gray-100 flex items-center justify-center text-gray-300`}
        title="Não foi possível carregar a foto"
      >
        <ImageOff className="w-5 h-5" />
      </div>
    );
  }

  if (!objectUrl) {
    return <div className={`${className} min-w-[64px] min-h-[64px] bg-gray-200 animate-pulse`} aria-label="Carregando foto…" />;
  }

  // eslint-disable-next-line @next/next/no-img-element
  return <img src={objectUrl} alt={alt} className={className} onClick={onClick} />;
}
