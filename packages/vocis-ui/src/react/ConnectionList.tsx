// Voice Gateway UI - React ConnectionList component

import React, { useEffect, useState } from 'react';
import { PlatformConnection, VoiceGatewayClient } from '../core';

interface ConnectionListProps {
  apiBaseUrl: string;
  authToken?: string;
  onEdit?: (connection: PlatformConnection) => void;
  onDelete?: (connectionId: string) => void;
  onStartSession?: (connection: PlatformConnection) => void;
}

export const ConnectionList: React.FC<ConnectionListProps> = ({
  apiBaseUrl,
  authToken,
  onEdit,
  onDelete,
  onStartSession,
}) => {
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const client = new VoiceGatewayClient(apiBaseUrl, authToken);
    
    client.listConnections()
      .then(setConnections)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load connections'))
      .finally(() => {
        setLoading(false);
        client.close();
      });
  }, [apiBaseUrl, authToken]);

  const handleDelete = async (connectionId: string) => {
    if (!confirm('Are you sure you want to delete this connection?')) {
      return;
    }

    const client = new VoiceGatewayClient(apiBaseUrl, authToken);
    await client.deleteConnection(connectionId);
    setConnections(connections.filter(c => c.id !== connectionId));
    onDelete?.(connectionId);
  };

  if (loading) {
    return <div className="loading">Loading connections...</div>;
  }

  if (error) {
    return <div className="error">Error: {error}</div>;
  }

  if (connections.length === 0) {
    return <div className="empty">No connections configured</div>;
  }

  return (
    <div className="connection-list">
      <h2>Configured Connections</h2>
      <ul>
        {connections.map((connection) => (
          <li key={connection.id} className="connection-item">
            <div className="connection-header">
              <h3>{connection.displayName}</h3>
              <span className="connection-id">{connection.id}</span>
            </div>
            <div className="connection-details">
              <p><strong>Connector:</strong> {connection.connectorId}</p>
              <p><strong>Server:</strong> {String(connection.configuration.serverUrl || 'N/A')}</p>
              <p><strong>Credential:</strong> {connection.credentialGrantId || 'Not configured'}</p>
            </div>
            <div className="connection-actions">
              {onStartSession && (
                <button onClick={() => onStartSession(connection)}>
                  Start Session
                </button>
              )}
              {onEdit && (
                <button onClick={() => onEdit(connection)}>
                  Edit
                </button>
              )}
              {onDelete && (
                <button onClick={() => handleDelete(connection.id)} className="delete">
                  Delete
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};
