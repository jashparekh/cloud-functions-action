import pytest

from plugin_scripts import deploy
from plugin_scripts.pipeline_exceptions import (
    CloudFunctionDirectoryNonExistent,
    DeployFailed,
)


@pytest.fixture
def debug_mode(monkeypatch):
    return monkeypatch.setenv("debug_mode", "false")


@pytest.fixture
def cloud_function_directory(monkeypatch):
    return monkeypatch.setenv("cloud_function_directory", "schemas/project")


@pytest.fixture
def cloud_function_name(monkeypatch):
    return monkeypatch.setenv("cloud_function_name", "cloud_function_name")


@pytest.fixture
def gcp_project(monkeypatch):
    return monkeypatch.setenv("gcp_project", "gcp_project")


@pytest.fixture
def gcp_region(monkeypatch):
    return monkeypatch.setenv("gcp_region", "gcp_region")


@pytest.fixture
def credentials(monkeypatch):
    return monkeypatch.setenv("credentials", '{"secret": "value"}')


def test__validate_env_variables_missing_cloud_function_directory(
    gcp_project, credentials, gcp_region, cloud_function_name
):
    with pytest.raises(Exception) as exec_info:
        deploy._validate_env_variables()
    assert exec_info.value.args[0] == "Missing `cloud_function_directory` config"


def test__validate_env_variables_missing_cloud_function_name(
    gcp_project, credentials, gcp_region, cloud_function_directory
):
    with pytest.raises(Exception) as exec_info:
        deploy._validate_env_variables()
    assert exec_info.value.args[0] == "Missing `cloud_function_name` config"


def test__validate_env_variables_missing_gcp_project(
    cloud_function_directory, credentials, gcp_region, cloud_function_name
):
    with pytest.raises(Exception) as exec_info:
        deploy._validate_env_variables()
    assert exec_info.value.args[0] == "Missing `gcp_project` config"


def test__validate_env_variables_missing_gcp_region(
    cloud_function_directory, credentials, gcp_project, cloud_function_name
):
    with pytest.raises(Exception) as exec_info:
        deploy._validate_env_variables()
    assert exec_info.value.args[0] == "Missing `gcp_region` config"


def test__validate_env_variables_missing_credentials(
    gcp_project, cloud_function_directory, gcp_region, cloud_function_name
):
    with pytest.raises(Exception) as exec_info:
        deploy._validate_env_variables()
    assert exec_info.value.args[0] == "Missing `credentials` config"


def test__validate_env_variables_all_variables_present(
    gcp_project, cloud_function_directory, credentials, gcp_region, cloud_function_name
):
    deploy._validate_env_variables()
    assert True


def test__validate_if_path_exists_true(mocker, cloud_function_directory):
    os_mock = mocker.patch("plugin_scripts.deploy.os")
    os_mock.path.isdir.return_value = True
    assert deploy._validate_if_path_exists()


def test__validate_if_path_exists_false(mocker, cloud_function_directory):
    os_mock = mocker.patch("plugin_scripts.deploy.os")
    os_mock.path.isdir.return_value = False
    assert not deploy._validate_if_path_exists()


def test__get_bq_credentials(mocker, credentials):
    expected = '{"secret": "value"}'
    mocker.patch(
        "plugin_scripts.deploy.service_account.Credentials.from_service_account_info"
    ).return_value = expected
    response = deploy._get_bq_credentials()
    assert response == expected


def test_main_cloud_function_directory_false(mocker):
    os_mock = mocker.patch("plugin_scripts.deploy.os")
    os_mock.path.isdir.return_value = False
    os_mock.environ = {
        "debug_mode": "false",
        "gcp_project": "gcp_project",
        "cloud_function_directory": "cloud_function_directory",
        "credentials": "credentials",
        "gcp_region": "gcp_region",
        "cloud_function_name": "cloud_function_name",
    }

    with pytest.raises(CloudFunctionDirectoryNonExistent):
        deploy.main()


def test_main_false(mocker):
    os_mock = mocker.patch("plugin_scripts.deploy.os")
    os_mock.path.isdir.return_value = True
    os_mock.environ = {
        "debug_mode": "false",
        "gcp_project": "gcp_project",
        "cloud_function_directory": "cloud_function_directory",
        "credentials": "credentials",
        "gcp_region": "gcp_region",
        "cloud_function_name": "cloud_function_name",
    }

    with pytest.raises(DeployFailed):
        deploy.main()


def test_main_true(mocker):
    os_mock = mocker.patch("plugin_scripts.deploy.os")
    os_mock.path.isdir.return_value = True
    os_mock.environ = {
        "debug_mode": "false",
        "gcp_project": "gcp_project",
        "cloud_function_directory": "cloud_function_directory",
        "credentials": "credentials",
        "gcp_region": "gcp_region",
        "cloud_function_name": "cloud_function_name",
    }

    mocker.patch("plugin_scripts.deploy._deploy")
    deploy.main()
    assert True
