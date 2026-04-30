import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, tokenStorage, activeSpaceStorage } from './api';
import type { User, FamilySpace } from './types';

type AuthState = {
  user: User | null;
  loading: boolean;
  spaces: FamilySpace[];
  activeSpace: FamilySpace | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  loginWithGoogleSession: (sessionId: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSpaces: () => Promise<FamilySpace[]>;
  setActiveSpaceId: (id: string) => Promise<void>;
  createSpace: (name: string) => Promise<FamilySpace>;
  joinSpace: (inviteCode: string) => Promise<FamilySpace>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [spaces, setSpaces] = useState<FamilySpace[]>([]);
  const [activeSpace, setActiveSpace] = useState<FamilySpace | null>(null);

  const refreshSpaces = useCallback(async (): Promise<FamilySpace[]> => {
    const list = await api.get<FamilySpace[]>('/spaces');
    setSpaces(list);
    const stored = await activeSpaceStorage.get();
    const found = list.find((s) => s.space_id === stored) || list[0] || null;
    setActiveSpace(found);
    if (found) await activeSpaceStorage.set(found.space_id);
    return list;
  }, []);

  const loadMe = useCallback(async () => {
    try {
      const u = await api.get<User>('/auth/me');
      setUser(u);
      await refreshSpaces();
    } catch {
      setUser(null);
      setSpaces([]);
      setActiveSpace(null);
    } finally {
      setLoading(false);
    }
  }, [refreshSpaces]);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  const login = async (email: string, password: string) => {
    const res = await api.post<{ token: string; user: User }>('/auth/login', { email, password });
    await tokenStorage.set(res.token);
    setUser(res.user);
    await refreshSpaces();
  };

  const register = async (email: string, password: string, name: string) => {
    const res = await api.post<{ token: string; user: User }>('/auth/register', { email, password, name });
    await tokenStorage.set(res.token);
    setUser(res.user);
    await refreshSpaces();
  };

  const loginWithGoogleSession = async (sessionId: string) => {
    const res = await api.post<{ token: string; user: User }>('/auth/google-session', { session_id: sessionId });
    await tokenStorage.set(res.token);
    setUser(res.user);
    await refreshSpaces();
  };

  const logout = async () => {
    try { await api.post('/auth/logout'); } catch {}
    await tokenStorage.clear();
    await activeSpaceStorage.clear();
    setUser(null);
    setSpaces([]);
    setActiveSpace(null);
  };

  const setActiveSpaceId = async (id: string) => {
    const found = spaces.find((s) => s.space_id === id) || null;
    if (found) {
      setActiveSpace(found);
      await activeSpaceStorage.set(id);
    }
  };

  const createSpace = async (name: string) => {
    const s = await api.post<FamilySpace>('/spaces', { name });
    await refreshSpaces();
    await activeSpaceStorage.set(s.space_id);
    setActiveSpace(s);
    return s;
  };

  const joinSpace = async (inviteCode: string) => {
    const s = await api.post<FamilySpace>('/spaces/join', { invite_code: inviteCode });
    await refreshSpaces();
    await activeSpaceStorage.set(s.space_id);
    setActiveSpace(s);
    return s;
  };

  return (
    <AuthContext.Provider value={{
      user, loading, spaces, activeSpace,
      login, register, loginWithGoogleSession, logout,
      refreshSpaces, setActiveSpaceId, createSpace, joinSpace,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
