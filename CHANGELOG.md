# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Inputs can now be set with `with:` as `action.yml` declares them. The previous way, bare lower case
  environment variables set with `env:` (`gcp_project: ...`), keeps working; the input wins if both are set.
- Failures now say why: the error is written to the log and as an error annotation on the run
  instead of a bare `DeployFailed`.

### Fixed

- The archive no longer contains `.git/`, `__pycache__/`, `*.pyc`, `.env`, `.env.*` and `.DS_Store`, so
  secrets stored next to the code are not uploaded to the function's source bucket. The archive is
  built in a stable (sorted) order.
- A failed upload of the source code (non-2xx from the signed upload URL) now fails the step instead of
  patching the function anyway and reporting success. The upload has a 5 minute timeout.
- `debug_mode` is parsed strictly (`true`/`false`/`1`/`0`/`yes`/`no`; empty means off); an empty value used to
  crash with a `SyntaxError`. The debug output printed the bound method `response.json` instead of the
  response body.
- An empty function directory (or one that only contains excluded files) fails with a clear message.
- Invalid `credentials` JSON fails with a message that does not echo the secret.

### Security

- Debug output redacts `environmentVariables` and `buildEnvironmentVariables` of the function definition.

## [v0.1.0] - 2021-12-19

### Changed

* Initial Release
