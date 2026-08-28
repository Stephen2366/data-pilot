"use client";

import { useEffect, useRef, useState } from "react";

/**
 * 按需加载 Vega-Lite，减少工作台首屏负担；失败时只提示降级，权威 table 仍由父组件保留。
 */
export function VegaChart({ spec }: { spec: Record<string, unknown> }) {
  const host = useRef<HTMLDivElement>(null);
  const identity = JSON.stringify(spec);
  const [failedIdentity, setFailedIdentity] = useState<string | null>(null);

  useEffect(() => {
    // React 卸载或 spec 切换后必须 finalize 旧 view，避免 canvas/SVG 实例和监听器泄漏。
    let disposed = false;
    let finalize: (() => void) | undefined;
    void import("vega-embed")
      .then(({ default: embed }) => {
        if (!host.current || disposed) return undefined;
        return embed(host.current, spec, { actions: false, renderer: "svg" });
      })
      .then((result) => {
        if (result) finalize = () => result.finalize();
      })
      .catch(() => {
        if (!disposed) setFailedIdentity(identity);
      });
    return () => {
      disposed = true;
      finalize?.();
    };
  }, [identity, spec]);

  if (failedIdentity === identity) {
    return <p className="inline-notice">图表渲染失败，已保留下面的权威数据表。</p>;
  }
  return <div ref={host} className="chart-host" aria-label="DataPilot 数据图表" />;
}
