// Voice Gateway UI - React ConnectorList component

import React, { useEffect, useState } from 'react';
import { ConnectorManifest, VoiceGatewayClient } from '../core';

interface ConnectorListProps {
  apiBaseUrl: string;
  authToken?: string;
  onSelect?: (connector: ConnectorManifest) => void;
}

export const ConnectorList: React.FC<ConnectorListProps> = ({
  apiBaseUrl,
  authToken,
  onSelect,
}) => {
  const [connectors, setConnectors] = useState<ConnectorManifest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const client = new VoiceGatewayClient(apiBaseUrl, authToken);
    
    client.listConnectors()
      .then(setConnectors)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load connectors'))
      .finally(() => {
        setLoading(false);
        client.close();
      });
  }, [apiBaseUrl, authToken]);

  if (loading) {
    return <div className="loading">Loading connectors...</div>;
  }

  if (error) {
    return <div className="error">Error: {error}</div>;
  }

  if (connectors.length === 0) {
    return <div className="empty">No connectors available</div>;
  }

  return (
    <div className="connector-list">
      <h2>Available Connectors</h2>
      <ul>
        {connectors.map((connector) => (
          <li key={connector.id} className="connector-item">
            <div className="connector-header">
              <h3>{connector.displayName}</h3>
              <span className="connector-id">{connector.id}</span>
            </div>
            <div className="connector-details">
              <p><strong>Protocol:</strong> ACP v{connector.protocolVersion}</p>
              <p><strong>Capabilities:</strong> {connector.capabilities.join(', ')}</p>
              <p><strong>Auth Methods:</strong> {connector.authenticationMethods.join(', ')}</p>
            </div>
            {onSelect && (
              <button onClick={() => onSelect(connector)}>
                Select Connector
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};
