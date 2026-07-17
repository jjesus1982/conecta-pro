'use client';

/**
 * Captura facial estilo app de banco: moldura OVAL/redonda, detecção CONTÍNUA e
 * captura AUTOMÁTICA quando o rosto está enquadrado (sem botão manual). Feedback ao
 * vivo (anel muda de cor). Usa face-api.js (useFaceDetection).
 *
 * - Modo CADASTRO (sem employeeDescriptor): captura ao detectar rosto nítido.
 * - Modo BATIDA (com employeeDescriptor): captura ao detectar E reconhecer (distância
 *   < threshold). Após N frames com rosto detectado mas sem match → "não reconhecido".
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Camera, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { useFaceDetection } from '@/hooks/useFaceDetection';

export interface FacialCaptureResult {
  success: boolean;
  matched: boolean;
  confidence: number;
  distance: number;
  imageData: string;
  timestamp: string;
  /** Descriptor de 128 floats do rosto capturado (para cadastro de referência). */
  descriptor: number[];
}

interface FacialCaptureProps {
  employeeDescriptor?: Float32Array;
  onCapture: (result: FacialCaptureResult) => void;
  onError?: (error: string) => void;
  threshold?: number;
  maxAttempts?: number;
}

type Status = 'idle' | 'loading' | 'starting' | 'scanning' | 'success' | 'failed' | 'error';

