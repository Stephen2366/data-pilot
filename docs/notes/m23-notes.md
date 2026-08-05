# M23 Eval / Semantic / Database Baseline Hygiene Notes

## Implementation checklist

- [x] 收口退款率、订单量与退款归因的单一语义定义。
- [x] 将影响 join / 过滤的数据库事实放入运行时可检索语料。
- [x] 把可确定性比较的 `expected_sql` case 升级为结果校验，保留真正的 manual case。
- [x] 增加语义、case 与 MySQL / SQLite oracle 边界的 focused regression。
- [x] 固化验证快照、取舍与未覆盖异常。
- [x] 为 Milvus collection 补上 Schema 文档内容 hash 复用校验，阻止同数量的旧语义向量被静默复用。
- [x] 将异常彩蛋审计独立为长期章节，并新增 3 条异常 case 与不复制既有 YAML 的专项组合入口。

## Working boundary

- 本模块不切换主模型、embedding、Milvus、RRF，也不清洗确定性 seed。
- SQLite 仍是离线 deterministic eval oracle；MySQL 仅做只读 ground-truth audit。

## Decisions and verification snapshot（2026-08-05）

- 商品退款率定义为成交订单内的退款单数 / 订单数：优先 `refunds.order_item_id -> order_items.product_id`，整单退款仅回退 `refunds.product_id`，不把整单退款复制给同订单每个商品。
- `order_count` 统一为 `COUNT(DISTINCT orders.id)`；未明确“成交”的订单量默认仍统计全量订单，只有题面明确成交才附加支付和取消过滤。
- challenge 的 12 条自动 SQL case、formal 的 8 条自动 SQL case 均改为 `result_match` 或已有 `expected_value`；两条递归 / SCD 困难题保留 `manual_review`，不伪装成自动能力分。
- `orders.order_status`、`orders.source_order_no`、`refunds.source_order_no` 和退款关系文档补入状态枚举、SRC/ORD 禁止 join、整单退款回退边界，因此会进入 field / relation schema documents。
- MySQL 与确定性 SQLite 对 20 条 reference SQL 的只读审计均执行成功，逐条行数一致；这证明当前 reference 可移植，不意味着 SQLite eval 自动覆盖所有 MySQL 方言风险。
- focused：`42 passed, 1 warning`；全量：`152 passed, 1 warning`。warning 为既有 Starlette/httpx `TestClient` deprecation。
- M23 后 `MilvusVectorIndex` 将 `schema_docs_hash` 写入 collection schema description；已有 collection 复用前必须同时匹配维度、行数和内容 hash。`net_refund_amount` 使 corpus 从 194 条增至 195 条；缺少该标记或仍为旧 corpus 的 M20/M22 collection 必须使用唯一新 collection 或 `MILVUS_RESET_COLLECTION=true` 显式重建。
- 异常专项固定为 6 条自动 case + `db_join_003` 人工归因素材：新增实际净退款金额只统计 `completed`，按 `processed_at` 过滤，并保留负数冲销；新增退款到渠道必须走内部 `refunds.order_id`；新增订单头 / 明细金额对账。`database-exception-suite.yaml` 只引用已有 case ID，避免 formal / challenge / diagnostic 的重复定义。
