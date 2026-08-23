# Release-bound retrieval evaluation

这里保存 #101 混合检索的冻结评测集与真实 Provider 结果。三个版本都绑定同一份
`KnowledgeRelease`、内容哈希、索引 Schema 和模型；失败版本保留，不覆盖历史。

## Frozen provenance

- Knowledge release: `knowledge-final-d58ae546aff48b45891359b9d29e294df8c96ba1d5a71c781394e200b7f0db67`
- Content hash: `sha256:d58ae546aff48b45891359b9d29e294df8c96ba1d5a71c781394e200b7f0db67`
- Retrieval index: `retrieval-index:88e00667c24e34fd93c3dd30`
- Chunk schema: `retrieval-corpus-v1`
- Embedding: `Pro/BAAI/bge-m3`
- Reranker: `Pro/BAAI/bge-reranker-v2-m3`

## Experiment history

### v1 — failed and retired

`retrieval_v1.json` used one global `0.06` rerank threshold and treated a generic
thesis-topic request as a negative query. The real held-out run exposed two coupled
problems: the alienated-labour paraphrase could fall below the threshold, while simply
lowering that threshold could not give a principled meaning to the otherwise generic
topic request. The suite also encoded that product intent incorrectly: a formal topic
request should search approved theories and return candidates, not be rejected as
off-corpus.

### v2 — failed and reverted

`retrieval_v2.json` changed topic requests to require non-empty results and evaluated a
lexical-title expansion inside the reranker query. In the frozen held-out run that
expansion promoted `theory:alienated-labour` above the expected
`theory:class-struggle` result for `test-v2-class-struggle`, so the Top-1 gate failed.
The title-expansion implementation was removed; the suite remains only as a record of
the rejected approach.

### v3 — passed once, then frozen

`retrieval_v3.json` moves the expansion to task classification: a formal topic request
adds an explicit retrieval objective before the unchanged Embedding → hybrid recall →
mandatory Reranker pipeline. Calibration fixed the global rerank threshold at `0.01`.
The v3 test split was then run exactly once against SiliconFlow on 2026-08-24; neither
its queries nor parameters were changed afterward.

Command shape, with credentials and paths supplied only through the runtime environment:

```bash
uv run python scripts/evaluate_retrieval.py \
  --suite evals/retrieval_v3.json \
  --split test
```

| Case | Expected behavior | Final result | Rerank score(s) | Latency |
| --- | --- | --- | --- | ---: |
| `test-v3-historical-materialism` | Top-1 historical materialism | historical materialism | `0.18533090` | 4207.3 ms |
| `test-v3-class-struggle` | Top-1 class struggle | class struggle, historical materialism | `0.66836107`, `0.02569173` | 4249.6 ms |
| `test-v3-alienated-labour` | Top-1 alienated labour | alienated labour | `0.15712234` | 3649.7 ms |
| `test-v3-symbolic-interaction` | reject off-corpus query | no result | — | 3871.7 ms |
| `test-v3-social-capital` | reject off-corpus query | no result | — | 3688.1 ms |
| `test-v3-topic-request` | return approved candidates | alienated labour, historical materialism, class struggle | `0.08385953`, `0.08118509`, `0.07129809` | 3691.8 ms |

Final gates:

- positive Top-1 accuracy: `1.0`
- negative rejection rate: `1.0`
- required-nonempty rate: `1.0`
- P95 latency: `4249.6 ms` (gate: at most `8000 ms`)
- provider calls: `2` per query (`1` Embedding + `1` Reranker)
- reranker documents: `3` per query (gate: at most `30`)

This is evidence for the frozen three-theory release, not a claim of broad-domain
retrieval quality. Expanding the corpus requires a new release-bound index and a newly
frozen evaluation suite; historical test queries must not be tuned after inspection.
