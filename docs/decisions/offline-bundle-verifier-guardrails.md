# Offline evidence-bundle verifier guardrails

GitHub issue #92 is the authority for this requirement-free deliverable. This
note fixes the architecture and security boundaries the implementation must
respect. It defines no RAES contract, evidence semantics, or implementation
plan.

## Keep byte integrity separate from evidence meaning

`raes-adapters verify-bundle --bundle PATH` is an always-installed, offline,
read-only verifier for the repository's existing `inventory.json` seal shape.
It proves only that one regular-file tree is closed over exact relative paths,
declared sizes, and SHA-256 digests, including nested inventories. It does not
prove that capture was complete, redaction was adequate, a RAES model is valid,
an aggregate is correct, a backend is conformant, or a scientific conclusion
is supported.

The integrity command must remain independent of simulator extras and backend
modules. In particular, it does not replace
`raes_adapters.cyborg.reproduction.verify_bundle()`: that backend-local
function validates the frozen CAGE-2 protocol, RAES artifact joins, evidence
closure, aggregates, tiers, and report text. Those semantic checks may run only
after the generic byte boundary succeeds and remain separately named and
reported.

The inventory object is the exact producer shape already emitted by
`raes_adapters.cli._seal_inventory()` and
`raes_adapters.cyborg.reproduction._seal_inventory()`:

```json
{"artifacts":[{"media_type":"application/json","path":"run.json","sha256":"...","size_bytes":1}]}
```

This repository must not promote that local seal into a second RAES evidence
schema, add semantic fields, or place it in `raes_adapters.base`. The verifier
may use private in-process records and a deterministic presentation card, but
neither is a portable evidence DTO, diagnostic schema, or persistence format.

## Canonical incumbents

| Concern | Incumbent and required boundary |
| --- | --- |
| Installed command | `[project.scripts]` in `pyproject.toml`, the `raes-adapters` distribution identity, and the existing researcher `cli.main()` exit/error conventions. Use one lazy top-level dispatcher so `verify-bundle` imports neither the researcher shell nor simulator modules. Do not add another console script or command framework. |
| Inventory production | `cli._seal_inventory()`, `cyborg.reproduction._seal_inventory()`, `raes_operations.run_artifacts.atomic_write_json_artifact()`, relative POSIX names, SHA-256, and inventory-last sealing. Verification consumes those final bytes; it does not call a writer or change producer semantics. |
| Strict input handling | The duplicate-key rejection and exact-shape behavior already used by `cli._strict_json()` and `cyborg.reproduction.load_strict_json()`. The verifier needs an isolated bounded byte parser because importing either semantic command path would violate offline isolation; matching tests, not a new schema registry, keep the shapes aligned. |
| Failure hygiene | Stable researcher exit mappings, fixed input-free messages, and the default-deny principles in `base.redaction`. Verifier output contains only allowlisted codes, dispositions, fixed disclaimers, and bounded counts, so it must never render a rejected path, JSON value, exception, argv, environment value, or traceback. |
| Semantic validation | Published RAES models and validators, environment-pack validation, task/run joins, conformance runners, and backend-local reproduction verification remain downstream owners. A digest match never bypasses them. |
| Persistence | None. Artifact producers retain exclusive roots, atomic writes, and inventory-last sealing. The verifier writes no report, cache, temporary extraction, repaired inventory, access log, or lock file; stdout/stderr are its only output surfaces. |
| Packaging and workflow | The single `pyproject.toml`, single `uv.lock`, `_verification_envs()`, existing `tests` and `distributions` sessions, clean-wheel probe, strict docs build, `.github/workflows/ci.yml`, and `PR Gate`. Add no verifier-only workflow or simulator dependency. Native simulator qualification remains the existing Ubuntu-authoritative lane and is not part of integrity verification. |

## Fixed admission limits

The limits are issue-owned security constants, not defaults or tuning knobs:

| Limit | Fixed value | Meaning |
| --- | ---: | --- |
| Regular files | 100,000 | Every discovered regular file, including inventories, is charged once. Directory traversal work must also remain bounded. |
| Inventories | 100,000 | Every distinct `inventory.json` admitted through transitive closure. |
| Inventory entries | 200,000 | Sum of entries across all admitted inventories. |
| Unique bytes | 4 GiB | Sum of bytes hashed per unique admitted path; hard-linked paths do not evade the budget. |
| Artifact bytes | 500 KiB | Maximum for each non-inventory regular file. |
| Inventory bytes | 16 MiB | Maximum raw size of each inventory before parsing. |
| Path depth | 32 | Maximum normalized POSIX path-component count. |
| Path bytes | 1,024 | Maximum UTF-8 byte length of each inventory-relative path. |

Limits are checked before unbounded allocation or work and failures use the
stable invalid/tampered exit (`3`). The 4 GiB ceiling is an I/O admission
budget, not permission to retain 4 GiB in memory: artifacts are hashed in
bounded chunks, only the current bounded inventory payload is parsed, and
records retain metadata rather than file content. Limit counters have one
definition shared by flat and nested bundles; nested inventories do not reset
budgets.

## Filesystem and parser security boundary

The selected root is untrusted and may mutate concurrently. Containment must
therefore be established by filesystem handles, not by pathname checks alone:

- open and pin the real root directory without following a symlink or reparse
  point, then enumerate and open every descendant relative to already admitted
  directory handles;
- apply no-follow semantics to every path component, require intermediate
  components to remain directories and terminal members to be regular files,
  and use non-blocking admission where a raced FIFO/device could otherwise
  hang before its type is checked;
- pin root, directory, and file identities around enumeration and hashing,
  then recheck membership and identities before reporting success;
- reject links, sockets, devices, FIFOs, mount/reparse escapes, unreadable
  members, replacements, additions, removals, and metadata/content mutation;
  no byte outside the selected root may be read even transiently; and
- never silently drop no-follow or handle-relative guarantees on a platform
  lacking the required primitives. Supply an equivalent safe primitive or fail
  closed; portability cannot weaken containment.

`Path.resolve()`, `rglob()`, `is_file()`, a pre-open `lstat()`, or
`O_NOFOLLOW` on only the final component cannot establish this boundary under
concurrent directory replacement. Inventory paths are logical POSIX paths and
must be opened component-by-component; do not reinterpret a complete inventory
string using host drive, UNC, or separator rules.

The root inventory is mandatory. Its object has exactly the `artifacts` key;
each entry has exactly `media_type`, `path`, `sha256`, and `size_bytes`.
Parsing rejects invalid UTF-8, duplicate JSON keys, non-object roots,
non-array artifacts, unknown/missing entry fields, booleans as sizes,
negative sizes, non-lowercase/non-64-character SHA-256 text, empty media types,
non-finite constants, excessive parser nesting, and every malformed path.
Paths are non-empty, normalized, relative POSIX text with no NUL, absolute
root, `.`/`..`, repeated separator, backslash, or over-limit encoding.
Parser depth/resource errors caused by input are invalid input (`3`), not an
internal failure (`70`).

Closure is global and exact. Each declared path appears once, every declared
member exists and matches, every discovered regular file other than the root
inventory is reached by exactly one inventory entry, and every referenced file
named `inventory.json` is parsed transitively. An inventory cannot list itself,
appear twice, reset the base to the bundle root, or leave extra files hidden in
a nested directory.

## Cross-cutting path

