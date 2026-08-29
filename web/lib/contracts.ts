/**
 * Web 对共享网络合同的稳定导入门面。
 *
 * ★ 真正的 schema 位于私有 `@datapilot/contracts` package；保留本文件让现有 UI import
 * 不承担 workspace 布局知识，也避免把 presenter/session 逻辑塞进共享包。
 */
export * from "@datapilot/contracts";
