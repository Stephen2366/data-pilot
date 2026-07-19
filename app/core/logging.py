"""请求日志与全链路追踪模块：日志格式配置 + trace_id 中间件。

★ 每个 HTTP 请求自动生成/透传 trace_id，排查问题时靠它把"用户看到的错误"
和"服务端日志"串起来。
"""

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request, Response

# 请求日志专用 logger：独立命名空间，后续可以只对它单独调整级别或输出目的地。
logger = logging.getLogger("datapilot.request")


def configure_logging() -> None:
    """配置全局日志的基础格式：时间 / 级别 / logger 名 / 内容。

    ★ `basicConfig` 只在根 logger 还没有 handler 时生效一次，重复调用不会叠加配置，
    所以放在应用启动入口调用是安全的。
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def register_request_logging_middleware(app: FastAPI) -> None:
    """注册请求日志中间件：为每个请求生成 / 透传 trace_id，并记录一行访问日志。

    中间件类比 SpringBoot 的 Filter / Interceptor：请求进入路由前、响应返回前都经过这里。
    ★ method / path / status / latency_ms / trace_id 是 M2 验收要求的日志字段；
    排查问题时靠 trace_id 把“用户看到的错误”和“服务端日志”串起来。
    """

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next) -> Response:
        # 上游（网关 / 前端）传了 x-trace-id 就复用，没传就现场生成，保证链路编号不断。
        trace_id = request.headers.get("x-trace-id") or str(uuid4())
        # 挂到 request.state：后续路由函数和异常处理器都从这里读同一个 trace_id。
        request.state.trace_id = trace_id
        started_at = time.perf_counter()
        # 先假定 500：若 call_next 中途抛异常，finally 里记录的就是这个兜底状态码。
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            # 无论成功失败都记一行日志；perf_counter 是单调时钟，不受系统改时间影响。
            latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "request_completed method=%s path=%s status=%s latency_ms=%s trace_id=%s",
                request.method,
                request.url.path,
                status_code,
                latency_ms,
                trace_id,
            )

        # 把 trace_id 回传给调用方：用户报障时报这个编号，服务端就能定位对应日志。
        response.headers["x-trace-id"] = trace_id
        return response
