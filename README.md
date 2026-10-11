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
| `scripts/desktop-licenses.scm`, `scripts/desktop-split` | the job's licence check and closure split |
| `scripts/ci-install-guix` | installs Guix on the runner |
| `modules/roguix/builder.pub` | CI's archive signing key; the secret half is the `BUILDER_SIGNING_KEY` Actions secret |
| `keys/substitutes.nonguix.org.pub` | nonguix's substitute key |
| `scripts/vps-import` | on the VPS: import CI's newest release into guix publish |

This repository has no packages of its own: the desktop's modules live in
try-roguix.

## Guix on the runners

The workflow installs Guix with `scripts/ci-install-guix`: the Guix
1.5.0 binary tarball from `ftpmirror.gnu.org`, or, if that fails, the copy
in this repository's `guix-binary-1.5.0` release, checked against the
sha256 pinned in the script, with a root guix-daemon and bordeaux's and
ci's keys authorized; it never runs `guix pull` (the job uses
`guix time-machine`). To update: verify the new tarball's `.sig` from
`ftp.gnu.org` with `gpg --verify` against the release signing key, change
`VERSION` and `SHA256` in the script, and upload the tarball to a release
`guix-binary-VERSION` here.

## The Roguix desktop's feed

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
