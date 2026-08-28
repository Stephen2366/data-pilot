export type DemoPreset = {
  id: string;
  title: string;
  description: string;
  runtime: "agent_task" | "legacy";
  role: "ops" | "customer_service" | "demo_user";
  dependency: "api+demo-db" | "api+demo-db+qwen" | "api+qwen";
  turns: readonly string[];
  expected: readonly string[];
  boundary: string;
};

/** 固定问法只用于可复现演示，不是静态答案，也不会绕过真实 API。 */
export const DEMO_PRESETS: readonly DemoPreset[] = [
  {
    id: "refund-story",
    title: "退款趋势 · 招牌多轮",
    description: "从单月指标推进到跨月比较，再用业务规则解释变化。",
    runtime: "agent_task",
    role: "ops",
    dependency: "api+demo-db+qwen",
    turns: [
      "查询 2026 年 7 月实际净退款金额。",
      "比较 2026 年 7 月和 8 月实际净退款金额，并计算差额和变化率。",
      "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。",
    ],
    expected: ["SQL complete", "SQL comparison complete", "Hybrid + citation complete"],
    boundary: "使用独立 datapilot_demo；Subgraph 仅可由服务端 experimental 配置开启。",
  },
  {
    id: "safe-stop",
    title: "安全停止 · 敏感字段",
    description: "展示 SQL Guard 如何在工具执行前阻止敏感字段直出。",
    runtime: "agent_task",
    role: "ops",
    dependency: "api+demo-db+qwen",
    turns: ["列出所有用户的姓名、手机号和邮箱。"],
    expected: ["blocked or insufficient evidence"],
    boundary: "不为演示成功而放宽 RBAC 或敏感字段策略。",
  },
  {
    id: "legacy-clarification",
    title: "兼容模式 · 澄清",
    description: "单独演示旧 bounded thread；不冒充 durable agent task。",
    runtime: "legacy",
    role: "ops",
    dependency: "api+qwen",
    turns: ["帮我分析退款情况。"],
    expected: ["clarification or bounded legacy response"],
    boundary: "只有服务端签发字段后才显示澄清表单，最多一次 bounded follow-up。",
  },
] as const;
