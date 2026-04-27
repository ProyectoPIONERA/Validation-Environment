This directory stores the local source references used by the generic EDC adapter.

Current convention:

- `connector/`: local clone or synchronized working copy of the upstream repository `https://github.com/luciamartinnunez/Connector`

Recommended workflow:

- Keep a prepared local working copy in `connector/`.
- Do not rely on the framework to clone or update the private upstream repository automatically.
- If `connector/` does not exist yet, place or synchronize a local checkout there explicitly.
- If `connector/` already exists as a Git repository, update it intentionally outside the default Level 4 path.
- If a local source directory is passed explicitly to `scripts/sync_sources.sh --source <path>`, the synchronization keeps the existing `build/` outputs so the adapter can reuse a previously built `connector.jar`.
- `scripts/build_image.sh --apply` refuses to synchronize from the default remote when `connector/` is missing or incomplete.
- `scripts/build_image.sh --apply --sync-source <path>` can synchronize from an explicit local source before the image build.
- `scripts/build_image.sh --apply` reuses `transfer/transfer-00-prerequisites/connector/build/libs/connector.jar` only when it is already present and still newer than its Gradle/runtime inputs.
- If the jar is missing or outdated, `scripts/build_image.sh --apply` rebuilds it through Gradle using a local `GRADLE_USER_HOME` inside `sources/connector/`.
- `scripts/build_image.sh --apply --force-build` still forces a rebuild even when the existing jar looks up to date.
