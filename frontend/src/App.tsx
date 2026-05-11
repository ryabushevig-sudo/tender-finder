import { useCallback, useEffect, useMemo, useState } from "react";
import {
  deleteDocument,
  exportDocument,
  extractItems,
  getDocument,
  getLlmHealth,
  listDocuments,
  searchForItem,
  uploadDocument,
  type DocumentDetail,
  type DocumentSummary,
  type Item,
  type LlmHealth,
} from "./api";
import { UploadBox } from "./components/UploadBox";
import { DocumentList } from "./components/DocumentList";
import { ItemsTable } from "./components/ItemsTable";
import { Header } from "./components/Header";

export default function App() {
  const [llm, setLlm] = useState<LlmHealth | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<DocumentDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searchingItems, setSearchingItems] = useState<Set<string>>(new Set());

  const refreshDocuments = useCallback(async () => {
    try {
      const list = await listDocuments();
      setDocuments(list);
      return list;
    } catch (e) {
      setError(`Не удалось получить список документов: ${(e as Error).message}`);
      return [];
    }
  }, []);

  const refreshSelected = useCallback(async (id: string) => {
    try {
      const doc = await getDocument(id);
      setSelected(doc);
    } catch (e) {
      setError(`Не удалось получить документ: ${(e as Error).message}`);
    }
  }, []);

  useEffect(() => {
    refreshDocuments();
    getLlmHealth()
      .then(setLlm)
      .catch(() =>
        setLlm({ provider: "unknown", model: "unknown", healthy: false }),
      );
  }, [refreshDocuments]);

  useEffect(() => {
    if (selectedId) {
      refreshSelected(selectedId);
    } else {
      setSelected(null);
    }
  }, [selectedId, refreshSelected]);

  const handleUpload = async (file: File) => {
    setBusy("Загружаю и парсю документ…");
    setError(null);
    try {
      const doc = await uploadDocument(file);
      await refreshDocuments();
      setSelectedId(doc.id);
    } catch (e) {
      setError(`Загрузка не удалась: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const handleExtract = async () => {
    if (!selectedId) return;
    setBusy("Извлекаю позиции через LLM (может занять минуту)…");
    setError(null);
    try {
      await extractItems(selectedId);
      await refreshSelected(selectedId);
      await refreshDocuments();
    } catch (e) {
      setError(`Извлечение не удалось: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const handleDeleteDoc = async (id: string) => {
    if (!confirm("Удалить документ?")) return;
    await deleteDocument(id);
    if (selectedId === id) {
      setSelectedId(null);
    }
    await refreshDocuments();
  };

  const handleExport = async () => {
    if (!selectedId || !selected) return;
    const blob = await exportDocument(selectedId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selected.filename.replace(/\.[^.]+$/, "")}_подбор.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleSearch = async (item: Item) => {
    if (!selectedId) return;
    setSearchingItems((s) => new Set(s).add(item.id));
    setError(null);
    try {
      await searchForItem(item.id);
      await refreshSelected(selectedId);
    } catch (e) {
      setError(`Поиск не удался для "${item.name}": ${(e as Error).message}`);
    } finally {
      setSearchingItems((s) => {
        const next = new Set(s);
        next.delete(item.id);
        return next;
      });
    }
  };

  const handleSearchAll = async () => {
    if (!selected) return;
    setBusy(`Поиск по ${selected.items.length} позициям…`);
    setError(null);
    try {
      for (const item of selected.items) {
        try {
          await searchForItem(item.id);
        } catch (e) {
          console.warn("Search failed for", item.id, e);
        }
      }
      if (selectedId) await refreshSelected(selectedId);
    } finally {
      setBusy(null);
    }
  };

  const handleItemUpdated = useCallback(() => {
    if (selectedId) refreshSelected(selectedId);
  }, [selectedId, refreshSelected]);

  const llmBadge = useMemo(() => {
    if (!llm) return null;
    const color = llm.healthy ? "bg-emerald-100 text-emerald-700 border-emerald-300" : "bg-amber-100 text-amber-700 border-amber-300";
    const label = llm.healthy ? "online" : "offline";
    return (
      <span className={`px-2 py-1 text-xs border rounded-md ${color}`}>
        LLM: {llm.provider} / {llm.model} ({label})
      </span>
    );
  }, [llm]);

  return (
    <div className="min-h-full flex flex-col">
      <Header llmBadge={llmBadge} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-6 grid grid-cols-12 gap-6">
        <aside className="col-span-12 lg:col-span-4 xl:col-span-3 space-y-4">
          <UploadBox onUpload={handleUpload} disabled={!!busy} />
          <DocumentList
            documents={documents}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onDelete={handleDeleteDoc}
          />
        </aside>

        <section className="col-span-12 lg:col-span-8 xl:col-span-9 space-y-4">
          {error && (
            <div className="rounded-md border border-rose-300 bg-rose-50 text-rose-800 px-4 py-3 text-sm">
              {error}
            </div>
          )}
          {busy && (
            <div className="rounded-md border border-blue-300 bg-blue-50 text-blue-800 px-4 py-3 text-sm flex items-center gap-2">
              <Spinner /> {busy}
            </div>
          )}

          {!selected && !busy && (
            <EmptyState />
          )}

          {selected && (
            <DocumentPanel
              document={selected}
              busy={!!busy}
              searchingItems={searchingItems}
              onExtract={handleExtract}
              onExport={handleExport}
              onSearchAll={handleSearchAll}
              onSearchItem={handleSearch}
              onItemUpdated={handleItemUpdated}
            />
          )}
        </section>
      </main>

      <footer className="text-center text-xs text-gray-500 py-4">
        Tender Finder · локальная утилита для подбора товаров по ТЗ
      </footer>
    </div>
  );
}

function DocumentPanel({
  document,
  busy,
  searchingItems,
  onExtract,
  onExport,
  onSearchAll,
  onSearchItem,
  onItemUpdated,
}: {
  document: DocumentDetail;
  busy: boolean;
  searchingItems: Set<string>;
  onExtract: () => void;
  onExport: () => void;
  onSearchAll: () => void;
  onSearchItem: (item: Item) => void;
  onItemUpdated: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-gray-200 bg-white p-4 flex flex-wrap items-center gap-3 justify-between">
        <div>
          <div className="font-semibold text-gray-900">{document.filename}</div>
          <div className="text-xs text-gray-500">
            Статус: {document.status} · позиций: {document.items.length}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="px-3 py-2 text-sm rounded-md border border-blue-500 bg-blue-500 text-white disabled:opacity-50 hover:bg-blue-600"
            onClick={onExtract}
            disabled={busy}
          >
            {document.items.length ? "Переизвлечь позиции" : "Извлечь позиции"}
          </button>
          <button
            className="px-3 py-2 text-sm rounded-md border border-emerald-500 bg-emerald-500 text-white disabled:opacity-50 hover:bg-emerald-600"
            onClick={onSearchAll}
            disabled={busy || document.items.length === 0}
          >
            Найти поставщиков по всем
          </button>
          <button
            className="px-3 py-2 text-sm rounded-md border border-gray-300 hover:bg-gray-50"
            onClick={onExport}
            disabled={document.items.length === 0}
          >
            Экспорт в Excel
          </button>
        </div>
      </div>

      {document.items.length > 0 ? (
        <ItemsTable
          items={document.items}
          searchingItems={searchingItems}
          onSearchItem={onSearchItem}
          onItemUpdated={onItemUpdated}
        />
      ) : (
        <div className="rounded-md border border-gray-200 bg-white p-6 text-sm text-gray-600">
          Нажмите «Извлечь позиции», чтобы прогнать документ через LLM и получить список товаров.
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center text-gray-500">
      <div className="text-lg font-semibold text-gray-700 mb-2">Загрузите ТЗ слева</div>
      <p className="text-sm">
        Поддерживаются файлы DOCX, PDF, XLSX. После парсинга нажмите «Извлечь позиции» —
        LLM соберёт список товаров с характеристиками. Дальше можно искать по поставщикам и
        экспортировать результат в Excel.
      </p>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4 text-blue-600" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
