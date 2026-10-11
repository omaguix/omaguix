;; The Guix that CI builds the Roguix desktop with
;; (.github/workflows/build-x86_64-desktop.yml): the Roguix desktop's pin,
;; try-roguix's guest/guix/modules/roguix/guix-commit, with nonguix for the
;; MacBook's kernel, as guix-x86_64-iso-omguix's channels-roguix.lock.scm.
;; Separate from channels.scm, the server's pin: a different commit changes
;; every store path, so each pin has its own job and release.
(list (channel
       (name 'nonguix)
       (url "https://gitlab.com/nonguix/nonguix")
       (branch "master")
       (commit "c0192e90a52cafb4d33b04734cbe9bbedd703a04")
       (introduction
        (make-channel-introduction
         "897c1a470da759236cc11798f4e0a5f7d4d59fbc"
         (openpgp-fingerprint
          "2A39 3FFF 68F4 EF7A 3D29  12AF 6F51 20A0 22FB B2D5"))))
      (channel
       (name 'guix)
       (url "https://git.guix.gnu.org/guix.git")
       (branch "master")
       (commit "7e74121a40a8308166e328a23647cf6f3768e6c8")
       (introduction
        (make-channel-introduction
         "9edb3f66fd807b096b48283debdcddccfea34bad"
         (openpgp-fingerprint
          "BBB0 2DDF 2CEA F6A8 0D1D  E643 A2A0 6DF2 A33A 54FA")))))
