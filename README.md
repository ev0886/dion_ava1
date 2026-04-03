# DION ABA1

Backend MVP foundation for the DION ABA1 vending machine control system.

Implemented MVP areas:

- RFID/PIN authorization
- dispense, return, and refill flows
- service mode diagnostics and export planning
- recovery scan and case handling
- local persistence, audit, and event logs
- mock, stub-real, and real hardware provider composition

Quick runtime pointers:

- API app factory: `app.api.create_app`
- bootstrap entry point: `python -m app.main`
- operator CLI: `python -m app.cli --help`
- test suite: `python -m pytest`

Operational notes for freeze/release-candidate use are in [docs/runtime-operator-summary.md](docs/runtime-operator-summary.md).
Project design/reference material remains in `docs/`.
