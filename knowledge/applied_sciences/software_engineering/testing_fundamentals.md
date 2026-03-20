# Software Testing Fundamentals

## Definition
Software testing is the process of evaluating a system to detect differences between expected and actual behavior. Testing provides confidence that the software meets requirements, reveals defects before production, and acts as a safety net for ongoing development.

## Core Concepts

- **Testing Pyramid:** (Martin Fowler) Unit tests (many, fast, cheap) → Integration tests (fewer, medium) → End-to-end tests (few, slow, expensive). UI tests at the top are the most brittle. Invert the pyramid = slow, fragile test suite.
- **Unit Testing:** Tests individual functions/classes in isolation. Dependencies replaced with mocks or stubs. Fast execution. TDD (Test-Driven Development): write failing test → write minimal code to pass → refactor.
- **Integration Testing:** Tests how multiple components work together (database + ORM, service + external API). More realistic but slower. Use test containers for real database dependencies.
- **End-to-End (E2E) Testing:** Tests the full user journey through the real application. Tools: Playwright, Cypress, Selenium. Valuable for critical user flows; expensive to maintain.
- **Test Double Types:**
  - Stub: Returns pre-defined data.
  - Mock: Verifies interaction occurred (was method called with right args?).
  - Fake: Simplified working implementation (in-memory database).
  - Spy: Records calls to a real object.
- **Test Quality — FIRST principles:** Fast, Independent, Repeatable, Self-validating, Timely.
- **Code Coverage:** Percentage of code executed by tests. 80% is a common target. High coverage does not guarantee quality — tests must also have meaningful assertions.
- **Property-Based Testing:** Generate hundreds of random inputs to find edge cases. Tools: Hypothesis (Python), QuickCheck (Haskell/Erlang), fast-check (JS).
- **Performance Testing:** Load testing (expected load), stress testing (beyond normal load), soak testing (sustained load). Tools: k6, Locust, JMeter.

## Testing Anti-Patterns
- Testing implementation details instead of behavior
- Brittle tests that break on refactoring
- Testing the framework/library, not your logic
- Slow tests that discourage running them often

## Practical Applications
- **CI/CD:** Tests run on every commit. Fail fast. Block merges if tests fail.
- **Regression testing:** Prevent previously fixed bugs from returning.
- **Refactoring:** Good test coverage enables fearless refactoring.
- **Documentation:** Tests serve as executable specification of expected behavior.
- **API contracts:** Consumer-driven contract testing (Pact) ensures services remain compatible.
