# CybORG/CAGE-2 Provisioner and manifest guardrails

GitHub issue #15 owns the first usable RAES boundary around the maintainer-
selected CybORG backend. The purpose is incremental: a researcher who uses
CybORG through RAES should retain more portable information about the scenario
and backend selection than a direct invocation retains, even before later
issues add action, observation, evaluation, and equivalence evidence.

## Authority and admission

The maintainer selected the pinned CAGE-2/CybORG profile, so the backend is
admitted. Qualification records source identity, installation mechanics,
known defects, and attainable claim strength. It does not decide whether an
adapter may exist.

The current packaging fact is narrower: the official CybORG 2.1 wheel omits
runtime data, while the qualified packaging-only fix has not been published as
an index artifact. Users can and do install CybORG from source. The adapter
therefore supports that documented source-install route and validates the
installed version and selected runtime-file digests. The empty optional extra
discloses an automatic-installation limitation; it is not an admission veto.

## Backend boundary

CybORG is the simulator backend. A RAES `RuntimeTarget` is only the RAES object
that groups the backend adapter's components and manifest. Issue #15 supplies
the Provisioner component:

- an admitted `ProvisioningPlan` enters the backend adapter;
- the adapter projects the complete desired state into a generated CybORG
  scenario and privately owns the resulting simulator;
- the RAES snapshot retains copied portable plan entries and the selected
  realization-envelope identity; and
- no native CybORG object or output crosses the portable boundary.

Issues #16–18 add logical stepping/action translation, participant episodes and
observations, and reward/evaluation projection. The issue #15 manifest must not
claim those components early.

## Honest partial reproducibility

The first useful record is intentionally modest. It identifies the admitted
RAES scenario descriptor, selected CybORG source profile, backend manifest, and
realization envelope. That is already more reproducible than an unrecorded
direct constructor call.

The native Scenario2 file is qualification evidence, not the adapter's runtime
scenario. Construction is a deterministic projection of admitted RAES
resources:

- each `network` compiled from a RAES switch becomes one CybORG subnet;
- each `node` compiled from a RAES VM becomes one or more CybORG hosts
  according to its admitted `count`;
- RAES infrastructure links become CybORG subnet memberships; and
- Linux and Windows OS-family requests select the pinned
  `linux_decoy_host` and `windows_user_host1` image definitions.

The projection uses the complete desired resource set, never a fixed native
scenario selected behind one descriptor. Two different admitted topologies
therefore produce different native scenario documents. Count expansion is
bounded normalization (`host` becomes `host-0`, `host-1`, ... when count is
greater than one). CybORG 2.1 allocates private CIDRs itself, so authored
network addresses are descriptor-substituted rather than falsely reported as
exact. Image selection is an explicit default/image substitution.

The realization envelope binds those transformations, the selected source
profile, the mapping version, and the configured seed into its configuration
digest. It marks resource allocation, content, accounts, feature bindings,
services, and ACL realization unsupported.
Requests for explicit images, OS versions, resource allocations, asset values,
runtime state, services, features, accounts, ACLs, or unattached hosts reject
before native construction rather than being silently dropped. Constructor
success is not action, observation, replay, scoring, or outcome-equivalence
evidence.

## Configuration and source checks

Target configuration is closed. The adapter validates the selected profile id,
source commit, simulator version, mapping-ledger resource, bounded seed,
realization-envelope identity, compiled resource shapes, link closure, native
name uniqueness, and supported semantic subset before native construction.

The default driver imports only the fixed `CybORG` package surface. It does not
accept an import path, caller-supplied native scenario path,
environment-selected revision, runtime download, subprocess, or secret. Before
import it verifies the complete Python source tree and every selected runtime
file—including the image catalogue and selected images—against qualification
digests. It then copies the package into a private runtime snapshot while
excluding installed bytecode and native import artifacts, verifies the copied
source and selected data again, and imports from that snapshot. Python therefore
executes the bytes whose identity was checked rather than an unverified cache.
The driver writes the generated scenario as a private canonical JSON document
accepted by CybORG's YAML loader, constructs synchronously, and deletes the
document immediately afterward.

CybORG 2.1 uses Python's process-global random generator while building native
subnets and addresses. Construction therefore runs under a backend-local lock,
seeds before the constructor when configured, repeats the seed before reset,
and restores the caller's global random state. An unseeded target is explicitly
identified as unseeded in the realization envelope.

## Atomic ownership and cleanup

CybORG is one aggregate in-process backend, not one native object per RAES plan
operation. The Provisioner interprets the complete desired state and performs
one prepare/replace transition under a lock.

- Validation completes before construction.
- `UNCHANGED` does not create another backend.
- A failed construction leaves the baseline snapshot unchanged.
- Replacement publishes the candidate only after old-state cleanup succeeds.
- A candidate whose compensation fails remains privately owned for retry.
- A failed old-state cleanup marks that backend unavailable; an unchanged apply
  cannot report it healthy and instead must complete cleanup and reconstruct the
  desired state.
- Mixed deletes and updates rebuild from the complete desired state; removed
  resources cannot survive through a stale aggregate descriptor.
- Delete removes the aggregate backend only when the desired state is empty.
- Repeated cleanup is harmless and retries previously unconfirmed cleanup.

Portable snapshots, results, receipts, diagnostics, stores, and logs may
contain only published RAES values and bounded adapter messages. Native
handles, ids, tuples, arrays, object representations, paths, logs, exception
text, and tracebacks remain process-private.

## Manifest evidence

The backend uses published RAES `BackendManifest`,
`BackendRealizationEnvelopeModel`, `ProvisionerCapabilities`,
`RealizationSupportDeclaration`, and `ConceptBinding` types. It publishes
through `backend_manifest_v2_model`/`backend_manifest_payload`; there is no
parallel schema or serializer.

The manifest is provisioning-only and names only contract versions exercised
by the target/control-plane path. Tests validate the rendered
`backend-manifest-v2`, SDL-to-plan-to-native differential projection, count and
link preservation, every configuration rejection, fail-closed lossy facts,
seed-bound identity, temporary-document deletion, snapshot portability,
construction/cleanup lifecycle, failed compensation, and source-installed
default-driver smoke. Stronger claims arrive only with their executable
evidence.
