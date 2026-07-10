'use client';

/**
 * Foto de checkpoint de ronda carregada de forma AUTENTICADA.
 *
 * A rota GET /api/v1/operacional/rondas/{round}/checkpoints/{cp}/fotos/{arquivo}
 * exige token — <img src> direto não leva Authorization, então baixamos via
 * axios (responseType blob) e exibimos com URL.createObjectURL.
 */

import { useEffect, useState } from 'react';
import { ImageOff, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';

const RONDAS_URL = '/api/v1/operacional/rondas';

interface CheckpointFotoProps {
  roundId: string;
  checkpointId: string;
  arquivo: string;
  alt?: string;
  className?: string;
  onClick?: () => void;
}

export function CheckpointFoto({
  roundId,
  checkpointId,
  arquivo,
  alt,
  className,
  onClick,
}: CheckpointFotoProps) {
  const [src, setSrc] = useState<string | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    let objectUrl: string | null = null;
    setSrc(null);
    setErro(false);
    api
      .get(
        `${RONDAS_URL}/${roundId}/checkpoints/${checkpointId}/fotos/${encodeURIComponent(arquivo)}`,
        { responseType: 'blob' }
      )
      .then((res) => {
        if (!ativo) return;
        objectUrl = URL.createObjectURL(res.data as Blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (ativo) setErro(true);
      });
    return () => {
      ativo = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [roundId, checkpointId, arquivo]);

  if (erro) {
    return (
      <span
        className={`flex items-center justify-center bg-gray-100 text-gray-400 ${className || ''}`}
        title={`Não foi possível carregar ${arquivo}`}
      >
        <ImageOff className="h-4 w-4" />
      </span>
    );
  }

  if (!src) {
    return (
      <span
        className={`flex animate-pulse items-center justify-center bg-gray-100 text-gray-400 ${className || ''}`}
      >
        <Loader2 className="h-4 w-4 animate-spin" />
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- blob local autenticado, next/image não se aplica
    <img
      src={src}
      alt={alt || arquivo}
      className={className}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
    />
  );
}
