import fnmatch
import json
import logging
import os
import sys
import zipfile
from pathlib import PurePosixPath
from pprint import pformat
from tempfile import TemporaryFile
from urllib.parse import urlparse

import requests
from google.cloud import storage
from google.oauth2 import service_account
from googleapiclient import discovery

from plugin_scripts.pipeline_exceptions import (
    CloudFunctionDirectoryNonExistent,
    DeployFailed,
)

sys.tracebacklimit = 0

_logger = logging.getLogger("cloud-function")
_logger.setLevel(logging.INFO)
console = logging.StreamHandler(sys.stdout)
_logger.addHandler(console)

# Never uploaded, whatever the directory contains: version control data, local
# environment files (secrets) and Python bytecode.
_EXCLUDED_DIRECTORIES = {".git", "__pycache__"}
_EXCLUDED_FILE_PATTERNS = (".env", ".env.*", "*.pyc", ".DS_Store")

# Matches the 100 MiB limit of the signed upload URL.
_UPLOAD_TIMEOUT_SECONDS = 300

# Redacted from debug output: they usually hold secrets.
_REDACTED_FUNCTION_FIELDS = ("environmentVariables", "buildEnvironmentVariables")

_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"", "false", "0", "no", "off"}


def _get_input(name: str) -> str:
    """Value of an action input.

    `with:` inputs reach the container as `INPUT_<NAME>`; before 2.0.0 the
    values were set with `env:` using the bare lower case name, which keeps
    working. The input wins when both are set.
    """
    value = os.environ.get(f"INPUT_{name.upper()}")
    if value is None or value == "":
        value = os.environ.get(name)
    return value or ""


def _parse_bool(value: str, name: str = "debug_mode") -> bool:
    lowered = value.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ValueError(f"`{name}` must be `true` or `false`, got `{value}`")


def _is_excluded(relative_path: str) -> bool:
    path = PurePosixPath(relative_path)
    if any(part in _EXCLUDED_DIRECTORIES for part in path.parts):
        return True
    return any(fnmatch.fnmatchcase(path.name, p) for p in _EXCLUDED_FILE_PATTERNS)


def _zip_directory(handler: zipfile.ZipFile) -> int:
    """Add the function directory to the archive, returns the number of files."""
    cloud_function_directory = _get_input("cloud_function_directory")
    file_count = 0

    for root, dirs, files in os.walk(cloud_function_directory):
        # Sorted so the archive is the same for the same input
        dirs[:] = sorted(d for d in dirs if d not in _EXCLUDED_DIRECTORIES)
        for file in sorted(files):
            full_path = os.path.join(root, file)
            arcname = os.path.relpath(full_path, cloud_function_directory)
            if _is_excluded(arcname.replace(os.sep, "/")):
                continue
            handler.write(full_path, arcname)
            file_count += 1
    return file_count


def _get_credentials():
    credentials = _get_input("credentials")
    try:
        svc = json.loads(credentials)
        return service_account.Credentials.from_service_account_info(svc)
    except (ValueError, TypeError) as e:
        # Do not echo the value: it is a secret
        raise ValueError(
            "`credentials` is not a valid service account key JSON "
            f"({type(e).__name__})"
        ) from None


def _upload_source_code_using_archive_url(archive_url: str, data):
    object_path = urlparse(archive_url)
    bucket_name = object_path.netloc
    blob_name = object_path.path.lstrip("/")

    storage_client = storage.Client(credentials=_get_credentials())
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data.read())
    _logger.info(f"Source code object {blob_name} uploaded to bucket {bucket_name}. \n")


