"""Feed an authorized document set to the existing transient-chunk retriever."""

from dataclasses import replace
from inspect import signature

from qunxue_api.adapters.research_agent.retrieval import lexical_relevance_score
from qunxue_api.adapters.retrieval import RetrievalChunk, RetrievalPipelineUnavailable
from qunxue_api.modules.agent_conversation import AgentEvidence


class SharedKnowledgeReferences:
    def __init__(self, application, retriever):
        self.application = application
        self.retriever = retriever

    def prepare(self, *, user_id, kb_id, query, tools):
        kb = self.application.require_read(user_id, kb_id)
        documents = self.application.documents(user_id, kb_id, ready_only=True)
        chunks, coordinates = [], {}
        for doc in documents:
            for segment in doc.segments:
                key = f"material:{doc.id}:{segment['segment_id']}"
                chunk = RetrievalChunk(
                    chunk_id=key,
                    document_kind="research_material",
                    knowledge_id=None,
                    theory_id=None,
                    content_version=1,
                    content_hash=segment["content_hash"],
                    title=doc.filename,
                    text=segment["text"],
                    source_ids=(key,),
                )
                chunks.append(chunk)
                coordinates[key] = (doc, segment)
        search = getattr(self.retriever, "search_chunks", None)
        mode, failure = "lexical", None
        if callable(search) and chunks:
            try:
                options = {}
                if "vector_cache" in signature(search).parameters:
                    options["vector_cache"] = self.application.repository.vector_cache(documents)
                result = search(
                    query=query,
                    chunks=tuple(chunks),
                    limit=8,
                    **options,
                )
                # Custom retrievers can only return identities in the authorized set.
                selected = [
                    hit.chunk.chunk_id for hit in result.hits if hit.chunk.chunk_id in coordinates
                ]
                mode = result.mode
            except RetrievalPipelineUnavailable:
                selected = []
                failure = "课程资料检索暂时失败，本轮未取得教师依据。"
        else:
            ranked = sorted(
                (
                    (lexical_relevance_score(query, title=c.title, text=c.text), c.chunk_id)
                    for c in chunks
                ),
                reverse=True,
            )
            selected = [key for score, key in ranked if score > 0][:8]
        items = []
        for key in selected:
            doc, segment = coordinates[key]
            evidence = AgentEvidence(
                citation_id=key,
                label=f"{kb.name} · {doc.filename}",
                kind="research_material",
                excerpt=segment["text"],
                source_kind="shared_material",
                source_id=key,
                material_id=str(doc.id),
                parse_id=str(doc.parse_id),
                segment_id=segment["segment_id"],
                locator=segment["locator"],
                knowledge_base_id=str(kb.id),
            )
            tools.evidence[key] = evidence
            items.append(
                {
                    "citation_id": key,
                    "label": evidence.label,
                    "excerpt": evidence.excerpt,
                    "locator": segment["locator"],
                    "source_kind": "shared_material",
                }
            )
        tools.select_evidence((*tools.selected_evidence_ids, *selected))
        tools.shared_reference_context = {
            "knowledge_base_name": kb.name,
            "items": items,
            "retrieval_mode": mode,
            "error": failure,
        }
        # Release any cache writes before model telemetry opens another SQLite writer.
        self.application.repository.commit()
        return items

    def filter_history(self, *, user_id, kb_id, turns):
        allowed = {
            str(doc.id) for doc in self.application.documents(user_id, kb_id, ready_only=True)
        }
        result = []
        for turn in turns:
            unavailable = any(
                c.source_kind == "shared_material" and c.material_id not in allowed
                for c in turn.assistant_message.citations
            )
            if unavailable:
                # Keep historical UI text, but never replay revoked retrieval content to a model.
                turn = replace(
                    turn,
                    assistant_message=replace(
                        turn.assistant_message,
                        content="该轮引用的课程资料已移出，本轮不可作为教师依据。",
                        citations=(),
                    ),
                    tool_summary=(),
                )
            result.append(turn)
        return tuple(result)
