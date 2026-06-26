import { create } from 'zustand';
import type { Node, Edge } from '@xyflow/react';

interface ModelGraphState {
  strategies: { id: number; name: string; is_active: boolean }[];
  selectedStrategyId: number | null;
  nodes: Node[];
  edges: Edge[];
  isExecuting: boolean;
  executingNodes: Set<string>;
  setStrategies: (s: { id: number; name: string; is_active: boolean }[]) => void;
  setSelectedStrategy: (id: number | null) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setIsExecuting: (v: boolean) => void;
  setExecutingNodes: (ids: Set<string>) => void;
  addExecutingNode: (id: string) => void;
  removeExecutingNode: (id: string) => void;
}

export const useModelGraphStore = create<ModelGraphState>((set) => ({
  strategies: [],
  selectedStrategyId: null,
  nodes: [],
  edges: [],
  isExecuting: false,
  executingNodes: new Set(),
  setStrategies: (strategies) => set({ strategies }),
  setSelectedStrategy: (id) => set({ selectedStrategyId: id }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setIsExecuting: (isExecuting) => set({ isExecuting }),
  setExecutingNodes: (ids) => set({ executingNodes: ids }),
  addExecutingNode: (id) =>
    set((state) => ({ executingNodes: new Set([...state.executingNodes, id]) })),
  removeExecutingNode: (id) =>
    set((state) => {
      const next = new Set(state.executingNodes);
      next.delete(id);
      return { executingNodes: next };
    }),
}));