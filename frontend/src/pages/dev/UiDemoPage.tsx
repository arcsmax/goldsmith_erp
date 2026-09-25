// /dev/ui — development-only gallery of every src/ui primitive in every state
// (UI-UX-PLAYBOOK section 9, phase 2 acceptance: "a demo route (dev only)
// shows all states at 1280 and 390"). Registered in App.tsx behind
// import.meta.env.DEV, so production builds do not contain it.
//
// Screenshot loop helpers: `?open=modal|dirty|dialog|sheet|prompt` opens an
// overlay on load; `?tab=` drives the Tabs example. Demo data only.
import React, { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  Button,
  ButtonLink,
  Card,
  DataTable,
  DeadlineChip,
  Dialog,
  EmptyState,
  Field,
  IconButton,
  ListCard,
  Modal,
  PageHeader,
  PageState,
  PromptDialog,
  Sheet,
  TabBar,
  Tabs,
  useTabParam,
  type Column,
  type SortState,
} from '../../ui';

const DEMO_NOW = new Date(2026, 8, 25, 10, 0);

interface DemoOrder {
  id: number;
  title: string;
  customer: string;
  deadline: string | null;
  weight: number;
  price: number;
}

const DEMO_ORDERS: DemoOrder[] = [
  { id: 1042, title: 'Trauringe Gelbgold 585', customer: 'Kundin A.', deadline: '2026-09-27', weight: 7.4, price: 1180 },
  { id: 1043, title: 'Kette kürzen', customer: 'Kunde B.', deadline: '2026-10-04', weight: 3.1, price: 45 },
  { id: 1044, title: 'Ring weiten, Stein neu fassen', customer: 'Kundin C.', deadline: '2026-09-22', weight: 4.8, price: 160 },
  { id: 1045, title: 'Anhänger nach Entwurf', customer: 'Kunde D.', deadline: null, weight: 2.2, price: 390 },
];

const PRICE = new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' });
const WEIGHT = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 2 });

const COLUMNS: Column<DemoOrder>[] = [
  { key: 'title', header: 'Titel', render: (o) => o.title, sortable: true },
  { key: 'customer', header: 'Kunde', render: (o) => o.customer, hideBelow: 'tablet' },
  {
    key: 'deadline',
    header: 'Frist',
    render: (o) => <DeadlineChip deadline={o.deadline} now={DEMO_NOW} />,
    sortable: true,
  },
  { key: 'weight', header: 'Gewicht (g)', render: (o) => WEIGHT.format(o.weight), numeric: true, hideBelow: 'desktop' },
  { key: 'price', header: 'Preis', render: (o) => PRICE.format(o.price), numeric: true, sortable: true },
];

function sortOrders(rows: DemoOrder[], sort: SortState): DemoOrder[] {
  const factor = sort.direction === 'asc' ? 1 : -1;
  const value = (o: DemoOrder): string | number =>
    sort.key === 'price' ? o.price : sort.key === 'deadline' ? o.deadline ?? '9999' : o.title;
  return [...rows].sort((a, b) => (value(a) > value(b) ? factor : value(a) < value(b) ? -factor : 0));
}

const Section: React.FC<{ id: string; title: string; children: React.ReactNode }> = ({ id, title, children }) => (
  <section id={id} aria-labelledby={`${id}-title`} className="ui-demo__section">
    <h2 id={`${id}-title`} className="ui-demo__heading">
      {title}
    </h2>
    {children}
  </section>
);

const Row: React.FC<{ children: React.ReactNode }> = ({ children }) => <div className="ui-demo__row">{children}</div>;

const ButtonsDemo: React.FC = () => (
  <Section id="buttons" title="Button, IconButton, ButtonLink">
    <Row>
      <Button icon="plus">Auftrag anlegen</Button>
      <Button variant="secondary">Entwurf speichern</Button>
      <Button variant="ghost">Abbrechen</Button>
      <Button variant="danger" icon="trash">
        Auftrag löschen
      </Button>
    </Row>
    <Row>
      <Button size="lg" icon="clock">
        Zeit starten
      </Button>
      <Button size="lg" variant="secondary">
        Status ändern
      </Button>
      <Button loading>Auftrag speichern</Button>
      <Button disabled>Nicht verfügbar</Button>
    </Row>
    <Row>
      <IconButton icon="pencil" label="Auftrag bearbeiten" />
      <IconButton icon="more" label="Weitere Aktionen" variant="secondary" />
      <IconButton icon="trash" label="Foto löschen" variant="danger" />
      <IconButton icon="close" label="Schließen" size="lg" />
      <ButtonLink to="/dev/ui?tab=photos" variant="secondary" icon="arrow-left">
        Zu den Fotos
      </ButtonLink>
    </Row>
  </Section>
);

