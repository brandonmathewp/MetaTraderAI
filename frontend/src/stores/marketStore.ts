import { create } from 'zustand';

interface MarketState {
  symbols: { symbol: string; base_asset: string; quote_asset: string }[];
  watchlist: string[];
  prices: Record<string, number>;
  selectedSymbol: string | null;
  setSymbols: (s: { symbol: string; base_asset: string; quote_asset: string }[]) => void;
  setWatchlist: (w: string[]) => void;
  addToWatchlist: (symbol: string) => void;
  removeFromWatchlist: (symbol: string) => void;
  setPrice: (symbol: string, price: number) => void;
  setSelectedSymbol: (s: string | null) => void;
}

export const useMarketStore = create<MarketState>((set) => ({
  symbols: [],
  watchlist: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'],
  prices: {},
  selectedSymbol: null,
  setSymbols: (symbols) => set({ symbols }),
  setWatchlist: (watchlist) => set({ watchlist }),
  addToWatchlist: (symbol) =>
    set((state) => ({
      watchlist: state.watchlist.includes(symbol) ? state.watchlist : [...state.watchlist, symbol],
    })),
  removeFromWatchlist: (symbol) =>
    set((state) => ({ watchlist: state.watchlist.filter((s) => s !== symbol) })),
  setPrice: (symbol, price) =>
    set((state) => ({ prices: { ...state.prices, [symbol]: price } })),
  setSelectedSymbol: (s) => set({ selectedSymbol: s }),
}));