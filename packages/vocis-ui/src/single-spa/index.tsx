// Voice Gateway UI - Single-SPA micro-frontend entry point

import { createRoot, Root } from 'react-dom/client';
import { SettingsPage } from './SettingsPage';

let reactRoot: Root | null = null;

interface CustomProps {
  apiBaseUrl?: string;
  authToken?: string;
  user?: { id: string; name?: string };
}

export function bootstrap() {
  console.log('Voice Gateway Settings: bootstrapped');
}

export function mount(props: CustomProps) {
  console.log('Voice Gateway Settings: mounting', props);

  let container = document.getElementById('voice-settings-root');
  if (!container) {
    container = document.createElement('div');
    container.id = 'voice-settings-root';
    document.body.appendChild(container);
  }

  reactRoot = createRoot(container);
  reactRoot.render(
    <SettingsPage
      apiBaseUrl={props.apiBaseUrl || '/api'}
      authToken={props.authToken}
      user={props.user}
    />
  );
}

export function unmount() {
  console.log('Voice Gateway Settings: unmounting');

  if (reactRoot) {
    reactRoot.unmount();
    reactRoot = null;
  }

  const container = document.getElementById('voice-settings-root');
  container?.remove();
}
