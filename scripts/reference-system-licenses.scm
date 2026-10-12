;; Print ungrafted package output licences for the reference system, including
;; packages referenced only by services, gexps, and their implicit inputs.
;; Usage: GUIX_SYSTEM=SYSTEM guix repl -L MODULES -- scripts/reference-system-licenses.scm
;; Each native runner uses the same system and graft setting as Build.
(use-modules (gnu system) (guix) (guix packages) (guix gexp)
             (guix grafts) (guix derivations) (guix licenses)
             (guix monads) (ice-9 match) (srfi srfi-1)
             (roguix system))

(define system
  (or (getenv "GUIX_SYSTEM")
      (error "GUIX_SYSTEM must name the reference system's architecture")))
(unless (member system '("aarch64-linux" "x86_64-linux"))
  (error "unsupported GUIX_SYSTEM" system))
(define packages '())

;; Observe package lowering while evaluating the entire operating system.
;; Merely inspecting operating-system-packages misses service dependencies.
;; Derivation inputs have no inverse mapping to their original package objects
;; (including service-local variants), so retain this lowering hook.  Guix's
;; package record type is private; resolve it explicitly at the pinned API.
;; Delegate unchanged to Guix's native/cross package lowering procedures.
(define-gexp-compiler
  (license-package-compiler (package (@@ (guix packages) <package>)) system target)
  (set! packages (cons package packages))
  (if target
      (package->cross-derivation package target system)
      (package->derivation package system)))

(define (license-names package)
  (match (package-license package)
    ((? license? l) (list (license-name l)))
    ((l ...) (map (lambda (x) (if (license? x) (license-name x) "unknown")) l))
    (_ (list "unknown"))))

(define (underscores name)
  (string-map (lambda (c) (if (char=? c #\space) #\_ c)) name))

(with-store store
  (parameterize ((%graft? #f)
                 (%current-system system))
    (run-with-store store
      (operating-system-derivation %roguix-reference-system)
      #:system system)
    (when (null? packages)
      (error "reference system lowering observed no packages"))
    (for-each
     (lambda (package)
       (for-each
        (match-lambda
          ((output . path)
           (format #t "~a ~a ~a~%" path (package-full-name package)
                   (string-join (map underscores (license-names package)) ","))))
        (derivation->output-paths (package-derivation store package system))))
     (package-closure (delete-duplicates packages eq?) #:system system))))
