// Voice Gateway UI - React VoiceSession component

import React, { useState } from 'react';
import { VoiceSession as VoiceSessionType, VoiceGatewayClient } from '../core';

interface VoiceSessionProps {
  apiBaseUrl: string;
  authToken?: string;
  connectionId: string;
  voiceProfileId: string;
  agentSessionId?: string;
  onSessionStart?: (session: VoiceSessionType) => void;
  onSessionEnd?: (session: VoiceSessionType) => void;
}

export const VoiceSession: React.FC<VoiceSessionProps> = ({
  apiBaseUrl,
  authToken,
  connectionId,
  voiceProfileId,
  agentSessionId,
  onSessionStart,
  onSessionEnd,
}) => {
  const [session, setSession] = useState<VoiceSessionType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startSession = async () => {
    setLoading(true);
    setError(null);

    const client = new VoiceGatewayClient(apiBaseUrl, authToken);

    try {
      const newSession = await client.startVoiceSession({
        connectionId,
        agentSessionId,
        voiceProfileId,
      });
      setSession(newSession);
      onSessionStart?.(newSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start session');
    } finally {
      setLoading(false);
    }
  };

  const endSession = async () => {
    if (!session) return;

    const client = new VoiceGatewayClient(apiBaseUrl, authToken);
    await client.endVoiceSession(session.agentSessionId);
    setSession(null);
    onSessionEnd?.(session);
  };

  if (session) {
    return (
      <div className="voice-session active">
        <h2>Active Voice Session</h2>
        <div className="session-details">
          <p><strong>Connection:</strong> {session.connectionId}</p>
          <p><strong>Agent Session:</strong> {session.agentSessionId}</p>
          <p><strong>Voice Profile:</strong> {session.voiceProfileId}</p>
          <p><strong>Status:</strong> {session.status}</p>
        </div>
        <button onClick={endSession}>End Session</button>
      </div>
    );
  }

  return (
    <div className="voice-session">
      <h2>Start Voice Session</h2>
      {error && <div className="error">{error}</div>}
      <div className="session-config">
        <p><strong>Connection:</strong> {connectionId}</p>
        <p><strong>Voice Profile:</strong> {voiceProfileId}</p>
        {agentSessionId && <p><strong>Agent Session:</strong> {agentSessionId}</p>}
      </div>
      <button onClick={startSession} disabled={loading}>
        {loading ? 'Starting...' : 'Start Session'}
      </button>
    </div>
  );
};
