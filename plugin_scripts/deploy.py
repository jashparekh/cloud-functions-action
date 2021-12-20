import ast
import json
import logging
import os
import sys
import zipfile
from pprint import pformat
from tempfile import TemporaryFile
from urllib.parse import urlparse

import requests
from google.cloud import storage
from google.oauth2 import service_account
from googleapiclient import discovery
from requests import Response

from plugin_scripts.pipeline_exceptions import (
    CloudFunctionDirectoryNonExistent,
    DeployFailed,
)

sys.tracebacklimit = 0

_logger = logging.getLogger("cloud-function")
_logger.setLevel(logging.INFO)
console = logging.StreamHandler(sys.stdout)
_logger.addHandler(console)


def _zip_directory(handler: zipfile.ZipFile):
    cloud_function_directory = os.environ.get("cloud_function_directory")

    for root, dirs, files in os.walk(cloud_function_directory):  # type: ignore # noqa: B007
        for file in files:
            handler.write(
                os.path.join(root, file),  # type: ignore
                os.path.relpath(
                    os.path.join(root, file), os.path.join(cloud_function_directory, ".")  # type: ignore
                ),
            )


def _get_bq_credentials():
    credentials = os.environ.get("credentials")
    svc = json.loads(credentials)
    return service_account.Credentials.from_service_account_info(svc)


def _upload_source_code_using_archive_url(archive_url: str, data):
    object_path = urlparse(archive_url)
    bucket_name = object_path.netloc
    blob_name = object_path.path.lstrip("/")

    storage_client = storage.Client(credentials=_get_bq_credentials())
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
    response: Response = requests.put(upload_url, headers=headers, data=data)
    _logger.info(f"HTTP Status Code for uploading data: {response.status_code} \n")

    if debug_mode:
        _logger.info(f"Response body: {pformat(response.json)} \n")


def _validate_env_variables():
    gcp_project = os.environ.get("gcp_project")
    gcp_region = os.environ.get("gcp_region")
    cloud_function_name = os.environ.get("cloud_function_name")
    cloud_function_directory = os.environ.get("cloud_function_directory")
    credentials = os.environ.get("credentials")

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
    cloud_function_directory = os.environ.get("cloud_function_directory")
    return os.path.isdir(cloud_function_directory)


def _handle_exception(e, debug_mode):
    if debug_mode:
        _logger.info(f"HTTP Status Code for patching Function: {str(e)} \n")


def _deploy(debug_mode: bool):
    deploy_failed = False

    try:
        gcp_project = os.environ.get("gcp_project")
        gcp_region = os.environ.get("gcp_region")
        cloud_function_name = os.environ.get("cloud_function_name")

        parent = f"projects/{gcp_project}/locations/{gcp_region}"
        function_path = f"projects/{gcp_project}/locations/{gcp_region}/functions/{cloud_function_name}"

        service = discovery.build(
            "cloudfunctions", "v1", credentials=_get_bq_credentials()
        )
        cloud_functions = service.projects().locations().functions()

        # check if cloud function exists, if it exists execution continues as is otherwise it will raise an exception
        function = cloud_functions.get(name=function_path).execute()

        if debug_mode:
            _logger.info(f"Function Definition: {pformat(function)} \n")

        with TemporaryFile() as data:
            file_handler = zipfile.ZipFile(data, mode="w")
            _zip_directory(file_handler)
            file_handler.close()
            data.seek(0)

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

        try:
            response = cloud_functions.patch(
                name=function_path, body=function
            ).execute()
            _logger.info("Successfully patched Cloud Function. \n")
            _logger.info(f"Operation Name: {response['name']} \n")

            if debug_mode:
                _logger.info(f"Response: {pformat(response)}")
        except Exception as e:
            deploy_failed = True
            _handle_exception(e, debug_mode)
    except Exception as e:
        deploy_failed = True
        _handle_exception(e, debug_mode)

    if deploy_failed:
        raise DeployFailed


def main():
    env_debug_mode: str = os.environ.get("debug_mode", "true").title()
    debug_mode = ast.literal_eval(env_debug_mode)

    _validate_env_variables()
    if _validate_if_path_exists():
        _deploy(debug_mode)
    else:
        raise CloudFunctionDirectoryNonExistent
