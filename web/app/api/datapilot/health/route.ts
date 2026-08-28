import { z } from "zod";
import { proxyFastApi } from "@/lib/server-adapter";

const healthSchema = z.object({ status: z.string() }).passthrough();

/** 浏览器只读取 readiness，不在前端复刻后端依赖诊断。 */
export async function GET() {
  return proxyFastApi({ path: "/health", method: "GET", responseSchema: healthSchema });
}
