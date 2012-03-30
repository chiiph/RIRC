(require 'json)
(require 'xml-rpc)
(require 'notify)

(defvar rirc-timer nil
  "")

(defvar rirc-history nil
  "")

(defvar rirc-separator "--------------------"
  "")

(defvar rirc-nick-color "#5288DB"
  "")

(defvar rirc-highlight-bg "#FF6600"
  "")

(defvar rirc-join-part-color "#71C42B"
  "")

(defvar rirc-highlight-str "chiiph"
  "")

(defvar rirc-host "localhost"
  "Host to which the client will connect")

(defvar rirc-port "8080"
  "Port used to connect")

(defvar rirc-networks []
  "Network array")

(defstruct rirc-channel
  "Channel structure"
  name lines network)

(defstruct rirc-network
  "Network structure"
  name channels)

(defvar rirc-current-network nil
  "Current network for the buffer")

(defvar rirc-current-channel nil
  "Current channel for the buffer")

(defvar rirc-current-channel-older-line 0
  "Age of the older line in the buffer")

(defvar rirc-cert "~/.config/rirc/rirc.pem"
  "")

(defvar rirc-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map text-mode-map)
    (define-key map (kbd "TAB") 'rirc-autocomplete)
    (define-key map (kbd "RET") 'rirc-send)
    map))

(defvar rirc-user ""
  "")

(defvar rirc-password ""
  "")

(defvar rirc-mode-line nil
  "")

(defvar rirc-mode-string nil
  "")

(defun rirc-init ()
  ""
  (interactive)
  (save-excursion
    (setq tls-program '((concat "gnutls-cli -p %p %h --protocols ssl3 --x509cafile "
                                rirc-cert)))
    (setq xml-rpc-debug 0)
    (rirc-initial-fetch)
    (rirc-start-timer)))

(defun rirc-mode ()
  "RIRC client major mode"
  (interactive)
  (kill-all-local-variables)
  (setq major-mode 'rirc-mode)
  (setq mode-name "RIRC")
  (setq mess-up-minibuffer-p nil)
  (setq url-show-status nil)
  (setq nomsg t)
  (use-local-map rirc-mode-map)
  (make-local-variable 'rirc-current-network)
  (make-local-variable 'rirc-current-channel)
  (make-local-variable 'rirc-current-channel-older-line)
  (make-local-variable 'rirc-mode-line)
  (run-hooks 'rirc-mode-hooks))

(defun rirc-get-host ()
  ;; (format "https://%s:%s/"
  (format "http://%s:%s/"
          rirc-host
          rirc-port))

(defun get-networks ()
  (let ((json-object-type 'hash-table)
        (json-key-type 'string))
    (gethash "networks" (json-read-from-string
                         (xml-rpc-method-call
                          (rirc-get-host)
                          'get_networks)))))

(defun get-channels (network)
  (let ((json-object-type 'hash-table)
        (json-key-type 'string))
    (gethash "channels" (json-read-from-string
                         (xml-rpc-method-call
                          (rirc-get-host)
                          'get_channels network)))))

(defun get-lines (network channel from count older-than)
  (let ((json-object-type 'hash-table)
        (json-key-type 'string))
    (gethash "lines" (json-read-from-string
                      (xml-rpc-method-call
                       (rirc-get-host)
                       'get_lines network channel from count older-than)))))

(defun send-msg (msg)
  (if (string-equal (substring rirc-current-channel 0 1) "#")
      (xml-rpc-method-call
       (rirc-get-host)
       'say rirc-current-network rirc-current-channel msg)
    (progn
      (xml-rpc-method-call
       (rirc-get-host)
       'msg rirc-current-network rirc-current-channel msg))))

(defun get-nick ()
  (xml-rpc-method-call
   (rirc-get-host)
   'nick rirc-current-network))

(defun get-names ()
  (let ((json-object-type 'hash-table)
        (json-key-type 'string))
    (gethash "names" (json-read-from-string
                      (xml-rpc-method-call
                       (rirc-get-host)
                       'names rirc-current-network rirc-current-channel)))))

(defun rirc-ping ()
  (xml-rpc-method-call
   (rirc-get-host)
   'ping rirc-current-network ""))

(defun rirc-names ()
  (interactive)
  (save-excursion
    (if (eq major-mode 'rirc-mode)
        (let ((inhibit-read-only t))
          (setq names (coerce (get-names) 'list))
          (setq names-str (mapconcat 'identity names ", "))
          (end-of-buffer)
          (search-backward rirc-separator nil t)
          (insert (format "%s\n"
                          names-str))
          (end-of-buffer)))))

(defun rirc-join (channel)
  (interactive "sJoin channel: ")
  (xml-rpc-method-call
   (rirc-get-host)
   'join rirc-current-network channel))

(defun rirc-part ()
  (interactive)
  (xml-rpc-method-call
   (rirc-get-host)
   'leave rirc-current-network rirc-current-channel))

(defun rirc-close ()
  (interactive)
  (xml-rpc-method-call
   (rirc-get-host)
   'close rirc-current-network rirc-current-channel)
  (kill-buffer))

(defun rirc-query (nick)
  (interactive "sQuery nick: ")
  (xml-rpc-method-call
   (format "http://%s:%s/"
           rirc-host
           rirc-port)
   'query rirc-current-network nick))

(defun rirc-initial-fetch ()
  "Fetches the initial state for RIRC"
  (let* ((networks (get-networks))
         (networks-length (length networks))
         (i 0))
    (save-excursion
      (setq rirc-networks networks)
      (while (< i networks-length)
        (let* ((channels (get-channels (aref networks i)))
               (channel-length (length channels))
               (j 0))
          (while (< j channel-length)
            (set-buffer (get-buffer-create (format "*rirc-%s*"
                                                   (aref channels j))))
            (rirc-mode)
            (setq rirc-current-network (aref networks i))
            (setq rirc-current-channel (aref channels j))
            (end-of-buffer)
            (if (not (search-backward rirc-separator nil t))
                (insert (format "%s\n"
                                rirc-separator)))
            (rirc-insert-formatted-lines (get-lines (aref networks i) (aref channels j) 0 400 -1)
                                         t t)
            (setq j (+ 1 j))))
        (setq i (+ 1 i))))))

(defun rirc-update ()
  (let* ((networks (get-networks))
         (networks-length (length networks))
         (i 0))
    (save-excursion
      (setq rirc-networks networks)
      (while (< i networks-length)
        (let* ((channels (get-channels (aref networks i)))
               (channel-length (length channels))
               (j 0))
          (while (< j channel-length)
            (if (not (member (get-buffer (format "*rirc-%s*"
                                                 (aref channels j)))
                             (buffer-list)))
                (progn
                  (set-buffer (get-buffer-create (format "*rirc-%s*"
                                                         (aref channels j))))
                  (rirc-mode)
                  (setq rirc-current-network (aref networks i))
                  (setq rirc-current-channel (aref channels j))
                  (end-of-buffer)
                  (if (not (search-backward rirc-separator nil t))
                      (insert (format "%s\n"
                                      rirc-separator)))
                  (rirc-update-buffer t)))
            (setq j (+ 1 j)))
          (setq i (+ 1 i))))
      (dolist (buffer (buffer-list))
        (progn
          (set-buffer buffer)
          (if (eq major-mode 'rirc-mode)
              (rirc-update-buffer))))
      (rirc-update-mode-line))))

(defun rirc-insert-formatted-lines (lines on-beginning &optional initial)
  (let ((lines-length (length lines))
        (k 0)
        (inhibit-read-only t))
    (while (< k lines-length)
      (save-window-excursion
        (save-excursion
          (save-restriction
            (widen)
      (let ((line (aref lines k)))
        (if on-beginning
            (beginning-of-buffer)
          (progn
            (end-of-buffer)
            (search-backward rirc-separator nil t)))
        (setq date-str (format-time-string "%d/%m/%y-%H:%M:%S"
                                           (seconds-to-time (aref line 0))))
        (setq nick-str (car (split-string (aref line 1) "!")))
        (if (string-equal nick-str "#")
            (setq nick-str (get-nick)))
        (if (string-equal nick-str "@")
            (setq nick-str "---"))
        (setq nick-str (propertize
                        (format "<%s>"
                                nick-str)
                        'font-lock-face '(:foreground "#5288DB")))
        (setq line-str (format "%s :: %s %s\n"
                               date-str
                               nick-str
                               (aref line 2)))
         (if (and (string-match rirc-highlight-str (aref line 2))
                  (rirc-notify nick-str (aref line 2) initial))
             (setq line-str (propertize
                             (format "%s :: %s %s\n"
                                     date-str
                                     nick-str
                                     (aref line 2))
                             'font-lock-face '(:background "#FF6600")))
           (if (> (length (cdr (split-string rirc-current-channel "!"))) 0)
               (rirc-notify nick-str (aref line 2) initial)))
         (insert line-str)
        (if (not rirc-mode-line)
            (setq rirc-mode-line rirc-current-channel)))
      (setq k (+ 1 k))))))
    (if (> lines-length 0)
        (setq rirc-current-channel-older-line (max (aref (aref lines (- lines-length 1)) 0)
                                                   (aref (aref lines 0) 0)
                                                   rirc-current-channel-older-line)))
    (save-window-excursion
      (save-restriction
        (widen)
    (beginning-of-buffer)
    (setq prop-start (point))
    (end-of-buffer)
    (search-backward rirc-separator nil t)
    (setq prop-end (point))
    (put-text-property prop-start prop-end 'read-only t)
    (end-of-buffer)))
))

(defun rirc-notify (nick line &optional initial)
  (if (and (not (string-equal nick-str "<->"))
           (not (string-equal nick-str "<@>"))
           (not (string-equal nick-str "<--->"))
           (not initial)
           (not (member (current-buffer) (mapcar 'window-buffer (window-list)))))
      (progn
        (notify nick line)
        (setq rirc-mode-line (propertize
                              (car (split-string rirc-current-channel "!"))
                              'font-lock-face '(:foreground "#FF6600")))
        t)
    nil))

(defun rirc-update-buffer (&optional on-beg)
  (interactive)
  (rirc-insert-formatted-lines (get-lines
                                rirc-current-network
                                rirc-current-channel
                                0 400
                                rirc-current-channel-older-line)
                               on-beg))

(defun rirc-start-timer ()
  (interactive)
  (setq rirc-timer (run-with-timer 1 5 'rirc-update)))

(defun rirc-stop-timer ()
  (interactive)
  (cancel-timer rirc-timer))

(defun rirc-stop ()
  (interactive)
  (rirc-stop-timer)
  (mapcar (lambda (buffer)
              (progn
                (set-buffer buffer)
                (if (eq major-mode 'rirc-mode)
                    (kill-buffer))))
          (buffer-list)))

(defun rirc-send ()
  (interactive)
  (save-excursion
    (end-of-buffer)
    (beginning-of-line)
    (setq msg-start (point))
    (end-of-line)
    (setq msg-stop (point))
    (send-msg (buffer-substring msg-start msg-stop))
    (beginning-of-line)
    (kill-line)))

(defun rirc-update-mode-line ()
  (save-excursion
    (setq global-mode-string (delete '(t rirc-mode-string)
                                     global-mode-string))
    (setq current-mode-line "a")
    (dolist (buffer (buffer-list) current-mode-line)
      (progn
        (set-buffer buffer)
        (if (eq major-mode 'rirc-mode)
            (progn
              (if rirc-mode-line
                  (progn
                    (setq current-mode-line (concat current-mode-line ", "))
                    (setq current-mode-line (concat current-mode-line rirc-mode-line))))
              (if (member (current-buffer) (mapcar 'window-buffer (window-list)))
                  (setq rirc-mode-line nil))))))
    (setq rirc-mode-string current-mode-line)
    (add-to-list 'global-mode-string
                 '(t rirc-mode-string))
    (force-mode-line-update 'all)))

(add-hook 'window-configuration-change-hook 'rirc-update-mode-line)

(provide 'rirc)