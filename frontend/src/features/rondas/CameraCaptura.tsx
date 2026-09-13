'use client';

/**
 * Captura de foto PELA CÂMERA (getUserMedia + canvas) — frente 6.
 *
 * `<input capture>` é dica, não trava: em vários aparelhos a galeria continua disponível.
 * Aqui a única fonte para item com foto obrigatória é o vídeo da câmera, quadro congelado
 * no canvas e comprimido (≤1280px, JPEG 0,7) ANTES de qualquer envio/fila. A galeria só
 * aparece quando `permitirGaleria` e a foto vinda de lá é marcada `capturada_na_hora=false`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Camera, ImagePlus, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { comprimirImagem, type FotoLocal } from './filaOffline';

interface Props {
  fotos: FotoLocal[];
  onChange: (fotos: FotoLocal[]) => void;
  max: number;
  obrigatoria: boolean;
  permitirGaleria?: boolean;
  disabled?: boolean;
}

export function CameraCaptura({ fotos, onChange, max, obrigatoria, permitirGaleria = false, disabled }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const galeriaRef = useRef<HTMLInputElement | null>(null);
  const [aberta, setAberta] = useState(false);
  const [abrindo, setAbrindo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const fechar = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setAberta(false);
  }, []);

  useEffect(() => fechar, [fechar]); // desmontou → solta a câmera

  const abrir = useCallback(async () => {
    setErro(null);
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setErro('Este navegador não dá acesso à câmera. Use o Chrome/Safari atualizado com HTTPS.');
      return;
    }
    setAbrindo(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 1280 } },
        audio: false,
      });
      streamRef.current = stream;
      setAberta(true);
      // o <video> só existe depois do setAberta — liga no próximo tick
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => undefined);
        }
      }, 0);
    } catch (e) {
      setErro(
        e instanceof DOMException && e.name === 'NotAllowedError'
          ? 'Permissão de câmera negada. Libere a câmera para este site e tente de novo.'
          : 'Câmera indisponível neste aparelho.'
      );
    } finally {
      setAbrindo(false);
    }
  }, []);

  const capturar = useCallback(async () => {
    const v = videoRef.current;
    if (!v || v.videoWidth === 0) return;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d')?.drawImage(v, 0, 0);
    const bmp = await createImageBitmap(canvas);
    const blob = await comprimirImagem(bmp);
    onChange([...fotos, { blob, capturada_na_hora: true, hora_aparelho: new Date().toISOString() }]);
    fechar();
  }, [fotos, onChange, fechar]);

  const daGaleria = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const arquivos = Array.from(e.target.files ?? []).slice(0, Math.max(0, max - fotos.length));
      e.target.value = '';
      const novas: FotoLocal[] = [];
      for (const f of arquivos) {
        try {
          novas.push({ blob: await comprimirImagem(f), capturada_na_hora: false, hora_aparelho: new Date().toISOString() });
        } catch {
          setErro(`"${f.name}" não pôde ser lida como imagem.`);
        }
      }
      if (novas.length) onChange([...fotos, ...novas]);
    },
    [fotos, max, onChange]
  );

  const previews = useMemo(() => fotos.map((f) => URL.createObjectURL(f.blob)), [fotos]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  const temProva = fotos.some((f) => f.capturada_na_hora);
  const cheio = fotos.length >= max;

  return (
    <div className="space-y-2">
      <span className="block text-xs font-medium text-muted-foreground">
        {obrigatoria ? 'Foto pela câmera * (obrigatória, tirada agora)' : 'Fotos (opcional)'} — {fotos.length}/{max}
      </span>

      {aberta ? (
        <div className="space-y-2">
          <video ref={videoRef} playsInline muted autoPlay className="w-full rounded-lg bg-black" />
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="h-12 flex-1" onClick={fechar}>
              Cancelar
            </Button>
            <Button type="button" className="h-12 flex-1" onClick={capturar}>
              <Camera className="mr-2 h-5 w-5" /> Tirar foto
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button
            type="button"
            variant={obrigatoria && !temProva ? 'default' : 'outline'}
            className="h-12 flex-1"
            onClick={abrir}
            disabled={disabled || cheio || abrindo}
          >
            {abrindo ? <Loader2 className="h-5 w-5 animate-spin" /> : <Camera className="mr-2 h-5 w-5" />}
            {abrindo ? '' : 'Abrir câmera'}
          </Button>
          {permitirGaleria && (
            <>
              <input ref={galeriaRef} type="file" accept="image/*" multiple className="hidden" onChange={daGaleria} />
              <Button
                type="button"
                variant="outline"
                className="h-12"
                onClick={() => galeriaRef.current?.click()}
                disabled={disabled || cheio}
                aria-label="Anexar da galeria (não vale como prova)"
              >
                <ImagePlus className="h-5 w-5" />
              </Button>
            </>
          )}
        </div>
      )}

      {erro && <p className="text-xs text-red-600">{erro}</p>}
      {obrigatoria && !temProva && !erro && (
        <p className="text-xs text-amber-700">Sem foto da câmera este item não fecha — a galeria não vale.</p>
      )}

      {previews.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {previews.map((url, idx) => (
            <div key={url} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element -- preview local (blob) */}
              <img src={url} alt={`Foto ${idx + 1}`} className="h-16 w-16 rounded-md object-cover" />
              {!fotos[idx]?.capturada_na_hora && (
                <span className="absolute bottom-0 left-0 rounded-tr bg-black/60 px-1 text-[9px] text-white">galeria</span>
              )}
              <button
                type="button"
                onClick={() => onChange(fotos.filter((_, i) => i !== idx))}
                disabled={disabled}
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-red-600 text-white"
                aria-label={`Remover foto ${idx + 1}`}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
