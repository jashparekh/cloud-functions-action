[![Actions Status](https://github.com/jashparekh/cloud-functions-action/workflows/Lint/badge.svg?branch=main)](https://github.com/jashparekh/cloud-functions-action/actions)
[![Actions Status](https://github.com/jashparekh/cloud-functions-action/workflows/Unit%20Tests/badge.svg?branch=main)](https://github.com/jashparekh/cloud-functions-action/actions)
[![Actions Status](https://github.com/jashparekh/cloud-functions-action/workflows/Integration%20Test/badge.svg?branch=main)](https://github.com/jashparekh/cloud-functions-action/actions)
![Version](https://img.shields.io/static/v3.svg?label=Version&message=v1&color=lightgrey&?link=http://left&link=https://github.com/jashparekh/cloud-functions-action/tree/v1)


# Cloud Function Github Action

This Github action can be used to deploy code to Cloud Functions.

### Simple

```yaml
name: "Deploy code to Cloud Function"
on:
  pull_request: {}
  push:
      branches: ["main"]

jobs:
  deploy_schemas:
    runs-on: ubuntu-latest
    name: Deploy code to Cloud Function
    steps:
      # To use this repository's private action,
      # you must check out the repository
      - name: Checkout
        uses: actions/checkout@v2.3.4
      - name: Deploy code to Cloud Function
        uses: jashparekh/cloud-functions-action@v1
        with:
          gcp_project: "gcp-us-project"
          gcp_region: "us-central1"
          cloud_function_name: "function-1"
          cloud_function_directory: "directory/function-code"
          credentials: ${{ secrets.GCP_SERVICE_ACCOUNT }}
```

Inputs are set with `with:`. Setting them as step `env:` variables with the same lower case names
(`gcp_project: ...`) still works; the `with:` input wins when both are set.

## Configuration

### Required

### `gcp_project` (required, string)

The name of the GCP project you want to deploy.

Example: `gcp-us-project`

### `gcp_region` (required, string)

GCP region where the cloud function is hosted.

Example: `us-central1`

### `cloud_function_name` (required, string)

Name of the cloud function in GCP.

Example: `function-1`

### `cloud_function_directory` (required, string)

The directory in your repository where are you storing the code files for cloud function.

Example: `directory/function-code`

### `credentials` (required, string)

Google Service Account with permission to create objects in the specified project. Can be stored as a [repository secret](https://docs.github.com/en/actions/reference/encrypted-secrets)

### `debug_mode` (optional, `true` or `false`, default `false`)

Logs the function definition (without its environment variables) and the upload response.

## What is uploaded

Everything under `cloud_function_directory` except `.git/`, `__pycache__/`, `*.pyc`, `.env`, `.env.*` and
`.DS_Store`. The files are added in sorted order. The deploy fails if nothing is left to upload.

## Contributing

See the [Contributing Guide](CONTRIBUTING.md) for additional information.

To execute tests locally (requires that `docker` and `docker-compose` are installed):

```bash
docker-compose run test
```

## Credits

This Github Action was originally written by [Jash Parekh](https://github.com/jashparekh).
