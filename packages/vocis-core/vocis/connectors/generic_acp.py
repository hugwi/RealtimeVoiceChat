"""Generic ACP executable lifecycle.

The existing SDK client is already platform-neutral despite its prototype-era
name. Keep one implementation until its behavior actually needs to diverge.
"""

from ..acp_sdk_client import (
    OfficialSdkAcpHarnessClient as GenericAcpClient,
    spawn_omnigent_acp_harness as spawn_generic_acp_connector,
)

__all__ = ["GenericAcpClient", "spawn_generic_acp_connector"]
