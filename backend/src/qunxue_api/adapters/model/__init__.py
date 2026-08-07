"""Provider-neutral model gateway and the deterministic demonstration adapter."""

from qunxue_api.adapters.model.cases import (
    BuiltInCase,
    BuiltInCaseCatalog,
    BuiltInCasePage,
)
from qunxue_api.adapters.model.gateway import ModelGateway
from qunxue_api.adapters.model.mock_provider import (
    DeterministicMockModelProvider,
    create_deterministic_mock_provider,
)
from qunxue_api.adapters.model.recording import (
    InMemoryModelInvocationRecorder,
    SqliteModelInvocationRecorder,
)
from qunxue_api.adapters.model.types import (
    ModelCapabilityName,
    ModelInvocationError,
    ModelInvocationRecord,
    ModelProvider,
    ModelProviderDescriptor,
    ModelProviderFailure,
    ModelProviderResult,
    ModelScenario,
)

__all__ = [
    "BuiltInCase",
    "BuiltInCaseCatalog",
    "BuiltInCasePage",
    "DeterministicMockModelProvider",
    "InMemoryModelInvocationRecorder",
    "ModelCapabilityName",
    "ModelGateway",
    "ModelInvocationError",
    "ModelInvocationRecord",
    "ModelProvider",
    "ModelProviderDescriptor",
    "ModelProviderFailure",
    "ModelProviderResult",
    "ModelScenario",
    "SqliteModelInvocationRecorder",
    "create_deterministic_mock_provider",
]