const CardsDemo: React.FC = () => (
  <Section id="cards" title="Card">
    <div className="ui-demo__grid">
      <Card title="Kunde" action={<ButtonLink to="/dev/ui" variant="ghost">Öffnen</ButtonLink>}>
        <p>Kundin A., Stammkundin seit 2019</p>
      </Card>
      <Card title="Überfällig" tone="danger">
        <p>3 Aufträge sind überfällig.</p>
      </Card>
      <Card title="Wartet auf Anprobe" tone="waiting">
        <p>2 Anproben heute.</p>
      </Card>
      <Card title="Abholbereit" tone="done">
        <p>4 Aufträge liegen bereit.</p>
      </Card>
      <Card>
        <p>Karte ohne Titel</p>
      </Card>
    </div>
  </Section>
);

const OverlaysDemo: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const open = params.get('open');
  const [title, setTitle] = useState('Trauringe Gelbgold 585');
  const [promptResult, setPromptResult] = useState<string | null>(null);
  const isDirty = title !== 'Trauringe Gelbgold 585';

  const show = (name: string | null): void => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (name) next.set('open', name);
        else next.delete('open');
        return next;
      },
      { replace: true },
    );
  };
  const close = (): void => {
    show(null);
    setTitle('Trauringe Gelbgold 585');
  };

  return (
    <Section id="overlays" title="Modal, Dialog, Sheet, PromptDialog">
      <Row>
        <Button variant="secondary" onClick={() => show('modal')}>
          Modal öffnen
        </Button>
        <Button variant="secondary" onClick={() => show('dirty')}>
          Formular mit Änderungen
        </Button>
        <Button variant="secondary" onClick={() => show('dialog')}>
          Löschen bestätigen
        </Button>
        <Button variant="secondary" onClick={() => show('sheet')}>
          Sheet öffnen
        </Button>
        <Button variant="secondary" onClick={() => show('prompt')}>
          Eingabe abfragen
        </Button>
      </Row>
      {promptResult !== null && <p>Letzte Eingabe: {promptResult || '(leer)'}</p>}

      <Modal
        open={open === 'modal' || open === 'dirty'}
        onClose={close}
        title="Auftrag bearbeiten"
        description="Pflichtfelder sind markiert."
        isDirty={open === 'dirty' ? true : isDirty}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              Abbrechen
            </Button>
            <Button onClick={close}>Auftrag speichern</Button>
          </>
        }
      >
        <Field label="Titel" name="title" required>
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Gewicht" name="weight" inputMode="decimal" suffix="g" help="Komma oder Punkt">
          <input defaultValue="7,4" />
        </Field>
      </Modal>

      <Dialog
        open={open === 'dialog'}
        title="Auftrag löschen?"
        message="Der Auftrag Nr. 1044 wird endgültig gelöscht. Das lässt sich nicht rückgängig machen."
        variant="danger"
        onConfirm={close}
        onCancel={close}
      />

      <Sheet open={open === 'sheet'} onClose={close} title="Nr. 1042 Trauringe Gelbgold 585" dismissOnBackdrop>
        <Row>
          <DeadlineChip deadline="2026-09-27" now={DEMO_NOW} size="lg" />
        </Row>
        <Row>
          <Button size="lg" icon="clock">
            Zeit starten
          </Button>
          <Button size="lg" variant="secondary">
            Status ändern
          </Button>
          <ButtonLink size="lg" variant="ghost" to="/dev/ui">
            Auftrag öffnen
          </ButtonLink>
        </Row>
      </Sheet>

      <PromptDialog
        open={open === 'prompt'}
        title="Kostenänderung ablehnen"
        label="Grund"
        help="Der Grund erscheint im Verlauf des Auftrags."
        confirmLabel="Ablehnung senden"
        required
        onSubmit={(value) => {
          setPromptResult(value);
          close();
        }}
        onCancel={close}
      />
    </Section>
  );
};

