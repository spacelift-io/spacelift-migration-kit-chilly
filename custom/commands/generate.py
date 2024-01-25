import json
import logging
import click

from spacemk.generator import Generator


class CustomGenerator(Generator):
    def __init__(self, ignore_branch_changes: bool = False, stack_type: str = "all"):
        self._ignore_branch_changes = ignore_branch_changes
        self._stack_type = stack_type
        Generator.__init__(self)

    def _process_data(self, data: dict) -> dict:
        logging.info("Start data processing")
        logging.info(f"Requested stack type: {self._stack_type}")

        stacks_to_keep = []
        for stack in data.get("stacks"):
            if stack.get("vcs.repository"):
                if self._stack_type == "jenkins":
                    logging.debug(
                        f"Ignoring stack '{stack.get('_relationships.space.name')}/{stack.get('name')}' "
                        "because it has a VCS configuration"
                    )
                else:
                    stacks_to_keep.append(stack)
            else:
                if self._stack_type in ["all", "jenkins"]:
                    logging.debug(
                        f"Setting default values for '{stack.get('_relationships.space.name')}/{stack.get('name')}' "
                        "with no VCS configuration"
                    )
                    stack.vcs.branch = "master"
                    stack.vcs.namespace = "CloudAutomation"
                    stack.vcs.project_root = "terraform/"
                    stack.vcs.provider = "github_custom"
                    stack.vcs.repository = "dummy-spacectl-repo"
                    stacks_to_keep.append(stack)
                else:
                    logging.debug(
                        f"Ignoring stack '{stack.get('_relationships.space.name')}/{stack.get('name')}' "
                        "because it has no VCS configuration"
                    )
        data["stacks"] = stacks_to_keep

        stack_variables_to_keep = []
        for stack_variable in data.get("stack_variables"):
            for stack_to_keep in stacks_to_keep:
                if stack_variable.get("_relationships.stack._source_id") == stack_to_keep.get("_source_id"):
                    if not stack_variable.get("_relationships.stack.vcs.repository"):
                        if self._stack_type in ["all", "jenkins"]:
                            logging.debug(
                                "Setting default values for the stack for "
                                f"'{stack_variable.get('_relationships.space.name')}/"
                                f"{stack_variable.get('_relationships.stack.name')}/{stack_variable.get('name')}' "
                                "because it has no VCS configuration"
                            )
                            stack_variable["_relationships"]["stack"]["vcs"] = {
                                "branch": "master",
                                "namespace": "CloudAutomation",
                                "project_root": "terraform/",
                                "provider": "github_custom",
                                "repository": "dummy-spacectl-repo",
                            }

                    stack_variables_to_keep.append(stack_variable)
                    break

        data["stack_variables"] = stack_variables_to_keep

        logging.info("Stop data processing")

        return data


@click.command(help="Generate Terraform code to manage Spacelift entities.")
@click.option(
    "-s",
    "--stack-type",
    default="all",
    help="Type of stacks to generate",
    type=click.Choice(["all", "jenkins", "regular"], case_sensitive=False),
)
@click.option(
    "--ignore-branch-changes",
    default=False,
    help="Adds a lifecycle argument to ignore chnages to the stack branches",
    is_flag=True,
    type=bool,
)
def generate(ignore_branch_changes: bool, stack_type: str):
    generator = CustomGenerator(ignore_branch_changes=ignore_branch_changes, stack_type=stack_type)
    generator.generate(extra_vars={"ignore_branch_changes": ignore_branch_changes})
