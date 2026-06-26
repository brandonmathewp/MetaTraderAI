import { useEffect, useRef, useCallback } from 'react';
import { useMarketStore } from '@/stores/marketStore';
import { useCostsStore } from '@/stores/costsStore';
import { useTradingStore } from '@/stores/tradingStore';
import { useModelGraphStore } from '@/stores/modelGraphStore';

export function useWebSocket(userId: number | null) {
  const wsRef = useRef<WebSocket | null>(null);

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
    } catch {}
  }, []);

  useEffect(() => {
    if (!userId) return;

    const token = localStorage.getItem('access_token');
    if (!token) return;

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/${userId}?token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'subscribe_ticker', symbol: 'BTCUSDT' }));
      ws.send(JSON.stringify({ type: 'subscribe_ticker', symbol: 'ETHUSDT' }));
      ws.send(JSON.stringify({ type: 'subscribe_ticker', symbol: 'SOLUSDT' }));
    };

    ws.onmessage = handleMessage;

    const pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      ws.close();
    };
  }, [userId, handleMessage]);

  return wsRef;
}