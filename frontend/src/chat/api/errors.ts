export class ChatDraftExpiredError extends Error {
  constructor(message = "chat draft expired") {
    super(message);
    this.name = "ChatDraftExpiredError";
  }
}
