import { useEffect, useRef, useCallback } from 'react';
import { useMarketStore } from '@/stores/marketStore';
import { useCostsStore } from '@/stores/costsStore';

const INITIAL_RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;

export function useWebSocket(userId: number | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case 'ticker':
        case 'market_update':
          if (data.data?.price) {
            useMarketStore.getState().setPrice(data.symbol, data.data.price);
          }
          break;
        case 'trade_update':
          break;
        case 'cost_update':
          if (data.costs) {
            const store = useCostsStore.getState();
            store.addLiveUpdate({
              cost_id: data.costs.cost_id,
              usd_cost: data.costs.usd_cost,
              model_name: data.costs.model_name,
              timestamp: data.costs.timestamp,
            });
            store.incrementModelCost(data.costs.model_name, data.costs.usd_cost);
          }
          break;
        case 'graph_execution':
          if (data.status === 'success' && data.cost_usd > 0) {
            const nodeLabel = data.node_label || 'llm';
            useCostsStore.getState().incrementModelCost(nodeLabel, data.cost_usd);
          }
          break;
        case 'pong':
          break;
      }
    } catch { /* ignore parse errors */ }
  }, []);

  const connect = useCallback(() => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/${userId}?token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectDelay.current = INITIAL_RECONNECT_DELAY;
      ws.send(JSON.stringify({ type: 'subscribe_ticker', symbol: 'BTCUSDT' }));
      ws.send(JSON.stringify({ type: 'subscribe_ticker', symbol: 'ETHUSDT' }));
      ws.send(JSON.stringify({ type: 'subscribe_ticker', symbol: 'SOLUSDT' }));
    };

    ws.onmessage = handleMessage;

    ws.onerror = () => {
      // onclose will fire after onerror, handling reconnection there
    };

    ws.onclose = (event) => {
      if (!event.wasClean) {
        if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
        reconnectTimer.current = setTimeout(() => {
          connect();
        }, reconnectDelay.current);
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY);
      }
    };
  }, [userId, handleMessage]);

  useEffect(() => {
    if (!userId) return;
    connect();

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [userId, connect]);

  return wsRef;
}