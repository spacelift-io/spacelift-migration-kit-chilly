# Customizations

Store all customizations in this folder.

See the main [README file](../README.md) for general information.

## Export Sensitive Variables

Perform the following actions **in each of the TFE organization to export from**:

1. Create am agent pool named `SMK`.
2. Start an agent using an **agent token** for the `SMK` pool for the organization. Make sure to name it aftert he TFE organization:

```shell
docker run -e TFC_ADDRESS=https://<DOMAIN NAME> -e TFC_AGENT_NAME=SMK-Agent -e TFC_AGENT_TOKEN=<AGENT TOKEN> --name=smk-tfc-agent-<ORGANIZATION NAME> --pull=always jmfontaine/tfc-agent:smk-latest
```

Note: Once started the agent can be ignored, for the most part. It will be stopped and started as needed. It can be removed once the export has completed.

3. [Export data from TFE, including sensitive variables](../README.md#export).
4. [Generate the Terraform source code to manage Spacelift resources](../README.md#generate).
5. [Publish the generated Terraform code to a git repository](../README.md#publish).
6. [Create and trigger an administrative stack](../README.md#deploy).
7. Run the `spacemk set-sensitive-env-vars` command to set the value for the sensitive environment variables.

## Upload Terraform State Files

Once the stacks have been created, set the values for the `upload_state_files` section of the `config.yml` file and run the `spacemk upload-state-files` command to upload the Terraform state files to AWS S3.

Also, make sure to [provide AWS credentials to the AWS SDK](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html).

## Generate Code for Jenkins Stacks

Once the data has been exported, run the `spacemk generate --stack-type=jenkins` command to generate Terraform code for the stacks without VCS configuration. Then, push that code to the GitHub repository as usual.

Check `spacemk generate --help` for all `--stack-type` option values.

## Ignore Stack Branch Changes

Once the data has been exported, run the `spacemk generate --ignore-branch-changes` command to generate Terraform code which ignores changes to the `branch` argument for stacks.

## Infracost Integration

Once the administrative stack has run and Spacelift resources have been created, manually set the value for the `INFRACOST_API_KEY` environment variable in the `Infracost` context in Spacelift.

## Transform Terraform Variables Into Environment Variables

TFE also exposes Terraform variables as regular environment variables which results in some workspaces working fine in TFE despite incorrectly configured variables but Spacelift being stricter, the stack might complained about missing environment variables after the migration.

You can list such variables in the `generator/tf_stack_variables_to_transform_env_var` section of the configuration file:

```yaml
generator:
  tf_stack_variables_to_transform_env_var:
    - FOO
    - BAR
```

The type for the listed variable will be transformed on the fly before generating the `main.tf` file. Please note that the original type will be shown in the `data.json` file.
