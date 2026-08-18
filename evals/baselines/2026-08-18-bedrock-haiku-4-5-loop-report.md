# Context tuning run

- model: `bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0`
- samples per case: 3
- reliability threshold: 0.8
- stop reason: **plateau -- no holdout improvement in 3 iterations**

## Per-iteration

| iter | ctx | protocol | train | holdout | strict | flaky | tokens |
|---|---|---|---|---|---|---|---|
| 0 | v000 | tool_call | 0.33 | 0.50 | 7 | 0 | 186600 |
| 1 | v001 | tool_call | 0.43 | 0.50 | 9 | 0 | 225723 |
| 2 | v001 | tool_call | 0.33 | 0.50 | 7 | 0 | 218085 |
| 3 | v001 | tool_call | 0.43 | 0.50 | 9 | 0 | 204828 |

## Outcome

- baseline holdout: 0.50
- best holdout: 0.50 (context v000)
- improvement: +0.00

The returned context is the best holdout-scoring version, not the last one -- train score can be raised by memorising, so holdout is the only evidence a change generalises.
