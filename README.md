# roguix

CI for the Roguix desktop's packages: GitHub Actions builds them and
publishes the store items no other server has, for
`https://roguix.frolow.dev` to serve.

| Repository | What it is |
| --- | --- |
| [roguixos/roguix](https://github.com/roguixos/roguix) | this one: the desktop feed's CI |
| [roguixos/try-roguix](https://github.com/roguixos/try-roguix) | the macOS app and the Roguix desktop guest |
| [roguixos/roguix-channel](https://github.com/roguixos/roguix-channel) | the desktop's channel, generated from try-roguix |

## Layout

| Path | What it is |
| --- | --- |
| `channels-desktop.scm` | the Roguix desktop's Guix and nonguix commits |
| `manifests/x86_64-desktop.scm` | what CI builds for the Roguix desktop on x86_64 |
| `.github/workflows/build-aarch64-desktop.yml` | builds try-roguix's reference system on a native ARM runner |
| `scripts/reference-system-licenses.scm` | licences of the reference system's packages, including service dependencies |
| `scripts/desktop-licenses.scm`, `scripts/desktop-split` | the x86_64 licence check and shared closure split |
| `scripts/ci-install-guix` | installs Guix on the runner |
| `modules/roguix/builder.pub` | CI's archive signing key; the secret half is the `BUILDER_SIGNING_KEY` Actions secret |
| `keys/substitutes.nonguix.org.pub` | nonguix's substitute key |
| `scripts/vps-import` | on the VPS: import CI's newest release into guix publish |

This repository has no packages of its own: the desktop's modules live in
try-roguix.

## Guix on the runners

The workflows install Guix with `scripts/ci-install-guix`: the Guix
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

## The aarch64 reference-system feed

Roguix users run Apple Silicon VM guests. On a push to `main` touching its
own inputs, or `workflow_dispatch`, `build-aarch64-desktop.yml` runs on
GitHub's native `ubuntu-24.04-arm` runner with a 350-minute limit. It checks
out [try-roguix at 85f1fdc56b75a0bb72e14b3579f86bc90c483401](https://github.com/roguixos/try-roguix/commit/85f1fdc56b75a0bb72e14b3579f86bc90c483401),
reads `guest/guix/modules/roguix/guix-commit` (currently
`7e74121a40a8308166e328a23647cf6f3768e6c8`), and builds the channel-defined
`(@ (roguix system) %roguix-reference-system)` with an absolute module load
path, `--system=aarch64-linux` and `--no-grafts`. This is the entire
reference system with default host settings and no extra packages, not a
machine's hand-written list. No nonguix channel, key or server is used.

The job trusts and substitutes from bordeaux and roguix.frolow.dev. It
computes the closure with `guix gc -R` and reuses `scripts/desktop-split
--reference-system`: bordeaux items go to `vps-fetch.txt`, items already
served by roguix.frolow.dev go to `vps-has.txt`, and the rest to
`publish.txt`. The splitter logs generated system outputs it drops in
`dropped-system.txt`; its comment lists the name patterns (system, etc,
boot, activation/shepherd files, system profile and similar). Package
inputs remain in the closure. Narinfo answers must be 200 or 404; licence
and Broadcom `wl` checks still cover the original closure. The licence
collector observes package lowering throughout the system, including
services, and checks their package closures, not just the system profile.

On `main`, nonempty `publish.txt` is exported and signed with
`BUILDER_SIGNING_KEY` as `roguix-aarch64-desktop.nar.zst`, then released as
`aarch64-desktop-DATE-COMMIT-ATTEMPT` with `publish.txt`, `outputs.txt` and
nonempty `vps-fetch.txt`/`vps-has.txt`. No release is made when no package
items need publishing. Grafts are not substitutable, so only ungrafted
items are published, as in the x86_64 job.

On the x86_64 VPS, run `scripts/vps-import -p aarch64-desktop` (or give an
explicit release tag). It accepts an absent `vps-fetch.txt` as an empty
set for this feed. `guix archive --import` and bordeaux substitution by
explicit store path do not depend on the host architecture; the importer
does not execute the aarch64 binaries. No contradictory architecture
restriction was found in this import path; the coordinator's CI/import
run remains the real end-to-end test.

## The existing x86_64 desktop feed

The desktop (try-roguix's Roguix modules) runs Guix 7e74121a with nonguix
c0192e90 (`channels-desktop.scm`); every store path depends on that pin.
On a push to `main` touching its files,
`.github/workflows/build-x86_64-desktop.yml` checks out
[roguixos/try-roguix](https://github.com/roguixos/try-roguix) at the commit it
pins (`TRY_ROGUIX_COMMIT`; roguixos/roguix-channel lags behind it), builds
the 16 packages of `manifests/x86_64-desktop.scm` without grafts (grafts
are not substitutable; the VPS grafts locally) and makes a release
`x86_64-desktop-DATE-COMMIT-ATTEMPT` with:

- `roguix-x86_64-desktop.nar.zst`: `guix archive --export` of
  `publish.txt`, signed with the builder key;
- `publish.txt`: the closure's items neither bordeaux nor
  roguix.frolow.dev serves;
- `vps-fetch.txt`: the items bordeaux serves, which the VPS substitutes
  from there, since an import needs every reference valid;
- `vps-has.txt`, unless empty: the items roguix.frolow.dev already
  serves, so the VPS has them and they are not exported again;
- `nonguix-only.txt`, unless empty: items only nonguix serves, exported,
  since the VPS substitutes only from bordeaux.

A run whose closure bordeaux and roguix.frolow.dev serve entirely makes no
release and passes; its log says so. `scripts/desktop-split` fails the run
on a server answering a narinfo request with anything but 200 or 404, on
any unfree item in the closure, on Broadcom's `wl` (its licence does not
allow distributing it built) and on per-machine items.

The VPS pulls the newest release with `scripts/vps-import`; CI has no
access to the VPS. The importing daemon must trust the builder key
(`modules/roguix/builder.pub`): on Guix System through `authorized-keys` in
`guix-service-type` (`guix archive --authorize` lasts only until the next
reconfigure), elsewhere with `guix archive --authorize`.

The builder key signs what the VPS imports and republishes under its own
key, which Roguix VMs trust: keep `BUILDER_SIGNING_KEY` to workflows on
`main`.

The job substitutes from bordeaux, nonguix and roguix.frolow.dev, so once
roguix.frolow.dev serves an earlier export for this pin it only downloads.
A cold build compiles the 22 items no server serves (the Hyprland 0.56
stack, quickshell, wayland 1.26, ttfx and the Roguix packages) on the
runner, with their inputs from bordeaux; nobody has timed that on a
runner. If it ever exceeds the 350-minute job limit, `actions/cache` does
not help (it cannot restore `/gnu/store` and the daemon's database): split
the build into jobs that pass `guix archive --export` of their outputs to
the next as artifacts, or publish a build from another machine first.
