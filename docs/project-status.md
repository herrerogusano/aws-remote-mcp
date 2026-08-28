# Project status

Region: `eu-west-1`

## Current state

The application core, local Streamable HTTP transport, authorization contract
and closed-by-default AWS foundation are implemented. The open pull request is
green locally and awaits final CI after cost-safety hardening. No project stack,
remote endpoint or external integration has been deployed.

## Deployment posture

- DEV stack prepared; deployment approval pending.
- Default API endpoint disabled.
- Temporary AWS IAM protection configured.
- MCP Lambda concurrency zero outside an approved test window.
- Five-minute signed validation window has scheduled and volume-based shutdown.
- PROD and continuous deployment do not exist.

## Account cost posture

The AWS account has a monthly $1 budget with two email notifications from $0.01
actual spend. AWS provides no guaranteed hard spending cap. The project therefore
uses disabled compute/endpoints and brief independently closed test windows as
its primary cost controls.

## Next decision

Review the exact closed-stack resources, IAM and rollback. If approved, deploy
the closed DEV foundation only. Opening a validation window is a separate
decision after the closed state is verified in AWS.
