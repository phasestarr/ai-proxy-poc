import type { AuthSession } from "../../auth/authTypes";

export function getSessionLabel(session: AuthSession): string {
  if (session.authType === "microsoft" && session.email) {
    return maskEmail(session.email);
  }

  return session.displayName;
}

export function formatHistoryTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "unknown";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function maskEmail(email: string): string {
  const [localPart, domain] = email.split("@");
  if (!localPart || !domain) {
    return email;
  }

  const visiblePrefixLength = Math.min(2, localPart.length);
  const visiblePrefix = localPart.slice(0, visiblePrefixLength);
  return `${visiblePrefix}****@${domain}`;
}

