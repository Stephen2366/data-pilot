const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_TIMEOUT_MS = 310_000;

export type AdapterConfig = {
  apiBaseUrl: URL;
  userRole: string;
  timeoutMs: number;
};

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase();
  if (normalized === "localhost" || normalized === "[::1]" || normalized === "::1") return true;
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(normalized);
  if (!match) return false;
  const octets = match.slice(1).map(Number);
  return octets.every((part) => part >= 0 && part <= 255) && octets[0] === 127;
}

/**
 * 解析 adapter 启动配置，并在任何 HTTP 请求之前冻结安全边界。
 *
 * Client 看不到这些字段；role 与 backend 只能由启动该本地进程的人通过环境变量配置。
 */
export function loadConfig(environment: NodeJS.ProcessEnv = process.env): AdapterConfig {
  const rawBase = environment.DATAPILOT_API_BASE_URL ?? DEFAULT_API_BASE_URL;
  let apiBaseUrl: URL;
  try {
    apiBaseUrl = new URL(rawBase);
  } catch {
    throw new Error("configuration_invalid: DATAPILOT_API_BASE_URL is not a URL");
  }
  if (
    apiBaseUrl.protocol !== "http:" ||
    !isLoopbackHostname(apiBaseUrl.hostname) ||
    apiBaseUrl.username !== "" ||
    apiBaseUrl.password !== "" ||
    apiBaseUrl.search !== "" ||
    apiBaseUrl.hash !== "" ||
    !["", "/"].includes(apiBaseUrl.pathname)
  ) {
    throw new Error("configuration_invalid: backend must be a credential-free loopback HTTP origin");
  }

  const userRole = environment.DATAPILOT_MCP_USER_ROLE ?? "ops";
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(userRole)) {
    throw new Error("configuration_invalid: DATAPILOT_MCP_USER_ROLE is invalid");
  }
  const timeoutMs = Number(environment.DATAPILOT_MCP_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);
  if (!Number.isInteger(timeoutMs) || timeoutMs < 300_000 || timeoutMs > 900_000) {
    throw new Error("configuration_invalid: timeout must be an integer from 300000 to 900000 ms");
  }
  return { apiBaseUrl, userRole, timeoutMs };
}
