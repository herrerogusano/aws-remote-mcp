# Safety shutdown capacity options

Status: offline design proposal only. It does not authorize a quota request,
CloudFormation change, IAM change, deployment, invocation or validation window.
No live AWS state was read while producing this note.

## Current contract

The MCP Lambda is deployed with reserved concurrency zero outside an approved
window. The safety-shutdown Lambda currently has no reserved concurrency and
therefore competes for the regional unreserved pool. Scheduler and the request
alarm's SNS topic can invoke the same idempotent handler. The handler attempts,
in order, to disable the API, restore MCP concurrency zero and delete the alarm,
and it reports if any action fails.

The read-only evidence supplied by coordination on 2026-10-01 was an applied
regional quota, account limit and unreserved pool of 10. This repository did not
repeat those reads. With that profile, neither MCP reserved concurrency one nor
a dedicated safety reservation can satisfy Lambda's documented 100-unit
unreserved floor. All proposed reserved paths must fail closed.

## Option A — static reserved concurrency one for safety shutdown

Assign `ReservedConcurrentExecutions: 1` to the safety function in an explicitly
selected environment. Keep that reservation while the stack exists, including
outside validation windows.

Advantages:

- unrelated Lambda traffic cannot consume the shutdown's single execution slot;
- no opening-script race is introduced to acquire safety capacity;
- the current handler IAM can remain scoped only to closing the API, MCP Lambda
  and alarm; the handler does not need to change its own concurrency;
- reserved concurrency does not pre-initialize an execution environment and is
  not provisioned concurrency. It is expected to have no fixed execution charge,
  although current AWS pricing must be rechecked before approval.

Costs and limits:

- every stack configured this way permanently consumes one regional concurrency
  unit. Reserving DEV and PROD therefore consumes two even while both are closed;
- concurrency one serializes Scheduler and SNS invocations. If both arrive
  together, one can be throttled or delayed. One successful invocation is enough
  to reach the desired state, but delivery/retry behavior must be explicitly
  configured and validated;
- dedicated capacity does not protect against IAM errors, control-plane errors,
  regional service failures or a defect in the handler;
- CloudFormation's execution role must be verified to permit setting concurrency
  on the exact safety function. No runtime-role broadening is expected.

Recommended scope if selected: reserve safety capacity for DEV only while PROD
has no authorized window mechanism. Do not reserve every environment merely
because it shares the template.

## Option B — dynamic safety reservation during a window

The opener could reserve safety concurrency one before creating the schedule or
alarm, then reserve MCP concurrency and enable the API last. Capacity would be
released only after API disablement, MCP concurrency zero and removal/readback of
all temporary triggers.

This reduces idle capacity allocation but adds a second concurrency mutation,
additional operator IAM, more partial states and more rollback branches. The
safety handler should not remove its own reservation: that would broaden its IAM
and creates a race with a simultaneous trigger. A separate closer would have to
release it after confirming no invocation or trigger remains pending.

This option provides no cost advantage over a static reservation because
reserved concurrency alone is not provisioned capacity. It is not recommended
unless regional capacity is so constrained that the static unit cannot be held.

## Capacity calculation

For static dedicated shutdown capacity:

`Q >= R_other + K + W + max(100, C)`

- `Q`: applied account concurrency quota in the target region;
- `R_other`: all other reserved/provisioned allocations, without double counting;
- `K`: static safety-shutdown reservations;
- `W`: simultaneous MCP window reservations;
- `C`: bounded simultaneous use of the unreserved pool.

If shutdown remains unreserved, use:

`Q >= R_other + W + max(100, C + S)`

where `S` is the shutdown concurrency that must remain runnable. The 100-unit
floor is shared capacity, not dedicated free capacity.

With `R_other=0` and `C<=100`:

| Planned reservations | Structural floor |
|---|---:|
| Two MCP windows, no dedicated shutdown | 102 |
| Two MCP windows, one dedicated shutdown | 103 |
| Two MCP windows, two dedicated shutdowns | 104 |

These are structural minima, not recommended quota requests. The requested value
must also include every existing allocation and credible unreserved workload in
the same account and region. Reservations in another region do not contribute.

## Option C — managed workflow without Lambda execution capacity

