"""Upload target adaptation; the original parser retains source identities and locators."""

import hashlib
from uuid import uuid4

from qunxue_api.modules.research_materials import (
    MaterialFormat,
    MaterialParseError,
    UnsupportedMaterialFormat,
)
from qunxue_api.modules.shared_knowledge import (
    SharedDocument,
    SharedKnowledgeService,
    SharedKnowledgeValidationError,
)


class SharedKnowledgeApplication(SharedKnowledgeService):
    def __init__(self, repository, *, parser):
        super().__init__(repository)
        self._parser = parser

    def upload(self, user_id, kb_id, *, filename, media_type, content, request_key):
        self.require_manage(user_id, kb_id)
        # Retrying an old upload cannot reattach a removed file.
        key = hashlib.sha256(f"{kb_id}:{request_key}".encode()).hexdigest()
        previous = self.repository.find_upload(user_id, key)
        if previous:
            if (
                previous.content_hash != hashlib.sha256(content).hexdigest()
                or previous.filename != filename
            ):
                raise SharedKnowledgeValidationError(
                    "相同请求标识不能上传不同文件，请重新发起上传。"
                )
            return previous
        if len(self.repository.documents(kb_id)) >= 100:
            raise SharedKnowledgeValidationError("每个课程资料库最多保存 100 份文件。")
        try:
            material_format = MaterialFormat.resolve(filename=filename, media_type=media_type)
        except UnsupportedMaterialFormat as exc:
            raise SharedKnowledgeValidationError("文件格式不支持或与扩展名不一致。") from exc
        if material_format.is_media:
            raise SharedKnowledgeValidationError(
                "课程资料暂支持 PDF、DOCX、PPTX、Markdown 和 TXT。"
            )
        document_id, parse_id = uuid4(), uuid4()
        error, segments, warnings = None, (), ()
        try:
            parsed = self._parser(
                filename=filename,
                media_type=media_type,
                content=content,
                material_id=document_id,
                parse_id=parse_id,
            )
            skipped = parsed.structured_document.get("unreadable_slides", [])
            if skipped:
                pages = "、".join(str(page) for page in skipped)
                warnings = (f"第 {pages} 页未提取到正文，图片内容未识别。",)
            segments = tuple(
                {
                    "segment_id": block.segment_id,
                    "parse_id": str(parse_id),
                    "ordinal": block.ordinal,
                    "kind": block.kind,
                    "text": block.text,
                    "content_hash": block.content_hash,
                    "locator": block.locator.as_dict(),
                }
                for block in parsed.blocks
            )
        except MaterialParseError as exc:
            error = str(exc)
        doc = SharedDocument(
            document_id,
            user_id,
            filename,
            material_format.canonical_media_type,
            hashlib.sha256(content).hexdigest(),
            len(content),
            parse_id,
            "failed" if error else "ready",
            segments,
            error,
            warnings,
        )
        # A synchronous parse and its links commit together. Process failure leaves no stuck job.
        self.require_manage(user_id, kb_id)
        saved = self.repository.save_document(doc, content=content, request_key=key, kb_id=kb_id)
        if saved.content_hash != doc.content_hash or saved.filename != doc.filename:
            raise SharedKnowledgeValidationError("相同请求标识不能上传不同文件。")
        self.repository.commit()
        return saved
