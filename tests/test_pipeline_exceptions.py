import pytest

from plugin_scripts.pipeline_exceptions import (
    CloudFunctionDirectoryNonExistent,
    DeployFailed,
)


@pytest.mark.parametrize(
    "exception_object",
    [
        CloudFunctionDirectoryNonExistent({}),
        DeployFailed({}),
    ],
)
def test_exception_init(exception_object):
    e = exception_object
    assert isinstance(e, Exception)


@pytest.mark.parametrize(
    "exception_class",
    [
        CloudFunctionDirectoryNonExistent,
        DeployFailed,
    ],
)
def test_exception_throws(exception_class):
    e = exception_class({})
    with pytest.raises(exception_class):
        raise e
