'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import api, { getErrorMessage } from '@/lib/api';

interface User {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  phone?: string;
  permissions?: string[];
  employee_id?: string | null;
  created_at?: string;
  updated_at?: string;
  last_login?: string;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface LoginCredentials {
  email: string;
  password: string;
}

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export function useAuth() {
  const router = useRouter();
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });
  // Singleton guard — evita múltiplas chamadas simultâneas de checkAuth
  const isCheckingRef = useRef(false);

  // Verificar autenticação ao montar
  useEffect(() => {
    const checkAuth = async () => {
      if (isCheckingRef.current) return;
      isCheckingRef.current = true;

      const token = localStorage.getItem('access_token');

      if (!token) {
        setState({ user: null, isLoading: false, isAuthenticated: false });
        isCheckingRef.current = false;
        return;
      }

      try {
        const res = await fetch('/api/v1/auth/me', {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        });

        if (res.status === 401 || res.status === 403) {
          // Tentar refresh antes de deslogar
          const refreshToken = localStorage.getItem('refresh_token');
          if (refreshToken) {
            try {
              const refreshRes = await fetch('/api/v1/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
              });
              if (refreshRes.ok) {
                const { access_token, refresh_token: newRefresh } = await refreshRes.json();
                localStorage.setItem('access_token', access_token);
                if (newRefresh) localStorage.setItem('refresh_token', newRefresh);
                // Atualizar cookie com o novo token
                const isSecure = window.location.protocol === 'https:';
                document.cookie = `auth_token=${access_token}; path=/; max-age=${30 * 60}; SameSite=Lax${isSecure ? '; Secure' : ''}`;
                // Buscar dados do usuário com o novo token
                const meRes = await fetch('/api/v1/auth/me', {
                  headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
                });
                if (meRes.ok) {
                  const userData: User = await meRes.json();
                  setState({ user: userData, isLoading: false, isAuthenticated: true });
                  isCheckingRef.current = false;
                  return;
                }
              }
            } catch {
              // Refresh falhou — continua para logout
            }
          }
          // Sem refresh ou refresh falhou
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          document.cookie = 'auth_token=; path=/; max-age=0';
          setState({ user: null, isLoading: false, isAuthenticated: false });
          isCheckingRef.current = false;
          return;
        }

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const userData: User = await res.json();
        // Renovar cookie para garantir que o middleware veja o token válido
        const isSecure = window.location.protocol === 'https:';
        document.cookie = `auth_token=${token}; path=/; max-age=${30 * 60}; SameSite=Lax${isSecure ? '; Secure' : ''}`;
        setState({
          user: userData,
          isLoading: false,
          isAuthenticated: true,
        });
      } catch {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        setState({ user: null, isLoading: false, isAuthenticated: false });
      } finally {
        isCheckingRef.current = false;
      }
    };

    checkAuth();
  }, []);

  // Login
  const login = useCallback(async (credentials: LoginCredentials): Promise<{ success: boolean; error?: string }> => {
    try {
      setState(prev => ({ ...prev, isLoading: true }));

      // Backend usa form-urlencoded com 'username' em vez de JSON com 'email'
      const formData = new URLSearchParams();
      formData.append('username', credentials.email);
      formData.append('password', credentials.password);

      const response = await api.post<LoginResponse>('/api/v1/auth/login', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });
      const { access_token, refresh_token } = response.data;

      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);

      // Sincronizar cookie para o middleware de rota
      // Secure flag só em HTTPS — em HTTP seria silenciosamente descartado pelo browser
      const isSecure = window.location.protocol === 'https:';
      document.cookie = `auth_token=${access_token}; path=/; max-age=${30 * 60}; SameSite=Lax${isSecure ? '; Secure' : ''}`;

      // Buscar dados do usuário após login (via proxy local — consistente com checkAuth)
      const meRes = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
      });
      const userData: User = meRes.ok ? await meRes.json() : { id: '', email: credentials.email, name: '', role: 'user', is_active: true };

      setState({
        user: userData,
        isLoading: false,
        isAuthenticated: true,
      });

      return { success: true };
    } catch (error) {
      setState(prev => ({ ...prev, isLoading: false }));
      return { success: false, error: getErrorMessage(error) };
    }
  }, []);

  // Logout
  const logout = useCallback(async () => {
    try {
      await api.post('/api/v1/auth/logout');
    } catch {
      // Ignorar erro de logout
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      document.cookie = 'auth_token=; path=/; max-age=0';
      setState({ user: null, isLoading: false, isAuthenticated: false });
      router.push('/login');
    }
  }, [router]);

  return {
    ...state,
    login,
    logout,
  };
}
