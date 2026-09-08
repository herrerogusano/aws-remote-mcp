# Operational approval policy

Explicit impact review is required before:

- creating or changing AWS infrastructure;
- enabling a remotely callable endpoint;
- adding OAuth/OIDC infrastructure or real credentials;
- broadening Lambda IAM across AWS services;
- performing the first real Telegram or Trello write;
- adding a persistent or uncertain-cost service;
- activating PROD or automatic deployment;
- deleting stacks, secrets, data or externally created content;
- replacing Lambda/API Gateway with a different compute architecture.

Each review identifies exact resources, permissions, exposure, expected traffic,
current pricing, secrets, failure modes and rollback. Approval is scoped only to
the action described and does not carry forward to later expansions.
