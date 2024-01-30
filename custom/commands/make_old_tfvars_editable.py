import logging
import click
from click.decorators import pass_meta_key
from spacemk.spacelift import Spacelift


class CustomSpacelift(Spacelift):
    def get_stack_ids(self) -> list[dict]:
        def get_paginated_results(cursor: str = None):
            operation = """
            query SearchStacks($input: SearchInput!) {
                searchStacks(input: $input) {
                    edges {
                        cursor
                        node {
                            id
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
            """

            variables = {
                "input": {"first": 50, "after": cursor, "orderBy": [{"field": "starred", "direction": "DESC"}]}
            }

            return self._call_api(operation=operation, variables=variables)

        stack_ids = []

        cursor = None
        while True:
            results = get_paginated_results(cursor=cursor)
            stack_ids.extend([edge.get("node.id") for edge in results.get("data.searchStacks.edges")])
            if results.get("data.searchStacks.pageInfo.hasNextPage"):
                cursor = results.get("data.searchStacks.pageInfo.endCursor")
            else:
                break

        return stack_ids

    def get_tfvars_file(self, stack_id: str) -> dict | None:
        operation = """
        query GetEnvironment($stackId: ID!) {
            stack(id: $stackId) {
                id
                runtimeConfig {
                    element {
                        ...configElement
                    }
                }
            }
        }

        fragment configElement on ConfigElement {
            id
            type
            value
            writeOnly
        }
        """

        variables = {"stackId": stack_id}

        response = self._call_api(operation=operation, variables=variables)
        all_mounted_files = [
            item["element"]
            for item in response.get("data.stack.runtimeConfig")
            if item.get("element.type") == "FILE_MOUNT"
        ]

        tf_vars_file = None
        tf_secret_vars_file = None
        for mounted_file in all_mounted_files:
            if mounted_file.get("id").endswith("/tf_vars_with_invalid_name.auto.tfvars"):
                tf_vars_file = mounted_file
            if mounted_file.get("id").endswith("/tf_secret_vars_with_invalid_name.auto.tfvars"):
                tf_secret_vars_file = mounted_file

        if tf_vars_file and tf_secret_vars_file:
            if tf_vars_file.get("writeOnly") == True:
                logging.info(
                    f"Found both tfvars files for stack '{stack_id}' "
                    "and 'tf_vars_with_invalid_name.auto.tfvars' is write-only."
                )
                return tf_vars_file
            else:
                logging.info(
                    f"Found both tfvars files for stack '{stack_id}' "
                    "but 'tf_vars_with_invalid_name.auto.tfvars' is not write-only. Ignoring."
                )
                return None
        else:
            logging.info(f"Did not find both tfvars files for stack '{stack_id}'. Ignoring.")
            return None

    def make_old_tfvars_editable(self, dry_run: bool, limit: int) -> None:
        logging.info("Making old tfvars files editable")

        if dry_run:
            logging.warning("This is a dry run. No changes will be made and the limit will be ignored.")

        counter = 0
        for stack_id in self.get_stack_ids():
            logging.info(f"Processing stack '{stack_id}'")
            tfvars_file = self.get_tfvars_file(stack_id=stack_id)
            if tfvars_file:
                if dry_run:
                    logging.warning(
                        f"Would have updated visibility of '{tfvars_file.get('id')}' for stack '{stack_id}' "
                        "if dry run was not enabled"
                    )
                else:
                    self.update_mounted_file_visibility(mounted_file=tfvars_file, stack_id=stack_id)
                    counter += 1

            if not dry_run and counter >= limit:
                logging.warning(f"Reached the limit of {limit}. Stopping.")
                break

    def update_mounted_file_visibility(self, mounted_file: dict, stack_id: str) -> None:
        logging.warning(f"Updating visibility of '{mounted_file.get('id')}' for stack '{stack_id}' to not write-only")
        self._set_mounted_file_content(
            content=mounted_file.get("value"),
            filename=mounted_file.get("id"),
            stack_id=stack_id,
            write_only=False,
        )


@click.command(help="Make old migrated tfvars files editable.")
@pass_meta_key("config")
@click.option(
    "--dry-run",
    default=True,
    help="Do not make any changes, just print what would be done",
    show_default=True,
    type=bool,
)
@click.option(
    "--limit",
    default=1,
    help="Number of tfvars file to updated at a time",
    show_default=True,
    type=int,
)
def make_old_tfvars_editable(config, dry_run: bool, limit: int):
    spacelift = CustomSpacelift(config.get("spacelift"))
    spacelift.make_old_tfvars_editable(dry_run=dry_run, limit=limit)
