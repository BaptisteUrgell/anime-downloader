import type { ErrorResponse, HttpValidationError } from './client';

export function formatApiError(
  payload: ErrorResponse | HttpValidationError | unknown,
  fallback = 'Une erreur est survenue.',
): string {
  if (!payload || typeof payload !== 'object') {
    return fallback;
  }

  if (payload instanceof Error && payload.message.trim().length > 0) {
    return payload.message;
  }

  if ('detail' in payload) {
    const detail = payload.detail;
    if (typeof detail === 'string' && detail.trim().length > 0) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const messages = detail
        .map((item) =>
          item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string'
            ? item.msg
            : null,
        )
        .filter((msg): msg is string => msg !== null);
      if (messages.length > 0) {
        return messages.join(', ');
      }
    }
  }

  return fallback;
}

export function formatZodError(error: unknown): string {
  if (typeof error === 'string') {
    return error;
  }
  if (error && typeof error === 'object' && 'message' in error && typeof error.message === 'string') {
    return error.message;
  }
  return 'Valeur invalide.';
}
