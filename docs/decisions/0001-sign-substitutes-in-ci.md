# Sign Roguix substitutes in GitHub Actions; serve static files

## Context

Owner decisions of 2026-10-12: CI signs substitutes for
`https://substitutes.omaguix.org` with a **fresh** key generated off the VPS (on
the owner's Guix machine) and held only in environment secret
`SUBSTITUTE_SIGNING_KEY`. The old `roguix.frolow.dev` key is erased from the VPS
and GitHub. The public key is `modules/roguix/substitutes.omaguix.org.pub` in
omaguix-channel; try-omaguix adds it. Until then the workflow does not run
(pushes use `[skip ci]`).

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

### Omaguix URL cutover

The repositories are now `omaguix/omaguix`, `omaguix/omaguix-channel` and
`omaguix/try-omaguix`. The substitute hostname is renamed to
`substitutes.omaguix.org` with the same fresh key described above, not a further
key rotation. The channel coordinator owns and publishes
`modules/roguix/substitutes.omaguix.org.pub`; its exact file SHA256 is
`f59f581309d9270a1e8b12b9c73313ca74cb66143c7cf39535c0c251bc309881`.
This repository does not publish that key.

Guix module/package identifiers and store identities, the authentication
introduction/fingerprint/keyring, local workflow checkout path `roguix-channel`,
archive names, static layout/state and CLI contracts remain unchanged.
Manual signer authorization is not expanded. Rebuilds and profile P integration
are outside this URL-only cutover.

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
Write it mode 0600, confirm its public half equals `substitutes.omaguix.org.pub`,
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
containing **only the substitutes.omaguix.org key**; accept only `valid-signature`.
Do not use `valid-narinfo?` as the verification interface. Decompress each NAR
and compare its SHA256 and byte count with `NarHash`/`NarSize`.
Release the tree tarball and manifest/checksums; partition below 2 GiB per asset.
Record workflow/channel commits, pin, architecture and the **full** Roguix set
needed (including reused `vps-has.txt` items), not just the exported delta.

### VPS delivery, cutover and retention

The VPS continues pulling releases; CI needs no SSH credentials. Safely extract
into staging (reject traversal, links and special files), verify signatures,
hashes and manifests, and merge into `/var/lib/roguix-substitutes` under a lock.
Install NARs before narinfos with atomic renames. The VPS serves that root
statically as `https://substitutes.omaguix.org` (nginx: `/nix-cache-info`,
`/<hash>.narinfo`, the advertised `/nar/...` paths; roguix-vps owns the serving
side). No dynamic HTTP compression, directory listing, uploads or `guix publish`
fallback.

Cutover is clean: guests trust only the new key, with no dual-key release.
There is no backfill: once `substitutes.omaguix.org` serves, `roguix.frolow.dev`
is switched off and nothing it served is carried over.

Keep items referenced by the latest **N releases per architecture**; union full
manifests, delete the rest. Measure unique NAR sizes, reference coverage, staging
peak and OS/site headroom on the 48 GB VPS before choosing/recording N and budget.
Keep advertised URL variants. Stop pulls if staging cannot fit; remove redundant
download/store/cache copies only after verification. Older VMs may need builds
after pruning.

### Repository changes and order

1. **omaguix/omaguix:** amend `build-desktop.yml` for pinned actions/artifacts
   and the protected signing job; add a small publish/mirror/verification helper,
   update `scripts/vps-import` for static releases and retention manifests, and
   README/tests. Keep existing imports working until static delivery is tested.
2. **Owner:** remove required reviewers; configure main-only branch deployments,
   no tags; then store the fresh key in the secret.
   These are repository settings, not enforced by YAML alone.
3. **roguix-vps:** advance its gitlink/`scripts/mac/vps-install-import`; manage
   pulls, static directory, retention and nginx in live Debian config
   and `modules/roguix-vps/system.scm`. Serve statically, switch off
   `roguix.frolow.dev`, erase the old key/backups. Preserve TLS/personal-site vhosts.
4. **omaguix/try-omaguix:** adds `substitutes.omaguix.org.pub` and the new endpoint.

## Alternatives

VPS signing retains mixed-host risk. Moving the existing key to a secret under
`roguix.frolow.dev` with a backfill (earlier choice) was superseded by a fresh
key and endpoint. Custom/private-procedure signers add complexity.

## Consequences

Earlier theft remains valid: **Guix has no key revocation**. The old key is
erased, not revoked; guests stop trusting it.
VPS compromise can deny/replay downloads, not newly steal the key.
Anyone who can push to main or change its workflow, or a stolen owner session/
token, can get code signed. There is no human release gate. GitHub/runner
compromise and bad builder output remain risks. In an organization-owned repo,
the literal actor/owner comparison disables human manual signing; pushes still
sign automatically. Hashes/signatures are not reproducible-build proof or freshness/
availability guarantees. Bordeaux loss/pruning can force builds; personal-site
security and channel signing are outside scope.
