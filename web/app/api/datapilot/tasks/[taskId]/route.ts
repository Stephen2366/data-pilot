import { taskControlResponseSchema, taskStatusResponseSchema } from "@/lib/contracts";
import { proxyFastApi } from "@/lib/server-adapter";

/** 转发带 role/version 的 clear mutation；路径参数和查询参数分别编码，避免路径注入。 */
export async function DELETE(request: Request, context: { params: Promise<{ taskId: string }> }) {
  const { taskId } = await context.params;
  const url = new URL(request.url);
  const role = url.searchParams.get("user_role") ?? "ops";
  const version = url.searchParams.get("expected_version");
  return proxyFastApi({
    path: `/api/query/tasks/${encodeURIComponent(taskId)}?user_role=${encodeURIComponent(role)}&expected_version=${encodeURIComponent(version ?? "")}`,
    method: "DELETE",
    responseSchema: taskControlResponseSchema,
  });
}

/** 转发只读 task 状态对账；GET 不携带 expected_version，也不会触发 Graph。 */
export async function GET(request: Request, context: { params: Promise<{ taskId: string }> }) {
  const { taskId } = await context.params;
  const url = new URL(request.url);
  const role = url.searchParams.get("user_role") ?? "ops";
  return proxyFastApi({
    path: `/api/query/tasks/${encodeURIComponent(taskId)}?user_role=${encodeURIComponent(role)}`,
    method: "GET",
    responseSchema: taskStatusResponseSchema,
  });
}
