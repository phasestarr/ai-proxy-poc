import type { AuthSession, SessionApiPayload } from "./authTypes";

export function mapAuthSession(payload: SessionApiPayload): AuthSession {
  return {
    userId: payload.user_id,
    authType: payload.auth_type,
    displayName: payload.display_name,
    email: payload.email,
    capabilities: payload.capabilities,
    persistent: payload.persistent,
    expiresAt: payload.expires_at,
  };
}
