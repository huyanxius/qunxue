"""Safe source registry. Automatic collection is intentionally opt-in and unconfigured."""

from qunxue_api.modules.frontier_knowledge import Candidate, SourceBlock, SourceSnapshot

SOURCE_DEFINITIONS = (
    (
        "society-journal",
        "社会",
        "journal_public_abstract",
        "https://www.society.shu.edu.cn",
        24,
        ["www.society.shu.edu.cn"],
        "公开原刊摘要；本批为定额采样，非连续全量监测",
    ),
    (
        "social-construction",
        "社会建设",
        "journal_public_abstract",
        "https://shjs.ruc.edu.cn",
        24,
        ["shjs.ruc.edu.cn"],
        "公开原刊摘要；本批为定额采样，非连续全量监测",
    ),
    (
        "sociological-studies",
        "社会学研究",
        "journal_directory",
        "https://shxyj.ajcass.com",
        12,
        ["sociology.nju.edu.cn", "public.nju.edu.cn"],
        "期刊目录/原文授权待核实；当前仅人工公开成果线索",
    ),
    (
        "social-development",
        "社会发展研究",
        "journal_directory",
        "https://shfzyj.ajcass.com",
        24,
        ["sociology.shu.edu.cn"],
        "期刊目录/原文授权待核实；当前仅人工公开成果线索",
    ),
    (
        "youth-studies",
        "青年研究",
        "journal_directory",
        "https://qnyj.ajcass.com",
        12,
        ["cohd.cau.edu.cn", "www.sps.sdu.edu.cn"],
        "期刊目录/原文授权待核实；当前仅人工公开成果线索",
    ),
    (
        "china-youth",
        "中国青年研究",
        "journal_directory",
        "https://www.cycnet.com",
        12,
        ["epc.swu.edu.cn"],
        "期刊目录/原文授权待核实；当前仅人工公开成果线索",
    ),
    (
        "sociology-perspective",
        "社会学视野",
        "werss",
        "https://www.sociologyol.org",
        2,
        [],
        "WeRSS尚未部署或授权，公众号账号ID和认证主体尚未核验",
    ),
    (
        "social-work-news",
        "中国社会工作报",
        "official_newspaper",
        "https://www.zyshgzb.gov.cn",
        6,
        ["www.zyshgzb.gov.cn"],
        "当前为人工核验官方实践文章；自动采集授权与站点规则待确认",
    ),
)


class SourceNotConfigured(RuntimeError):
    code = "SourceNotConfigured"


class DisabledSourceAdapter:
    """Port implementation makes unsafe or unauthenticated collection fail closed."""

    def __init__(self, source_id: str, reason: str):
        self.source_id = source_id
        self.reason = reason

    def discover(self, cursor: str | None) -> tuple[Candidate, ...]:
        raise SourceNotConfigured(self.reason)

    def fetch(self, candidate: Candidate) -> SourceSnapshot:
        raise SourceNotConfigured(self.reason)

    def parse(self, snapshot: SourceSnapshot) -> tuple[SourceBlock, ...]:
        if snapshot.source_id != self.source_id:
            raise ValueError("snapshot source does not match adapter")
        return snapshot.blocks


class LocalCorpusSourceAdapter:
    """Replay an explicitly supplied crawler export through the durable source lifecycle.

    Only local, already-authorized captured records are consumed. This class does not
    fetch any URL or pretend a quota sample is a continuously monitored source.
    """

    def __init__(self, source_id: str, name: str, records: list[dict]):
        self.source_id = source_id
        self.records = {
            str(r.get("external_id") or r["id"]): r for r in records if r["source_name"] == name
        }
        from qunxue_api.modules.frontier_knowledge import content_hash

        self.next_cursor = content_hash(self.records)
        self.reason = "explicit_local_corpus_replay"

    def discover(self, cursor: str | None) -> tuple[Candidate, ...]:
        from qunxue_api.modules.frontier_knowledge import content_hash

        if cursor == self.next_cursor:
            return ()
        return tuple(
            Candidate(
                self.source_id,
                key,
                r["title"],
                r["url"],
                tuple(r.get("authors") or []),
                r.get("doi"),
                r.get("published_at"),
                content_hash(r),
            )
            for key, r in sorted(self.records.items())
        )

    def fetch(self, candidate: Candidate) -> SourceSnapshot:
        from qunxue_api.modules.frontier_knowledge import content_hash

        if candidate.source_id != self.source_id or candidate.external_id not in self.records:
            raise ValueError("unknown local source candidate")
        record = self.records[candidate.external_id]
        digest = content_hash(record)
        snapshot_id = f"local-{digest[:32]}"
        blocks = tuple(
            SourceBlock(f"{snapshot_id}:{i}", e["snippet"], e["locator"])
            for i, e in enumerate(record.get("evidence", []))
            if e.get("snippet")
        )
        return SourceSnapshot(
            snapshot_id,
            self.source_id,
            digest,
            "metadata_and_short_excerpt",
            blocks,
            metadata=record,
        )

    def parse(self, snapshot: SourceSnapshot) -> tuple[SourceBlock, ...]:
        if snapshot.source_id != self.source_id:
            raise ValueError("snapshot source mismatch")
        return snapshot.blocks
