"""Infrastructure adapters for automation, storage, AI, and platform sync."""

from .ai_stub import TemplatePromptWorkflowGenerator
from .artifact_store import FileArtifactStore, InMemoryArtifactStore
from .automation_stub import StubAutomationProvider
from .deepseek_generator import DeepSeekWorkflowGenerator
from .deepseek_instrument_generator import DeepSeekInstrumentProfileGenerator
from .inmemory import EchoInstructionGenerator, StubProcessExecutorClient
from .platform_stub import StubPlatformClient
from .process_signal import UdpProcessExecutorClient
from .speclabos_client import SpecLabOSPlatformClient
from .local_vision import LocalVisionProvider
from .vision_stub import StubVisionProvider
from .win32_automation import Win32AutomationProvider

__all__ = [
    "DeepSeekInstrumentProfileGenerator",
    "DeepSeekWorkflowGenerator",
    "EchoInstructionGenerator",
    "FileArtifactStore",
    "InMemoryArtifactStore",
    "LocalVisionProvider",
    "SpecLabOSPlatformClient",
    "StubAutomationProvider",
    "StubPlatformClient",
    "StubProcessExecutorClient",
    "StubVisionProvider",
    "TemplatePromptWorkflowGenerator",
    "UdpProcessExecutorClient",
    "Win32AutomationProvider",
]
