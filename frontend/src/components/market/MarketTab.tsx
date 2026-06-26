import { useEffect, useState } from 'react';
import { Search, ArrowUpCircle, ArrowDownCircle, Percent } from 'lucide-react';
import { marketApi, tradingApi } from '@/lib/api';
import { useMarketStore } from '@/stores/marketStore';
import { useTradingStore } from '@/stores/tradingStore';
import { CandlestickChart } from './CandlestickChart';
import toast from 'react-hot-toast';

export default function MarketTab() {
  const { watchlist, prices, selectedSymbol, setSelectedSymbol, addToWatchlist } = useMarketStore();
  const { portfolios, selectedPortfolioId, setPortfolios } = useTradingStore();
  const [search, setSearch] = useState('');
  const [allSymbols, setAllSymbols] = useState<string[]>([]);
  const [klines, setKlines] = useState<{ time: any; open: number; high: number; low: number; close: number }[]>([]);
  const [orderBook, setOrderBook] = useState<{ bids: number[][]; asks: number[][] } | null>(null);
  const [quantity, setQuantity] = useState('');
  const [tradeLoading, setTradeLoading] = useState(false);
  const [quantityPct, setQuantityPct] = useState(100);

  useEffect(() => {
    marketApi.getSymbols().then((res) => {
      setAllSymbols((res?.symbols ?? []).map((s: any) => s.symbol));
    }).catch(() => {});

    tradingApi.getPortfolios().then((res: any) => setPortfolios(res)).catch(() => {});
  }, [setPortfolios]);

  useEffect(() => {
    const fetchPrices = () => {
      watchlist.forEach((sym) => {
        marketApi.getPrice(sym).then((r) => {
          useMarketStore.getState().setPrice(sym, r.price);
        }).catch(() => {});
      });
    };
    fetchPrices();
    const iv = setInterval(fetchPrices, 5000);
    return () => clearInterval(iv);
  }, [watchlist]);

  useEffect(() => {
    if (!selectedSymbol) return;
    marketApi.getKlines(selectedSymbol, '1m', 200).then((res: any) => {
      const data = res.klines.map((k: any) => ({
        time: (Math.floor(k.open_time / 1000)) as any,
        open: k.open, high: k.high, low: k.low, close: k.close,
      }));
      setKlines(data);
    }).catch(() => {});
    marketApi.getOrderBook(selectedSymbol, 20).then((r: any) => {
      setOrderBook({ bids: r.bids, asks: r.asks });
    }).catch(() => {});
  }, [selectedSymbol]);

  useEffect(() => {
    if (!selectedSymbol || !selectedPortfolioId) return;
    tradingApi.getPositions(selectedPortfolioId).then((p: any) => {
      const pos = p.find((x: any) => x.symbol === selectedSymbol);
      if (pos && pos.quantity > 0) {
        setQuantity(pos.quantity.toFixed(4));
      } else {
        setQuantity('');
      }
    }).catch(() => {});
  }, [selectedSymbol, selectedPortfolioId]);

  const currentPrice = selectedSymbol ? prices[selectedSymbol] : null;

  const handleMarketOrder = async (side: string) => {
    if (!selectedPortfolioId || !selectedSymbol || !quantity) {
      toast.error('Select a portfolio and enter quantity');
      return;
    }
    const qty = parseFloat(quantity);
    if (isNaN(qty) || qty <= 0) { toast.error('Invalid quantity'); return; }

    setTradeLoading(true);
    try {
      const res: any = await tradingApi.marketOrder({
        symbol: selectedSymbol,
        side,
        quantity: qty,
        portfolio_id: selectedPortfolioId,
      });

      if (res.order.status === 'REJECTED') {
        toast.error(res.order.reject_reason || 'Order rejected');
      } else {
        toast.success(`${side} ${qty} ${selectedSymbol} filled @ $${res.order.filled_price?.toFixed(2)}`);
        setQuantity('');
        tradingApi.getPositions(selectedPortfolioId).then((p: any) => {
          useTradingStore.getState().setPositions(p);
        }).catch(() => {});
        tradingApi.getSummary(selectedPortfolioId).then((s: any) => {
          const updated = useTradingStore.getState().portfolios.map((pf) =>
            pf.id === selectedPortfolioId ? { ...pf, cash_balance: s.cash_balance, equity: s.equity } : pf
          );
          useTradingStore.getState().setPortfolios(updated);
        }).catch(() => {});
      }
    } catch (e: any) {
      toast.error(e.message || 'Trade failed');
    } finally {
      setTradeLoading(false);
    }
  };

  const setQtyFromPercent = (pct: number) => {
    setQuantityPct(pct);
    if (!selectedPortfolioId || !currentPrice) return;
    tradingApi.getSummary(selectedPortfolioId).then((s: any) => {
      const maxVal = s.cash_balance * (pct / 100);
      const qty = maxVal / currentPrice;
      setQuantity(qty.toFixed(4));
    }).catch(() => {});
  };

  const filtered = search ? allSymbols.filter((s) => s.toLowerCase().includes(search.toLowerCase())) : [];

  return (
    <div className="flex flex-col h-full">
      <div className="relative px-4 pt-2 pb-1">
        <Search className="absolute left-7 top-4 h-4 w-4 text-muted-foreground" />
        <input
          type="text" placeholder="Search symbols..." value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-card border border-border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
        />
        {filtered.length > 0 && (
          <div className="absolute top-full left-4 right-4 mt-1 bg-card border border-border rounded-lg shadow-lg z-50 max-h-48 overflow-auto">
            {filtered.slice(0, 20).map((s) => (
              <button key={s} onClick={() => { if (!watchlist.includes(s)) addToWatchlist(s); setSelectedSymbol(s); setSearch(''); }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-accent">
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Price tickers */}
      <div className="flex gap-2 px-4 py-1 overflow-x-auto">
        {watchlist.map((sym) => (
          <button key={sym} onClick={() => setSelectedSymbol(sym)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap ${
              selectedSymbol === sym ? 'bg-primary text-primary-foreground' : 'bg-card border border-border hover:bg-accent'
            }`}>
            {sym}
            <span className={prices[sym] !== undefined ? '' : 'hidden'}>
              ${prices[sym]?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 8 })}
            </span>
          </button>
        ))}
      </div>

      {selectedSymbol && (
        <div className="flex-1 flex flex-col min-h-0 overflow-auto px-4">
          <div className="flex items-center justify-between py-2">
            <div>
              <span className="text-lg font-bold">{selectedSymbol}</span>
              <span className="ml-2 text-xl text-primary">
                ${currentPrice?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 8 }) || '---'}
              </span>
            </div>
          </div>

          <div className="min-h-[220px] flex-shrink-0">
            <CandlestickChart data={klines} containerClassName="w-full h-[220px]" />
          </div>

          {/* Quick trade */}
          <div className="flex-shrink-0 bg-card border border-border rounded-lg p-3 my-2">
            {/* Portfolio selector */}
            <select
              value={selectedPortfolioId || ''}
              onChange={(e) => useTradingStore.getState().setSelectedPortfolio(e.target.value ? parseInt(e.target.value) : null)}
              className="w-full bg-black/30 border border-border rounded px-2 py-1.5 text-xs mb-2"
            >
              <option value="">-- Select Portfolio --</option>
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>{p.name} (${p.cash_balance?.toLocaleString(undefined, { maximumFractionDigits: 0 })})</option>
              ))}
            </select>

            {/* Quantity controls */}
            <div className="flex gap-2 items-center mb-2">
              <input
                type="number" step="any" value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="Quantity"
                className="flex-1 bg-black/30 border border-border rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <span className="text-xs text-muted-foreground">
                ≈ ${((parseFloat(quantity) || 0) * (currentPrice || 0)).toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
            </div>

            {/* Percentage quick picks */}
            <div className="flex gap-1 mb-2">
              {[25, 50, 75, 100].map((pct) => (
                <button key={pct}
                  onClick={() => setQtyFromPercent(pct)}
                  className={`flex-1 py-1 text-[10px] rounded border transition-colors ${
                    quantityPct === pct ? 'border-primary bg-primary/10 text-primary' : 'border-border hover:bg-accent'
                  }`}>
                  <Percent className="h-3 w-3 inline mr-0.5" />{pct}%
                </button>
              ))}
            </div>

            {/* Buy/Sell buttons */}
            <div className="flex gap-2">
              <button
                onClick={() => handleMarketOrder('BUY')}
                disabled={tradeLoading || !selectedPortfolioId}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
              >
                <ArrowUpCircle className="h-4 w-4" />
                Buy {selectedSymbol.replace('USDT', '')}
              </button>
              <button
                onClick={() => handleMarketOrder('SELL')}
                disabled={tradeLoading || !selectedPortfolioId}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
              >
                <ArrowDownCircle className="h-4 w-4" />
                Sell {selectedSymbol.replace('USDT', '')}
              </button>
            </div>
            {selectedPortfolioId && (
              <div className="mt-2 text-[10px] text-muted-foreground text-center">
                Portfolio: {portfolios.find(p => p.id === selectedPortfolioId)?.name} ·
                Cash: ${portfolios.find(p => p.id === selectedPortfolioId)?.cash_balance?.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
            )}
          </div>

          {/* Orderbook */}
          {orderBook && (
            <div className="grid grid-cols-2 gap-2 mb-3 text-xs flex-shrink-0">
              <div>
                <div className="text-muted-foreground mb-1">Bids</div>
                {orderBook.bids.slice(0, 5).map(([price, qty], i) => (
                  <div key={i} className="flex justify-between text-green-400">
                    <span>${price.toFixed(2)}</span>
                    <span>{qty.toFixed(4)}</span>
                  </div>
                ))}
              </div>
              <div>
                <div className="text-muted-foreground mb-1">Asks</div>
                {orderBook.asks.slice(0, 5).map(([price, qty], i) => (
                  <div key={i} className="flex justify-between text-red-400">
                    <span>${price.toFixed(2)}</span>
                    <span>{qty.toFixed(4)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}