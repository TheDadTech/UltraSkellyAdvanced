#!/usr/bin/env bash
set -e

install -m 0644 \
  files/skelly-ai-source.tar.gz \
  "${ROOTFS_DIR}/root/skelly-ai-source.tar.gz"
install -m 0755 \
  files/install-chroot.sh \
  "${ROOTFS_DIR}/root/install-skelly-ai-image.sh"
install -m 0644 \
  files/SKELLY-AI-README.txt \
  "${ROOTFS_DIR}/boot/firmware/SKELLY-AI-README.txt"

on_chroot <<'EOF'
/root/install-skelly-ai-image.sh
rm -f /root/install-skelly-ai-image.sh /root/skelly-ai-source.tar.gz
EOF
