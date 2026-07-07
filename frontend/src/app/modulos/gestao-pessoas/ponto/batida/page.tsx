'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import {
  Fingerprint,
  Camera,
  MapPin,
  CheckCircle2,
  Clock,
  Wifi,
  WifiOff,
  Loader2,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

interface PunchRecord {
  id?: number | string;
  tipo?: string;
  type?: string;
  hora?: string;
  timestamp?: string;
  local?: string;
  location?: string;
}

interface BatidaPayload {
  latitude?: number;
  longitude?: number;
}

export default function BaterPontoPage() {
  const queryClient = useQueryClient();
  const [punched, setPunched] = useState(false);
  const [geoEnabled, setGeoEnabled] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => { setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }); setGeoEnabled(true); },
        () => { setGeoEnabled(false); },
      );
    } else {
      setGeoEnabled(false);
    }
  }, []);

  // Fetch today's punches — backend resolves employee from auth
  const { data: todayPunches, isLoading: loadingPunches } = useQuery<PunchRecord[]>({
    queryKey: ['ponto', 'batidas', 'hoje'],
    queryFn: async () => {
      try {
        const res = await customInstance({ url: '/api/v1/people-management/ponto/batidas/me' }) as unknown as { batidas?: PunchRecord[]; items?: PunchRecord[] } | PunchRecord[];
        if (Array.isArray(res)) return res;
        return (res as Record<string, unknown>)?.batidas as PunchRecord[] ?? (res as Record<string, unknown>)?.items as PunchRecord[] ?? [];
      } catch (err) {
        console.error('fetchTodayPunches:', err);
        return [];
      }
    },
    staleTime: 10000,
    retry: 1,
  });

  const punchMutation = useMutation({
    mutationFn: (body: BatidaPayload) => {
      // Build query string for optional GPS coords
      const params = new URLSearchParams();
      if (body.latitude != null) params.set('latitude', String(body.latitude));
      if (body.longitude != null) params.set('longitude', String(body.longitude));
      const qs = params.toString();
      return customInstance({
        url: `/api/v1/people-management/ponto/batida/me${qs ? '?' + qs : ''}`,
        method: 'POST',
      });
    },
    onSuccess: () => {
      setPunched(true);
      setTimeout(() => setPunched(false), 3000);
      queryClient.invalidateQueries({ queryKey: ['ponto', 'batidas'] });
    },
  });

  function handlePunch() {
    const payload: BatidaPayload = {};
    if (coords) {
      payload.latitude = coords.lat;
      payload.longitude = coords.lng;
    }
    punchMutation.mutate(payload);
  }

  const punches = todayPunches ?? [];
  const punching = punchMutation.isPending;

  return (
    <div className="p-6 space-y-6 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-2">
        <Fingerprint className="w-6 h-6 text-blue-500" />
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Bater Ponto</h1>
      </div>

      {punchMutation.isError && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-500 px-4 py-3 rounded-lg text-sm">
          {(() => {
            const err = punchMutation.error as any;
            const detail = err?.response?.data?.detail || err?.message || 'Erro desconhecido';
            if (detail.includes('não encontrado') || detail.includes('not found')) {
              return 'Seu usuário não está vinculado a um funcionário. Verifique se o e-mail do seu login é o mesmo cadastrado no seu perfil de funcionário.';
            }
            return `Erro ao registrar batida: ${detail}`;
          })()}
        </div>
      )}

      <Card className="border border-[hsl(var(--border))]">
        <CardContent className="p-8 flex flex-col items-center">
          <p className="font-data tabular-nums text-5xl font-bold text-[hsl(var(--foreground))] mb-2">{currentTime}</p>
          <p className="text-sm text-[hsl(var(--muted-foreground))] mb-8">
            {new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' })}
          </p>

          <button
            onClick={handlePunch}
            disabled={punching}
            className={`w-40 h-40 rounded-full flex flex-col items-center justify-center gap-2 text-white font-bold text-lg transition-all duration-300 shadow-lg ${
              punched
                ? 'bg-green-500 scale-95'
                : punching
                ? 'bg-blue-400 animate-pulse scale-105'
                : 'bg-blue-600 hover:bg-blue-700 hover:scale-105 active:scale-95'
            }`}
          >
            {punched ? (
              <>
                <CheckCircle2 className="w-10 h-10" />
                <span className="text-sm">Registrado!</span>
              </>
            ) : (
              <>
                {punching ? <Loader2 className="w-10 h-10 animate-spin" /> : <Camera className="w-10 h-10" />}
                <span className="text-sm">{punching ? 'Registrando...' : 'Bater Ponto'}</span>
              </>
            )}
          </button>

          <div className="mt-8 flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              {geoEnabled ? (
                <MapPin className="h-4 w-4 text-green-500" />
              ) : (
                <MapPin className="h-4 w-4 text-red-500" />
              )}
              <span className={geoEnabled ? 'text-emerald-500' : 'text-red-500'}>
                {geoEnabled ? 'GPS Ativo' : 'GPS Inativo'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Wifi className="h-4 w-4 text-emerald-500" />
              <span className="text-emerald-500">Online</span>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-[hsl(var(--border))]">
        <CardContent className="p-4">
          <h2 className="text-sm font-semibold text-[hsl(var(--foreground))] mb-3">Batidas de Hoje</h2>
          {loadingPunches ? (
            <div className="flex justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-[hsl(var(--muted-foreground))]" />
            </div>
          ) : (
            <div className="space-y-3">
              {punches.length === 0 ? (
                <p className="text-sm text-[hsl(var(--muted-foreground))] text-center py-4">Nenhuma batida registrada hoje</p>
              ) : (
                punches.map((punch, idx) => (
                  <div key={punch.id ?? idx} className="flex items-center justify-between py-2 border-b border-[hsl(var(--border))] last:border-0">
                    <div className="flex items-center gap-3">
                      <Clock className="h-4 w-4 text-[hsl(var(--muted-foreground))]" />
                      <div>
                        <p className="text-sm font-medium text-[hsl(var(--foreground))]">{punch.tipo || punch.type || `Batida ${idx + 1}`}</p>
                        <p className="text-xs text-[hsl(var(--muted-foreground))]">{punch.local || punch.location || ''}</p>
                      </div>
                    </div>
                    <span className="font-data tabular-nums text-sm font-medium text-[hsl(var(--foreground))]">{punch.hora || punch.timestamp || '--:--'}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
