;; What CI builds for the Roguix desktop on x86_64 and publishes on
;; roguix.frolow.dev: the packages of try-roguix's Roguix modules
;; (guest/guix/modules, loaded with -L) that the MacBook's desktop uses, as
;; guix-x86_64-iso-omguix's roguix-packages.scm selects them from its
;; system.  Build with the Guix of channels-desktop.scm.
;;
;; The packages are named, not taken from the modules' exports, because
;; several are private bindings (hyprland, wayland, quickshell); a name
;; that matches no package, or two, is an error.  Update the list with the
;; try-roguix pin in .github/workflows/build-x86_64-desktop.yml.
(use-modules (guix packages)
             (guix profiles)
             (ice-9 match)
             (srfi srfi-1))

(define %desktop-packages
  '("aquamarine@0.14.0"
    "fastfetch@2.66.0"
    "font-jetbrains-mono-nerd@3.5.1"
    "glaze@7.2.0"
    "hyprland@0.56.1"
    "hyprutils@0.14.2"
    "macos-style-cursor-theme@2.0.1"
    "omarchy@4.0.4"
    "quickshell@0.3.1"
    "roguix-agent@1"
    "roguix-omarchy-compat@1"
    "roguix-timezone@1"
    "ttfx@0.5.0"
    "wayland@1.26.0"
    "wayland-protocols@1.49"
    "xdg-desktop-portal-hyprland@1.3.12"))

(define %roguix-modules
  '((roguix apps) (roguix cursors) (roguix integrations) (roguix omarchy)
    (roguix packages) (roguix services) (roguix system) (roguix ttfx)))

;; Every package bound in the modules, public or private.
(define %roguix-packages
  (delete-duplicates
   (append-map (lambda (name)
                 (hash-fold (lambda (sym var acc)
                              (if (and (variable-bound? var)
                                       (package? (variable-ref var)))
                                  (cons (variable-ref var) acc)
                                  acc))
                            '()
                            (module-obarray (resolve-module name))))
               %roguix-modules)
   eq?))

(define (desktop-package full-name)
  (match (filter (lambda (package)
                   (string=? (package-full-name package) full-name))
                 %roguix-packages)
    ((package) package)
    (() (error "no Roguix package named" full-name))
    (packages (error "several Roguix packages named" full-name))))

(packages->manifest (map desktop-package %desktop-packages))
