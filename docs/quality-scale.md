# Quality bar: Home Assistant's Integration Quality Scale

The standard we hold our Home Assistant integrations to is Home Assistant's own
[Integration Quality Scale](https://www.home-assistant.io/docs/quality_scale/)
([developer rules](https://developers.home-assistant.io/docs/core/integration-quality-scale/)).

**Target: Gold.** Bronze and Silver are the floor; Platinum where it costs little.

The scale officially scores core integrations only, so for a custom integration this is our own
bar, not a badge. Each tier includes every rule of the tiers below it.

> Written 2026-11-27 from the published rule set. The Home Assistant sites couldn't be reached
> from the environment this was written in, so check the links above for rules added since.

## Tracking it: `quality_scale.yaml`

Keep a `quality_scale.yaml` next to `manifest.json`, the same file core integrations use. Every
rule gets a status:

```yaml
rules:
  config-flow: done
  test-before-configure: todo
  discovery:
    status: exempt
    comment: A cloud service; there is no device on the network to discover.
```

- `done`: the rule is met, and a test proves it where it can.
- `todo`: not met yet.
- `exempt`: doesn't apply. Always give a `comment` saying why.

## The tiers

| Tier | What it means for a household |
|---|---|
| Bronze | Set up from the UI, follows basic coding standards, its config flow is tested, basic docs. |
| Silver | Reliable: handles errors and outages, recovers by itself, asks to sign in again when it must, has an active owner. |
| Gold | The best experience: discovered automatically, devices and entities named and translated, full docs, diagnostics, repairs. |
| Platinum | Technical excellence: fully async, strictly typed, efficient with the network and CPU. |

## Bronze

- `action-setup`: service actions are registered in `async_setup`, not per config entry.
- `appropriate-polling`: a polling integration polls at a sensible interval.
- `brands`: brand assets (icon, logo) exist ([home-assistant/brands](https://github.com/home-assistant/brands)).
- `common-modules`: shared patterns live in common modules (`coordinator.py`, `entity.py`).
- `config-flow`: set up from the UI; `data_description` on every field; `data` vs `options` used correctly.
- `config-flow-test-coverage`: the config flow has full test coverage.
- `dependency-transparency`: every dependency is on [PyPI](https://pypi.org/), open source, and built in public CI.
- `docs-actions`: the docs describe each service action.
- `docs-high-level-description`: the docs say what the brand, product or service is.
- `docs-installation-instructions`: step-by-step install instructions.
- `docs-removal-instructions`: how to remove it.
- `entity-event-setup`: entities subscribe to events in `async_added_to_hass` and unsubscribe on removal.
- `entity-unique-id`: every entity has a unique ID.
- `has-entity-name`: entities set `has_entity_name = True`.
- `runtime-data`: runtime state goes in `ConfigEntry.runtime_data`, not `hass.data`.
- `test-before-configure`: the config flow tests the connection before creating the entry.
- `test-before-setup`: setup checks it can work and raises `ConfigEntryNotReady` / `ConfigEntryAuthFailed` / `ConfigEntryError` when it can't.
- `unique-config-entry`: the same device or account can't be set up twice.

## Silver

- `action-exceptions`: service actions raise `ServiceValidationError` / `HomeAssistantError` on failure.
- `config-entry-unloading`: config entries unload cleanly.
- `docs-configuration-parameters`: the docs describe every option.
- `docs-installation-parameters`: the docs describe every setup field.
- `entity-unavailable`: entities show unavailable when their source can't be reached.
- `integration-owner`: it has a named code owner.
- `log-when-unavailable`: log once when the service goes away and once when it comes back.
- `parallel-updates`: `PARALLEL_UPDATES` is set on each platform.
- `reauthentication-flow`: expired credentials are re-entered from the UI.
- `test-coverage`: above 95% test coverage across every module.

## Gold

- `devices`: it creates devices.
- `diagnostics`: it implements diagnostics, with secrets redacted.
- `discovery`: it can be discovered (zeroconf, SSDP, DHCP, Bluetooth, USB…).
- `discovery-update-info`: discovery updates a device's network info (a new IP).
- `docs-data-update`: the docs say how and how often data updates.
- `docs-examples`: the docs give automation examples.
- `docs-known-limitations`: the docs list known limitations.
- `docs-supported-devices`: the docs list supported (and unsupported) devices.
- `docs-supported-functions`: the docs describe each entity and function.
- `docs-troubleshooting`: the docs have troubleshooting steps.
- `docs-use-cases`: the docs describe use cases.
- `dynamic-devices`: devices added after setup appear without a reload.
- `entity-category`: entities get the right `EntityCategory` (config, diagnostic).
- `entity-device-class`: entities use device classes where one fits.
- `entity-disabled-by-default`: noisy or rarely used entities are disabled by default.
- `entity-translations`: entity names come from `strings.json` translations.
- `exception-translations`: exception messages are translatable.
- `icon-translations`: icons come from `icons.json`, not hard-coded.
- `reconfiguration-flow`: settings can be changed from the UI with a reconfigure flow.
- `repair-issues`: repair issues and repair flows are raised when a person must act.
- `stale-devices`: devices that are gone are removed.

## Platinum

- `async-dependency`: the dependency is async.
- `inject-websession`: the dependency accepts Home Assistant's shared web session.
- `strict-typing`: the code passes strict [mypy](https://mypy-lang.org/) typing.
