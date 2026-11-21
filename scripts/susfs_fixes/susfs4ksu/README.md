# Vendored SUSFS Patches (Fail-Safe)

This directory contains vendored copies of SUSFS kernel patches from
https://gitlab.com/simonpunk/susfs4ksu.git for use as a fail-safe when the
upstream clone is unavailable or missing a required patch file.

## Directory Structure

Each kernel version has its own subdirectory:

```
kernel_patches/
  android12-5.10/
    50_add_susfs_in_gki-android12-5.10.patch
    fs/susfs.c
    include/linux/susfs.h
    include/linux/susfs_def.h
    KernelSU/10_enable_susfs_for_ksu.patch
  android13-5.10/
    ...
  android16-6.12/
    ...
```

## Fallback Logic (in .github/workflows/build.yml)

The build workflow tries upstream first:
1. Clones `https://gitlab.com/simonpunk/susfs4ksu.git -b gki-<android>-<kernel>`
2. Checks if `kernel_patches/50_add_susfs_in_gki-<android>-<kernel>.patch` exists in the clone
3. If the clone fails OR the patch file is missing → falls back to vendored copies here

## Populating Vendored Patches

All patch files are already populated from upstream `gitlab.com/simonpunk/susfs4ksu.git`.
To update a version, clone upstream and copy:

```bash
# For each version, clone upstream and copy:
git clone https://gitlab.com/simonpunk/susfs4ksu.git -b gki-android16-6.12
cp susfs4ksu/kernel_patches/50_add_susfs_in_gki-android16-6.12.patch scripts/susfs_fixes/susfs4ksu/kernel_patches/android16-6.12/
cp susfs4ksu/kernel_patches/fs/susfs.c scripts/susfs_fixes/susfs4ksu/kernel_patches/android16-6.12/fs/
cp susfs4ksu/kernel_patches/include/linux/susfs.h scripts/susfs_fixes/susfs4ksu/kernel_patches/android16-6.12/include/linux/
cp susfs4ksu/kernel_patches/include/linux/susfs_def.h scripts/susfs_fixes/susfs4ksu/kernel_patches/android16-6.12/include/linux/
cp susfs4ksu/kernel_patches/KernelSU/10_enable_susfs_for_ksu.patch scripts/susfs_fixes/susfs4ksu/kernel_patches/android16-6.12/KernelSU/
```

Note: `gki-android17-6.18` is NOT vendored here — it is handled separately by the
existing `scripts/susfs_fixes/susfs618_kernel_patches/` port and should remain unchanged.
