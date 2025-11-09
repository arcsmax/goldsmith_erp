// QR/NFC Scanner Page
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useOrders, useTimeTracking } from '../contexts';
import { ordersApi } from '../api';
import { OrderType } from '../types';
import QuickActionModal from '../components/QuickActionModal';
import '../styles/scanner.css';

export const ScannerPage: React.FC = () => {
  const navigate = useNavigate();
  const { setActiveOrder, getOrderTab, setOrderTab } = useOrders();
  const { startTracking } = useTimeTracking();
  const [scanInput, setScanInput] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastScanned, setLastScanned] = useState<Array<{ id: number; time: string }>>([]);
  const [scannedOrder, setScannedOrder] = useState<OrderType | null>(null);
  const [showQuickActions, setShowQuickActions] = useState(false);

  // Auto-focus on scan input when page loads
  useEffect(() => {
    const input = document.getElementById('scan-input');
    if (input) {
      input.focus();
    }

    // Load last scanned orders from localStorage
    const saved = localStorage.getItem('last_scanned_orders');
    if (saved) {
      try {
        setLastScanned(JSON.parse(saved));
      } catch (e) {
        console.error('Failed to load last scanned orders');
      }
    }
  }, []);

  const handleScan = async (orderId: string) => {
    if (!orderId || isScanning) return;

    const id = parseInt(orderId.trim());
    if (isNaN(id)) {
      setError('Ungültige Auftragsnummer');
      return;
    }

    try {
      setIsScanning(true);
      setError(null);

      // Fetch order from API
      const order = await ordersApi.getById(id);

      // Get last active tab for this order
      const activeTab = getOrderTab(id);

      // Register order in context
      setActiveOrder(order);

      // Save to last scanned
      const newScanned = [
        { id, time: new Date().toLocaleTimeString('de-DE') },
        ...lastScanned.filter((s) => s.id !== id).slice(0, 9), // Keep last 10
      ];
      setLastScanned(newScanned);
      localStorage.setItem('last_scanned_orders', JSON.stringify(newScanned));

      // Show quick actions modal
      console.log(`📱 Scanned Order #${id} → Showing quick actions`);
      setScannedOrder(order);
      setShowQuickActions(true);
      setScanInput(''); // Clear input for next scan
    } catch (err: any) {
      setError(
        err.response?.status === 404
          ? `Auftrag #${id} nicht gefunden`
          : 'Fehler beim Laden des Auftrags'
      );
      setScanInput('');
    } finally {
      setIsScanning(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleScan(scanInput);
    }
  };

  const handleQuickAccess = (orderId: number) => {
    setScanInput(orderId.toString());
    handleScan(orderId.toString());
  };

  // Quick Action Modal Handlers
  const handleCloseModal = () => {
    setShowQuickActions(false);
    setScannedOrder(null);
  };

  const handleStartTimeTracking = async (activityId: number, location?: string) => {
    if (!scannedOrder) return;

    try {
      await startTracking(scannedOrder.id, activityId, location);
      // Navigate to order page after starting tracking
      const activeTab = getOrderTab(scannedOrder.id);
      navigate(`/orders/${scannedOrder.id}`);
    } catch (err) {
      console.error('Failed to start tracking from scanner:', err);
      throw err; // Let modal handle the error
    }
  };

  const handleChangeLocation = async (location: string) => {
    if (!scannedOrder) return;

    try {
      // TODO: Implement location change API call
      console.log(`Change location for order #${scannedOrder.id} to ${location}`);
      // Navigate to order page
      navigate(`/orders/${scannedOrder.id}`);
    } catch (err) {
      console.error('Failed to change location:', err);
      throw err;
    }
  };

  const handleViewMaterials = () => {
    if (!scannedOrder) return;

    // Set the active tab to materials and navigate
    setOrderTab(scannedOrder.id, 'materials');
    navigate(`/orders/${scannedOrder.id}`);
  };

  return (
    <div className="scanner-container">
      <div className="scanner-box">
        <div className="scanner-icon">📷</div>
        <h1>QR/NFC Scanner</h1>
        <p className="scanner-subtitle">
          Scannen Sie den QR-Code oder NFC-Tag des Auftrags
        </p>

        {/* Scan Input */}
        <div className="scan-input-group">
          <input
            id="scan-input"
            type="text"
            value={scanInput}
            onChange={(e) => setScanInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Auftragsnummer eingeben oder scannen..."
            className="scan-input"
            autoFocus
            disabled={isScanning}
          />
          <button
            onClick={() => handleScan(scanInput)}
            disabled={!scanInput || isScanning}
            className="btn-scan"
          >
            {isScanning ? 'Lädt...' : 'Öffnen'}
          </button>
        </div>

        {/* Error Message */}
        {error && <div className="scan-error">{error}</div>}

        {/* Info Box */}
        <div className="scan-info">
          <h3>💡 So funktioniert's:</h3>
          <ol>
            <li>QR-Code mit Smartphone-Kamera scannen</li>
            <li>Oder NFC-Tag an Lesegerät halten</li>
            <li>Oder Auftragsnummer manuell eingeben</li>
            <li>Auftrag öffnet sich mit dem zuletzt aktiven Tab</li>
          </ol>
        </div>

        {/* Last Scanned Orders */}
        {lastScanned.length > 0 && (
          <div className="last-scanned">
            <h3>Zuletzt gescannt:</h3>
            <div className="scanned-list">
              {lastScanned.map((item) => (
                <button
                  key={item.id}
                  className="scanned-item"
                  onClick={() => handleQuickAccess(item.id)}
                >
                  <span className="scanned-id">#{item.id}</span>
                  <span className="scanned-time">{item.time}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Manual Input Note */}
        <p className="manual-note">
          Für Tests: Geben Sie eine Auftragsnummer ein (z.B. "1", "2", "3")
        </p>
      </div>

      {/* Quick Action Modal */}
      {showQuickActions && scannedOrder && (
        <QuickActionModal
          order={scannedOrder}
          onClose={handleCloseModal}
          onStartTimeTracking={handleStartTimeTracking}
          onChangeLocation={handleChangeLocation}
          onViewMaterials={handleViewMaterials}
        />
      )}
    </div>
  );
};
