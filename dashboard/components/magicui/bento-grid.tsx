"use client";

import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface BentoGridProps {
  children: ReactNode;
  className?: string;
}

interface BentoCardProps {
  name: string;
  className?: string;
  background?: ReactNode;
  icon?: ReactNode;
  description: string;
  href?: string;
  cta?: string;
}

export function BentoGrid({ children, className }: BentoGridProps) {
  return (
    <div
      className={cn(
        "grid w-full auto-rows-[22rem] grid-cols-3 gap-4",
        className
      )}
    >
      {children}
    </div>
  );
}

export function BentoCard({
  name,
  className,
  background,
  icon,
  description,
  href,
  cta,
}: BentoCardProps) {
  return (
    <div
      key={name}
      className={cn(
        "group relative col-span-3 flex flex-col justify-between overflow-hidden rounded-xl",
        "bg-white/5 backdrop-blur-sm border border-white/10",
        "hover:border-cyber-yellow/50 transition-all duration-500 ease-out",
        "hover:shadow-[0_0_30px_rgba(255,215,0,0.2)]",
        className
      )}
    >
      <div className="pointer-events-none absolute inset-0 transform-gpu transition-all duration-500 group-hover:scale-105">
        {background}
      </div>
      <div className="pointer-events-none z-10 flex transform-gpu flex-col gap-1 p-6 transition-all duration-500">
        {icon && <div className="text-cyber-yellow">{icon}</div>}
        <h3 className="text-xl font-semibold text-neutral-100 font-mono">
          {name}
        </h3>
        <p className="max-w-lg text-neutral-400">{description}</p>
      </div>

      {href && (
        <div className="pointer-events-auto relative z-10 flex items-center justify-between p-6">
          <a
            href={href}
            className="inline-flex items-center gap-1 text-sm font-medium text-cyber-yellow hover:text-retro-red transition-colors"
          >
            {cta || "Learn more"} →
          </a>
        </div>
      )}
    </div>
  );
}
