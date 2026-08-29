# Claude Agent Instructions

## Code style

- Prefer deep modules with narrow interfaces.
- Include numpy-style documentation strings for public interface members and modules.

## Tooling

Use `uv` for dependency management and `ruff` for linting/formatting.
Use `ty` for typechecking; it is pinned in the dev dependency group and runs as a pre-commit hook before every commit.
- Run `pre-commit install --hook-type pre-commit --hook-type commit-msg` after cloning.
- The `commit-msg` hook enforces Conventional Commits format (see https://www.conventionalcommits.org/).

### Commit messages

- Write all commit messages in Conventional Commits format: `type(scope?): description`.

## Coding workflow

- Use a red-green-refactor approach to coding
  - Start with a red/failing unit-test
  - Then write the minimal implementation to make the test pass
  - Finally, refactor to simplify the code, improve maintainability, etc.
- Implement vertical slices, but follow the component structure from the architecture.

## When to write code at all

Before writing any code, stop at the first rung that holds:

1. Does this need to be built at all? No? Skip it.
2. Does it already exist in the codebase? Reuse the helper, util, or pattern.
3. Does the standard library do it? Use it.
4. Does a native platform feature cover it? Use it.
5. Does an already-installed dependency solve it? Use it.
6. Can this be one line? Do it.
7. Only then: write the minimum code that works.

## Important documentation sources

- [Architecture documentation](docs/architecture)

