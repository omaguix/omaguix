# roguix

Roguix's hand-maintained Guix modules: packages Guix does not have yet,
built by GitHub Actions and served by `https://roguix.frolow.dev`.

| Repository | What it is |
| --- | --- |
| [roguixos/roguix](https://github.com/roguixos/roguix) | this one: packages, CI |
| [rofrol/try-roguix](https://github.com/rofrol/try-roguix) | the macOS app and the Roguix desktop guest |
| [rofrol/roguix-channel](https://github.com/rofrol/roguix-channel) | the desktop's channel, generated from try-roguix |

## Layout

| Path | What it is |
| --- | --- |
| `channels.scm` | the Guix commit CI builds with and the VPS runs |
| `modules/roguix/packages/` | packages: `postgresql-17` in `(roguix packages databases)`, `node-22` in `(roguix packages node)` |
| `manifests/x86_64.scm` | what CI builds for x86_64 |
| `modules/roguix/builder.pub` | CI's archive signing key; the secret half is the `BUILDER_SIGNING_KEY` Actions secret |
| `channels-desktop.scm` | the Roguix desktop's Guix and nonguix commits |
| `manifests/x86_64-desktop.scm` | what CI builds for the Roguix desktop on x86_64 |
| `scripts/desktop-licenses.scm`, `scripts/desktop-split` | the desktop job's licence check and closure split |
| `keys/substitutes.nonguix.org.pub` | nonguix's substitute key, for the desktop job |
| `scripts/vps-import` | on the VPS: import CI's newest release into guix publish |

## Guix pin

Every store path depends on the Guix commit, so CI and the VPS use the one
in `channels.scm`; otherwise the VPS asks roguix.frolow.dev for paths CI
never built and compiles them itself. To move on: change the commit, let
CI build and publish, `scripts/vps-import` on the VPS, then
`guix pull -C channels.scm` there and reconfigure.

## Guix on the runners

Both workflows install Guix with `scripts/ci-install-guix`: the Guix
1.5.0 binary tarball from `ftpmirror.gnu.org`, or, if that fails, the copy
in this repository's `guix-binary-1.5.0` release, checked against the
sha256 pinned in the script, with a root guix-daemon and bordeaux's and
ci's keys authorized; it never runs `guix pull` (the jobs use
`guix time-machine`). To update: verify the new tarball's `.sig` from
`ftp.gnu.org` with `gpg --verify` against the release signing key, change
`VERSION` and `SHA256` in the script, and upload the tarball to a release
`guix-binary-VERSION` here.

## Publishing

On a push to `main` touching packages, the manifest or the pin,
`.github/workflows/build-x86_64.yml` builds `manifests/x86_64.scm` without
grafts (grafts are not substitutable; the VPS grafts locally) and makes a
release `x86_64-DATE-COMMIT-ATTEMPT` with:

- `roguix-x86_64.nar.zst`: `guix archive --export` of `publish.txt`,
  signed with the builder key;
- `publish.txt`: the closure's items bordeaux does not serve;
- `vps-fetch.txt`: the rest, which the VPS substitutes from bordeaux,
  since an import needs every reference valid.

The VPS pulls it with `scripts/vps-import`; CI has no access to the VPS.
The importing daemon must trust the builder key
(`modules/roguix/builder.pub`): on Guix System through `authorized-keys` in
`guix-service-type` (`guix archive --authorize` lasts only until the next
reconfigure), elsewhere with `guix archive --authorize`.

The builder key signs what the VPS imports and republishes under its own
key, which Roguix VMs trust: keep `BUILDER_SIGNING_KEY` to workflows on
`main`.

## The Roguix desktop's feed

The desktop (try-roguix's Roguix modules) runs another pin, Guix 7e74121a
with nonguix c0192e90 (`channels-desktop.scm`), so it has its own job and
release, never mixed with the server's. On a push to `main` touching its
files, `.github/workflows/build-x86_64-desktop.yml` checks out
[rofrol/try-roguix](https://github.com/rofrol/try-roguix) at the commit it
pins (`TRY_ROGUIX_COMMIT`; rofrol/roguix-channel lags behind it), builds
the 16 packages of `manifests/x86_64-desktop.scm` without grafts, and makes
a release `x86_64-desktop-DATE-COMMIT-ATTEMPT` with
`roguix-x86_64-desktop.nar.zst`, `publish.txt`, `vps-fetch.txt` and
`nonguix-only.txt` (items only nonguix serves: exported, since the VPS
substitutes only from bordeaux). `scripts/desktop-split` fails the run on
any unfree item in the closure, on Broadcom's `wl` (its licence does not
allow distributing it built) and on per-machine items. The VPS imports it
with `scripts/vps-import -p x86_64-desktop`.

The job substitutes from bordeaux, nonguix and roguix.frolow.dev, so once
roguix.frolow.dev serves an earlier export for this pin it only downloads.
A cold build compiles the 22 items no server serves (the Hyprland 0.56
stack, quickshell, wayland 1.26, ttfx and the Roguix packages) on the
runner, with their inputs from bordeaux; nobody has timed that on a
runner. If it ever exceeds the 350-minute job limit, `actions/cache` does
not help (it cannot restore `/gnu/store` and the daemon's database): split
the build into jobs that pass `guix archive --export` of their outputs to
the next as artifacts, or publish a build from another machine first.
