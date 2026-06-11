"use client";

import { createContext, useCallback, useContext, useState } from "react";

import { Button } from "@/components/ui/button";

type ConfirmOptions = {
  title?: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
};

const ConfirmContext = createContext<(o?: ConfirmOptions) => Promise<boolean>>(
  async () => false,
);

export function useConfirm() {
  return useContext(ConfirmContext);
}

/** Modal de confirmación reutilizable con API imperativa basada en promesas:
 *  `const confirm = useConfirm(); if (await confirm({...})) { ... }` */
export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<{
    opts: ConfirmOptions;
    resolve: (v: boolean) => void;
  } | null>(null);

  const confirm = useCallback(
    (opts: ConfirmOptions = {}) =>
      new Promise<boolean>((resolve) => setState({ opts, resolve })),
    [],
  );

  const close = (value: boolean) => {
    state?.resolve(value);
    setState(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4 backdrop-blur-sm print:hidden"
          onClick={() => close(false)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-sm rounded-2xl border bg-card p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold tracking-tight">
              {state.opts.title ?? "¿Confirmar?"}
            </h2>
            {state.opts.message && (
              <p className="mt-1.5 text-sm text-muted-foreground">{state.opts.message}</p>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => close(false)}>
                {state.opts.cancelText ?? "No"}
              </Button>
              <Button size="sm" onClick={() => close(true)} autoFocus>
                {state.opts.confirmText ?? "Sí"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
