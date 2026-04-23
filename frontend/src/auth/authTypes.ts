export type AuthType = "guest" | "microsoft";

export type SessionApiPayload = {
  user_id: string;
  auth_type: AuthType;
  display_name: string;
  email: string | null;
  capabilities: string[];
  persistent: boolean;
  idle_expires_at: string;
  absolute_expires_at: string;
};

export type AuthSessionEnvelope = {
  authenticated: true;
  session: SessionApiPayload;
};

export type AuthIssuePayload = {
  authenticated?: false;
  detail?: string;
  reason?: string;
  action?: "login" | "session_conflict";
  redirect_to?: string;
  can_evict_oldest?: boolean;
  auth_type?: AuthType | null;
  session_limit?: number | null;
};

export type AuthSession = {
  userId: string;
  authType: AuthType;
  displayName: string;
  email: string | null;
  capabilities: string[];
  persistent: boolean;
  idleExpiresAt: string;
  absoluteExpiresAt: string;
};

export type SessionConflictInfo = {
  reason: string;
  detail: string;
  redirectTo: string;
  canEvictOldest: boolean;
  authType: AuthType | null;
  sessionLimit: number | null;
};

export type AuthStatus = "booting" | "anonymous" | "guest" | "microsoft";