const FieldsDemo: React.FC = () => (
  <Section id="fields" title="Field">
    <div className="ui-demo__grid">
      <Field label="Titel" name="demo-title" required help="Kurz, zum Beispiel „Trauringe Meier“.">
        <input />
      </Field>
      <Field label="Gewicht" name="demo-weight" inputMode="decimal" suffix="g" error="Gewicht fehlt. Bitte in Gramm eingeben.">
        <input />
      </Field>
      <Field label="Preis" name="demo-price" inputMode="decimal" suffix="€">
        <input defaultValue="1.180,00" className="ui-num" />
      </Field>
      <Field label="Telefon" name="demo-phone" inputMode="tel">
        <input type="tel" autoComplete="tel" />
      </Field>
      <Field label="Legierung" name="demo-alloy">
        <select defaultValue="585">
          <option value="333">Gelbgold 333</option>
          <option value="585">Gelbgold 585</option>
          <option value="750">Gelbgold 750</option>
        </select>
      </Field>
      <Field label="Notiz" name="demo-note" help="Nur intern sichtbar.">
        <textarea rows={3} />
      </Field>
      <Field label="Auftragsnummer" name="demo-disabled">
        <input disabled defaultValue="Nr. 1042" />
      </Field>
    </div>
  </Section>
);

const TablesDemo: React.FC = () => {
  const [sort, setSort] = useState<SortState>({ key: 'deadline', direction: 'asc' });
  const rows = useMemo(() => sortOrders(DEMO_ORDERS, sort), [sort]);
  const emptyAction = <Button icon="plus">Ersten Auftrag anlegen</Button>;
  return (
    <Section id="tables" title="DataTable, ListCard">
      <DataTable<DemoOrder>
        rows={rows}
        columns={COLUMNS}
        getRowKey={(o) => o.id}
        rowHref={(o) => `/dev/ui?order=${o.id}`}
        caption="Aufträge (Demo)"
        showCaption
        sort={sort}
        onSortChange={setSort}
        cardMeta={(o) => o.customer}
        cardBadges={(o) => <DeadlineChip deadline={o.deadline} now={DEMO_NOW} />}
      />
      <h3 className="ui-demo__subheading">Laden</h3>
      <DataTable<DemoOrder> rows={[]} columns={COLUMNS} getRowKey={(o) => o.id} caption="Laden" state={{ status: 'loading' }} />
      <h3 className="ui-demo__subheading">Fehler</h3>
      <DataTable<DemoOrder>
        rows={[]}
        columns={COLUMNS}
        getRowKey={(o) => o.id}
        caption="Fehler"
        state={{ status: 'error', error: 'Aufträge konnten nicht geladen werden.', retry: () => undefined }}
      />
      <h3 className="ui-demo__subheading">Leer</h3>
      <DataTable<DemoOrder>
        rows={[]}
        columns={COLUMNS}
        getRowKey={(o) => o.id}
        caption="Leer"
        empty={{ title: 'Noch keine Aufträge', body: 'Lege den ersten Auftrag an.', action: emptyAction, headingLevel: 3 }}
      />
      <h3 className="ui-demo__subheading">ListCard einzeln</h3>
      <div className="ui-demo__grid">
        <ListCard
          href="/dev/ui"
          title="Trauringe Gelbgold 585"
          meta="Kundin A."
          badges={<DeadlineChip deadline="2026-09-27" now={DEMO_NOW} />}
        />
        <ListCard title="Ohne Link (nur Anzeige)" meta="Kunde B." />
      </div>
    </Section>
  );
};

