// Voice Gateway UI - SettingsPage component for single-spa

import React, { useState } from 'react';
import {
  ConnectorList,
  ConnectionList,
  ConnectionForm,
  VoiceSession,
} from '../react';
import { ConnectorManifest, PlatformConnection } from '../core';

interface SettingsPageProps {
  apiBaseUrl: string;
  authToken?: string;
  user?: { id: string; name?: string };
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  apiBaseUrl,
  authToken,
  user,
}) => {
  const [activeTab, setActiveTab] = useState<'connectors' | 'connections' | 'sessions'>('connectors');
  const [selectedConnector, setSelectedConnector] = useState<ConnectorManifest | null>(null);
  const [editingConnection, setEditingConnection] = useState<PlatformConnection | null>(null);
  const [sessionConnection, setSessionConnection] = useState<PlatformConnection | null>(null);

  const handleSelectConnector = (connector: ConnectorManifest) => {
    setSelectedConnector(connector);
    setActiveTab('connections');
  };

  const handleEditConnection = (connection: PlatformConnection) => {
    setEditingConnection(connection);
  };

  const handleSaveConnection = () => {
    setEditingConnection(null);
    // Refresh will happen via effect in ConnectionList
  };

  const handleStartSession = (connection: PlatformConnection) => {
    setSessionConnection(connection);
  };

  const handleSessionEnd = () => {
    setSessionConnection(null);
  };

  return (
    <div className="voice-settings">
      <header className="settings-header">
        <h1>Voice Gateway Settings</h1>
        {user && <span className="user-info">Welcome, {user.name || user.id}</span>}
      </header>

      <nav className="settings-nav">
        <button
          className={activeTab === 'connectors' ? 'active' : ''}
          onClick={() => setActiveTab('connectors')}
        >
          Connectors
        </button>
        <button
          className={activeTab === 'connections' ? 'active' : ''}
          onClick={() => setActiveTab('connections')}
        >
          Connections
        </button>
        <button
          className={activeTab === 'sessions' ? 'active' : ''}
          onClick={() => setActiveTab('sessions')}
        >
          Sessions
        </button>
      </nav>

      <main className="settings-content">
        {activeTab === 'connectors' && (
          <ConnectorList
            apiBaseUrl={apiBaseUrl}
            authToken={authToken}
            onSelect={handleSelectConnector}
          />
        )}

        {activeTab === 'connections' && (
          <>
            {editingConnection ? (
              <ConnectionForm
                apiBaseUrl={apiBaseUrl}
                authToken={authToken}
                connectorId={editingConnection.connectorId}
                existingConnection={editingConnection}
                onSave={handleSaveConnection}
                onCancel={() => setEditingConnection(null)}
              />
            ) : selectedConnector ? (
              <ConnectionForm
                apiBaseUrl={apiBaseUrl}
                authToken={authToken}
                connectorId={selectedConnector.id}
                onSave={handleSaveConnection}
              />
            ) : (
              <ConnectionList
                apiBaseUrl={apiBaseUrl}
                authToken={authToken}
                onEdit={handleEditConnection}
                onDelete={() => {}}
                onStartSession={handleStartSession}
              />
            )}
          </>
        )}

        {activeTab === 'sessions' && (
          sessionConnection ? (
            <VoiceSession
              apiBaseUrl={apiBaseUrl}
              authToken={authToken}
              connectionId={sessionConnection.id}
              voiceProfileId="default"
              onSessionEnd={handleSessionEnd}
            />
          ) : (
            <ConnectionList
              apiBaseUrl={apiBaseUrl}
              authToken={authToken}
              onStartSession={handleStartSession}
            />
          )
        )}
      </main>
    </div>
  );
};
