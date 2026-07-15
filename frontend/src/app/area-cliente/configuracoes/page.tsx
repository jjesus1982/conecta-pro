'use client';

import React, { useEffect, useState, FormEvent } from 'react';
import { msgFromDetail } from '@/lib/string';
import { Lock, Bell, Building2, Loader2, Check, AlertCircle } from 'lucide-react';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || '') + '/api/v1/portal';

function getPortalHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('portal_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface ClientInfo {
  nome: string;
  cnpj: string;
  email: string;
  telefone: string;
}

export default function ConfiguracoesPage() {
  // Password change
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordMsg, setPasswordMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Notifications
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [notifLoading, setNotifLoading] = useState(false);
  const [notifMsg, setNotifMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Client info
  const [clientInfo, setClientInfo] = useState<ClientInfo | null>(null);
  const [infoLoading, setInfoLoading] = useState(true);

  useEffect(() => {
    async function fetchSettings() {
      try {
        const [infoRes, prefsRes] = await Promise.all([
          fetch(`${API_BASE}/settings/info`, { headers: getPortalHeaders() }),
          fetch(`${API_BASE}/settings/preferences`, { headers: getPortalHeaders() }),
        ]);
        if (infoRes.ok) {
          setClientInfo(await infoRes.json());
        }
        if (prefsRes.ok) {
          const prefs = await prefsRes.json();
          setEmailNotifications(prefs.email_notifications ?? true);
        }
      } catch {
        // silently handle
      } finally {
        setInfoLoading(false);
      }
    }
    fetchSettings();
  }, []);

  async function handlePasswordChange(e: FormEvent) {
    e.preventDefault();
    setPasswordMsg(null);

    if (newPassword.length < 6) {
      setPasswordMsg({ type: 'error', text: 'A nova senha deve ter pelo menos 6 caracteres.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordMsg({ type: 'error', text: 'As senhas não coincidem.' });
      return;
    }

    setPasswordLoading(true);
    try {
      const res = await fetch(`${API_BASE}/settings/password`, {
        method: 'PUT',
        headers: getPortalHeaders(),
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(msgFromDetail(data?.detail) || 'Erro ao alterar senha.');
      }
      setPasswordMsg({ type: 'success', text: 'Senha alterada com sucesso!' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erro ao alterar senha.';
      setPasswordMsg({ type: 'error', text: message });
    } finally {
      setPasswordLoading(false);
    }
  }

  async function handleToggleNotifications() {
    const newValue = !emailNotifications;
    setEmailNotifications(newValue);
    setNotifLoading(true);
    setNotifMsg(null);
    try {
      const res = await fetch(`${API_BASE}/settings/preferences`, {
        method: 'PATCH',
        headers: getPortalHeaders(),
        body: JSON.stringify({ email_notifications: newValue }),
      });
      if (!res.ok) throw new Error('Erro ao salvar preferências.');
      setNotifMsg({ type: 'success', text: 'Preferências salvas!' });
    } catch {
      setEmailNotifications(!newValue); // revert
      setNotifMsg({ type: 'error', text: 'Erro ao salvar preferências.' });
    } finally {
      setNotifLoading(false);
    }
  }

  function formatCnpjDisplay(cnpj: string): string {
    const d = cnpj.replace(/\D/g, '');
    if (d.length !== 14) return cnpj;
    return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Configurações</h1>
        <p className="text-gray-500 text-sm mt-1">Gerencie sua conta e preferências.</p>
      </div>

      {/* Change Password */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-5">
          <Lock className="h-5 w-5 text-indigo-600" />
          <h2 className="text-lg font-semibold text-gray-900">Alterar Senha</h2>
        </div>

        {passwordMsg && (
          <div
            className={`mb-4 p-3 rounded-lg text-sm flex items-center gap-2 ${
              passwordMsg.type === 'success'
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}
          >
            {passwordMsg.type === 'success' ? (
              <Check className="h-4 w-4 flex-shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
            )}
            {passwordMsg.text}
          </div>
        )}

        <form onSubmit={handlePasswordChange} className="space-y-4">
          <div>
            <label htmlFor="current" className="block text-sm font-medium text-gray-700 mb-1">
              Senha Atual
            </label>
            <input
              id="current"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-gray-900"
            />
          </div>
          <div>
            <label htmlFor="newpw" className="block text-sm font-medium text-gray-700 mb-1">
              Nova Senha
            </label>
            <input
              id="newpw"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={6}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-gray-900"
            />
          </div>
          <div>
            <label htmlFor="confirm" className="block text-sm font-medium text-gray-700 mb-1">
              Confirmar Nova Senha
            </label>
            <input
              id="confirm"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-gray-900"
            />
          </div>
          <button
            type="submit"
            disabled={passwordLoading}
            className="flex items-center gap-2 bg-indigo-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {passwordLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            Salvar Senha
          </button>
        </form>
      </div>

      {/* Notification Preferences */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-5">
          <Bell className="h-5 w-5 text-indigo-600" />
          <h2 className="text-lg font-semibold text-gray-900">Preferências de Notificação</h2>
        </div>

        {notifMsg && (
          <div
            className={`mb-4 p-3 rounded-lg text-sm flex items-center gap-2 ${
              notifMsg.type === 'success'
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}
          >
            {notifMsg.type === 'success' ? (
              <Check className="h-4 w-4 flex-shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
            )}
            {notifMsg.text}
          </div>
        )}

        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-900">Notificações por E-mail</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Receba atualizações sobre kits e chamados por e-mail.
            </p>
          </div>
          <button
            type="button"
            onClick={handleToggleNotifications}
            disabled={notifLoading}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${
              emailNotifications ? 'bg-indigo-600' : 'bg-gray-200'
            } ${notifLoading ? 'opacity-50' : ''}`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                emailNotifications ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>
      </div>

      {/* Contact Info (read-only) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center gap-2 mb-5">
          <Building2 className="h-5 w-5 text-indigo-600" />
          <h2 className="text-lg font-semibold text-gray-900">Dados de Contato</h2>
        </div>

        {infoLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
          </div>
        ) : clientInfo ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider">Nome / Razão Social</p>
              <p className="text-sm font-medium text-gray-900 mt-1">{clientInfo.nome}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider">CNPJ</p>
              <p className="text-sm font-medium text-gray-900 mt-1">
                {formatCnpjDisplay(clientInfo.cnpj)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider">E-mail</p>
              <p className="text-sm font-medium text-gray-900 mt-1">{clientInfo.email}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wider">Telefone</p>
              <p className="text-sm font-medium text-gray-900 mt-1">{clientInfo.telefone}</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400 text-center py-4">
            Informações de contato não disponíveis.
          </p>
        )}

        <p className="text-xs text-gray-400 mt-4 pt-4 border-t border-gray-100">
          Para alterar dados cadastrais, entre em contato com nosso suporte.
        </p>
      </div>
    </div>
  );
}
