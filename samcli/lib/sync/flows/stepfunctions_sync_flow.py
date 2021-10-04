"""Base SyncFlow for StepFunctions"""
import logging
from typing import Any, Dict, List, TYPE_CHECKING, cast, Optional


from boto3.session import Session

from samcli.lib.providers.provider import Stack, get_resource_by_id, ResourceIdentifier
from samcli.lib.sync.sync_flow import SyncFlow, ResourceAPICall
from samcli.lib.providers.exceptions import MissingLocalDefinition

if TYPE_CHECKING:
    from samcli.commands.deploy.deploy_context import DeployContext
    from samcli.commands.build.build_context import BuildContext

LOG = logging.getLogger(__name__)


class StepFunctionsSyncFlow(SyncFlow):
    _state_machine_identifier: str
    _stepfunctions_client: Any
    _definition_uri: Optional[str]
    _stacks: List[Stack]
    _states_definition: Optional[str]

    def __init__(
        self,
        state_machine_identifier: str,
        build_context: "BuildContext",
        deploy_context: "DeployContext",
        physical_id_mapping: Dict[str, str],
        stacks: List[Stack],
    ):
        """
        Parameters
        ----------
        state_machine_identifier : str
            State Machine resource identifier that need to be synced.
        build_context : BuildContext
            BuildContext used for build related parameters
        deploy_context : BuildContext
            DeployContext used for this deploy related parameters
        physical_id_mapping : Dict[str, str]
            Mapping between resource logical identifier and physical identifier
        stacks : List[Stack], optional
            List of stacks containing a root stack and optional nested stacks
        """
        super().__init__(
            build_context,
            deploy_context,
            physical_id_mapping,
            log_name="StepFunctions " + state_machine_identifier,
            stacks=stacks,
        )
        self._state_machine_identifier = state_machine_identifier
        self._stepfunctions_client = None

    def set_up(self) -> None:
        super().set_up()
        self._stepfunctions_client = cast(Session, self._session).client("stepfunctions")

    def gather_resources(self) -> None:
        self._definition_uri = self._get_definition_file(self._state_machine_identifier)
        self._states_definition = self._process_definition_file()

    def _process_definition_file(self) -> Optional[str]:
        if self._definition_uri is None:
            return None
        with open(self._definition_uri, "r", encoding="utf-8") as states_file:
            states_data = states_file.read()
            return states_data

    def _get_definition_file(self, state_machine_identifier: str) -> Optional[str]:
        state_machine_resource = get_resource_by_id(self._stacks, ResourceIdentifier(state_machine_identifier))
        if state_machine_resource is None:
            return None
        properties = state_machine_resource.get("Properties", {})
        definition_file = properties.get("DefinitionUri")
        return cast(Optional[str], definition_file)

    def compare_remote(self) -> bool:
        # Not comparing with remote right now, instead only making update api calls
        # Note: describe state machine has a better rate limit then update state machine
        # So if we face any throttling issues, comparing should be desired
        return False

    def gather_dependencies(self) -> List[SyncFlow]:
        return []

    def _get_resource_api_calls(self) -> List[ResourceAPICall]:
        return []

    def _equality_keys(self):
        return self._state_machine_identifier

    def sync(self) -> None:
        state_machine_arn = self.get_physical_id(self._state_machine_identifier)
        if self._definition_uri is None:
            LOG.error(
                "%sUpdate State Machine fails since no DefinitionUri defined in the template, \
if you are using inline Definition please run sam sync --infra",
                self.log_prefix,
            )
            raise MissingLocalDefinition(ResourceIdentifier(self._state_machine_identifier), "DefinitionUri")
        LOG.debug("%sTrying to update State Machine definition", self.log_prefix)
        response = self._stepfunctions_client.update_state_machine(
            stateMachineArn=state_machine_arn, definition=self._states_definition
        )
        LOG.debug("%sUpdate State Machine: %s", self.log_prefix, response)