A Standard Step Functions workflow could perform the control-plane sequence
directly: API Gateway disable, MCP concurrency zero, alarm cleanup and final
readback. Scheduler would start the workflow at the deadline; an EventBridge
rule matching the named CloudWatch alarm's `ALARM` event could start the same
workflow for the request tripwire.

This removes shutdown dependence on Lambda concurrency, but adds a state machine,
two narrowly scoped trigger roles, a task role, state-transition cost, event
delivery latency and another regional control-plane dependency. The workflow
must attempt every closing action, bound retries/backoff, tolerate duplicate
triggers and record a terminal failure without payloads or private identifiers.
It must not use parallel closure when API disablement must precede compute stop.

Before choosing this option, verify against current primary AWS documentation:

- exact Step Functions AWS SDK integration support for API Gateway v2, Lambda
  concurrency and CloudWatch alarm operations;
- Scheduler and EventBridge target support, retry policy, maximum event age and
  duplicate-delivery behavior;
- exact per-transition/event cost and log-retention behavior;
- CloudFormation resource support and least-privilege resource scoping.

Scheduler universal AWS SDK targets may be useful for a deadline, but one target
does not provide an ordered multi-action transaction. Multiple schedules can
partially succeed. Systems Manager Automation is another control-plane executor,
but its supported targets, latency, IAM and cost also require primary-source
verification. Neither is accepted here without a separate spike and review.

## Trigger races and failure handling

Scheduler and the alarm path may fire together, and an alarm closure does not
automatically cancel a deadline invocation already queued. Every design must
expect duplicates and make each target-state operation idempotent. A duplicate
must not be suppressed merely because another close started: the first attempt
may fail partway through.

Required order and evidence:

1. disable API Gateway;
2. set MCP reserved concurrency to zero;
3. remove alarm and schedule where safe;
4. read back API disabled, MCP concurrency zero, stage throttle 1/1 and no
   temporary controls;
5. emit only allowlisted status/error categories.

Retries must be bounded and distinguish an already-absent resource from an
unverified failure. Keep the manual close script as an operator recovery path.

## Minimum future read-only inventory

These reads require new, current authority and must use the intended account and
`eu-west-1`. They were not executed for this proposal.

### Identity and applied capacity

1. `sts:GetCallerIdentity` once, checking the account locally without logging it.
2. `servicequotas:GetServiceQuota` for Lambda concurrent executions.
3. `lambda:GetAccountSettings` for the applied regional and unreserved limits.

### All regional allocations

4. Paginated `lambda:ListFunctions`, or an exact authoritative stack inventory
   if it is proven to cover every function in the region.
5. `lambda:GetFunctionConcurrency` for every discovered function.
6. `lambda:ListProvisionedConcurrencyConfigs` for every function, accounting for
   Lambda's reserved/provisioned overlap without double counting.

`GetAccountSettings` is enough for the structural preflight used by the opener,
but not for attributing every allocation to a project. CloudWatch concurrency
metrics are useful operational evidence, not a substitute for configuration
inventory or a preventive capacity guarantee.

### Closed-state verification for each project/environment

7. Exact CloudFormation stack status and outputs.
8. `apigatewayv2:GetApi` and `GetStages`: endpoint disabled and throttle 1/1.
9. `lambda:GetFunctionConcurrency`: MCP zero and safety value exactly as designed.
10. Exact-name CloudWatch alarm read and exact Scheduler group listing: no
    temporary control remains.
11. If trigger wiring changes, read the exact Lambda/SNS/EventBridge/Scheduler or
    Step Functions resource policies and targets without invoking them.

No Cost Explorer query, Lambda invocation, endpoint request, external provider
call or write is required for this inventory.

## Recommendation and gates

Do not change the current quota-10 deployment. Before any regional increase,
choose explicitly between:

- static safety reservation one in DEV as the smallest design change; or
- a separately prototyped Step Functions/EventBridge closure that removes the
  Lambda-pool dependency at the cost of more infrastructure and IAM.

Only after that choice should the supervisor calculate one account-wide regional
target across every MCP and environment. Quota request, live inventory, IaC/IAM
implementation, deployment and controlled trigger validation are separate gates.

## References to verify before implementation

- https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html
- https://docs.aws.amazon.com/lambda/latest/dg/monitoring-concurrency.html
- https://docs.aws.amazon.com/step-functions/latest/dg/supported-services-awssdk.html
- https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html
- https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-and-eventbridge.html

