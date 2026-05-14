import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type AuthSession = {
  email: string;
  onboardingComplete: boolean;
};

type AuthContextValue = {
  session: AuthSession | null;
  isAuthenticated: boolean;
  register: (input: { email: string; password: string }) => { ok: true } | { ok: false; error: string };
  login: (input: { email: string; password: string }) => { ok: true } | { ok: false; error: string };
  logout: () => void;
  completeOnboarding: () => void;
};

const SESSION_KEY = "glyco_session_v1";
const ACCOUNTS_KEY = "glyco_accounts_v1";

type StoredAccount = { email: string };

function safeParseJson<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);

  useEffect(() => {
    const stored = safeParseJson<AuthSession>(localStorage.getItem(SESSION_KEY));
    if (stored?.email) setSession(stored);
  }, []);

  const persistSession = useCallback((next: AuthSession | null) => {
    setSession(next);
    if (!next) {
      localStorage.removeItem(SESSION_KEY);
      return;
    }
    localStorage.setItem(SESSION_KEY, JSON.stringify(next));
  }, []);

  const loadAccounts = useCallback(() => {
    return safeParseJson<StoredAccount[]>(localStorage.getItem(ACCOUNTS_KEY)) ?? [];
  }, []);

  const saveAccounts = useCallback((accounts: StoredAccount[]) => {
    localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts));
  }, []);

  const register = useCallback(
    ({ email, password }: { email: string; password: string }) => {
      const normalized = normalizeEmail(email);
      if (!normalized.includes("@")) return { ok: false as const, error: "Enter a valid email." };
      if (password.trim().length < 6) return { ok: false as const, error: "Password must be at least 6 characters." };

      const accounts = loadAccounts();
      if (accounts.some((a) => a.email === normalized)) {
        return { ok: false as const, error: "An account with this email already exists." };
      }

      saveAccounts([...accounts, { email: normalized }]);
      persistSession({ email: normalized, onboardingComplete: false });
      return { ok: true as const };
    },
    [loadAccounts, persistSession, saveAccounts]
  );

  const login = useCallback(
    ({ email, password }: { email: string; password: string }) => {
      const normalized = normalizeEmail(email);
      if (!normalized.includes("@")) return { ok: false as const, error: "Enter a valid email." };
      if (!password.trim()) return { ok: false as const, error: "Enter your password." };

      const accounts = loadAccounts();
      if (!accounts.some((a) => a.email === normalized)) {
        return { ok: false as const, error: "Account not found. Please register first." };
      }

      const storedSession = safeParseJson<AuthSession>(localStorage.getItem(SESSION_KEY));
      const onboardingComplete = storedSession?.email === normalized ? !!storedSession.onboardingComplete : true;
      persistSession({ email: normalized, onboardingComplete });
      return { ok: true as const };
    },
    [loadAccounts, persistSession]
  );

  const logout = useCallback(() => {
    persistSession(null);
  }, [persistSession]);

  const completeOnboarding = useCallback(() => {
    if (!session) return;
    persistSession({ ...session, onboardingComplete: true });
  }, [persistSession, session]);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isAuthenticated: !!session,
      register,
      login,
      logout,
      completeOnboarding,
    }),
    [completeOnboarding, login, logout, register, session]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
