"""Application-owned attachment storage and delivery tuning values."""

UPLOAD_READ_CHUNK_BYTES = 1024 * 1024
STORED_FILE_DELETE_RETRY_BASE_SECONDS = 60
STORED_FILE_DELETE_RETRY_MAX_SECONDS = 86_400
STORED_FILE_DELETE_RETRY_MAX_EXPONENT = 10
STORED_FILE_DELETE_ERROR_MAX_CHARS = 4_000
STORED_FILE_CLEANUP_BATCH_SIZE = 50
ATTACHMENT_CONTENT_CACHE_MAX_AGE_SECONDS = 300


def validate_attachment_config() -> None:
    if UPLOAD_READ_CHUNK_BYTES < 1:
        raise ValueError("UPLOAD_READ_CHUNK_BYTES must be positive")
    if not 0 < STORED_FILE_DELETE_RETRY_BASE_SECONDS <= STORED_FILE_DELETE_RETRY_MAX_SECONDS:
        raise ValueError("stored file delete retry values are invalid")
    if STORED_FILE_DELETE_RETRY_MAX_EXPONENT < 0:
        raise ValueError("STORED_FILE_DELETE_RETRY_MAX_EXPONENT must not be negative")
    if STORED_FILE_CLEANUP_BATCH_SIZE < 1:
        raise ValueError("STORED_FILE_CLEANUP_BATCH_SIZE must be positive")
    if STORED_FILE_DELETE_ERROR_MAX_CHARS < 1:
        raise ValueError("STORED_FILE_DELETE_ERROR_MAX_CHARS must be positive")
    if ATTACHMENT_CONTENT_CACHE_MAX_AGE_SECONDS < 1:
        raise ValueError("ATTACHMENT_CONTENT_CACHE_MAX_AGE_SECONDS must be positive")


validate_attachment_config()
