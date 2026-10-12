# Sign Roguix substitutes in GitHub Actions; serve static files

## Context

Owner decision `d-zuer37ri`: move the existing VM-trusted publish key from the
mixed-use VPS into a GitHub environment secret via a trusted machine. Keep
`https://roguix.frolow.dev` and its public key; no VM/image changes, new endpoint,
fresh key or legacy tree. Today CI exports with the builder key; VPS re-signs.

Protocol verified at Guix pin `7e74121a40a8308166e328a23647cf6f3768e6c8`:
- [guix/scripts/publish.scm](https://github.com/guix-mirror/guix/blob/7e74121a40a8308166e328a23647cf6f3768e6c8/guix/scripts/publish.scm): `%nix-cache-info`, `narinfo-string`, `signed-string`, `bake-narinfo+nar`.
- [guix/narinfo.scm](https://github.com/guix-mirror/guix/blob/7e74121a40a8308166e328a23647cf6f3768e6c8/guix/narinfo.scm): `read-narinfo`, `narinfo-signature->canonical-sexp`, `narinfo-sha256`.
- [guix/pki.scm](https://github.com/guix-mirror/guix/blob/7e74121a40a8308166e328a23647cf6f3768e6c8/guix/pki.scm): `signature-sexp`, `signature-case`.
- [guix/scripts/substitute.scm](https://github.com/guix-mirror/guix/blob/7e74121a40a8308166e328a23647cf6f3768e6c8/guix/scripts/substitute.scm): `process-substitution`, `guix-substitute` (NAR hash comparison).

`nix-cache-info`: `StoreDir: /gnu/store`, `WantMassQuery: 0`, `Priority: 100`.
`<store-hash>.narinfo`: `StorePath`, `NarHash: sha256:<Nix-base32 hash>`,
`NarSize`, basename `References`, optional basename `Deriver`, then
`Signature: 1;<hostname>;<base64 S-expression>`. It authenticates SHA256 of the
exact UTF-8 prefix, including its final newline, with signed data, signature
value and public key embedded. The hostname is not the trust anchor.
`StorePath`, `NarHash`, `References` must be signed; subsequent `URL`,
`Compression`, `FileSize` are not. Publish omits `FileHash`/`System`; preserve
its bytes, not Nix `Sig:` format. `NarHash` hashes the **uncompressed single-item
NAR**, not compressed bytes or an export bundle. Relative URLs resolve at root.

## Decision

### CI signing and release

Keep native authenticated builds, builder-signed exports and `desktop-split`
licence/per-machine checks. Exclude bordeaux-served items; references may point
there because guests use both servers. Ambiguous responses fail. Artifact lists:
`publish.txt`, `vps-fetch.txt`, `vps-has.txt` and the full package closure.

Add a separate signing job on a fresh runner with
`environment: substitute-signing`. Owner amendment: sign automatically on main,
with **no required reviewers and no per-release approval**. Its deployment branch
policy permits only the `main` branch, not tags. The signing job also checks the
main ref; manual `workflow_dispatch` signing requires
`github.actor == github.repository_owner`. Push signing has no actor restriction.
Checkout and artifact download actions are allowed, pinned to full commit SHAs.
Use this run's export/lists and reviewed workflow/pin, not artifact scripts.
Only this job gets `contents: write`; other token permissions stay minimal.

Before exposing the production key, install pinned Guix, authorize
`modules/roguix/builder.pub`, fetch required reference paths from bordeaux and
Roguix, and `guix archive --import` the builder-signed export into the fresh
runner store. This works across architectures; do not execute imported code.
Only the signing step receives environment secret `SUBSTITUTE_SIGNING_KEY`.
Write it mode 0600, confirm its public half equals the existing guest key,
and run pinned `guix publish` bound to localhost with explicit key files,
`--cache`, `--cache-bypass-threshold=0`, and `--compression=gzip:3`.
For every `publish.txt` item request its narinfo, waiting with a bounded poll
for the publisher's baked response, then fetch each advertised NAR URL.
Mirror exact bytes into `tree/<hash>.narinfo`, `tree/nix-cache-info` and
`tree/nar/gzip/<store-basename>` (or `tree/nar/<store-basename>` for `none`).
Use compatible gzip; honor advertised `none` for already-compressed items.
Stop publish/remove secrets on exit. No private procedures, disposable key,
signature stripping or custom signer.

Verification parses narinfos, computes SHA256 of the exact pre-signature bytes
with required signed fields present, and uses `signature-case` against an ACL
containing **only the VM-trusted key**; accept only `valid-signature`.
Do not use `valid-narinfo?` as the verification interface. Decompress each NAR
and compare its SHA256 and byte count with `NarHash`/`NarSize`.
Release the tree tarball and manifest/checksums; partition below 2 GiB per asset.
Record workflow/channel commits, pin, architecture and the **full** Roguix set
needed (including reused `vps-has.txt` items), not just the exported delta.

### VPS delivery, transition and retention

The VPS continues pulling releases; CI needs no SSH credentials. Safely extract
into staging (reject traversal, links and special files), verify signatures,
hashes and manifests, and merge into `/var/lib/roguix-substitutes` under a lock.
Install NARs before narinfos with atomic renames. Nginx serves the same root:
`/nix-cache-info`, `/<hash>.narinfo`, and the advertised `/nar/...` paths.
During transition, missing static narinfos **and NARs** fall back to local
publish on 8181. No dynamic HTTP compression, directory listing or uploads.

Before removing the VPS key, inventory/bake currently served items with its
publish and mirror exact narinfos/all NAR URLs into the same tree, including
older/manual feeds. Verify coverage and clean-store downloads on both
architectures with the existing VM ACL; stop publish, remove fallback, erase
the key from VPS/backups and transfer-machine temporary storage. VMs retain
the same endpoint/key throughout.

Keep items referenced by the latest **N releases per architecture**; union full
manifests, delete the rest. Measure unique NAR sizes, reference coverage, staging
peak and OS/site headroom on the 48 GB VPS before choosing/recording N and budget.
Keep advertised URL variants. Stop pulls if staging cannot fit; remove redundant
download/store/cache copies only after verification. Older VMs may need builds
after pruning; backfilled items follow this policy, not eternal retention.

### Repository changes and order

1. **roguixos/roguix:** amend `build-desktop.yml` for pinned actions/artifacts
   and the protected signing job; add a small publish/mirror/verification helper,
   update `scripts/vps-import` for static releases and retention manifests, and
   README/tests. Keep existing imports working until static delivery is tested.
2. **Owner:** remove required reviewers; configure main-only branch deployments,
   no tags; then transfer the existing key via a trusted machine into the secret.
   These are repository settings, not enforced by YAML alone.
3. **roguix-vps:** advance its gitlink/`scripts/mac/vps-install-import`; manage
   pulls, static directory, retention and nginx fallback in live Debian config
   and `modules/roguix-vps/system.scm`. Backfill, verify, stop publish, remove
   fallback, erase key/backups. Preserve TLS/personal-site vhosts.
4. **try-roguix:** unchanged, including images and the existing public key.

## Alternatives

VPS signing retains mixed-host risk; fresh keys require guest trust rollout.
The owner chose continuity. Custom/private-procedure signers add complexity.

## Consequences

Earlier theft remains valid: **Guix has no key revocation**. Moving/deleting the
key cannot invalidate stolen copies; replacement would require VM trust updates.
Post-removal VPS compromise can deny/replay downloads, not newly steal the key.
Anyone who can push to main or change its workflow, or a stolen owner session/
token, can get code signed. There is no human release gate. GitHub/runner
compromise and bad builder output remain risks. In an organization-owned repo,
the literal actor/owner comparison disables human manual signing; pushes still
sign automatically. Hashes/signatures are not reproducible-build proof or freshness/
availability guarantees. Bordeaux loss/pruning can force builds; personal-site
security and channel signing are outside scope.
