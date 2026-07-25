// Voice Gateway UI - React ConnectionForm component

import React, { useState } from 'react';
import { PlatformConnection, VoiceGatewayClient } from '../core';

interface ConnectionFormProps {
  apiBaseUrl: string;
  authToken?: string;
  connectorId: string;
  existingConnection?: PlatformConnection;
  onSave?: (connection: PlatformConnection) => void;
  onCancel?: () => void;
}

export const ConnectionForm: React.FC<ConnectionFormProps> = ({
  apiBaseUrl,
  authToken,
  connectorId,
  existingConnection,
  onSave,
  onCancel,
}) => {
  const [id, setId] = useState(existingConnection?.id || '');
  const [displayName, setDisplayName] = useState(
    existingConnection?.displayName || ''
  );
  const [serverUrl, setServerUrl] = useState(
    String(existingConnection?.configuration.serverUrl || '')
  );
  const [credentialGrantId, setCredentialGrantId] = useState(
    existingConnection?.credentialGrantId || ''
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const client = new VoiceGatewayClient(apiBaseUrl, authToken);

    try {
      const connection = existingConnection
        ? await client.updateConnection(existingConnection.id, {
            displayName,
            configuration: { serverUrl },
            credentialGrantId: credentialGrantId || null,
          })
        : await client.createConnection({
            id,
            connectorId,
            displayName,
            configuration: { serverUrl },
            credentialGrantId: credentialGrantId || null,
          });

      onSave?.(connection);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save connection');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="connection-form" onSubmit={handleSubmit}>
      <h2>{existingConnection ? 'Edit' : 'Create'} Connection</h2>

      {error && <div className="error">{error}</div>}

      <div className="form-group">
        <label htmlFor="id">Connection ID</label>
        <input
          id="id"
          type="text"
          value={id}
          onChange={(e) => setId(e.target.value)}
          required
          disabled={!!existingConnection}
          placeholder="e.g., remote"
        />
      </div>

      <div className="form-group">
        <label htmlFor="displayName">Display Name</label>
        <input
          id="displayName"
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          required
          placeholder="e.g., Remote OmniGent"
        />
      </div>

      <div className="form-group">
        <label htmlFor="serverUrl">Server URL</label>
        <input
          id="serverUrl"
          type="url"
          value={serverUrl}
          onChange={(e) => setServerUrl(e.target.value)}
          required
          placeholder="e.g., https://omnigent.example.com"
        />
      </div>

      <div className="form-group">
        <label htmlFor="credentialGrantId">Credential Grant ID (optional)</label>
        <input
          id="credentialGrantId"
          type="text"
          value={credentialGrantId}
          onChange={(e) => setCredentialGrantId(e.target.value)}
          placeholder="e.g., grant-123"
        />
        <small>Leave empty to authorize via device flow later</small>
      </div>

      <div className="form-actions">
        <button type="submit" disabled={loading}>
          {loading ? 'Saving...' : existingConnection ? 'Update' : 'Create'}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
};
