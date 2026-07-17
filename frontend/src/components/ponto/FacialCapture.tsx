'use client';

/**
 * Componente de captura facial para batida de ponto.
 * Usa face-api.js para deteccao e reconhecimento.
 */
import React, { useState, useCallback, useEffect } from 'react';
import { Camera, CheckCircle, XCircle, Loader2, RotateCcw } from 'lucide-react';
import { useFaceDetection } from '@/hooks/useFaceDetection';
import type { FaceDetectionResult } from '@/hooks/useFaceDetection';

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

type CaptureStatus = 'idle' | 'loading' | 'ready' | 'capturing' | 'success' | 'failed' | 'error';

export function FacialCapture({
  employeeDescriptor,
  onCapture,
  onError,
  threshold = 0.6,
  maxAttempts = 3,
}: FacialCaptureProps): React.JSX.Element {
  const [status, setStatus] = useState<CaptureStatus>('idle');
  const [attempts, setAttempts] = useState<number>(0);
  const [message, setMessage] = useState<string>('Clique para iniciar');

  const {
    isLoading,
    isReady,
    error,
    result,
    videoRef,
    canvasRef,
    startCamera,
    stopCamera,
    captureAndDetect,
    compareFaces,
  } = useFaceDetection({ minConfidence: 0.5 });

  useEffect((): void => {
    if (isLoading) {
      setStatus('loading');
      setMessage('Carregando modelos de reconhecimento...');
    } else if (error) {
      setStatus('error');
      setMessage(error);
      onError?.(error);
    } else if (isReady && status === 'loading') {
      setStatus('ready');
      setMessage('Pronto. Clique para iniciar camera.');
    }
  }, [isLoading, isReady, error, status, onError]);

  const handleStart = useCallback(async (): Promise<void> => {
    try {
      setStatus('capturing');
      setMessage('Iniciando camera...');
      await startCamera();
      setMessage('Posicione seu rosto no centro da tela');
    } catch (err: unknown) {
      setStatus('error');
      const msg = err instanceof Error ? err.message : 'Erro ao iniciar camera';
      setMessage(msg);
      onError?.(msg);
    }
  }, [startCamera, onError]);

  const handleCapture = useCallback(async (): Promise<void> => {
    if (status !== 'capturing') return;

    setMessage('Detectando face...');
    const detection: FaceDetectionResult | null = await captureAndDetect();

    if (!detection || !detection.detected) {
      setAttempts((prev) => prev + 1);
      if (attempts + 1 >= maxAttempts) {
        setStatus('failed');
        setMessage('Nao foi possivel detectar seu rosto. Tente novamente.');
        stopCamera();
        return;
      }
      setMessage(`Face nao detectada. Tentativa ${attempts + 1}/${maxAttempts}`);
      return;
    }

    let matched = true;
    let distance = 0;

    if (employeeDescriptor && detection.descriptor) {
      distance = compareFaces(detection.descriptor, employeeDescriptor);
      matched = distance < threshold;
    }

    // Capturar imagem do video
    const canvas = document.createElement('canvas');
    if (videoRef.current) {
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx?.drawImage(videoRef.current, 0, 0);
    }
    const imageData: string = canvas.toDataURL('image/jpeg', 0.8);

    const captureResult: FacialCaptureResult = {
      success: true,
      matched,
      confidence: detection.confidence,
      distance,
      imageData,
      timestamp: new Date().toISOString(),
      descriptor: detection.descriptor ? Array.from(detection.descriptor) : [],
    };

    if (matched) {
      setStatus('success');
      setMessage('Face reconhecida com sucesso!');
    } else {
      setStatus('failed');
      setMessage('Face nao corresponde ao cadastro');
    }

    stopCamera();
    onCapture(captureResult);
  }, [
    status, attempts, maxAttempts, employeeDescriptor, threshold,
    captureAndDetect, compareFaces, stopCamera, onCapture, videoRef,
  ]);

  const handleReset = useCallback((): void => {
    setStatus('ready');
    setAttempts(0);
    setMessage('Pronto. Clique para iniciar camera.');
    stopCamera();
  }, [stopCamera]);

  const getBorderColor = (): string => {
    switch (status) {
      case 'success': return 'border-green-500 bg-green-50';
      case 'failed':
      case 'error': return 'border-red-500 bg-red-50';
      case 'capturing': return 'border-blue-500 bg-blue-50';
      default: return 'border-gray-300 bg-gray-100';
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <div className={`relative rounded-lg overflow-hidden border-4 ${getBorderColor()}`}>
        <video
          ref={videoRef}
          className="w-full h-64 object-cover"
          autoPlay
          muted
          playsInline
          style={{ display: status === 'capturing' ? 'block' : 'none' }}
        />
        <canvas
          ref={canvasRef}
          className="absolute top-0 left-0 w-full h-64"
          style={{ display: status === 'capturing' ? 'block' : 'none' }}
        />

        {status !== 'capturing' && (
          <div className="w-full h-64 flex items-center justify-center">
            <div className="text-center">
              {status === 'loading' && <Loader2 className="w-12 h-12 animate-spin text-blue-500 mx-auto mb-4" />}
              {status === 'success' && <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />}
              {(status === 'failed' || status === 'error') && <XCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />}
              {(status === 'idle' || status === 'ready') && <Camera className="w-16 h-16 text-gray-400 mx-auto mb-4" />}
            </div>
          </div>
        )}
      </div>

      <p className="text-center mt-4 text-gray-700 font-medium">{message}</p>

      <div className="mt-4 flex gap-2 justify-center">
        {(status === 'idle' || status === 'ready') && (
          <button
            onClick={handleStart}
            disabled={!isReady}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            <Camera className="w-5 h-5 inline mr-2" />
            Iniciar Captura
          </button>
        )}

        {status === 'capturing' && (
          <button
            onClick={handleCapture}
            className="px-6 py-3 bg-green-600 text-white rounded-lg font-medium hover:bg-green-700 transition-colors animate-pulse"
          >
            Capturar Face
          </button>
        )}

        {(status === 'success' || status === 'failed' || status === 'error') && (
          <button
            onClick={handleReset}
            className="px-6 py-3 bg-gray-600 text-white rounded-lg font-medium hover:bg-gray-700 transition-colors"
          >
            <RotateCcw className="w-5 h-5 inline mr-2" />
            Tentar Novamente
          </button>
        )}
      </div>

      {result && result.detected && (
        <div className="mt-4 text-center text-sm text-gray-600">
          Confianca: {(result.confidence * 100).toFixed(1)}%
        </div>
      )}
    </div>
  );
}

export type { FacialCaptureProps, FacialCaptureResult };
