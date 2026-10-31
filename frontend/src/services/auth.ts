import axios from "axios";
import { api } from "./api";
import type { User } from "../types/models";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export interface AuthenticatedProfile {
  id: string;
  email: string;
  role: "teacher" | "student";
  /** Name the user chose; null until they set one. */
  display_name?: string | null;
}

// Supabase Auth returns `{ msg }` or `{ error_description }` rather than a FastAPI-style `detail`.
function readableAuthError(error: unknown, fallback: string): Error {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as Record<string, unknown> | undefined;
    const message = data?.msg ?? data?.error_description ?? data?.message;
    if (typeof message === "string" && message) return new Error(message.charAt(0).toUpperCase() + message.slice(1));
    if (!error.response) return new Error("Could not reach the authentication service. Check your connection.");
  }
  return error instanceof Error ? error : new Error(fallback);
}

export async function signIn(email: string, password: string): Promise<string> {
  if (!supabaseUrl || !supabaseAnonKey) throw new Error("Authentication is not configured. Contact your administrator.");
  try {
    const response = await axios.post(`${supabaseUrl}/auth/v1/token?grant_type=password`, { email, password }, {
      headers: { apikey: supabaseAnonKey, "Content-Type": "application/json" },
    });
    const token = response.data.access_token as string;
    sessionStorage.setItem("tg_access_token", token);
    return token;
  } catch (error) {
    throw readableAuthError(error, "Unable to sign in.");
  }
}

export async function signUp(email: string, password: string): Promise<void> {
  if (!supabaseUrl || !supabaseAnonKey) throw new Error("Authentication is not configured. Contact your administrator.");
  try {
    await axios.post(`${supabaseUrl}/auth/v1/signup`, { email, password }, {
      headers: { apikey: supabaseAnonKey, "Content-Type": "application/json" },
    });
  } catch (error) {
    throw readableAuthError(error, "Unable to create your account.");
  }
}

export async function getProfile(): Promise<User> {
  const response = await api.get<AuthenticatedProfile>("/auth/me");
  const chosen = response.data.display_name?.trim();
  // Until the user saves a name, derive one from the email (shown only to the user themselves).
  const fallback = response.data.email
    .split("@")[0]
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
  const name = chosen || fallback;
  const initials = name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  return {
    id: response.data.id,
    email: response.data.email,
    name,
    role: response.data.role,
    initials,
    needsName: !chosen,
  };
}

/** Save the name shown to teachers and on the course leaderboard. */
export async function updateDisplayName(displayName: string): Promise<void> {
  await api.patch("/users/me", { display_name: displayName.trim() });
}

export function signOut(): void {
  sessionStorage.removeItem("tg_access_token");
}
