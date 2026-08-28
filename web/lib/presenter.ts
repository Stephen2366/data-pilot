import type { AgentResponse } from "@/lib/contracts";

export type ProductState =
  | "complete"
  | "partial"
  | "clarification"
  | "blocked"
  | "unsupported"
  | "insufficient"
  | "external_unavailable"
  | "failed"
  | "unrecognized";

export type PresentedResponse = {
  state: ProductState;
  eyebrow: string;
  title: string;
  detail: string;
  tone: "positive" | "warning" | "danger" | "neutral";
};

/**
 * 四轴状态的 closed-world 投影。
 *
 * ★ 这是纯函数：不读取 answer 真值、不猜模型意图，也不修改后端事实。新增状态组合若没有
 * 显式登记，会进入 unrecognized 而不是悄悄显示成功。
 */
export function presentResponse(response: AgentResponse): PresentedResponse {
  if (response.safety_status === "blocked") {
    return {
      state: "blocked",
      eyebrow: "安全边界",
      title: "请求已被安全停止",
      detail: response.reason_code ?? response.blocked_reason ?? "服务端没有公开更多原因。",
      tone: "danger",
    };
  }
  if (response.execution_status === "external_unavailable") {
    return {
      state: "external_unavailable",
      eyebrow: "运行依赖",
      title: "外部能力当前不可用",
      detail: response.reason_code ?? "请检查对应 runtime readiness。",
      tone: "warning",
    };
  }
  if (response.execution_status === "failed") {
    return {
      state: "failed",
      eyebrow: "执行结果",
      title: "本轮执行失败",
      detail: response.reason_code ?? response.error_type ?? "服务端已安全结束本轮。",
      tone: "danger",
    };
  }
  if (response.answer_status === "clarification_required") {
    return {
      state: "clarification",
      eyebrow: "需要补充",
      title: "DataPilot 需要更明确的条件",
      detail: response.reason_code ?? "请填写服务端签发的字段。",
      tone: "neutral",
    };
  }
  if (response.answer_status === "partial") {
    return {
      state: "partial",
      eyebrow: "部分完成",
      title: "已返回可验证的部分结果",
      detail: response.reason_code ?? "仍有要求没有获得充分证据。",
      tone: "warning",
    };
  }
  if (response.answer_status === "unsupported") {
    return {
      state: "unsupported",
      eyebrow: "能力边界",
      title: "当前问题不在支持范围内",
      detail: response.reason_code ?? "DataPilot 没有为该问题选择不安全的替代路径。",
      tone: "neutral",
    };
  }
  if (response.answer_status === "insufficient_evidence") {
    return {
      state: "insufficient",
      eyebrow: "证据边界",
      title: "证据不足，未生成确定答案",
      detail: response.reason_code ?? "已保留安全停止原因。",
      tone: "warning",
    };
  }
  if (response.execution_status === "completed" && response.answer_status === "complete") {
    return {
      state: "complete",
      eyebrow: response.route === "hybrid" ? "混合分析完成" : "分析完成",
      title: "本轮结果已完成",
      detail: "完成表示响应合同闭合，不等同于外部质量评测结论。",
      tone: "positive",
    };
  }
  return {
    state: "unrecognized",
    eyebrow: "合同保护",
    title: "出现未登记的产品状态",
    detail: `execution=${response.execution_status}, answer=${response.answer_status}, safety=${response.safety_status}`,
    tone: "danger",
  };
}
