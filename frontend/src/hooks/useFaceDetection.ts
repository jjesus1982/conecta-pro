'use client';

/**
 * Hook para deteccao e reconhecimento facial usando face-api.js
 * Usado no modulo de Ponto Eletronico para batida facial
 */
import { useState, useEffect, useRef, useCallback } from 'react';

interface FaceDetectionResult {
  detected: boolean;
  confidence: number;
  descriptor: Float32Array | null;
  boundingBox: {
    x: number;
    y: number;
    width: number;
    height: number;
  } | null;
}

interface UseFaceDetectionOptions {
  minConfidence?: number;
  inputSize?: number;
  scoreThreshold?: number;
}

interface UseFaceDetectionReturn {
  isLoading: boolean;
  isReady: boolean;
  error: string | null;
  result: FaceDetectionResult | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  canvasRef: React.RefObject<HTMLCanvasElement | null>;
  startCamera: () => Promise<void>;
  stopCamera: () => void;
  captureAndDetect: () => Promise<FaceDetectionResult | null>;
  compareFaces: (descriptor1: Float32Array, descriptor2: Float32Array) => number;
}

const DEFAULT_OPTIONS: UseFaceDetectionOptions = {
  minConfidence: 0.5,
  inputSize: 416,
  scoreThreshold: 0.5,
};

export function useFaceDetection(
  options: UseFaceDetectionOptions = {}
): UseFaceDetectionReturn {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isReady, setIsReady] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FaceDetectionResult | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const faceapiRef = useRef<typeof import('face-api.js') | null>(null);

  // Carregar modelos do face-api.js (dynamic import para SSR safety)
  useEffect(() => {
    const loadModels = async (): Promise<void> => {
      try {
        setIsLoading(true);
        setError(null);

        const faceapi = await import('face-api.js');
        faceapiRef.current = faceapi;

        const MODEL_URL = '/models';

        await Promise.all([
          faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
          faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
          faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
        ]);

        setIsReady(true);
        setIsLoading(false);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Erro ao carregar modelos';
        setError(message);
        setIsLoading(false);
      }
    };

    loadModels();

    return () => {
      stopCamera();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startCamera = useCallback(async (): Promise<void> => {
    try {
      // iOS (Safari e Chrome, ambos WebKit) e Android exigem HTTPS + getUserMedia.
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          'Este navegador não abre a câmera. No iPhone use o Safari ou o Chrome; ' +
          'evite abrir por um link dentro do WhatsApp/Instagram.',
        );
      }

      // facingMode 'user' (frontal) e resolução 'ideal' (não 'exact') p/ máxima
      // compatibilidade — iOS rejeita constraints exatas.
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
      });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        streamRef.current = stream;
        await videoRef.current.play();
      }
    } catch (err: unknown) {
      const name = (err as { name?: string })?.name;
      let message: string;
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        message =
          'Câmera bloqueada. Toque no “aA”/cadeado na barra de endereço e permita a câmera. ' +
          'Se abriu por um link do WhatsApp/Instagram, abra no Safari (iPhone) ou Chrome (Android).';
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        message = 'Nenhuma câmera frontal encontrada neste aparelho.';
      } else if (name === 'NotReadableError' || name === 'AbortError') {
        message = 'A câmera está em uso por outro app. Feche os outros apps e tente de novo.';
      } else {
        message = err instanceof Error && err.message ? err.message : 'Não foi possível abrir a câmera. Tente novamente.';
      }
      setError(message);
      throw new Error(message);
    }
  }, []);

  const stopCamera = useCallback((): void => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  const captureAndDetect = useCallback(async (): Promise<FaceDetectionResult | null> => {
    const faceapi = faceapiRef.current;
    if (!videoRef.current || !isReady || !faceapi) {
      return null;
    }

    try {
      const detection = await faceapi
        .detectSingleFace(
          videoRef.current,
          new faceapi.TinyFaceDetectorOptions({
            inputSize: opts.inputSize,
            scoreThreshold: opts.scoreThreshold,
          })
        )
        .withFaceLandmarks()
        .withFaceDescriptor();

      if (!detection) {
        const noFace: FaceDetectionResult = {
          detected: false,
          confidence: 0,
          descriptor: null,
          boundingBox: null,
        };
        setResult(noFace);
        return noFace;
      }

      const faceResult: FaceDetectionResult = {
        detected: true,
        confidence: detection.detection.score,
        descriptor: detection.descriptor,
        boundingBox: {
          x: detection.detection.box.x,
          y: detection.detection.box.y,
          width: detection.detection.box.width,
          height: detection.detection.box.height,
        },
      };

      setResult(faceResult);

      // Desenhar no canvas
      if (canvasRef.current && videoRef.current) {
        const canvas = canvasRef.current;
        const displaySize = {
          width: videoRef.current.videoWidth,
          height: videoRef.current.videoHeight,
        };
        faceapi.matchDimensions(canvas, displaySize);
        const resized = faceapi.resizeResults(detection, displaySize);
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          faceapi.draw.drawDetections(canvas, [resized]);
          faceapi.draw.drawFaceLandmarks(canvas, [resized]);
        }
      }

      return faceResult;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro na deteccao';
      setError(message);
      return null;
    }
  }, [isReady, opts.inputSize, opts.scoreThreshold]);

  const compareFaces = useCallback(
    (descriptor1: Float32Array, descriptor2: Float32Array): number => {
      const faceapi = faceapiRef.current;
      if (!faceapi) return 1.0;
      return faceapi.euclideanDistance(descriptor1, descriptor2);
    },
    []
  );

  return {
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
  };
}

export type { FaceDetectionResult, UseFaceDetectionOptions };
