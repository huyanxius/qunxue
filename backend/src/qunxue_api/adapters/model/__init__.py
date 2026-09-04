"""Provider-neutral model gateway and the deterministic demonstration adapter."""

from qunxue_api.adapters.model.attempt_recording import (
    PersistedModelRouteAttempt,
    SqliteModelAttemptRecorder,
)
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
from qunxue_api.adapters.model.openai_compatible_provider import (
    OpenAICompatibleModelProvider,
)
from qunxue_api.adapters.model.recording import (
    InMemoryModelInvocationRecorder,
    SqliteModelInvocationRecorder,
)
from qunxue_api.adapters.model.routed_provider import RoutedModelProvider
from qunxue_api.adapters.model.routing import (
    InMemoryModelAttemptRecorder,
    ModelAttemptFailure,
    ModelAttemptRecord,
    ModelAttemptRecorder,
    ModelAttemptResult,
    ModelEndpoint,
    ModelEndpointHealth,
    ModelHealthSnapshot,
    ModelRouteContext,
    ModelRouteExecutor,
    ModelRouteResult,
    ModelRouteScope,
    ModelRoutesUnavailable,
    current_model_route_scope,
    model_route_scope,
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
    "InMemoryModelAttemptRecorder",
    "InMemoryModelInvocationRecorder",
    "ModelAttemptFailure",
    "ModelAttemptRecord",
    "ModelAttemptRecorder",
    "ModelAttemptResult",
    "ModelCapabilityName",
    "ModelEndpoint",
    "ModelEndpointHealth",
    "ModelGateway",
    "ModelHealthSnapshot",
    "ModelInvocationError",
    "ModelInvocationRecord",
    "ModelProvider",
    "ModelProviderDescriptor",
    "ModelProviderFailure",
    "ModelProviderResult",
    "ModelRouteContext",
    "ModelRouteExecutor",
    "ModelRouteResult",
    "ModelRouteScope",
    "ModelRoutesUnavailable",
    "ModelScenario",
    "OpenAICompatibleModelProvider",
    "PersistedModelRouteAttempt",
    "RoutedModelProvider",
    "SqliteModelInvocationRecorder",
    "SqliteModelAttemptRecorder",
    "current_model_route_scope",
    "create_deterministic_mock_provider",
    "model_route_scope",
]
