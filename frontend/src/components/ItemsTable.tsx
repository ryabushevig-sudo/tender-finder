import { useState } from "react";
import { updateItem, deleteItem, type Item, type ProductMatch } from "../api";

export function ItemsTable({
  items,
  searchingItems,
  matchingItems,
  onSearchItem,
  onMatchItem,
  onItemUpdated,
}: {
  items: Item[];
  searchingItems: Set<string>;
  matchingItems: Set<string>;
  onSearchItem: (item: Item) => void;
  onMatchItem: (item: Item) => void;
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
            <th className="px-3 py-2 text-right w-60">Действия</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <ItemRow
              key={item.id}
              item={item}
              searching={searchingItems.has(item.id)}
              matching={matchingItems.has(item.id)}
              onSearch={() => onSearchItem(item)}
              onMatch={() => onMatchItem(item)}
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
  matching,
  onSearch,
  onMatch,
  onUpdated,
}: {
  item: Item;
  searching: boolean;
  matching: boolean;
  onSearch: () => void;
  onMatch: () => void;
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
                title="Простой поиск поставщиков по названию (без сопоставления характеристик)"
              >
                {searching ? "Поиск…" : "Найти"}
              </button>
              <button
                className="px-2 py-1 text-xs rounded border border-indigo-500 text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                onClick={() => {
                  setExpanded(true);
                  onMatch();
                }}
                disabled={matching}
                title="LLM предложит марки/модели по характеристикам и сравнит каждую с требованиями ТЗ"
              >
                {matching ? "Подбор…" : "Подбор по характеристикам"}
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
            <SpecsAndOffers item={item} matching={matching} />
          </td>
        </tr>
      )}
    </>
  );
}

function SpecsAndOffers({ item, matching }: { item: Item; matching: boolean }) {
  const specs = item.specifications && typeof item.specifications === "object"
    ? Object.entries(item.specifications as Record<string, unknown>)
    : [];
  return (
    <div className="space-y-4">
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <div className="text-xs uppercase text-gray-500 mb-1">Характеристики (ТЗ)</div>
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

      <MatchesPanel matches={item.matches} matching={matching} />
    </div>
  );
}

function verdictBadge(verdict: string | null) {
  const v = (verdict || "").toLowerCase();
  if (v === "high") return { color: "bg-emerald-100 text-emerald-800 border-emerald-300", label: "Хорошее совпадение" };
  if (v === "medium") return { color: "bg-amber-100 text-amber-800 border-amber-300", label: "Частичное совпадение" };
  if (v === "low") return { color: "bg-rose-100 text-rose-800 border-rose-300", label: "Слабое совпадение" };
  return { color: "bg-gray-100 text-gray-700 border-gray-300", label: "Мало данных" };
}

function statusIcon(status: string) {
  if (status === "match") return <span className="text-emerald-600 font-bold">✓</span>;
  if (status === "mismatch") return <span className="text-rose-600 font-bold">✗</span>;
  return <span className="text-gray-400 font-bold">?</span>;
}

function MatchesPanel({
  matches,
  matching,
}: {
  matches: ProductMatch[];
  matching: boolean;
}) {
  if (matching && matches.length === 0) {
    return (
      <div className="border border-indigo-200 bg-indigo-50 rounded p-3 text-xs text-indigo-800">
        LLM предлагает гипотезы и ищет соответствующие товары — обычно ~30–90 секунд…
      </div>
    );
  }
  if (matches.length === 0) {
    return (
      <div className="border border-dashed border-indigo-200 rounded p-3 text-xs text-gray-500">
        Подбор по характеристикам ещё не запускался — нажмите «Подбор по характеристикам».
        LLM предложит несколько конкретных марок/моделей, найдёт их у поставщиков и сверит
        каждую характеристику с ТЗ.
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs uppercase text-gray-500">
          Подбор по характеристикам · {matches.length}{" "}
          {matches.length === 1 ? "гипотеза" : "гипотез"}
        </div>
        {matching && (
          <span className="text-xs text-indigo-700">обновляю…</span>
        )}
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        {matches.map((m) => {
          const badge = verdictBadge(m.verdict);
          const brandModel = [m.hypothesis_brand, m.hypothesis_model]
            .filter(Boolean)
            .join(" ");
          return (
            <div
              key={m.id}
              className="border border-gray-200 bg-white rounded-md p-3 text-xs space-y-2"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold text-gray-900">
                    {brandModel || "Без марки"}
                  </div>
                  {m.hypothesis_description && (
                    <div className="text-gray-600 mt-0.5">
                      {m.hypothesis_description}
                    </div>
                  )}
                </div>
                <span
                  className={`px-2 py-0.5 rounded border whitespace-nowrap ${badge.color}`}
                  title={m.verdict || ""}
                >
                  {m.match_score != null ? `${m.match_score}% · ` : ""}
                  {badge.label}
                </span>
              </div>

              {m.found_url ? (
                <div className="border-t border-gray-100 pt-2 space-y-1">
                  <a
                    href={m.found_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-700 hover:underline font-medium block truncate"
                    title={m.found_title || m.found_url}
                  >
                    {m.found_title || m.found_url}
                  </a>
                  <div className="flex justify-between text-gray-500">
                    <span>{m.found_domain}</span>
                    {m.found_price && (
                      <span className="text-emerald-700 font-semibold">
                        {m.found_price}
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="border-t border-gray-100 pt-2 text-gray-500 italic">
                  Поставщик не найден по запросу «{m.search_query}»
                </div>
              )}

              {m.specs_compared && m.specs_compared.length > 0 && (
                <div className="border-t border-gray-100 pt-2">
                  <div className="text-gray-500 mb-1">Соответствие ТЗ:</div>
                  <table className="w-full text-xxs">
                    <tbody>
                      {m.specs_compared.map((s, i) => (
                        <tr key={i} className="align-top">
                          <td className="pr-2 py-0.5 w-4">{statusIcon(s.status)}</td>
                          <td className="pr-2 py-0.5 text-gray-700">{s.name}</td>
                          <td className="pr-2 py-0.5 text-gray-500">
                            {s.required ? `ТЗ: ${s.required}` : ""}
                          </td>
                          <td className="py-0.5 text-gray-700">
                            {s.found ? `найдено: ${s.found}` : ""}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {m.summary && (
                <div className="border-t border-gray-100 pt-2 text-gray-700">
                  {m.summary}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
