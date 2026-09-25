// Systemübersicht (ADMIN only; W4-03): one panel per concern, each with its
// own query, so a failing endpoint only affects its own panel.
import React from 'react';
import { ButtonLink, Card, PageHeader } from '../ui';
import { SystemStatusPanel } from './admin/SystemStatusPanel';
import { WorkshopSettingsPanel } from './admin/WorkshopSettingsPanel';
import { EmailConfigPanel } from './admin/EmailConfigPanel';
import { OutboxQueuePanel } from './admin/OutboxQueuePanel';
import { CustomerImportPanel } from './admin/CustomerImportPanel';
import { ThemePanel } from './admin/ThemePanel';
import '../styles/admin.css';

const UsersPanel: React.FC = () => (
  <Card
    title="Benutzer"
    className="admin-panel"
    action={
      <ButtonLink to="/users" variant="secondary" icon="user-check">
        Benutzer verwalten
      </ButtonLink>
    }
  >
    <p className="admin-panel__intro">
      Konten anlegen, Rollen vergeben und Zugänge sperren. Rollen steuern, wer Preise, Kosten und
      Entwürfe sieht.
    </p>
  </Card>
);

export const AdminSystemPage: React.FC = () => (
  <div className="admin-system-page">
    <PageHeader
      title="Systemübersicht"
      secondaryActions={
        <ButtonLink to="/admin/scan-gate" variant="ghost" icon="scan">
          Scan-Nutzung ansehen
        </ButtonLink>
      }
    />
    <div className="admin-panels">
      <SystemStatusPanel />
      <WorkshopSettingsPanel />
      <OutboxQueuePanel />
      <EmailConfigPanel />
      <UsersPanel />
      <CustomerImportPanel />
      <ThemePanel />
    </div>
  </div>
);

export default AdminSystemPage;
