import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const completeFixture = JSON.parse(readFileSync(new URL("../test/fixtures/sql-complete.json", import.meta.url), "utf-8"));
const blockedFixture = JSON.parse(readFileSync(new URL("../test/fixtures/blocked.json", import.meta.url), "utf-8"));
const clarificationFixture = JSON.parse(readFileSync(new URL("../test/fixtures/legacy-clarification.json", import.meta.url), "utf-8"));

/** 每个 UI 合同测试固定健康门，只替换网络边界，不伪造组件内部状态。 */
async function mockHealth(page: import("@playwright/test").Page) {
  await page.route("**/api/datapilot/health", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) }),
  );
}

test("发送后立即形成右侧消息、清空输入且外层视口固定", async ({ page }) => {
  await mockHealth(page);
  await page.route("**/api/datapilot/query", async (route) => {
    // 留出短窗口观察真实 pending UI；不依赖组件内部状态或伪造节点进度。
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(completeFixture) });
  });
  await page.goto("/");
  const input = page.getByLabel("输入数据分析问题");
  await input.fill("比较 7 月和 8 月实际净退款金额");
  await page.getByRole("button", { name: /开始分析/ }).click();

  await expect(input).toHaveValue("");
  await expect(input).toBeDisabled();
  await expect(page.locator(".question-bubble").getByText("比较 7 月和 8 月实际净退款金额", { exact: true })).toBeVisible();
  await expect(page.getByText("DataPilot 正在查询和分析", { exact: true })).toBeVisible();
  await expect(page.getByText("把一次提问，推进成", { exact: false })).toHaveCount(0);

  const layout = await page.evaluate(() => ({
    pageOverflow: getComputedStyle(document.querySelector(".shell")!).overflow,
    timelineOverflow: getComputedStyle(document.querySelector(".timeline")!).overflowY,
  }));
  expect(layout).toEqual({ pageOverflow: "hidden", timelineOverflow: "auto" });
  await expect(page.getByText("本轮结果已完成")).toBeVisible();
});

test("task start 与 continue 只使用服务端确认的 version", async ({ page }) => {
  const requests: unknown[] = [];
  await mockHealth(page);
  await page.route("**/api/datapilot/query", async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(completeFixture) });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /开始分析/ }).click();
  await expect(page.getByText("本轮结果已完成")).toBeVisible();
  await page.getByLabel("输入数据分析问题").fill("比较 7 月和 8 月");
  await page.getByRole("button", { name: /继续任务/ }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[0]).toMatchObject({ task: { action: "start" } });
  expect(requests[1]).toMatchObject({ task: { action: "continue", task_id: "task_m50_fixture_001", expected_version: 1 } });
  await expect(page.getByRole("button", { name: /兼容模式/ })).toBeDisabled();
});

test("安全拒绝不会显示成功", async ({ page }) => {
  await mockHealth(page);
  await page.route("**/api/datapilot/query", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(blockedFixture) }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: /开始分析/ }).click();
  await expect(page.getByText("请求已被安全停止")).toBeVisible();
  await expect(page.getByText("本轮结果已完成")).toHaveCount(0);
});

test("known rejection 不推进 version、不误标成功也不自动重试", async ({ page }) => {
  const requests: unknown[] = [];
  const typedRejection = {
    ...completeFixture,
    action_attempts: [],
    agent_budget: null,
    agent_loop_runtime: null,
    agent_termination: null,
    answer: "本轮未执行。",
    answer_status: "no_answer",
    chart_spec: null,
    columns: [],
    execution_status: "not_started",
    graph_invocation_count: 0,
    reason_code: "task_version_conflict",
    route: "none",
    rows: [],
    sql: null,
    tables_used: [],
    task: null,
    task_action: "rejected",
    task_context: null,
    task_delta: null,
    task_runtime_invocation_count: 0,
    task_transition: null,
    turn_action: "rejected",
  };
  await mockHealth(page);
  await page.route("**/api/datapilot/query", async (route) => {
    requests.push(route.request().postDataJSON());
    if (requests.length === 1) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(completeFixture) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(typedRejection) });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /开始分析/ }).click();
  await expect(page.getByText("v1", { exact: true })).toBeVisible();
  await page.getByLabel("输入数据分析问题").fill("继续分析");
  await page.getByRole("button", { name: /继续任务/ }).click();
  await expect(page.getByRole("status")).toContainText("任务版本已变化");
  await expect(page.getByText("v1", { exact: true })).toBeVisible();
  await expect(page.getByText("当前 lineage 已冻结")).toHaveCount(0);
  await page.waitForTimeout(100);
  expect(requests).toHaveLength(2);
  await expect(page.getByText("本轮结果已完成")).toHaveCount(1);
});

test("合同漂移形成 unknown outcome 并冻结 lineage", async ({ page }) => {
  let calls = 0;
  await mockHealth(page);
  await page.route("**/api/datapilot/query", async (route) => {
    calls += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...completeFixture, runtime_family: "future" }),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /开始分析/ }).click();
  await expect(page.getByText("当前 lineage 已冻结")).toBeVisible();
  await expect(page.getByText("本轮结果已完成")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /开始分析/ })).toBeDisabled();
  await page.waitForTimeout(100);
  expect(calls).toBe(1);
});

