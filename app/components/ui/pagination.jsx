import Link from "next/link";

import { ChevronLeftIcon, ChevronRightIcon } from "@heroicons/react/20/solid";

function buildPageItems(page, totalPages) {
  const pages = new Set([1, totalPages, page - 1, page, page + 1]);
  if (page <= 3) {
    pages.add(2);
    pages.add(3);
  }
  if (page >= totalPages - 2) {
    pages.add(totalPages - 1);
    pages.add(totalPages - 2);
  }

  const ordered = [...pages].filter((value) => value >= 1 && value <= totalPages).sort((a, b) => a - b);
  const items = [];
  for (let index = 0; index < ordered.length; index += 1) {
    const value = ordered[index];
    const previous = ordered[index - 1];
    if (previous && value - previous > 1) {
      items.push("gap");
    }
    items.push(value);
  }
  return items;
}

export default function Pagination({ page, pageSize, total, hrefForPage, label = "results" }) {
  const totalPages = Math.max(Math.ceil(total / pageSize), 1);
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const start = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const end = total === 0 ? 0 : Math.min(currentPage * pageSize, total);
  const items = buildPageItems(currentPage, totalPages);

  return (
    <div className="mt-6 border-t border-white/10 px-4 py-3 sm:flex sm:items-center sm:justify-between sm:px-6">
      <div className="space-y-3 sm:hidden">
        <p className="text-center text-xs text-slate-400">
          Showing <span className="font-medium text-white">{start}</span> to{" "}
          <span className="font-medium text-white">{end}</span> of{" "}
          <span className="font-medium text-white">{total}</span> {label}
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Link
            href={hrefForPage(Math.max(currentPage - 1, 1))}
            prefetch={false}
            aria-disabled={currentPage <= 1}
            className={`relative inline-flex items-center justify-center rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium ${
              currentPage <= 1 ? "pointer-events-none text-slate-500 opacity-50" : "text-slate-200 hover:bg-white/10"
            }`}
          >
            Previous
          </Link>
          <Link
            href={hrefForPage(Math.min(currentPage + 1, totalPages))}
            prefetch={false}
            aria-disabled={currentPage >= totalPages}
            className={`relative inline-flex items-center justify-center rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium ${
              currentPage >= totalPages ? "pointer-events-none text-slate-500 opacity-50" : "text-slate-200 hover:bg-white/10"
            }`}
          >
            Next
          </Link>
        </div>
      </div>
      <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
        <p className="text-sm text-slate-300">
          Showing <span className="font-medium text-white">{start}</span> to{" "}
          <span className="font-medium text-white">{end}</span> of{" "}
          <span className="font-medium text-white">{total}</span> {label}
        </p>
        <nav aria-label="Pagination" className="isolate inline-flex -space-x-px rounded-md">
          <Link
            href={hrefForPage(Math.max(currentPage - 1, 1))}
            prefetch={false}
            aria-disabled={currentPage <= 1}
            className={`relative inline-flex items-center rounded-l-md px-2 py-2 ring-1 ring-inset ring-white/10 ${
              currentPage <= 1 ? "pointer-events-none text-slate-600 opacity-50" : "text-slate-400 hover:bg-white/5"
            }`}
          >
            <span className="sr-only">Previous</span>
            <ChevronLeftIcon className="h-5 w-5" />
          </Link>
          {items.map((item, index) =>
            item === "gap" ? (
              <span
                key={`gap-${index}`}
                className="relative inline-flex items-center px-4 py-2 text-sm font-semibold text-slate-500 ring-1 ring-inset ring-white/10"
              >
                ...
              </span>
            ) : item === currentPage ? (
              <span
                key={item}
                aria-current="page"
                className="relative z-10 inline-flex items-center bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950"
              >
                {item}
              </span>
            ) : (
              <Link
                key={item}
                href={hrefForPage(item)}
                prefetch={false}
                className="relative inline-flex items-center px-4 py-2 text-sm font-semibold text-slate-200 ring-1 ring-inset ring-white/10 hover:bg-white/5"
              >
                {item}
              </Link>
            ),
          )}
          <Link
            href={hrefForPage(Math.min(currentPage + 1, totalPages))}
            prefetch={false}
            aria-disabled={currentPage >= totalPages}
            className={`relative inline-flex items-center rounded-r-md px-2 py-2 ring-1 ring-inset ring-white/10 ${
              currentPage >= totalPages ? "pointer-events-none text-slate-600 opacity-50" : "text-slate-400 hover:bg-white/5"
            }`}
          >
            <span className="sr-only">Next</span>
            <ChevronRightIcon className="h-5 w-5" />
          </Link>
        </nav>
      </div>
    </div>
  );
}
