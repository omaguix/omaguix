;; Only tests generate keys. Never read or overwrite /etc/guix signing keys.
(use-modules (guix store) (gcrypt pk-crypto))
(define directory (getenv "STATIC_TEST_DIR"))
(define (write-key name key)
  (call-with-output-file (string-append directory "/" name)
    (lambda (port) (display (canonical-sexp->string key) port)))
  (chmod (string-append directory "/" name) #o600))
;; The parameters of `guix archive --generate-key' (guix/scripts/archive.scm),
;; which made the real signing key.
(define parameters
  (string->canonical-sexp "(genkey (ecdsa (curve Ed25519) (flags rfc6979)))"))
(define pair (generate-key parameters))
(write-key "test.pub" (find-sexp-token pair 'public-key))
(write-key "test.sec" (find-sexp-token pair 'private-key))
(write-key "wrong.pub" (find-sexp-token (generate-key parameters) 'public-key))
(with-store store
  (let ((plain (add-text-to-store store "roguix-static-test" "tiny test item\n"))
        (compressed (add-to-store store "roguix-static-test.gz" #t "sha256"
                                  (string-append directory "/payload.gz"))))
    (call-with-output-file (string-append directory "/items.txt")
      (lambda (port) (format port "~a~%~a~%" plain compressed)))))
