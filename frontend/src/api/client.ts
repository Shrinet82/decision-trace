import type { AskRequest, AskResponse, DecisionDetail } from './types';
import { getMockAskResponse } from './mocks';

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.PROD ? '/api' : 'http://localhost:8000');

export const USE_MOCKS =
  import.meta.env.VITE_USE_MOCKS !== undefined
    ? import.meta.env.VITE_USE_MOCKS === 'true' || import.meta.env.VITE_USE_MOCKS === '1'
    : import.meta.env.MODE === 'test';

export class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

/**
 * Ask a natural language question about decisions and evidence paths.
 */
export async function askQuestion(payload: AskRequest): Promise<AskResponse> {
  if (USE_MOCKS) {
    // Simulate brief network latency for realism
    await new Promise((resolve) => setTimeout(resolve, 80));
    return getMockAskResponse(payload.question);
  }

  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new ApiError(
      `Failed to get answer: ${response.statusText} (${response.status})`,
      response.status,
      errorBody
    );
  }

  return response.json();
}

/**
 * Fetch detailed decision by ID.
 */
export async function getDecision(decisionId: string): Promise<DecisionDetail> {
  const response = await fetch(`${API_BASE_URL}/decisions/${encodeURIComponent(decisionId)}`, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new ApiError(
      `Failed to load decision ${decisionId}: ${response.statusText} (${response.status})`,
      response.status,
      errorBody
    );
  }

  return response.json();
}
