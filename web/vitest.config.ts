import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": import.meta.dirname,
      // Next 在服务端构建中识别 `server-only` marker；Vitest 需要一个空 marker 才能直接
      // 验证 thin BFF adapter，本 alias 不进入 production bundle。
      "server-only": `${import.meta.dirname}/test/server-only.ts`,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.ts"],
    include: ["test/**/*.test.{ts,tsx}"],
  },
});
