import axios from "axios";
import { getSupabaseClient } from "./supabase";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use(async (config) => {
  const { data: { session } } = await getSupabaseClient().auth.getSession();
  if (session?.access_token) config.headers.Authorization = `Bearer ${session.access_token}`;
  return config;
});

async function getTrustedProfile() {
  const { data: { session } } = await getSupabaseClient().auth.getSession();
  if (!session?.access_token) throw new Error("Sign-in completed without an access token. Please sign in again.");
  const response = await api.get("/auth/me", { headers: { Authorization: `Bearer ${session.access_token}` } });
  return { ...response.data, name: session.user.user_metadata.name ?? session.user.email?.split("@")[0] ?? "TrustGrade user" } as { id: string; email: string; role: "teacher" | "student"; name: string };
}

export const authService = {
  async login(email: string, password: string) {
    const client = getSupabaseClient();
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) throw error;
    try {
      return await getTrustedProfile();
    } catch (error) {
      await client.auth.signOut();
      throw error;
    }
  },
  async register(name: string, email: string, password: string, role: "teacher" | "student") {
    const client = getSupabaseClient();
    const { data, error } = await client.auth.signUp({ email, password, options: { data: { name, role } } });
    if (error) throw error;
    if (!data.session) throw new Error("Check your email to confirm your account, then sign in. Role access is confirmed from your trusted profile.");
    return getTrustedProfile();
  },
  async logout() {
    const { error } = await getSupabaseClient().auth.signOut();
    if (error) throw error;
  },
};
