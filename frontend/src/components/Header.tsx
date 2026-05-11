import type { ReactNode } from "react";

export function Header({ llmBadge }: { llmBadge: ReactNode }) {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-3">
        <div className="text-lg font-bold text-gray-900">Tender Finder</div>
        <div className="text-sm text-gray-500 hidden sm:block">
          подбор товаров по тендерной документации
        </div>
        <div className="flex-1" />
        {llmBadge}
      </div>
    </header>
  );
}
