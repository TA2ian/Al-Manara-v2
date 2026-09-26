---
name: Telegram runtime integration strategy
description: Project decision for integrating complete bot behavior without growing a monolithic runtime.
---

Do not add new business flows directly into the monolithic Telegram polling runtime. First establish a coherent production composition and separate bounded customer/admin routers, then connect existing application and persistence services through those boundaries.

**Why:** A full-code review found that most V2 services are implemented and tested but unreachable in production, while repeated route additions concentrated orchestration, state, and policy in one runtime file and obscured the missing end-to-end composition.

**How to apply:** Keep the poller lease and V2 domain/persistence foundations. Refactor production composition, private-chat policy, durable conversation state, customer routers, and admin routers before adding further behavior.