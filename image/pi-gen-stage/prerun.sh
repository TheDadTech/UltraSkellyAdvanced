#!/usr/bin/env bash
set -e

if [[ ! -d "${ROOTFS_DIR}" ]]; then
  copy_previous
fi
