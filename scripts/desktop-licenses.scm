;; For every package in the closure (implicit inputs included) of the
;; packages of a manifest, print its ungrafted output paths with the
;; package's name and licence names: "PATH NAME LICENCE,...", spaces in a
;; licence name turned into "_".  scripts/desktop-split reads it.
;;
;;   guix repl -L MODULES -- scripts/desktop-licenses.scm MANIFEST
(use-modules (guix) (guix grafts) (guix derivations) (guix licenses)
             (guix profiles) (ice-9 match) (srfi srfi-1))

(define packages
  (filter-map (lambda (entry)
                (let ((item (manifest-entry-item entry)))
                  (and (package? item) item)))
              (manifest-entries (load (canonicalize-path
                                       (cadr (command-line)))))))

(define (license-names package)
  (match (package-license package)
    ((? license? l) (list (license-name l)))
    ((l ...) (map (lambda (x) (if (license? x) (license-name x) "unknown")) l))
    (_ (list "unknown"))))

(define (underscores name)
  (string-map (lambda (c) (if (char=? c #\space) #\_ c)) name))

(with-store store
  (parameterize ((%graft? #f))
    (for-each
     (lambda (package)
       (for-each
        (match-lambda
          ((output . path)
           (format #t "~a ~a ~a~%"
                   path
                   (package-full-name package)
                   (string-join (map underscores (license-names package))
                                ","))))
        (derivation->output-paths
         (package-derivation store package "x86_64-linux"))))
     (package-closure packages #:system "x86_64-linux"))))
