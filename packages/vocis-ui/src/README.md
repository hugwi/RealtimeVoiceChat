# Voice Gateway UI

Reusable settings UI for Voice Gateway - React components + single-spa micro-frontend.

## Architecture

```
voice_gateway_ui/
├── core/              # Framework-agnostic types & API client
│   ├── types.ts       # TypeScript types
│   ├── apiClient.ts   # HTTP client for VoiceGatewayApi
│   └── index.ts       # Exports
│
├── react/             # React components (primary)
│   ├── ConnectorList.tsx
│   ├── ConnectionForm.tsx
│   ├── ConnectionList.tsx
│   ├── VoiceSession.tsx
│   └── index.tsx      # Exports
│
├── single-spa/        # Standalone micro-frontend
│   ├── index.tsx      # mount/unmount/bootstrap
│   ├── SettingsPage.tsx
│   └── webpack.config.js
│
├── styles.css         # Default styles
├── package.json
└── tsconfig.json
```

## Usage

### Option A: React Components (Best for OmniGent)

```bash
npm install @voice-gateway/ui
```

```tsx
import { ConnectorList, ConnectionList, ConnectionForm } from '@voice-gateway/ui/react';

function OmniGentSettings() {
  return (
    <div>
      <ConnectorList apiBaseUrl="/api" />
      <ConnectionList 
        apiBaseUrl="/api"
        onEdit={(conn) => setEditing(conn)}
        onStartSession={(conn) => startSession(conn)}
      />
    </div>
  );
}
```

### Option B: Single-SPA Micro-Frontend

```javascript
// In your root app (OmniGent)
singleSpa.registerApplication({
  name: '@vg/settings',
  app: () => import('@voice-gateway/ui/single-spa'),
  activeWhen: (location) => 
    location.pathname.startsWith('/voice-settings'),
  customProps: {
    apiBaseUrl: '/api/voice',
    authToken: user.token,
    user: { id: 'user-123', name: 'Alice' }
  }
});
```

## Components

### ConnectorList
Lists available Platform Connectors.

```tsx
<ConnectorList 
  apiBaseUrl="/api"
  authToken="bearer-token"
  onSelect={(connector) => handleSelect(connector)}
/>
```

### ConnectionList
Lists configured Platform Connections.

```tsx
<ConnectionList
  apiBaseUrl="/api"
  authToken="bearer-token"
  onEdit={(conn) => handleEdit(conn)}
  onDelete={(id) => handleDelete(id)}
  onStartSession={(conn) => handleStart(conn)}
/>
```

### ConnectionForm
Create or edit a Platform Connection.

```tsx
<ConnectionForm
  apiBaseUrl="/api"
  authToken="bearer-token"
  connectorId="omnigent"
  existingConnection={editingConnection}
  onSave={(conn) => handleSave(conn)}
  onCancel={() => handleCancel()}
/>
```

### VoiceSession
Start and manage Voice Sessions.

```tsx
<VoiceSession
  apiBaseUrl="/api"
  authToken="bearer-token"
  connectionId="remote"
  voiceProfileId="default"
  agentSessionId="conv-123"
  onSessionStart={(session) => handleStart(session)}
  onSessionEnd={(session) => handleEnd(session)}
/>
```

## Build

```bash
# Build core library and React components
npm run build

# Build single-spa micro-frontend
npm run build:single-spa

# Development server for single-spa
npm run dev:single-spa
```

## API Client

```typescript
import { VoiceGatewayClient } from '@voice-gateway/ui';

const client = new VoiceGatewayClient('/api', 'bearer-token');

// List connectors
const connectors = await client.listConnectors();

// List connections
const connections = await client.listConnections();

// Create connection
const connection = await client.createConnection({
  id: 'remote',
  connectorId: 'omnigent',
  displayName: 'Remote OmniGent',
  configuration: { serverUrl: 'https://omnigent.example.com' },
  credentialGrantId: 'grant-123',
});

// Start voice session
const session = await client.startVoiceSession({
  connectionId: 'remote',
  voiceProfileId: 'default',
  agentSessionId: 'conv-123',
});
```

## Styling

Include the default styles:

```tsx
import '@voice-gateway/ui/styles.css';
```

Or customize by overriding CSS classes:
- `.voice-settings`
- `.connector-list`
- `.connection-list`
- `.connection-form`
- `.voice-session`

## License

MIT
