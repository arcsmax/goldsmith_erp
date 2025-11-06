/**
 * Dashboard Page
 */
import './Dashboard.css';

export default function Dashboard() {
  return (
    <div className="dashboard">
      <h1 className="page-title">Dashboard</h1>

      <div className="dashboard-grid">
        <div className="stat-card">
          <div className="stat-icon">📋</div>
          <div className="stat-content">
            <div className="stat-label">Offene Aufträge</div>
            <div className="stat-value">12</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">⏳</div>
          <div className="stat-content">
            <div className="stat-label">In Bearbeitung</div>
            <div className="stat-value">5</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">💎</div>
          <div className="stat-content">
            <div className="stat-label">Niedriger Bestand</div>
            <div className="stat-value">3</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">💰</div>
          <div className="stat-content">
            <div className="stat-label">Materialwert</div>
            <div className="stat-value">€15,420</div>
          </div>
        </div>
      </div>

      <div className="dashboard-sections">
        <section className="dashboard-section">
          <h2>Willkommen im Goldsmith ERP</h2>
          <p>
            Ihr zentrales System für Auftrags-, Material- und Kundenverwaltung.
          </p>
          <p className="status-message">
            ✅ System ist bereit und läuft
          </p>
        </section>

        <section className="dashboard-section">
          <h3>Nächste Schritte</h3>
          <ul className="next-steps">
            <li>📋 Aufträge verwalten</li>
            <li>💎 Materialbestand prüfen</li>
            <li>👥 Kunden anlegen</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
