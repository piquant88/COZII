import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { api, tokenStorage, activeSpaceStorage } from './api';
import type { User, FamilySpace } from './types';

export type SpaceRole = {
  role: 'owner' | 'member' | 'staff';
  staff_id: string | null;
  permissions: Record<string, boolean>;
};

type AuthState = {
  user: User | null;
  loading: boolean;
  spaces: FamilySpace[];
  activeSpace: FamilySpace | null;
  spaceRole: SpaceRole | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  loginWithGoogleSession: (sessionId: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshSpaces: () => Promise<FamilySpace[]>;
  refreshSpaceRole: () => Promise<SpaceRole | null>;
  setActiveSpaceId: (id: string) => Promise<void>;
  createSpace: (name: string, opts?: { space_type?: 'roommates' | 'household'; currency?: string }) => Promise<FamilySpace>;
  joinSpace: (inviteCode: string) => Promise<FamilySpace>;
  joinAsStaff: (inviteCode: string) => Promise<{ space_id: string; staff_id: string }>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

const DEFAULT_PERMS: Record<string, boolean> = {
  view_tasks: true, log_attendance: true, request_shopping: true,
  view_handbook: true, view_wage_amount: true,
  view_other_staff: false, view_family: false,
  view_finance: false, view_inventory: false,
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [spaces, setSpaces] = useState<FamilySpace[]>([]);
  const [activeSpace, setActiveSpace] = useState<FamilySpace | null>(null);
  const [spaceRole, setSpaceRole] = useState<SpaceRole | null>(null);
  const lastRoleSpaceId = useRef<string | null>(null);

  const refreshSpaces = useCallback(async (): Promise<FamilySpace[]> => {
    const list = await api.get<FamilySpace[]>('/spaces');
    setSpaces(list);
    const stored = await activeSpaceStorage.get();
    const found = list.find((s) => s.space_id === stored) || list[0] || null;
    setActiveSpace(found);
    if (found) await activeSpaceStorage.set(found.space_id);
    return list;
  }, []);

  const refreshSpaceRole = useCallback(async (): Promise<SpaceRole | null> => {
    if (!activeSpace) { setSpaceRole(null); return null; }
    try {
      const r = await api.get<any>(`/spaces/${activeSpace.space_id}/my_role`);
      const perms = { ...DEFAULT_PERMS, ...(r?.permissions || {}) };
      const role: SpaceRole = { role: r.role, staff_id: r.staff_id || null, permissions: perms };
      setSpaceRole(role);
      lastRoleSpaceId.current = activeSpace.space_id;
      return role;
    } catch {
      setSpaceRole(null);
      return null;
    }
  }, [activeSpace]);

  // re-fetch role whenever activeSpace changes
  useEffect(() => {
    if (activeSpace && activeSpace.space_id !== lastRoleSpaceId.current) {
      refreshSpaceRole();
    } else if (!activeSpace) {
      setSpaceRole(null);
      lastRoleSpaceId.current = null;
    }
  }, [activeSpace, refreshSpaceRole]);

  const loadMe = useCallback(async () => {
    try {
      const u = await api.get<User>('/auth/me');
      setUser(u);
      await refreshSpaces();
    } catch {
      setUser(null);
      setSpaces([]);
      setActiveSpace(null);
      setSpaceRole(null);
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
    setSpaceRole(null);
    lastRoleSpaceId.current = null;
  };

  const setActiveSpaceId = async (id: string) => {
    const found = spaces.find((s) => s.space_id === id) || null;
    if (found) {
      setActiveSpace(found);
      await activeSpaceStorage.set(id);
    }
  };

  const createSpace = async (name: string, opts?: { space_type?: 'roommates' | 'household'; currency?: string }) => {
    const s = await api.post<FamilySpace>('/spaces', {
      name,
      space_type: opts?.space_type || 'roommates',
      currency: opts?.currency || 'USD',
    });
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

  const joinAsStaff = async (inviteCode: string) => {
    const r = await api.post<{ ok: boolean; space_id: string; staff_id: string }>('/household/staff/join', { invite_code: inviteCode });
    const list = await refreshSpaces();
    const s = list.find((x) => x.space_id === r.space_id);
    if (s) {
      await activeSpaceStorage.set(s.space_id);
      setActiveSpace(s);
    }
    return { space_id: r.space_id, staff_id: r.staff_id };
  };

  return (
    <AuthContext.Provider value={{
      user, loading, spaces, activeSpace, spaceRole,
      login, register, loginWithGoogleSession, logout,
      refreshSpaces, refreshSpaceRole, setActiveSpaceId, createSpace, joinSpace, joinAsStaff,
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
