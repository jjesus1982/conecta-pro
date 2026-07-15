"use client";

import { useEffect, useRef, useState } from "react";
import { BrowserMultiFormatReader } from "@zxing/browser";
import { BarcodeFormat, DecodeHintType } from "@zxing/library";

/**
 * Scanner de câmera para pagamentos: lê QR Code (PIX copia-e-cola) e código de
 * barras (boleto — Interleaved 2 of 5 / Code128). Ao detectar, chama onDetect com
 * o texto e o formato ("qr" | "barcode"). Requer HTTPS (erp.conectamais.pro tem).
 */
export default function ScannerPagamento({
  onDetect,
  onClose,
}: {
  onDetect: (texto: string, formato: "qr" | "barcode") => void;
  onClose: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [erro, setErro] = useState<string>("");
  const [status, setStatus] = useState<string>("Iniciando câmera…");

  useEffect(() => {
    const hints = new Map();
    hints.set(DecodeHintType.POSSIBLE_FORMATS, [
      BarcodeFormat.QR_CODE,
      BarcodeFormat.ITF, // boleto (Interleaved 2 of 5)
      BarcodeFormat.CODE_128,
    ]);
    hints.set(DecodeHintType.TRY_HARDER, true); // leitura mais robusta do código de barras do boleto
    // Continuous scan + hint de leitura assumindo o código sempre presente ajuda barras finas
    hints.set(DecodeHintType.ASSUME_GS1, false);
    const reader = new BrowserMultiFormatReader(hints, { delayBetweenScanAttempts: 100 });
    let controls: { stop: () => void } | null = null;
    let parado = false;

    // Alta resolução é essencial pro código de barras do boleto (barras finas).
    const constraints: MediaStreamConstraints = {
      video: {
        facingMode: { ideal: "environment" }, // prefere traseira (celular); no Mac cai na frontal
        width: { ideal: 1920 },
        height: { ideal: 1080 },
        // @ts-expect-error focusMode não está na tipagem padrão, mas ajuda quando suportado
        advanced: [{ focusMode: "continuous" }],
      },
    };

    (async () => {
      try {
        controls = await reader.decodeFromConstraints(
          constraints,
          videoRef.current!,
          (result) => {
            if (result && !parado) {
              parado = true;
              const fmt = result.getBarcodeFormat();
              const tipo = fmt === BarcodeFormat.QR_CODE ? "qr" : "barcode";
              try { controls?.stop(); } catch { /* */ }
              onDetect(result.getText(), tipo);
            }
          }
        );
        setStatus("QR Code (PIX): centralize. Boleto: preencha a largura com o código de barras, bem focado.");
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (/permission|denied|notallowed/i.test(msg)) {
          setErro("Permissão de câmera negada. Autorize a câmera no navegador e tente de novo.");
        } else if (/notfound|no.*device/i.test(msg)) {
          setErro("Nenhuma câmera encontrada neste dispositivo.");
        } else {
          setErro("Não foi possível abrir a câmera: " + msg);
        }
      }
    })();

    return () => {
      parado = true;
      try { controls?.stop(); } catch { /* */ }
    };
  }, [onDetect]);

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-md p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold text-[#0A2540]">Escanear pagamento</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl leading-none">×</button>
        </div>

        {erro ? (
          <div className="text-sm text-red-600 py-8 text-center">{erro}</div>
        ) : (
          <>
            <div className="relative rounded-lg overflow-hidden bg-black aspect-video">
              <video ref={videoRef} className="w-full h-full object-cover" muted playsInline />
              {/* guia larga p/ código de barras do boleto (e serve pro QR também) */}
              <div className="pointer-events-none absolute inset-x-4 top-1/2 -translate-y-1/2 h-16 border-2 border-white/70 rounded" />
            </div>
            <p className="text-xs text-gray-500 mt-2 text-center">{status}</p>
          </>
        )}

        <div className="mt-3 flex justify-end">
          <button
            onClick={onClose}
            className="text-sm border border-gray-300 text-gray-700 px-4 py-1.5 rounded-lg hover:bg-gray-100"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