test("unknown 冻结可跨刷新并通过只读 status 恢复到服务端新版本", async ({ page }) => {
  let queryCalls = 0;
  let statusCalls = 0;
  let clearedVersion = "";
  await mockHealth(page);
  await page.route("**/api/datapilot/query", async (route) => {
    queryCalls += 1;
    if (queryCalls === 1) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(completeFixture) });
      return;
    }
    await route.fulfill({
      status: 504,
      contentType: "application/json",
      body: JSON.stringify({ ok: false, error: { code: "backend_timeout", message: "等待超时", outcome: "unknown", status: 504 } }),
    });
  });
  await page.route("**/api/datapilot/tasks/**", async (route) => {
    if (route.request().method() === "GET") {
      statusCalls += 1;
      await route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({
          ok: true, reason_code: "task_status_ready", safety_status: "passed", message: "任务状态已核对。",
          task: { task_id: completeFixture.task.task_id, task_version: 3, status: "active", expires_at: completeFixture.task.expires_at },
        }),
      });
      return;
    }
    clearedVersion = new URL(route.request().url()).searchParams.get("expected_version") ?? "";
    await route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        ok: true, reason_code: "task_cleared", safety_status: "passed", message: "任务已清理。",
        task: { ...completeFixture.task, task_version: 4, status: "cleared" },
      }),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /开始分析/ }).click();
  await page.getByLabel("输入数据分析问题").fill("比较 7 月和 8 月实际净退款金额");
  await page.getByRole("button", { name: /继续任务/ }).click();
  await expect(page.getByText("当前 lineage 已冻结")).toBeVisible();
  await page.reload();
  await expect(page.getByText("当前 lineage 已冻结")).toBeVisible();
  await expect(page.getByText("比较 7 月和 8 月实际净退款金额")).toBeVisible();
  await page.getByRole("button", { name: "检查任务状态" }).click();
  await expect(page.getByRole("status")).toContainText("已完成并提交到 v3");
  await expect(page.getByLabel("输入数据分析问题")).toBeEnabled();
  await page.getByRole("button", { name: "清理任务与本地快照" }).click();
  expect(queryCalls).toBe(2);
  expect(statusCalls).toBe(1);
  expect(clearedVersion).toBe("3");
});

test("clear 同步清理服务端 task 投影与 sessionStorage", async ({ page }) => {
  await mockHealth(page);
  await page.route("**/api/datapilot/query", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(completeFixture) }),
  );
  let deleteUrl = "";
  await page.route("**/api/datapilot/tasks/**", async (route) => {
    deleteUrl = route.request().url();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        reason_code: "task_cleared",
        safety_status: "passed",
        message: "任务已清理。",
        task: { ...completeFixture.task, status: "cleared", task_version: 2 },
      }),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /开始分析/ }).click();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("datapilot.m50.session.v1"))).not.toBeNull();
  await page.getByRole("button", { name: "清理任务与本地快照" }).click();
  await expect(page.getByText("尚未开始 task")).toBeVisible();
  await expect(page.getByRole("status")).toContainText("本地公开快照也已移除");
  expect(await page.evaluate(() => sessionStorage.getItem("datapilot.m50.session.v1"))).toBeNull();
  expect(deleteUrl).toContain("expected_version=1");
  expect(deleteUrl).toContain("user_role=ops");
});

test("legacy clarification 与 bounded follow-up 只提交服务端签发字段", async ({ page }) => {
  const requests: Array<Record<string, unknown>> = [];
  const followUpReady = {
    ...clarificationFixture,
    answer: "澄清已完成。",
    answer_status: "complete",
    execution_status: "completed",
    graph_invocation_count: 1,
    reason_code: "answer_ready",
    trace_id: "trace-m50-follow-up-ready",
    turn_action: "resume",
    thread: {
      ...clarificationFixture.thread,
      checkpoint_version: 2,
      status: "follow_up_ready",
      clarification: null,
      follow_up_budget_remaining: 1,
      follow_up: {
        identity: "follow-up-m50-v1",
        actions: [{
          action: "explain_same_evidence",
          label: "解释同一证据",
          fields: [{ key: "focus", label: "关注点", value_type: "text", allowed_values: [], max_length: 64 }],
        }],
      },
    },
  };
  const resolved = {
    ...followUpReady,
    answer: "追问已完成。",
    trace_id: "trace-m50-follow-up-resolved",
    turn_action: "follow_up",
    thread: {
      ...followUpReady.thread,
      checkpoint_version: 3,
      status: "resolved",
      follow_up_budget_remaining: 0,
      follow_up: null,
    },
  };
  const responses = [clarificationFixture, followUpReady, resolved];
  await mockHealth(page);
  await page.route("**/api/datapilot/query", async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(responses[requests.length - 1]) });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /兼容模式/ }).click();
  await page.getByRole("button", { name: /开始分析/ }).click();
  await expect(page.getByText("请选择月份。")).toBeVisible();
  // reload 后必须恢复 legacy mode；否则同一 thread snapshot 会被 task UI 误读。
  await page.reload();
  await expect(page.getByText("请选择月份。")).toBeVisible();
  await page.getByLabel("月份").fill("2026-07");
  await page.getByRole("button", { name: /提交澄清/ }).click();
  expect(requests[1]).toMatchObject({
    thread_id: "thread_m50_fixture_001",
    expected_version: 1,
    clarification_answers: { month: "2026-07" },
  });
  await page.getByRole("button", { name: "解释同一证据" }).click();
  await page.getByLabel("关注点").fill("退款变化");
  await page.getByRole("button", { name: /执行追问/ }).click();
  expect(requests[2]).toMatchObject({
    thread_id: "thread_m50_fixture_001",
    expected_version: 2,
    follow_up_action: "explain_same_evidence",
    follow_up_fields: { focus: "退款变化" },
  });
  expect(requests[2]).not.toHaveProperty("task");
  await expect(page.getByText("追问已完成。")).toBeVisible();
});