| Layer the command passes | Required treatment |
| --- | --- |
| Authentication/authorization | None: this is a local process acting with the invoking user's filesystem authority. It adds no HTTP route, daemon, remote identity, participant authority, or policy decision. A future network surface must use RAES strict-default control-plane security rather than exposing this function directly. |
| Secrets and environment bindings | No credential, token, secret resolver, `.env`, ambient configuration, or environment-selected policy is read. `--bundle` is the only path input; users must not encode secrets in path names because argv is OS-visible. The command never echoes that path. |
| CLI/config shape | Closed `argparse` options: `verify-bundle`, required `--bundle`, and fixed `--format` choices. Limits, inventory names, algorithms, parser modules, import paths, network locations, and output destinations are not configurable by flags or environment. |
| Filesystem parser/policy gate | Descriptor-rooted containment, regular-file admission, strict POSIX path validation, exact JSON shape, duplicate rejection, fixed limits, digest/size comparison, global inventory closure, and mutation checks all pass before success is rendered. |
| OS/process exposure | No shell, subprocess, archive extraction, plugin discovery, home-directory scan, temporary output, or runtime download. The bundle path necessarily appears in process argv but never in output, logs, artifacts, or child processes. File descriptors are close-on-exec even though no child is launched. |
| Error envelope | `0` is verified, `2` closed usage failure, `3` invalid/tampered/unreadable/over-limit input, and `70` an unexpected internal defect. Expected hostile input must not reach `70`. JSON, terminal, and Markdown renderers emit deterministic allowlisted content only; internal failures go to stderr without details or traceback. |
| Logging/observability | No library logging. Success may expose fixed claim text and bounded counts; failure exposes only a stable code/status. Paths, member names, digests, media types, rejected values, file bytes, exception details, and timing are not observability fields. |
| Persistence/network/imports | No writes or network access. Lazy dispatch imports only stdlib-backed verifier code for this command and must work from the base clean-installed wheel without simulator extras. |

## Extension seam

The backend extension seam is the existing inventory producer shape: a new
adapter that emits the same seal needs no verifier registration or backend-name
branch. The presentation seam is the pure `--format` renderer over one
integrity-only result; adding an explicitly required renderer must not alter
verification or rerun filesystem access. Lazy command dispatch is the import
isolation seam.

A future inventory version, digest algorithm, archive transport, remote object
store, or semantic claim requires a separately governed contract and threat
model. Do not prebuild a schema registry, algorithm plugin, filesystem service,
or configurable policy in anticipation of it.

## Gotchas and anti-patterns

- Do not reuse the CybORG reproduction verifier as the generic command or move
  its protocol, aggregate, tier, leakage-scan, or scientific checks into shared
  code.
- Do not call producer-side sealers, atomic writers, RAES contract loaders, or
  simulator imports while verifying bytes.
- Do not use path resolution plus prefix comparison as the containment proof,
  follow an intermediate link after an earlier check, or trust a directory
  entry after reopening it by pathname.
- Do not buffer all artifacts or all inventories, enumerate an unbounded tree,
  parse before checking byte limits, or let a special-file race block.
- Do not accept permissive JSON, extra fields, duplicate keys/paths, platform-
  native separators, digest aliases, algorithm negotiation, or caller-raised
  limits.
- Do not expose a `--repair`, `--write-report`, `--force`, `--follow-links`,
  `--fetch`, `--schema`, or `--simulator` path.
- Do not render the selected root, member paths, hashes, rejected content,
  exception text, traceback, environment, or argv in any format or log.
- Do not describe a green card as semantic validity, completeness, privacy,
  conformance, reproducibility, aggregate agreement, or scientific support.

## Non-goals and implementation boundaries

- No simulator installation, import, execution, qualification, or native
  conformance is performed.
- No RAES/environment-pack model, schema, validator, diagnostic envelope,
  exception hierarchy, capability, profile, fixture corpus, evidence type, or
  policy gate is added or replaced.
- No semantic artifact parsing, aggregate recomputation, leakage/privacy scan,
  source admission, provenance validation, task/run join, or conclusion is
  performed.
- No archive extraction, remote URI, network service, authentication system,
  database, cache, repaired bundle, persisted report, or background monitor is
  introduced.
- Verification is a point-in-time byte-integrity judgment over one selected
  regular-file tree; it is not a durable attestation and cannot prevent later
  mutation.
