# M34 EnterpriseRAG-Bench 长期基线轻量清单

> 本文件固化 2026-08-16 已登记长期 RAG 基线的可提交身份与文件校验值。原始 execution 明细体积较大，仍保存在本机 `.agent_work/temp/`，不提交 Git；即使临时文件之后被清理，本清单与 `docs/state/eval-baselines.md` 仍能证明当时登记的是哪组 completed artifact。它不替代原始逐题证据，也不能单独用于重新评分。

## 共同身份

| 项目 | 值 |
|---|---|
| dataset identity | `70c572328a90ec5dc380c086181af4d3706264f5aefd71c2856329f996d93cf7` |
| question-set identity | `9a21ca95995c9d2c9e962351e9e7485630233a89c280a5c928b6bc40b9cd271c` |
| split identity | `f8164d3f57fe4c262f3a8f7ecd293196748d2abcbd4f387f3fbb8f50208138dd` |
| external profile identity | `e8783fe0b3eb738132f11b701ed2fadedfd7da2c0958d88c2755863a17875fa2` |
| corpus / split | 36,417 documents / 139,214 units；60 diagnostic/dev + 120 held-out |

## Completed artifact 对账

| Artifact | 协议 / runtime | Artifact identity | 原始文件 SHA-256 | 关键结果 |
|---|---|---|---|---|
| lexical retrieval dev | `enterprise-rag-retrieval-eval-v1`；`knowledge-enterprise-sqlite-lexical-v1`；`fts5-unicode61-or-bm25-dedup-physical-v1`；@20 | `7b444240067f990dc1bc11d45b5010e0e8306a5100f29cd9d6d3a4da6188d182` | `ea5022c4bf89229d2515fb71e9ff2e8ddbb162cf22178f572c57837abc56edd2` | coverage/all-gold/MRR `0.810417 / 0.766667 / 0.645303` |
| lexical retrieval held-out | 同上 | `4d77b74080da851c3c3fa58cac39d5317946ac6ded952349b3e69b4a02fa75c7` | `649a3899147b2e8e33486277e15aa9f327472c548784e6b55431aa4548f645e5` | `0.823125 / 0.775000 / 0.723134` |
| semantic retrieval dev | `enterprise-rag-retrieval-eval-v1`；`knowledge-enterprise-milvus-semantic-v1`；`qwen-dense-cosine-dedup-physical-v1`；@20 | `f207369360bac6f57ae3c46d628b6d87746fe9b398a7e712988fecd4cf27ac26` | `92d72f1a4230bea8e1f4b1c89d84811b9e7b9940249e86989537293ebc371ccb` | `0.737500 / 0.700000 / 0.621421` |
| semantic retrieval held-out | 同上 | `32ab5f303047c4fcf52fa70657ec806fbed9735cb4ce593139fa7c3fde88c8c6` | `7b022f7bc0d6785c1dfaaad5bc83f02d66125984ecc0c122e20a78857c8b5957` | `0.773958 / 0.741667 / 0.630477` |
| Answer / Citation full | `enterprise-rag-answer-eval-v1`；lexical external 默认；Composer `rag-qwen-evidence-support-nonthinking-unbounded-v4` | `d9fa2b20863c568cbc7091dea4724c5d69d74979b5b4ba3d3eb14ff101eeb41f` | `75592af855ab05993fe5593c2e90210d0f42f74b10fda18a56b3023578fd99fa` | complete `146/180`；all-gold cited `80/180`；mean gold coverage `49.3981%`；10 unavailable；24 support contract rejected；405,305 tokens |

## 原始文件位置与解释边界

- Retrieval：`.agent_work/temp/m34-{lexical,semantic}-tool-{dev,heldout}-retrieval.json`
- Answer：`.agent_work/temp/m34-answer-eval-full-v4.json`
- 上述五个文件在固化本清单时均存在、状态为 `completed`，共同 dataset/question/split/profile identity 一致。
- Retrieval 只证明 gold document coverage；Answer `complete` 只证明回答、support 与 citation 合同闭合。M34 未启用 LLM Judge，因此两者都不能冒充自然答案正确率或生产质量。
