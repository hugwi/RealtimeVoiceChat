// Voice Gateway UI - Shared TypeScript types

export type ConnectorManifest = {
  id: string;
  displayName: string;
  protocolVersion: string;
  capabilities: string[];
  authenticationMethods: string[];
  configuration: Record<string, unknown>;
};

export type PlatformConnection = {
  id: string;
  connectorId: string;
  displayName: string;
  configuration: Record<string, unknown>;
  credentialGrantId: string | null;
};

export type VoiceSession = {
  connectionId: string;
  agentSessionId: string;
  voiceProfileId: string;
  status: 'active' | 'ended';
};

export type VoiceGatewayError = {
  code: string;
  message: string;
};

export type ApiError = VoiceGatewayError;

export const ERROR_CODES = {
  CONNECTOR_NOT_FOUND: 'CONNECTOR_NOT_FOUND',
  CONNECTION_NOT_FOUND: 'CONNECTION_NOT_FOUND',
  SESSION_ERROR: 'SESSION_ERROR',
  AUTH_REQUIRED: 'AUTH_REQUIRED',
  INVALID_CONFIG: 'INVALID_CONFIG',
} as const;
