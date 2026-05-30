import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type AuthSession = {
  userId: number;
  email: string;
  fullName: string;
  onboardingComplete: boolean;
};

export type DemoAccount = {
  email: string;
  userId: number;
  fullName: string;
  onboardingComplete: boolean;
  scenario: "stable" | "watch" | "concerning";
  description: string;
};

type AuthContextValue = {
  session: AuthSession | null;
  isAuthenticated: boolean;
  demoAccounts: DemoAccount[];
  switchDemoAccount: (email: string) => void;
  register: (input: { email: string; password: string; fullName?: string; userId: number }) => { ok: true } | { ok: false; error: string };
  login: (input: { email: string; password: string }) => { ok: true } | { ok: false; error: string };
  logout: () => void;
  updateSession: (patch: Partial<Pick<AuthSession, "email" | "fullName">>) => void;
};

const SESSION_KEY = "glyco_session_v1";
const ACCOUNTS_KEY = "glyco_accounts_v1";

type StoredAccount = { email: string; userId: number; fullName: string; onboardingComplete: boolean };

const DEMO_ACCOUNTS: DemoAccount[] = [
  { email: "demo-monitoring", userId: 1, fullName: "Sarah Kovac", onboardingComplete: true, scenario: "concerning", description: "Best judge demo: active risk, monitoring trend, forecast, alerts, agent context, and report handoff." },
  { email: "demo-high-risk", userId: 2, fullName: "Milan Hadzic", onboardingComplete: true, scenario: "concerning", description: "High baseline risk profile for showing risk factors and doctor-ready summary." },
  { email: "demo-low-risk", userId: 3, fullName: "Lejla Moric", onboardingComplete: true, scenario: "stable", description: "Low-risk contrast case for showing that Glyco does not over-alert." },
  { email: "demo-improving", userId: 101, fullName: "Hana Novak", onboardingComplete: true, scenario: "stable", description: "Improving readings story for positive trend and routine reinforcement." },
  { email: "demo-high-variability", userId: 102, fullName: "Marko Jukic", onboardingComplete: true, scenario: "watch", description: "Variable glucose pattern for anomaly explanation and monitoring guidance." },
  { email: "demo-hypo-watch", userId: 103, fullName: "Ema Horvat", onboardingComplete: true, scenario: "watch", description: "Low-glucose watch case for forecast safety messaging." },
  { email: "demo-night-shift", userId: 104, fullName: "Ivan Knezevic", onboardingComplete: true, scenario: "watch", description: "Lifestyle-context case for agent personalization and practical next steps." },
  { email: "demo-weekend-spikes", userId: 105, fullName: "Petra Babic", onboardingComplete: true, scenario: "watch", description: "Post-meal/weekend spike story for Nutrition handoff." },
  { email: "demo-stable", userId: 106, fullName: "Luka Kralj", onboardingComplete: true, scenario: "stable", description: "Stable monitoring case for calm baseline comparison." },
];

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

function isValidLoginId(value: string) {
  return value.includes("@") || value.startsWith("demo-");
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [accounts, setAccounts] = useState<StoredAccount[]>([]);

  useEffect(() => {
    const stored = safeParseJson<AuthSession>(sessionStorage.getItem(SESSION_KEY));
    if (stored?.email) setSession(stored);
    setAccounts([...(safeParseJson<StoredAccount[]>(sessionStorage.getItem(ACCOUNTS_KEY)) ?? []), ...DEMO_ACCOUNTS]);
  }, []);

  const persistSession = useCallback((next: AuthSession | null) => {
    setSession(next);
    if (!next) {
      sessionStorage.removeItem(SESSION_KEY);
      return;
    }
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
  }, []);

  const saveAccounts = useCallback((accounts: StoredAccount[]) => {
    setAccounts(accounts);
    sessionStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts));
  }, []);

  const register = useCallback(
    (input: { email: string; password: string; fullName?: string; userId: number }) => {
      const { email, password, userId } = input;
      const normalized = normalizeEmail(email);
      if (!normalized.includes("@")) return { ok: false as const, error: "Enter a valid email." };
      if (password.trim().length < 6) return { ok: false as const, error: "Password must be at least 6 characters." };

      if (accounts.some((a) => a.email === normalized)) {
        return { ok: false as const, error: "An account with this email already exists." };
      }

      const fullName = email.split("@")[0] || "Glyco User";
      saveAccounts([...accounts, { email: normalized, userId, fullName: input.fullName?.trim() || fullName, onboardingComplete: true }]);
      persistSession({ userId, email: normalized, fullName: input.fullName?.trim() || fullName, onboardingComplete: true });
      return { ok: true as const };
    },
    [accounts, persistSession, saveAccounts]
  );

  const login = useCallback(
    ({ email, password }: { email: string; password: string }) => {
      const normalized = normalizeEmail(email);
      if (!isValidLoginId(normalized)) return { ok: false as const, error: "Enter a valid email or demo login ID." };
      if (!password.trim()) return { ok: false as const, error: "Enter your password." };

      if (!accounts.some((a) => a.email === normalized)) {
        return { ok: false as const, error: "Account not found. Please register first." };
      }

      const account = accounts.find((a) => a.email === normalized);
      const storedSession = safeParseJson<AuthSession>(sessionStorage.getItem(SESSION_KEY));
      const onboardingComplete = storedSession?.email === normalized ? !!storedSession.onboardingComplete : true;
      persistSession({ userId: account?.userId ?? 1, email: normalized, fullName: account?.fullName ?? normalized, onboardingComplete });
      return { ok: true as const };
    },
    [accounts, persistSession]
  );

  const logout = useCallback(() => {
    persistSession(null);
  }, [persistSession]);

  const switchDemoAccount = useCallback((email: string) => {
    const account = DEMO_ACCOUNTS.find((item) => item.email === normalizeEmail(email));
    if (!account) return;
    persistSession({
      userId: account.userId,
      email: account.email,
      fullName: account.fullName,
      onboardingComplete: true,
    });
  }, [persistSession]);

  const updateSession = useCallback((patch: Partial<Pick<AuthSession, "email" | "fullName">>) => {
    if (!session) return;
    const updatedSession = { ...session, ...patch };
    saveAccounts(accounts.map((account) => account.email === session.email ? { ...account, email: updatedSession.email, fullName: updatedSession.fullName, onboardingComplete: true } : account));
    persistSession(updatedSession);
  }, [accounts, persistSession, saveAccounts, session]);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isAuthenticated: !!session,
      demoAccounts: DEMO_ACCOUNTS,
      switchDemoAccount,
      register,
      login,
      logout,
      updateSession,
    }),
    [login, logout, register, session, switchDemoAccount, updateSession]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
