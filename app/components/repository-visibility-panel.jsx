"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Label, Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import { CheckIcon, ChevronUpDownIcon } from "@heroicons/react/20/solid";

import { readApiErrorDetail } from "@/app/lib/user-form";

const visibilityOptions = [
  {
    value: "private",
    label: "Private",
    description: "Authenticated pull access only",
  },
  {
    value: "public",
    label: "Public read",
    description: "Anonymous pull tokens allowed",
  },
];

function readCookie(name) {
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

function optionFor(value) {
  return visibilityOptions.find((option) => option.value === value) || visibilityOptions[0];
}

export default function RepositoryVisibilityPanel({ repositoryName, initialVisibility }) {
  const router = useRouter();
  const [selected, setSelected] = useState(optionFor(initialVisibility));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function updateVisibility(nextOption) {
    setSelected(nextOption);
    setError("");
    setSaving(true);

    try {
      const response = await fetch("/api/admin/repositories/visibility", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": readCookie("rcr_csrf"),
        },
        body: JSON.stringify({
          repository_name: repositoryName,
          visibility: nextOption.value,
        }),
      });

      const payload = await response.json().catch(() => ({}));

      if (!response.ok) {
        setSelected(optionFor(initialVisibility));
        setError(readApiErrorDetail(payload, "Could not update repository visibility."));
        return;
      }

      setSelected(optionFor(payload.repository.visibility));
      router.refresh();
    } catch {
      setSelected(optionFor(initialVisibility));
      setError("Could not update repository visibility.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="w-full max-w-xs">
      <Listbox value={selected} by="value" onChange={updateVisibility} disabled={saving}>
        <Label className="block text-sm font-medium text-slate-300">Visibility</Label>
        <div className="relative mt-2">
          <ListboxButton className="grid w-full cursor-default grid-cols-1 rounded-xl border border-white/10 bg-slate-950/80 py-2.5 pl-3 pr-2 text-left text-white outline-none transition hover:border-cyan-400/40 focus-visible:border-cyan-400 focus-visible:ring-2 focus-visible:ring-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-70">
            <span className="col-start-1 row-start-1 truncate pr-7">
              <span className="block text-sm font-semibold">{selected.label}</span>
              <span className="block truncate text-xs text-slate-400">{selected.description}</span>
            </span>
            <ChevronUpDownIcon
              aria-hidden="true"
              className="col-start-1 row-start-1 size-5 self-center justify-self-end text-slate-400"
            />
          </ListboxButton>

          <ListboxOptions
            transition
            className="absolute right-0 z-10 mt-2 max-h-60 w-full overflow-auto rounded-xl border border-white/10 bg-slate-950 py-1 text-sm shadow-2xl shadow-slate-950/40 outline-none data-[closed]:data-[leave]:opacity-0 data-[leave]:transition data-[leave]:duration-100 data-[leave]:ease-in"
          >
            {visibilityOptions.map((option) => (
              <ListboxOption
                key={option.value}
                value={option}
                className="group relative cursor-default select-none py-2.5 pl-9 pr-4 text-white data-[focus]:bg-cyan-400 data-[focus]:text-slate-950 data-[focus]:outline-none"
              >
                <span className="block truncate font-normal group-data-[selected]:font-semibold">{option.label}</span>
                <span className="block truncate text-xs text-slate-400 group-data-[focus]:text-slate-800">
                  {option.description}
                </span>
                <span className="absolute inset-y-0 left-0 hidden items-center pl-2 text-cyan-300 group-data-[focus]:text-slate-950 group-data-[selected]:flex">
                  <CheckIcon aria-hidden="true" className="size-5" />
                </span>
              </ListboxOption>
            ))}
          </ListboxOptions>
        </div>
      </Listbox>
      {error ? <p className="mt-2 text-sm text-rose-300">{error}</p> : null}
    </div>
  );
}
