import logging

from python_on_whales import Container, docker
from spacemk.exporters.terraform import TerraformExporter as BaseTerraformExporter


class TerraformExporter(BaseTerraformExporter):
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
        logging.warning("Skipping sensitive data extraction for the time being")

        return data

    def _filter_data(self, data: dict) -> dict:
        data = self._drop_aws_access_keys(data)

        return data

    def _start_agent_container(self, container_name: str, token: str) -> Container:
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
            return BaseTerraformExporter._start_agent_container(self, container_name=container_name, token=token)
