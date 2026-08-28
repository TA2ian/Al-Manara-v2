# ADR-008: Telegram Runtime — aiogram

## Status

Accepted.

## Decision

Al-Manara v2 uses **aiogram 3.31.0** as the Telegram application framework baseline.

The dependency is pinned to the exact version in the production dependency lock. Minor/major upgrades require dependency compatibility tests and an explicit review before adoption.

## Compatibility

The selected aiogram release supports Python 3.13 and declares Python compatibility from 3.10 through below 3.15. The release was published on 2026-08-26. citeturn1search0

## Architectural rules

aiogram is confined to the `presentation/telegram` boundary and its directly related adapters/middleware. Domain and application business services must not import aiogram types.

Telegram handlers are interaction adapters only. They may:

- authenticate/authorize through the application boundary;
- validate and normalize transport input;
- construct application commands/queries;
- invoke application services;
- render application results through centralized message templates/keyboards.

Handlers must not:

- mutate `Order.status` directly;
- perform pricing or fee calculations;
- execute database queries directly;
- implement wallet validation rules;
- implement receipt comparison rules;
- decide authorization independently of the authorization service;
- contain duplicated business logic.

## FSM rule

aiogram FSM is permitted only for transient interaction state, such as the input currently expected from a user. It is not a source of truth for `Order.status`, verification status, wallet status, or other persistent domain state.

## Router rules

Routers are organized by business interaction boundary, with namespaced and unique callback conventions. Callback uniqueness and keyboard-to-handler reachability are enforced by automated tests.

## Rationale

aiogram 3.x provides an asynchronous architecture, routers, FSM, middlewares, and typed Telegram API integration that fit the project's presentation-layer requirements. citeturn1search1turn1search0

The decision intentionally does not reuse or preserve the routing/FSM architecture of the legacy repository.
