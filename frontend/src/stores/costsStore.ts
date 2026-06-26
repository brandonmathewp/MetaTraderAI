import { create } from 'zustand';

interface CostEntry {
  model: string;
  calls: number;
  request_tokens: number;
  response_tokens: number;
  cost: number;
}

interface StrategyCost {
  strategy_id: number | null;
  strategy_name: string;
  total_cost: number;
  calls: number;
}

interface Budget {
  id: number;
  model_name: string;
  max_usd_per_day: number;
  current_usd_spent: number;
  usage_pct: number;
}

interface CostHistory {
  date: string;
  total_cost: number;
  calls: number;
}

interface LiveCostUpdate {
  cost_id: number;
  usd_cost: number;
  model_name: string;
  timestamp: string;
}

interface CostsState {
  todayCosts: CostEntry[];
  overallCost: number;
  overallCalls: number;
  strategyCosts: StrategyCost[];
  predictiveCost: number;
  predictive7d: number;
  predictive30d: number;
  budgets: Budget[];
  costHistory: CostHistory[];
  modelRates: Record<string, { input: number; output: number }>;
  recentUpdates: LiveCostUpdate[];
  lastUpdate: number;
  setTodayCosts: (entries: CostEntry[], overall: number, calls: number) => void;
  setStrategyCosts: (s: StrategyCost[]) => void;
  setPredictiveCost: (v: number) => void;
  setPredictives: (d7: number, d30: number) => void;
  setBudgets: (b: Budget[]) => void;
  setCostHistory: (h: CostHistory[]) => void;
  setModelRates: (r: Record<string, { input: number; output: number }>) => void;
  addLiveUpdate: (u: LiveCostUpdate) => void;
  incrementModelCost: (model: string, cost: number) => void;
}

export const useCostsStore = create<CostsState>((set) => ({
  todayCosts: [],
  overallCost: 0,
  overallCalls: 0,
  strategyCosts: [],
  predictiveCost: 0,
  predictive7d: 0,
  predictive30d: 0,
  budgets: [],
  costHistory: [],
  modelRates: {},
  recentUpdates: [],
  lastUpdate: 0,
  setTodayCosts: (entries, overall, calls) =>
    set({ todayCosts: entries, overallCost: overall, overallCalls: calls, lastUpdate: Date.now() }),
  setStrategyCosts: (strategyCosts) => set({ strategyCosts }),
  setPredictiveCost: (predictiveCost) => set({ predictiveCost }),
  setPredictives: (d7, d30) => set({ predictive7d: d7, predictive30d: d30 }),
  setBudgets: (budgets) => set({ budgets }),
  setCostHistory: (costHistory) => set({ costHistory }),
  setModelRates: (modelRates) => set({ modelRates }),
  addLiveUpdate: (update) =>
    set((state) => ({
      recentUpdates: [update, ...state.recentUpdates].slice(0, 20),
      lastUpdate: Date.now(),
    })),
  incrementModelCost: (model, cost) =>
    set((state) => {
      const updated = state.todayCosts.map((c) =>
        c.model === model ? { ...c, cost: c.cost + cost, calls: c.calls + 1 } : c
      );
      const exists = state.todayCosts.some((c) => c.model === model);
      if (!exists) {
        updated.push({ model, calls: 1, request_tokens: 0, response_tokens: 0, cost });
      }
      return {
        todayCosts: updated,
        overallCost: state.overallCost + cost,
        overallCalls: state.overallCalls + 1,
        lastUpdate: Date.now(),
      };
    }),
}));