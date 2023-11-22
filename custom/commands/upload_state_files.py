import json
import logging
import os

import boto3
import click

from benedict import benedict
from botocore.exceptions import ClientError
from pathlib import Path
from spacemk import get_tmp_folder, get_tmp_subfolder


def _find_stack(data: dict, workspace_id: str) -> dict | None:
    for stack in data.get("stacks"):
        if stack.get("_source_id") == workspace_id:
            return stack

    return None


def _list_state_files(data: dict) -> list[dict]:
    state_files = []

    folder = get_tmp_subfolder("state-files")

    for organization_folder in folder.iterdir():
        if not organization_folder.is_dir():
            logging.warning(f"'{organization_folder}' is not a folder. Ignoring.")
            continue

        for state_file in organization_folder.iterdir():
            if not state_file.is_file():
                logging.warning(f"'{state_file}' is not a file. Ignoring.")
                continue

            workspace_id = state_file.stem
            stack = _find_stack(data=data, workspace_id=workspace_id)
            if not stack:
                logging.warning(f"Could not find stack for workspace id '{workspace_id}'. Ignoring.")

            state_files.append(
                {
                    "object_name": f"{organization_folder.name}/{stack.name}/{stack.name}.tfstate",
                    "path": state_file,
                }
            )

    return state_files


def _load_data_from_file() -> dict:
    path = Path(get_tmp_folder(), "data.json")

    with path.open("r", encoding="utf-8") as fp:
        return benedict(json.load(fp))


def _upload_file(bucket: str, file_path: str, object_name: str) -> None:
    client = boto3.client("s3")
    try:
        client.upload_file(file_path, bucket, object_name)
    except ClientError as e:
        logging.error(e)


@click.command(help="Upload Terraform state files to an AWS S3 bucket.")
@click.decorators.pass_meta_key("config")
def upload_state_files(config):
    data = _load_data_from_file()

    for file in _list_state_files(data=data):
        _upload_file(
            bucket=config.get("upload_state_files.bucket"), file_path=file["path"], object_name=file["object_name"]
        )
