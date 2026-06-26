import { useState, useCallback, useEffect } from 'react';
import Editor, { type OnMount } from '@monaco-editor/react';
import {
  Play, Save, FileCode, Trash2, FolderOpen, Plus,
  RefreshCw, CheckCircle, XCircle,
} from 'lucide-react';
import { scriptsApi, tradingApi } from '@/lib/api';
import toast from 'react-hot-toast';

interface ScriptMeta {
  id: number;
  name: string;
  code_preview: string;
  created_at: string | null;
  updated_at: string | null;
}

interface Template {
  name: string;
  description: string;
  code: string;
}

export default function EditorTab() {
  const [code, setCode] = useState('');
  const [output, setOutput] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [scriptName, setScriptName] = useState('untitled');
  const [scriptId, setScriptId] = useState<number | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  const [savedScripts, setSavedScripts] = useState<ScriptMeta[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [portfolios, setPortfolios] = useState<{ id: number; name: string }[]>([]);
  const [validating, setValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<{ valid: boolean; functions: string[]; symbols: string[] } | null>(null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    scriptsApi.getTemplates().then((r: any) => {
      setTemplates(r);
      if (r?.length > 0) {
        setCode(r[0].code);
        setScriptName(r[0].name);
      }
    }).catch(() => {});
    tradingApi.getPortfolios().then((r: any) => setPortfolios(r)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!showSaved) return;
    scriptsApi.list().then((r: any) => setSavedScripts(r)).catch(() => {});
  }, [showSaved]);

  const handleEditorMount: OnMount = (editor, monaco) => {
    monaco.languages.registerCompletionItemProvider('python', {
      triggerCharacters: ['.', '('],
      provideCompletionItems: (model: any, position: any) => {
        const word = model.getWordUntilPosition(position);
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        };

        const snippets = [
          { label: 'market.get_price', insertText: "await market.get_price(symbol=\"${1:BTCUSDT}\")", detail: "Get current price", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'market.get_indicator', insertText: "await market.get_indicator(symbol=\"${1:BTCUSDT}\", \"${2:RSI}\", period=${3:14})", detail: "Get technical indicator", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'market.get_klines', insertText: "await market.get_klines(symbol=\"${1:BTCUSDT}\", interval=\"${2:5m}\", limit=${3:100})", detail: "Get candlestick data", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'market.get_orderbook', insertText: "await market.get_orderbook(symbol=\"${1:BTCUSDT}\", depth=${2:20})", detail: "Get order book", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'model.predict', insertText: "await model.predict(name=\"${1:gpt-4o-mini}\", prompt=\"${2:Analyze market}\", context=${3:{}})", detail: "Call LLM for prediction", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'portfolio.get_balance', insertText: "await portfolio.get_balance()", detail: "Get cash balance", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'portfolio.get_positions', insertText: "await portfolio.get_positions()", detail: "Get all positions", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'portfolio.get_pnl', insertText: "await portfolio.get_pnl()", detail: "Get profit/loss", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'portfolio.get_equity', insertText: "await portfolio.get_equity()", detail: "Get total equity", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'trade.buy', insertText: "await trade.buy(symbol=\"${1:BTCUSDT}\", quantity=${2:0.01})", detail: "Execute buy order", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'trade.sell', insertText: "await trade.sell(symbol=\"${1:BTCUSDT}\", quantity=${2:0.01})", detail: "Execute sell order", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'trade.set_stop_loss', insertText: "await trade.set_stop_loss(symbol=\"${1:BTCUSDT}\", price=${2:0})", detail: "Set stop loss", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'trade.set_take_profit', insertText: "await trade.set_take_profit(symbol=\"${1:BTCUSDT}\", price=${2:0})", detail: "Set take profit", kind: monaco.languages.CompletionItemKind.Function },
          { label: 'async def run', insertText: "async def run():\n    ${1}", detail: "Define async run function", kind: monaco.languages.CompletionItemKind.Keyword },
          { label: 'result = await run', insertText: "result = await run()", detail: "Execute the run function", kind: monaco.languages.CompletionItemKind.Keyword },
          { label: 'print', insertText: 'print(${1:message})', detail: "Print to output console", kind: monaco.languages.CompletionItemKind.Function },
        ];

        return { suggestions: snippets.map((s) => ({ ...s, range, insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet })) };
      },
    });

    // Add Ctrl+S handler
    editor.addAction({
      id: 'save-script',
      label: 'Save Script',
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS],
      run: () => handleSave(),
    });
  };

  const runScript = useCallback(async () => {
    setRunning(true);
    setOutput((o) => [...o, `[RUN] ${new Date().toLocaleTimeString()} Executing "${scriptName}"...`]);
    try {
      const res: any = await scriptsApi.execute({
        code,
        portfolio_id: portfolioId || undefined,
      });

      if (res.validation_failed) {
        setOutput((o) => [...o, `[VALIDATION FAILED]`, ...res.errors.map((e: string) => `  ✗ ${e}`)]);
        toast.error('Script validation failed');
      } else if (res.errors?.length > 0) {
        setOutput((o) => [...o, `[ERROR]`, ...res.errors.map((e: string) => `  ${e}`)]);
        toast.error('Script execution failed');
      } else {
        if (res.output) {
          setOutput((o) => [...o, ...res.output.split('\n')]);
        }
        if (res.result) {
          setOutput((o) => [...o, `[RESULT] ${JSON.stringify(res.result, null, 2)}`]);
        }
        setOutput((o) => [...o, `[OK] Completed in ${res.elapsed_ms}ms`]);
        toast.success(`Completed in ${res.elapsed_ms}ms`);
      }
    } catch (e: any) {
      setOutput((o) => [...o, `[FATAL] ${e.message || 'Unknown error'}`]);
      toast.error(e.message || 'Execution failed');
    } finally {
      setRunning(false);
    }
  }, [code, scriptName, portfolioId]);

  const handleSave = async () => {
    try {
      if (scriptId) {
        await scriptsApi.update(scriptId, { name: scriptName, python_code: code });
        toast.success(`Updated "${scriptName}"`);
      } else {
        const res: any = await scriptsApi.create({ name: scriptName, python_code: code });
        setScriptId(res.id);
        toast.success(`Saved "${scriptName}"`);
      }
      setDirty(false);
    } catch (e: any) {
      try {
        const body = JSON.parse(e.message);
        if (body.errors) {
          toast.error(`Validation: ${body.errors[0]}`);
        } else {
          toast.error(e.message || 'Save failed');
        }
      } catch {
        toast.error(e.message || 'Save failed');
      }
    }
  };

  const handleValidate = async () => {
    setValidating(true);
    try {
      const res: any = await scriptsApi.validate(code);
      setValidationResult(res);
      if (res.valid) {
        toast.success(`Valid — ${res.functions?.length || 0} functions, ${res.symbols?.length || 0} symbols`);
      } else {
        toast.error(`Invalid: ${res.errors?.[0] || 'Unknown error'}`);
      }
    } catch (e: any) {
      toast.error(e.message || 'Validation failed');
    } finally {
      setValidating(false);
    }
  };

  const handleLoad = async (id: number) => {
    try {
      const res: any = await scriptsApi.get(id);
      setCode(res.python_code);
      setScriptName(res.name);
      setScriptId(res.id);
      setShowSaved(false);
      setDirty(false);
      toast.success(`Loaded "${res.name}"`);
    } catch (e: any) {
      toast.error(e.message || 'Load failed');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this script?')) return;
    try {
      await scriptsApi.delete(id);
      if (scriptId === id) {
        setScriptId(null);
        setScriptName('untitled');
      }
      setShowSaved(false);
      toast.success('Script deleted');
    } catch (e: any) {
      toast.error(e.message || 'Delete failed');
    }
  };

  const handleNew = () => {
    setCode('');
    setScriptName('untitled');
    setScriptId(null);
    setOutput([]);
    setDirty(false);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-border">
        <input
          value={scriptName}
          onChange={(e) => { setScriptName(e.target.value); setDirty(true); }}
          className={`bg-transparent border-none outline-none text-sm font-medium flex-1 min-w-0 ${dirty ? 'text-yellow-400' : ''}`}
          title={dirty ? 'Unsaved changes' : ''}
        />

        {/* Portfolio selector */}
        <select
          value={portfolioId || ''}
          onChange={(e) => setPortfolioId(e.target.value ? parseInt(e.target.value) : null)}
          className="bg-card border border-border rounded px-1.5 py-1 text-[10px] w-16 flex-shrink-0"
          title="Portfolio for execution"
        >
          <option value="">None</option>
          {portfolios.map((p) => (
            <option key={p.id} value={p.id}>{p.name.slice(0, 4)}</option>
          ))}
        </select>

        <button onClick={handleValidate} disabled={validating} className={`p-1.5 rounded ${validating ? 'text-muted-foreground' : 'text-blue-400 hover:bg-blue-400/10'}`} title="Validate">
          <CheckCircle className="h-3.5 w-3.5" />
        </button>
        <button onClick={handleSave} className="p-1.5 hover:bg-accent rounded" title="Save (Ctrl+S)">
          <Save className="h-3.5 w-3.5" />
        </button>
        <button onClick={() => setShowSaved(!showSaved)} className="p-1.5 hover:bg-accent rounded" title="Load">
          <FolderOpen className="h-3.5 w-3.5" />
        </button>
        <button onClick={() => setShowTemplates(!showTemplates)} className="p-1.5 hover:bg-accent rounded" title="Templates">
          <FileCode className="h-3.5 w-3.5" />
        </button>
        <button onClick={handleNew} className="p-1.5 hover:bg-accent rounded" title="New">
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button onClick={runScript} disabled={running}
          className={`p-1.5 rounded ${running ? 'text-muted-foreground' : 'text-green-400 hover:bg-green-400/10'}`}
          title="Run (Ctrl+Enter)"
        >
          {running ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Templates */}
      {showTemplates && (
        <div className="border-b border-border bg-card px-3 py-2">
          <div className="text-xs text-muted-foreground mb-1.5">Templates</div>
          <div className="flex gap-2 overflow-x-auto">
            {templates.map((t) => (
              <button
                key={t.name}
                onClick={() => { setCode(t.code); setScriptName(t.name); setShowTemplates(false); setDirty(true); }}
                className="px-2.5 py-1.5 text-xs rounded border border-border hover:bg-accent whitespace-nowrap flex-shrink-0"
                title={t.description}
              >
                {t.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Saved scripts */}
      {showSaved && (
        <div className="border-b border-border bg-card px-3 py-2 max-h-48 overflow-auto">
          <div className="text-xs text-muted-foreground mb-1.5">Saved Scripts</div>
          {savedScripts.length === 0 ? (
            <div className="text-xs text-muted-foreground">No saved scripts</div>
          ) : (
            savedScripts.map((s) => (
              <div key={s.id} className="flex items-center gap-2 py-1.5 border-b border-border/30 last:border-b-0">
                <button onClick={() => handleLoad(s.id)} className="flex-1 text-left text-xs truncate hover:text-primary">
                  {s.name}
                  <span className="text-muted-foreground ml-2 text-[10px]">
                    {s.updated_at ? new Date(s.updated_at).toLocaleDateString() : ''}
                  </span>
                </button>
                <button onClick={() => handleDelete(s.id)} className="p-0.5 hover:bg-red-500/20 rounded text-red-400/60 hover:text-red-400">
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {/* Validation result */}
      {validationResult && (
        <div className={`border-b px-3 py-1.5 text-xs flex items-center gap-2 ${validationResult.valid ? 'bg-green-500/5 border-green-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
          {validationResult.valid ? (
            <CheckCircle className="h-3 w-3 text-green-400" />
          ) : (
            <XCircle className="h-3 w-3 text-red-400" />
          )}
          <span className={validationResult.valid ? 'text-green-400' : 'text-red-400'}>
            {validationResult.valid
              ? `Valid — ${validationResult.functions.length} fns, ${validationResult.symbols.length} symbols`
              : 'Script has errors'}
          </span>
        </div>
      )}

      {/* Editor */}
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          defaultLanguage="python"
          value={code}
          onChange={(v) => { setCode(v || ''); setDirty(true); }}
          onMount={handleEditorMount}
          theme="vs-dark"
          options={{
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            minimap: { enabled: false },
            lineNumbers: 'on',
            wordWrap: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 4,
            insertSpaces: true,
            suggestOnTriggerCharacters: true,
            quickSuggestions: true,
            snippetSuggestions: 'top',
          }}
        />
      </div>

      {/* Output console */}
      <div className="border-t border-border bg-black/50" style={{ maxHeight: '30%' }}>
        <div className="flex items-center justify-between px-3 py-1 border-b border-border/50">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Output</span>
            {output.length > 0 && <span className="text-[10px] text-muted-foreground">({output.length} lines)</span>}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => {
                const text = output.join('\n');
                navigator.clipboard.writeText(text);
                toast.success('Output copied');
              }}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Copy
            </button>
            <button onClick={() => setOutput([])} className="text-xs text-muted-foreground hover:text-foreground">
              Clear
            </button>
          </div>
        </div>
        <div className="p-2 text-xs font-mono space-y-0.5 overflow-auto max-h-[25vh]">
          {output.length === 0 && (
            <span className="text-muted-foreground">Click ▶ to run script. Output appears here.</span>
          )}
          {output.map((line, i) => {
            const isError = line.includes('[ERROR]') || line.includes('[ERR]') || line.includes('[FATAL]') || line.includes('[VALIDATION FAILED]');
            const isSuccess = line.includes('[OK]');
            const isOutput = line.includes('[OUT]');
            const isRun = line.includes('[RUN]');
            const isResult = line.includes('[RESULT]');
            return (
              <div key={i} className={
                isError ? 'text-red-400' :
                isSuccess ? 'text-green-400' :
                isRun ? 'text-blue-400' :
                isOutput ? 'text-foreground/80' :
                isResult ? 'text-yellow-400' :
                'text-muted-foreground'
              }>
                {line}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}