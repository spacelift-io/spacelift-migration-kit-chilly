import logging
import time

from benedict import benedict
from python_on_whales import docker
from python_on_whales.exceptions import NoSuchContainer
from spacemk import is_command_available
from spacemk.exporters.terraform import TerraformExporter as BaseTerraformExporter


class TerraformTestExporter(BaseTerraformExporter):
    def _enrich_workspace_variable_data(self, data: dict) -> dict:  # noqa: PLR0915
        def find_workspace(data: dict, workspace_id: str) -> dict:
            for workspace in data.get("workspaces"):
                if workspace.get("id") == workspace_id:
                    return workspace

            logging.warning(f"Could not find workspace '{workspace_id}'")

            return None

        def find_variable(data: dict, variable_id: str) -> dict:
            for variable in data.get("workspace_variables"):
                if variable.get("id") == variable_id:
                    return variable

            logging.warning(f"Could not find variable '{variable_id}'")

            return None

        if not is_command_available(["docker", "ps"], execute=True):
            logging.warning("Docker is not installed. Skipping enriching workspace variables data.")
            return data

        logging.info("Start enriching workspace variables data")

        # List organizations, workspaces and associated variables
        organizations = benedict()
        for variable in data.get("workspace_variables"):
            if variable.get("attributes.sensitive") is False:
                continue

            workspace_id = variable.get("relationships.workspace.data.id")
            organization_id = find_workspace(data, workspace_id).get("relationships.organization.data.id")

            if organization_id not in organizations:
                organizations[organization_id] = benedict()

            if workspace_id not in organizations[organization_id]:
                organizations[organization_id][workspace_id] = benedict()

            organizations[organization_id][workspace_id][variable.get("id")] = variable.get("attributes.key")

        if len(organizations) == 0 or len(organizations.keys()) == 0:
            return data

        for organization_id, workspaces in organizations.items():
            logging.info(f"Start local TFC/TFE agent for organization '{organization_id}'")

            agent_pool_request_data = {
                "data": {
                    "attributes": {
                        "name": "SMK",
                        "organization-scoped": True,
                    },
                    "type": "agent-pools",
                }
            }
            agent_pool_data = self._extract_data_from_api(
                method="POST",
                path=f"/organizations/{organization_id}/agent-pools",
                properties=["id"],
                request_data=agent_pool_request_data,
            )
            agent_pool_id = agent_pool_data[0].get("id")
            logging.info(f"Created '{agent_pool_id}' agent pool")

            agent_token_request_data = {
                "data": {
                    "attributes": {
                        "description": "SMK",
                    },
                    "type": "authentication-tokens",
                }
            }
            agent_token_data = self._extract_data_from_api(
                method="POST",
                path=f"/agent-pools/{agent_pool_id}/authentication-tokens",
                properties=["attributes.token", "id"],
                request_data=agent_token_request_data,
            )
            tfc_agent_token_id = agent_token_data[0].get("id")
            tfc_agent_token = agent_token_data[0].get("attributes.token")
            logging.info(f"Created '{tfc_agent_token_id}' agent token")

            try:
                with docker.run(
                    "jmfontaine/tfc-agent:smk-1",
                    detach=True,
                    envs={
                        "TFC_AGENT_NAME": "SMK-Agent",
                        "TFC_AGENT_TOKEN": tfc_agent_token,
                    },
                    name=f"smk-tfc-agent-{organization_id}",
                    remove=False, # Should be set to True but it might help to set it to False while troubleshooting
                ) as tfc_agent_container_id:
                    logging.debug(f"Running TFC Agent Docker container '{tfc_agent_container_id}'")

                    for workspace_id, workspace_variables in workspaces.items():
                        current_configuration_version_id = find_workspace(data, workspace_id).get(
                            "relationships.current-configuration-version.data.id"
                        )
                        if current_configuration_version_id is None:
                            logging.warning(
                                f"Workspace '{organization_id}/{workspace_id}' has no current configuration. Ignoring."
                            )
                            continue

                        logging.info(f"Backing up the '{organization_id}/{workspace_id}' workspace execution mode")
                        workspace_data_backup = self._extract_data_from_api(
                            path=f"/workspaces/{workspace_id}",
                            properties=[
                                "attributes.execution-mode",
                                "attributes.setting-overwrites",
                                "relationships.agent-pool",
                            ],
                        )[
                            0
                        ]  # KLUDGE: There should be a way to pull single item from the API instead of a list of items

                        logging.info(f"Updating the '{organization_id}/{workspace_id}' workspace to use the TFC Agent")
                        self._extract_data_from_api(
                            method="PATCH",
                            path=f"/workspaces/{workspace_id}",
                            request_data={
                                "data": {
                                    "attributes": {
                                        "agent-pool-id": agent_pool_id,
                                        "execution-mode": "agent",
                                        "setting-overwrites": {"execution-mode": True, "agent-pool": True},
                                    },
                                    "type": "workspaces",
                                }
                            },
                        )

                        logging.info(f"Trigger a plan for the '{organization_id}/{workspace_id}' workspace")
                        run_data = self._extract_data_from_api(
                            method="POST",
                            path="/runs",
                            properties=["relationships.plan.data.id"],
                            request_data={
                                "data": {
                                    "attributes": {
                                        "allow-empty-apply": False,
                                        "plan-only": True,
                                        "refresh": False,  # No need to waste time refreshing the state
                                    },
                                    "relationships": {
                                        "workspace": {"data": {"id": workspace_id, "type": "workspaces"}},
                                    },
                                    "type": "runs",
                                }
                            },
                        )[
                            0
                        ]  # KLUDGE: There should be a way to pull single item from the API instead of a list of items

                        logging.info(f"Restoring the '{organization_id}/{workspace_id}' workspace execution mode")
                        self._extract_data_from_api(
                            method="PATCH",
                            path=f"/workspaces/{workspace_id}",
                            request_data={
                                "data": {
                                    "attributes": {
                                        "execution-mode": workspace_data_backup.get("attributes.execution-mode"),
                                        "setting-overwrites": workspace_data_backup.get(
                                            "attributes.setting-overwrites"
                                        ),
                                    },
                                    "relationships": {
                                        "agent-pool": workspace_data_backup.get("relationships.agent-pool"),
                                    },
                                    "type": "workspaces",
                                }
                            },
                        )

                        logging.info("Retrieve the output for the plan")
                        plan_id = run_data.get("relationships.plan.data.id")
                        plan_data = self._extract_data_from_api(
                            path=f"/plans/{plan_id}", properties=["attributes.log-read-url"]
                        )[
                            0
                        ]  # KLUDGE: There should be a way to pull single item from the API instead of a list of items
                        # KLUDGE: Looks like the logs are not immediately available.
                        # If the logs are not available the response will have a 200 HTTP status but an empty body.
                        # Ideally, we should check for this, wait, and try again until it succeeds.
                        time.sleep(30)
                        logs_data = self._download_text_file(url=plan_data.get("attributes.log-read-url"))

                        logging.info("Extract the env var values from the plan output")
                        for line in logs_data.split("\n"):
                            for workspace_variable_id, workspace_variable_name in workspace_variables.items():
                                prefix = f"{workspace_variable_name}="
                                if line.startswith(prefix):
                                    value = line.removeprefix(prefix)
                                    masked_value = "*" * len(value)

                                    logging.debug(
                                        f"Found sensitive env var: '{workspace_variable_name}={masked_value}'"
                                    )

                                    variable = find_variable(data, workspace_variable_id)
                                    variable["attributes.value"] = value

                                # KLUDGE: Ideally this should be retrieved independently for more clarity,
                                # and only if needed.
                                if line.startswith("ATLAS_CONFIGURATION_VERSION_GITHUB_BRANCH="):
                                    branch_name = line.removeprefix("ATLAS_CONFIGURATION_VERSION_GITHUB_BRANCH=")
                                    workspace = find_workspace(data, workspace_id)
                                    if workspace and not workspace.get("attributes.vcs-repo.branch"):
                                        workspace["attributes.vcs-repo.branch"] = branch_name

            except NoSuchContainer as e:
                logging.warning(
                    f"Could not find TFC Agent Docker container '{tfc_agent_container_id}' to stop it. Ignoring."
                )
                logging.debug(e)

                logging.info(f"Stop local TFC/TFE agent for organization '{organization_id}'")

            logging.info(f"Deleting '{agent_pool_id}' agent pool")
            self._extract_data_from_api(
                method="DELETE",
                path=f"/agent-pools/{agent_pool_id}",
            )

        logging.info("Stop enriching workspace variables data")

        return data

    def _enrich_data(self, data: dict) -> dict:
        logging.info("Start enriching data")

        # Focus on enriching the workspace variables only
        data = self._enrich_workspace_variable_data(data)

        logging.info("Stop enriching data")

        return data

    def _extract_data(self) -> dict:
        data = benedict()

        # Harcode test data instead of pulling it from the API
        # If the Docker container crashes, you might need to manually delete the "SMK" agent pool for the organization

        data["organizations"] = [
            {"attributes": {"email": "admin@example.com", "name": "smk-organization-1"}, "id": "smk-organization-1"}
        ]

        data["workspaces"] = [
            {
                "attributes": {
                    "auto-apply": False,
                    "description": "SMK Workspace #1",
                    "name": "smk-workspace-1",
                    "resource-count": 3,
                    "terraform-version": "latest",
                    "vcs-repo": {"branch": "", "identifier": "jfinck42/iac-tests", "service-provider": "github"},
                    "working-directory": "terraform/",
                },
                "id": "ws-kJpdEf9zNHR4PCqa",
                "relationships": {
                    "current-configuration-version": {"data": {"id": "cv-hB4Z3i5Wsx6Cf1iY"}},
                    "current-state-version": {"data": {"id": "sv-hvLn5ncranVfgPMC"}},
                    "organization": {"data": {"id": "smk-organization-1"}},
                    "project": {"data": {"id": "prj-XGjmPS8av1UcZQJW"}},
                },
            }
        ]

        data["workspace_variables"] = [
            {
                "attributes": {
                    "category": "env",
                    "description": "Example sensitive environment variable",
                    "hcl": False,
                    "key": "EXAMPLE_SENSITIVE_ENV_VAR",
                    "sensitive": True,
                    "value": None,
                },
                "id": "var-eDjQK8yKxrkXzjGi",
                "relationships": {"workspace": {"data": {"id": "ws-kJpdEf9zNHR4PCqa"}}},
            }
        ]

        return data
