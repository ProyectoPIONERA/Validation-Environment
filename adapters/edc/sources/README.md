This directory stores the local source references used by the generic EDC adapter.

Current convention:

- `connector/`: local clone or synchronized working copy of the upstream repository `https://github.com/luciamartinnunez/Connector`

Recommended workflow:

- If `connector/` does not exist yet, `scripts/sync_sources.sh --apply` clones it from GitHub.
- If `connector/` already exists as a Git repository, `scripts/sync_sources.sh --apply` updates it.
- If a local source directory is passed explicitly to `scripts/sync_sources.sh --source <path>`, the synchronization keeps the existing `build/` outputs so the adapter can reuse a previously built `connector.jar`.
- `scripts/build_image.sh --apply` can trigger the synchronization step automatically before the image build.
- `scripts/build_image.sh --apply` reuses `transfer/transfer-00-prerequisites/connector/build/libs/connector.jar` when it is already present in `sources/connector/`.
- If the jar is missing, `scripts/build_image.sh --apply --force-build` falls back to Gradle using a local `GRADLE_USER_HOME` inside `sources/connector/`.