const StatesDemo: React.FC = () => (
  <Section id="states" title="EmptyState, PageState">
    <div className="ui-demo__grid">
      <Card title="EmptyState">
        <EmptyState
          headingLevel={3}
          title="Noch keine Aufträge"
          body="Lege den ersten Auftrag an oder scanne eine Auftragstüte."
          action={<Button icon="plus">Ersten Auftrag anlegen</Button>}
          secondaryAction={
            <Button variant="secondary" icon="scan">
              QR-Code scannen
            </Button>
          }
        />
      </Card>
      <Card title="Laden (Liste)">
        <PageState state={{ status: 'loading' }} skeletonCount={3} />
      </Card>
      <Card title="Laden (Detail)">
        <PageState state={{ status: 'loading' }} skeleton="detail" skeletonCount={2} />
      </Card>
      <Card title="Fehler">
        <PageState state={{ status: 'error', error: 'Kunden konnten nicht geladen werden.', retry: () => undefined }} />
      </Card>
      <Card title="Leer">
        <PageState state={{ status: 'empty' }} empty={{ title: 'Keine Treffer', body: 'Filter zurücksetzen oder anders suchen.', headingLevel: 3 }} />
      </Card>
      <Card title="Bereit">
        <PageState state={{ status: 'ready' }}>
          <p>Inhalt ist geladen.</p>
        </PageState>
      </Card>
    </div>
  </Section>
);

const TAB_IDS = ['overview', 'photos', 'time'] as const;

const NavigationDemo: React.FC = () => {
  const [tab, setTab] = useTabParam(TAB_IDS, 'overview');
  return (
    <Section id="navigation" title="PageHeader, Tabs, TabBar">
      <Card>
        <PageHeader
          title="Beispiel: Auftrag Nr. 1042"
          meta={<DeadlineChip deadline="2026-09-27" now={DEMO_NOW} />}
          back={{ to: '/dev/ui', label: 'Aufträge' }}
          primaryAction={<Button>Anprobe erledigt</Button>}
          secondaryActions={<IconButton icon="more" label="Weitere Aktionen" variant="secondary" />}
          stickyPrimary={false}
        />
      </Card>
      <Tabs
        label="Auftragsbereiche"
        selectedId={tab}
        onSelect={setTab}
        tabs={[
          { id: 'overview', label: 'Übersicht', panel: <p>Übersicht zum Auftrag.</p> },
          { id: 'photos', label: 'Fotos', panel: <p>Fotos des Werkstücks.</p> },
          { id: 'time', label: 'Zeit', panel: <p>Erfasste Zeiten: 3,5 h</p> },
        ]}
      />
      <h3 className="ui-demo__subheading">TabBar (unter 1024px fest am unteren Rand)</h3>
      <TabBar
        label="Hauptnavigation (Demo)"
        className="ui-tab-bar--static"
        items={[
          { to: '/dashboard', label: 'Heute', icon: 'home' },
          { to: '/orders', label: 'Aufträge', icon: 'clipboard' },
          { to: '/dev/ui', label: 'Scan', icon: 'scan', prominent: true },
          { to: '/time-tracking', label: 'Zeit', icon: 'clock' },
          { to: '/settings', label: 'Mehr', icon: 'menu' },
        ]}
      />
    </Section>
  );
};

const DeadlinesDemo: React.FC = () => (
  <Section id="deadlines" title="DeadlineChip">
    <Row>
      <DeadlineChip deadline="2026-10-04" now={DEMO_NOW} />
      <DeadlineChip deadline="2026-09-28" now={DEMO_NOW} />
      <DeadlineChip deadline="2026-09-26" now={DEMO_NOW} />
      <DeadlineChip deadline="2026-09-25" now={DEMO_NOW} />
      <DeadlineChip deadline="2026-09-24" now={DEMO_NOW} />
      <DeadlineChip deadline="2026-09-22" now={DEMO_NOW} />
      <DeadlineChip deadline={null} now={DEMO_NOW} />
    </Row>
    <Row>
      <DeadlineChip deadline="2026-10-04" now={DEMO_NOW} size="lg" />
      <DeadlineChip deadline="2026-09-27" now={DEMO_NOW} size="lg" />
      <DeadlineChip deadline="2026-09-22" now={DEMO_NOW} size="lg" />
    </Row>
  </Section>
);

export const UiDemoPage: React.FC = () => (
  <main className="ui-demo">
    <PageHeader
      title="UI-Bausteine"
      meta="Entwicklungsansicht: alle Bausteine aus src/ui in allen Zuständen"
      primaryAction={<Button icon="plus">Neuer Auftrag</Button>}
    />
    <ButtonsDemo />
    <CardsDemo />
    <OverlaysDemo />
    <FieldsDemo />
    <TablesDemo />
    <StatesDemo />
    <NavigationDemo />
    <DeadlinesDemo />
  </main>
);

export default UiDemoPage;
