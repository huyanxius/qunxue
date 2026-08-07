from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass

from qunxue_api.adapters.model.types import ModelScenario


@dataclass(frozen=True, slots=True)
class BuiltInCase:
    case_id: str
    title: str
    summary: str
    phenomenon: str
    research_intent: str | None
    context: str | None
    content_status: str
    scenario: ModelScenario
    knowledge_release_id: str


@dataclass(frozen=True, slots=True)
class BuiltInCasePage:
    items: tuple[BuiltInCase, ...]
    next_cursor: str | None


class BuiltInCaseCatalog:
    def __init__(self, cases: tuple[BuiltInCase, ...]) -> None:
        self._cases = cases
        self._by_id = {item.case_id: item for item in cases}
        self._by_phenomenon = {item.phenomenon: item for item in cases}
        if len(self._by_id) != len(cases):
            raise ValueError("built-in case ids must be unique")
        if len(self._by_phenomenon) != len(cases):
            raise ValueError("built-in case phenomena must be unique")

    @classmethod
    def default(cls) -> "BuiltInCaseCatalog":
        release_id = "knowledge-demo-v1"
        return cls(
            (
                BuiltInCase(
                    case_id="success",
                    title="社区互助机制比较",
                    summary="去标识化合成案例：信息足以演示完整判断链。",
                    phenomenon="同一社区中的互助为何逐渐减少？",
                    research_intent="比较关系持续性与制度规范的解释",
                    context="社区持续更新，成员流动增加",
                    content_status="demonstration",
                    scenario=ModelScenario.SUCCESS,
                    knowledge_release_id=release_id,
                ),
                BuiltInCase(
                    case_id="no-reliable-candidate",
                    title="暂无可靠理论候选",
                    summary="去标识化合成案例：召回结果不足以形成可靠候选。",
                    phenomenon="短期活动结束后参与热情为何迅速下降？",
                    research_intent="检验现有理论是否足以解释该现象",
                    context="缺少活动前后可比材料",
                    content_status="demonstration",
                    scenario=ModelScenario.NO_RELIABLE_CANDIDATE,
                    knowledge_release_id=release_id,
                ),
                BuiltInCase(
                    case_id="timeout",
                    title="模型调用超时",
                    summary="去标识化合成案例：演示超时后的可恢复状态。",
                    phenomenon="跨组织协作中的沟通为何反复中断？",
                    research_intent="比较结构与互动层面的解释",
                    context="模型调用被确定性设置为超时",
                    content_status="demonstration",
                    scenario=ModelScenario.TIMEOUT,
                    knowledge_release_id=release_id,
                ),
                BuiltInCase(
                    case_id="insufficient-sources",
                    title="来源不足",
                    summary="去标识化合成案例：演示证据来源不足的降级状态。",
                    phenomenon="新制度推行后反馈为何出现明显分化？",
                    research_intent="识别制度执行与群体差异的关系",
                    context="当前只有一条未核验的系统摘要",
                    content_status="demonstration",
                    scenario=ModelScenario.INSUFFICIENT_SOURCES,
                    knowledge_release_id=release_id,
                ),
                BuiltInCase(
                    case_id="user-deferred",
                    title="用户暂缓决定",
                    summary="去标识化合成案例：模型成功后由用户暂缓理论决定。",
                    phenomenon="志愿团队中的职责分配为何持续摇摆？",
                    research_intent="先比较候选解释，再由用户决定是否继续",
                    context="用户希望补充材料后再作正式采用决定",
                    content_status="demonstration",
                    scenario=ModelScenario.USER_DEFERRED,
                    knowledge_release_id=release_id,
                ),
            )
        )

    def get(self, case_id: str) -> BuiltInCase:
        try:
            return self._by_id[case_id]
        except KeyError as error:
            raise LookupError(case_id) from error

    def find_by_phenomenon(self, phenomenon: str) -> BuiltInCase | None:
        return self._by_phenomenon.get(phenomenon.strip())

    def list_all(self) -> tuple[BuiltInCase, ...]:
        return self._cases

    @property
    def knowledge_release_id(self) -> str:
        release_ids = {item.knowledge_release_id for item in self._cases}
        if len(release_ids) != 1:
            raise RuntimeError("built-in cases must share one knowledge release")
        return next(iter(release_ids))

    def list_page(self, *, cursor: str | None, limit: int) -> BuiltInCasePage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        offset = self._decode_cursor(cursor) if cursor else 0
        if offset > len(self._cases):
            raise ValueError("cursor is outside the built-in case collection")
        items = self._cases[offset : offset + limit]
        next_offset = offset + len(items)
        next_cursor = (
            self._encode_cursor(next_offset) if next_offset < len(self._cases) else None
        )
        return BuiltInCasePage(items=items, next_cursor=next_cursor)

    @staticmethod
    def _encode_cursor(offset: int) -> str:
        return urlsafe_b64encode(f"case:{offset}".encode()).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> int:
        try:
            padding = "=" * (-len(cursor) % 4)
            value = urlsafe_b64decode(f"{cursor}{padding}").decode()
            prefix, raw_offset = value.split(":", maxsplit=1)
            if prefix != "case":
                raise ValueError
            offset = int(raw_offset)
            if offset < 0:
                raise ValueError
            return offset
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("invalid built-in case cursor") from error
