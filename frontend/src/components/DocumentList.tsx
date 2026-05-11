import type { DocumentSummary } from "../api";

export function DocumentList({
  documents,
  selectedId,
  onSelect,
  onDelete,
}: {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  if (documents.length === 0) {
    return null;
  }
  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <div className="px-3 py-2 border-b border-gray-200 text-xs uppercase tracking-wide text-gray-500">
        Документы
      </div>
      <ul>
        {documents.map((doc) => {
          const isSelected = doc.id === selectedId;
          return (
            <li
              key={doc.id}
              className={
                "flex items-start gap-2 px-3 py-2 border-b border-gray-100 last:border-b-0 cursor-pointer " +
                (isSelected ? "bg-blue-50" : "hover:bg-gray-50")
              }
              onClick={() => onSelect(doc.id)}
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-900 truncate" title={doc.filename}>
                  {doc.filename}
                </div>
                <div className="text-xs text-gray-500">
                  {doc.status} · позиций: {doc.items_count}
                </div>
              </div>
              <button
                className="text-xs text-rose-600 hover:text-rose-800"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(doc.id);
                }}
                title="Удалить"
              >
                ✕
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
