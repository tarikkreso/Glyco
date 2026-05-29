import { useSyncExternalStore } from "react";
import type { AgentChatResponse } from "../api/client";

export type AgentChatMessage = {
  role: "user" | "assistant";
  content: string;
  response?: AgentChatResponse;
  created_at: string;
};

type AgentChatState = {
  draft: string;
  messages: AgentChatMessage[];
};

const STORAGE_KEY = "glyco.agentChatSession.v1";
const initialAssistant: AgentChatMessage = {
  role: "assistant",
  content: (typeof navigator !== "undefined" && navigator.language && navigator.language.toLowerCase().startsWith("bs"))
    ? "Pitajte Glyco o riziku ove sedmice, promjenama u praćenju, pitanjima za doktora ili podršci porodice. Agent će koristiti vaš profil, očitanja, rezultate modela i kurirane smjernice."
    : "Ask Glyco about this week's risk, monitoring changes, doctor questions, or family support. The agent will use your profile, logs, model results, and curated guidance notes.",
  created_at: new Date().toISOString(),
};

const listeners = new Set<() => void>();

function loadState(): AgentChatState {
  if (typeof window === "undefined") return { draft: "", messages: [initialAssistant] };
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "");
    if (Array.isArray(parsed?.messages)) {
      return {
        draft: typeof parsed.draft === "string" ? parsed.draft : "",
        messages: parsed.messages.length ? parsed.messages : [initialAssistant],
      };
    }
  } catch {
    // Ignore invalid localStorage and fall back to a fresh chat.
  }
  return { draft: "", messages: [initialAssistant] };
}

let state: AgentChatState = loadState();

function persist() {
  if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function emit() {
  persist();
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return state;
}

export function setAgentDraft(draft: string) {
  state = { ...state, draft };
  emit();
}

export function appendAgentUserMessage(content: string) {
  state = {
    ...state,
    draft: "",
    messages: [...state.messages, { role: "user", content, created_at: new Date().toISOString() }],
  };
  emit();
}

export function appendAgentAssistantMessage(content: string, response?: AgentChatResponse) {
  state = {
    ...state,
    messages: [...state.messages, { role: "assistant", content, response, created_at: new Date().toISOString() }],
  };
  emit();
}

export function resetAgentConversation() {
  state = { draft: "", messages: [{ ...initialAssistant, created_at: new Date().toISOString() }] };
  emit();
}

export function useAgentChatSession() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
