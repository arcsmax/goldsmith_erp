import React, { useEffect, useState } from 'react';
import OrderList from './components/OrderList';
import { OrderType } from './types';

const App: React.FC = () => {
  const [orders, setOrders] = useState<OrderType[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const wsRef = React.useRef<WebSocket | null>(null);

  useEffect(() => {
    // Fetch initial orders
    const fetchOrders = async () => {
      try {
        const response = await fetch('/api/v1/orders/');
        if (!response.ok) {
          throw new Error(`HTTP error! Status: ${response.status}`);
        }
        const data = await response.json();
        setOrders(data);
      } catch (err) {
        setError('Failed to fetch orders. Please try again later.');
        console.error('Error fetching orders:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchOrders();

    // Setup WebSocket connection
    const wsUrl = `ws://${window.location.host}/ws/orders`;
    wsRef.current = new WebSocket(wsUrl);
    
    wsRef.current.onopen = () => {
      console.log('WebSocket connection established');
    };
    
    wsRef.current.onmessage = (event) => {
      console.log('WebSocket message received:', event.data);
      // Refresh orders data when we get an update
      fetchOrders();
    };
    
    wsRef.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    wsRef.current.onclose = () => {
      console.log('WebSocket connection closed');
    };

    // Cleanup function
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Goldsmith ERP</h1>
      </header>
      
      <main className="app-main">
        {loading ? (
          <p>Loading orders...</p>
        ) : error ? (
          <p className="error-message">{error}</p>
        ) : (
          <OrderList orders={orders} />
        )}
      </main>
      
      <footer className="app-footer">
        <p>&copy; 2025 Goldsmith ERP</p>
      </footer>
    </div>
  );
};

export default App;