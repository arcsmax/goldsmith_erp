// Order Context - Manages active orders and tab states
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { OrderType } from '../types';

// Tab types for order detail page
export type OrderTab = 'details' | 'materials' | 'status' | 'notes' | 'history' | 'time-tracking';

interface OrderTabState {
  orderId: number;
  activeTab: OrderTab;
  timestamp: number;
}

interface OrderContextType {
  activeOrders: Map<number, OrderType>;
  orderTabStates: Map<number, OrderTab>;
  setActiveOrder: (order: OrderType, tab?: OrderTab) => void;
  setOrderTab: (orderId: number, tab: OrderTab) => void;
  getOrderTab: (orderId: number) => OrderTab;
  removeActiveOrder: (orderId: number) => void;
  clearAllOrders: () => void;
}

const OrderContext = createContext<OrderContextType | undefined>(undefined);

interface OrderProviderProps {
  children: ReactNode;
}

const STORAGE_KEY = 'goldsmith_order_tabs';

/**
 * OrderProvider Component
 * Manages multiple active orders and their tab states
 * Persists tab states to localStorage for workflow continuity
 */
export const OrderProvider: React.FC<OrderProviderProps> = ({ children }) => {
  const [activeOrders, setActiveOrders] = useState<Map<number, OrderType>>(new Map());
  const [orderTabStates, setOrderTabStates] = useState<Map<number, OrderTab>>(new Map());

  // Load tab states from localStorage on mount
  useEffect(() => {
    const loadTabStates = () => {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const states: OrderTabState[] = JSON.parse(stored);
          const tabMap = new Map<number, OrderTab>();

          states.forEach((state) => {
            tabMap.set(state.orderId, state.activeTab);
          });

          setOrderTabStates(tabMap);
          console.log('Loaded order tab states:', tabMap.size, 'orders');
        }
      } catch (error) {
        console.error('Failed to load order tab states:', error);
      }
    };

    loadTabStates();
  }, []);

  // Save tab states to localStorage whenever they change
  useEffect(() => {
    try {
      const states: OrderTabState[] = [];
      orderTabStates.forEach((tab, orderId) => {
        states.push({
          orderId,
          activeTab: tab,
          timestamp: Date.now(),
        });
      });

      // Keep only last 50 orders to prevent storage overflow
      const sorted = states.sort((a, b) => b.timestamp - a.timestamp).slice(0, 50);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sorted));
    } catch (error) {
      console.error('Failed to save order tab states:', error);
    }
  }, [orderTabStates]);

  /**
   * Set active order and optionally specify tab
   * If no tab specified, uses last known tab or defaults to 'details'
   */
  const setActiveOrder = (order: OrderType, tab?: OrderTab) => {
    setActiveOrders((prev) => {
      const newMap = new Map(prev);
      newMap.set(order.id, order);
      return newMap;
    });

    if (tab) {
      setOrderTab(order.id, tab);
    } else if (!orderTabStates.has(order.id)) {
      // First time opening this order, default to 'details'
      setOrderTab(order.id, 'details');
    }
  };

  /**
   * Set active tab for specific order
   */
  const setOrderTab = (orderId: number, tab: OrderTab) => {
    setOrderTabStates((prev) => {
      const newMap = new Map(prev);
      newMap.set(orderId, tab);
      return newMap;
    });
  };

  /**
   * Get active tab for order (defaults to 'details')
   */
  const getOrderTab = (orderId: number): OrderTab => {
    return orderTabStates.get(orderId) || 'details';
  };

  /**
   * Remove order from active orders
   */
  const removeActiveOrder = (orderId: number) => {
    setActiveOrders((prev) => {
      const newMap = new Map(prev);
      newMap.delete(orderId);
      return newMap;
    });
  };

  /**
   * Clear all active orders (useful for logout)
   */
  const clearAllOrders = () => {
    setActiveOrders(new Map());
  };

  const value: OrderContextType = {
    activeOrders,
    orderTabStates,
    setActiveOrder,
    setOrderTab,
    getOrderTab,
    removeActiveOrder,
    clearAllOrders,
  };

  return <OrderContext.Provider value={value}>{children}</OrderContext.Provider>;
};

/**
 * useOrders Hook
 * Custom hook to access order context
 */
export const useOrders = (): OrderContextType => {
  const context = useContext(OrderContext);
  if (context === undefined) {
    throw new Error('useOrders must be used within an OrderProvider');
  }
  return context;
};
