"use client";

import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: "ok" | "error" | "loading";
  label?: string;
  className?: string;
}

export default function StatusBadge({
  status,
  label,
  className,
}: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-mono",
        status === "ok" && "bg-green-500/10 text-green-400",
        status === "error" && "bg-red-500/10 text-red-400",
        status === "loading" && "bg-yellow-500/10 text-yellow-400",
        className
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          status === "ok" && "bg-green-400",
          status === "error" && "bg-red-400",
          status === "loading" && "bg-yellow-400 animate-pulse"
        )}
      />
      {label ?? status}
    </span>
  );
}
