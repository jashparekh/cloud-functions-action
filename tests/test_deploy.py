import io
import zipfile

import pytest

from plugin_scripts import deploy
from plugin_scripts.pipeline_exceptions import (
    CloudFunctionDirectoryNonExistent,
    DeployFailed,
)
from tests.fakes import FakeApi, FakePut, anonymous_credentials, response

FUNCTION = {"name": "projects/p/locations/r/functions/f", "runtime": "python311"}


@pytest.fixture
def function_dir(tmp_path):
    root = tmp_path / "fn"
    (root / "sub").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "__pycache__").mkdir()
    (root / "main.py").write_text("def f(request): return 'ok'")
    (root / "requirements.txt").write_text("requests")
    (root / "sub" / "helper.py").write_text("x = 1")
    (root / "sub" / "helper.pyc").write_bytes(b"\x00")
    (root / ".env").write_text("SECRET=1")
    (root / ".env.local").write_text("SECRET=2")
    (root / ".git" / "config").write_text("[core]")
    (root / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\x00")
    return root


@pytest.fixture
def env(monkeypatch, function_dir):
    for key in list(__import__("os").environ):
        if key.startswith("INPUT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("gcp_project", "p")
    monkeypatch.setenv("gcp_region", "r")
    monkeypatch.setenv("cloud_function_name", "f")
    monkeypatch.setenv("cloud_function_directory", str(function_dir))
    monkeypatch.setenv("credentials", '{"type": "service_account"}')
    monkeypatch.delenv("debug_mode", raising=False)
    return monkeypatch


@pytest.fixture
def api(mocker):
    def install(responses):
        fake = FakeApi(responses)
        mocker.patch.object(deploy.discovery, "build", fake.build)
        mocker.patch.object(deploy, "_get_credentials", anonymous_credentials)
        return fake

    return install


def test_input_names_are_read_from_with_inputs_and_legacy_env(monkeypatch):
    monkeypatch.delenv("INPUT_GCP_PROJECT", raising=False)
    monkeypatch.setenv("gcp_project", "legacy")
    assert deploy._get_input("gcp_project") == "legacy"
    monkeypatch.setenv("INPUT_GCP_PROJECT", "from-with")
    assert deploy._get_input("gcp_project") == "from-with"
    monkeypatch.setenv("INPUT_GCP_PROJECT", "")
    assert deploy._get_input("gcp_project") == "legacy"


@pytest.mark.parametrize(
    "missing",
    [
        "gcp_project",
        "gcp_region",
        "cloud_function_name",
        "cloud_function_directory",
        "credentials",
    ],
)
def test_validate_env_variables_missing(env, missing):
    env.delenv(missing)
    with pytest.raises(Exception, match=f"Missing `{missing}` config"):
        deploy._validate_env_variables()


def test_validate_env_variables_with_inputs(env):
    for name in (
        "gcp_project",
        "gcp_region",
        "cloud_function_name",
        "cloud_function_directory",
        "credentials",
    ):
        env.setenv(f"INPUT_{name.upper()}", "x")
        env.delenv(name)
    deploy._validate_env_variables()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("", False),
        ("false", False),
        ("FALSE", False),
        ("0", False),
    ],
)
def test_parse_bool(value, expected):
    assert deploy._parse_bool(value) is expected


def test_parse_bool_rejects_garbage():
    with pytest.raises(ValueError, match="debug_mode"):
        deploy._parse_bool("maybe")


def test_zip_excludes_secrets_and_vcs_and_is_sorted(env):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        count = deploy._zip_directory(z)
    names = zipfile.ZipFile(buffer).namelist()
    assert names == ["main.py", "requirements.txt", "sub/helper.py"]
    assert count == 3


def test_get_credentials_invalid_json_does_not_leak_value(env):
    env.setenv("credentials", "super-secret-not-json")
    with pytest.raises(ValueError) as exc:
        deploy._get_credentials()
    assert "super-secret" not in str(exc.value)


def test_get_credentials_valid(mocker, env):
    expected = object()
    mocker.patch(
        "plugin_scripts.deploy.service_account.Credentials.from_service_account_info",
        return_value=expected,
    )
    assert deploy._get_credentials() is expected


def test_main_directory_missing(env, tmp_path):
    env.setenv("cloud_function_directory", str(tmp_path / "nope"))
    with pytest.raises(CloudFunctionDirectoryNonExistent, match="does not exist"):
        deploy.main()


def test_main_deploy_via_upload_url(env, api, mocker, caplog):
    fake = api(
        [
            response(FUNCTION),
            response({"uploadUrl": "https://storage.example/upload"}),
            response({"name": "operations/op1"}),
        ]
    )
    put = FakePut(200)
    mocker.patch.object(deploy.requests, "put", put)
    deploy.main()
    out = caplog.text
    assert "Operation Name: operations/op1" in out
    assert put.calls[0][0] == "https://storage.example/upload"
    assert put.calls[0][1]["timeout"] == deploy._UPLOAD_TIMEOUT_SECONDS
    assert fake.http is not None


def test_main_deploy_via_archive_url(env, api, mocker):
    api(
        [
            response({**FUNCTION, "sourceArchiveUrl": "gs://bucket/dir/src.zip"}),
            response({"name": "operations/op2"}),
        ]
    )
    storage = mocker.patch.object(deploy.storage, "Client")
    deploy.main()
    bucket = storage.return_value.bucket
    bucket.assert_called_once_with("bucket")
    bucket.return_value.blob.assert_called_once_with("dir/src.zip")
    bucket.return_value.blob.return_value.upload_from_string.assert_called_once()


def test_main_function_not_found_has_message(env, api, caplog):
    api([response({"error": {"message": "Function f does not exist"}}, status=404)])
    with pytest.raises(DeployFailed, match="projects/p/locations/r/functions/f"):
        deploy.main()
    assert "::error::Deploying projects/p/locations/r/functions/f failed" in caplog.text


def test_main_upload_failure_is_fatal_and_does_not_patch(env, api, mocker):
    fake = api(
        [
            response(FUNCTION),
            response({"uploadUrl": "https://storage.example/upload"}),
        ]
    )
    mocker.patch.object(deploy.requests, "put", FakePut(403, "denied"))
    with pytest.raises(DeployFailed, match="HTTP 403: denied"):
        deploy.main()
    assert fake.http is not None


def test_main_empty_directory_fails(env, api, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / ".env").write_text("x")
    env.setenv("cloud_function_directory", str(empty))
    api([response(FUNCTION)])
    with pytest.raises(DeployFailed, match="No files to upload"):
        deploy.main()


def test_debug_mode_redacts_environment_variables(env, api, mocker, caplog):
    env.setenv("debug_mode", "true")
    api(
        [
            response({**FUNCTION, "environmentVariables": {"SETTING": "not-for-logs"}}),
            response({"uploadUrl": "https://storage.example/upload"}),
            response({"name": "operations/op3"}),
        ]
    )
    mocker.patch.object(deploy.requests, "put", FakePut(200, "<ok/>"))
    deploy.main()
    out = caplog.text
    assert "not-for-logs" not in out
    assert "<redacted>" in out
    assert "Response body: <ok/>" in out


def test_invalid_debug_mode_fails_before_deploying(env):
    env.setenv("debug_mode", "maybe")
    with pytest.raises(ValueError, match="debug_mode"):
        deploy.main()
