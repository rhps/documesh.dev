# explain-error

Match an error message or stack trace to the closest documentation sections.

## When to use

- When the user pastes an error message, exception, or log output
- When the user asks "why is this failing?" about a specific error

## How it works

Extracts error signatures (exception names, k8s state reasons, errno codes, exit codes)
and matches them against a federated index of 17,000+ documentation chunks.
Returns top-3 diversified results with an honest disclaimer — never a diagnosis.
