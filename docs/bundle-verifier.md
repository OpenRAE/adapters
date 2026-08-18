# Offline bundle verifier

The base `raes-adapters` installation includes a simulator-independent command
for checking the byte integrity of an evidence bundle:

```shell
raes-adapters verify-bundle --bundle exported-evidence
```

The command is read-only and offline. It does not import a simulator, repair an
inventory, write a report, recompute an aggregate, or contact a network
service. The selected path is necessarily visible in the process argument
list, so do not put secrets in bundle directory names; the command itself never
echoes that path.

## What is verified

The selected root must be a real directory containing `inventory.json`. Each
inventory has exactly one `artifacts` array, and each entry has exactly these
fields:

```json
{
  "media_type": "application/json",
  "path": "run.json",
  "sha256": "3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7",
  "size_bytes": 4
}
```

Paths are normalized relative POSIX paths. A referenced file named
`inventory.json` is parsed as a nested inventory relative to its own directory.
Verification requires exact global closure: every declared file must exist and
match its size and lowercase SHA-256 digest, and every regular file other than
the root inventory must be declared exactly once.

The verifier rejects links, special files, mount escapes, unreadable members,
extra or missing files, malformed or duplicate JSON fields, traversal paths,
and mutation during enumeration or hashing. Containment is rooted in pinned
filesystem descriptors. On a platform without equivalent handle-relative,
no-follow, directory, and non-blocking primitives, verification fails closed
with `bundle.filesystem.unsupported`.

## Output formats

Terminal output is the default. JSON and Markdown are deterministic alternatives:

```shell
raes-adapters verify-bundle --bundle exported-evidence --format json
raes-adapters verify-bundle --bundle exported-evidence --format markdown
```

Every format reports only a stable status/code, bounded counts, the
`integrity-only` claim, and explicit disclaimers that semantic fidelity and
capture completeness were not assessed. Paths, member names, hashes, media
types, rejected values, file bytes, and exception details are never rendered.
The card is command presentation, not a RAES evidence model or a durable
attestation.

## Fixed limits

Limits are security constants and cannot be changed by flags or environment:

| Limit | Value |
| --- | ---: |
| Regular files, including inventories | 100,000 |
| Inventories | 100,000 |
| Inventory entries | 200,000 |
| Bytes hashed across unique paths | 4 GiB |
| Bytes in one non-inventory artifact | 500 KiB |
| Bytes in one inventory | 16 MiB |
| Relative path components | 32 |
| UTF-8 bytes in one relative path | 1,024 |

Directory traversal has a separate fixed work bound, so empty directories do
not consume the regular-file budget and cannot create unbounded work. Artifact
hashes are streamed in bounded chunks; the 4 GiB I/O ceiling is not a memory
allocation budget.

## Exit status

| Exit | Meaning |
| --- | --- |
| `0` | The exact byte-inventory closure was verified. |
| `2` | The command line was invalid. |
| `3` | The bundle was invalid, tampered, unreadable, unsupported, or over a fixed limit. |
| `70` | An unexpected internal defect occurred; no exception detail is exposed. |

A successful result is a point-in-time byte-integrity judgment. It does not
establish semantic validity, evidence completeness, privacy, conformance,
reproducibility, aggregate agreement, or scientific support. Backend-specific
commands remain responsible for those separately governed checks.
