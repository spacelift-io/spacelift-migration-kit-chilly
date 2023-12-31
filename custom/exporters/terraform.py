import logging
import time

from python_on_whales import Container, docker
from spacemk.exporters.terraform import TerraformExporter as BaseTerraformExporter


class TerraformExporter(BaseTerraformExporter):
    def _create_agent_pool(self, organization_id: str) -> str:
        agent_pools_data = self._extract_data_from_api(
            path=f"/organizations/{organization_id}/agent-pools",
            properties=["attributes.name", "id"],
        )

        for agent_pool_data in agent_pools_data:
            if agent_pool_data.get("attributes.name") == "SMK":
                logging.info(f"Reusing existing '{agent_pool_data.get('id')}' agent pool")

                return agent_pool_data.get("id")

        logging.error(f"Could not find an agent pool name 'SMK' for organization '{organization_id}'")

    def _delete_agent_pool(self, id_: str) -> None:
        logging.info(f"Keep existing '{id_}' agent pool")

    def _drop_aws_access_keys(self, data: dict) -> dict:
        purged_workspace_variables = []

        for variable in data.get("workspace_variables"):
            variable_name = variable.get("attributes.key")
            if variable_name in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]:
                logging.debug(f"Dropping '{variable_name}' workspace env var")
            else:
                purged_workspace_variables.append(variable)

        data["workspace_variables"] = purged_workspace_variables

        return data

    def _enrich_workspace_variable_data(self, data: dict) -> dict:
        if self._config.get("skip_sensitive_variable_values_export", False):
            logging.warning("Skipping sensitive data extraction")
            return data

        return BaseTerraformExporter._enrich_workspace_variable_data(self, data)

    def _filter_data(self, data: dict) -> dict:
        data = self._drop_aws_access_keys(data)

        return data

    def _start_agent_container(self, agent_pool_id: str, container_name: str) -> Container:
        if docker.container.exists(container_name):
            logging.info(f"Found a container named '{container_name}'. Using it instead of starting a new one.")
            container = docker.container.inspect(container_name)

            if not container.state.running:
                container.start()

            logging.debug(
                f"Reusing TFC/TFE agent Docker container '{container.id}' from image '{container.config.image}'"
            )

            return container
        else:
            logging.error(f"Could not find a local TFC/TFE agent for organization '{agent_pool_id}'")
