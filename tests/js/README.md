# JS unit tests

Pure-logic tests for `shared/assets/js/*` using Node's built-in test runner
(no dependencies, Node >= 18):

    node --test tests/js/*.test.js

Each module under test is a classic browser script that attaches to a global
`BB` namespace. The tests load it with `loadModules()` from `_harness.js`,
which evaluates the file against a minimal fake `window`/`document`.
