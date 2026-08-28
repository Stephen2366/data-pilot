import { agentResponseSchema, queryRequestSchema } from "@/lib/contracts";
import { proxyFastApi } from "@/lib/server-adapter";

/** 同源 query 入口：严格校验请求与响应，业务语义仍由 FastAPI 决定。 */
export async function POST(request: Request) {
  return proxyFastApi({
    path: "/api/query",
    method: "POST",
    request,
    requestSchema: queryRequestSchema,
    responseSchema: agentResponseSchema,
  });
}
