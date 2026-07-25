// Voice Gateway UI - HTTP client for VoiceGatewayApi

import { ApiError, ERROR_CODES, ConnectorManifest, PlatformConnection, VoiceSession } from './types';

export class VoiceGatewayClient {
  private readonly baseUrl: string;
  private readonly authToken: string | null;

  constructor(baseUrl: string, authToken?: string) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.authToken = authToken || null;
  }

  close(): void {
    // No-op for now, can add cleanup logic later
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }

    const response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        code: ERROR_CODES.SESSION_ERROR,
        message: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw error as ApiError;
    }

    return response.json();
  }

  async listConnectors(): Promise<ConnectorManifest[]> {
    return this.request<ConnectorManifest[]>('GET', '/api/connectors');
  }

  async listConnections(): Promise<PlatformConnection[]> {
    return this.request<PlatformConnection[]>('GET', '/api/connections');
  }

  async createConnection(connection: Omit<PlatformConnection, 'credentialGrantId'> & { credentialGrantId?: string | null }): Promise<PlatformConnection> {
    return this.request<PlatformConnection>('POST', '/api/connections', connection);
  }

  async updateConnection(connectionId: string, updates: Partial<PlatformConnection>): Promise<PlatformConnection> {
    return this.request<PlatformConnection>('PATCH', `/api/connections/${connectionId}`, updates);
  }

  async deleteConnection(connectionId: string): Promise<void> {
    return this.request<void>('DELETE', `/api/connections/${connectionId}`);
  }

  async startVoiceSession(params: {
    connectionId: string;
    agentSessionId?: string;
    voiceProfileId: string;
  }): Promise<VoiceSession> {
    return this.request<VoiceSession>('POST', '/api/sessions', params);
  }

  async endVoiceSession(sessionId: string): Promise<void> {
    return this.request<void>('DELETE', `/api/sessions/${sessionId}`);
  }
}
