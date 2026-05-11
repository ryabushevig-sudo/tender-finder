import { useState } from "react";
import { updateItem, deleteItem, type Item } from "../api";

export function ItemsTable({
  items,
  searchingItems,
  onSearchItem,
  onItemUpdated,
}: {
  items: Item[];
  searchingItems: Set<string>;
  onSearchItem: (item: Item) => void;
  onItemUpdated: () => void;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-600 uppercase text-xs">
          <tr>
            <th className="px-3 py-2 text-left w-10">№</th>
            <th className="px-3 py-2 text-left">Наименование</th>
            <th className="px-3 py-2 text-left w-20">Кол-во</th>
            <th className="px-3 py-2 text-left w-16">Ед.</th>
            <th className="px-3 py-2 text-left w-40">Поисковый запрос</th>
            <th className="px-3 py-2 text-right w-44">Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <ItemRow
              key={item.id}
              item={item}
              searching={searchingItems.has(item.id)}
              onSearch={() => onSearchItem(item)}
              onUpdated={onItemUpdated}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ItemRow({
  item,
  searching,
  onSearch,
  onUpdated,
}: {
  item: Item;
  searching: boolean;
  onSearch: () => void;
  onUpdated: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    name: item.name,
    quantity: item.quantity?.toString() ?? "",
    unit: item.unit ?? "",
    search_query: item.search_query ?? "",
  });

  const save = async () => {
    await updateItem(item.id, {
      name: draft.name,
      quantity: draft.quantity ? Number(draft.quantity) : null,
      unit: draft.unit || null,
      search_query: draft.search_query || null,
    });
    setEditing(false);
    onUpdated();
  };

  const remove = async () => {
    if (!confirm(`Удалить позицию "${item.name}"?`)) return;
    await deleteItem(item.id);
    onUpdated();
  };

  return (
    <>
      <tr className="border-t border-gray-100 align-top">
        <td className="px-3 py-2 text-gray-500">{item.position}</td>
        <td className="px-3 py-2">
          {editing ? (
            <textarea
              className="w-full border rounded px-2 py-1"
              rows={2}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          ) : (
            <div>
              <button
                className="font-medium text-gray-900 hover:text-blue-700 text-left"
                onClick={() => setExpanded((x) => !x)}
              >
                {item.name}
              </button>
              {(item.gost || item.okpd2) && (
                <div className="text-xs text-gray-500 mt-1">
                  {item.gost && <span className="mr-2">ГОСТ: {item.gost}</span>}
                  {item.okpd2 && <span>ОКПД2: {item.okpd2}</span>}
                </div>
              )}
            </div>
          )}
        </td>
        <td className="px-3 py-2">
          {editing ? (
            <input
              className="w-20 border rounded px-2 py-1"
              value={draft.quantity}
              onChange={(e) => setDraft({ ...draft, quantity: e.target.value })}
            />
          ) : (
            item.quantity ?? "—"
          )}
        </td>
        <td className="px-3 py-2">
          {editing ? (
            <input
              className="w-16 border rounded px-2 py-1"
              value={draft.unit}
              onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
            />
          ) : (
            item.unit ?? "—"
          )}
        </td>
        <td className="px-3 py-2 text-xs text-gray-600">
          {editing ? (
            <input
              className="w-full border rounded px-2 py-1"
              value={draft.search_query}
              onChange={(e) => setDraft({ ...draft, search_query: e.target.value })}
            />
          ) : (
            item.search_query || <span className="text-gray-400">{item.name}</span>
          )}
        </td>
        <td className="px-3 py-2 text-right space-x-1 whitespace-nowrap">
          {editing ? (
            <>
              <button
                className="px-2 py-1 text-xs rounded bg-blue-500 text-white hover:bg-blue-600"
                onClick={save}
              >
                Сохранить
              </button>
              <button
                className="px-2 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50"
                onClick={() => {
                  setEditing(false);
                  setDraft({
                    name: item.name,
                    quantity: item.quantity?.toString() ?? "",
                    unit: item.unit ?? "",
                    search_query: item.search_query ?? "",
                  });
                }}
              >
                Отмена
              </button>
            </>
          ) : (
            <>
              <button
                className="px-2 py-1 text-xs rounded border border-emerald-500 text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                onClick={onSearch}
                disabled={searching}
              >
                {searching ? "Поиск…" : "Найти"}
              </button>
              <button
                className="px-2 py-1 text-xs rounded border border-gray-300 hover:bg-gray-50"
                onClick={() => setEditing(true)}
              >
                Изменить
              </button>
              <button
                className="px-2 py-1 text-xs rounded border border-rose-300 text-rose-600 hover:bg-rose-50"
                onClick={remove}
              >
                Удалить
              </button>
            </>
          )}
        </td>
      </tr>

      {expanded && (
        <tr className="border-t border-gray-100 bg-gray-50">
          <td colSpan={6} className="px-4 py-3">
            <SpecsAndOffers item={item} />
          </td>
        </tr>
      )}
    </>
  );
}

function SpecsAndOffers({ item }: { item: Item }) {
  const specs = item.specifications && typeof item.specifications === "object"
    ? Object.entries(item.specifications as Record<string, unknown>)
    : [];
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <div className="text-xs uppercase text-gray-500 mb-1">Характеристики</div>
        {specs.length > 0 ? (
          <ul className="text-xs text-gray-700 space-y-0.5">
            {specs.map(([k, v]) => (
              <li key={k}>
                <span className="text-gray-500">{k}:</span> {String(v)}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-gray-400">нет</div>
        )}
      </div>
      <div>
        <div className="text-xs uppercase text-gray-500 mb-1">
          Найденные поставщики ({item.offers.length})
        </div>
        {item.offers.length === 0 ? (
          <div className="text-xs text-gray-400">
            ещё не искали — нажмите «Найти»
          </div>
        ) : (
          <ul className="text-xs space-y-2">
            {item.offers.map((offer) => (
              <li key={offer.id} className="border border-gray-200 rounded p-2 bg-white">
                <div className="flex items-center justify-between gap-2">
                  <a
                    href={offer.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-700 hover:underline font-medium truncate"
                    title={offer.title}
                  >
                    {offer.title}
                  </a>
                  {offer.price && (
                    <span className="text-emerald-700 font-semibold whitespace-nowrap">
                      {offer.price}
                    </span>
                  )}
                </div>
                <div className="text-gray-500 text-xxs">{offer.supplier_domain}</div>
                {offer.snippet && (
                  <div className="text-gray-600 mt-1 line-clamp-2">{offer.snippet}</div>
                )}
                <div className="flex gap-3 mt-1 text-gray-600">
                  {offer.contact_phone && <span>📞 {offer.contact_phone}</span>}
                  {offer.contact_email && <span>✉ {offer.contact_email}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
