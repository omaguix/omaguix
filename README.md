# roguix

CI for the Roguix desktop's packages: GitHub Actions builds the reference
system for aarch64 and x86_64 and publishes the package store items no
other configured server has, for `https://substitutes.omaguix.org` to serve.

| Repository | What it is |
| --- | --- |
| [omaguix/omaguix](https://github.com/omaguix/omaguix) | this one: the desktop feed's CI |
| [omaguix/try-omaguix](https://github.com/omaguix/try-omaguix) | the macOS app and the Roguix desktop guest |
| [omaguix/omaguix-channel](https://github.com/omaguix/omaguix-channel) | the desktop's channel, generated from try-omaguix |

## Layout

| Path | What it is |
| --- | --- |
| `.github/workflows/build-desktop.yml` | builds the authenticated omaguix-channel's reference system on native ARM and x86_64 runners |
| `scripts/reference-system-licenses.scm` | licences of the reference system's packages, including service dependencies; requires `GUIX_SYSTEM` from the caller |
| `scripts/desktop-split` | checks licences and splits the closure of the reference system's package outputs |
| `scripts/ci-install-guix` | installs Guix on the runner |
| `scripts/ci-guix-daemon` | serves the runner's store with a given Guix's guix-daemon, socket-activated |
| `scripts/guix-base` | the commit G' is made on: the pin, or the channel's Guix fork commit on top of it |
| `modules/roguix/builder.pub` | CI's archive signing key; the secret half is the `BUILDER_SIGNING_KEY` Actions secret |
| `scripts/vps-import` | legacy archive import, or opt-in static release installation |
| `scripts/static-substitutes` | shell orchestration of pinned Guix publishing and mirroring |
| `scripts/static-tree` | tarballs, delivery, installation and retention |
| `scripts/verify-substitutes.scm` | single-key ACL signature and keypair verification |
| `tests/` | secret-free fixtures and optional throwaway-key Guix integration |

This repository has no packages of its own: the desktop's modules are
published in omaguix-channel, generated from try-omaguix.

## Guix on the runners

The workflow installs Guix with `scripts/ci-install-guix`: the Guix
1.5.0 binary tarball selected by `uname -m` (`x86_64` or `aarch64`; other
architectures fail), from `ftpmirror.gnu.org`, or, if that fails, the copy
in this repository's `guix-binary-1.5.0` release. Each architecture has a
pinned sha256, verified with Efraim Flashner's release signing key
`A28BF40C3E551372662D14F741AAE7DCCA3D8351`. The script starts a root
guix-daemon through `scripts/ci-guix-daemon`, socket-activated, and authorizes bordeaux's and ci's keys; it never runs
`guix pull` itself. To update: verify both new
tarballs' `.sig` files from `ftp.gnu.org` with `gpg --verify` against the
release signing key, change `VERSION` and both `SHA256` values in the
script, and upload both tarballs to a release `guix-binary-VERSION` here.

## The reference-system feeds

On a push to `main` touching its own inputs, `build-desktop.yml` resolves
omaguix-channel's `main` head with
`git ls-remote https://github.com/omaguix/omaguix-channel main` once for both
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

Both jobs check out [omaguix-channel](https://github.com/omaguix/omaguix-channel)
at the resolved commit with full history and fetch its `keyring` branch.
After installing Guix, each authenticates the channel from its introduction
before reading its Guix pin or authorizing its substitute key:

```sh
guix git authenticate --keyring=origin/keyring --end="$CHANNEL_COMMIT" \
  bcc938512706d19de86dd8c6f50853fa80b063b8 \
  '7D1A 8B40 0C26 0998 097F  63E5 28B8 3B16 11FA 815E'
```

Authentication failure stops the job. The channel's `.guix-channel` selects
`modules`; the jobs read `modules/omaguix/guix-commit` (currently
`7e74121a40a8308166e328a23647cf6f3768e6c8`) and authorize
`modules/omaguix/substitutes.omaguix.org.pub` from that authenticated checkout.

A `guix-profile` job per architecture makes the Guix the release is built
with (try-omaguix `docs/decisions/0007-move-vms-across-guix-pins.md`): it
clones Guix, authenticates its history up to that commit G with Guix's own
channel introduction, commits G plus the channel's
`modules/omaguix/guix-skip-forward-check.patch` as G' with
`scripts/guix-patched-commit` (a fixed identity and G's date, so both
architectures make the same G'), pulls G' into a fresh profile P (with
authentication off for that local Guix clone only), checks that
`P/bin/guix describe` names G', and hands P's exported closure to the
build job. While the channel's `modules/omaguix/guix-fork` names a
commit F of a Guix fork (`URL COMMIT`, for a fix not yet in Guix),
`scripts/guix-base` fetches F, checks that its only parent is G, and G' is
F plus the patch instead; F is not authenticated by Guix's introduction,
the signed channel commit that names it is. The pull trusts
substitutes.omaguix.org's key from the authenticated channel as well as
bordeaux's and ci's: bordeaux has no substitutes for P's `(guix self)`
nodes once the fork patches a core module, so a release whose G' did not
change substitutes the previous release's P instead of compiling it, and
whatever no server has, such as most of a new G', is built in the job
(the owner, 2026-10-27). The build job imports P,
switches the runner's daemon to P's `guix-daemon` with
`scripts/ci-guix-daemon`, so that daemon builtins such as
builtin:git-download run P's Guix rather than the tarball's, and builds the channel-defined
`(@ (omaguix system) %omaguix-reference-system)` with `P/bin/guix`, so P is
by construction the Guix that built the release; with `ROGUIX_MODULES` set to the checkout's absolute `modules` path, the
matrix's `--system` and `--no-grafts`. This is the entire reference system
with default host settings and no extra packages, not a machine's
hand-written list. Only bordeaux and substitutes.omaguix.org are configured
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
served by substitutes.omaguix.org go to `vps-has.txt`, and the rest to
`publish.txt`. Narinfo answers must be 200 or 404; licence and Broadcom
`wl` checks cover `publish.txt`. The licence collector uses the matrix's
`GUIX_SYSTEM` and observes package lowering throughout the system,
including services, and checks their package closures, not just the system
profile. The splitter fails on unfree or unknown licences, Broadcom `wl`,
ambiguous server answers, per-machine items to publish that are no package
output and not in the closure of P (passed with `--guix-profile`; its
closure joins the split like a package's and is made from G' alone, before
the system), or an item to publish with a reference (`guix gc --references`) in
none of the three lists, which the VPS could not import.

On `main`, nonempty `publish.txt` is exported with `BUILDER_SIGNING_KEY` as
`roguix-PREFIX.nar.zst` and uploaded with split lists as `signing-PREFIX`.
A separate protected job releases the compatibility archive and a verified
static substitute tree (below), tagged `PREFIX-DATE-COMMIT-RUNIDATTEMPT`.
Only that job has `contents: write`. No new release is made when `publish.txt`
is empty, preserving the legacy importer's latest nonempty archive. Grafts
are not substitutable, so only ungrafted items are published.

The build also uploads `split-PREFIX`, which try-omaguix's `release.py`
reads, with `channel-commit.txt`, `guix-commit.txt`, `system.txt`,
`release-tag.txt` (the tag when `publish.txt` is nonempty, else empty),
`guix-profile.txt` (P), `guix-patched-commit.txt` (G'),
`guix-patch-sha256.txt`, `publish.txt`, `vps-fetch.txt`, `vps-has.txt`, and
`package-closure.txt`. The signing job takes the tag from the split and
checks it, P's place in the package closure, G' and the patch's SHA-256
before signing anything. Upload uses
`always()` gated on a successful split: it includes empty publish lists
when no release is needed and preserves completed split results even if
export or release fails, but does not present an incomplete split as a
usable artifact. All workflow actions are pinned to full commit SHAs.

## Automatic signing and static substitutes

See [decision 0001](docs/decisions/0001-sign-substitutes-in-ci.md).
The current replacement signing public file's SHA256 is
`5e9b4547f9a8409a42e658276deb6e3f4502f6715681a9617f8b105ea73b4f2a`;
the channel coordinator owns and publishes it, not this repository.
It supersedes the original fresh key (SHA256
`f59f581309d9270a1e8b12b9c73313ca74cb66143c7cf39535c0c251bc309881`,
AA89); neither that key nor the old VPS key is trusted.
Root generated the replacement locally using Guix libgcrypt parameters;
native key test/sign/verify succeeded, and `SUBSTITUTE_SIGNING_KEY` was replaced
from memory at `2026-10-14T12:58:50Z`. No private file or MacBook access was used.
Keep CI disabled (pushes use `[skip ci]`) until the authenticated channel
publishes the current public key and current-key readiness is confirmed.
An empty valid HTTPS substitute tree is permitted for bootstrap.
Guix module/package identifiers and store identities are unchanged, as are the
channel authentication introduction, fingerprint and keyring. The local workflow
checkout remains `roguix-channel`; archive names, static layout/state and CLI
contracts remain unchanged. No rebuild or profile P integration is part of this
URL cutover.

Configure `substitute-signing` with **no required reviewers** and a deployment
policy allowing only branch `main`, with no tag policies. Signing is automatic
on main pushes. Manual signing requires both `github.actor` and
`github.triggering_actor` to be the maintainer's account, `rofrol`: in this
organization-owned repository `github.repository_owner` is the organization,
which never dispatches, and a re-run by another member must not sign. Do not
broaden it to organization members.
These environment settings must be applied on GitHub; YAML cannot set them.

Keep the current replacement key generated off the VPS only in environment
secret `SUBSTITUTE_SIGNING_KEY`, under the configured policy; do not generate
another key for the hostname rename. Its public half remains
`modules/omaguix/substitutes.omaguix.org.pub` in the authenticated channel;
guests trust only that current key. Earlier theft remains valid (Guix has no revocation).
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
# Optional pruning, only after measuring space:
scripts/vps-import --static-dir /var/lib/roguix-substitutes \
  --key /etc/guix/signing-key.pub --keep "$MEASURED_N"
scripts/static-tree install --release downloaded-release \
  --directory /var/lib/roguix-substitutes --key /etc/guix/signing-key.pub
```

The installer verifies checksums and all incoming narinfos/NARs before moving
NARs, then narinfos. State/lock live in `.roguix/`; nginx must deny hidden paths.
Without `--keep`, nothing is deleted. With N, pull the latest N release deltas
per architecture, retain their full-set union and all existing URL variants,
and verify reused items before deleting anything. Missing items
block pruning: this is not a historical snapshot recovery service. Local
`install --keep N` uses installed manifests. Measure the 48 GB VPS's staging
peak and OS/site headroom before choosing N; older clients may need builds.
Nginx serving belongs to roguix-vps.

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
`main`. Once substitutes.omaguix.org serves an earlier export for the same pin,
the jobs can substitute those items instead of rebuilding them. The protected
job also signs static substitutes directly with the fresh substitutes.omaguix.org key;
only its signing step receives that key.
