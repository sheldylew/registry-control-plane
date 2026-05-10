"use client";

import { Fragment } from "react";
import { Menu, MenuButton, MenuItem, MenuItems, Transition } from "@headlessui/react";
import { EllipsisHorizontalIcon } from "@heroicons/react/24/outline";

import Button from "@/app/components/ui/button";

export default function ActionMenu({ items, label = "Actions" }) {
  const loading = items.some((item) => item.loading);

  return (
    <Menu as="div" className="relative inline-block text-left">
      <MenuButton as={Button} variant="secondary" size="iconSm" aria-label={label} loading={loading}>
        {loading ? null : <EllipsisHorizontalIcon className="h-4 w-4" />}
      </MenuButton>
      <Transition
        as={Fragment}
        enter="transition duration-100 ease-out"
        enterFrom="scale-95 opacity-0"
        enterTo="scale-100 opacity-100"
        leave="transition duration-75 ease-in"
        leaveFrom="scale-100 opacity-100"
        leaveTo="scale-95 opacity-0"
      >
        <MenuItems anchor="bottom end" className="z-20 mt-2 w-52 rounded-lg border border-white/10 bg-slate-950 p-1 shadow-2xl shadow-slate-950/40 focus:outline-none">
          {items.map((item) => (
            <MenuItem key={item.label} disabled={item.disabled || item.loading}>
              {({ focus, disabled }) => (
                item.href ? (
                  <a
                    href={item.href}
                    className={`flex w-full items-center rounded-md px-3 py-2 text-sm ${
                      focus ? "bg-white/10 text-white" : "text-slate-200"
                    } ${disabled ? "opacity-50" : ""}`}
                  >
                    {item.label}
                  </a>
                ) : (
                  <button
                    type="button"
                    onClick={item.onSelect}
                    className={`flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm ${
                      focus ? "bg-white/10 text-white" : "text-slate-200"
                    } ${disabled ? "opacity-50" : ""}`}
                  >
                    {item.loading ? (
                      <span
                        aria-hidden="true"
                        className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
                      />
                    ) : null}
                    {item.label}
                  </button>
                )
              )}
            </MenuItem>
          ))}
        </MenuItems>
      </Transition>
    </Menu>
  );
}
