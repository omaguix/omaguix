# roguix

CI for the Roguix desktop's packages: GitHub Actions builds the reference
system for aarch64 and x86_64 and publishes the package store items no
other configured server has, for `https://roguix.frolow.dev` to serve.

| Repository | What it is |
| --- | --- |
| [roguixos/roguix](https://github.com/roguixos/roguix) | this one: the desktop feed's CI |
| [roguixos/try-roguix](https://github.com/roguixos/try-roguix) | the macOS app and the Roguix desktop guest |
| [roguixos/roguix-channel](https://github.com/roguixos/roguix-channel) | the desktop's channel, generated from try-roguix |

## Layout

| Path | What it is |
| --- | --- |
| `.github/workflows/build-desktop.yml` | builds the authenticated roguix-channel's reference system on native ARM and x86_64 runners |
| `scripts/reference-system-licenses.scm` | licences of the reference system's packages, including service dependencies; requires `GUIX_SYSTEM` from the caller |
| `scripts/desktop-split` | checks licences and splits the closure of the reference system's package outputs |
| `scripts/ci-install-guix` | installs Guix on the runner |
| `modules/roguix/builder.pub` | CI's archive signing key; the secret half is the `BUILDER_SIGNING_KEY` Actions secret |
| `scripts/vps-import` | legacy archive import, or opt-in static release installation |
| `scripts/static-substitutes` | shell orchestration of pinned Guix publishing and mirroring |
| `scripts/static-tree` | tarballs, delivery, installation and retention |
| `scripts/verify-substitutes.scm` | single-key ACL signature and keypair verification |
| `tests/` | secret-free fixtures and optional throwaway-key Guix integration |

This repository has no packages of its own: the desktop's modules are
published in roguix-channel, generated from try-roguix.

## Guix on the runners

The workflow installs Guix with `scripts/ci-install-guix`: the Guix
1.5.0 binary tarball selected by `uname -m` (`x86_64` or `aarch64`; other
architectures fail), from `ftpmirror.gnu.org`, or, if that fails, the copy
in this repository's `guix-binary-1.5.0` release. Each architecture has a
pinned sha256, verified with Efraim Flashner's release signing key
`A28BF40C3E551372662D14F741AAE7DCCA3D8351`. The script starts a root
guix-daemon and authorizes bordeaux's and ci's keys; it never runs
`guix pull` (the jobs use `guix time-machine`). To update: verify both new
tarballs' `.sig` files from `ftp.gnu.org` with `gpg --verify` against the
release signing key, change `VERSION` and both `SHA256` values in the
script, and upload both tarballs to a release `guix-binary-VERSION` here.

## The reference-system feeds

On a push to `main` touching its own inputs, `build-desktop.yml` resolves
roguix-channel's `main` head with
`git ls-remote https://github.com/roguixos/roguix-channel main` once for both
architectures. A `workflow_dispatch` instead requires `channel_commit`,
validated as exactly 40 lowercase hexadecimal characters. The run name
contains that input; push runs say `main (resolved at run time)` because
GitHub evaluates the run name before jobs run. The resolver records the
exact commit in its job summary. The workflow builds a two-entry matrix:

| System | Native runner | Release prefix |
| --- | --- | --- |
| `aarch64-linux` | `ubuntu-24.04-arm` | `aarch64-desktop` |
| `x86_64-linux` | `ubuntu-24.04` | `x86_64-desktop` |

Each job has a 350-minute limit and its own architecture-specific
concurrency group. Matrix fail-fast is disabled, so one architecture's
failure does not cancel the other.

Both jobs check out [roguix-channel](https://github.com/roguixos/roguix-channel)
at the resolved commit with full history and fetch its `keyring` branch.
After installing Guix, each authenticates the channel from its introduction
before reading its Guix pin or authorizing its substitute key:

```sh
guix git authenticate --keyring=origin/keyring --end="$CHANNEL_COMMIT" \
  bcc938512706d19de86dd8c6f50853fa80b063b8 \
  '7D1A 8B40 0C26 0998 097F  63E5 28B8 3B16 11FA 815E'
```

Authentication failure stops the job. The channel's `.guix-channel` selects
`modules`; the jobs read `modules/roguix/guix-commit` (currently
`7e74121a40a8308166e328a23647cf6f3768e6c8`) and authorize
`modules/roguix/roguix.frolow.dev.pub` from that authenticated checkout.
They build the channel-defined `(@ (roguix system) %roguix-reference-system)`
with `ROGUIX_MODULES` set to the checkout's absolute `modules` path, the
matrix's `--system` and `--no-grafts`. This is the entire reference system
with default host settings and no extra packages, not a machine's
hand-written list. Only bordeaux and roguix.frolow.dev are configured
substitute servers.

New `x86_64-desktop` releases now come from this reference system, including
its x86_64 binary releases, and serve x86_64 machines such as Intel
MacBooks. Earlier releases under the same prefix came from a hand-written
package list; they remain historical releases, not reference-system builds.
The `aarch64-desktop` feed serves Apple Silicon VM guests.

Each job computes the system's closure with `guix gc -R` and runs
`scripts/desktop-split`. It takes the package outputs the licence collector
lists that are in that closure, and splits their `guix gc -R` closure, so
the files generated for the one reference system (system, etc, udev rules,
pam.d, shepherd services and similar) are left out unless a package output
references them: bordeaux items go to `vps-fetch.txt`, items already
served by roguix.frolow.dev go to `vps-has.txt`, and the rest to
`publish.txt`. Narinfo answers must be 200 or 404; licence and Broadcom
`wl` checks cover `publish.txt`. The licence collector uses the matrix's
`GUIX_SYSTEM` and observes package lowering throughout the system,
including services, and checks their package closures, not just the system
profile. The splitter fails on unfree or unknown licences, Broadcom `wl`,
ambiguous server answers, per-machine items to publish that are no package
output, or an item to publish with a reference (`guix gc --references`) in
none of the three lists, which the VPS could not import.

On `main`, nonempty `publish.txt` is exported with `BUILDER_SIGNING_KEY` as
`roguix-PREFIX.nar.zst` and uploaded with split lists as `signing-PREFIX`.
A separate protected job releases the compatibility archive and a verified
static substitute tree (below), tagged `PREFIX-DATE-COMMIT-RUNIDATTEMPT`.
Only that job has `contents: write`. No new release is made when `publish.txt`
is empty, preserving the legacy importer's latest nonempty archive. Grafts
are not substitutable, so only ungrafted items are published.

The build also uploads diagnostics as `split-PREFIX` with `channel-commit.txt`,
`guix-commit.txt`, `system.txt`, `release-tag.txt`, `publish.txt`,
`vps-fetch.txt`, `vps-has.txt`, and `package-closure.txt`. The old release tag
marker stays empty; the signing job records the actual tag in its manifest.
Upload uses
`always()` gated on a successful split: it includes empty publish lists
when no release is needed and preserves completed split results even if
export or release fails, but does not present an incomplete split as a
usable artifact. All workflow actions are pinned to full commit SHAs.

## Automatic signing and static substitutes

See [decision 0001](docs/decisions/0001-sign-substitutes-in-ci.md).
Configure `substitute-signing` with **no required reviewers** and a deployment
policy allowing only branch `main`, with no tag policies. Signing is automatic
on main pushes. Manual signing requires `github.actor == github.repository_owner`;
in this organization-owned repository that literal check blocks human manual
dispatch. Do not silently broaden it to organization members.
These environment settings must be applied on GitHub; YAML cannot set them.

Move the existing VPS key through a trusted machine into environment secret
`SUBSTITUTE_SIGNING_KEY`, after configuring the policy. Guests and the HTTPS
endpoint remain unchanged. Earlier theft remains valid (Guix has no revocation).
Anyone able to push main/change its workflow, or a stolen owner session/token,
can get code signed; there is no human release gate.

The workflow authenticates the channel, validates artifact lists, authorizes
the builder key, fetches references, and imports the signed export on a fresh
runner. Only the signing step receives the VM-trusted secret. The remaining parts:
- `static-substitutes`: shell orchestration of pinned localhost `guix publish`,
  HTTP baking/mirroring for `publish.txt`, secret cleanup, and packing.
- `verify-substitutes.scm`: the **only** Guix protocol verifier; public-half
  challenge, mandatory signed fields, single-key `signature-case`, safe URL
  mapping, and Guix decompression/hash ports for uncompressed NarHash/NarSize.
- `static-tree`: inherited loopback socket, ordinary tarballs/checksums,
  safe staging/extraction, locked atomic installation, and manifest retention.
- `vps-import`: opt-in static delivery; the legacy archive path is unchanged.

Static releases contain only new items, not redundant snapshots. The manifest
records the **full** Roguix set (`publish.txt` plus `vps-has.txt`), architecture
and commits. Bordeaux references remain external. Assets are `manifest.json`,
`SHA256SUMS` and independent `tree-0000.tar`, ... below 2 GB each, without a
custom chunk codec or extra NAR compression. A single file too large for a
tarball fails publication rather than exceeding GitHub's limit. Legacy archive
assets remain; the draft is published only after all uploads complete.

Install the helper files alongside `vps-import`; Python 3.11+ and Guix are
required. Guix supplies decompression, including the VPS's existing zstd format.

```sh
scripts/vps-import --static-dir /var/lib/roguix-substitutes \
  --key /etc/guix/signing-key.pub -p x86_64-desktop
# Optional pruning, only after measuring space and completing the backfill:
scripts/vps-import --static-dir /var/lib/roguix-substitutes \
  --key /etc/guix/signing-key.pub --keep "$MEASURED_N"
scripts/static-tree install --release downloaded-release \
  --directory /var/lib/roguix-substitutes --key /etc/guix/signing-key.pub
```

The installer verifies checksums and all incoming narinfos/NARs before moving
NARs, then narinfos. State/lock live in `.roguix/`; nginx must deny hidden paths.
Without `--keep`, nothing is deleted. With N, pull the latest N release deltas
per architecture, retain their full-set union and all existing URL variants,
and verify reused/backfilled items before deleting anything. Missing items
block pruning: this is not a historical snapshot recovery service. Local
`install --keep N` uses installed manifests. Measure the 48 GB VPS's staging
peak and OS/site headroom before choosing N; older clients may need builds.
Nginx fallback, backfill and removing publish/the VPS key belong to roguix-vps.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
shellcheck scripts/static-substitutes scripts/vps-import scripts/desktop-split
ruff check --no-cache scripts/static-tree tests/test_static_substitutes.py
```

Fixtures cover archive integrity, path/link safety, installation, retention,
verifier rejection and workflow scope; they do not emulate Guix cryptography.
When Guix is available the integration test creates test-local throwaway keys,
bakes tiny regular/compressed items, installs them and checks tampering/wrong
keys. Otherwise it is explicitly skipped. Real GitHub environment/dispatch,
signing, delivery and VPS cutover still need end-to-end checks.

## Importing on the VPS

The VPS pulls the newest x86_64 release with `scripts/vps-import` (the
`x86_64-desktop` default), or the ARM feed with
`scripts/vps-import -p aarch64-desktop`. An explicit release tag also
selects its feed. Both feeds accept an absent `vps-fetch.txt` as an empty
set: GitHub rejects empty assets. Other HTTP errors still fail.

The importer fetches bordeaux references before importing the signed
archive, then bakes guix publish's cache one item at a time.
`guix archive --import` and bordeaux substitution by explicit store path
do not depend on the host architecture; the x86_64 VPS does not execute
the aarch64 binaries. The coordinator's CI/import run remains the real
end-to-end test. CI has no access to the VPS.

The importing daemon must trust the builder key
(`modules/roguix/builder.pub`): on Guix System through `authorized-keys` in
`guix-service-type` (`guix archive --authorize` lasts only until the next
reconfigure), elsewhere with `guix archive --authorize`.

The builder key signs what the VPS imports and republishes under its own
key, which Roguix VMs trust: keep `BUILDER_SIGNING_KEY` to workflows on
`main`. Once roguix.frolow.dev serves an earlier export for the same pin,
the jobs can substitute those items instead of rebuilding them. The protected
job also signs static substitutes directly with the existing VM-trusted key;
only its signing step receives that key.
