"use client";

import { cn } from "@/lib/utils";

interface BorderBeamProps {
  className?: string;
  size?: number;
  duration?: number;
  borderWidth?: number;
  colorFrom?: string;
  colorTo?: string;
  delay?: number;
}

export default function BorderBeam({
  className,
  size = 200,
  duration = 15,
  borderWidth = 1.5,
  colorFrom = "#FFD700",
  colorTo = "#FF4500",
  delay = 0,
}: BorderBeamProps) {
  return (
    <div
      style={
        {
          "--size": size,
          "--duration": duration,
          "--border-width": borderWidth,
          "--color-from": colorFrom,
          "--color-to": colorTo,
          "--delay": `-${delay}s`,
        } as React.CSSProperties
      }
      className={cn(
        "pointer-events-none absolute inset-0 rounded-full [mask:linear-gradient(white,transparent)]",
        className
      )}
    >
      <div
        className="absolute inset-0 rounded-full"
        style={{
          animation: `border-beam calc(var(--duration) * 1s) infinite linear`,
          animationDelay: "var(--delay)",
          background: `linear-gradient(0deg, var(--color-from), var(--color-to))`,
          borderRadius: "inherit",
          maskImage:
            "linear-gradient(to bottom, transparent 0%, black 10%, black 90%, transparent 100%)",
        }}
      />
    </div>
  );
}
