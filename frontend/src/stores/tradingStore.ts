import { create } from 'zustand';

interface Portfolio {
  id: number;
  name: string;
  initial_balance: number;
  cash_balance: number;
  equity: number;
}

interface Position {
  id: number;
  symbol: string;
  quantity: number;
  avg_entry: number;
  current_price: number;
  unrealized_pnl: number;
}

interface Trade {
  id: number;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  confidence: number | null;
  outcome_pnl: number | null;
  status: string;
  created_at: string;
  closed_at: string | null;
}

interface TradingState {
  portfolios: Portfolio[];
  positions: Position[];
  trades: Trade[];
  selectedPortfolioId: number | null;
  setPortfolios: (portfolios: Portfolio[]) => void;
  setPositions: (positions: Position[]) => void;
  setTrades: (trades: Trade[]) => void;
  setSelectedPortfolio: (id: number | null) => void;
}

export const useTradingStore = create<TradingState>((set) => ({
  portfolios: [],
  positions: [],
  trades: [],
  selectedPortfolioId: null,
  setPortfolios: (portfolios) => set({ portfolios }),
  setPositions: (positions) => set({ positions }),
  setTrades: (trades) => set({ trades }),
  setSelectedPortfolio: (id) => set({ selectedPortfolioId: id }),
}));