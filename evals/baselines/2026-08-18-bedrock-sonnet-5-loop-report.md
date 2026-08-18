# Context tuning run

- model: `bedrock/global.anthropic.claude-sonnet-5`
- samples per case: 3
- reliability threshold: 0.8
- stop reason: **only environment/config failures remain -- not context-addressable**

## Per-iteration

| iter | ctx | protocol | train | holdout | strict | flaky | tokens |
|---|---|---|---|---|---|---|---|
| 0 | v000 | tool_call | 0.38 | 0.50 | 8 | 0 | 226485 |
| 1 | v001 | tool_call | 0.41 | 0.67 | 8 | 2 | 265424 |
| 2 | v002 | tool_call | 0.00 | 0.00 | 0 | 0 | 0 |

## Outcome

- baseline holdout: 0.50
- best holdout: 0.67 (context v001)
- improvement: +0.17

The returned context is the best holdout-scoring version, not the last one -- train score can be raised by memorising, so holdout is the only evidence a change generalises.
