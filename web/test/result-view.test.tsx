import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResultView } from "@/components/result-view";
import { agentResponseSchema } from "@/lib/contracts";
import completeFixture from "./fixtures/sql-complete.json";
import blockedFixture from "./fixtures/blocked.json";

vi.mock("vega-embed", () => ({ default: vi.fn(async () => ({ finalize: vi.fn() })) }));

describe("ResultView", () => {
  it("同时保留业务答案、表格和 Trace 入口", () => {
    render(<ResultView response={agentResponseSchema.parse(completeFixture)} />);
    expect(screen.getByText(/120,000 元/)).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("技术细节")).toBeInTheDocument();
  });

  it("blocked 不显示成功标题", () => {
    render(<ResultView response={agentResponseSchema.parse(blockedFixture)} />);
    expect(screen.getByText("请求已被安全停止")).toBeInTheDocument();
    expect(screen.queryByText("本轮结果已完成")).not.toBeInTheDocument();
  });
});