def _upload_source_code_using_upload_url(upload_url: str, debug_mode: bool, data):
    # Prepare Header and data for PUT request
    # https://cloud.google.com/functions/docs/reference/rest/v1/projects.locations.functions/generateUploadUrl
    headers = {
        "content-type": "application/zip",
        "x-goog-content-length-range": "0,104857600",
    }
    response = requests.put(
        upload_url, headers=headers, data=data, timeout=_UPLOAD_TIMEOUT_SECONDS
    )
    _logger.info(f"HTTP Status Code for uploading data: {response.status_code} \n")

    if not response.ok:
        raise DeployFailed(
            f"Uploading the source code failed with HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    if debug_mode:
        _logger.info(f"Response body: {response.text[:500]} \n")


def _validate_env_variables():
    gcp_project = _get_input("gcp_project")
    gcp_region = _get_input("gcp_region")
    cloud_function_name = _get_input("cloud_function_name")
    cloud_function_directory = _get_input("cloud_function_directory")
    credentials = _get_input("credentials")

    if not gcp_project:
        raise Exception("Missing `gcp_project` config")

    if not gcp_region:
        raise Exception("Missing `gcp_region` config")

    if not cloud_function_name:
        raise Exception("Missing `cloud_function_name` config")

    if not cloud_function_directory:
        raise Exception("Missing `cloud_function_directory` config")

    if not credentials:
        raise Exception("Missing `credentials` config")


def _validate_if_path_exists():
    return os.path.isdir(_get_input("cloud_function_directory"))


def _redacted(function: dict) -> dict:
    return {
        k: ("<redacted>" if k in _REDACTED_FUNCTION_FIELDS else v)
        for k, v in function.items()
    }


def _error_message(e: Exception) -> str:
    # googleapiclient.errors.HttpError has a readable str(), others fall back to
    # the class name so that the message is never empty.
    return str(e).strip() or type(e).__name__


def _deploy(debug_mode: bool):
    gcp_project = _get_input("gcp_project")
    gcp_region = _get_input("gcp_region")
    cloud_function_name = _get_input("cloud_function_name")

    parent = f"projects/{gcp_project}/locations/{gcp_region}"
    function_path = f"{parent}/functions/{cloud_function_name}"

    try:
        service = discovery.build(
            "cloudfunctions", "v1", credentials=_get_credentials()
        )
        cloud_functions = service.projects().locations().functions()

        # check if cloud function exists, if it does not this raises an HttpError
        function = cloud_functions.get(name=function_path).execute()

        if debug_mode:
            _logger.info(f"Function Definition: {pformat(_redacted(function))} \n")

        with TemporaryFile() as data:
            file_handler = zipfile.ZipFile(data, mode="w")
            file_count = _zip_directory(file_handler)
            file_handler.close()
            if file_count == 0:
                raise DeployFailed(
                    "No files to upload: the cloud function directory is empty"
                )
            data.seek(0)
            _logger.info(f"Zipped {file_count} files. \n")

            if "sourceArchiveUrl" in function:
                archive_url = function["sourceArchiveUrl"]
                _upload_source_code_using_archive_url(archive_url, data)
            else:
                # https://cloud.google.com/functions/docs/reference/rest/v1/projects.locations.functions/generateUploadUrl
                upload_url = cloud_functions.generateUploadUrl(
                    parent=parent, body={}
                ).execute()["uploadUrl"]
                _upload_source_code_using_upload_url(upload_url, debug_mode, data)
                function["sourceUploadUrl"] = upload_url

        response = cloud_functions.patch(name=function_path, body=function).execute()
        _logger.info("Successfully patched Cloud Function. \n")
        _logger.info(f"Operation Name: {response['name']} \n")

        if debug_mode:
            _logger.info(f"Response: {pformat(response)}")
    except DeployFailed:
        raise
    except Exception as e:
        raise DeployFailed(f"Deploying {function_path} failed: {_error_message(e)}")


def main():
    debug_mode = _parse_bool(_get_input("debug_mode"))

    try:
        _validate_env_variables()
        if not _validate_if_path_exists():
            raise CloudFunctionDirectoryNonExistent(
                f"`cloud_function_directory` `{_get_input('cloud_function_directory')}`"
                " does not exist or is not a directory"
            )
        _deploy(debug_mode)
    except Exception as e:
        # GitHub shows this as an error annotation on the run
        _logger.error(f"::error::{_error_message(e).splitlines()[0]}")
        raise
