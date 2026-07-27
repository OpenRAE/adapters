.PHONY: devmain docs policy precommit prepush verify

REQUIREMENT_ARG := $(shell if test -n "$${ACES_REQUIREMENT_UID:-}" || git branch --show-current | grep -qE '[A-Z]{3}-[0-9]{3}'; then :; else printf '%s' '--skip-requirement'; fi)

devmain: ## Open the dev -> main promotion PR titled so the PR-title gate passes
	@gh pr create --base main --head dev \
	  --title "chore(main): promote dev" \
	  --body "Promotes \`dev\` to \`main\`. Merge with a merge commit — squashing collapses the Conventional Commit subjects Release Please needs and loses this release's CHANGELOG."

docs: ## Build documentation strictly
	uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s docs

policy: ## Run repository policy for the current branch posture
	uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s policy -- $(REQUIREMENT_ARG)

precommit: ## Run the repository pre-commit boundary
	uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s hook-pre-commit -- $(REQUIREMENT_ARG)

prepush: ## Run the repository pre-push boundary
	uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s hook-pre-push -- $(REQUIREMENT_ARG)

verify: ## Run the canonical verification graph
	uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify -- $(REQUIREMENT_ARG)
