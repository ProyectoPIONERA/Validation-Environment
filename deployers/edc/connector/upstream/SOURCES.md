# Upstream Sources for `deployers/edc/connector`

This directory contains framework-owned deployment artifacts derived from upstream references.
It is intentionally not a live clone of any external repository.

## Primary Upstream

- Repository: `https://github.com/luciamartinnunez/Connector`
- Optional local reference checkout: `adapters/edc/sources/connector`
- Reference commit: `43e72469c3027fb40bfa2ba806d3e5e8cb0e1add`

## Referenced Paths

- `transfer/transfer-00-prerequisites/resources/configuration/provider-configuration.properties`
- `transfer/transfer-00-prerequisites/resources/configuration/consumer-configuration.properties`
- `transfer/transfer-01-negotiation/resources/create-asset.json`
- `transfer/transfer-01-negotiation/resources/create-policy.json`
- `transfer/transfer-01-negotiation/resources/create-contract-definition.json`
- `transfer/transfer-01-negotiation/resources/fetch-catalog.json`
- `transfer/transfer-01-negotiation/resources/negotiate-contract.json`
- `transfer/transfer-02-provider-push/resources/start-transfer.json`

## Usage Rules

- Use the upstream repository as a reference for EDC runtime configuration and flow examples.
- Keep this chart self-contained and reproducible inside `Validation-Environment`.
- If synchronization with the upstream is needed later, do it with a manual maintenance script instead of cloning during normal deployment.