export function FacialCapture({
  employeeDescriptor,
  onCapture,
  onError,
  threshold = 0.68,
  maxAttempts = 12,
}: FacialCaptureProps): React.JSX.Element {
  const { isLoading, isReady, error, videoRef, startCamera, stopCamera, captureAndDetect, compareFaces } =
    useFaceDetection({ minConfidence: 0.4, inputSize: 320, scoreThreshold: 0.4 });

  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState('Toque em Iniciar');
  const [faceIn, setFaceIn] = useState(false);

  const loopRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const doneRef = useRef(false);
  const missRef = useRef(0); // frames com rosto detectado mas sem match (batida)
  const hitRef = useRef(0); // frames bons consecutivos (cadastro)

  const stopLoop = () => {
    if (loopRef.current) { clearInterval(loopRef.current); loopRef.current = null; }
  };

  useEffect(() => {
    if (isLoading) { setStatus('loading'); setMessage('Carregando reconhecimento...'); }
    else if (error) { setStatus((s) => (s === 'scanning' ? s : 'error')); }
    else if (isReady) { setStatus((s) => (s === 'loading' ? 'idle' : s)); if (message.startsWith('Carregando')) setMessage('Toque em Iniciar'); }
  }, [isLoading, isReady, error]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { stopLoop(); }, []);

  const grabFrame = (): string => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return '';
    const c = document.createElement('canvas');
    c.width = v.videoWidth; c.height = v.videoHeight;
    const ctx = c.getContext('2d');
    if (ctx) { ctx.translate(c.width, 0); ctx.scale(-1, 1); ctx.drawImage(v, 0, 0); }
    return c.toDataURL('image/jpeg', 0.8);
  };

  const finish = useCallback((res: FacialCaptureResult) => {
    if (doneRef.current) return;
    doneRef.current = true;
    stopLoop();
    stopCamera();
    onCapture(res);
  }, [onCapture, stopCamera]);

  const tick = useCallback(async () => {
    if (doneRef.current) return;
    const v = videoRef.current;
    if (!v || !v.videoWidth) return; // câmera ainda inicializando
    const det = await captureAndDetect();
    if (!det || !det.detected) {
      hitRef.current = 0; setFaceIn(false); setMessage('Centralize o rosto no círculo'); return;
    }
    setFaceIn(true);

    if (employeeDescriptor && det.descriptor) {
      // BATIDA: reconhecer
      const distance = compareFaces(det.descriptor, employeeDescriptor);
      if (distance < threshold) {
        setStatus('success'); setMessage('Rosto reconhecido!');
        finish({ success: true, matched: true, confidence: det.confidence, distance,
          imageData: grabFrame(), timestamp: new Date().toISOString(), descriptor: Array.from(det.descriptor) });
      } else {
        missRef.current += 1;
        setMessage('Segure firme, reconhecendo...');
        if (missRef.current >= maxAttempts) {
          setStatus('failed'); setMessage('Não reconheci. Tente com boa luz, de frente.');
          finish({ success: true, matched: false, confidence: det.confidence, distance,
            imageData: grabFrame(), timestamp: new Date().toISOString(), descriptor: Array.from(det.descriptor) });
        }
      }
    } else {
      // CADASTRO: capturar rosto nítido (2 frames bons seguidos)
      hitRef.current = det.confidence >= 0.5 ? hitRef.current + 1 : 0;
      setMessage(hitRef.current >= 1 ? 'Segure... capturando' : 'Centralize o rosto no círculo');
      if (hitRef.current >= 2) {
        setStatus('success'); setMessage('Rosto capturado!');
        finish({ success: true, matched: true, confidence: det.confidence, distance: 0,
          imageData: grabFrame(), timestamp: new Date().toISOString(), descriptor: Array.from(det.descriptor || []) });
      }
    }
  }, [employeeDescriptor, threshold, maxAttempts, captureAndDetect, compareFaces, finish]); // eslint-disable-line

  const begin = useCallback(async () => {
    doneRef.current = false; missRef.current = 0; hitRef.current = 0;
    setStatus('starting'); setMessage('Abrindo câmera...');
    try {
      await startCamera();
      setStatus('scanning'); setMessage('Centralize o rosto no círculo');
      stopLoop();
      loopRef.current = setInterval(() => { void tick(); }, 550);
    } catch (e: unknown) {
      const m = e instanceof Error ? e.message : 'Não foi possível abrir a câmera.';
      setStatus('error'); setMessage(m); onError?.(m);
    }
  }, [startCamera, tick, onError]);

  const videoVisible = status === 'scanning' || status === 'success' || status === 'failed';
  const ring =
    status === 'success' ? 'border-emerald-500'
    : status === 'failed' || status === 'error' ? 'border-red-500'
    : faceIn ? 'border-emerald-400' : 'border-white/70';

  return (
    <div className="w-full flex flex-col items-center">
      <div className={`relative w-64 h-64 sm:w-72 sm:h-72 rounded-full overflow-hidden border-4 ${ring} bg-black transition-colors`}>
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className="w-full h-full object-cover"
          style={{ transform: 'scaleX(-1)', display: videoVisible ? 'block' : 'none' }}
        />
        {(status === 'idle' || status === 'loading' || status === 'starting') && (
          <div className="absolute inset-0 flex items-center justify-center">
            {status === 'loading' || status === 'starting'
              ? <Loader2 className="w-10 h-10 text-white/80 animate-spin" />
              : <Camera className="w-12 h-12 text-white/60" />}
          </div>
        )}
        {status === 'success' && (
          <div className="absolute inset-0 flex items-center justify-center bg-emerald-500/25">
            <CheckCircle2 className="w-16 h-16 text-emerald-300" />
          </div>
        )}
        {status === 'failed' && (
          <div className="absolute inset-0 flex items-center justify-center bg-red-500/20">
            <XCircle className="w-16 h-16 text-red-300" />
          </div>
        )}
      </div>

      <p className="text-center mt-3 text-sm font-medium text-[hsl(var(--foreground))]">{message}</p>

      <div className="mt-3 min-h-[48px] flex items-center">
        {status === 'idle' && (
          <button
            onClick={begin}
            disabled={!isReady}
            className="px-8 py-3 rounded-xl bg-[#F97316] text-white font-semibold hover:bg-[#EA6A0A] disabled:opacity-50 flex items-center gap-2"
          >
            <Camera className="w-5 h-5" /> Iniciar
          </button>
        )}
        {status === 'scanning' && (
          <p className="text-xs text-[hsl(var(--muted-foreground))] flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Reconhecendo automaticamente…
          </p>
        )}
        {(status === 'failed' || status === 'error') && (
          <button onClick={begin} className="px-8 py-3 rounded-xl bg-[#F97316] text-white font-semibold hover:bg-[#EA6A0A]">
            Tentar de novo
          </button>
        )}
      </div>
    </div>
  );
}
