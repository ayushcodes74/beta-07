import axios from "axios";
import { api } from "./api";
import type { User } from "../types/models";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export interface AuthenticatedProfile {
  id: string;
  email: string;
  role: "teacher" | "student";
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
  const name = response.data.email.split("@")[0].replace(/[._-]+/g, " ");
  const initials = name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  return {
    id: response.data.id,
    email: response.data.email,
    name: name.replace(/\b\w/g, (character) => character.toUpperCase()),
    role: response.data.role,
    initials,
  };
}

export function signOut(): void {
  sessionStorage.removeItem("tg_access_token");
}
